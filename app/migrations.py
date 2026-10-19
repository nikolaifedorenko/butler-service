"""Миграции схемы БД, применяемые при старте сервера.

Вынесено из app/main.py: стартовая миграция разрослась до нескольких сотен строк
raw-DDL и переносов данных, и в точке входа её было ни прочитать, ни протестировать.

Как это работает (и какие у подхода ограничения)
----------------------------------------------
* ``Base.metadata.create_all()`` создаёт отсутствующие таблицы (см. app/db.py);
* ``migrate_db()`` дописывает недостающие КОЛОНКИ в уже существующие таблицы
  (``ALTER TABLE ... ADD COLUMN``), создаёт индексы и переносит данные
  (переименования ролей и блоков, заполнение doc_type, периоды работы и т.д.);
* все шаги идемпотентны: повторный вызов ничего не ломает (проверено
  tests/test_selfcheck.py::test_migraciya_idempotentna);
* ожидаемое состояние схемы проверяет ``GET /api/selfcheck``, который берёт
  список таблиц и колонок из models.py — единственного источника правды.

Ограничение: это «лёгкие» миграции без версий и отката. Для боевой базы с
данными заказчиков следующий шаг — Alembic (``alembic revision --autogenerate``
+ ``alembic upgrade head`` в Dockerfile): тогда появится история, откат и
возможность применять миграции отдельно от запуска приложения.
"""
from __future__ import annotations

import contextlib

from .db import SessionLocal, engine


