"""Стражи находок P1 внешнего ревью от 20.10.2026 — батч «прочее» (батч 5 плана).

Каждая группа закрепляет один фикс, чтобы находка не вернулась:

* **P1-misc-1** — границы фильтра аудита: `AuditLog.ts` хранится в UTC, фильтр
  задаётся ЛОКАЛЬНЫМИ датами объекта — обе границы переводятся через APP_TZ
  (прежде date_from сдвигался на хардкодные −3 ч, date_to не конвертировался
  вовсе — асимметрия ломала выборку при любом APP_TZ ≠ +3 и на любом поясе
  захватывала чужие сутки по date_to);
* **P1-misc-2** — `resend()` повторяет отправку письма С КОПИЕЙ: снимок cc
  хранится в журнале (`notify_dispatches.cc_json`), миграция идемпотентна;
* **P1-misc-3** — FK/unique валидируются ДО вставки: битая ссылка/дубль имени —
  типизированные 400/409/422 вместо IntegrityError → 500 (PostgreSQL) или
  молчаливой записи сироты/дубля (SQLite — FK не включены);
* **P1-misc-4** — загрузка медиа потоковая: `read_upload_streaming` читает
  чанками на диск (в памяти только первые 64 КБ для sniff), превышение лимита
  прерывает чтение и удаляет временный файл; в интерфейсах больше нет
  `await file.read(` (до 500 МБ в RAM на запрос).

Данные сажаются под уникальными именами/действиями («p1-misc-guard…») и
удаляются в каждом тесте; даты аудита фиксированные (2026-12-31/2027-01-01) —
не пересекаются с демо-данными и другими тестами.
"""
from __future__ import annotations

import base64
import datetime as dt
import io
import json
import pathlib
import tempfile

import pytest
from sqlalchemy import delete, select

from app.core.audit import AuditLog
from app.core.errors import PayloadTooLarge
from app.core.identity import AccessGroupMember
from app.core.media import read_upload_streaming, save_photo_ref

BASE = pathlib.Path(__file__).resolve().parent.parent
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


# ── P1-misc-1: границы фильтра аудита — локальные даты → UTC через APP_TZ ─────

def test_misc1_audit_filter_boundaries_are_local(admin_client, db):
    """APP_TZ = Europe/Moscow (+3, conftest). Четыре записи вокруг локальных суток
    01.01.2027: A — 31.12 23:59 МСК, B — 01.01 00:00 МСК, C — 01.01 23:59 МСК,
    D — 02.01 00:00 МСК. Фильтр date_from=date_to=2027-01-01 обязан вернуть
    ровно B и C. Старый код включал D (date_to без конверсии: «< 02.01 00:00 UTC»
    = 02.01 03:00 МСК) — и ломался бы целиком на другом APP_TZ."""
    rows = {
        "A": dt.datetime(2026, 12, 31, 20, 59),   # UTC = 31.12 23:59 МСК
        "B": dt.datetime(2026, 12, 31, 21, 0),    # UTC = 01.01 00:00 МСК
        "C": dt.datetime(2027, 1, 1, 20, 59),     # UTC = 01.01 23:59 МСК
        "D": dt.datetime(2027, 1, 1, 21, 0),      # UTC = 02.01 00:00 МСК
    }
    for tag, ts in rows.items():
        db.add(AuditLog(ts=ts, actor_id=None, actor_name="p1-misc-guard",
                        action="p1_misc_audit_guard", target=tag, payload_json="{}"))
    db.commit()
    try:
        r = admin_client.get("/api/audit", params={
            "action": "p1_misc_audit_guard",
            "date_from": "2027-01-01", "date_to": "2027-01-01", "limit": 50})
        assert r.status_code == 200, r.text
        got = {item["target"] for item in r.json()["items"]}
        assert got == {"B", "C"}, f"границы суток съехали: {got}"
    finally:
        db.execute(delete(AuditLog).where(AuditLog.action == "p1_misc_audit_guard"))
        db.commit()


def test_misc1_no_hardcoded_utc_offset():
    src = (BASE / "app/modules/audit/interface/audit_api.py").read_text(encoding="utf-8")
    assert "hours=3" not in src and "hours=-3" not in src
    assert "_utc_bound" in src          # границы переводит общая функция


# ── P1-misc-2: resend() повторяет отправку с копией (cc) ──────────────────────

