"""Заполнение БД демо-данными при первом запуске (идемпотентно).

Демо-поток движка v7.1 (спецификация overtime_spec_v7_1_final.md):
* учёт начинается с ACCOUNTING_START (первый период цепочки); начальный банк задаётся
  посевающей корректировкой OPENING_SEED (v7.1/R37) — только в первом периоде;
* Табель — первичный документ: заполняется из циклов (инструмент владельца),
  планируемые отсутствия (отпуск/больничный/отгул) — коды Табеля;
* График генерируется из Табеля по окнам CFG-WINDOWS (16.3); «отпросился» — запись
  согласованного отсутствия (логический разрез, v7/R17), на часы не влияет;
* периоды закрываются последовательно (RUL-SEQUENTIAL-CLOSING): демо-месяцы до текущего
  остаются открытыми, чтобы показать сценарий закрытия/пересчёта в УТ.
"""
from __future__ import annotations

import datetime as dt
import json
import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .base_schedule import save_base_config
from .deps import local_date, now_local
from .models import (
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_MANAGER,
    ROLE_SUPERVISOR,
    BankAdjustment,
    BlockAssignment,
    Department,
    Employee,
    EmploymentPeriod,
    PositionHistory,
    Punch,
    ScheduleAbsence,
    Setting,
    ShiftType,
    User,
)
from .schedule_helpers import DEFAULT_RULES, RULE_DESCRIPTIONS
from .security import hash_password

DEFAULT_PASSWORD = "demo1234"

# цвета должностей: батлер — серый, старший — оранжевый, менеджеры/документооборот — жёлтый
COLOR_BUTLER = "#8a94a6"
COLOR_SENIOR = "#e8842c"
COLOR_ADMIN = "#d9a514"
COLOR_NIGHT = "#7c8db0"

# код, название, kind, начало, конец, через ночь, цвет, порядок, рабочая, в зачёт,
# «выходной по умолчанию». Словарь с 18.10.2026 — только добавляемые смены Графика
# и системное отсутствие «Отпросился (выходной за часы)»: связка «смена → код
# Табеля» (tzh_code) и подпись сетки (display_code) удалены, виды отсутствий
# (больничный, отпуск…) больше не нужны — отсутствия ставятся кодами Табеля.
SHIFT_TYPES = [
    ("DAY12", "08:00–20:00 (12 ч, график 2/2 или 3/3)", "work", "08:00", "20:00", False, "#34a862", 10, True, True, False),
    ("NIGHT12", "20:00–08:00 (ночная, ручная смена Графика)", "work", "20:00", "08:00", True, "#5b6bd6", 20, True, True, False),
    ("DAY9", "09:00–18:00 (9 ч, график 5/2)", "work", "09:00", "18:00", False, "#2bb673", 30, True, True, False),
    ("DAY8_17", "08:00–17:00 (8 ч, график 5/2)", "work", "08:00", "17:00", False, "#4cae52", 40, True, True, False),
    ("DAY10_22", "10:00–22:00 (12 ч)", "work", "10:00", "22:00", False, "#7ac943", 50, True, True, False),
    # суточная смена — графиковая: в Табеле обычная явка «Я 12» (окно 08:00–20:00),
    # присутствие через полночь относится к карточке следующего дня (норматив 12.10.2026)
    ("SUTKI", "08:00–08:00 (сутки, 1/3)", "work", "08:00", "08:00", True, "#b44fd6", 60, True, True, False),
    # «Отпросился (выходной за часы)» — ОДНА сущность с двумя точками ввода (Q3,
    # 12.10.2026): интервал части смены либо вся смена («выходной за часы»). Это
    # данные Графика, а не код первичного документа: в Табеле остаётся явка,
    # недостачу гасит банк (EX-29).
    ("TIMEOFF_HOURS", "Отпросился (выходной за часы)", "absence", "", "", False, "#0e9aa7", 110, False, False, False),
]

SHIFT_EXTRA = {
    "VACATION": {"doc_type": "vacation_paid", "punch_in_allowed": False, "punch_out_allowed": False},
    "VACATION_UNPAID": {"doc_type": "vacation_unpaid", "punch_in_allowed": False,
                        "punch_out_allowed": False},
    "TIMEOFF_HOURS": {"doc_type": "day_off_hours"},
}

