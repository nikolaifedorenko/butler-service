"""Сотрудники: карточка, приём, правка, история, скрытие; справочники департаментов и служб.

Приём создаёт сотрудника, учётную запись, первую должность, блок графика и период работы
одной операцией. Должность и блок графика при правке карточки меняются с сегодняшней даты и
остаются в истории. Скрытый сотрудник исчезает из списков, его история сохраняется.
Переводы, увольнение и повторный приём с произвольной даты — в ``lifecycle.py``.
Каждая операция — одна транзакция вместе с записью аудита.
"""
from __future__ import annotations

import secrets
import string
from typing import Optional

from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, object_session, selectinload

from app.core.audit import audit
from app.core.auth import Principal
from app.core.auth_guards import can_manage_user
from app.core.db import transactional
from app.core.errors import Conflict, NotFound, Validation
from app.core.format import normalize_hex_color
from app.core.identity import User
from app.core.roles import ROLE_EMPLOYEE
from app.core.security import MIN_PASSWORD_LEN, hash_password
from app.core.sessions import revoke_user_sessions
from app.core.time import local_date
from app.modules.cars.application.catalog import Car
from app.modules.people.application import (
    Department,
    EmergencyContact,
    Employee,
    PositionHistory,
    Subdivision,
    normalize_group,
    open_period,
    periods_of,
    slugify_username,
    suggest_genitive,
)
from app.modules.timesheet.application import employee_card
from app.modules.timesheet.application.catalog import BlockAssignment

from .lifecycle import normalize_block_history, parse_date, touch_block, touch_position

# Символы начального пароля: латиница и цифры без визуально похожих (0 и O, 1, l и I) —
# такой пароль легко продиктовать.
_LOOKALIKE = set("lo" "IO" "01")
_INITIAL_CHARS = "".join(c for c in string.ascii_lowercase + string.ascii_uppercase + string.digits
                         if c not in _LOOKALIKE)


def _check_password(password: Optional[str]) -> None:
    """Пароль, который задаёт руководитель, — по тому же правилу, что смена своего."""
    if password and len(password) < MIN_PASSWORD_LEN:
        raise Validation(f"Пароль слишком короткий (минимум {MIN_PASSWORD_LEN} символов)")


def _initial_password() -> str:
    """Случайный пароль новой учётной записи: показывается один раз — в ответе на приём."""
    return "".join(secrets.choice(_INITIAL_CHARS) for _ in range(12))


_CAR_UNSET = object()      # «кар не предзагружен» — отличается от «кара нет» (None)


def employee_dict(e: Employee, with_user: bool = False, car=_CAR_UNSET) -> dict:
    data = {
        "id": e.id, "full_name": e.full_name, "short_name": e.short_name or e.display_name,
        "full_name_genitive": e.full_name_genitive or "",
        "full_name_genitive_hint": e.full_name_genitive or suggest_genitive(e.full_name),
        "position": e.position, "phone": e.phone,
        "tab_number": e.tab_number or "",
        "hired_at": e.hired_at.isoformat() if e.hired_at else None,
        "emergency_name": e.emergency_name or "", "emergency_phone": e.emergency_phone or "",
        "telegram": e.telegram or "", "email": e.email or "",
        "dismissed_at": e.dismissed_at.isoformat() if e.dismissed_at else None,
        "contacts": [{"id": c.id, "name": c.name, "phone": c.phone, "relation": c.relation}
                     for c in e.contacts] if hasattr(e, "contacts") else [],
        "department_id": e.department_id,
        "department": e.department.name if e.department else None,
        "nationality": e.nationality or "",
        "subdivision": e.subdivision or "",
        "schedule_group": e.schedule_group or "", "group_color": e.group_color or "#8a94a6",
        "schedule_pattern": e.schedule_pattern or "",
        "active": e.active,
        "deleted": e.deleted_at is not None,
        "deleted_at": e.deleted_at.isoformat() if e.deleted_at else None,
    }
    if with_user:
        data["username"] = e.user.username if e.user else None
        data["role"] = e.user.role if e.user else None
    # закреплённый электрокар: из предзагруженной карты (список сотрудников) или одним запросом
    if car is _CAR_UNSET:
        sess = object_session(e)
        car = sess.scalar(select(Car).where(Car.assigned_to == e.id)) if sess is not None else None
    data["assigned_car_id"] = car.id if car else None
    data["assigned_car_number"] = car.number if car else ""
    return data


def cars_by_employee(db: Session, employee_ids: list[int]) -> dict[int, Car]:
    """Закреплённые кары одним запросом: {employee_id: Car}."""
    if not employee_ids:
        return {}
    return {c.assigned_to: c for c in db.scalars(
        select(Car).where(Car.assigned_to.in_(employee_ids)))}