def migrate_db() -> None:
    """Лёгкая миграция: добавляет новые колонки/таблицы и переносит данные,
    чтобы ранее созданные локальные БД продолжали работать после обновления.

    Что делает текущая версия:
      * роли: senior → supervisor;
      * блоки: «Администрация» → «Пятидневка» (+ индивидуальный шаблон выходных);
      * сотрудники: гражданство, служба/подразделение;
      * словарь смен: архивация вместо удаления, ревизии, «списывать из банка», тип документа;
      * ячейки графика: частичное отсутствие (отпросился с … до …);
      * табель: несогласованные перерывы и часы согласованного отсутствия;
      * периоды работы (приём → увольнение → повторный приём);
      * корректировки банка часов;
      * дни двойной оплаты (производственный календарь) и периоды ВИП-гостей:
        таблицы double_pay_days / vip_double_pay и колонки ДЯ2/ДН2 в табеле.
    """

    from sqlalchemy import inspect, text

    insp = inspect(engine)
    additions = {
        "employees": [
            ("tab_number", "VARCHAR(40) DEFAULT ''"),
            ("hired_at", "DATE"),
            ("emergency_name", "VARCHAR(200) DEFAULT ''"),
            ("emergency_phone", "VARCHAR(40) DEFAULT ''"),
            ("schedule_pattern", "VARCHAR(60) DEFAULT ''"),
            ("schedule_anchor", "DATE"),
            ("deleted_at", "DATE"),
            ("telegram", "VARCHAR(64) DEFAULT ''"),
            ("email", "VARCHAR(120) DEFAULT ''"),
            ("dismissed_at", "DATE"),
            ("full_name_genitive", "VARCHAR(220) DEFAULT ''"),
            ("nationality", "VARCHAR(120) DEFAULT ''"),
            ("subdivision", "VARCHAR(160) DEFAULT ''"),
        ],
        "timesheet_rows": [
            ("pay_ot_day", "FLOAT DEFAULT 0"),
            ("pay_ot_night", "FLOAT DEFAULT 0"),
            ("late_hours", "FLOAT DEFAULT 0"),
            ("early_hours", "FLOAT DEFAULT 0"),
            ("unused_hours", "FLOAT DEFAULT 0"),
            ("gap_hours", "FLOAT DEFAULT 0"),
            ("auth_hours", "FLOAT DEFAULT 0"),
            ("pay_ot_day2", "FLOAT DEFAULT 0"),
            ("pay_ot_night2", "FLOAT DEFAULT 0"),
            ("double_reason", "VARCHAR(16) DEFAULT ''"),
        ],
        "shift_types": [
            ("doc_type", "VARCHAR(40) DEFAULT ''"),
            ("archived_at", "DATE"),
            ("punch_in_allowed", "BOOLEAN DEFAULT 1"),
            ("punch_out_allowed", "BOOLEAN DEFAULT 1"),
        ],
        "schedule_entries": [
            ("partial_shift_id", "INTEGER"),
            ("from_time", "VARCHAR(5) DEFAULT ''"),
            ("until_time", "VARCHAR(5) DEFAULT ''"),
            ("punch_in_override", "BOOLEAN"),
            ("punch_out_override", "BOOLEAN"),
        ],
        "block_assignments": [
            ("pattern_json", "TEXT DEFAULT ''"),
        ],
        # ночной отчёт v2 (19.10.2026): зоны обхода — первый уровень навигации,
        # снимок зоны в отчёте и ссылка ответа на пункт шаблона зоны
        "night_areas": [
            ("zone_id", "INTEGER"),
        ],
        "night_area_sections": [
            ("zone_id", "INTEGER"),
            ("zone_name", "VARCHAR(160) DEFAULT ''"),
        ],
        "night_check_items": [
            ("zone_item_id", "INTEGER"),
        ],
        # ночная отметка кара (19.10.2026): где батлер нашёл кар и факт перепарковки
        # («кар был на месте, но его переставили» — место в карточке могло устареть)
        "car_night_checks": [
            ("found_location", "VARCHAR(160) DEFAULT ''"),
            ("moved", "BOOLEAN DEFAULT 0"),
        ],
        "users": [
            ("token_version", "INTEGER DEFAULT 0"),
        ],
    }
    with engine.begin() as con:
        for table, cols in additions.items():
            if not insp.has_table(table):
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols:
                if name not in have:
                    con.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

        if insp.has_table("users"):
            con.execute(text("UPDATE users SET role='supervisor' WHERE role='senior'"))
        if insp.has_table("punches"):
            # основной фильтр всех запросов по отметкам: employee_id = ? AND ts >= ?
            con.execute(text("CREATE INDEX IF NOT EXISTS ix_punches_emp_ts ON punches (employee_id, ts)"))
        # доска «кто на работе» и статус смены фильтруют по start_utc без employee_id —
        # без индекса это полный скан растущих таблиц
        if insp.has_table("schedule_shifts"):
            con.execute(text("CREATE INDEX IF NOT EXISTS ix_sched_shifts_start "
                             "ON schedule_shifts (start_utc)"))
        if insp.has_table("schedule_absences"):
            con.execute(text("CREATE INDEX IF NOT EXISTS ix_sched_abs_start "
                             "ON schedule_absences (start_utc)"))

        # «Администрация» → «Пятидневка» (название блока уточнили по смыслу)
        if insp.has_table("employees"):
            con.execute(text("UPDATE employees SET schedule_group='Пятидневка' "
                             "WHERE schedule_group='Администрация'"))
        if insp.has_table("block_assignments"):
            con.execute(text('UPDATE block_assignments SET "group"=:new '
                             'WHERE "group"=:old'), {"new": "Пятидневка", "old": "Администрация"})

        # вид отсутствий, по которому печатаем документ, и списание часов с банка.
        # AWAY_HOURS упомянут только как исторический код: вид слит с TIMEOFF_HOURS
        # в единую сущность «отпросился (выходной за часы)» — см. migrate_timeoff_entity
        if insp.has_table("shift_types"):
            for code, doc_type in (("VACATION", "vacation_paid"),
                                   ("VACATION_UNPAID", "vacation_unpaid"),
                                   ("TIMEOFF_HOURS", "day_off_hours"),
                                   ("AWAY_HOURS", "time_off_request")):
                con.execute(text("UPDATE shift_types SET doc_type=:dt "
                                 "WHERE code=:c AND (doc_type IS NULL OR doc_type='')"),
                            {"dt": doc_type, "c": code})
            _apply_timesheet_code_normative(con)

        # сотрудники без записей блоков получают открытую запись от даты приёма
        if insp.has_table("employees") and insp.has_table("block_assignments"):
            con.execute(text("""
                INSERT INTO block_assignments (employee_id, "group", start_date, end_date, pattern_json)
                SELECT e.id, e.schedule_group, COALESCE(e.hired_at, '2020-01-01'), NULL, ''
                FROM employees e
                WHERE e.schedule_group <> '' AND e.deleted_at IS NULL
                  AND NOT EXISTS (SELECT 1 FROM block_assignments b WHERE b.employee_id = e.id)
            """))

        # справочник служб/подразделений: заполняем существующими значениями из карточек
        if insp.has_table("employees") and insp.has_table("subdivisions"):
            con.execute(text("""
                INSERT INTO subdivisions (name)
                SELECT DISTINCT e.subdivision FROM employees e
                WHERE e.subdivision <> ''
                  AND NOT EXISTS (SELECT 1 FROM subdivisions s WHERE s.name = e.subdivision)
            """))

    # «НБ» — артефакт: вид SICK_UNPAID (добавлялся 16.10.2026) убираем из словаря
    _migrate_remove_sick_unpaid()
    # старым базам докладываем новые смены словаря из сида
    _migrate_missing_shifts()
    # периоды работы (приём → увольнение → повторный приём)
    _migrate_employment_periods()
    # индивидуальный шаблон пятидневки: берём выходные из общих настроек (как было раньше)
    _migrate_fiveday_patterns()
    # общий шаблон блоков в настройках: переименовываем ключ «Администрация»
    _migrate_base_groups_key()