def test_misc2_resend_uses_saved_cc(db, monkeypatch):
    from app.modules.notify.adapters.orm import NotifyDispatch
    from app.modules.notify.application.dispatch import deliver_row

    captured: dict = {}

    def fake_deliver(**kwargs):
        captured.update(kwargs)
        return "ext-guard-1"

    monkeypatch.setattr("app.modules.notify.application.dispatch.deliver", fake_deliver)
    row = NotifyDispatch(domain="night", ref_id=1, channel="email", target="to@example.com",
                         subject="Тема", message="Текст", status="failed", error="smtp down",
                         attempts=1,   # как в БД после первой (неудачной) отправки
                         cc_json=json.dumps(["copy1@example.com", "copy2@example.com"]),
                         media_json="[]")
    db.add(row)
    try:
        out = deliver_row(db, row, cfg=object())     # cfg-заглушка: deliver перехвачен
        assert captured["cc"] == ("copy1@example.com", "copy2@example.com")
        assert out.status == "sent" and out.external_id == "ext-guard-1"
        assert out.attempts == 2
    finally:
        db.rollback()


def test_misc2_dispatch_stores_cc_snapshot():
    """dispatch() обязан писать снимок cc в журнал (source-страж: без него
    resend физически негде взять копию)."""
    src = (BASE / "app/modules/notify/application/dispatch.py").read_text(encoding="utf-8")
    assert "cc_json=json.dumps(list(cc))" in src
    assert "cc: tuple = ()" not in src          # прежний хардкод не вернулся


# ── P1-misc-3: FK/unique — типизированные отказы ДО вставки ───────────────────

def test_misc3_area_with_bad_zone_rejected(admin_client):
    r = admin_client.post("/api/night/areas",
                          json={"name": "p1-misc-guard-area", "zone_id": 999999})
    assert r.status_code == 400, r.text          # было: 500 (PG) / сирота (SQLite)
    assert "Зона обхода не найдена" in r.json()["detail"]


def test_misc3_area_bulk_with_bad_zone_rejected(admin_client):
    r = admin_client.post("/api/night/areas/bulk",
                          json={"prefix": "p1-misc-guard ", "start": 1, "count": 2,
                                "zone_id": 999999})
    assert r.status_code == 400, r.text
    assert "Зона обхода не найдена" in r.json()["detail"]


def test_misc3_area_rename_duplicate_rejected(admin_client, db):
    from app.modules.night.adapters.orm import NightArea
    a = admin_client.post("/api/night/areas", json={"name": "p1-misc-guard-A"}).json()["id"]
    b = admin_client.post("/api/night/areas", json={"name": "p1-misc-guard-B"}).json()["id"]
    try:
        r = admin_client.put(f"/api/night/areas/{b}", json={"name": "p1-misc-guard-A"})
        assert r.status_code == 409, r.text      # было: IntegrityError → 500
        assert "Такая область уже есть" in r.json()["detail"]
        # rename в update_area тоже валидирует зону
        r = admin_client.put(f"/api/night/areas/{b}",
                             json={"name": "p1-misc-guard-B", "zone_id": 999999})
        assert r.status_code == 400, r.text
    finally:
        db.execute(delete(NightArea).where(NightArea.id.in_([a, b])))
        db.commit()


def test_misc3_employee_with_bad_department_rejected(admin_client, db):
    r = admin_client.post("/api/employees",
                          json={"full_name": "p1-misc-guard Сотрудник",
                                "department_id": 999999})
    assert r.status_code == 422, r.text          # было: 500 (PG) / сирота (SQLite)
    assert "Департамент не найден" in r.json()["detail"]


def test_misc3_group_rename_duplicate_rejected(admin_client):
    g1 = admin_client.post("/api/access/groups", json={"name": "p1-misc-guard-g1"}).json()["id"]
    g2 = admin_client.post("/api/access/groups", json={"name": "p1-misc-guard-g2"}).json()["id"]
    try:
        r = admin_client.put(f"/api/access/groups/{g2}", json={"name": "p1-misc-guard-g1"})
        assert r.status_code == 409, r.text      # было: IntegrityError → 500
        assert "Группа с таким названием уже есть" in r.json()["detail"]
    finally:
        admin_client.delete(f"/api/access/groups/{g1}")
        admin_client.delete(f"/api/access/groups/{g2}")


