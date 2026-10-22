"""Стражи находок P1 внешнего ревью от 20.10.2026 — батч «ночной отчёт + электрокары».

Каждая группа закрепляет один фикс, чтобы находка не вернулась:

* **P1-night-1** — повторная отметка кара обновляет ``checked_at`` (last write wins):
  вместе с ним свежими остаются ``car.last_checked_at`` и флаг «кар взяли ПОСЛЕ
  проверки» (``taken_after_check``);
* **P1-night-2** — автозакрытие по дедлайну 08:00 проставляет ``close_reason="auto"``
  (DOCX-выгрузка больше не подписывает закрытый отчёт «Открыт · закроется 08:00»);
* **P1-night-3** — переоткрытый вручную отчёт не закрывается снова: ``reopened_at``
  выключает для него автозакрытие, а GET /today и /reports больше не выполняют
  ``sync_reports`` (обслуживание — стартовый прогон и фоновый поток
  ``bootstrap/night_sync.py`` под неблокирующим замком ``try_lock``);
* **P1-night-4** — окно досоздания пропущенных смен честно равно BACKFILL_DAYS
  (прежняя формула ``min(len(have) + 31, 31)`` всегда давала 31 и имитировала
  более умное поведение).

Даты смен фиксированные и не пересекаются с другими модулями тестов
(2026-05-10…22 заняты test_night_shift / test_cars / test_night_zones).
"""
from __future__ import annotations

import contextlib
import datetime as dt
import inspect
import io
import os
import pathlib
import re
import subprocess
import sys
import time
import zipfile

from sqlalchemy import select

from app.core.time import now_local
from app.modules.night.application.night import (
    ensure_report,
    finalize_report,
    sync_reports,
)
from tests.test_cars import NIGHT_CHECK_FORM, _obhod, _park

BASE = pathlib.Path(__file__).resolve().parent.parent

D_FINALIZE = dt.date(2026, 6, 1)     # P1-night-2: close_reason="auto"
D_REOPEN = dt.date(2026, 6, 2)       # P1-night-3: переоткрытие выживает
D_GET_PURE = dt.date(2026, 6, 3)     # P1-night-3: GET без побочных записей
D_SYNC_ONCE = dt.date(2026, 6, 4)    # P1-night-3: фоновый раунд run_sync_once
D_DOCX = dt.date(2026, 6, 5)         # P1-night-2/3: подписи в выгрузке
D_CARS = dt.date(2026, 6, 9)         # P1-night-1: повторная отметка кара

# 06:00 UTC = 09:00 МСК следующих суток — дедлайн 08:00 уже прошёл
def _utc_after_deadline(shift_d: dt.date) -> str:
    return f"{(shift_d + dt.timedelta(days=1)).isoformat()} 06:00:00"


@contextlib.contextmanager
def _smena(db, freeze, shift_d: dt.date):
    """Открытый отчёт за фиксированную прошлую смену + уборка за тестом."""
    from app.modules.night.application.catalog import NightReport

    with freeze(f"{shift_d.isoformat()} 23:00:00"):   # 02:00 МСК следующих суток — смена идёт
        rep = ensure_report(db, shift_d)
        assert rep is not None, "отчёт для идущей смены не создан"
        try:
            yield rep
        finally:
            db.expire_all()
            fresh = db.get(NightReport, rep.id)
            if fresh is not None:
                db.delete(fresh)          # каскад убирает области и пункты
            db.commit()


def _dates(db) -> set[dt.date]:
    from app.modules.night.application.catalog import NightReport

    db.expire_all()
    return {d for (d,) in db.execute(select(NightReport.date))}


def _cleanup_dates(db, dates: set[dt.date]) -> None:
    """Удалить отчёты, досозданные sync_reports (каскад убирает области и пункты)."""
    from app.modules.night.application.catalog import NightReport

    for rep in db.scalars(select(NightReport).where(NightReport.date.in_(dates))):
        db.delete(rep)
    db.commit()


@contextlib.contextmanager
def _smena_rt(db, freeze, shift_d: dt.date):
    """Отчёт смены, созданный под заморозкой, но с РЕАЛЬНЫМ временем в теле теста.

    Нужен там, где важна реальная разница времён: повторная отметка кара
    (checked_at пишется now_local() — под непрерывным freeze время стояло бы на
    месте) и run_sync_once (закрывает отчёт по РЕАЛЬНО прошедшему дедлайну).
    Уборка: ночные отметки каров + сам отчёт (каскад)."""
    from app.modules.cars.application.catalog import CarNightCheck
    from app.modules.night.application.catalog import NightReport

    with freeze(f"{shift_d.isoformat()} 23:00:00"):   # 02:00 МСК следующих суток — смена идёт
        rep = ensure_report(db, shift_d)
        assert rep is not None, "отчёт для идущей смены не создан"
        rep_id = rep.id
    try:
        yield rep
    finally:
        db.expire_all()
        for ch in db.scalars(select(CarNightCheck).where(CarNightCheck.report_id == rep_id)):
            db.delete(ch)
        fresh = db.get(NightReport, rep_id)
        if fresh is not None:
            db.delete(fresh)
        db.commit()