def _migrate_remove_sick_unpaid() -> None:
    """Историческая миграция (16.10.2026): вид «НБ»/SICK_UNPAID. С 18.10.2026 все
    виды отсутствий словаря, кроме системного «Отпросился», удаляет
    migrate_schedule_dict_simplify — здесь делать нечего."""
    return


def _migrate_missing_shifts() -> None:
    """Историческая миграция: докладывала старым базам смены из старого сида.
    Словарь смен 18.10.2026 изменился (только добавляемые смены и «Отпросился»),
    свежие базы заполняет сид, старым базам состав правит владелец."""
    return


def _apply_timesheet_code_normative(con) -> None:
    """Норматив от 12.10.2026: коды Табеля «С» и «НВ» из справочника исключены.

    * суточная смена (SUTKI) — графиковая смена: в Табеле обычная явка «Я», по факту
      сотрудник работает через полночь, а часы вне окна расчёт относит к переработке;
    * «выходной за ранее отработанные часы» (TIMEOFF_HOURS) — отсутствие в Графике:
      в Табеле остаётся явка, недостачу гасит банк часов (паттерн EX-29).

    Правим только словарь (shift_types), историю Табеля не переписываем: версии
    справочников очищает engine_bootstrap.strip_removed_day_codes, и только если
    в Табеле не осталось строк с этими кодами.
    """

    # связка «смена → код Табеля» (tzh_code) удалена 18.10.2026: править нечего


