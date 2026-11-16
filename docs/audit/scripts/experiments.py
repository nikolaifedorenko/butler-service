"""Эксперименты аудита на временной SQLite-базе с демо-сидом (боевых данных нет).

Каждый эксперимент печатает строку `EXP-<ID> | ФАКТ/НЕ ПОДТВЕРЖДЕНО | что увидели`.
Код приложения не меняется; база — временный файл, путь задаёт AUDIT_DB.

    AUDIT_DB=/tmp/audit_exp.db .venv/bin/python docs/audit/scripts/experiments.py
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
DB_FILE = Path(os.environ.get("AUDIT_DB", Path(tempfile.gettempdir()) / "audit_exp.db"))
for suf in ("", "-wal", "-shm"):
    Path(str(DB_FILE) + suf).unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["SECRET_KEY"] = "audit-secret-key-0123456789"
os.environ["CSRF_ENABLED"] = "0"
os.environ["ALLOW_IMPERSONATION"] = "1"
os.environ["APP_TZ"] = "Europe/Moscow"
os.environ["NIGHT_SYNC_ENABLED"] = "0"
os.environ["DEMO_SEED"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.identity import AccessGrant, User  # noqa: E402
from app.main import app, init_db  # noqa: E402

init_db()
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
results: list[str] = []


def out(exp: str, ok: bool, text: str) -> None:
    line = f"{exp} | {'ФАКТ' if ok else 'НЕ ПОДТВЕРЖДЕНО'} | {text}"
    results.append(line)
    print(line, flush=True)


def client(username: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": "demo1234"})
    assert r.status_code == 200, (username, r.status_code, r.text)
    return c


def uid(username: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.username == username))


def emp_of(username: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(User.employee_id).where(User.username == username))


def grant(username: str, perm: str, effect: str) -> None:
    with SessionLocal() as db:
        db.add(AccessGrant(user_id=uid(username), permission=perm, effect=effect))
        db.commit()


def ungrant(username: str) -> None:
    with SessionLocal() as db:
        for g in db.scalars(select(AccessGrant).where(AccessGrant.user_id == uid(username))):
            db.delete(g)
        db.commit()


# ── SEC: подделка X-Forwarded-For обходит лимит попыток входа ────────────────
def exp_xff():
    settings.trust_proxy_headers = True        # как в docker-compose.prod.yml (TRUST_PROXY_HEADERS=1)
    try:
        c = TestClient(app)
        codes = [c.post("/api/auth/login", json={"username": "admin", "password": f"wrong{i}"},
                        headers={"X-Forwarded-For": f"10.9.{i // 250}.{i % 250}, 203.0.113.7"}).status_code
                 for i in range(30)]
        same = [c.post("/api/auth/login", json={"username": "admin", "password": "wrong"},
                       headers={"X-Forwarded-For": "198.51.100.1, 203.0.113.7"}).status_code
                for _ in range(12)]
        out("EXP-XFF", 429 not in codes and 429 in same,
            f"30 неверных паролей с разным левым XFF (nginx дописывает реальный IP справа): "
            f"429 ни разу ({sorted(set(codes))}); с одинаковым XFF 429 на попытке "
            f"{same.index(429) + 1 if 429 in same else '—'}")
    finally:
        settings.trust_proxy_headers = False


# ── AUTHZ: имперсонация без can_manage_user ──────────────────────────────────
def exp_impersonate_manager():
    sup = client("gromova")                                # supervisor
    target = emp_of("smirnov")                             # сотрудник-менеджер
    r = sup.post("/api/auth/impersonate", json={"employee_id": target})
    ok = r.status_code == 200
    detail = f"supervisor → impersonate(сотрудник менеджера smirnov): {r.status_code}"
    if ok:
        p = sup.post("/api/punches", json={"kind": "auto"})
        detail += f"; затем POST /api/punches от его имени: {p.status_code} {p.json().get('message', p.json().get('detail'))}"
        with SessionLocal() as db:
            from app.core.audit import AuditLog
            last = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).first()
            detail += f"; в журнале: actor_id={last.actor_id} actor_name={last.actor_name!r} action={last.action}"
    out("EXP-IMP-1", ok, detail)


# ── AUTHZ: сброс пароля админом не отзывает сессии ───────────────────────────
def exp_password_reset_sessions():
    victim = client("kuznetsova")
    adm = client("admin")
    emp_id = emp_of("kuznetsova")
    data = adm.get("/api/employees").json()
    e = next(x for x in data if x["id"] == emp_id)
    body = {k: e.get(k) for k in ("full_name", "short_name", "position", "phone", "tab_number",
                                  "schedule_group", "group_color")}
    body.update({"full_name": e["full_name"], "role": e["role"], "username": e["username"],
                 "password": "NewStrongPass123", "balance_hours": e.get("balance_hours", 0) or 0,
                 "hired_at": e.get("hired_at")})
    r = adm.put(f"/api/employees/{emp_id}", json={k: v for k, v in body.items() if v is not None})
    me = victim.get("/api/auth/me")
    out("EXP-PWD", r.status_code == 200 and me.status_code == 200,
        f"PUT /api/employees/{emp_id} с новым паролем: {r.status_code}; старая cookie → /api/auth/me: {me.status_code}")


# ── AUTHZ: PUT сотрудника без поля role молча понижает роль ──────────────────
def exp_role_default():
    adm = client("admin")
    emp_id = emp_of("gromova")
    e = next(x for x in adm.get("/api/employees").json() if x["id"] == emp_id)
    before = e["role"]
    body = {"full_name": e["full_name"], "position": e["position"], "schedule_group": e["schedule_group"],
            "hired_at": e.get("hired_at"), "balance_hours": e.get("balance_hours") or 0}
    r = adm.put(f"/api/employees/{emp_id}", json=body)
    after = r.json().get("role")
    with SessionLocal() as db:
        from app.core.audit import AuditLog
        last = db.scalars(select(AuditLog).where(AuditLog.action == "employee_update")
                          .order_by(AuditLog.id.desc()).limit(1)).first()
    out("EXP-ROLE", before != after,
        f"роль до: {before}, после PUT без role: {after}; запись аудита: {last.payload_json!r}")
    # вернуть как было, чтобы не влиять на остальные эксперименты
    body["role"] = before
    adm.put(f"/api/employees/{emp_id}", json=body)


# ── UI/DATA: «Стартовый банк часов» не влияет на банк ────────────────────────
def exp_balance_hours():
    adm = client("admin")
    emp_id = emp_of("ivanov")
    h1 = adm.get(f"/api/employees/{emp_id}/history").json()["bank_now"]
    e = next(x for x in adm.get("/api/employees").json() if x["id"] == emp_id)
    body = {"full_name": e["full_name"], "position": e["position"], "schedule_group": e["schedule_group"],
            "hired_at": e.get("hired_at"), "role": e["role"], "balance_hours": 999.0}
    r = adm.put(f"/api/employees/{emp_id}", json=body)
    h2 = adm.get(f"/api/employees/{emp_id}/history").json()["bank_now"]
    st = client("ivanov").get("/api/punches/status").json()["balance_hours"]
    out("EXP-BANK", r.status_code == 200 and h1 == h2,
        f"balance_hours 2 → 999: сохранено ({r.status_code}), bank_now до {h1} / после {h2}, "
        f"у сотрудника на экране отметок {st}")


# ── AUTHZ: supervisor правит balance_hours, хотя корректировка банка — только admin/manager
def exp_sup_balance():
    sup = client("gromova")
    emp_id = emp_of("orlov")
    e = next(x for x in sup.get("/api/employees").json() if x["id"] == emp_id)
    body = {"full_name": e["full_name"], "position": e["position"], "schedule_group": e["schedule_group"],
            "hired_at": e.get("hired_at"), "role": e["role"], "balance_hours": 77.0}
    r = sup.put(f"/api/employees/{emp_id}", json=body)
    adj = sup.post(f"/api/employees/{emp_id}/bank-adjust", json={"hours": 1, "note": "тест"})
    out("EXP-SUPBANK", r.status_code == 200 and adj.status_code == 403,
        f"supervisor: PUT balance_hours=77 → {r.status_code}; POST bank-adjust → {adj.status_code}")


# ── AUTHZ: роль в теле игнорирует индивидуальный allow/deny ──────────────────
def exp_role_vs_grants():
    grant("smirnov", "settings.edit", "deny")
    m = client("smirnov")
    r1 = m.post("/api/doublepay/days", json={"date": "2026-12-31", "reason": "holiday"})
    ungrant("smirnov")
    grant("gromova", "settings.edit", "allow")
    s = client("gromova")
    r2 = s.post("/api/doublepay/days", json={"date": "2026-12-30", "reason": "holiday"})
    ungrant("gromova")
    out("EXP-ROLEGRANT", r1.status_code == 403 and r2.status_code == 403,
        f"manager с deny settings.edit → POST /api/doublepay/days: {r1.status_code} (ожидаемо 403); "
        f"supervisor с ЯВНЫМ allow settings.edit → {r2.status_code}: {r2.json().get('detail')!r}")


# ── AUTHZ: отметка «за другого» без punches.punch_for_others молча ставится себе ──
def exp_punch_for_other():
    grant("gromova", "punches.punch_for_others", "deny")
    s = client("gromova")
    other = emp_of("sidorov")
    st_before = s.get("/api/punches/status").json()["on_shift"]
    r = s.post("/api/punches", json={"kind": "auto", "employee_id": other})
    ungrant("gromova")
    body = r.json()
    with SessionLocal() as db:
        from app.modules.timesheet.adapters.orm import Punch
        p = db.get(Punch, body["punch"]["id"]) if r.status_code == 200 else None
    out("EXP-PUNCHOTHER", p is not None and p.employee_id != other,
        f"POST /api/punches employee_id={other} (sidorov) от supervisor без punch_for_others: "
        f"{r.status_code} {body.get('message') or body.get('detail')!r}; отметка записана сотруднику "
        f"id={p.employee_id if p else '—'} (сама gromova={emp_of('gromova')}, была на смене: {st_before})")


# ── IDOR: фото доступно любому вошедшему без прав раздела ────────────────────
def exp_photo_idor():
    from app.core.media import save_photo
    with SessionLocal() as db:
        ph = save_photo(db, kind="car_return", ref_id=1, filename="damage.png", blob=PNG,
                        user_id=uid("smirnov"), user_name="Смирнов")
        db.commit()
        pid = ph.id
    for k in ("cars.view", "night.view", "cars.use", "presence.view", "schedule.view", "me.punch"):
        grant("volkov", k, "deny")
    e = client("volkov")
    me = e.get("/api/auth/me").json()["permissions"]
    r = e.get(f"/api/photos/{pid}/file")
    r2 = e.get(f"/api/night/photos/{pid}/file")
    ungrant("volkov")
    out("EXP-PHOTO", r.status_code == 200,
        f"сотрудник с правами {me} (всё снято) → GET /api/photos/{pid}/file: {r.status_code}, "
        f"алиас /api/night/photos: {r2.status_code}")


# ── AUTHZ: ночной обход без night.view ───────────────────────────────────────
def _open_report():
    from app.core.time import now_local
    from app.modules.night.adapters.orm import NightAreaSection, NightCheckItem, NightReport
    from app.modules.night.application.night import ensure_report
    with SessionLocal() as db:
        rep = db.scalars(select(NightReport).order_by(NightReport.date.desc())).first()
        if rep is None:
            rep = ensure_report(db, dt.date.today())
        rep.status, rep.reopened_at = "open", now_local()
        sec = db.scalars(select(NightAreaSection).where(NightAreaSection.report_id == rep.id,
                                                        NightAreaSection.area_id.is_not(None))).first()
        item = db.scalars(select(NightCheckItem).where(NightCheckItem.section_id == sec.id)).first()
        db.commit()
        return rep.id, sec.id, item.id


def exp_night_without_view():
    rep_id, sec_id, item_id = _open_report()
    grant("morozova", "night.view", "deny")
    e = client("morozova")
    r0 = e.get("/api/night/today")
    r1 = e.post(f"/api/night/sections/{sec_id}/take", json={"ack": True})
    r2 = e.put(f"/api/night/items/{item_id}/answer", json={"answer": "bad", "comment": "аудит"})
    r3 = e.post(f"/api/night/sections/{sec_id}/close", json={"force_unanswered": True})
    ungrant("morozova")
    out("EXP-NIGHTVIEW", r0.status_code == 403 and r2.status_code == 200,
        f"сотрудник с deny night.view: GET /today {r0.status_code}; take {r1.status_code}; "
        f"answer {r2.status_code}; close {r3.status_code}")
    return rep_id


def exp_dispatch_by_employee(rep_id):
    e = client("petrov")
    r = e.post(f"/api/night/reports/{rep_id}/dispatch", json={"mode": "all"})
    out("EXP-DISPATCH", r.status_code != 403,
        f"рядовой сотрудник (night.view по умолчанию) → POST /api/night/reports/{rep_id}/dispatch: "
        f"{r.status_code} {str(r.json())[:160]}")


# ── CONC: два телефона берут один кар ────────────────────────────────────────
def exp_car_race():
    from app.core.auth import Principal
    from app.modules.cars.application.cars import take_car
    from app.modules.cars.application.catalog import Car
    from app.modules.employees.adapters.orm import Employee
    with SessionLocal() as db:
        car = db.scalars(select(Car).where(Car.status == "free", Car.assigned_to.is_(None))).first()
        car_id = car.id
    s1, s2 = SessionLocal(), SessionLocal()
    try:
        busy = {h for (h,) in s1.execute(select(Car.holder_user_id).where(Car.holder_user_id.is_not(None)))}
        free_users = [u for u in s1.scalars(select(User).where(User.employee_id.is_not(None),
                                                                 User.role == "employee")) if u.id not in busy]
        u1 = free_users[0]
        u2 = s2.get(User, free_users[1].id)
        p1 = Principal(u1, s1.get(Employee, u1.employee_id))
        p2 = Principal(u2, s2.get(Employee, u2.employee_id))
        c1, c2 = s1.get(Car, car_id), s2.get(Car, car_id)       # оба читают «свободен»
        # чередование как у двух HTTP-запросов: оба прочитали кар ДО коммита соседа
        assert c1.status == c2.status == "free"
        take_car(s1, c1, p1, ack_assigned=True)
        s1.commit()
        take_car(s2, c2, p2, ack_assigned=True)   # c2 прочитан до коммита s1 — «свободен»
        s2.commit()
    finally:
        s1.close()
        s2.close()
    with SessionLocal() as db:
        from app.modules.cars.adapters.orm import CarHistory
        hist = db.scalars(select(CarHistory).where(CarHistory.car_id == car_id, CarHistory.action == "take")).all()
        holder = db.get(Car, car_id).holder_name
    out("EXP-CARRACE", len(hist) == 2,
        f"кар id={car_id}: два «взять» с чередованием чтение/чтение/запись+commit/запись+commit — оба успешны, "
        f"в истории {len(hist)} записи «take», держатель в карточке: {holder}")


# ── LOGIC: «выдать» кар на обслуживании обходит правило «снять с обслуживания — менеджер» ──
def exp_give_maintenance():
    from app.modules.cars.application.catalog import Car
    with SessionLocal() as db:
        car = db.scalars(select(Car).where(Car.status == "free", Car.holder_user_id.is_(None))).first()
        car.status = "maintenance"
        db.commit()
        car_id = car.id
    s = client("gromova")
    r1 = s.post(f"/api/cars/{car_id}/status", json={"status": "free"})
    r2 = s.post(f"/api/cars/{car_id}/give", json={"employee_id": emp_of("orlov")})
    with SessionLocal() as db:
        st = db.get(Car, car_id).status
    out("EXP-GIVEMAINT", r1.status_code != 200 and r2.status_code == 200 and st == "busy",
        f"supervisor: снять с обслуживания → {r1.status_code}; «выдать» тот же кар → {r2.status_code}, статус стал {st}")


# ── DATA: очистка медиа по сроку хранения не трогает фото при разных сроках ──
def exp_cleanup_retention():
    from app.core import media
    from app.core.media import Photo, cleanup_photos, save_photo
    from app.core.time import now_local
    with SessionLocal() as db:
        ph = save_photo(db, kind="night_item", ref_id=1, filename="old.png", blob=PNG,
                        user_id=None, user_name="")
        ph.created_at = now_local() - dt.timedelta(days=60)
        db.commit()
        pid = ph.id
    orig = media._RULES_PROVIDER
    media._RULES_PROVIDER = lambda db: {"photo_retention_days": 30, "video_retention_days": 180}
    try:
        with SessionLocal() as db:
            removed = cleanup_photos(db)
            still = bool(db.get(Photo, pid).path)
    finally:
        media._RULES_PROVIDER = orig
    out("EXP-RETENTION", still,
        f"срок фото 30 дн, видео 180 дн; фото возрастом 60 дн → cleanup_photos удалил {removed}, файл на месте: {still}")


# ── AUTHZ: удаление своего фото из закрытого ночного отчёта ──────────────────
def exp_photo_delete_closed():
    from app.core.media import save_photo
    from app.modules.night.adapters.orm import NightAreaSection, NightCheckItem, NightReport
    with SessionLocal() as db:
        rep = db.scalars(select(NightReport).order_by(NightReport.date.desc())).first()
        sec = db.scalars(select(NightAreaSection).where(NightAreaSection.report_id == rep.id,
                                                        NightAreaSection.area_id.is_not(None))).first()
        item = db.scalars(select(NightCheckItem).where(NightCheckItem.section_id == sec.id)).first()
        ph = save_photo(db, kind="night_item", ref_id=item.id, filename="proof.png", blob=PNG,
                        user_id=uid("fedorov"), user_name="Фёдоров")
        rep.status = "closed"
        db.commit()
        pid = ph.id
    r = client("fedorov").delete(f"/api/photos/{pid}")
    out("EXP-PHOTODEL", r.status_code == 200,
        f"автор удаляет фото-доказательство из ЗАКРЫТОГО ночного отчёта: {r.status_code}")


if __name__ == "__main__":
    exp_xff()
    exp_impersonate_manager()
    exp_password_reset_sessions()
    exp_role_default()
    exp_balance_hours()
    exp_sup_balance()
    exp_role_vs_grants()
    exp_punch_for_other()
    exp_photo_idor()
    rep_id = exp_night_without_view()
    exp_dispatch_by_employee(rep_id)
    exp_car_race()
    exp_give_maintenance()
    exp_cleanup_retention()
    exp_photo_delete_closed()
