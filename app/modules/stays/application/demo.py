"""Демо-данные «Шахматки» (§11): весь фонд (37 вилл, имение, 2 медицинских апартамента,
400 номеров в двух корпусах), вымышленные гости с VIP/VVIP и связями, брони от «вчера» на
месяц вперёд (совместная, переезд, смена главного гостя, отказ от батлера, не заехал),
назначения батлеров с примерами перегруза, «вне смены» и «нужна подмена».

Батлеры демо — Сидоров, Морозова, Петров, Орлов, Фёдоров: Иванова и Кузнецову используют
тесты, а тестовая база создаётся с DEMO_SEED=1. Все брони заканчиваются не раньше сегодня:
распределение по объектам размещает только такие (окно, ревью этапа 2)."""
from __future__ import annotations

import datetime as dt
import random
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import local_date
from app.modules.employees.application.catalog import Employee
from app.modules.timesheet.application.catalog import TabelDay
from app.modules.timesheet.application.engine_common import engine_ports
from app.modules.timesheet.application.roster import roster

from ..adapters.orm import (
    Assignment,
    Block,
    BlockNight,
    CategoryKind,
    CategoryState,
    CoverageLine,
    Guest,
    GuestLink,
    Label,
    Logistics,
    Move,
    Occupant,
    Ooo,
    Reservation,
    StayGroup,
)
from . import allocation, fund_drafts, fund_versions
from .fund import seed_escorts_from_positions
from .fund_versions import INITIAL_DATE
from .guests import guest_search_text

CATEGORIES = [  # код, название, вид, сопровождение, вес, объектов
    ("VEG", "Вилла Garden", "villa", True, 4, 13), ("FWV", "Вилла у воды", "villa", True, 4, 12),
    ("VIG", "Вилла с видом", "villa", True, 4, 12), ("ESTATE", "Имение сёгуна", "estate", True, 6, 1),
    ("MED", "Медицинские апартаменты", "apartment", True, 3, 2),
    ("DLX", "Делюкс", "room", False, 1, 160), ("PRM", "Премьер", "room", False, 1, 110),
    ("FAM", "Семейный", "room", False, 1, 60), ("JST", "Джуниор сюит", "room", False, 1, 40),
    ("SUI", "Сюит", "room", True, 2, 20), ("PRS", "Президентский", "room", True, 3, 10),
]
# виды категорий: код в CATEGORIES, название в справочнике, раскрывать раздел на шахматке
KINDS = {"villa": ("вилла", True), "estate": ("имение", True), "apartment": ("апартаменты", True),
         "room": ("номер", False)}
LABELS = [("От руководства", "#d8833b"), ("Открытый рынок", "#3b6fd8"), ("Корпоративный", "#7a4fd0")]
SURNAMES = ["Орлов", "Гусев", "Лебедев", "Фомина", "Зайцев", "Кузьмин", "Белова", "Новиков", "Соловьёва",
            "Васильев", "Павлова", "Семёнов", "Голубева", "Виноградов", "Богданова", "Воробьёв", "Фролова",
            "Медведев", "Тарасова", "Беляев", "Комарова", "Киселёв", "Макарова", "Андреев", "Ковалёва",
            "Ильин", "Гаврилова", "Титов", "Кудрявцева", "Баранов", "Куликова", "Алексеев", "Степанова",
            "Яковлев", "Сорокина", "Сергеев", "Романова", "Захаров", "Борисова", "Королёв", "Герасимова",
            "Пономарёв", "Григорьева", "Лазарев", "Миронова", "Ефимов", "Абрамова", "Мельников", "Власова",
            "Афанасьев", "Карпова", "Ершов", "Никитина", "Соболев", "Третьякова", "Субботин", "Шарова",
            "Ларионов", "Кононова", "Блинов"]
FIRST = ["Андрей", "Мария", "Пётр", "Елена", "Дмитрий", "Ольга", "Игорь", "Анна", "Сергей", "Наталья"]
# семья из трёх поколений (§4): ключ, фамилия, имя, пол, уровень
FAMILY = (("ivan", "Петров", "Иван", "m", "vip"), ("maria", "Петрова", "Мария", "f", "vip"),
          ("petr", "Петров", "Пётр", "m", "regular"), ("olga", "Петрова", "Ольга", "f", "regular"),
          ("nikolay", "Петров", "Николай", "m", "regular"), ("anna", "Смирнова", "Анна", "f", "regular"),
          ("viktor", "Козлов", "Виктор", "m", "regular"), ("galina", "Козлова", "Галина", "f", "regular"),
          ("elena", "Петрова", "Елена", "f", "regular"))