def _migrate_employment_periods() -> None:
    """Создать периоды работы по hired_at/dismissed_at (один раз, при переходе на новую схему)."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if not (insp.has_table("employment_periods") and insp.has_table("employees")):
        return
    with engine.begin() as con:
        con.execute(text("""
            INSERT INTO employment_periods (employee_id, start_date, end_date, note, created_at)
            SELECT e.id,
                   COALESCE(e.hired_at, '2020-01-01'),
                   CASE WHEN e.dismissed_at IS NOT NULL AND e.active = 0 THEN e.dismissed_at ELSE NULL END,
                   'восстановлено по дате приёма/увольнения',
                   CURRENT_TIMESTAMP
            FROM employees e
            WHERE NOT EXISTS (SELECT 1 FROM employment_periods p WHERE p.employee_id = e.id)
        """))
        # уволенные: открытый период блока закрываем датой увольнения (последний рабочий день)
        con.execute(text("""
            UPDATE block_assignments
            SET end_date = (SELECT e.dismissed_at FROM employees e WHERE e.id = block_assignments.employee_id)
            WHERE end_date IS NULL
              AND employee_id IN (SELECT id FROM employees
                                  WHERE dismissed_at IS NOT NULL AND active = 0 AND deleted_at IS NULL)
        """))


def _migrate_fiveday_patterns() -> None:
    """Пятидневка: перенести выходные из общих настроек в шаблон каждого сотрудника,
    чтобы дальше выходные можно было задавать индивидуально (вс/пн, пт/сб, сб/вс…)."""
    import json

    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if not (insp.has_table("block_assignments") and insp.has_table("settings")):
        return
    with engine.begin() as con:
        row = con.execute(text("SELECT value FROM settings WHERE key='base_groups'")).first()
        off_weekdays, shift_code = [5, 6], "DAY9"
        if row and row[0]:
            try:
                groups = json.loads(row[0])
                cfg = groups.get("Пятидневка") or groups.get("Администрация") or {}
                off_weekdays = cfg.get("off_weekdays") or off_weekdays
                shift_code = cfg.get("shift_code") or shift_code
            except (json.JSONDecodeError, AttributeError):
                pass
        con.execute(text("""
            UPDATE block_assignments
            SET pattern_json = :pj
            WHERE "group" = 'Пятидневка' AND (pattern_json IS NULL OR pattern_json = '')
        """), {"pj": json.dumps({"kind": "week5", "off_weekdays": off_weekdays,
                                 "shift_code": shift_code}, ensure_ascii=False)})


def _migrate_base_groups_key() -> None:
    import json

    from sqlalchemy import text

    with engine.begin() as con:
        row = con.execute(text("SELECT value FROM settings WHERE key='base_groups'")).first()
        if not row or not row[0]:
            return
        try:
            groups = json.loads(row[0])
        except json.JSONDecodeError:
            return
        if "Администрация" in groups and "Пятидневка" not in groups:
            groups["Пятидневка"] = groups.pop("Администрация")
            con.execute(text("UPDATE settings SET value=:v WHERE key='base_groups'"),
                        {"v": json.dumps(groups, ensure_ascii=False)})


def seed_statement_kinds() -> None:
    """Словарь видов заявлений: при первом запуске новой версии добавляем встроенные
    виды (тексты — из сохранённых настроек, иначе дефолтные). Если словарь уже
    заполнен — не вмешиваемся (удалённые пользователем виды не воскрешаем)."""
    from sqlalchemy import func, select

    from .doc_render import DOC_TYPES
    from .doc_templates import load_doc_templates
    from .models import StatementKind

    db = SessionLocal()
    try:
        if db.scalar(select(func.count(StatementKind.id))):
            return
        doc = load_doc_templates(db)
        legacy_text = {
            "vacation_paid": doc["vacation"],
            "vacation_unpaid": doc["vacation_unpaid"],
            "day_off_hours": doc["day_off_hours"],
            "time_off_request": doc["time_off_request"],
        }
        order = 10
        for code, name in DOC_TYPES.items():
            db.add(StatementKind(code=code, name=name, text=legacy_text.get(code, ""),
                                 builtin=True, sort_order=order))
            order += 10
        db.commit()
    finally:
        db.close()


def migrate_shift_tabel_codes() -> None:
    """Историческая миграция T1 (12.10.2026): чистила «код в табеле» у смен.
    Поле tzh_code удалено 18.10.2026 вместе со связкой справочников."""
    return


TIMEOFF_UNIFIED_CODE = "TIMEOFF_HOURS"
TIMEOFF_UNIFIED_NAME = "Отпросился (выходной за часы)"
TIMEOFF_MERGED_CODES = ("AWAY_HOURS",)


def migrate_timeoff_entity() -> None:
    """T4 (решение владельца Q3, 12.10.2026): «отпросился» и «выходной за часы» — ОДНА сущность.

    Одна запись словаря с двумя точками ввода: интервал части смены либо вся смена.
    Старым базам: записи согласованных отсутствий дубля (`AWAY_HOURS` «Отпросился:
    отсутствовал часть смены») переносятся на объединённый вид, сам дубль архивируется —
    прошлые ячейки Графика и напечатанные заявления остаются читаемыми (архив, не удаление).
    Название объединённого вида приводится к нормативному, только если его не меняли
    руками. Идемпотентно.
    """
    from sqlalchemy import inspect, text

    from .deps import local_date

    insp = inspect(engine)
    if not (insp.has_table("shift_types") and insp.has_table("schedule_absences")):
        return
    with engine.begin() as con:
        target = con.execute(text(
            "SELECT id, name FROM shift_types WHERE code=:c"),
            {"c": TIMEOFF_UNIFIED_CODE}).first()
        if target is None:
            return                      # свежую базу заполняет сид новым словарём
        if (target[1] or "") == "Выходной за часы":
            con.execute(text("UPDATE shift_types SET name=:n WHERE id=:i"),
                        {"n": TIMEOFF_UNIFIED_NAME, "i": target[0]})
        if not con.execute(text("SELECT doc_type FROM shift_types WHERE id=:i"),
                           {"i": target[0]}).scalar():
            # базовая привязка заявления; точку ввода учитывает doc_type_of_absence (T4)
            con.execute(text("UPDATE shift_types SET doc_type='day_off_hours' WHERE id=:i"),
                        {"i": target[0]})
        today = local_date().isoformat()
        for code in TIMEOFF_MERGED_CODES:
            dup = con.execute(text("SELECT id FROM shift_types WHERE code=:c"), {"c": code}).first()
            if dup is None:
                continue
            con.execute(text("UPDATE schedule_absences SET kind_id=:t WHERE kind_id=:d"),
                        {"t": target[0], "d": dup[0]})
            con.execute(text("UPDATE shift_types SET active=0, archived_at=:d WHERE id=:i "
                             "AND archived_at IS NULL"), {"d": today, "i": dup[0]})


def migrate_settings_value_text() -> None:
    """settings.value — TEXT вместо VARCHAR(255) (16.10.2026).

    В settings хранятся шаблоны документов (tpl_*), а они длиннее 255 символов:
    SQLite длину не контролирует, PostgreSQL отклонял сохранение шаблонов
    («value too long for type character varying(255)»). На PostgreSQL колонка
    расширяется, на SQLite DDL не требуется. Идемпотентно."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if not insp.has_table("settings") or engine.dialect.name != "postgresql":
        return
    with engine.begin() as con:
        con.execute(text("ALTER TABLE settings ALTER COLUMN value TYPE TEXT"))


