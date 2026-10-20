"""DoD «TZ/now — только core/time.py» (долг №3, батч 20.10.2026).

Граничный режим: 22:30 UTC — в Москве (APP_TZ по умолчанию) уже 01:30 следующих
суток. Раньше семь вызовов `dt.date.today()` в timesheet читали СЕРВЕРНУЮ дату и
в ночную смену выбирали «вчерашнюю» версию справочников/день по умолчанию; теперь
все они используют `core.time.local_date()` (дата объекта). Тесты фиксируют:
(1) сам инвариант local_date ≠ серверное today у полуночи; (2) поведение экрана
«Расчёт» — действующая версия настроек выбирается по дате объекта.
"""
from __future__ import annotations

import datetime as dt
import json

from freezegun import freeze_time

UTC_EVENING = "2026-10-20 22:30:00"      # UTC; в Москве — 2026-10-21 01:30


def test_local_date_is_object_date_not_server_date():
    """Инвариант источника: local_date() — сутки объекта (APP_TZ), today() — сервера."""
    from app.core.time import local_date

    with freeze_time(UTC_EVENING):
        assert local_date() == dt.date(2026, 10, 21)
        # на сервере с TZ=Europe/Moscow даты совпадут — это не ошибка теста:
        # утверждается только каноническое значение local_date().


def test_day_code_colors_follow_object_date(db):
    """`day_code_colors()` (engine_common) читает действующую версию справочников
    по «сегодня» ОБЪЕКТА: версия с valid_from = локальное завтра (по UTC ещё
    сегодня) обязана победить. До фикса base_version(db, dt.date.today()) в
    ночном окне выбирал вчерашнюю версию.

    Через HTTP не проверяем намеренно: freezegun подменяет dt.date, и FastAPI
    ломается на аннотации `on: Optional[dt.date]` (pydantic introspection).
    Отсутствие `today()` в модулях гарантировано AST-стражем
    (test_modules_architecture.py::test_no_system_time_reads_in_modules).
    """
    from app.core.time import local_date
    from app.modules.timesheet.adapters.orm import EngineSettingsVersion
    from app.modules.timesheet.adapters.settings_codec import to_payload
    from app.modules.timesheet.application.engine_common import day_code_colors
    from app.modules.timesheet.domain.settings.defaults import default_settings

    with freeze_time(UTC_EVENING):
        object_today = local_date()                       # 2026-10-21 (Москва)
        payload = to_payload(default_settings())
        code = next(iter(payload["day_code_policy"]))
        marker = "#0f0f0f"
        payload["day_code_policy"][code]["color"] = marker
        row = EngineSettingsVersion(valid_from=object_today,
                                    payload_json=json.dumps(payload),
                                    note="tz-boundary-test")
        db.add(row)
        db.commit()
        try:
            colors = day_code_colors(db)
            assert colors.get(code) == marker, (
                "действующая версия выбрана не по дате объекта — где-то снова "
                "читается серверное dt.date.today()")
        finally:
            db.delete(row)
            db.commit()
