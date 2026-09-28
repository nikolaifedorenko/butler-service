"""Правила расчёта (настройки) + служебные эндпоинты: health, сид, статистика."""
from __future__ import annotations

import json
import threading
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import Principal, audit, current_principal, require_admin, require_manager
from ..db import SessionLocal, get_db
from ..deps import local_date, now_local
from ..models import Employee, Punch, ScheduleEntry, TimesheetRow, Setting, User
from ..base_schedule import DEFAULT_BASE, load_base_config, save_base_config
from ..doc_templates import load_doc_templates, save_doc_templates
from ..timesheet import DEFAULT_RULES, load_rules, rule_options

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings_api(principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    rules = load_rules(db)
    meta = {o["key"]: o for o in rule_options()}
    items = [{"key": k, "value": rules[k], "default": DEFAULT_RULES[k],
              "description": meta[k]["description"], "type": meta[k]["type"]} for k in DEFAULT_RULES]
    counts = {
        "employees": db.scalar(select(func.count(Employee.id)).where(Employee.active.is_(True))) or 0,
        "users": db.scalar(select(func.count(User.id))) or 0,
        "schedule_entries": db.scalar(select(func.count(ScheduleEntry.id))) or 0,
        "punches": db.scalar(select(func.count(Punch.id))) or 0,
        "timesheet_rows": db.scalar(select(func.count(TimesheetRow.id))) or 0,
    }
    return {"rules": rules, "items": items, "counts": counts,
            "base": load_base_config(db), "doc": load_doc_templates(db)}


class DocIn(BaseModel):
    company: str = ""
    director: str = ""
    vacation: str = ""
    vacation_unpaid: str = ""
    day_off_hours: str = ""       # заявление на выходной за ранее отработанные часы
    time_off_request: str = ""    # заявление «отпросился с … до …»


@router.put("/doc")
def update_doc(payload: DocIn, principal: Principal = Depends(require_manager),
               db: Session = Depends(get_db)):
    """Шаблоны заявлений и реквизиты организации для печати документов."""
    doc = save_doc_templates(db, payload.model_dump())
    audit(db, principal, "doc_templates_update", "settings", {})
    db.commit()
    return {"ok": True, "doc": doc}


class BaseIn(BaseModel):
    cycle: str = "2/2"
    anchor: str = "2024-01-01"
    groups: dict = {}


@router.put("/base")
def update_base(payload: BaseIn, principal: Principal = Depends(require_manager),
                db: Session = Depends(get_db)):
    """Базовый цикл объекта: какие дни рабочие у Смены 1 / Смены 2 / Администрации — на все месяцы."""
    import datetime as _dt

    from ..base_schedule import _flag_for

    try:
        _dt.date.fromisoformat(payload.anchor)
    except ValueError:
        raise HTTPException(status_code=422, detail="Опорная дата должна быть в формате ГГГГ-ММ-ДД")
    cfg = {"cycle": payload.cycle, "anchor": payload.anchor, "groups": payload.groups or DEFAULT_BASE["groups"]}
    probe = local_date()
    for name, g in cfg["groups"].items():
        try:
            _flag_for(cfg, g, probe)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Блок «{name}»: {exc}")
    save_base_config(db, cfg)
    audit(db, principal, "base_cycle_update", "settings", cfg)
    db.commit()
    return {"ok": True, "base": load_base_config(db)}


class RuleIn(BaseModel):
    key: str
    value: str


@router.put("")
def update_settings(payload: list[RuleIn], principal: Principal = Depends(require_manager),
                    db: Session = Depends(get_db)):
    """Сохранить правила расчёта (доступно администратору)."""
    changed = {}
    for item in payload:
        if item.key not in DEFAULT_RULES:
            raise HTTPException(status_code=422, detail=f"Неизвестный параметр: {item.key}")
        setting = db.get(Setting, item.key)
        if setting is None:
            setting = Setting(key=item.key, value=item.value,
                              description=next((o["description"] for o in rule_options() if o["key"] == item.key), ""))
            db.add(setting)
        else:
            setting.value = item.value
        changed[item.key] = item.value
    audit(db, principal, "settings_update", "rules", changed)
    db.commit()
    return {"ok": True, "rules": load_rules(db)}


# ─────────────── фоновый пересчёт табеля ───────────────
# Пересчёт месяца на большом штате — тысячи строк: держать для этого HTTP-запрос
# открытым нельзя (таймаут обратного прокси, занятый воркер). Поэтому background=1
# запускает работу в отдельном потоке со своей сессией, а клиент опрашивает статус.
_JOBS_LOCK = threading.Lock()
_RECALC_JOBS: list[dict] = []
MAX_JOBS_KEPT = 10


def _register_job(job: dict) -> None:
    with _JOBS_LOCK:
        _RECALC_JOBS.insert(0, job)
        del _RECALC_JOBS[MAX_JOBS_KEPT:]


def _update_job(job_id: str, **fields) -> None:
    with _JOBS_LOCK:
        for job in _RECALC_JOBS:
            if job["id"] == job_id:
                job.update(fields)
                return


def running_job() -> Optional[dict]:
    with _JOBS_LOCK:
        return next((j for j in _RECALC_JOBS if j["status"] == "running"), None)


def _recalc_worker(job_id: str, year: int, month: int, actor_id: Optional[int],
                   actor_name: str) -> None:
    """Поток пересчёта: собственная сессия, аудит и статус пишем сами."""
    from ..models import AuditLog, utcnow
    from ..timesheet import month_bounds, recalc_range

    db = SessionLocal()
    try:
        first, last = month_bounds(year, month)
        count = recalc_range(db, first, last)
        db.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action="recalc_all",
                        target=f"{year}-{month:02d}",
                        payload_json=json.dumps({"rows": count, "background": True}),
                        ts=utcnow()))
        db.commit()
        _update_job(job_id, status="done", days=count,
                    finished_at=now_local().isoformat(timespec="seconds"))
    except Exception as exc:                       # noqa: BLE001 — статус виден клиенту
        db.rollback()
        _update_job(job_id, status="error", error=str(exc)[:500],
                    finished_at=now_local().isoformat(timespec="seconds"))
    finally:
        db.close()