def migrate_manual_replaces_generated() -> None:
    """Старые базы: ручная смена не вытесняла генерацию дня (дефект до 16.10.2026) —
    в ячейке Графика соседствовали смена из Табеля и ручная («08:00–20:00» и
    «09:00–18:00» разом). Удаляем generated-строки тех дней, где стоит ручная смена;
    движок после правки (schedule_view.save_schedule_day / rebuild_generated_schedule)
    их больше не создаёт. Идемпотентно."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if not insp.has_table("schedule_shifts"):
        return
    with engine.begin() as con:
        con.execute(text(
            "DELETE FROM schedule_shifts WHERE source = 'generated' AND EXISTS ("
            "SELECT 1 FROM schedule_shifts AS m WHERE m.source = 'manual' "
            "AND m.employee_id = schedule_shifts.employee_id "
            "AND m.date = schedule_shifts.date)"))


def migrate_time_off_template() -> None:
    """Шаблон «об отсутствии на рабочем месте» с перечнем интервалов (16.10.2026).

    Несколько отлучек в один день печатаются ОДНИМ заявлением со списком интервалов
    («с 14:00 до 16:00 (2 ч) и с 18:00 до 20:00 (2 ч)»): плейсхолдеры {from_time}/
    {until_time}/{hours} для этого не годятся, в тексте появился {intervals}.
    Сохранённые тексты (настройка tpl_time_off_request и текст вида заявления
    time_off_request), которые НЕ редактировали вручную, заменяются на новую версию;
    пользовательские правки не трогаются. Идемпотентно.
    """
    from sqlalchemy import select

    from .doc_templates import DEFAULT_TPL_TIME_OFF, PREV_DEFAULT_TPL_TIME_OFF
    from .models import Setting, StatementKind

    db = SessionLocal()
    try:
        row = db.scalar(select(Setting).where(Setting.key == "tpl_time_off_request"))
        if row is not None and (row.value or "") == PREV_DEFAULT_TPL_TIME_OFF:
            row.value = DEFAULT_TPL_TIME_OFF
        kind = db.scalar(select(StatementKind).where(StatementKind.code == "time_off_request"))
        if kind is not None and (kind.text or "") == PREV_DEFAULT_TPL_TIME_OFF:
            kind.text = DEFAULT_TPL_TIME_OFF
        db.commit()
    finally:
        db.close()


def migrate_night_cars() -> None:
    """Старым локальным БД докладываем таблицы ночных отчётов и электрокаров.

    Новые таблицы создаёт Base.metadata.create_all, но в SQLite у create_all нет
    if-not-exists для индексов на уже существующих таблицах — поэтому всё делаем
    аккуратно, по inspect. Полноту схемы проверяет /api/selfcheck."""
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import text

    insp = sa_inspect(engine)
    with engine.begin() as con:
        for idx in (
            "CREATE INDEX IF NOT EXISTS ix_night_sections_report ON night_area_sections (report_id)",
            "CREATE INDEX IF NOT EXISTS ix_night_items_section ON night_check_items (section_id)",
            "CREATE INDEX IF NOT EXISTS ix_car_history_car_ts ON car_history (car_id, ts)",
            "CREATE INDEX IF NOT EXISTS ix_photos_kind_ref ON photos (kind, ref_id)",
        ):
            # таблица ещё не создана — create_all разберётся сам
            with contextlib.suppress(Exception):
                con.execute(text(idx))
    # шаг «Проверка электрокаров» для старых открытых смен, где его не было
    if insp.has_table("night_reports") and insp.has_table("night_area_sections"):
        from .night import CAR_AREA_NAME

        with engine.begin() as con:
            con.execute(text("""
                INSERT INTO night_area_sections (report_id, area_id, name, category, snapshot_json,
                                                sort_order, status)
                SELECT r.id, NULL, :name, 'cars', '[]', 900, 'free'
                FROM night_reports r
                WHERE NOT EXISTS (SELECT 1 FROM night_area_sections s
                                  WHERE s.report_id = r.id AND s.category = 'cars')
            """), {"name": CAR_AREA_NAME})


def migrate_night_zones() -> None:
    """Зоны обхода ночного отчёта (v2, 19.10.2026): зона вырастает из «категории» области.

    Что делает:
      * по зоне на каждое значение ``night_areas.category`` (пустая категория →
        зона «Без зоны») и простановка ``night_areas.zone_id``;
      * снимок в уже созданных отчётах: ``night_area_sections.zone_id/zone_name``
        из области — история не должна зависеть от более поздних правок справочника;
      * индексы новых колонок (в SQLite ``ADD COLUMN`` индекс не создаёт).

    Идемпотентна: повторный вызов ничего не создаёт и не перезаписывает
    (проверено tests/test_night_zones.py).
    """
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import text

    from .deps import now_local

    insp = sa_inspect(engine)
    if not (insp.has_table("night_areas") and insp.has_table("night_zones")):
        return                      # таблицы ещё не созданы — create_all разберётся сам
    ts = now_local()
    with engine.begin() as con:
        for idx in (
            "CREATE INDEX IF NOT EXISTS ix_night_areas_zone_id ON night_areas (zone_id)",
            "CREATE INDEX IF NOT EXISTS ix_night_area_sections_zone ON night_area_sections (zone_id)",
            "CREATE INDEX IF NOT EXISTS ix_night_check_items_zone_item ON night_check_items (zone_item_id)",
            "CREATE INDEX IF NOT EXISTS ix_zone_checklist_items_zone ON zone_checklist_items (zone_id)",
            "CREATE INDEX IF NOT EXISTS ix_checklist_overrides_area ON checklist_overrides (area_id)",
            "CREATE INDEX IF NOT EXISTS ix_checklist_overrides_zone_item ON checklist_overrides (zone_item_id)",
        ):
            # таблицы шаблона зоны/правок может ещё не быть — не мешаем create_all
            with contextlib.suppress(Exception):
                con.execute(text(idx))
        cats = [r[0] for r in con.execute(text(
            "SELECT DISTINCT COALESCE(category, '') FROM night_areas WHERE zone_id IS NULL"))]
        for cat in cats:
            name = cat.strip() or "Без зоны"
            row = con.execute(text("SELECT id FROM night_zones WHERE name = :n"), {"n": name}).first()
            if row is None:
                con.execute(text("INSERT INTO night_zones (name, sort_order, active, created_at, updated_at) "
                                 "VALUES (:n, 100, 1, :ts, :ts)"), {"n": name, "ts": ts})
                row = con.execute(text("SELECT id FROM night_zones WHERE name = :n"), {"n": name}).first()
            con.execute(text("UPDATE night_areas SET zone_id = :z WHERE zone_id IS NULL "
                             "AND COALESCE(category, '') = :cat"), {"z": row[0], "cat": cat})
        # снимок зоны в существующих отчётах (у шага «Проверка электрокаров» area_id NULL — не трогаем)
        con.execute(text("""
            UPDATE night_area_sections
               SET zone_id = (SELECT a.zone_id FROM night_areas a
                               WHERE a.id = night_area_sections.area_id),
                   zone_name = (SELECT z.name FROM night_zones z
                                 WHERE z.id = (SELECT a.zone_id FROM night_areas a
                                                WHERE a.id = night_area_sections.area_id))
             WHERE area_id IS NOT NULL AND COALESCE(zone_name, '') = ''
        """))


def migrate_engine_v7() -> None:
    """Миграция на движок v7.1 (base 15 «Миграция прототипа» + решение владельца:
    расчётные данные v4 были тестовыми — удаляются).

    * новые таблицы schedule_shifts / schedule_absences создаёт create_all;
    * bank_adjustments.reason_code — маркер OPENING_SEED (v7.1/R37);
    * period_closings.flags_json — снимок флагов при закрытии (7.2);
    * legacy-таблицы timesheet_rows и schedule_entries удаляются вместе со старым движком;
    * расчётные данные автоматически НЕ очищаются (раньше — однократно по маркеру
      в settings); маркер только записывается, очистка демо-базы — вручную.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    existing = set(insp.get_table_names())
    with engine.begin() as con:
        cols = {c["name"] for c in insp.get_columns("bank_adjustments")} \
            if "bank_adjustments" in existing else set()
        if "reason_code" not in cols and "bank_adjustments" in existing:
            con.execute(text("ALTER TABLE bank_adjustments ADD COLUMN reason_code VARCHAR(32) DEFAULT ''"))
        cols = {c["name"] for c in insp.get_columns("period_closings")} \
            if "period_closings" in existing else set()
        if "flags_json" not in cols and "period_closings" in existing:
            con.execute(text("ALTER TABLE period_closings ADD COLUMN flags_json TEXT DEFAULT '{}'"))
        for legacy in ("timesheet_rows", "schedule_entries"):
            if legacy in existing:
                con.execute(text(f"DROP TABLE IF EXISTS {legacy}"))
        # Раньше при отсутствии маркера здесь выполнялся DELETE FROM по семи расчётным
        # таблицам (Табель, смены, закрытия периодов…). Переход v4 → v7.1 уже выполнен
        # на всех стендах, а автоматическое удаление на старте опасно: восстановление
        # бэкапа без этой строки в settings молча стирало бы боевые данные.
        # Теперь маркер только фиксируется; демо-базу при необходимости пересоздают
        # вручную (удалить timetrack.db — сид заполнит её заново).
        marker = con.execute(text(
            "SELECT value FROM settings WHERE key = 'engine_v7_reset'")).scalar() \
            if "settings" in existing else "n/a"
        has_data = "tabel_days" in existing and con.execute(
            text("SELECT 1 FROM tabel_days LIMIT 1")).first() is not None
        if marker is None:
            import logging
            if has_data:  # на свежей базе предупреждать не о чем
                logging.getLogger("uvicorn.error").warning(
                    "migrate_engine_v7: маркер engine_v7_reset не найден — данные НЕ очищаются "
                    "(автоочистка отключена), маркер записан")
            con.execute(text(
                "INSERT INTO settings (key, value, description) VALUES "
                "('engine_v7_reset', '1', 'Движок v7.1: маркер миграции (автоочистка отключена)')"))


