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
            ("deduct_from_bank", "BOOLEAN DEFAULT 0"),
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
            con.execute(text("UPDATE shift_types SET deduct_from_bank=1 "
                             "WHERE code IN ('TIMEOFF_HOURS','AWAY_HOURS') "
                             "AND (deduct_from_bank IS NULL OR deduct_from_bank=0)"))
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

    # старым базам докладываем новые смены словаря из сида
    _migrate_missing_shifts()
    # периоды работы (приём → увольнение → повторный приём)
    _migrate_employment_periods()
    # индивидуальный шаблон пятидневки: берём выходные из общих настроек (как было раньше)
    _migrate_fiveday_patterns()
    # общий шаблон блоков в настройках: переименовываем ключ «Администрация»
    _migrate_base_groups_key()


def _migrate_missing_shifts() -> None:
    """Старым базам докладываем отсутствующие смены из словаря сида. Существующие
    смены НЕ трогаются (их значения правит владелец, история — через ревизии)."""
    from sqlalchemy import inspect, text

    from .seed import SHIFT_EXTRA, SHIFT_TYPES

    insp = inspect(engine)
    if not insp.has_table("shift_types"):
        return
    with engine.begin() as con:
        # свежую базу заполняет сид (seed_if_empty) — не дублируем его здесь
        if insp.has_table("users"):
            users = con.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
            if not users:
                return
        have = {r[0] for r in con.execute(text("SELECT code FROM shift_types"))}
        for (code, name, disp, tzh, kind, start, end, overnight, color, order,
             is_work, counted, default_off) in SHIFT_TYPES:
            if code in have:
                continue
            extra = SHIFT_EXTRA.get(code, {})
            con.execute(text("""
                INSERT INTO shift_types (code, name, display_code, tzh_code, kind, start_time, end_time,
                    overnight, color, sort_order, is_working, counts_as_worked, is_default_off, active,
                    deduct_from_bank, doc_type, archived_at)
                VALUES (:code, :name, :disp, :tzh, :kind, :start, :end, :overnight, :color, :order,
                    :is_work, :counted, :default_off, 1, :deduct, :doc_type, NULL)
            """), {"code": code, "name": name, "disp": disp, "tzh": tzh, "kind": kind,
                   "start": start, "end": end, "overnight": int(bool(overnight)), "color": color,
                   "order": order, "is_work": int(bool(is_work)), "counted": int(bool(counted)),
                   "default_off": int(bool(default_off)),
                   "deduct": int(bool(extra.get("deduct_from_bank", False))),
                   "doc_type": extra.get("doc_type", "")})


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
    from sqlalchemy import text

    con.execute(text("UPDATE shift_types SET tzh_code='Я' "
                     "WHERE code='SUTKI' AND (tzh_code='С' OR tzh_code='' OR tzh_code IS NULL)"))
    con.execute(text("UPDATE shift_types SET tzh_code='' "
                     "WHERE code='TIMEOFF_HOURS' AND tzh_code='НВ'"))


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
    """T1 (норматив 12.10.2026): в поле «код в табеле» — только коды CFG-DAY-CODES.

    Редактор смен писал туда короткое имя смены («08-20»), поэтому health-панель
    выдавала APP-SHIFT-CODE, а ночные и суточные смены не заполняли Табель из циклов.
    Значения, которых нет в словаре кодов действующей версии справочников, очищаются:
    пустое поле — честное состояние («у смены не задан код Табеля»), его видно в
    словаре смен, а владелец ставит нужный код через исправленный редактор (выбор из
    списка). Подпись сетки (`display_code`) и история ревизий не меняются.

    Идемпотентно; если действующей версии справочников нет (свежая база до bootstrap),
    миграция ничего не делает — сравнивать не с чем.
    """
    import json
    import logging

    from sqlalchemy import inspect, text

    from .deps import local_date
    from .engine.adapters.sql_settings import base_version

    insp = inspect(engine)
    if not (insp.has_table("shift_types") and insp.has_table("engine_settings_versions")):
        return
    db = SessionLocal()
    try:
        ver = base_version(db, local_date())
        codes: set[str] = set()
        if ver is not None:
            try:
                codes = set((json.loads(ver.payload_json).get("day_code_policy") or {}).keys())
            except (TypeError, ValueError, AttributeError):
                codes = set()
    finally:
        db.close()
    if not codes:
        return
    with engine.begin() as con:
        rows = con.execute(text(
            "SELECT id, code, tzh_code FROM shift_types "
            "WHERE tzh_code IS NOT NULL AND tzh_code <> ''")).all()
        bad = [(rid, code, (tzh or "").strip()) for rid, code, tzh in rows
               if (tzh or "").strip() not in codes]
        for rid, _code, _tzh in bad:
            con.execute(text("UPDATE shift_types SET tzh_code='' WHERE id=:i"), {"i": rid})
    if bad:
        logging.getLogger("uvicorn.error").info(
            "T1: очищено поле «код в табеле» у смен %s — значения не из словаря "
            "CFG-DAY-CODES (ставьте код через словарь смен)",
            ", ".join(f"{c} («{t}»)" for _rid, c, t in bad))


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
            con.execute(text("UPDATE shift_types SET name=:n, display_code=:d WHERE id=:i"),
                        {"n": TIMEOFF_UNIFIED_NAME, "d": "ОТПР", "i": target[0]})
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


def migrate_engine_v7() -> None:
    """Миграция на движок v7.1 (base 15 «Миграция прототипа» + решение владельца:
    расчётные данные v4 были тестовыми — удаляются).

    * новые таблицы schedule_shifts / schedule_absences создаёт create_all;
    * bank_adjustments.reason_code — маркер OPENING_SEED (v7.1/R37);
    * period_closings.flags_json — снимок флагов при закрытии (7.2);
    * legacy-таблицы timesheet_rows и schedule_entries удаляются вместе со старым движком;
    * расчётные данные (закрытия, переносы, версии справочников, модификаторы, Табель)
      очищаются ОДИН раз (маркер в settings) — демо-база пересоздаётся сидом.
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
        marker = con.execute(text(
            "SELECT value FROM settings WHERE key = 'engine_v7_reset'")).scalar()
        if marker is None and "settings" in existing:
            for table in ("period_closings", "deferred_carry", "engine_settings_versions",
                          "day_modifiers", "tabel_days", "schedule_shifts", "schedule_absences"):
                if table in existing or table in set(insp.get_table_names()):
                    con.execute(text(f"DELETE FROM {table}"))
            con.execute(text(
                "INSERT INTO settings (key, value, description) VALUES "
                "('engine_v7_reset', '1', 'Движок v7.1: расчётные данные v4 были тестовыми — очищены')"))
