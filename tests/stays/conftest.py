"""Фикстуры модуля «Шахматка»: пользователи с ролями модуля (ревизия 0008)."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select


def _role_user(app_stack, username: str, role: str):
    from app.core.db import SessionLocal
    from app.core.identity import User
    from app.core.security import hash_password
    from tests.conftest import DEMO_PASSWORD, _login

    with SessionLocal() as s:
        if s.scalar(select(User).where(User.username == username)) is None:
            s.add(User(username=username, password_hash=hash_password(DEMO_PASSWORD), role=role))
            s.commit()
    return _login(app_stack["app"], username)


@pytest.fixture()
def mgmt_client(app_stack):
    """Руководство: только просмотр (stays.view, stays.guests)."""
    return _role_user(app_stack, "stays_mgmt", "mgmt_view")


@pytest.fixture()
def occupancy_client(app_stack):
    """Непрофильная служба: загрузка без данных гостей (stays.occupancy)."""
    return _role_user(app_stack, "stays_occupancy", "occupancy")


@pytest.fixture()
def today(monkeypatch):
    """«Сегодня» модуля шахматки: freeze() на будущие даты просрочил бы токен входа.

    Версии фонда, опубликованные тестом «в будущем» (make_category под подменённой датой),
    снимаются после теста: их правки (выведенные объекты, деления) действовали бы с их даты
    для всех следующих тестов, а версия «сегодня» под настоящей датой их бы уже не отменила."""
    import datetime as dt

    from app.core.db import SessionLocal
    from app.modules.stays.adapters.orm import FundVersion
    from app.modules.stays.application import allocation, fund_drafts, reservations

    with SessionLocal() as s:
        top = s.scalar(select(func.coalesce(func.max(FundVersion.id), 0)))

    def _set(iso: str) -> None:
        for mod in (reservations, allocation, fund_drafts):
            monkeypatch.setattr(mod, "local_date", lambda: dt.date.fromisoformat(iso), raising=False)
    yield _set
    monkeypatch.undo()
    with SessionLocal() as s:
        _drop_versions(s, list(s.scalars(select(FundVersion.id).where(FundVersion.id > top))))
        s.commit()


def _drop_versions(s, ids: list[int]) -> None:
    from sqlalchemy import delete, update

    from app.modules.stays.adapters.orm import (
        CategoryState,
        FundVersion,
        GroupState,
        UnitLineage,
        UnitState,
        UnitStateFlag,
    )

    if not ids:
        return
    s.execute(update(FundVersion).where(FundVersion.base_version_id.in_(ids)).values(base_version_id=None))
    s.execute(delete(UnitLineage).where(UnitLineage.version_id.in_(ids)))
    s.execute(delete(UnitStateFlag).where(UnitStateFlag.version_id.in_(ids)))
    s.execute(delete(UnitState).where(UnitState.version_id.in_(ids)))
    s.execute(update(GroupState).where(GroupState.version_id.in_(ids)).values(parent_id=None))
    s.execute(delete(GroupState).where(GroupState.version_id.in_(ids)))
    s.execute(delete(CategoryState).where(CategoryState.version_id.in_(ids)))
    s.execute(delete(FundVersion).where(FundVersion.id.in_(ids)))


class Demo:
    """Малый набор: категория, 5 объектов, 6 гостей с уникальными фамилиями, 4 брони."""

    def __init__(self, cat, guests, res):
        self.cat, self.guests, self.res = cat, guests, res
        self.surnames = {g["last_name"] for g in guests}


@pytest.fixture()
def demo_small(manager_role_client, manager_client):
    from .helpers import create_res, make_category, make_guest, uniq

    cat = make_category(manager_role_client, n_units=5)
    u = uniq()
    gs = [make_guest(manager_client, f"Фамилия{u}{i}", level=("vvip" if i == 0 else "vip" if i == 1 else "regular"))
          for i in range(6)]
    gid = manager_client.post("/api/stays/groups", json={"title": "Семья"}).json()["id"]
    res = [
        create_res(manager_client, cat, "2029-02-01", "2029-02-06", [(gs[0]["id"], "main", None, None),
                   (gs[2]["id"], "guest", None, None)], note=f"Заметка{u}", customer=f"Заказчик{u}"),
        create_res(manager_client, cat, "2029-02-03", "2029-02-08", [(gs[1]["id"], "main", None, None)],
                   group_id=gid),
        create_res(manager_client, cat, "2029-02-03", "2029-02-08", [(gs[3]["id"], "main", None, None)],
                   group_id=gid),
        create_res(manager_client, cat, "2029-02-02", "2029-02-04", [(gs[4]["id"], "main", "2029-02-02", "2029-02-03"),
                   (gs[5]["id"], "main", "2029-02-03", "2029-02-04")],
                   logistics=[{"kind": "flight", "date": "2029-02-02", "time": "07:40", "description": f"SU{u}"}]),
    ]
    return Demo(cat, gs, res)


@pytest.fixture(scope="session")
def big_fund(app_stack):
    """440 объектов и ~300 броней в одном месяце — для бюджетов SQL (без API: так быстрее)."""
    import datetime as dt
    from unittest import mock

    from app.core.db import SessionLocal
    from app.core.time import local_date
    from app.modules.stays.adapters.orm import CategoryState, Guest, Occupant, Reservation
    from app.modules.stays.application import fund_drafts as fd
    from app.modules.stays.application.allocation import run_allocation

    from .helpers import kind_id

    with SessionLocal() as s:
        if s.scalar(select(CategoryState.category_id).where(CategoryState.code == "BIGDLX")) is None:
            draft = fd.open_draft(s, local_date(), None, "big_fund")
            cat_ids = [fd.save_category(s, draft.rev, {"code": f"BIG{k}", "title": k, "kind_id": kind_id("room"),
                                                       "escorted": k == "VIL", "weight": 1}, None)
                       for k in ("DLX", "STE", "VIL")]
            for i in range(440):
                fd.save_unit(s, draft.rev, {"label": f"B{i:03d}", "category_id": cat_ids[i % 3],
                                            "floor": str(i // 40)}, None)
            with mock.patch.object(fd._allocation, "run_allocation", lambda db: None):
                fd.publish(s, None)                 # распределение — один раз, после броней
            base = dt.date(2029, 6, 1)
            for i in range(300):
                g = Guest(last_name=f"Большой{i}", search_text=f"большой{i}")
                ci = base + dt.timedelta(days=i % 25)
                r = Reservation(number=f"BIG{i}", check_in=ci, check_out=ci + dt.timedelta(days=2 + i % 4),
                                category_id=cat_ids[i % 3], search_text=f"big{i}")
                s.add_all([g, r])
                s.flush()
                s.add(Occupant(reservation_id=r.id, guest_id=g.id, date_from=r.check_in,
                               date_to=r.check_out, role="main"))
            run_allocation(s)
            s.commit()
    return {"first": "2029-06-01", "last": "2029-06-30"}


@pytest.fixture()
def names_client(app_stack):
    """Служба «с фамилиями»: только stays.view, без профилей гостей (уровень names, §8)."""
    from app.core.db import SessionLocal
    from app.core.identity import AccessGrant, Role

    with SessionLocal() as s:
        if s.get(Role, "stays_names") is None:
            s.add(Role(code="stays_names", title="Шахматка с фамилиями", rank=20, max_assignable_rank=-1,
                       builtin=False))
            s.add(AccessGrant(role="stays_names", permission="stays.view", effect="allow"))
            s.commit()
    return _role_user(app_stack, "stays_names_user", "stays_names")


@pytest.fixture()
def butlers(app_stack, manager_role_client):
    """Два демо-батлера (Иванов, Кузнецова) в списке «Сопровождают гостей» и их График на 14 дней."""
    import datetime as dt

    from app.core.db import SessionLocal
    from app.core.time import local_date
    from app.modules.employees.application.catalog import Employee
    from app.modules.timesheet.application.engine_common import engine_ports
    from app.modules.timesheet.application.roster import roster

    with SessionLocal() as s:
        ids = [s.scalar(select(Employee.id).where(Employee.full_name.like(f"{n}%"))) for n in ("Иванов", "Кузнецова")]
        for e in ids:
            assert manager_role_client.put(f"/api/stays/escorts/{e}", json={"active": True}).status_code == 200
        first = local_date() + dt.timedelta(days=1)
        last = first + dt.timedelta(days=13)
        duty = roster(ids, first, last, engine_ports(s))
    days = [first + dt.timedelta(days=i) for i in range(14)]
    return {"a": ids[0], "b": ids[1], "days": days,
            "on": lambda e, d: bool(duty.get((e, d)) and duty[(e, d)].on_shift)}


@pytest.fixture()
def assign_only_client(app_stack):
    """stays.assign и stays.view без права на правку Графика."""
    from app.core.db import SessionLocal
    from app.core.identity import AccessGrant, Role

    with SessionLocal() as s:
        if s.get(Role, "stays_assign") is None:
            s.add(Role(code="stays_assign", title="Назначения без Графика", rank=20, max_assignable_rank=-1,
                       builtin=False))
            s.add_all(AccessGrant(role="stays_assign", permission=p, effect="allow")
                      for p in ("stays.view", "stays.assign", "stays.guests"))
            s.commit()
    return _role_user(app_stack, "stays_assign_user", "stays_assign")


def assert_no_pd(obj, words: set[str], path: str = "") -> None:
    """Ни одна строка ответа (на любой глубине) не содержит слов из words (§8, «На что смотреть» №4)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert_no_pd(v, words, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            assert_no_pd(v, words, f"{path}[{i}]")
    elif isinstance(obj, str):
        hit = [w for w in words if w and w.lower() in obj.lower()]
        assert not hit, f"{path}: {obj!r} содержит {hit}"


@pytest.fixture()
def butler_client(app_stack):
    """Батлер Иванов (роль «сотрудник»): stays.mine и stays.edit_mine."""
    from tests.conftest import _login
    return _login(app_stack["app"], "ivanov")


@pytest.fixture()
def own_reservation(manager_role_client, manager_client, butlers):
    """Бронь, где Иванов ведёт гостей завтра, и чужая бронь (ведёт Кузнецова)."""
    import datetime as dt

    from .helpers import create_res, make_category, make_guest
    d = butlers["days"][0]
    cat = make_category(manager_role_client, n_units=2)
    mine_g, other_g = make_guest(manager_client, "Свойгость"), make_guest(manager_client, "Чужойгость")
    mine = create_res(manager_client, cat, d.isoformat(), (d + dt.timedelta(days=2)).isoformat(),
                      [(mine_g["id"], "main", None, None)], note="старое")
    other = create_res(manager_client, cat, d.isoformat(), (d + dt.timedelta(days=2)).isoformat(),
                       [(other_g["id"], "main", None, None)])
    for r, e in ((mine, butlers["a"]), (other, butlers["b"])):
        assert manager_client.put("/api/stays/coverage/day", json={"day": d.isoformat(), "reservation_id": r["id"],
                                                                   "employee_id": e}).status_code == 200
    return {"mine": mine, "other": other, "mine_guest": mine_g, "other_guest": other_g, "day": d}
