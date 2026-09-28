"""Заполнение БД демо-данными при первом запуске (идемпотентно)."""
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
    BlockAssignment,
    Department,
    Employee,
    EmploymentPeriod,
    PositionHistory,
    Punch,
    ScheduleEntry,
    Setting,
    ShiftType,
    User,
)
from .security import hash_password
from .timesheet import DEFAULT_RULES, RULE_DESCRIPTIONS, recalc_range

DEFAULT_PASSWORD = "demo1234"

# цвета должностей: батлер — серый, старший — оранжевый, менеджеры/документооборот — жёлтый
COLOR_BUTLER = "#8a94a6"
COLOR_SENIOR = "#e8842c"
COLOR_ADMIN = "#d9a514"
COLOR_NIGHT = "#7c8db0"

# код, название, код в сетке, код Т-13, kind, начало, конец, через ночь, цвет, порядок, рабочая, в зачёт, «выходной по умолчанию»
SHIFT_TYPES = [
    ("DAY12", "08:00–20:00 (12 ч, график 2/2 или 3/3)", "08–20", "Я", "work", "08:00", "20:00", False, "#34a862", 10, True, True, False),
    ("NIGHT12", "20:00–08:00 (ночная, внутренний учёт)", "20–08", "Н", "work", "20:00", "08:00", True, "#5b6bd6", 20, True, True, False),
    ("DAY9", "09:00–18:00 (9 ч, график 5/2)", "09–18", "Я", "work", "09:00", "18:00", False, "#2bb673", 30, True, True, False),
    ("DAY8_17", "08:00–17:00 (9 ч, график 5/2)", "08–17", "Я", "work", "08:00", "17:00", False, "#4cae52", 40, True, True, False),
    ("DAY10_22", "10:00–22:00 (12 ч)", "10–22", "Я", "work", "10:00", "22:00", False, "#7ac943", 50, True, True, False),
    ("SUTKI", "08:00–08:00 (сутки, 1/3)", "СУТ", "С", "work", "08:00", "08:00", True, "#b44fd6", 60, True, True, False),
    ("OFF", "Выходной по графику", "ВЫХ", "В", "absence", "", "", False, "#c3cdd9", 70, False, False, True),
    ("SICK", "Больничный", "БОЛ", "Б", "absence", "", "", False, "#e05d4b", 80, False, False, False),
    ("VACATION", "Отпуск (за счёт предприятия)", "ОТП", "ОТ", "absence", "", "", False, "#f0a500", 90, False, False, False),
    ("VACATION_UNPAID", "Отпуск за свой счёт", "ОСЧ", "ДО", "absence", "", "", False, "#d9822b", 100, False, False, False),
    ("TIMEOFF_HOURS", "Выходной за часы", "ВЧ", "НВ", "absence", "", "", False, "#17a2b8", 110, False, False, False),
    ("PAID_OFF", "Выходной оплачиваемый (донорские и т.п.)", "ВОП", "ОВ", "absence", "", "", False, "#9b59b6", 120, False, True, False),
    ("ABSENT_UNKNOWN", "Неявка по невыясненной причине", "НН", "НН", "absence", "", "", False, "#b03a48", 130, False, False, False),
    ("AWAY_HOURS", "Отпросился: отсутствовал часть смены", "ОТПР", "Я", "absence", "", "", False, "#0e9aa7", 140, False, False, False),
]

# дополнительные свойства словаря смен: какой документ печатаем и списывать ли часы с банка
SHIFT_EXTRA = {
    "VACATION": {"doc_type": "vacation_paid"},
    "VACATION_UNPAID": {"doc_type": "vacation_unpaid"},
    "TIMEOFF_HOURS": {"doc_type": "day_off_hours", "deduct_from_bank": True},
    "AWAY_HOURS": {"doc_type": "time_off_request", "deduct_from_bank": True},
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
    ("Петров Пётр Петрович", "Батлер (ночные смены)", "008", "2021-08-02", "Смена 2", COLOR_NIGHT, "2/2", 1, -1.0, ROLE_EMPLOYEE, "petrov", "Петрова Л. П., +7 916 100-20-37"),
    ("Орлов Никита Павлович", "Батлер (ночные смены)", "009", "2024-02-12", "Смена 2", COLOR_NIGHT, "2/2", 1, 0.0, ROLE_EMPLOYEE, "orlov", "Орлова В. Н., +7 916 100-20-38"),
    ("Фёдоров Дмитрий Андреевич", "Батлер (ночные смены)", "010", "2023-05-30", "Смена 2", COLOR_NIGHT, "3/3", 1, 3.0, ROLE_EMPLOYEE, "fedorov", "Фёдорова А. Д., +7 916 100-20-39"),
    ("Волков Артём Дмитриевич", "Батлер (гибкий график)", "011", "2025-02-03", "Другие смены", "#4c9a6a", "3/3", 0, 0.0, ROLE_EMPLOYEE, "volkov", "Волкова Д. А., +7 916 100-20-41"),
]