# ФИО, должность, таб.№, приём, группа, цвет, график, сдвиг, банк, роль, логин, экстренный контакт
EMPLOYEES = [
    ("Смирнов Алексей Владимирович", "Менеджер объекта", "001", "2021-03-15", "Пятидневка", COLOR_ADMIN, "5/2", 0, 0.0, ROLE_MANAGER, "smirnov", "Смирнова Е. П., +7 916 100-20-30"),
    ("Соколова Елена Викторовна", "Документооборот", "002", "2022-06-01", "Пятидневка", COLOR_ADMIN, "5/2", 0, 0.0, ROLE_EMPLOYEE, "sokolova", "Соколов И. В., +7 916 100-20-31"),
    ("Громова Ольга Петровна", "Старший батлер", "003", "2020-02-10", "Смена 1", COLOR_SENIOR, "2/2", 0, 4.0, ROLE_SUPERVISOR, "gromova", "Громов П. С., +7 916 100-20-32"),
    ("Иванов Иван Иванович", "Батлер", "004", "2023-09-01", "Смена 1", COLOR_BUTLER, "2/2", 0, 2.0, ROLE_EMPLOYEE, "ivanov", "Иванова М. И., +7 916 100-20-33"),
    ("Кузнецова Мария Сергеевна", "Батлер", "005", "2024-04-15", "Смена 1", COLOR_BUTLER, "2/2", 2, 0.0, ROLE_EMPLOYEE, "kuznetsova", "Кузнецов С. С., +7 916 100-20-34"),
    ("Морозова Анна Игоревна", "Батлер", "006", "2023-01-09", "Смена 1", COLOR_BUTLER, "2/2", 3, 0.0, ROLE_EMPLOYEE, "morozova", "Морозов И. И., +7 916 100-20-35"),
    ("Сидоров Сидор Сидорович", "Батлер", "007", "2022-11-21", "Смена 1", COLOR_BUTLER, "3/3", 0, 6.0, ROLE_EMPLOYEE, "sidorov", "Сидорова Т. С., +7 916 100-20-36"),
    ("Петров Пётр Петрович", "Батлер (суточные смены)", "008", "2021-08-02", "Смена 2", COLOR_NIGHT, "1/3", 1, -1.0, ROLE_EMPLOYEE, "petrov", "Петрова Л. П., +7 916 100-20-37"),
    ("Орлов Никита Павлович", "Батлер (суточные смены)", "009", "2024-02-12", "Смена 2", COLOR_NIGHT, "1/3", 2, 0.0, ROLE_EMPLOYEE, "orlov", "Орлова В. Н., +7 916 100-20-38"),
    ("Фёдоров Дмитрий Андреевич", "Батлер (суточные смены)", "010", "2023-05-30", "Смена 2", COLOR_NIGHT, "1/3", 0, 3.0, ROLE_EMPLOYEE, "fedorov", "Фёдорова А. Д., +7 916 100-20-39"),
    ("Волков Артём Дмитриевич", "Батлер (гибкий график)", "011", "2025-02-03", "Другие смены", "#4c9a6a", "3/3", 0, 0.0, ROLE_EMPLOYEE, "volkov", "Волкова Д. А., +7 916 100-20-41"),
]


def _short_name(full_name: str) -> str:
    parts = full_name.split()
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."
    return full_name


def accounting_start(today: dt.date) -> dt.date:
    """Первый период цепочки учёта v7.1: 1-е число месяца «два месяца назад» —
    демо показывает последовательное закрытие периодов (RUL-SEQUENTIAL-CLOSING)."""
    prev = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    return (prev - dt.timedelta(days=1)).replace(day=1)


