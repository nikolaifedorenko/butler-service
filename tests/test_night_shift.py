"""Ночная смена 20:00–08:00: граница полуночи, создание и автозакрытие отчёта.

Регрессия, которую закрывают эти тесты: ``ensure_report()`` сравнивал время с
«сегодняшней» датой (``now_local().time() < SHIFT_START``), из-за чего смена,
идущая СЕЙЧАС (например 02:00 ночи), оставалась без отчёта, если сервер стартовал
после 20:00 — раздел «Ночной отчёт» был пуст до самого автозакрытия.
Теперь сравнение идёт с моментом старта смены (20:00 даты смены).

Время фиксируется freezegun'ом: в тестах оно указывается в UTC, APP_TZ=Europe/Moscow (+3).
"""
from __future__ import annotations

import datetime as dt

from app.deps import now_local
from app.night import (
    SHIFT_END,
    SHIFT_START,
    close_deadline,
    current_shift_date,
    ensure_report,
    finalize_report,
    sync_reports,
)

# смена, на которой проверяем: заведомо вне окна автобэкапа sync_reports (31 день),
# чтобы тесты не пересекались с демо-данными текущего месяца
SHIFT_DATE = dt.date(2026, 5, 10)
UTC_DURING_SHIFT = "2026-05-10 23:00:00"    # 02:00 МСК 11.05 — смена 10.05 идёт
UTC_BEFORE_SHIFT = "2026-05-10 15:00:00"    # 18:00 МСК 10.05 — смена ещё не началась
UTC_AFTER_DEADLINE = "2026-05-11 06:00:00"  # 09:00 МСК 11.05 — дедлайн 08:00 прошёл


def _cleanup(db, dates: set[dt.date]) -> None:
    """Удалить отчёты, созданные тестом (каскад убирает области и пункты)."""
    from sqlalchemy import select

    from app.models import NightReport

    for rep in db.scalars(select(NightReport).where(NightReport.date.in_(dates))):
        db.delete(rep)
    db.commit()


def test_shift_boundaries_are_consistent():
    """12:00 ночи принадлежит смене, начавшейся накануне в 20:00."""
    assert dt.time(20, 0) == SHIFT_START
    assert dt.time(8, 0) == SHIFT_END
    assert close_deadline(SHIFT_DATE) == dt.datetime(2026, 5, 11, 8, 0)


def test_during_shift_now_is_after_shift_start(freeze):
    with freeze(UTC_DURING_SHIFT):
        now = now_local()
        assert now.date() == SHIFT_DATE + dt.timedelta(days=1)
        assert current_shift_date() == SHIFT_DATE
        # ключевая проверка: «сейчас» уже позже старта смены 10.05 в 20:00
        assert now >= dt.datetime.combine(SHIFT_DATE, SHIFT_START)


def test_ensure_report_creates_otchet_dlya_idushchei_smeny(freeze, db):
    """Регрессия: в 02:00 идущая смена обязана получить отчёт."""
    created: set[dt.date] = set()
    try:
        with freeze(UTC_DURING_SHIFT):
            rep = ensure_report(db, SHIFT_DATE)
            assert rep is not None, (
                "отчёт для ИДУЩЕЙ ночной смены не создан — раздел «Ночной отчёт» "
                "будет пуст до автозакрытия (старая ошибка сравнения с today)")
            assert rep.date == SHIFT_DATE
            assert rep.status == "open"
            created.add(SHIFT_DATE)
            # снимок областей непустой: обход можно вести сразу
            assert len(rep.areas) >= 1
            assert any(s.category == "cars" for s in rep.areas), \
                "шаг «Проверка электрокаров» не создан"
    finally:
        _cleanup(db, created)


def test_ensure_report_ne_sozdaet_budushchuyu_smenu(freeze, db):
    """До 20:00 отчёт будущей смены не создаётся (батлеры не видят «завтрашний» обход)."""
    created: set[dt.date] = set()
    try:
        with freeze(UTC_BEFORE_SHIFT):
            assert now_local() < dt.datetime.combine(SHIFT_DATE, SHIFT_START)
            rep = ensure_report(db, SHIFT_DATE)
            assert rep is None, "отчёт создан раньше начала смены"
    finally:
        _cleanup(db, created)


def test_sync_reports_zakryvaet_nastupivshii_dedlain(freeze, db):
    """После 08:00 отчёт закрывается сам; незакрытые области дают итог «неполный»."""
    from sqlalchemy import select

    from app.models import NightReport

    created: set[dt.date] = set()
    try:
        with freeze(UTC_DURING_SHIFT):
            rep = ensure_report(db, SHIFT_DATE)
            assert rep is not None
            created.add(SHIFT_DATE)
            rep_id = rep.id

        with freeze(UTC_AFTER_DEADLINE):
            before = {d for (d,) in db.execute(select(NightReport.date))}
            sync_reports(db)
            after = {d for (d,) in db.execute(select(NightReport.date))}
            created.update(after - before)

            rep = db.get(NightReport, rep_id)
            assert rep.status == "closed", "отчёт не закрыт после дедлайна 08:00"
            assert rep.result == "partial", \
                f"ожидался итог «неполный» (области не закрыты), получено {rep.result!r}"
            assert rep.closed_at is not None
    finally:
        _cleanup(db, created)


def test_finalize_report_polnyi_itog_pri_zakrytyh_oblastyah(freeze, db):
    """Все области закрыты + шаг электрокаров завершён → итог «полный»."""
    created: set[dt.date] = set()
    try:
        with freeze(UTC_DURING_SHIFT):
            rep = ensure_report(db, SHIFT_DATE)
            assert rep is not None
            created.add(SHIFT_DATE)
            for sec in rep.areas:
                sec.status = "done"
                sec.closed_at = now_local()
            rep.cars_step_done = True
            db.commit()
            result = finalize_report(rep)
            db.commit()
            assert result == "full", f"ожидался «полный», получено {result!r}"
    finally:
        _cleanup(db, created)


def test_today_report_dostupen_vo_vremya_smeny(freeze, manager_client, db):
    """GET /api/night/today во время идущей смены отдаёт отчёт, а не «ещё не началась».

    sync_reports() внутри маршрута досоздаёт пропущенные смены за 31 день, поэтому
    до и после запроса снимаем список дат и убираем всё, что появилось.
    """
    from sqlalchemy import select

    from app.models import NightReport

    def dates() -> set[dt.date]:
        return {d for (d,) in db.execute(select(NightReport.date))}

    before = dates()
    try:
        with freeze(UTC_DURING_SHIFT):
            today_shift = current_shift_date()
            r = manager_client.get("/api/night/today")
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["available"] is True, (
                f"во время идущей смены отчёт недоступен: {data.get('note')!r}")
            assert data["report"]["date"] == today_shift.isoformat()
            assert data["report"]["status"] == "open"
    finally:
        db.expire_all()
        _cleanup(db, dates() - before)