def test_misc3_members_bad_user_rejected_and_roster_kept(admin_client, db):
    g = admin_client.post("/api/access/groups", json={"name": "p1-misc-guard-g3"}).json()["id"]
    try:
        r = admin_client.put(f"/api/access/groups/{g}/members", json={"user_ids": [1]})
        assert r.status_code == 200, r.text
        r = admin_client.put(f"/api/access/groups/{g}/members",
                             json={"user_ids": [1, 999999]})
        assert r.status_code == 422, r.text      # было: 500 (PG) / призрак (SQLite)
        assert "999999" in r.json()["detail"]
        db.expire_all()
        # валидация ДО удаления состава: прежний участник не потерялся
        members = list(db.scalars(select(AccessGroupMember.user_id)
                                  .where(AccessGroupMember.group_id == g)))
        assert members == [1]
    finally:
        admin_client.delete(f"/api/access/groups/{g}")


# ── P1-misc-4: потоковая загрузка медиа ───────────────────────────────────────

class _FakeUpload:
    """Мини-UploadFile: синхронный .file + filename (duck-typing core/media)."""

    def __init__(self, data: bytes, filename: str = "photo.png"):
        self.file = io.BytesIO(data)
        self.filename = filename


def _temp_leftovers() -> set:
    return {p for p in pathlib.Path(tempfile.gettempdir()).glob("butler-upload-*")}


def test_misc4_streaming_reads_to_disk_and_enforces_limit():
    data = PNG * 4096                      # ~280 КБ — больше одного чанка не нужно, но и не крошечный
    ref = read_upload_streaming(_FakeUpload(data), 10 * 1024 * 1024)
    try:
        assert ref.size == len(data)
        assert ref.head.startswith(b"\x89PNG")
        assert ref.tmp_path.exists() and ref.tmp_path.stat().st_size == len(data)
    finally:
        ref.discard()

    before = _temp_leftovers()
    with pytest.raises(PayloadTooLarge):
        read_upload_streaming(_FakeUpload(data), 10)   # лимит 10 байт
    assert _temp_leftovers() <= before, "временный файл не удалён после отказа"


def test_misc4_save_photo_ref_moves_file_and_rejects_non_media(db):

    ref = read_upload_streaming(_FakeUpload(PNG), 10 * 1024 * 1024)
    photo = save_photo_ref(db, kind="night_item", ref_id=1, ref=ref,
                           user_id=None, user_name="p1-misc-guard")
    try:
        assert not ref.tmp_path.exists()               # перенесён, не скопирован
        on_disk = BASE / photo.path
        assert on_disk.exists() and on_disk.read_bytes() == PNG
        assert photo.media_type == "photo" and photo.size == len(PNG)
    finally:
        (BASE / photo.path).unlink(missing_ok=True)
        db.rollback()

    bad = read_upload_streaming(_FakeUpload(b"%PDF-1.4 not media"), 1024)
    with pytest.raises(ValueError):
        save_photo_ref(db, kind="night_item", ref_id=1, ref=bad,
                       user_id=None, user_name="p1-misc-guard")
    assert not bad.tmp_path.exists(), "временный файл не удалён после отказа по типу"
    db.rollback()


def test_misc4_interfaces_do_not_read_uploads_into_memory():
    """Source-страж: в точках загрузки медиа нет `await file.read(` (прежний
    путь — до HARD_MAX_MB=500 в оперативной памяти на запрос)."""
    for rel in ("app/modules/night/interface", "app/modules/cars/interface/cars_api.py"):
        path = BASE / rel
        src = "".join(f.read_text(encoding="utf-8") for f in sorted(path.glob("*.py"))) \
            if path.is_dir() else path.read_text(encoding="utf-8")
        assert "await file.read(" not in src, rel
        assert "read_upload_streaming" in src, rel


def test_conc04_route_handlers_are_sync():
    """CONC-04 (аудит 21.10.2026): обработчик `async def` с синхронными БД и диском держал
    event loop воркера — пока один телефон грузил фото, ждали все запросы. Обработчики
    маршрутов — только `def` (FastAPI выполняет их в пуле потоков)."""
    import ast

    offenders = []
    for path in sorted((BASE / "app").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.AsyncFunctionDef) and any(
                    "router." in ast.unparse(d) for d in node.decorator_list):
                offenders.append(f"{path.relative_to(BASE)}:{node.lineno} {node.name}")
    assert not offenders, offenders