def seed_if_empty(db: Session) -> bool:
    if db.scalar(select(func.count(User.id))):
        for key, value in DEFAULT_RULES.items():
            if not db.get(Setting, key):
                db.add(Setting(key=key, value=value, description=RULE_DESCRIPTIONS.get(key, "")))
        db.commit()
        return False

    rnd = random.Random(20260922)
    today = local_date()
    acc_start = accounting_start(today)

    for key, value in DEFAULT_RULES.items():
        db.add(Setting(key=key, value=value, description=RULE_DESCRIPTIONS.get(key, "")))

    dep_butlers = Department(name="Служба батлеров")
    dep_mgmt = Department(name="Управление")
    db.add_all([dep_butlers, dep_mgmt])
    db.flush()
    deps = {"Служба батлеров": dep_butlers.id, "Управление": dep_mgmt.id}

    shifts = {}
    for (code, name, kind, start, end, overnight, color, order, is_work, counted,
         default_off) in SHIFT_TYPES:
        st = ShiftType(code=code, name=name, kind=kind,
                       start_time=start, end_time=end, overnight=overnight,
                       color=color, sort_order=order, is_working=is_work,
                       counts_as_worked=counted, is_default_off=default_off,
                       **SHIFT_EXTRA.get(code, {}))
        db.add(st)
        shifts[code] = st
    db.flush()

    # администратор: полный доступ, сам в график не встаёт
    db.add(User(username="admin", password_hash=hash_password(DEFAULT_PASSWORD), role=ROLE_ADMIN))

    employees = []
    for (full_name, position, tab, hired, group, color, pattern, offset, balance, role, login,
         emergency) in EMPLOYEES:
        name, phone = [x.strip() for x in emergency.split(",", 1)]
        hired_d = dt.date.fromisoformat(hired)
        emp = Employee(full_name=full_name, short_name=_short_name(full_name), position=position,
                       phone=f"+7 9{rnd.randint(10, 99)} {rnd.randint(100, 999)}-"
                             f"{rnd.randint(10, 99)}-{rnd.randint(10, 99)}",
                       tab_number=tab, hired_at=hired_d, emergency_name=name, emergency_phone=phone,
                       department_id=deps["Управление"] if group == "Пятидневка" else deps["Служба батлеров"],
                       schedule_group=group, group_color=color,
                       schedule_pattern=pattern, schedule_anchor=acc_start,
                       balance_hours=balance)
        db.add(emp)
        db.flush()
        emp.telegram = {"ivanov": "@ivanov_butler", "gromova": "@gromova_senior",
                        "smirnov": "@smirnov_mgr"}.get(login, "")
        emp.email = f"{login}@butler.service"
        db.add(User(username=login, password_hash=hash_password(DEFAULT_PASSWORD),
                    role=role, employee_id=emp.id))
        # история должностей: принят на позицию ниже текущей, затем повышение/перевод
        if position == "Старший батлер":
            db.add(PositionHistory(employee_id=emp.id, position="Батлер",
                                   start_date=hired_d, end_date=hired_d.replace(year=hired_d.year + 1)))
            db.add(PositionHistory(employee_id=emp.id, position=position,
                                   start_date=hired_d.replace(year=hired_d.year + 1), end_date=None))
        elif position == "Батлер":
            db.add(PositionHistory(employee_id=emp.id, position="Батлер (стажёр)",
                                   start_date=hired_d, end_date=hired_d + dt.timedelta(days=90)))
            db.add(PositionHistory(employee_id=emp.id, position=position,
                                   start_date=hired_d + dt.timedelta(days=90), end_date=None))
        else:
            db.add(PositionHistory(employee_id=emp.id, position=position, start_date=hired_d, end_date=None))
        pattern_json = ""
        if group == "Пятидневка":
            pattern_json = json.dumps({"kind": "week5", "off_weekdays": [5, 6],
                                       "value": "Я 9",
                                       "label": "5/2, выходные сб и вс"}, ensure_ascii=False)
        elif group == "Смена 2":
            pattern_json = json.dumps({"kind": "cycle", "cycle": pattern or "1/3",
                                       "value": "Я 12", "anchor": acc_start.isoformat(),
                                       "label": f"{pattern or '1/3'} сутки"}, ensure_ascii=False)
        elif group == "Другие смены":
            pattern_json = json.dumps({"kind": "cycle", "cycle": pattern or "3/3",
                                       "value": "Я 12", "anchor": acc_start.isoformat(),
                                       "label": f"{pattern or '3/3'} сутки"}, ensure_ascii=False)
        db.add(BlockAssignment(employee_id=emp.id, group=group, start_date=acc_start,
                               end_date=None, pattern_json=pattern_json))
        # период работы: учёт v7.1 начинается с acc_start — первый период цепочки (R35/R37)
        db.add(EmploymentPeriod(employee_id=emp.id, start_date=acc_start, end_date=None,
                                note="учёт переработок v7.1"))
        employees.append((emp, pattern, offset))
    db.flush()

    from .models import EmergencyContact
    demo_contacts = {
        "Иванов": [("Иванова Мария Ивановна", "+7 916 100-20-33", "мать"),
                   ("Иванов Сергей Иванович", "+7 916 100-20-40", "брат")],
        "Громова": [("Громов Павел С.", "+7 916 100-20-32", "муж")],
    }
    for emp, _, _ in employees:
        for prefix, rows in demo_contacts.items():
            if emp.full_name.startswith(prefix):
                for name, phone, rel in rows:
                    db.add(EmergencyContact(employee_id=emp.id, name=name, phone=phone, relation=rel))
    db.flush()

    # демо-переход между группами: Морозова была в Смене 1, с 16-го числа — в Смене 2
    morozova = next(e for e, _, _ in employees if e.full_name.startswith("Морозова"))
    transfer = today.replace(day=16) if today.day >= 16 else today.replace(day=1) + dt.timedelta(days=15)
    for ba in db.scalars(select(BlockAssignment).where(BlockAssignment.employee_id == morozova.id)):
        ba.end_date = transfer - dt.timedelta(days=1)
    db.add(BlockAssignment(employee_id=morozova.id, group="Смена 2", start_date=transfer,
                           end_date=None,
                           pattern_json=json.dumps({"kind": "cycle", "cycle": "1/3",
                                                      "value": "Я 12",
                                                    "shift_code": "SUTKI",
                                                    "anchor": transfer.isoformat(),
                                                    "label": "1/3 сутки"}, ensure_ascii=False)))
    morozova.schedule_group = "Смена 2"
    db.flush()

    # ───────────────────── базовый цикл объекта: 2/2 дневные ─────────────────────
    save_base_config(db, {
        "cycle": "2/2",
        "anchor": acc_start.isoformat(),
        "groups": {
            # значение рабочего дня по умолчанию для блока: сотрудник без своего
            # значения берёт его отсюда; личные значения живут в карточке (18.10.2026)
            "Смена 1": {"value": "Я 12"},
            "Смена 2": {"value": "Я 12"},
            "Пятидневка": {"value": "Я 9", "off_weekdays": [5, 6]},
        },
    })
    db.flush()

    # ───────────────────── начальный банк: посев OPENING_SEED (v7.1/R37) ─────────────────────
    for (full_name, _pos, _tab, _hired, _grp, _color, _pat, _off, balance, _role, _login,
         _em) in EMPLOYEES:
        emp = next(e for e, _, _ in employees if e.full_name == full_name)
        db.add(BankAdjustment(employee_id=emp.id, hours=balance, effective_date=acc_start,
                              note="Начальный банк на старте учёта v7.1",
                              reason_code="OPENING_SEED", author_name="system"))
    db.flush()

    # ───────────────────── планируемые отсутствия текущего месяца — коды Табеля ─────────────────────
    from .engine.domain.settings.defaults import default_settings
    from .models import TabelDay
    defaults = default_settings()

    def set_absence_code(emp: Employee, d1: int, d2: int, code: str, note: str = "") -> None:
        policy = defaults.day_code_policy.get(code)
        if policy is None or policy.carries_hours:
            return
        for day_n in range(d1, d2 + 1):
            try:
                date = dt.date(today.year, today.month, day_n)
            except ValueError:
                continue
            db.add(TabelDay(employee_id=emp.id, date=date, code=code, plan_minutes=0,
                            note=note, source="manual"))

    by_name = {e.full_name.split()[0]: e for e, _, _ in employees}
    set_absence_code(by_name["Кузнецова"], 7, 20, "ОТ",
                     "Ежегодный оплачиваемый отпуск, приказ №47")
    set_absence_code(by_name["Фёдоров"], 3, 8, "Б", "Листок нетрудоспособности №1234")
    set_absence_code(by_name["Орлов"], 14, 15, "ДО",
                     "Заявление: отпуск без сохранения з/п")
    set_absence_code(by_name["Морозова"], 25, 25, "ОВ", "Донорский день, справка №88")
    db.flush()

    # ───────────────────── Табель из циклов + График из Табеля (движок v7.1) ─────────────────────
    from .engine.adapters.factory import build_ports
    from .engine.application.schedule_view import rebuild_generated_schedule
    from .engine.domain.types.entities import Period
    from .engine_bootstrap import bootstrap_engine
    from .tabel_fill import fill_timesheet_from_cycles
    bootstrap_engine(db)                                  # версия справочников v7.1
    fill_result = fill_timesheet_from_cycles(
        db, [e for e, _, _ in employees], acc_start, today + dt.timedelta(days=40))
    assert not fill_result["warnings"], fill_result["warnings"][:3]

    # «отпросился» — согласованное отсутствие (логический разрез Графика, v7/R17):
    # часы не списывает, влияет только на флаги и доску
    ivanov = by_name["Иванов"]
    # «Отпросился» осмысленно только в день со сменой и часами: демо-день — ближайший
    # рабочий день по Табелю назад от today−3. Фиксированный сдвиг раз в 4 дня попадает
    # на «В» цикла 2/2 — а в дне без смены блок отсутствия в ячейке не показывается
    # (правило 16.10.2026), демо-сценарий интервала на смене становился невидим.
    away_day = today - dt.timedelta(days=3)
    for _ in range(8):
        row = db.scalar(select(TabelDay).where(TabelDay.employee_id == ivanov.id,
                                               TabelDay.date == away_day))
        if row is not None and row.plan_minutes > 0:
            break
        away_day -= dt.timedelta(days=1)

    def _utc_naive(local: dt.datetime) -> dt.datetime:
        from .deps import TZ
        return local.replace(tzinfo=TZ).astimezone(dt.timezone.utc).replace(tzinfo=None)

    db.add(ScheduleAbsence(employee_id=ivanov.id,
                           start_utc=_utc_naive(dt.datetime.combine(away_day, dt.time(14, 0))),
                           end_utc=_utc_naive(dt.datetime.combine(away_day, dt.time(16, 0))),
                           kind_id=shifts["TIMEOFF_HOURS"].id,
                           note="Отпросился с 14:00 до 16:00 (заявление)"))
    db.flush()

    ports = build_ports(db, dt.datetime.now(dt.timezone.utc), "system")
    for emp, _, _ in employees:
        rebuild_generated_schedule(str(emp.id), Period(acc_start, today + dt.timedelta(days=40)),
                                   ports)
    db.flush()

    # ───────────────────── отметки прихода/ухода (от acc_start до сегодня) ─────────────────────
    from .base_schedule import BlockIndex, load_base_config, pattern_for_date, working_flag
    base_cfg = load_base_config(db)
    block_index = BlockIndex.load(db, [e.id for e, _, _ in employees])
    now = now_local()
    absence_rows = {(r.employee_id, r.date): r for r in db.scalars(select(TabelDay).where(
        TabelDay.source == "manual"))}

    ot_descriptions = [
        "Догонял подготовку зала к банкету, работал с Ивановым",
        "Закрывал инвентаризацию белья вместе со старшим батлером",
        "Помогал службе кейтеринга: сервировка, вынос блюд",
        "Принимал доставку оборудования, раскладка по кладовым",
    ]

    def add_punch(emp_id: int, ts: dt.datetime, kind: str, note: str = "") -> None:
        if ts > now:
            return
        db.add(Punch(employee_id=emp_id, ts=ts.replace(second=rnd.randint(0, 59), microsecond=0),
                     kind=kind, source="web", note=note))

    for emp, _, _ in employees:
        d = acc_start
        while d <= today:
            row = absence_rows.get((emp.id, d))
            pat = pattern_for_date(db, emp, d, base_cfg, index=block_index)
            works = pat.get("kind") != "manual"
            window = defaults.windows.get((pat.get("value") or "").strip()) if works else None
            if works:
                try:
                    works = working_flag(base_cfg, pat, d)
                except ValueError:
                    works = False
            works = works and window is not None
            if row is not None:                    # ручная строка Табеля (отсутствие/код)
                policy = defaults.day_code_policy.get(row.code)
                works = works and policy is not None and policy.carries_hours
            if works:
                midnight = dt.datetime(d.year, d.month, d.day)
                start = midnight + dt.timedelta(minutes=window.start_minute)
                end = midnight + dt.timedelta(minutes=window.end_minute)
                if start <= now < end:                      # смена идёт прямо сейчас
                    add_punch(emp.id, start + dt.timedelta(minutes=rnd.randint(-8, 12)), "IN")
                elif end <= now:
                    dice = rnd.random()
                    late_in = rnd.randint(3, 27) if dice < 0.3 else rnd.randint(-10, 2)
                    out_shift = rnd.choice([-95, -70, -40, -15, 0, 10, 25, 45, 80, 130])
                    add_punch(emp.id, start + dt.timedelta(minutes=late_in), "IN")
                    note = rnd.choice(ot_descriptions) if out_shift >= 45 else ""
                    add_punch(emp.id, end + dt.timedelta(minutes=out_shift), "OUT", note)
                    # аномалии для демонстрации: забытый уход и «не пришёл»
                    if emp.full_name.startswith("Фёдоров") and d == today - dt.timedelta(days=4):
                        db.query(Punch).filter(
                            Punch.employee_id == emp.id, Punch.ts >= end,
                            Punch.ts <= end + dt.timedelta(hours=6),
                            Punch.kind == "OUT").delete()
                    if emp.full_name.startswith("Смирнов") and d == today - dt.timedelta(days=2):
                        db.query(Punch).filter(
                            Punch.employee_id == emp.id,
                            Punch.ts >= start - dt.timedelta(hours=2),
                            Punch.ts <= end + dt.timedelta(hours=6)).delete()
            d += dt.timedelta(days=1)
    db.flush()

    # ───────────────────── ночной отчёт и электрокары (вне движка) ─────────────────────
    _seed_night_dirs(db)
    _seed_cars(db, {e.full_name.split()[0]: e for e, _, _ in employees})

    db.commit()
    return True


