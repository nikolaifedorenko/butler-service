"""Ход смены: отчёт дня и архив, взять и закрыть область, ответы на пункты, фото."""
from __future__ import annotations

import datetime as dt

from fastapi import Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.media import (
    max_upload_bytes,
    read_upload_streaming,
    save_photo_ref,
)
from app.core.permissions import has_perm, require_perm
from app.core.time import now_local

from ..adapters.orm import (
    NightAreaSection,
    NightCheckItem,
    NightInterception,
    NightReport,
)
from ..application.night import (
    SHIFT_START,
    current_shift_date,
    report_dict,
    section_dict,
)
from .night_common import (
    AnswerIn,
    CloseSectionIn,
    InterceptionAck,
    _get_report,
    _get_section,
    _guard_open,
    _guard_section_open,
    _principal_name,
    _report_payload,
    router,
)

# ─────────────────────────── ход смены ───────────────────────────

@router.get("/today")
def today_report(principal: Principal = Depends(require_perm("night.view")), db: Session = Depends(get_db)):
    """Актуальный отчёт текущей ночной смены.

    GET без побочных записей (ревью 20.10.2026, P1): обслуживание — досоздание
    наступивших смен и автозакрытие в 08:00 — выполняет фоновая синхронизация
    (bootstrap/night_sync.py, период settings.night_sync_seconds) и стартовый
    прогон init_db(), а не каждый запрос раздела."""
    shift_d = current_shift_date()
    rep = db.scalar(select(NightReport).where(NightReport.date == shift_d))
    if rep is None:
        # до 20:00 смена действительно ещё не началась; после — отчёт вот-вот
        # создаст фоновый раунд (или стартовый прогон, если сервер только поднялся)
        if now_local() < dt.datetime.combine(shift_d, SHIFT_START):
            note = (f"Ночная смена {shift_d.strftime('%d.%m.%Y')} ещё не началась — "
                    f"отчёт появится в 20:00. Прошлые смены — в «Архиве».")
        else:
            note = (f"Ночная смена {shift_d.strftime('%d.%m.%Y')} началась — отчёт создаётся; "
                    f"обновите страницу через минуту. Прошлые смены — в «Архиве».")
        return {"available": False, "shift_date": shift_d.isoformat(), "note": note}
    return {"available": True, "report": _report_payload(db, rep)}


@router.get("/reports")
def list_reports(limit: int = 60, principal: Principal = Depends(require_perm("night.view")),
                 db: Session = Depends(get_db)):
    """Архив ночных отчётов (супервайзер и выше): список с итогами (чистое чтение)."""
    out = []
    # PERF-01: области и пункты — тремя запросами на весь архив, а не по запросу на отчёт и область
    q = (select(NightReport)
         .options(selectinload(NightReport.areas).selectinload(NightAreaSection.items))
         .order_by(NightReport.date.desc()).limit(min(limit, 365)))
    for rep in db.scalars(q):
        d = report_dict(rep, with_items=False)
        out.append(d)
    return {"reports": out}


@router.get("/reports/{report_id}")
def get_report(report_id: int, principal: Principal = Depends(require_perm("night.view")),
               db: Session = Depends(get_db)):
    rep = _get_report(db, report_id)
    return {"report": _report_payload(db, rep)}


@router.post("/sections/{section_id}/take")
def take_section(section_id: int, payload: InterceptionAck,
                 principal: Principal = Depends(require_perm("night.view")), db: Session = Depends(get_db)):
    """Взять область в работу. Если её уже ведёт другой — предупреждаем и пишем перехват."""
    sec = _get_section(db, section_id)
    rep = _get_report(db, sec.report_id)
    _guard_open(rep)
    me = principal.user.id
    warning = None
    if sec.status == "taken" and sec.taken_by == me:
        return {"ok": True, "section": section_dict(sec), "warning": None, "already": True}
    if sec.status == "taken" and sec.taken_by and sec.taken_by != me:
        if not payload.ack:
            raise HTTPException(status_code=409, detail={
                "interception": True,
                "message": f"Эту область уже проверяет {sec.taken_by_name} "
                           f"(с {sec.taken_at:%H:%M}). Продолжить? Отметка перейдёт вам."})
        db.add(NightInterception(report_id=rep.id, section_id=sec.id,
                                 from_user_id=sec.taken_by, from_user_name=sec.taken_by_name,
                                 to_user_id=me, to_user_name=_principal_name(principal)))
        warning = f"Вы перехватили область у {sec.taken_by_name}"
    if sec.status == "done":
        # по ТЗ область ведёт один человек: закрыть её может кто угодно, а переоткрыть —
        # только тот, кто закрыл (или супервайзер и выше)
        if principal.user.id != sec.closed_by and not has_perm(db, principal, "night.reopen_any"):
            raise HTTPException(status_code=409,
                                detail=f"Область закрыта в {sec.closed_at:%H:%M} — переоткрыть может "
                                       f"тот, кто её закрыл, или супервайзер")
        sec.status = "taken"
        sec.closed_at = None
        warning = "Область переоткрыта"
    sec.status = "taken"
    sec.taken_by = me
    sec.taken_by_name = _principal_name(principal)
    sec.taken_at = now_local()
    audit(db, principal, "night_section_take", f"section:{sec.id}",
          {"area": sec.name, "intercepted": bool(warning and "перехват" in warning)})
    db.commit()
    return {"ok": True, "section": section_dict(sec), "warning": warning}