# первичные связи: parent — первый родитель второго; остальное родство вычисляется
FAMILY_LINKS = (("ivan", "maria", "spouse"), ("nikolay", "olga", "spouse"), ("viktor", "galina", "spouse"),
                ("olga", "ivan", "parent"), ("nikolay", "ivan", "parent"), ("olga", "elena", "parent"),
                ("nikolay", "elena", "parent"), ("anna", "olga", "parent"), ("viktor", "maria", "parent"),
                ("galina", "maria", "parent"), ("ivan", "petr", "parent"), ("maria", "petr", "parent"))
DEMO_BUTLERS = ("Сидоров", "Морозова", "Петров", "Орлов", "Фёдоров")


def _butlers(db: Session) -> dict[str, int]:
    out = {}
    for e in db.scalars(select(Employee).where(Employee.active.is_(True))):
        key = e.full_name.split()[0]
        if key in DEMO_BUTLERS:
            out[key] = e.id
    return out


FLAGS = [("Смежные номера", "#d8833b"), ("Вид на море", "#3b6fd8"), ("С бассейном", "#2f9e8f"),
         ("Для аллергиков", "#7a4fd0")]
CONNECT = ("CNX", "Коннект", "room", False, 2, 1)                      # объект «12134» делится в будущей версии
ROOT_VILLAS = "Винные виллы"
VILLA_NODES = {"VEG": [(ROOT_VILLAS, "Семейная", "Первая линия"), (ROOT_VILLAS, "Семейная", "Вторая линия")],
               "FWV": [(ROOT_VILLAS, "У воды")], "VIG": [(ROOT_VILLAS, "С видом")]}
BLOCKS = {"1": "Блок A", "2": "Блок B"}
VIEWS = ("Вид на море", "Вид на парк")


def _tree() -> list[tuple[str, ...]]:
    nodes = [p for ps in VILLA_NODES.values() for p in ps]
    nodes += [("Имение",), ("Медцентр",)]
    nodes += [("Корпус", blk, view) for blk in BLOCKS.values() for view in VIEWS]
    return nodes