@router.post("/recalc-all")
def recalc_all(year: Optional[int] = None, month: Optional[int] = None, background: bool = False,
               principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Полный пересчёт табеля (нужен после изменения правил округления/ночных).

    background=1 — запустить в фоне и вернуть job_id (клиент опрашивает
    /api/settings/recalc-status). По умолчанию пересчёт синхронный: так его
    вызывают тесты и небольшие базы.
    """
    from ..timesheet import month_bounds, recalc_range

    today = local_date()
    year = year or today.year
    month = month or today.month

    if background:
        busy = running_job()
        if busy is not None:
            return {"ok": False, "started": False, "job_id": busy["id"],
                    "detail": "Пересчёт уже запущен — дождитесь завершения"}
        job_id = uuid.uuid4().hex[:12]
        _register_job({"id": job_id, "year": year, "month": month, "status": "running",
                       "days": None, "error": None, "actor_name": principal.name,
                       "started_at": now_local().isoformat(timespec="seconds"),
                       "finished_at": None})
        threading.Thread(target=_recalc_worker, args=(job_id, year, month,
                                                      principal.user.id, principal.name),
                         name=f"recalc-{job_id}", daemon=True).start()
        return {"ok": True, "started": True, "job_id": job_id, "year": year, "month": month}

    first, last = month_bounds(year, month)
    count = recalc_range(db, first, last)
    audit(db, principal, "recalc_all", f"{year}-{month:02d}", {"rows": count})
    db.commit()
    return {"ok": True, "recalculated_days": count}


@router.get("/recalc-status")
def recalc_status(principal: Principal = Depends(require_manager)):
    """Состояние фонового пересчёта: текущая задача и последние завершённые."""
    with _JOBS_LOCK:
        jobs = [dict(j) for j in _RECALC_JOBS]
    return {"running": any(j["status"] == "running" for j in jobs),
            "current": next((j for j in jobs if j["status"] == "running"), None),
            "jobs": jobs}
