"""Часть 4, задача 4: API экрана «Мои гости» — «Сегодня», «Мой месяц», «Все мои гости», карточка
своего гостя с историей (спецификация 2026-10-27-stays-butler-mine-design §5, §7)."""
from __future__ import annotations

import datetime as dt
import json

import pytest
from sqlalchemy import delete, select

from app.modules.stays.application import mine

from .helpers import API, create_res, make_category, make_guest, set_guest
from .test_mine_ownership import _line


def D(iso: str) -> dt.date:
    return dt.date.fromisoformat(iso)


def _hp(day: str, half: int) -> int:
    return D(day).toordinal() * 2 + half


@pytest.fixture()
def on_day(monkeypatch):
    """«Сегодня» экрана «Мои гости»."""
    def _set(day: dt.date) -> None:
        monkeypatch.setattr(mine, "local_date", lambda: day)
    return _set


def _res(client, cat, ci: str, co: str, guests: list[dict], **kw) -> dict:
    return create_res(client, cat, ci, co, [(g["id"], "main" if i == 0 else "guest", None, None)
                                            for i, g in enumerate(guests)], **kw)


def _short(employee_id: int) -> str:
    from app.core.db import SessionLocal
    from app.modules.employees.application.catalog import Employee

    with SessionLocal() as s:
        e = s.get(Employee, employee_id)
        return e.short_name or e.full_name


# ── «Сегодня» ────────────────────────────────────────────────────────────────

def test_today_lists_only_today_led(manager_role_client, manager_client, butlers, butler_client, on_day):
    """Брони, где Иванов ведёт кого-то в эту ночь; в карточке — только те гости, кого ведёт он
    (явный список Кузнецовой сильнее его строки «вся бронь»); логистика — сегодня и завтра."""
    me, other = butlers["a"], butlers["b"]
    day = D("2041-03-10")
    cat = make_category(manager_role_client, n_units=3)
    g1, g2, g3, g4 = (make_guest(manager_client) for _ in range(4))
    a = _res(manager_client, cat, "2041-03-09", "2041-03-12", [g1, g2], note="подать завтрак в номер", logistics=[
        {"kind": "flight", "date": "2041-03-10", "time": "07:40", "description": "сегодня"},
        {"kind": "transfer", "date": "2041-03-11", "time": "10:00", "description": "завтра"},
        {"kind": "flight", "date": "2041-03-12", "time": "12:00", "description": "послезавтра"}])
    b = _res(manager_client, cat, "2041-03-10", "2041-03-12", [g3])
    c = _res(manager_client, cat, "2041-03-10", "2041-03-12", [g4])
    _line(me, day, a["id"])
    _line(other, day, a["id"], guests=(g2["id"],))
    _line(me, day + dt.timedelta(days=1), b["id"])          # ведёт завтра — не сегодня
    _line(other, day, c["id"])                              # чужая
    on_day(day)
    body = butler_client.get(f"{API}/mine/today")
    assert body.status_code == 200, body.text
    body = body.json()
    assert body["date"] == "2041-03-10"
    rows = {x["reservation_id"]: x for x in body["reservations"]}
    assert a["id"] in rows and b["id"] not in rows and c["id"] not in rows
    row = rows[a["id"]]
    assert [g["guest_id"] for g in row["guests"]] == [g1["id"]]
    assert row["guests"][0]["role"] == "main" and row["check_in"] == "2041-03-09" and row["check_out"] == "2041-03-12"
    assert row["unit"] in {u["label"] for u in cat["units"]}
    assert [lg["description"] for lg in row["logistics"]] == ["сегодня", "завтра"]
    assert row["note"] == "подать завтрак в номер"
    assert set(row["guests"][0]) >= {"guest_id", "name", "special", "vip_code", "role", "phone", "preferences",
                                     "special_dates_soon"}