def _unit_specs() -> list[dict]:
    """Объекты исходной версии: обозначения, узлы дерева и флаги демо-фонда."""
    specs: list[dict] = []
    villa_no = 4001
    room_no = {"1": 101, "2": 101}
    for code, _t, kind, _e, _w, n in [*CATEGORIES, CONNECT]:
        for i in range(n):
            flags: list[str] = []
            floor = ""
            if kind == "villa":
                label, path = str(villa_no), VILLA_NODES[code][(i * 2 // n) % len(VILLA_NODES[code])]
                villa_no += 1
                if code == "FWV":
                    flags.append("С бассейном")
            elif kind == "estate":
                label, path = "Имение", ("Имение",)
            elif kind == "apartment":
                label, path = f"MED-{i + 1}", ("Медцентр",)
                flags.append("Для аллергиков")
            elif code == CONNECT[0]:
                label, path, floor = "12134", ("Корпус", BLOCKS["1"], VIEWS[0]), "1"
                flags.append("Смежные номера")
            else:
                b = "1" if i % 2 == 0 else "2"
                num = room_no[b]
                room_no[b] = num + 1 if (num % 100) < 40 else (num // 100 + 1) * 100 + 1
                sea = (num % 100) <= 20
                label, floor = f"{b}-{num}", str(num // 100)
                path = ("Корпус", BLOCKS[b], VIEWS[0 if sea else 1])
                if sea and num % 100 <= 6:
                    flags.append("Вид на море")
                if code == "FAM" and i % 5 == 0:
                    flags.append("Смежные номера")
            specs.append({"label": label, "category": code, "path": list(path), "floor": floor, "flags": flags})
    return specs


def _seed_kinds(db: Session) -> dict[str, int]:
    """Четыре вида демо (ревизия 0012 могла уже завести их в базе с прежними данными)."""
    have = dict(db.execute(select(CategoryKind.title, CategoryKind.id)).all())
    out = {}
    for i, (code, (title, expanded)) in enumerate(KINDS.items()):
        out[code] = have.get(title) or fund_drafts.save_kind(
            db, {"title": title, "sort_order": i * 10, "expanded": expanded}, None)
    return out


def _seed_fund(db: Session) -> tuple[dict, dict]:
    """Фонд демо: исходная версия через seed_initial, затем будущая версия с делением коннекта."""
    specs = _unit_specs()
    kind_ids = _seed_kinds(db)
    fund_drafts.seed_initial(
        db,
        categories=[{"code": c, "title": t, "kind_id": kind_ids[k], "escorted": e, "weight": w}
                    for c, t, k, e, w, _n in [*CATEGORIES, CONNECT]],
        groups=[{"path": list(p)} for p in _tree()],
        flags=[{"title": t, "color": c} for t, c in FLAGS],
        units=specs)
    snap = fund_versions.fund_on(db, INITIAL_DATE)
    cats = {c.code: SimpleNamespace(id=c.id) for c in snap.categories.values()}
    by_label = {u.label: SimpleNamespace(id=u.id) for u in snap.units.values()}
    units: dict[str, list[SimpleNamespace]] = {}
    for sp in specs:
        units.setdefault(sp["category"], []).append(by_label[sp["label"]])
    seed_connect_split(db)
    return cats, units


def seed_connect_split(db: Session) -> None:
    """Через две недели коннект 12134 делится на два номера Делюкс 1213 и 1214 (lineage от него).
    Это будущая версия фонда: распределение этапа 1 читает фонд на сегодня, брони демо от неё не зависят."""
    snap = fund_versions.fund_on(db, local_date())
    connect = next(u.id for u in snap.units.values() if u.label == "12134")
    dlx_id = next(c.id for c in snap.categories.values() if c.code == "DLX")
    draft = fund_drafts.open_draft(db, local_date() + dt.timedelta(days=14), None, "Деление коннекта 12134")
    fund_drafts.split_unit(db, draft.rev, connect, [{"label": "1213", "category_id": dlx_id},
                                                     {"label": "1214", "category_id": dlx_id}])
    fund_drafts.publish(db, None, draft.rev)


def seed_stays_demo(db: Session) -> None:
    if db.scalar(select(CategoryState.category_id).where(CategoryState.code == "VEG")) is not None:
        return
    rnd = random.Random(23)
    today = local_date()
    cats, units = _seed_fund(db)
    labels = [Label(title=t, color=c) for t, c in LABELS]
    db.add_all(labels)
    db.flush()

    guests = []
    for i, last in enumerate(SURNAMES):
        level = "vvip" if i in (0, 1) else "vip" if i in range(2, 10) else "regular"
        g = Guest(last_name=last, first_name=FIRST[i % len(FIRST)], gender="mf"[i % 2], level=level, source="demo",
                  phone=f"+7916{1000000 + i * 7919:07d}",
                  preferences_json='{"allergy": "орехи"}' if i % 9 == 0 else "{}")
        g.search_text = guest_search_text(g, set())
        guests.append(g)
    db.add_all(guests)
    db.flush()
    for a, b, kind in ((0, 10, "spouse"), (0, 11, "parent"), (0, 12, "assistant"), (1, 13, "spouse"),
                       (2, 14, "security"), (3, 15, "parent"), (4, 16, "spouse")):
        db.add(GuestLink(guest_a_id=guests[a].id, guest_b_id=guests[b].id, kind=kind))
    family = {key: Guest(last_name=last, first_name=first, middle_name="", phone="", email="", gender=gender,
                         level=level, source="demo")
              for key, last, first, gender, level in FAMILY}
    for g in family.values():
        g.search_text = guest_search_text(g, set())
    db.add_all(family.values())
    db.flush()
    for a, b, kind in FAMILY_LINKS:
        db.add(GuestLink(guest_a_id=family[a].id, guest_b_id=family[b].id, kind=kind))

    made: list[Reservation] = []
    gi = iter(range(10_000))

    def guest() -> Guest:
        return guests[next(gi) % len(guests)]

    def book(cat: str, ci: dt.date, co: dt.date, unit: SimpleNamespace | None, **kw) -> Reservation:
        status = "in_house" if ci <= today < co else "confirmed"
        r = Reservation(number=f"F{len(made) + 1:05d}", status=kw.pop("status", status), check_in=ci, check_out=co,
                        category_id=cats[cat].id, label_id=labels[len(made) % 3].id, source="demo",
                        search_text=f"f{len(made) + 1:05d}", **kw)
        db.add(r)
        db.flush()
        if unit is not None:
            # индекс 0 — первая часть первого сегмента; закрепление действует на весь сегмент
            db.add(Assignment(reservation_id=r.id, seg_index=0, unit_id=unit.id, pinned=True))
        made.append(r)
        return r

    def live(r: Reservation, *gs: Guest) -> None:
        for n, g in enumerate(gs):
            db.add(Occupant(reservation_id=r.id, guest_id=g.id, date_from=r.check_in, date_to=r.check_out,
                            role="main" if n == 0 else "guest"))

    # виллы, имение, апартаменты, люксы — плотно; первая бронь объекта уже идёт, но выезд не раньше сегодня
    for code in ("VEG", "FWV", "VIG", "ESTATE", "MED", "SUI", "PRS"):
        for u in units[code]:
            d = today - dt.timedelta(days=rnd.randint(0, 3))
            while d < today + dt.timedelta(days=28):
                co = d + dt.timedelta(days=rnd.randint(3, 7))
                if co < today + dt.timedelta(days=1):
                    co = today + dt.timedelta(days=1)
                r = book(code, d, co, u, declined_butler=(len(made) % 23 == 0))
                live(r, guest(), *([guest()] if rnd.random() < 0.4 else []))
                if rnd.random() < 0.3:
                    db.add(Logistics(reservation_id=r.id, kind="transfer", date=d, time="14:30",
                                     description="Трансфер SVO, Mercedes V"))
                d = co + dt.timedelta(days=rnd.randint(0, 2))
    # номера основного корпуса — автораспределение
    for _ in range(100):
        code = rnd.choice(["DLX", "PRM", "FAM", "JST"])
        ci = today + dt.timedelta(days=rnd.randint(0, 25))
        r = book(code, ci, ci + dt.timedelta(days=rnd.randint(1, 5)), None)
        live(r, guest())

    # особые случаи: совместная бронь, переезд, смена главного, не заехал
    group = StayGroup(title="Семья Орловых")
    db.add(group)
    db.flush()
    gci, gco = today + dt.timedelta(days=30), today + dt.timedelta(days=35)
    for g in (guests[0], guests[10]):
        r = book("VEG", gci, gco, None, group_id=group.id)
        live(r, g)
    mv = book("FWV", today + dt.timedelta(days=30), today + dt.timedelta(days=37), None)
    db.add(Move(reservation_id=mv.id, move_date=today + dt.timedelta(days=33), category_id=cats["VIG"].id))
    live(mv, guests[2])
    sw = book("VIG", today + dt.timedelta(days=30), today + dt.timedelta(days=36), None)
    db.add_all([Occupant(reservation_id=sw.id, guest_id=guests[3].id, date_from=sw.check_in,
                         date_to=sw.check_in + dt.timedelta(days=3), role="main"),
                Occupant(reservation_id=sw.id, guest_id=guests[15].id, date_from=sw.check_in + dt.timedelta(days=3),
                         date_to=sw.check_out, role="main")])
    # семья Петровых живёт сегодня в двух объектах: родственники видны на табло дня и в карточке брони
    staying = [r for r in made if r.status == "in_house" and r.check_out > today + dt.timedelta(days=1)][:2]
    for r, keys in zip(staying, (("ivan", "maria", "petr"), ("olga", "anna")), strict=False):
        for key in keys:
            db.add(Occupant(reservation_id=r.id, guest_id=family[key].id, date_from=r.check_in,
                            date_to=r.check_out, role="guest"))
    ns = book("PRS", today - dt.timedelta(days=1), today + dt.timedelta(days=3), None, status="no_show")
    live(ns, guests[5])
    _demo_ooo_blocks(db, today, units, cats)
    db.flush()
    allocation.run_allocation(db)

    seed_escorts_from_positions(db)
    _demo_coverage(db, today, made, units)
    _demo_users(db)


def _demo_ooo_blocks(db: Session, today: dt.date, units: dict, cats: dict) -> None:
    """Два OOO (целые сутки и с половинками: с обеда по утро) и два блока, один — с переменным остатком по ночам."""
    one = dt.timedelta(days=1)
    db.add_all([
        Ooo(unit_id=units["PRS"][0].id, start=today + 2 * one, end=today + 5 * one, start_half="AM",
            end_half="PM", reason="Ремонт ванной"),
        Ooo(unit_id=units["JST"][0].id, start=today + 8 * one, end=today + 10 * one, start_half="PM",
            end_half="AM", reason="Замена мебели")])
    fixed = Block(title="Конференция «Лето»", start=today + 12 * one, end=today + 15 * one)
    varying = Block(title="Свадьба Орловых", start=today + 20 * one, end=today + 24 * one)
    db.add_all([fixed, varying])
    db.flush()
    for n in range(3):
        db.add(BlockNight(block_id=fixed.id, category_id=cats["DLX"].id, night=fixed.start + n * one, quantity=2))
    for n, qty in enumerate((4, 4, 3, 2)):      # остаток блока убывает к ночи заезда гостей
        db.add(BlockNight(block_id=varying.id, category_id=cats["FAM"].id, night=varying.start + n * one,
                          quantity=qty))


def _demo_users(db: Session) -> None:
    """Демо-входы для ролей модуля: «Руководство: только просмотр» и «Загрузка без гостей»."""
    from app.core.identity import User
    from app.core.security import hash_password

    for login, role in (("rukovod", "mgmt_view"), ("sluzhba", "occupancy")):
        if db.scalar(select(User.id).where(User.username == login)) is None:
            db.add(User(username=login, password_hash=hash_password("demo1234"), role=role))
    db.flush()


def _demo_coverage(db: Session, today: dt.date, made: list[Reservation], units: dict) -> None:
    b = _butlers(db)
    if len(b) < 4:
        return
    first, last = today, today + dt.timedelta(days=29)
    ids = list(b.values())
    duty = roster(ids, first, last, engine_ports(db))

    def on(e: int, d: dt.date) -> bool:
        return bool(duty.get((e, d)) and duty[(e, d)].on_shift)

    def line(r: Reservation, d: dt.date, e: int) -> None:
        db.add(CoverageLine(day=d, employee_id=e, reservation_id=r.id, source="template"))

    escorted = set(db.scalars(select(CategoryState.category_id).where(CategoryState.escorted.is_(True))))
    pairs = [(b["Сидоров"], b["Морозова"]), (b["Петров"], b["Орлов"])]
    for n, r in enumerate(m for m in made if m.category_id in escorted and m.status != "no_show"
                          and not m.declined_butler and m.group_id is None):
        if n % 6 == 5:
            continue                                        # дыры: брони без батлера
        a, c = pairs[n % 2]
        d = max(r.check_in, first)
        while d < min(r.check_out, last + dt.timedelta(days=1)):
            if n == 0:
                line(r, d, b["Сидоров"])                     # «один на весь срок» → дни вне смены
            elif on(a, d) or on(c, d):
                line(r, d, a if on(a, d) else c)
            d += dt.timedelta(days=1)
    # перегруз: Морозова ведёт ещё три брони в один день
    day = today + dt.timedelta(days=2)
    extra = [r for r in made if r.category_id in escorted and r.check_in <= day < r.check_out
             and r.status != "no_show"][:3]
    for r in extra:
        line(r, day, b["Морозова"])
    # «нужна подмена»: у демо-батлера в окне код отсутствия; нет — отпуск на его выходной
    codes = {"ОТ", "ДО", "Б", "ОВ", "К"}
    target = next(((e, d) for (e, d), v in sorted(duty.items(), key=lambda x: x[0][1])
                   if v.tabel_code in codes and e in ids), None)
    if target is None:
        target = next(((e, d) for (e, d), v in sorted(duty.items(), key=lambda x: x[0][1])
                       if not v.on_shift and v.tabel_code and e in ids), None)
        if target is not None:
            row = db.scalar(select(TabelDay).where(TabelDay.employee_id == target[0], TabelDay.date == target[1]))
            row.code = "ОТ"
    # «Мои гости» для демо-входа ivanov: одна ночь сегодня (тесты берут Иванова с завтрашнего дня)
    ivanov = db.scalar(select(Employee.id).where(Employee.full_name.like("Иванов%")))
    tonight = next((r for r in made if r.category_id in escorted and r.check_in <= today < r.check_out
                    and r.status != "no_show" and r.group_id is None), None)
    if ivanov and tonight:
        line(tonight, today, ivanov)
    if target is not None:
        e, d = target
        r = next((r for r in made if r.category_id in escorted and r.check_in <= d < r.check_out
                  and r.status != "no_show"), None)
        if r is not None:
            line(r, d, e)
    db.flush()