def _short_name(full_name: str) -> str:
    parts = full_name.split()
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."
    return full_name


def seed_if_empty(db: Session) -> bool:
    if db.scalar(select(func.count(User.id))):
        for key, value in DEFAULT_RULES.items():
            if not db.get(Setting, key):
                db.add(Setting(key=key, value=value, description=RULE_DESCRIPTIONS.get(key, "")))
        db.commit()
        return False

    rnd = random.Random(20260922)
    today = local_date()

    for key, value in DEFAULT_RULES.items():
        db.add(Setting(key=key, value=value, description=RULE_DESCRIPTIONS.get(key, "")))

    dep_butlers = Department(name="Служба батлеров")
    dep_mgmt = Department(name="Управление")
    db.add_all([dep_butlers, dep_mgmt])
    db.flush()
    deps = {"Служба батлеров": dep_butlers.id, "Управление": dep_mgmt.id}

    shifts = {}
    for (code, name, disp, tzh, kind, start, end, overnight, color, order, is_work, counted, default_off) in SHIFT_TYPES:
        st = ShiftType(code=code, name=name, display_code=disp, tzh_code=tzh, kind=kind,
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
    for (full_name, position, tab, hired, group, color, pattern, offset, balance, role, login, emergency) in EMPLOYEES:
        name, phone = [x.strip() for x in emergency.split(",", 1)]
        hired_d = dt.date.fromisoformat(hired)
        emp = Employee(full_name=full_name, short_name=_short_name(full_name), position=position,
                       phone=f"+7 9{rnd.randint(10, 99)} {rnd.randint(100, 999)}-"
                             f"{rnd.randint(10, 99)}-{rnd.randint(10, 99)}",
                       tab_number=tab, hired_at=hired_d, emergency_name=name, emergency_phone=phone,
                       department_id=deps["Управление"] if group == "Пятидневка" else deps["Служба батлеров"],
                       schedule_group=group, group_color=color,
                       schedule_pattern=pattern, schedule_anchor=today.replace(day=1),
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
                                       "shift_code": "DAY9",
                                       "label": "5/2, выходные сб и вс"}, ensure_ascii=False)
        elif group == "Другие смены":
            pattern_json = json.dumps({"kind": "cycle", "cycle": pattern or "3/3",
                                       "shift_code": "NIGHT12", "anchor": hired_d.isoformat(),
                                       "label": f"{pattern or '3/3'} ночные"}, ensure_ascii=False)
        db.add(BlockAssignment(employee_id=emp.id, group=group, start_date=hired_d,
                               end_date=None, pattern_json=pattern_json))
        db.add(EmploymentPeriod(employee_id=emp.id, start_date=hired_d, end_date=None,
                                note="приём на работу"))
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

    # демо-переход между сменами: Морозова была в Смене 1, с 16-го числа — в Смене 2
    morozova = next(e for e, _, _ in employees if e.full_name.startswith("Морозова"))
    transfer = today.replace(day=16) if today.day >= 16 else today.replace(day=1) + dt.timedelta(days=15)
    for ba in db.scalars(select(BlockAssignment).where(BlockAssignment.employee_id == morozova.id)):
        ba.end_date = transfer - dt.timedelta(days=1)
    db.add(BlockAssignment(employee_id=morozova.id, group="Смена 2", start_date=transfer, end_date=None))
    morozova.schedule_group = "Смена 2"
    db.flush()

    # ───────────────────── график: прошлый, текущий и следующий месяцы ─────────────────────
    prev_month = (today.replace(day=1) - dt.timedelta(days=1))
    nxt = today.replace(day=1)
    nxt = dt.date(nxt.year + (nxt.month == 12), nxt.month % 12 + 1, 1)

    # ───────────────────── базовый цикл объекта: на все месяцы вперёд и назад ─────────────────────
    anchor = prev_month.replace(day=1)
    save_base_config(db, {
        "cycle": "2/2",
        "anchor": anchor.isoformat(),
        "groups": {
            "Смена 1": {"shift_code": "DAY12", "invert": False},
            "Смена 2": {"shift_code": "NIGHT12", "invert": True},
            # у пятидневки выходные теперь задаются у каждого сотрудника (карточка → «Перевод в блок»)
            "Пятидневка": {"shift_code": "DAY9", "off_weekdays": [5, 6]},
        },
    })
    db.flush()

    # ───────────────────── исключения: планируемые отсутствия в текущем месяце ─────────────────────
    schedule_map: dict[tuple[int, dt.date], ShiftType] = {}
    y, m = today.year, today.month
    by_name = {e.full_name.split()[0]: e for e, _, _ in employees}
    notes: dict[tuple[int, dt.date], str] = {}

    def set_absence(emp: Employee, d1: int, d2: int, shift: ShiftType, note: str = "") -> None:
        for day in range(d1, d2 + 1):
            try:
                date = dt.date(y, m, day)
            except ValueError:
                continue
            schedule_map[(emp.id, date)] = shift
            if note:
                notes[(emp.id, date)] = note

    set_absence(by_name["Кузнецова"], 7, 20, shifts["VACATION"], "Ежегодный оплачиваемый отпуск, приказ №47")
    set_absence(by_name["Фёдоров"], 3, 8, shifts["SICK"], "Листок нетрудоспособности №1234")
    set_absence(by_name["Орлов"], 14, 15, shifts["VACATION_UNPAID"], "Заявление: отпуск без сохранения з/п")
    set_absence(by_name["Морозова"], 25, 25, shifts["PAID_OFF"], "Донорский день, справка №88")
    for day in (11, 25):
        try:
            date = dt.date(y, m, day)
        except ValueError:
            continue
        if schedule_map.get((by_name["Сидоров"].id, date), shifts["OFF"]).code == "DAY12":
            schedule_map[(by_name["Сидоров"].id, date)] = shifts["TIMEOFF_HOURS"]
            notes[(by_name["Сидоров"].id, date)] = "Отгул за ранее отработанные часы"

    for (emp_id, date), shift in schedule_map.items():
        db.add(ScheduleEntry(employee_id=emp_id, date=date, shift_type_id=shift.id,
                             note=notes.get((emp_id, date), "")))
    db.flush()

    from .base_schedule import base_shift, load_base_config
    base_cfg = load_base_config(db)

    def shift_for(emp: Employee, d: dt.date) -> ShiftType | None:
        override = schedule_map.get((emp.id, d))
        if override is not None:
            return override
        return base_shift(db, emp, d, base_cfg)

    # ───────────────────── отметки прихода/ухода за последние ~45 дней ─────────────────────
    now = now_local()
    emp_index = {e.id: e for e, _, _ in employees}

    def add_punch(emp_id: int, ts: dt.datetime, kind: str, note: str = "") -> None:
        if ts > now:
            return
        db.add(Punch(employee_id=emp_id, ts=ts.replace(second=rnd.randint(0, 59), microsecond=0),
                     kind=kind, source="web", note=note))

    class _FakeEntry:
        __slots__ = ("employee_id", "date", "shift_type")
        def __init__(self, employee_id, date, shift_type):
            self.employee_id, self.date, self.shift_type = employee_id, date, shift_type

    entries = []
    for emp, _, _ in employees:
        d = today - dt.timedelta(days=45)
        while d <= today:
            sh = shift_for(emp, d)
            if sh is not None and sh.kind == "work":
                entries.append(_FakeEntry(emp.id, d, sh))
            d += dt.timedelta(days=1)

    ot_descriptions = [
        "Догонял подготовку зала к банкету, работал с Ивановым",
        "Закрывал инвентаризацию белья вместе со старшим батлером",
        "Помогал службе кейтеринга: сервировка, вынос блюд",
        "Принимал доставку оборудования, раскладка по кладовым",
    ]

    for e in entries:
        emp = emp_index.get(e.employee_id)
        if not emp or not e.shift_type or e.shift_type.kind != "work":
            continue
        if e.date > today:
            continue
        shift = e.shift_type
        sh, sm = (int(x) for x in shift.start_time.split(":"))
        eh, em = (int(x) for x in shift.end_time.split(":"))
        start = dt.datetime(e.date.year, e.date.month, e.date.day, sh, sm)
        end = dt.datetime(e.date.year, e.date.month, e.date.day, eh, em)
        if shift.overnight:
            end += dt.timedelta(days=1)

        if start <= now < end:                      # смена идёт прямо сейчас
            add_punch(emp.id, start + dt.timedelta(minutes=rnd.randint(-8, 12)), "IN")
            continue
        if end > now:                               # сегодняшняя смена ещё не закончилась
            add_punch(emp.id, start + dt.timedelta(minutes=rnd.randint(-8, 12)), "IN")
            continue

        dice = rnd.random()
        late_in = rnd.randint(3, 27) if dice < 0.3 else rnd.randint(-10, 2)
        out_shift = rnd.choice([-95, -70, -40, -15, 0, 10, 25, 45, 80, 130])
        add_punch(emp.id, start + dt.timedelta(minutes=late_in), "IN")
        note = rnd.choice(ot_descriptions) if out_shift >= 45 else ""
        add_punch(emp.id, end + dt.timedelta(minutes=out_shift), "OUT", note)

        # аномалии для демонстрации контроля
        if emp.full_name.startswith("Фёдоров") and e.date == today - dt.timedelta(days=4):
            db.query(Punch).filter(Punch.employee_id == emp.id,
                                   Punch.ts >= end, Punch.ts <= end + dt.timedelta(hours=6),
                                   Punch.kind == "OUT").delete()
        if emp.full_name.startswith("Смирнов") and e.date == today - dt.timedelta(days=2):
            db.query(Punch).filter(Punch.employee_id == emp.id,
                                   Punch.ts >= start - dt.timedelta(hours=2),
                                   Punch.ts <= end + dt.timedelta(hours=6)).delete()

    db.flush()

    # ───────────────────── пересчёт табеля ─────────────────────
    recalc_range(db, today - dt.timedelta(days=40), today + dt.timedelta(days=40), commit=False)

    # ───────────────────── ночной отчёт: справочник областей и чек-листы ─────────────────────
    _seed_night_dirs(db)
    # ───────────────────── электрокары: места парковки и парк ─────────────────────
    _seed_cars(db, {e.full_name.split()[0]: e for e, _, _ in employees})

    db.commit()
    return True