def test_today_unit_by_fund_of_day(manager_role_client, manager_client, butlers, butler_client, today, on_day):
    """Объект «Сегодня» — по версии фонда этого дня: переименование с даты D видно с D."""
    today("2041-05-10")
    cat = make_category(manager_role_client, n_units=1)
    unit = cat["units"][0]
    g = make_guest(manager_client)
    r = create_res(manager_client, cat, "2041-06-08", "2041-06-13", [(g["id"], "main", None, None)],
                   moves=[{"move_date": "2041-06-11", "category_id": cat["id"]}])
    opened = manager_role_client.post(f"{API}/fund/draft", json={"valid_from": "2041-06-10"})
    assert opened.status_code == 200, opened.text
    renamed = cat["code"] + "-нов"
    put = manager_role_client.put(f"{API}/fund/draft/units/{unit['id']}", json={
        "rev": opened.json()["rev"], "label": renamed, "category_id": cat["id"]})
    assert put.status_code == 200, put.text
    assert manager_role_client.post(f"{API}/fund/draft/publish", json={"rev": put.json()["rev"]}).status_code == 200
    for d in ("2041-06-09", "2041-06-12"):
        _line(butlers["a"], D(d), r["id"])

    def unit_on(day: str) -> str:
        on_day(D(day))
        rows = butler_client.get(f"{API}/mine/today").json()["reservations"]
        return next(x["unit"] for x in rows if x["reservation_id"] == r["id"])
    assert unit_on("2041-06-09") == unit["label"]
    assert unit_on("2041-06-12") == renamed


def test_today_special_dates_7_days(manager_role_client, manager_client, butlers, butler_client, on_day):
    """Особые даты и день рождения — ежегодные, в ближайшие 7 дней, датой ближайшего раза."""
    day = D("2041-07-01")
    cat = make_category(manager_role_client, n_units=1)
    g = make_guest(manager_client, special=True)
    set_guest(g["id"], birth_date=dt.date(1980, 7, 4), special_dates_json=json.dumps([
        {"date": "2010-07-06", "what": "Годовщина свадьбы"}, {"date": "2015-07-20", "what": "Далеко"},
        {"date": "2016-06-30", "what": "Вчера"}, {"date": "", "what": "Без даты"}], ensure_ascii=False))
    r = _res(manager_client, cat, "2041-07-01", "2041-07-03", [g])
    _line(butlers["a"], day, r["id"])
    on_day(day)
    rows = butler_client.get(f"{API}/mine/today").json()["reservations"]
    guest = next(x for x in rows if x["reservation_id"] == r["id"])["guests"][0]
    assert guest["special"] is True
    assert guest["special_dates_soon"] == [{"date": "2041-07-04", "what": "День рождения"},
                                           {"date": "2041-07-06", "what": "Годовщина свадьбы"}]


def test_today_departing_led_last_night(manager_role_client, manager_client, butlers, butler_client, on_day):
    """Гость, которого батлер вёл прошлой ночью и который выезжает сегодня, — в «Сегодня» с
    departing (виден трансфер выезда); выехавший вчера — нет (Ruling 6)."""
    me = butlers["a"]
    cat = make_category(manager_role_client, n_units=3)
    g1, g2, g3, g4 = (make_guest(manager_client) for _ in range(4))
    a = _res(manager_client, cat, "2041-08-07", "2041-08-10", [g1], logistics=[
        {"kind": "transfer", "date": "2041-08-10", "time": "11:00", "description": "выезд"}])
    b = _res(manager_client, cat, "2041-08-06", "2041-08-09", [g2])
    c = create_res(manager_client, cat, "2041-08-09", "2041-08-12", [
        (g3["id"], "main", None, None), (g4["id"], "guest", "2041-08-09", "2041-08-10")])
    _line(me, D("2041-08-09"), a["id"])
    _line(me, D("2041-08-08"), b["id"])
    _line(me, D("2041-08-09"), c["id"])
    _line(me, D("2041-08-10"), c["id"])
    on_day(D("2041-08-10"))
    rows = {x["reservation_id"]: x for x in butler_client.get(f"{API}/mine/today").json()["reservations"]}
    assert b["id"] not in rows
    ra = rows[a["id"]]
    assert ra["departing"] is True and [(g["guest_id"], g["departing"]) for g in ra["guests"]] == [(g1["id"], True)]
    assert [lg["description"] for lg in ra["logistics"]] == ["выезд"]
    assert ra["unit"] in {u["label"] for u in cat["units"]}            # объект прошлой ночи
    rc = rows[c["id"]]
    assert rc["departing"] is False
    assert [(g["guest_id"], g["departing"]) for g in rc["guests"]] == [(g3["id"], False), (g4["id"], True)]