def _guard_supervisor(db: Session, principal: Principal, new_role: str,
                      target_user: Optional[User]) -> None:
    can_manage_user(db, principal, target_user, new_role)


class ContactIn(BaseModel):
    name: str
    phone: str = ""
    relation: str = ""


class EmployeeIn(BaseModel):
    full_name: str
    short_name: str = ""
    full_name_genitive: str = ""
    position: str = ""
    phone: str = ""
    tab_number: str = ""
    hired_at: Optional[str] = None          # YYYY-MM-DD
    emergency_name: str = ""
    emergency_phone: str = ""
    telegram: str = ""
    email: str = ""
    contacts: list[ContactIn] = []
    department_id: Optional[int] = None
    nationality: str = ""          # гражданство — для документов
    subdivision: str = ""          # служба/подразделение в официальных документах
    schedule_group: str = ""
    group_color: str = "#8a94a6"
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None     # не передана — при правке роль не меняется

    @field_validator("group_color", mode="before")
    @classmethod
    def _valid_group_color(cls, v):
        return normalize_hex_color(v, "#8a94a6")


def _sync_contacts(db: Session, emp: Employee, contacts: list[ContactIn]) -> None:
    for c in list(emp.contacts):
        db.delete(c)
    db.flush()
    for c in contacts:
        if c.name.strip():
            obj = EmergencyContact(employee_id=emp.id, name=c.name.strip(),
                                   phone=c.phone.strip(), relation=c.relation.strip())
            db.add(obj)
            emp.contacts.append(obj)


def list_employees(db: Session, include_deleted: bool = False) -> list[dict]:
    """Сотрудники с учётной записью и закреплённым каром; скрытые — только по запросу."""
    stmt = (select(Employee)
            .options(joinedload(Employee.department), joinedload(Employee.user),
                     selectinload(Employee.contacts))
            .order_by(Employee.active.desc(), Employee.schedule_group, Employee.full_name))
    if not include_deleted:
        stmt = stmt.where(Employee.deleted_at.is_(None))
    emps = db.scalars(stmt).all()
    cars = cars_by_employee(db, [e.id for e in emps])
    return [employee_dict(e, with_user=True, car=cars.get(e.id)) for e in emps]


@transactional
def create_employee(db: Session, principal: Principal, payload: EmployeeIn) -> dict:
    role = payload.role or ROLE_EMPLOYEE
    _guard_supervisor(db, principal, role, None)
    _check_password(payload.password)
    hired = parse_date(payload.hired_at) or local_date()
    department_id = None
    if payload.department_id:
        dep = db.get(Department, payload.department_id)
        if dep is None:
            raise Validation("Департамент не найден")
        department_id = dep.id
    emp = Employee(
        full_name=payload.full_name.strip(), short_name=payload.short_name.strip(),
        full_name_genitive=payload.full_name_genitive.strip(),
        position=payload.position.strip(), phone=payload.phone.strip(),
        tab_number=payload.tab_number.strip(), hired_at=hired,
        emergency_name=payload.emergency_name.strip(), emergency_phone=payload.emergency_phone.strip(),
        telegram=payload.telegram.strip(), email=payload.email.strip(),
        nationality=payload.nationality.strip(), subdivision=payload.subdivision.strip(),
        department_id=department_id,
        schedule_group=normalize_group(payload.schedule_group.strip()),
        group_color=payload.group_color,
        schedule_pattern="",
    )
    db.add(emp)
    db.flush()

    if emp.position:
        db.add(PositionHistory(employee_id=emp.id, position=emp.position, start_date=hired, end_date=None))
    if emp.schedule_group:
        db.add(BlockAssignment(employee_id=emp.id, group=emp.schedule_group, start_date=hired,
                               end_date=None, pattern={}))
    open_period(db, emp, hired, note="приём на работу", user_id=principal.user.id)

    username = (payload.username or slugify_username(emp.full_name)).strip().lower()
    if db.scalar(select(User).where(User.username == username)):
        username = f"{username}{emp.id}"
    password = payload.password or _initial_password()
    db.add(User(username=username, password_hash=hash_password(password),
                role=role, employee_id=emp.id))
    _sync_contacts(db, emp, payload.contacts)
    audit(db, principal, "employee_create", f"employee:{emp.id}",
          {"full_name": emp.full_name, "username": username, "role": role})
    db.flush()
    data = employee_dict(emp, with_user=True)
    # пароль в ответе — только сгенерированный (его больше нигде не узнать); введённый
    # администратором он и так знает — не гоняем его по сети и не показываем на экране
    data["initial_password"] = None if payload.password else password
    return data