NIGHT_AREAS = [
    ("Лобби", "общие зоны", ["Чистота пола и стоек ресепшн", "Освещение: все лампы горят",
                             "Мебель расставлена по схеме", "Нет посторонних запахов"]),
    ("Ресторан", "общие зоны", ["Столы сервированы на завтраки", "Посуда убрана в шкаф",
                                "Проверка холодильного оборудования (температура)",
                                "Мусор вынесен, пакеты сменены"]),
    ("Зона SPA", "общие зоны", ["Бассейн: уровень воды и химия в норме", "Шезлонги протёрты",
                                 "Полотенца пополнены"]),
    ("Кухня", "служебные", ["Оборудование выключено", "Продукты подписаны и убраны",
                            "Вытяжка проверена", "Уборка завершена"]),
    ("Кладовая белья", "служебные", ["Учёт по журналу сходится", "Дверь закрыта на навесной замок"]),
]

CAR_LOCATIONS = ["Парковка у главного входа", "Навес у служебного входа", "Место с зарядкой у корпуса B"]
CARS_DEMO = [("1", "free", "Парковка у главного входа", ""), ("2", "busy", "Навес у служебного входа", "Иванов"),
             ("3", "charging", "Место с зарядкой у корпуса B", ""), ("4", "free", "Навес у служебного входа", ""),
             ("5", "maintenance", "Гараж", "")]


def _seed_night_dirs(db: Session) -> None:
    from .models import ChecklistItem, NightArea

    for name, cat, items in NIGHT_AREAS:
        area = NightArea(name=name, category=cat)
        db.add(area)
        db.flush()
        for i, text in enumerate(items, start=10):
            db.add(ChecklistItem(area_id=area.id, text=text, sort_order=i))
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