# Зоны обхода ночного отчёта (v2, 19.10.2026): зона → объекты → чек-лист.
# Чек-лист задаётся НА ЗОНУ, поэтому у десятков однотипных объектов он одинаковый;
# индивидуальные особенности отдельных объектов — ниже, в _seed_night_dirs().
# Формат: (зона, порядок, шаблон чек-листа зоны, объекты зоны)
NIGHT_ZONES_DEMO = [
    ("Семейные виллы", 10,
     ["Витражи закрыты", "Свет выключен", "Вилла убрана", "Вилла укомплектована"],
     [f"Вилла {n}" for n in range(4001, 4013)]),
    ("Президентские виллы", 20,
     ["Витражи закрыты", "Свет выключен", "Вилла убрана", "Вилла укомплектована", "Бассейн накрыт"],
     [f"Вилла {n}" for n in range(5001, 5005)]),
    ("Офисы и служебные", 30,
     ["Оборудование выключено", "Продукты подписаны и убраны", "Вытяжка проверена",
      "Уборка завершена", "Двери и сейфы закрыты"],
     ["Кухня", "Кладовая белья", "Офис батлер-сервиса"]),
    ("Общие зоны", 40,
     ["Чистота пола и стоек ресепшн", "Освещение: все лампы горят",
      "Мебель расставлена по схеме", "Нет посторонних запахов"],
     ["Лобби", "Ресторан", "Зона SPA"]),
]