@transactional
def update_employee(db: Session, principal: Principal, employee_id: int, payload: EmployeeIn) -> dict:
    emp = db.get(Employee, employee_id)
    if not emp:
        raise NotFound("Сотрудник не найден")
    _guard_supervisor(db, principal, payload.role, emp.user)
    _check_password(payload.password)
    changes: dict = {}

    today = local_date()
    emp.full_name = payload.full_name.strip()
    emp.short_name = payload.short_name.strip()
    emp.full_name_genitive = payload.full_name_genitive.strip()
    emp.phone = payload.phone.strip()
    emp.tab_number = payload.tab_number.strip()
    emp.hired_at = parse_date(payload.hired_at) or emp.hired_at
    emp.emergency_name = payload.emergency_name.strip()
    emp.emergency_phone = payload.emergency_phone.strip()
    emp.telegram = payload.telegram.strip()
    emp.email = payload.email.strip()
    emp.nationality = payload.nationality.strip()
    emp.subdivision = payload.subdivision.strip()
    if payload.department_id:
        dep = db.get(Department, payload.department_id)
        emp.department_id = dep.id if dep else None
    else:
        emp.department_id = None
    emp.group_color = payload.group_color

    # должность и блок меняются с фиксацией даты (история / переводы)
    touch_position(db, emp, payload.position.strip(), today)
    emp.position = payload.position.strip()
    new_group = normalize_group(payload.schedule_group.strip())
    touch_block(db, emp, new_group, today)
    emp.schedule_group = new_group
    normalize_block_history(db, emp)
    if not periods_of(db, emp.id):
        open_period(db, emp, emp.hired_at or today, note="восстановлено при редактировании",
                    user_id=principal.user.id)

    if emp.user:
        if payload.role and payload.role != emp.user.role:
            changes["role"] = [emp.user.role, payload.role]
            emp.user.role = payload.role
        if payload.username and payload.username.strip().lower() != emp.user.username:
            new_username = payload.username.strip().lower()
            if db.scalar(select(User).where(User.username == new_username, User.id != emp.user.id)):
                raise Conflict("Такой логин уже занят")
            changes["username"] = [emp.user.username, new_username]
            emp.user.username = new_username
        if payload.password:
            emp.user.password_hash = hash_password(payload.password)
            changes["password_changed"] = True
        if "role" in changes or "password_changed" in changes:
            # прежние сессии (в том числе украденная cookie) больше не действуют
            revoke_user_sessions(db, emp.user.id)
    _sync_contacts(db, emp, payload.contacts)
    audit(db, principal, "employee_update", f"employee:{emp.id}", {"full_name": emp.full_name, **changes})
    db.flush()
    return employee_dict(emp, with_user=True)


def employee_history(db: Session, employee_id: int) -> dict:
    """История должностей и принадлежность к блокам графика с датами."""
    emp = db.get(Employee, employee_id)
    if not emp:
        raise NotFound("Сотрудник не найден")
    pos = db.scalars(select(PositionHistory).where(PositionHistory.employee_id == employee_id)
                     .order_by(PositionHistory.start_date)).all()
    periods = periods_of(db, emp.id)
    card = employee_card.history(db, emp)
    return {
        "positions": [{"position": p.position, "start": p.start_date.isoformat(),
                       "end": p.end_date.isoformat() if p.end_date else None} for p in pos],
        "blocks": [{**b, "group": normalize_group(b["group"])} for b in card["blocks"]],
        "current_value": card["current_value"],
        "employment": [{"start": p.start_date.isoformat(),
                        "end": p.end_date.isoformat() if p.end_date else None,
                        "note": p.note or "", "current": p.end_date is None} for p in periods],
        "bank_adjustments": card["bank_adjustments"],
        "bank_now": card["bank_now"],
    }


@transactional
def delete_employee(db: Session, principal: Principal, employee_id: int) -> dict:
    """«Полное удаление»: сотрудник исчезает из списков и графика, но ВСЯ история
    (табель, отметки, аудит) сохраняется — записи помечаются deleted_at."""
    emp = db.get(Employee, employee_id)
    if not emp:
        raise NotFound("Сотрудник не найден")
    _guard_supervisor(db, principal, ROLE_EMPLOYEE, emp.user)
    if emp.deleted_at:
        raise Conflict("Сотрудник уже удалён")
    emp.deleted_at = local_date()
    emp.active = False
    if emp.user:
        emp.user.is_active = False
        revoke_user_sessions(db, emp.user.id)   # сессии завершаются
    audit(db, principal, "employee_delete", f"employee:{emp.id}",
          {"full_name": emp.full_name, "note": "данные истории сохранены"})
    return employee_dict(emp, with_user=True)