def test_today_sorted_by_unit_naturally(manager_role_client, manager_client, butlers, butler_client, on_day):
    """Порядок «Сегодня» — по объекту естественно: «-2» раньше «-10» (как в «Моём месяце»)."""
    cat = make_category(manager_role_client, n_units=11)
    labels = {u["label"] for u in cat["units"]}
    for _ in range(11):
        r = _res(manager_client, cat, "2041-08-20", "2041-08-22", [make_guest(manager_client)])
        _line(butlers["a"], D("2041-08-20"), r["id"])
    on_day(D("2041-08-20"))
    units = [x["unit"] for x in butler_client.get(f"{API}/mine/today").json()["reservations"] if x["unit"] in labels]
    assert units == [f"{cat['code']}-{i}" for i in range(1, 12)]


def test_staff_guest_stays_explicit_line_beats_whole(manager_role_client, manager_client, butlers):
    """Карточка гостя у службы: в ночь, когда гостя явно ведёт B, строка «вся бронь» A его не
    ведёт; в остальные ночи A — по-прежнему батлер гостя."""
    from app.core.db import SessionLocal
    from app.modules.employees.application.catalog import Employee
    from app.modules.stays.adapters.orm import CoverageLine

    a_id, b_id = butlers["a"], butlers["b"]
    cat = make_category(manager_role_client, n_units=1)
    g1, g2 = make_guest(manager_client), make_guest(manager_client)
    r = _res(manager_client, cat, "2043-05-20", "2043-05-22", [g1, g2])
    _line(a_id, D("2043-05-20"), r["id"])
    _line(b_id, D("2043-05-20"), r["id"], guests=(g2["id"],))
    _line(a_id, D("2043-05-21"), r["id"])
    with SessionLocal() as s:
        a_name, b_name = s.get(Employee, a_id).full_name, s.get(Employee, b_id).full_name

    def butlers_of(g):
        stays = manager_client.get(f"{API}/guests/{g['id']}/card").json()["stays"]
        return next(x for x in stays if x["reservation_id"] == r["id"])["butlers"]
    assert butlers_of(g1) == [a_name]
    assert sorted(butlers_of(g2)) == sorted([a_name, b_name])        # A — за ночь 21-го
    # без ночи 21-го у A гость g2 — только B
    with SessionLocal() as s:
        s.execute(delete(CoverageLine).where(CoverageLine.reservation_id == r["id"], CoverageLine.day == D("2043-05-21")))
        s.commit()
    assert butlers_of(g2) == [b_name]
    assert butlers_of(g1) == [a_name]


# ── «Мой месяц» ──────────────────────────────────────────────────────────────

def _month(client, first: str, last: str):
    return client.get(f"{API}/mine/month", params={"first": first, "last": last})


def test_month_rows_and_unallocated_row(manager_role_client, manager_client, butlers, butler_client):
    """Строки — объекты своих броней периода, «без объекта» — внизу; своя бронь из прошлого месяца
    (строка только в августе) — тоже полосой; чужой брони нет."""
    me, other = butlers["a"], butlers["b"]
    one = make_category(manager_role_client, n_units=1)
    two = make_category(manager_role_client, n_units=2)
    ga, gb, gc, gd, ge = (make_guest(manager_client) for _ in range(5))
    a = _res(manager_client, one, "2041-09-05", "2041-09-08", [ga], number="1")
    b = _res(manager_client, one, "2041-09-05", "2041-09-08", [gb], number="2")   # овербукинг — без объекта
    assert b["segments"][0]["unit_id"] is None
    c = _res(manager_client, two, "2041-09-10", "2041-09-12", [gc])
    d = _res(manager_client, two, "2041-09-10", "2041-09-12", [gd])
    e = _res(manager_client, two, "2041-08-30", "2041-09-03", [ge])
    _line(me, D("2041-09-05"), a["id"])
    _line(me, D("2041-09-06"), b["id"])
    _line(me, D("2041-09-10"), c["id"])
    _line(other, D("2041-09-10"), d["id"])
    _line(me, D("2041-08-30"), e["id"])
    resp = _month(butler_client, "2041-09-01", "2041-09-30")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["days"][0] == "2041-09-01" and len(body["days"]) == 30
    bars = {bar["reservation_id"]: (row["unit_id"], row["label"], bar) for row in body["rows"] for bar in row["bars"]}
    assert set(bars) == {a["id"], b["id"], c["id"], e["id"]}
    assert body["rows"][-1]["unit_id"] is None and body["rows"][-1]["label"] == "без объекта"
    assert [x["reservation_id"] for x in body["rows"][-1]["bars"]] == [b["id"]]
    assert all(row["unit_id"] is not None for row in body["rows"][:-1])
    uid, label, bar = bars[a["id"]]
    assert uid == one["units"][0]["id"] and label == one["units"][0]["label"]
    assert (bar["start_pos"], bar["end_pos"]) == (_hp("2041-09-05", 1), _hp("2041-09-08", 0))
    assert bar["main_guest"].startswith(ga["last_name"]) and bar["status"] == "confirmed"
    # объект — после распределения всех броней (d могла сдвинуть c на другой объект категории)
    card = manager_client.get(f"{API}/reservations/{c['id']}/card").json()
    assert bars[c["id"]][0] == card["segments"][0]["unit_id"]
    # строка объекта — один раз, даже если в нём несколько своих броней
    assert len({row["unit_id"] for row in body["rows"]}) == len(body["rows"])