# Ответственные службы (этап 3): (название, порядок, чат, письмо, ящик, копия, примечание).
# Чаты закрепляются позже — из общего каталога Telegram («Настройки → Чаты и Почта»).
NIGHT_SERVICES_DEMO = [
    ("Батлер-сервис", 10, True, True, "butler@resort.example", "", "круглосуточный пост"),
    ("Хозяйственная служба", 20, True, False, "", "", ""),
    ("Техническая служба", 30, True, True, "tech@resort.example", "butler@resort.example",
     "дежурный инженер"),
    ("Служба безопасности", 40, True, False, "", "", "пост №1"),
    ("СПА и бассейны", 50, False, True, "spa@resort.example", "", ""),
]

# Служба по умолчанию у пункта шаблона зоны (демо: видно, как недостаток уходит получателю)
NIGHT_ITEM_SERVICE = {
    "Витражи закрыты": "Батлер-сервис",
    "Свет выключен": "Техническая служба",
    "Вилла убрана": "Хозяйственная служба",
    "Вилла укомплектована": "Батлер-сервис",
    "Бассейн накрыт": "СПА и бассейны",
    "Оборудование выключено": "Техническая служба",
    "Продукты подписаны и убраны": "Хозяйственная служба",
    "Вытяжка проверена": "Техническая служба",
    "Уборка завершена": "Хозяйственная служба",
    "Двери и сейфы закрыты": "Служба безопасности",
    "Чистота пола и стоек ресепшн": "Хозяйственная служба",
    "Освещение: все лампы горят": "Техническая служба",
    "Мебель расставлена по схеме": "Хозяйственная служба",
    "Нет посторонних запахов": "Хозяйственная служба",
}