# ─────────────────────────────── подразделения ───────────────────────────────
def list_departments(db: Session) -> list[dict]:
    deps = db.scalars(select(Department).order_by(Department.name)).all()
    return [{"id": d.id, "name": d.name} for d in deps]


class DepartmentIn(BaseModel):
    name: str


@transactional
def create_department(db: Session, principal: Principal, payload: DepartmentIn) -> dict:
    name = payload.name.strip()
    if not name:
        raise Validation("Название департамента не может быть пустым")
    if db.scalar(select(Department).where(Department.name == name)):
        raise Conflict(f"Департамент «{name}» уже есть")
    dep = Department(name=name)
    db.add(dep)
    audit(db, principal, "department_create", name)
    db.flush()
    return {"id": dep.id, "name": dep.name}


@transactional
def rename_department(db: Session, principal: Principal, dep_id: int, payload: DepartmentIn) -> dict:
    dep = db.get(Department, dep_id)
    if not dep:
        raise NotFound("Департамент не найден")
    name = payload.name.strip()
    if not name:
        raise Validation("Название департамента не может быть пустым")
    other = db.scalar(select(Department).where(Department.name == name, Department.id != dep_id))
    if other:
        raise Conflict(f"Департамент «{name}» уже есть")
    old = dep.name
    dep.name = name
    audit(db, principal, "department_rename", f"department:{dep_id}", {"before": old, "after": name})
    return {"id": dep.id, "name": dep.name}


@transactional
def delete_department(db: Session, principal: Principal, dep_id: int) -> dict:
    """Удалить департамент: у привязанных сотрудников поле очищается (история остаётся)."""
    dep = db.get(Department, dep_id)
    if not dep:
        raise NotFound("Департамент не найден")
    linked = db.scalars(select(Employee).where(Employee.department_id == dep_id)).all()
    for emp in linked:
        emp.department_id = None
    db.delete(dep)
    audit(db, principal, "department_delete", f"department:{dep_id}",
          {"name": dep.name, "unlinked_employees": len(linked)})
    return {"ok": True, "unlinked_employees": len(linked)}


# ──────────────────────── службы/подразделения (справочник) ────────────────────────
def list_subdivisions(db: Session) -> list[dict]:
    subs = db.scalars(select(Subdivision).order_by(Subdivision.name)).all()
    return [{"id": s.id, "name": s.name} for s in subs]


class SubdivisionIn(BaseModel):
    name: str


@transactional
def create_subdivision(db: Session, principal: Principal, payload: SubdivisionIn) -> dict:
    name = payload.name.strip()
    if not name:
        raise Validation("Название службы не может быть пустым")
    if db.scalar(select(Subdivision).where(Subdivision.name == name)):
        raise Conflict(f"Служба «{name}» уже есть")
    sub = Subdivision(name=name)
    db.add(sub)
    audit(db, principal, "subdivision_create", name)
    db.flush()
    return {"id": sub.id, "name": sub.name}


@transactional
def rename_subdivision(db: Session, principal: Principal, sub_id: int, payload: SubdivisionIn) -> dict:
    """Переименовать службу — у сотрудников значение обновляется следом."""
    sub = db.get(Subdivision, sub_id)
    if not sub:
        raise NotFound("Служба не найдена")
    name = payload.name.strip()
    if not name:
        raise Validation("Название службы не может быть пустым")
    other = db.scalar(select(Subdivision).where(Subdivision.name == name, Subdivision.id != sub_id))
    if other:
        raise Conflict(f"Служба «{name}» уже есть")
    old = sub.name
    updated = 0
    for emp in db.scalars(select(Employee).where(Employee.subdivision == old)).all():
        emp.subdivision = name
        updated += 1
    sub.name = name
    audit(db, principal, "subdivision_rename", f"subdivision:{sub_id}",
          {"before": old, "after": name, "employees_updated": updated})
    return {"id": sub.id, "name": sub.name, "employees_updated": updated}


@transactional
def delete_subdivision(db: Session, principal: Principal, sub_id: int) -> dict:
    """Удалить службу: у сотрудников, где она указана, поле очищается."""
    sub = db.get(Subdivision, sub_id)
    if not sub:
        raise NotFound("Служба не найдена")
    updated = 0
    for emp in db.scalars(select(Employee).where(Employee.subdivision == sub.name)).all():
        emp.subdivision = ""
        updated += 1
    db.delete(sub)
    audit(db, principal, "subdivision_delete", f"subdivision:{sub_id}",
          {"name": sub.name, "employees_cleared": updated})
    return {"ok": True, "employees_cleared": updated}