def test_month_tentative_flag(manager_role_client, manager_client, butlers, butler_client):
    cat = make_category(manager_role_client, n_units=1)
    g = make_guest(manager_client, special=True)
    r = _res(manager_client, cat, "2041-10-03", "2041-10-05", [g], status="tentative")
    _line(butlers["a"], D("2041-10-03"), r["id"])
    body = _month(butler_client, "2041-10-01", "2041-10-31").json()
    bar = next(b for row in body["rows"] for b in row["bars"] if b["reservation_id"] == r["id"])
    assert bar["status"] == "tentative" and bar["special"] is True


def test_month_load_levels_one_many_over(manager_role_client, manager_client, butlers, butler_client):
    """Нагрузка батлера по дням: один гость, несколько, выше лимита; дни без гостей — без отметки."""
    me = butlers["a"]
    small = make_category(manager_role_client, n_units=2, weight=4)
    big = make_category(manager_role_client, n_units=1, weight=50)
    g1, g2, g3, g4 = (make_guest(manager_client) for _ in range(4))
    r1 = _res(manager_client, small, "2041-11-02", "2041-11-03", [g1])
    r2 = _res(manager_client, small, "2041-11-04", "2041-11-05", [g2, g3])
    r3 = _res(manager_client, big, "2041-11-06", "2041-11-07", [g4])
    for day, r in (("2041-11-02", r1), ("2041-11-04", r2), ("2041-11-06", r3)):
        _line(me, D(day), r["id"])
    body = _month(butler_client, "2041-11-01", "2041-11-30").json()
    load = {x["day"]: x for x in body["load"]}
    assert set(load) == {"2041-11-02", "2041-11-04", "2041-11-06"}
    assert (load["2041-11-02"]["level"], load["2041-11-02"]["guests"], load["2041-11-02"]["value"]) == ("one", 1, 4.0)
    assert (load["2041-11-04"]["level"], load["2041-11-04"]["guests"]) == ("many", 2)
    assert load["2041-11-06"]["level"] == "over" and load["2041-11-06"]["value"] > body["limit"]


@pytest.fixture()
def tabel_days():
    from app.core.db import SessionLocal
    from app.modules.timesheet.application.catalog import TabelDay

    made: list[tuple[int, dt.date]] = []

    def add(employee_id: int, day: dt.date, code: str) -> None:
        with SessionLocal() as s:
            s.add(TabelDay(employee_id=employee_id, date=day, code=code, plan_minutes=0))
            s.commit()
        made.append((employee_id, day))
    yield add
    with SessionLocal() as s:
        for e, d in made:
            s.execute(delete(TabelDay).where(TabelDay.employee_id == e, TabelDay.date == d))
        s.commit()


def test_month_absences_from_schedule(butlers, butler_client, tabel_days):
    """Дни отсутствия по Графику — коды подмены (ОТ, Б…); выходной «В» — не отсутствие."""
    tabel_days(butlers["a"], D("2041-12-05"), "ОТ")
    tabel_days(butlers["a"], D("2041-12-06"), "Б")
    tabel_days(butlers["a"], D("2041-12-07"), "В")
    tabel_days(butlers["b"], D("2041-12-08"), "ОТ")                 # чужое отсутствие
    body = _month(butler_client, "2041-12-01", "2041-12-31").json()
    assert body["absences"] == ["2041-12-05", "2041-12-06"]