CAR_LOCATIONS = ["Парковка у главного входа", "Навес у служебного входа",
                 "Место с зарядкой у корпуса B"]
CARS_DEMO = [("1", "free", "Парковка у главного входа", ""), ("2", "busy", "Навес у служебного входа", "Иванов"),
             ("3", "charging", "Место с зарядкой у корпуса B", ""), ("4", "free", "Навес у служебного входа", ""),
             ("5", "maintenance", "Гараж", "")]


def _seed_night_dirs(db: Session) -> None:
    """Зоны, объекты и чек-листы ночного обхода (демо-данные).

    Показывает обе возможности v2: общий шаблон зоны на все её объекты и
    индивидуальные особенности конкретного объекта — своя формулировка, свой пункт,
    отключённый пункт и своя служба («Вилла 4001» / «Вилла 4002»). У пунктов шаблона
    зоны заданы ответственные службы — по ним этап 5 собирает недостатки к отправке.
    """
    import json

    from sqlalchemy import select

    from .models import (
        ChecklistItem,
        ChecklistOverride,
        NightArea,
        NightZone,
        ResponsibilityService,
        ZoneChecklistItem,
    )

    services: dict[str, int] = {}
    for name, order, tg, mail, email_to, email_copy, note in NIGHT_SERVICES_DEMO:
        svc = ResponsibilityService(name=name, sort_order=order, use_telegram=tg,
                                    use_email=mail, email_to=email_to,
                                    email_copy=email_copy, chat_ids=json.dumps([]), note=note)
        db.add(svc)
        db.flush()
        services[name] = svc.id

    for zone_name, order, tpl, objects in NIGHT_ZONES_DEMO:
        zone = NightZone(name=zone_name, sort_order=order)
        db.add(zone)
        db.flush()
        for i, text in enumerate(tpl, start=10):
            db.add(ZoneChecklistItem(zone_id=zone.id, text=text, sort_order=i,
                                     service_id=services.get(NIGHT_ITEM_SERVICE.get(text, ""))))
        for j, obj_name in enumerate(objects):
            db.add(NightArea(name=obj_name, category=zone_name, zone_id=zone.id,
                             sort_order=(j + 1) * 10))
        db.flush()

    # индивидуальные особенности объекта (демо для экрана настроек)
    def _zone_item(zone_name: str, text: str):
        return db.scalar(select(ZoneChecklistItem).join(NightZone, NightZone.id == ZoneChecklistItem.zone_id)
                         .where(NightZone.name == zone_name, ZoneChecklistItem.text == text))

    villa_4001 = db.scalar(select(NightArea).where(NightArea.name == "Вилла 4001"))
    villa_4002 = db.scalar(select(NightArea).where(NightArea.name == "Вилла 4002"))
    clean_item = _zone_item("Семейные виллы", "Вилла убрана")
    kit_item = _zone_item("Семейные виллы", "Вилла укомплектована")
    if villa_4001 is not None and clean_item is not None:
        # своя формулировка И своя служба: детскую комнату проверяет батлер-сервис
        db.add(ChecklistOverride(area_id=villa_4001.id, zone_item_id=clean_item.id,
                                 text="Вилла убрана (включая детскую комнату)",
                                 service_id=services.get("Батлер-сервис")))
        db.add(ChecklistItem(area_id=villa_4001.id, sort_order=90,
                             text="Детская кроватка установлена и исправна",
                             service_id=services.get("Батлер-сервис")))
    if villa_4002 is not None and kit_item is not None:
        db.add(ChecklistOverride(area_id=villa_4002.id, zone_item_id=kit_item.id, disabled=True))
    db.flush()


def _seed_cars(db: Session, by_name: dict) -> None:
    from .cars import create_car
    from .models import CarLocation, User

    admin = db.scalar(select(User).where(User.username == "admin"))
    principal = None
    if admin is not None:
        from .auth import Principal
        principal = Principal(user=admin, employee=None)
    for i, loc_name in enumerate(CAR_LOCATIONS, start=10):
        db.add(CarLocation(name=loc_name, sort_order=i, builtin=True))
    db.flush()
    for number, status, location, holder_key in CARS_DEMO:
        car = create_car(db, principal, number, location)
        car.status = status
        if status == "charging":
            car.on_charge, car.charge = True, "empty"
        if holder_key:
            emp = by_name.get(holder_key)
            if emp is not None and emp.user is not None:
                car.holder_user_id = emp.user.id
                car.holder_name = emp.display_name
                if number == "1":
                    car.assigned_to = emp.id
    db.flush()
