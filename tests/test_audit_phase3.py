"""Фаза 3 аудита (22.10.2026): расхождения интерфейса и API.

* UI-01 — «Стартовый банк часов» убран: движок v7.1 его не читал (EXP-BANK), а супервайзер,
  которому корректировка банка запрещена, это поле правил (EXP-SUPBANK). Присланное поле
  игнорируется, в ответе его нет;
* BUG-02 / BUG-03 — кары: см. тесты ниже.
"""
from __future__ import annotations

from sqlalchemy import select


def _employee(client, username: str = "ivanov") -> dict:
    return next(e for e in client.get("/api/employees").json() if e.get("username") == username)


def test_start_bank_field_is_gone(admin_client, manager_client, db):
    from app.modules.employees.application import Employee

    e = _employee(admin_client)
    before = db.scalar(select(Employee.balance_hours).where(Employee.id == e["id"]))
    body = {"full_name": e["full_name"], "position": e["position"],
            "schedule_group": e["schedule_group"], "hired_at": e.get("hired_at")}
    for client in (admin_client, manager_client):          # менеджмент и супервайзер
        r = client.put(f"/api/employees/{e['id']}", json=body | {"balance_hours": 999})
        assert r.status_code == 200, r.text
        assert "balance_hours" not in r.json()
    db.expire_all()
    assert db.scalar(select(Employee.balance_hours).where(Employee.id == e["id"])) == before


def test_give_does_not_bypass_maintenance(manager_client, db):
    """BUG-02 (EXP-GIVEMAINT): супервайзер не может снять кар с обслуживания, но «выдавал» его —
    кар становился «занят». Отключённый кар тоже выдавался."""
    from app.modules.cars.application.catalog import Car

    car = db.scalars(select(Car).where(Car.status == "free", Car.holder_user_id.is_(None))).first()
    emp_id = _employee(manager_client)["id"]
    try:
        for status, word in (("maintenance", "обслуживании"), ("disabled", "отключён")):
            car.status = status
            db.commit()
            r = manager_client.post(f"/api/cars/{car.id}/give", json={"employee_id": emp_id})
            assert r.status_code == 400 and word in r.json()["detail"], r.text
            db.expire_all()
            assert db.get(Car, car.id).status == status
    finally:
        car.status = "free"
        db.commit()


def test_who_returned_needs_issue_right(employee_client):
    """BUG-03 (решение владельца В-11): «кто вернул» за другого — только с правом cars.issue;
    свой возврат без этих полей работает как раньше."""
    from tests.test_cars import RETURN_FORM, _free_car

    held = (employee_client.get("/api/cars").json()["me"] or {}).get("held")
    if not held:
        held = _free_car(employee_client)["id"]
        r = employee_client.post(f"/api/cars/{held}/take", json={"ack_assigned": True})
        assert r.status_code == 200, r.text
    r = employee_client.post(f"/api/cars/{held}/return", data={**RETURN_FORM, "by_name": "Петров П. П."})
    assert r.status_code == 403, r.text
    r = employee_client.post(f"/api/cars/{held}/return", data=RETURN_FORM)
    assert r.status_code == 200, r.text