def test_month_span_max_62_422(butler_client):
    too_long = _month(butler_client, "2042-01-01", "2042-03-04")                     # 63 дня
    assert too_long.status_code == 422 and "62" in too_long.json()["detail"]
    assert _month(butler_client, "2042-01-01", "2042-03-03").status_code == 200      # ровно 62
    assert _month(butler_client, "2042-01-10", "2042-01-09").status_code == 422


# ── «Все мои гости» и карточка ───────────────────────────────────────────────

def test_all_guests_search_only_own(manager_role_client, manager_client, butlers, butler_client):
    from .helpers import uniq
    u = uniq()
    cat = make_category(manager_role_client, n_units=2)
    mine_g = make_guest(manager_client, f"Поисксвой{u}")
    foreign = make_guest(manager_client, f"Поисксвой{u}чужой")
    r1 = _res(manager_client, cat, "2041-02-01", "2041-02-03", [mine_g])
    r2 = _res(manager_client, cat, "2041-02-10", "2041-02-12", [mine_g])
    r3 = _res(manager_client, cat, "2041-02-01", "2041-02-03", [foreign])
    _line(butlers["a"], D("2041-02-01"), r1["id"])
    _line(butlers["a"], D("2041-02-10"), r2["id"])
    _line(butlers["b"], D("2041-02-01"), r3["id"])
    body = butler_client.get(f"{API}/mine/guests", params={"q": f"поисксвой{u}"}).json()
    assert body["total"] == 1
    (row,) = body["rows"]
    assert row["guest_id"] == mine_g["id"] and row["name"].startswith(f"Поисксвой{u}")
    # обе брони в будущем: проживаний ещё нет, следующий заезд — ближайший (финальное ревью, п. 3)
    assert row["stays"] == 0 and row["last_stay"] is None and row["next_stay"] == "2041-02-01"
    assert row["special"] is False and row["vip_code"] == ""
    everyone = butler_client.get(f"{API}/mine/guests").json()
    assert everyone["total"] >= 1 and len(everyone["rows"]) <= 50
    assert foreign["id"] not in {x["guest_id"] for x in everyone["rows"]}
    assert butler_client.get(f"{API}/mine/guests", params={"limit": 51}).status_code == 422


def test_guest_card_history_me_and_other_name(manager_role_client, manager_client, butlers, butler_client):
    """Карточка своего гостя: профиль целиком и кто его вёл — «вёл я» и имя другого батлера."""
    me, other = butlers["a"], butlers["b"]
    cat = make_category(manager_role_client, n_units=1)
    g = make_guest(manager_client)
    set_guest(g["id"], phone="+79991234567")
    r = _res(manager_client, cat, "2041-04-03", "2041-04-08", [g])
    for i, e in ((0, me), (1, me), (2, other), (3, other), (4, other)):
        _line(e, D("2041-04-03") + dt.timedelta(days=i), r["id"])
    resp = butler_client.get(f"{API}/mine/guests/{g['id']}")
    assert resp.status_code == 200, resp.text
    card = resp.json()
    assert card["id"] == g["id"] and card["phone_display"] and "links" in card and "special_dates" in card
    (stay,) = [h for h in card["history"] if h["reservation_id"] == r["id"]]
    assert (stay["check_in"], stay["check_out"], stay["unit"]) == ("2041-04-03", "2041-04-08", cat["units"][0]["label"])
    assert stay["led"] == [
        {"employee_id": me, "name": _short(me), "me": True, "first": "2041-04-03", "last": "2041-04-05"},
        {"employee_id": other, "name": _short(other), "me": False, "first": "2041-04-05", "last": "2041-04-08"}]


def test_foreign_guest_card_403(manager_role_client, manager_client, butlers, butler_client):
    cat = make_category(manager_role_client, n_units=1)
    g = make_guest(manager_client)
    r = _res(manager_client, cat, "2041-04-20", "2041-04-22", [g])
    _line(butlers["b"], D("2041-04-20"), r["id"])
    assert butler_client.get(f"{API}/mine/guests/{g['id']}").status_code == 403
    assert butler_client.get(f"{API}/mine/guests/999999999").status_code == 404


def test_mine_screens_need_perm(mgmt_client):
    for path in ("/mine/today", "/mine/month?first=2041-01-01&last=2041-01-31", "/mine/guests", "/mine/guests/1"):
        assert mgmt_client.get(f"{API}{path}").status_code == 403, path