# ─────────────────────── P1-night-2: close_reason при автозакрытии ───────────────────────

def test_finalize_report_stavit_close_reason_auto(db, freeze):
    """Автозакрытие по дедлайну обязано проставить close_reason="auto".

    Раньше finalize_report() не трогал close_reason, и DOCX-выгрузка подписывала
    автозакрытый отчёт «Открыт · закроется 08:00» (строка статуса строилась по
    пустому close_reason)."""
    with _smena(db, freeze, D_FINALIZE) as rep, freeze(_utc_after_deadline(D_FINALIZE)):
        result = finalize_report(rep)
        db.commit()
        assert rep.status == "closed"
        assert rep.close_reason == "auto", \
                f"автозакрытие не проставило причину: {rep.close_reason!r}"
        assert result in ("full", "partial")


def test_ruchnoe_zakrytie_daet_close_reason_manual(manager_client, db, freeze):
    """Ручное закрытие — close_reason="manual" (finalize_report(reason=…))."""
    with _smena(db, freeze, D_DOCX) as rep:
        r = manager_client.post(f"/api/night/reports/{rep.id}/close",
                                json={"force_unanswered": True})
        assert r.status_code == 200, r.text
        db.refresh(rep)
        assert rep.status == "closed" and rep.close_reason == "manual"


# ─────────────────────── P1-night-2/3: подписи DOCX-выгрузки ───────────────────────

def _docx_text(data: bytes) -> str:
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", "", xml)


def test_docx_pokazyvaet_prichinu_zakrytiya_i_pereotkrytie(manager_client, db, freeze):
    """Строка статуса в DOCX: автозакрытие / переоткрытие / ручное закрытие."""
    with _smena(db, freeze, D_DOCX) as rep:
        # автозакрытие (дедлайн прошёл) — «Закрыт автоматически в 08:00»
        with freeze(_utc_after_deadline(D_DOCX)):
            finalize_report(rep)
            db.commit()
        r = manager_client.get(f"/api/night/reports/{rep.id}/export.docx")
        assert r.status_code == 200, r.status_code
        text = _docx_text(r.content)
        assert "Закрыт автоматически в 08:00" in text, \
            "автозакрытый отчёт подписан неверно (до фикса — «Открыт · закроется 08:00»)"

        # переоткрытие — «Открыт · переоткрыт вручную», без обещания автозакрытия
        r = manager_client.post(f"/api/night/reports/{rep.id}/reopen")
        assert r.status_code == 200, r.text
        text = _docx_text(manager_client.get(
            f"/api/night/reports/{rep.id}/export.docx").content)
        assert "переоткрыт вручную" in text
        assert "закроется" not in text, \
            "переоткрытый отчёт обещает автозакрытие, которое для него отключено"

        # повторное ручное закрытие — «Закрыт вручную»
        r = manager_client.post(f"/api/night/reports/{rep.id}/close",
                                json={"force_unanswered": True})
        assert r.status_code == 200, r.text
        text = _docx_text(manager_client.get(
            f"/api/night/reports/{rep.id}/export.docx").content)
        assert "Закрыт вручную" in text


# ─────────────────────── P1-night-3: переоткрытие выживает ───────────────────────