def migrate_schedule_dict_simplify() -> None:
    """Упрощение словаря смен и базового цикла (решения владельца 18.10.2026).

    * значение рабочего дня переезжает к сотруднику: паттерны блоков и настройки
      блоков получают ключ "value" (ключ CFG-WINDOWS), вычисленный из прежней
      связки «смена → код Табеля → окно»; ключ "shift_code" убирается;
    * виды отсутствий словаря (больничный, отпуск, НН…) удаляются: отсутствия
      ставятся кодами Табеля; согласованные отсутствия Графика перепривязываются
      к системному виду «Отпросился (выходной за часы)» (создаётся, если его нет);
    * столбцы display_code / tzh_code / deduct_from_bank удаляются из shift_types
      и shift_revisions: связка справочников разорвана, банк гасит недостачу дня
      механически (домен bank/ флаг не читал).
    Миграция идемпотентна: ориентируется на наличие столбцов и видов.
    """
    import datetime as dt
    import json

    from sqlalchemy import inspect, text

    from .engine.adapters.sql_settings import SqlSettingsAdapter
    from .engine.application.months import month_period

    insp = inspect(engine)
    existing = set(insp.get_table_names())
    if "shift_types" not in existing:
        return
    cols = {c["name"] for c in insp.get_columns("shift_types")}
    if "tzh_code" not in cols:
        return                                    # миграция уже выполнена
    today = dt.date.today()
    windows = {}
    try:
        session = SessionLocal()
        try:
            st = SqlSettingsAdapter(session).load(month_period(today.year, today.month))
            windows = dict(st.windows)
        finally:
            session.close()
    except Exception:                              # свежая база: версии ещё нет
        windows = {}
    with engine.begin() as con:

        def value_of(shift_code: str, start: str, end: str, overnight: bool) -> str:
            def hm(v: str) -> int:
                h, m = (int(x) for x in (v or "0:0").split(":"))
                return h * 60 + m
            s, e = hm(start), hm(end)
            for key, w in windows.items():
                if (w.start_minute, w.end_minute) == (s, e):
                    return key
            if overnight or e <= s:                # якорь: окно начинается со смены
                for key, w in windows.items():
                    if w.start_minute == s:
                        return key
            return ""

        shifts = con.execute(text(
            "SELECT id, code, start_time, end_time, overnight, kind FROM shift_types")).mappings().all()
        by_code = {r["code"]: r for r in shifts}
        value_by_code = {r["code"]: value_of(r["code"], r["start_time"], r["end_time"],
                                             bool(r["overnight"])) for r in shifts}

        # 1. настройки блоков: shift_code → value
        row = con.execute(text("SELECT value FROM settings WHERE key = 'base_groups'")).first()
        if row and row[0]:
            try:
                groups = json.loads(row[0])
            except json.JSONDecodeError:
                groups = {}
            for gcfg in (groups or {}).values():
                if isinstance(gcfg, dict) and gcfg.get("shift_code"):
                    sh = by_code.get(gcfg.pop("shift_code"))
                    gcfg.pop("invert", None)
                    if sh is not None and not gcfg.get("value"):
                        gcfg["value"] = value_by_code.get(sh["code"], "")
            con.execute(text("UPDATE settings SET value = :v WHERE key = 'base_groups'"),
                        {"v": json.dumps(groups, ensure_ascii=False)})

        # 2. паттерны блоков сотрудников: shift_code → value
        for ba in con.execute(text("SELECT id, pattern_json FROM block_assignments")).mappings().all():
            pat = {}
            try:
                pat = json.loads(ba["pattern_json"] or "")
            except json.JSONDecodeError:
                pat = {}
            if not isinstance(pat, dict) or not pat.get("shift_code"):
                continue
            sh = by_code.get(pat.pop("shift_code"))
            if sh is not None and not pat.get("value"):
                pat["value"] = value_by_code.get(sh["code"], "")
            con.execute(text("UPDATE block_assignments SET pattern_json = :v WHERE id = :id"),
                        {"v": json.dumps(pat, ensure_ascii=False), "id": ba["id"]})

        # 3. системный вид «Отпросился (выходной за часы)» + чистка видов отсутствий
        asked = con.execute(text("SELECT id FROM shift_types WHERE code = 'TIMEOFF_HOURS'")).first()
        if asked is None:
            con.execute(text(
                "INSERT INTO shift_types (code, name, kind, start_time, end_time, overnight,"
                " color, sort_order, is_working, counts_as_worked, is_default_off, doc_type,"
                " punch_in_allowed, punch_out_allowed, active)"
                " VALUES ('TIMEOFF_HOURS', 'Отпросился (выходной за часы)', 'absence', '', '', 0,"
                " '#0e9aa7', 110, 0, 0, 0, '', 1, 1, 1)"))
            asked = con.execute(text("SELECT id FROM shift_types WHERE code = 'TIMEOFF_HOURS'")).first()
        doomed = [r["id"] for r in con.execute(text(
            "SELECT id FROM shift_types WHERE kind = 'absence' AND code <> 'TIMEOFF_HOURS'"))]
        if doomed:
            ids = ", ".join(str(i) for i in doomed)
            con.execute(text(f"UPDATE schedule_absences SET kind_id = {asked[0]} "
                             f"WHERE kind_id IN ({ids})"))
            con.execute(text(f"DELETE FROM shift_revisions WHERE shift_type_id IN ({ids})"))
            con.execute(text(f"DELETE FROM shift_types WHERE id IN ({ids})"))

        # 4._DROP столбцов связки
        for table in ("shift_types", "shift_revisions"):
            tcols = {c["name"] for c in insp.get_columns(table)}
            for colname in ("display_code", "tzh_code", "deduct_from_bank"):
                if colname in tcols:
                    con.execute(text(f"ALTER TABLE {table} DROP COLUMN {colname}"))