@router.post("/sections/{section_id}/close")
def close_section(section_id: int, payload: CloseSectionIn | None = None,
                  principal: Principal = Depends(require_perm("night.view")), db: Session = Depends(get_db)):
    """Завершить проверку области.

    По ТЗ закрыть можно и с незаполненными пунктами (останутся «не отмечено») —
    но только после подтверждения; все пункты закрыты — закрываем сразу."""
    sec = _get_section(db, section_id)
    rep = _get_report(db, sec.report_id)
    _guard_open(rep)
    unanswered = [i for i in sec.items if not i.answer]
    force = bool(payload and payload.force_unanswered)
    if unanswered and not force:
        raise HTTPException(status_code=409, detail={
            "unanswered": len(unanswered),
            "message": f"Не отмечено пунктов: {len(unanswered)}. "
                       f"Они останутся как «не отмечено». Закрыть всё равно?"})
    sec.status = "done"
    sec.closed_at = now_local()
    sec.closed_by = principal.user.id
    audit(db, principal, "night_section_close", f"section:{sec.id}",
          {"area": sec.name, "unanswered": len(unanswered)})
    db.commit()
    return {"ok": True, "section": section_dict(sec)}


@router.post("/sections/{section_id}/reopen")
def reopen_section(section_id: int, principal: Principal = Depends(require_perm("night.close")),
                   db: Session = Depends(get_db)):
    sec = _get_section(db, section_id)
    rep = _get_report(db, sec.report_id)
    _guard_open(rep)
    sec.status = "taken"
    sec.closed_at = None
    audit(db, principal, "night_section_reopen", f"section:{section_id}")
    db.commit()
    return {"ok": True, "section": section_dict(sec)}


@router.put("/items/{item_id}/answer")
def answer_item(item_id: int, payload: AnswerIn, principal: Principal = Depends(require_perm("night.view")),
                db: Session = Depends(get_db)):
    """Отметить пункт: ОК / Не ОК (+ комментарий). Перезапись — last write wins."""
    ni = db.get(NightCheckItem, item_id)
    if ni is None:
        raise HTTPException(status_code=404, detail="Пункт не найден")
    sec = _get_section(db, ni.section_id)
    rep = _get_report(db, sec.report_id)
    _guard_open(rep)
    _guard_section_open(sec)
    if payload.answer not in ("ok", "bad", ""):
        raise HTTPException(status_code=400, detail="Неизвестный ответ")
    ni.answer = payload.answer
    ni.comment = payload.comment[:2000]
    ni.answered_by = principal.user.id
    ni.answered_by_name = _principal_name(principal)
    ni.answered_at = now_local()
    if sec.status == "free":       # отметка без «взять в работу» тоже закрепляет область
        sec.status = "taken"
        sec.taken_by = principal.user.id
        sec.taken_by_name = _principal_name(principal)
        sec.taken_at = now_local()
    audit(db, principal, "night_item_answer", f"item:{item_id}",
          {"answer": ni.answer, "section_id": sec.id})
    db.commit()
    return {"ok": True, "item": {"id": ni.id, "answer": ni.answer, "comment": ni.comment}}


@router.post("/items/{item_id}/photo")
def add_item_photo(item_id: int, file: UploadFile = File(...),
                   principal: Principal = Depends(require_perm("night.view")),
                   db: Session = Depends(get_db)):
    ni = db.get(NightCheckItem, item_id)
    if ni is None:
        raise HTTPException(status_code=404, detail="Пункт не найден")
    sec = _get_section(db, ni.section_id)
    rep = _get_report(db, sec.report_id)
    _guard_open(rep)
    _guard_section_open(sec)
    limit = max_upload_bytes(db)
    # потоковая загрузка: файл идёт на диск чанками, не в память (P1 20.10.2026)
    ref = read_upload_streaming(file, limit)
    try:
        photo = save_photo_ref(db, kind="night_item", ref_id=ni.id, ref=ref,
                               user_id=principal.user.id, user_name=_principal_name(principal))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        ref.discard()   # после save_photo_ref файла уже нет (перенесён/удалён) — missing_ok
    db.commit()
    return {"ok": True, "photo": {"id": photo.id, "url": f"/api/photos/{photo.id}/file",
                                  "media_type": photo.media_type or "photo"}}