def test_pereotkrytyi_otchet_ne_zakryvaetsya_snova(manager_client, db, freeze):
    """Реopen живёт дольше двух минут: sync_reports пропускает переоткрытые отчёты.

    До фикса ближайший sync_reports (каждый GET /today и /reports, throttle 120 с)
    закрывал переоткрытый отчёт по прошедшему дедлайну, и правки падали в 409."""
    created: set[dt.date] = set()
    try:
        with _smena(db, freeze, D_REOPEN) as rep:
            before = _dates(db)
            # закрываем вручную и переоткрываем (HTTP — вне заморозки)
            r = manager_client.post(f"/api/night/reports/{rep.id}/close",
                                    json={"force_unanswered": True})
            assert r.status_code == 200, r.text
            r = manager_client.post(f"/api/night/reports/{rep.id}/reopen")
            assert r.status_code == 200, r.text
            data = r.json()["report"]
            assert data["status"] == "open" and data["close_reason"] == ""
            assert data["reopened_at"], "момент переоткрытия не зафиксирован"

            # переоткрытие уже открытого отчёта — 409 (иначе no-op убил бы автозакрытие)
            r = manager_client.post(f"/api/night/reports/{rep.id}/reopen")
            assert r.status_code == 409, r.text

            # HTTP-сессия закоммитила переоткрытие: сбрасываем снимок тестовой
            # сессии (SQLite) И её identity map: SessionLocal собран с
            # expire_on_commit=False, поэтому commit() атрибуты не гасит, а
            # SELECT в sync вернул бы экземпляр со старым reopened_at=NULL.
            # В проде такой ситуации нет: фоновый раунд работает в свежей сессии.
            db.commit()
            db.expire_all()

            # дедлайн давно прошёл — sync обязан ПРОПУСТИТЬ переоткрытый отчёт
            with freeze(_utc_after_deadline(D_REOPEN)):
                res = sync_reports(db, force=True)
                created |= _dates(db) - before
                assert D_REOPEN.isoformat() not in res["closed"], res
            db.refresh(rep)
            assert rep.status == "open", \
                "переоткрытый отчёт снова закрыт автозакрытием — правки упадут в 409"

            # закрытие вручную после правок работает и фиксирует причину
            r = manager_client.post(f"/api/night/reports/{rep.id}/close",
                                    json={"force_unanswered": True})
            assert r.status_code == 200, r.text
            db.commit()          # снять снимок сессии до refresh
            db.refresh(rep)      # refresh перечитывает атрибуты независимо от expire
            assert rep.status == "closed" and rep.close_reason == "manual"
    finally:
        _cleanup_dates(db, created - {D_REOPEN})


def test_get_today_i_reports_ne_pishut_v_bazu(manager_client, db, freeze):
    """GET /api/night/today и /api/night/reports — чистое чтение (идемпотентность).

    Просроченный открытый отчёт обязан дожить до ответа: закрытие выполняет
    фоновая синхронизация, а не запрос раздела."""
    with _smena(db, freeze, D_GET_PURE) as rep:
        r = manager_client.get("/api/night/today")
        assert r.status_code == 200, r.text
        r = manager_client.get("/api/night/reports?limit=60")
        assert r.status_code == 200, r.text
        db.refresh(rep)
        assert rep.status == "open", \
            "GET раздела закрыл просроченный отчёт — побочная запись в запросе чтения"


def test_night_api_bolshe_ne_vyzyvaet_sync_reports():
    """Страж-исходник: из интерфейса ночного модуля sync_reports исчез целиком."""
    import pathlib

    from app.modules.night import interface

    # маршруты разложены по файлам (шаг 6.5) — проверяем весь пакет interface
    for f in pathlib.Path(interface.__file__).parent.glob("*.py"):
        assert "sync_reports" not in f.read_text(encoding="utf-8"), \
            f"sync_reports вернулся в {f.name} — обслуживание снова выполняется в запросах"


# ─────────────────────── P1-night-3: фоновый раунд и замок лидера ───────────────────────

def test_run_sync_once_zakryvaet_prosrochennyi_otchet(db, freeze):
    """Раунд фоновой синхронизации: просроченный открытый отчёт закрывается (auto)."""
    from app.bootstrap.night_sync import run_sync_once

    created: set[dt.date] = set()
    try:
        with _smena_rt(db, freeze, D_SYNC_ONCE) as rep:
            before = _dates(db)
            res = run_sync_once()          # реальное время: дедлайн июня давно прошёл
            assert "skipped" not in res, res
            db.commit()                    # снять снимок сессии: раунд писал ДРУГОЙ сессией
            created |= _dates(db) - before
            db.refresh(rep)
            assert rep.status == "closed" and rep.close_reason == "auto"
            assert D_SYNC_ONCE.isoformat() in res["closed"], res
    finally:
        from app.modules.night.application.night import current_shift_date

        _cleanup_dates(db, created - {current_shift_date()})


def test_run_sync_once_propuskaet_raund_esli_zamok_u_soseda():
    """Несколько воркеров: раунд выполняет один процесс, соседние пропускают (try_lock)."""
    from app.bootstrap.night_sync import LOCK_NAME, run_sync_once
    from app.core.startup_lock import try_lock

    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import time\n"
         "from app.core.startup_lock import try_lock\n"
         f"with try_lock({LOCK_NAME!r}) as got:\n"
         "    print('held' if got else 'busy', flush=True)\n"
         "    time.sleep(10)\n"],
        cwd=BASE, env=os.environ.copy(), stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "held", "ребёнок не взял замок"
        res = run_sync_once()
        assert res.get("skipped"), f"раунд не пропущен при занятом замке: {res}"
    finally:
        holder.kill()
        holder.wait(timeout=10)
    # после выхода соседа замок свободен
    with try_lock(LOCK_NAME) as got:
        assert got is True


