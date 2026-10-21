"""Кары при параллельных запросах (аудит 21.10.2026, CONC-01, EXP-CARRACE).

Два телефона жмут «Взять» на одном каре: оба прочитали «свободен» до коммита соседа.
Раньше оба запроса проходили (две записи «take», держатель — последний). Демо-данные
общие на прогон — состояние каров восстанавливаем, журнал истории не трогаем.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import select

_STATE = ("status", "holder_user_id", "holder_name", "has_key", "on_charge", "last_taken_at")


@contextmanager
def _restore(SessionLocal, *car_ids):
    from app.modules.cars.application.catalog import Car

    with SessionLocal() as s:
        saved = {cid: {f: getattr(s.get(Car, cid), f) for f in _STATE} for cid in car_ids}
    try:
        yield
    finally:
        with SessionLocal() as s:
            for cid, fields in saved.items():
                for f, v in fields.items():
                    setattr(s.get(Car, cid), f, v)
            s.commit()


def _free_cars_and_users(db, n_cars):
    from app.core.auth import Principal
    from app.core.identity import User
    from app.modules.cars.application.catalog import Car
    from app.modules.employees.adapters.orm import Employee

    cars = db.scalars(select(Car).where(Car.status == "free", Car.assigned_to.is_(None))
                      .order_by(Car.id)).all()[:n_cars]
    busy = set(db.scalars(select(Car.holder_user_id).where(Car.holder_user_id.is_not(None))))
    users = [u for u in db.scalars(select(User).where(User.employee_id.is_not(None),
                                                      User.role == "employee").order_by(User.id))
             if u.id not in busy][:2]
    assert len(cars) == n_cars and len(users) == 2, "в демо-данных нет свободных каров/сотрудников"
    return [c.id for c in cars], [u.id for u in users], Principal, User, Employee


def test_two_takes_of_one_car_second_gets_conflict(app_stack, db):
    from app.modules.cars.application.cars import CarConflict, take_car
    from app.modules.cars.application.catalog import Car, CarHistory
    from app.modules.cars.interface.cars_api import _err

    SessionLocal = app_stack["SessionLocal"]
    (car_id,), (uid1, uid2), Principal, User, Employee = _free_cars_and_users(db, 1)
    takes_before = len(db.scalars(select(CarHistory).where(
        CarHistory.car_id == car_id, CarHistory.action == "take")).all())

    with _restore(SessionLocal, car_id):
        s1, s2 = SessionLocal(), SessionLocal()
        try:
            u1, u2 = s1.get(User, uid1), s2.get(User, uid2)
            p1 = Principal(u1, s1.get(Employee, u1.employee_id))
            p2 = Principal(u2, s2.get(Employee, u2.employee_id))
            c1, c2 = s1.get(Car, car_id), s2.get(Car, car_id)
            assert c1.status == c2.status == "free"          # оба прочитали до коммита соседа
            take_car(s1, c1, p1)
            s1.commit()
            with pytest.raises(CarConflict) as exc:
                take_car(s2, c2, p2)
            s2.rollback()
            assert _err(exc.value).status_code == 409
        finally:
            s1.close()
            s2.close()

        with SessionLocal() as s:
            car = s.get(Car, car_id)
            assert car.holder_user_id == uid1
            takes = s.scalars(select(CarHistory).where(
                CarHistory.car_id == car_id, CarHistory.action == "take")).all()
            assert len(takes) == takes_before + 1


def test_second_car_for_same_holder_is_rejected_by_index(app_stack, db):
    """Проверка «у вас уже есть кар» читает базу; параллельный запрос мог дать человеку
    второй кар между проверкой и записью — это ловит частичный unique-индекс."""
    from app.modules.cars.application.cars import CarConflict, add_history
    from app.modules.cars.application.catalog import Car

    SessionLocal = app_stack["SessionLocal"]
    (a, b), (uid, _), *_ = _free_cars_and_users(db, 2)
    with _restore(SessionLocal, a, b):
        with SessionLocal() as s:
            s.get(Car, a).holder_user_id = uid
            s.commit()
        with SessionLocal() as s:
            car = s.get(Car, b)
            car.holder_user_id = uid
            with pytest.raises(CarConflict):
                add_history(s, car, "give", None)
            s.rollback()