# ── Бюджет SQL (§7) ──────────────────────────────────────────────────────────

NOW = D("2042-02-10")


@pytest.fixture()
def history_of():
    """Батлер (новый, неактивный сотрудник) с n своими броннями в прошлом (2001–2005) и одной
    сегодня; общий гость — во всех. Без API: так быстрее. Удаляется после теста."""
    from app.core.db import SessionLocal
    from app.modules.employees.application.catalog import Employee
    from app.modules.stays.adapters.orm import CategoryState, CoverageLine, Guest, Occupant, Reservation

    made: list[tuple[int, list[int], list[int]]] = []

    def build(n: int) -> tuple[int, int]:
        with SessionLocal() as s:
            cat_id = s.scalar(select(CategoryState.category_id).order_by(CategoryState.category_id).limit(1))
            emp = Employee(full_name=f"Историев Бюджет {n}", short_name=f"Историев{n}", position="Батлер",
                           hired_at=dt.date(2000, 1, 1), active=False)
            shared = Guest(last_name=f"Общий{n}", search_text=f"общий{n}")
            s.add_all([emp, shared])
            s.flush()
            rids, gids = [], [shared.id]
            for i in range(n + 1):
                ci = NOW if i == n else dt.date(2001, 1, 1) + dt.timedelta(days=3 * i)
                g = Guest(last_name=f"Историев{n}гость{i}", search_text=f"историев{n}гость{i}")
                r = Reservation(number=f"HIST{n}-{i}", check_in=ci, check_out=ci + dt.timedelta(days=2),
                                category_id=cat_id, search_text=f"hist{n}-{i}")
                s.add_all([g, r])
                s.flush()
                s.add_all([Occupant(reservation_id=r.id, guest_id=g.id, date_from=r.check_in, date_to=r.check_out,
                                    role="main"),
                           Occupant(reservation_id=r.id, guest_id=shared.id, date_from=r.check_in,
                                    date_to=r.check_out, role="guest"),
                           CoverageLine(day=ci, employee_id=emp.id, reservation_id=r.id)])
                rids.append(r.id)
                gids.append(g.id)
            s.commit()
            made.append((emp.id, rids, gids))
            return emp.id, shared.id
    yield build
    with SessionLocal() as s:
        for e, rids, gids in made:
            s.execute(delete(CoverageLine).where(CoverageLine.employee_id == e))
            s.execute(delete(Occupant).where(Occupant.reservation_id.in_(rids)))
            s.execute(delete(Reservation).where(Reservation.id.in_(rids)))
            s.execute(delete(Guest).where(Guest.id.in_(gids)))
            s.execute(delete(Employee).where(Employee.id == e))
        s.commit()


def test_mine_budget_independent_of_history(history_of, sql_counter, on_day, db):
    """Каждый из четырёх ответов — одно и то же число SQL-операторов при 5 и 500 своих бронях."""
    from app.modules.stays.adapters.duty_timesheet import TimesheetDuty
    from app.modules.stays.adapters.orm import Guest

    on_day(NOW)
    small, big = history_of(5), history_of(500)
    calls = {
        "today": lambda e, g: mine.mine_today(db, e),
        "month": lambda e, g: mine.mine_month(db, e, D("2042-02-01"), D("2042-02-28"), TimesheetDuty(db)),
        "guests": lambda e, g: mine.mine_guests(db, e),
        "card": lambda e, g: mine.mine_guest_card(db, e, db.get(Guest, g)),
    }
    for name, call in calls.items():
        counts, sizes = [], []
        for e, g in (small, big):
            db.expire_all()
            call(e, g)                                    # прогрев кэшей процесса
            db.expire_all()
            gst = db.get(Guest, g)
            with sql_counter() as c:
                out = call(e, gst.id)
            counts.append(c["total"])
            sizes.append(out)
        assert counts[0] == counts[1], (name, counts)
        if name == "today":
            assert all(len(x["reservations"]) == 1 for x in sizes)
        if name == "month":
            assert all(sum(len(r["bars"]) for r in x["rows"]) == 1 for x in sizes)
        if name == "guests":
            assert [x["total"] for x in sizes] == [7, 502] and len(sizes[1]["rows"]) == 50
        if name == "card":
            assert [len(x["history"]) for x in sizes] == [6, 501]