def test_try_lock_neblokiruyushchiy_i_osvobozhdaetsya():
    """try_lock: свободен → True, занят в процессе → сосед не ждёт, после → снова True."""
    from app.core.startup_lock import try_lock

    with try_lock("t-p1-night") as got:
        assert got is True
        holder = subprocess.Popen(
            [sys.executable, "-c",
             "from app.core.startup_lock import try_lock\n"
             "with try_lock('t-p1-night') as g:\n"
             "    print('held' if g else 'busy', flush=True)\n"],
            cwd=BASE, env=os.environ.copy(), stdout=subprocess.PIPE, text=True)
        try:
            assert holder.stdout is not None
            assert holder.stdout.readline().strip() == "busy", \
                "замок отдан второму процессу, пока его держит первый"
        finally:
            holder.wait(timeout=10)
    with try_lock("t-p1-night") as got:
        assert got is True


# ─────────────────────── P1-night-4: честное окно досоздания ───────────────────────

def test_backfill_okno_chestnoe():
    """Окно досоздания пропущенных смен — константа BACKFILL_DAYS, формула-обманка снята."""
    from app.modules.night.application import night

    assert night.BACKFILL_DAYS == 31
    src = inspect.getsource(night.sync_reports)
    assert "min(len(have)" not in src, "формула min(len(have) + 31, 31) вернулась"
    assert "BACKFILL_DAYS" in src


# ─────────────────────── P1-night-1: повторная отметка кара ───────────────────────

def test_povtornaya_otmetka_kara_obnovlyaet_checked_at(manager_client, db, freeze):
    """Перезапись отметки (last write wins) обновляет checked_at и карточку кара.

    До фикса ch.checked_at оставался от ПЕРВОЙ отметки: car.last_checked_at старел,
    а taken_after_check («кар взяли после проверки») ложно горел, когда кар брали
    между двумя отметками."""
    from app.modules.cars.application.catalog import Car

    with _smena_rt(db, freeze, D_CARS) as rep:
        entry = _obhod(manager_client, rep.id)["list"][0]
        car = entry["car"]
        url = f"/api/night/reports/{rep.id}/cars/{car['id']}/check"

        r = manager_client.post(url, data={**NIGHT_CHECK_FORM,
                                           "found_location": car["location"] or "Парковка",
                                           "comment": "первая отметка"})
        assert r.status_code == 200, r.text
        check1 = next(e for e in _obhod(manager_client, rep.id)["list"]
                      if e["car"]["id"] == car["id"])["check"]
        t1 = check1["checked_at"]
        assert t1, "checked_at первой отметки пустой"
        card1 = next(c for c in _park(manager_client) if c["id"] == car["id"])
        assert card1["last_checked_at"] == t1

        # кар взяли ПОСЛЕ первой отметки — флаг «взяли после проверки» горит
        car_orm = db.get(Car, car["id"])
        car_orm.last_taken_at = now_local() + dt.timedelta(seconds=1)
        db.commit()
        check_mid = next(e for e in _obhod(manager_client, rep.id)["list"]
                         if e["car"]["id"] == car["id"])["check"]
        assert check_mid["taken_after_check"] is True

        # повторная отметка (перезапись): время обновляется, флаг гаснет
        time.sleep(1.05)          # checked_at хранится с точностью до секунды
        r = manager_client.post(url, data={**NIGHT_CHECK_FORM,
                                           "found_location": car["location"] or "Парковка",
                                           "comment": "вторая отметка"})
        assert r.status_code == 200, r.text
        check2 = next(e for e in _obhod(manager_client, rep.id)["list"]
                      if e["car"]["id"] == car["id"])["check"]
        t2 = check2["checked_at"]
        assert t2 > t1, f"повторная отметка не обновила checked_at: {t1} → {t2}"
        assert check2["comment"] == "вторая отметка"
        assert check2["taken_after_check"] is False, \
            "кар не брали после ПОВТОРНОЙ отметки, а флаг «взяли после проверки» горит"
        card2 = next(c for c in _park(manager_client) if c["id"] == car["id"])
        assert card2["last_checked_at"] == t2, "карточка кара осталась со старым временем проверки"


def test_settings_nochnoy_sinhronizacii(app_stack):
    """Фоновая синхронизация настраивается и по умолчанию включена (60 с)."""
    from app.bootstrap import night_sync
    from app.core.config import settings

    assert settings.night_sync_enabled is True
    assert settings.night_sync_seconds == 60
    assert night_sync.LOCK_NAME == "night-sync"
