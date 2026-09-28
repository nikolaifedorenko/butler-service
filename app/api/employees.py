"""Сотрудники: карточка (табельный №, приём, экстренный контакт), история должностей,
переводы между блоками, деактивация и «полное удаление» без потери истории,
ограничения супервайзера, словарь смен."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..auth import Principal, audit, can_manage_user, current_principal, require_manager
from ..base_schedule import dump_pattern, validate_pattern
from ..db import get_db
from ..deps import local_date, slugify_username
from ..employment import close_period, open_period, periods_of
from ..groups import GROUP_META, group_choices as group_choices_list, normalize_group
from ..names import suggest_genitive
from ..models import (
    ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_SUPERVISOR, BankAdjustment, BlockAssignment,
    Car, Department, EmergencyContact, Employee, PositionHistory, ShiftType, Subdivision, User, utcnow,
)
from ..security import hash_password
from ..shiftrev import REV_FIELDS, add_revision, archive_shift, freeze_before_update
from ..timesheet import bank_as_of, recalc_range

router = APIRouter(prefix="/api", tags=["directory"])

DEFAULT_PASSWORD = "demo1234"


_CAR_UNSET = object()      # «кар не предзагружен» — отличается от «кара нет» (None)


def _emp_dict(e: Employee, with_user: bool = False, car=_CAR_UNSET) -> dict:
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
        "balance_hours": e.balance_hours, "active": e.active,
        "deleted": e.deleted_at is not None,
        "deleted_at": e.deleted_at.isoformat() if e.deleted_at else None,
    }
    if with_user:
        data["username"] = e.user.username if e.user else None
        data["role"] = e.user.role if e.user else None
    # закреплённый электрокар (для карточки сотрудника): берём из предзагруженной
    # карты (список сотрудников) или через ORM-связь — в сессии текущего запроса.
    # Раньше здесь открывалась ОТДЕЛЬНАЯ SessionLocal на каждого сотрудника:
    # чтение вне транзакции запроса + лишнее соединение на каждой строке списка.
    if car is _CAR_UNSET:
        car = e.assigned_car
    data["assigned_car_id"] = car.id if car else None
    data["assigned_car_number"] = car.number if car else ""
    return data


def cars_by_employee(db: Session, employee_ids: list[int]) -> dict[int, Car]:
    """Закреплённые кары одним запросом: {employee_id: Car}."""
    if not employee_ids:
        return {}
    return {c.assigned_to: c for c in db.scalars(
        select(Car).where(Car.assigned_to.in_(employee_ids)))}


def _guard_supervisor(principal: Principal, new_role: str, target_user: Optional[User]) -> None:
    """Супервайзер может управлять только обычными пользователями (employee).

    Правило одно на всё приложение и живёт в app/auth.py:can_manage_user —
    здесь лишь тонкая обёртка, чтобы не переписывать все места вызова.
    """
    can_manage_user(principal, target_user, new_role)


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
    balance_hours: float = 0.0
    username: Optional[str] = None
    password: Optional[str] = None
    role: str = ROLE_EMPLOYEE


def _parse_date(value: Optional[str]) -> Optional[dt.date]:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Дата должна быть в формате ГГГГ-ММ-ДД")


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


def _touch_position(db: Session, emp: Employee, new_position: str, since: dt.date) -> None:
    """Закрыть текущую запись истории должностей и открыть новую (повышение/понижение/перевод)."""
    if (emp.position or "") == (new_position or ""):
        return
    cur = db.scalar(select(PositionHistory).where(
        PositionHistory.employee_id == emp.id, PositionHistory.end_date.is_(None)))
    if cur:
        cur.end_date = since - dt.timedelta(days=1)
    db.add(PositionHistory(employee_id=emp.id, position=new_position, start_date=since, end_date=None))


def _coverage_start(emp: Employee) -> dt.date:
    return emp.hired_at or dt.date(2020, 1, 1)


def normalize_block_history(db: Session, emp: Employee) -> None:
    """Инвариант истории блоков: периоды не пересекаются, идут подряд,
    соседние периоды одной группы склеиваются. Чинит в т.ч. старые «рваные» истории."""
    recs = list(db.scalars(select(BlockAssignment).where(
        BlockAssignment.employee_id == emp.id).order_by(BlockAssignment.start_date)))
    if not recs:
        return
    result: list[BlockAssignment] = []
    for rec in recs:
        if result:
            last = result[-1]
            last_end = last.end_date
            if last_end is None or last_end >= rec.start_date:
                # последний открытый/перекрывающий период упирается в начало нового
                new_end = rec.start_date - dt.timedelta(days=1)
                if last_end is None or last_end > new_end:
                    if new_end < last.start_date:
                        db.delete(last)
                        result.pop()
                    else:
                        last.end_date = new_end
        if result:
            last = result[-1]
            if last.group == rec.group and last.end_date == rec.start_date - dt.timedelta(days=1):
                last.end_date = rec.end_date
                db.delete(rec)
                continue
            if last.group == rec.group and last.end_date is None:
                db.delete(rec)
                continue
        result.append(rec)
    db.flush()


def _touch_block(db: Session, emp: Employee, new_group: str, since: dt.date,
                 pattern_json: str = "") -> None:
    """
    Перевод между блоками с произвольной датой: история с даты перевода перезаписывается.
    Все периоды, начинающиеся не раньше `since`, заменяются новым открытым периодом;
    период, накрывающий `since`, обрезается по `since-1` (или склеивается, если группа та же).
    `pattern_json` — индивидуальный шаблон блока (выходные пятидневки, цикл 3/3 и т.п.).
    """
    new_group = normalize_group(new_group)
    if (normalize_group(emp.schedule_group) or "") == (new_group or ""):
        if pattern_json:
            cur = db.scalar(select(BlockAssignment).where(
                BlockAssignment.employee_id == emp.id, BlockAssignment.end_date.is_(None)
            ).order_by(BlockAssignment.start_date.desc()))
            if cur is not None:
                cur.pattern_json = pattern_json
                db.flush()
        return
    doomed = db.scalars(select(BlockAssignment).where(
        BlockAssignment.employee_id == emp.id, BlockAssignment.start_date >= since)).all()
    for rec in doomed:
        db.delete(rec)
    straddling = db.scalar(select(BlockAssignment).where(
        BlockAssignment.employee_id == emp.id,
        BlockAssignment.start_date < since,
        BlockAssignment.end_date.is_(None)))
    if straddling is not None:
        if normalize_group(straddling.group) == new_group:
            if pattern_json:
                straddling.pattern_json = pattern_json
                db.flush()
            return                      # он и так уже в этой группе с более ранней даты
        straddling.end_date = since - dt.timedelta(days=1)
    prev = db.scalar(select(BlockAssignment).where(
        BlockAssignment.employee_id == emp.id,
        BlockAssignment.start_date < since).order_by(BlockAssignment.start_date.desc()))
    if prev is not None and normalize_group(prev.group) == new_group \
            and prev.end_date == since - dt.timedelta(days=1):
        prev.end_date = None            # склеиваем с предыдущим периодом той же группы
        if pattern_json:
            prev.pattern_json = pattern_json
        db.flush()
        return
    if prev is not None and prev.end_date is None:
        prev.end_date = since - dt.timedelta(days=1)
    db.add(BlockAssignment(employee_id=emp.id, group=new_group, start_date=since, end_date=None,
                           pattern_json=pattern_json))
    db.flush()
    normalize_block_history(db, emp)


@router.get("/employees")
def list_employees(include_deleted: bool = False, principal: Principal = Depends(require_manager),
                   db: Session = Depends(get_db)):
    stmt = (select(Employee)
            .options(joinedload(Employee.department), joinedload(Employee.user),
                     selectinload(Employee.contacts))
            .order_by(Employee.active.desc(), Employee.schedule_group, Employee.full_name))
    if not include_deleted:
        stmt = stmt.where(Employee.deleted_at.is_(None))
    emps = db.scalars(stmt).all()
    cars = cars_by_employee(db, [e.id for e in emps])
    return [_emp_dict(e, with_user=True, car=cars.get(e.id)) for e in emps]


@router.get("/group-choices")
def group_choices(principal: Principal = Depends(require_manager)):
    """Блоки графика: Смена 1 / Смена 2 / Пятидневка / Другие смены.

    kind — какой шаблон задаётся при переводе сотрудника в блок:
    base (базовый цикл объекта), week5 (свои выходные), cycle (3/3, 1/3, «РРВВ»), manual."""
    return group_choices_list()


class SuggestGenitiveIn(BaseModel):
    full_name: str


@router.post("/employees/suggest-genitive")
def suggest_genitive_api(payload: SuggestGenitiveIn, principal: Principal = Depends(require_manager)):
    """Подсказка родительного падежа по ФИО («от Иванова Ивана Ивановича»).
    Результат — лишь предложение: в карточке его можно исправить вручную."""
    return {"genitive": suggest_genitive(payload.full_name.strip())}


@router.post("/employees")
def create_employee(payload: EmployeeIn, principal: Principal = Depends(require_manager),
                    db: Session = Depends(get_db)):
    _guard_supervisor(principal, payload.role, None)
    hired = _parse_date(payload.hired_at) or local_date()
    emp = Employee(
        full_name=payload.full_name.strip(), short_name=payload.short_name.strip(),
        full_name_genitive=payload.full_name_genitive.strip(),
        position=payload.position.strip(), phone=payload.phone.strip(),
        tab_number=payload.tab_number.strip(), hired_at=hired,
        emergency_name=payload.emergency_name.strip(), emergency_phone=payload.emergency_phone.strip(),
        telegram=payload.telegram.strip(), email=payload.email.strip(),
        nationality=payload.nationality.strip(), subdivision=payload.subdivision.strip(),
        department_id=payload.department_id,
        schedule_group=normalize_group(payload.schedule_group.strip()),
        group_color=payload.group_color,
        schedule_pattern="", balance_hours=payload.balance_hours,
    )
    db.add(emp)
    db.flush()

    if emp.position:
        db.add(PositionHistory(employee_id=emp.id, position=emp.position, start_date=hired, end_date=None))
    if emp.schedule_group:
        db.add(BlockAssignment(employee_id=emp.id, group=emp.schedule_group, start_date=hired,
                               end_date=None, pattern_json=""))
    open_period(db, emp, hired, note="приём на работу", user_id=principal.user.id)

    username = (payload.username or slugify_username(emp.full_name)).strip().lower()
    if db.scalar(select(User).where(User.username == username)):
        username = f"{username}{emp.id}"
    password = payload.password or DEFAULT_PASSWORD
    db.add(User(username=username, password_hash=hash_password(password),
                role=payload.role, employee_id=emp.id))
    _sync_contacts(db, emp, payload.contacts)
    audit(db, principal, "employee_create", f"employee:{emp.id}",
          {"full_name": emp.full_name, "username": username, "role": payload.role})
    db.commit()
    data = _emp_dict(emp, with_user=True)
    data["initial_password"] = password
    return data


@router.put("/employees/{employee_id}")
def update_employee(employee_id: int, payload: EmployeeIn,
                    principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    _guard_supervisor(principal, payload.role, emp.user)

    today = local_date()
    emp.full_name = payload.full_name.strip()
    emp.short_name = payload.short_name.strip()
    emp.full_name_genitive = payload.full_name_genitive.strip()
    emp.phone = payload.phone.strip()
    emp.tab_number = payload.tab_number.strip()
    emp.hired_at = _parse_date(payload.hired_at) or emp.hired_at
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
    emp.balance_hours = payload.balance_hours

    # должность и блок меняются с фиксацией даты (история / переводы)
    _touch_position(db, emp, payload.position.strip(), today)
    emp.position = payload.position.strip()
    new_group = normalize_group(payload.schedule_group.strip())
    _touch_block(db, emp, new_group, today)
    emp.schedule_group = new_group
    normalize_block_history(db, emp)
    if not periods_of(db, emp.id):
        open_period(db, emp, emp.hired_at or today, note="восстановлено при редактировании",
                    user_id=principal.user.id)

    if emp.user:
        emp.user.role = payload.role
        if payload.username and payload.username.strip().lower() != emp.user.username:
            new_username = payload.username.strip().lower()
            if db.scalar(select(User).where(User.username == new_username, User.id != emp.user.id)):
                raise HTTPException(status_code=409, detail="Такой логин уже занят")
            emp.user.username = new_username
        if payload.password:
            emp.user.password_hash = hash_password(payload.password)
    _sync_contacts(db, emp, payload.contacts)
    audit(db, principal, "employee_update", f"employee:{emp.id}", {"full_name": emp.full_name})
    db.commit()
    return _emp_dict(emp, with_user=True)


class DatedAction(BaseModel):
    date: Optional[str] = None
    position: str = ""
    group: str = ""
    # индивидуальный шаблон блока (Пятидневка — свои выходные; Другие смены — свой цикл):
    kind: str = ""                 # base | week5 | cycle | manual (пусто — по типу блока)
    shift_code: str = ""           # рабочая смена шаблона (DAY9, NIGHT12, SUTKI…)
    cycle: str = ""                # "3/3", "1/3", "custom:РРВВРВ"
    anchor: Optional[str] = None   # опорная дата цикла
    off_weekdays: list[int] = []   # выходные дни недели (0=пн … 6=вс) для пятидневки
    label: str = ""


def _build_pattern_json(payload: DatedAction) -> str:
    """Собрать и проверить индивидуальный шаблон блока из payload перевода."""
    group = normalize_group(payload.group.strip())
    kind = (payload.kind or GROUP_META.get(group, {}).get("kind") or "base").strip()
    if kind == "base":
        return ""
    pattern: dict = {"kind": kind}
    if payload.shift_code.strip():
        pattern["shift_code"] = payload.shift_code.strip()
    if kind == "week5":
        pattern["off_weekdays"] = sorted({int(d) % 7 for d in payload.off_weekdays})
    if kind == "cycle":
        pattern["cycle"] = (payload.cycle or "").strip() or "3/3"
        if payload.anchor:
            pattern["anchor"] = payload.anchor
    if payload.label.strip():
        pattern["label"] = payload.label.strip()
    try:
        label = validate_pattern(pattern)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not pattern.get("label"):
        pattern["label"] = label
    return dump_pattern(pattern)


@router.post("/employees/{employee_id}/position-change")
def position_change(employee_id: int, payload: DatedAction,
                    principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Перевод/повышение/понижение с произвольной даты."""
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    if not payload.position.strip():
        raise HTTPException(status_code=422, detail="Укажите новую должность")
    since = _parse_date(payload.date) or local_date()
    _touch_position(db, emp, payload.position.strip(), since)
    emp.position = payload.position.strip()
    audit(db, principal, "position_change", f"employee:{emp.id}",
          {"position": emp.position, "since": since.isoformat()})
    db.commit()
    return _emp_dict(emp)


@router.post("/employees/{employee_id}/block-change")
def block_change(employee_id: int, payload: DatedAction,
                 principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Перевод между блоками графика (Смена 1 ↔ Смена 2) с произвольной даты."""
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    if not payload.group.strip():
        raise HTTPException(status_code=422, detail="Укажите блок графика")
    since = _parse_date(payload.date) or local_date()
    group = normalize_group(payload.group.strip())
    pattern_json = _build_pattern_json(payload)
    _touch_block(db, emp, group, since, pattern_json=pattern_json)
    emp.schedule_group = group
    # цикл сотрудника для «Продолжить график»: из индивидуального шаблона
    if payload.kind == "cycle" or (pattern_json and '"kind": "cycle"' in pattern_json):
        emp.schedule_pattern = payload.cycle.strip() or "3/3"
        emp.schedule_anchor = _parse_date(payload.anchor) or since
    elif group == "Пятидневка":
        emp.schedule_pattern = emp.schedule_pattern or "5/2"
    audit(db, principal, "block_change", f"employee:{emp.id}",
          {"group": emp.schedule_group, "since": since.isoformat(), "pattern": pattern_json})
    db.commit()
    return _emp_dict(emp)


@router.post("/employees/{employee_id}/dismiss")
def dismiss_employee(employee_id: int, payload: DatedAction,
                     principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Увольнение (деактивация) с произвольной даты; история сохраняется."""
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    _guard_supervisor(principal, ROLE_EMPLOYEE, emp.user)
    since = _parse_date(payload.date) or local_date()
    emp.dismissed_at = since
    emp.active = False
    if emp.user:
        emp.user.is_active = False
    # При увольнении все закрепления электрокаров снимаются автоматически (ТЗ, ч.3)
    for car in db.scalars(select(Car).where(Car.assigned_to == emp.id)):
        car.assigned_to = None
        car.note = (car.note + "; " if car.note else "") + "закрепление снято: увольнение"
    close_period(db, emp, until=since, note="увольнение")
    audit(db, principal, "employee_dismiss", f"employee:{emp.id}",
          {"since": since.isoformat(), "note": "дата считается последним рабочим днём"})
    db.commit()
    return _emp_dict(emp, with_user=True)


class RehireIn(BaseModel):
    date: Optional[str] = None     # первый рабочий день после повторного приёма
    position: str = ""
    group: str = ""
    kind: str = ""
    shift_code: str = ""
    cycle: str = ""
    anchor: Optional[str] = None
    off_weekdays: list[int] = []
    label: str = ""


@router.post("/employees/{employee_id}/rehire")
def rehire_employee(employee_id: int, payload: RehireIn,
                    principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Повторный приём уволенного сотрудника с произвольной даты.

    В графике будут видны: смены ДО увольнения, неактивные дни между периодами
    и активные дни после повторного приёма. Вся прошлая история сохраняется."""
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    if emp.deleted_at:
        raise HTTPException(status_code=409,
                            detail="Сотрудник помечен удалённым — сначала восстановите запись")
    since = _parse_date(payload.date) or local_date()

    periods = periods_of(db, emp.id)
    last = periods[-1] if periods else None
    if last is not None and last.end_date is not None \
            and last.start_date <= since <= last.end_date + dt.timedelta(days=1):
        # дата приёма вплотную к увольнению (или раньше) — просто возобновляем период
        last.end_date = None
        last.note = (last.note + "; " if last.note else "") + f"повторный приём с {since.isoformat()}"
    else:
        open_period(db, emp, since, note="повторный приём", user_id=principal.user.id)

    emp.active = True
    emp.dismissed_at = None
    if emp.user:
        emp.user.is_active = True
    if payload.position.strip():
        _touch_position(db, emp, payload.position.strip(), since)
        emp.position = payload.position.strip()
    if payload.group.strip():
        act = DatedAction(date=since.isoformat(), group=payload.group, kind=payload.kind,
                          shift_code=payload.shift_code, cycle=payload.cycle,
                          anchor=payload.anchor, off_weekdays=payload.off_weekdays,
                          label=payload.label)
        group = normalize_group(act.group.strip())
        _touch_block(db, emp, group, since, pattern_json=_build_pattern_json(act))
        emp.schedule_group = group
    elif not db.scalar(select(BlockAssignment).where(
            BlockAssignment.employee_id == emp.id, BlockAssignment.end_date.is_(None))):
        _touch_block(db, emp, normalize_group(emp.schedule_group) or "Смена 1", since)

    audit(db, principal, "employee_rehire", f"employee:{emp.id}", {"since": since.isoformat()})
    db.flush()
    today = local_date()
    if since <= today:
        recalc_range(db, since, today, employee_ids=[emp.id], commit=False)
    db.commit()
    return _emp_dict(emp, with_user=True)


# ─────────────────── ручные корректировки банка часов ───────────────────
def _guard_bank(principal: Principal) -> None:
    if principal.role not in (ROLE_ADMIN, ROLE_MANAGER):
        raise HTTPException(status_code=403,
                            detail="Корректировать банк часов может только администратор или менеджер")


def _author_name(principal: Principal) -> str:
    if principal.employee:
        return principal.employee.display_name
    return principal.user.username


def _adjustment_dict(a: BankAdjustment) -> dict:
    return {"id": a.id, "hours": a.hours, "date": a.effective_date.isoformat(),
            "note": a.note or "", "author": a.author_name or "",
            "created_at": a.created_at.isoformat(timespec="minutes") if a.created_at else ""}


class BankAdjustIn(BaseModel):
    hours: float                   # со знаком: +4 добавить, -8 списать
    date: Optional[str] = None     # с какой даты учитывается (по умолчанию сегодня)
    note: str = ""                 # «почему» — обязательное пояснение


@router.post("/employees/{employee_id}/bank-adjust")
def bank_adjust(employee_id: int, payload: BankAdjustIn,
                principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Ручная корректировка банка часов (+/−) с автором, датой и причиной."""
    _guard_bank(principal)
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    hours = round(payload.hours, 2)
    if hours == 0:
        raise HTTPException(status_code=422, detail="Часы корректировки не могут быть нулевыми")
    if not payload.note.strip():
        raise HTTPException(status_code=422,
                            detail="Укажите причину корректировки — она попадёт в историю")
    eff = _parse_date(payload.date) or local_date()
    adj = BankAdjustment(employee_id=emp.id, hours=hours, effective_date=eff,
                         note=payload.note.strip(), author_id=principal.user.id,
                         author_name=_author_name(principal), created_at=utcnow())
    db.add(adj)
    audit(db, principal, "bank_adjust", f"employee:{emp.id}",
          {"hours": hours, "date": eff.isoformat(), "note": adj.note})
    db.commit()
    return {"ok": True, "adjustment": _adjustment_dict(adj),
            "bank_now": bank_as_of(db, emp, local_date())}


@router.get("/employees/{employee_id}/bank-adjustments")
def bank_adjustments(employee_id: int, principal: Principal = Depends(require_manager),
                     db: Session = Depends(get_db)):
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    items = db.scalars(select(BankAdjustment).where(
        BankAdjustment.employee_id == employee_id).order_by(
        BankAdjustment.effective_date.desc(), BankAdjustment.id.desc())).all()
    return {"items": [_adjustment_dict(a) for a in items],
            "bank_now": bank_as_of(db, emp, local_date()),
            "start_balance": emp.balance_hours}


@router.delete("/employees/{employee_id}/bank-adjustments/{adjustment_id}")
def bank_adjust_delete(employee_id: int, adjustment_id: int,
                       principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    _guard_bank(principal)
    adj = db.get(BankAdjustment, adjustment_id)
    if not adj or adj.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Корректировка не найдена")
    data = _adjustment_dict(adj)
    db.delete(adj)
    audit(db, principal, "bank_adjust_delete", f"employee:{employee_id}", data)
    db.commit()
    emp = db.get(Employee, employee_id)
    return {"ok": True, "bank_now": bank_as_of(db, emp, local_date()) if emp else 0.0}


@router.get("/employees/{employee_id}/history")
def employee_history(employee_id: int, principal: Principal = Depends(require_manager),
                     db: Session = Depends(get_db)):
    """История должностей и принадлежность к блокам графика с датами."""
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    pos = db.scalars(select(PositionHistory).where(PositionHistory.employee_id == employee_id)
                     .order_by(PositionHistory.start_date)).all()
    blocks = db.scalars(select(BlockAssignment).where(BlockAssignment.employee_id == employee_id)
                        .order_by(BlockAssignment.start_date)).all()
    periods = periods_of(db, emp.id)
    adjustments = db.scalars(select(BankAdjustment).where(
        BankAdjustment.employee_id == employee_id).order_by(
        BankAdjustment.effective_date.desc(), BankAdjustment.id.desc())).all()

    def _block_label(b: BlockAssignment) -> str:
        from ..base_schedule import parse_pattern
        pat = parse_pattern(b.pattern_json)
        if not pat:
            return ""
        try:
            return validate_pattern(pat)
        except ValueError:
            return ""

    return {
        "positions": [{"position": p.position, "start": p.start_date.isoformat(),
                       "end": p.end_date.isoformat() if p.end_date else None} for p in pos],
        "blocks": [{"group": normalize_group(b.group), "start": b.start_date.isoformat(),
                    "end": b.end_date.isoformat() if b.end_date else None,
                    "pattern_label": _block_label(b)} for b in blocks],
        "employment": [{"start": p.start_date.isoformat(),
                        "end": p.end_date.isoformat() if p.end_date else None,
                        "note": p.note or "", "current": p.end_date is None} for p in periods],
        "bank_adjustments": [_adjustment_dict(a) for a in adjustments],
        "bank_now": bank_as_of(db, emp, local_date()),
    }


@router.post("/employees/{employee_id}/deactivate")
def deactivate_employee(employee_id: int, principal: Principal = Depends(require_manager),
                        db: Session = Depends(get_db)):
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    _guard_supervisor(principal, ROLE_EMPLOYEE, emp.user)
    emp.active = not emp.active
    if emp.user:
        emp.user.is_active = emp.active
    audit(db, principal, "employee_deactivate" if not emp.active else "employee_activate",
          f"employee:{emp.id}")
    db.commit()
    return _emp_dict(emp, with_user=True)


@router.post("/employees/{employee_id}/delete")
def delete_employee(employee_id: int, principal: Principal = Depends(require_manager),
                    db: Session = Depends(get_db)):
    """«Полное удаление»: сотрудник исчезает из списков и графика, но ВСЯ история
    (табель, отметки, аудит) сохраняется — записи помечаются deleted_at."""
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    _guard_supervisor(principal, ROLE_EMPLOYEE, emp.user)
    if emp.deleted_at:
        raise HTTPException(status_code=409, detail="Сотрудник уже удалён")
    emp.deleted_at = local_date()
    emp.active = False
    if emp.user:
        emp.user.is_active = False
    audit(db, principal, "employee_delete", f"employee:{emp.id}",
          {"full_name": emp.full_name, "note": "данные истории сохранены"})
    db.commit()
    return _emp_dict(emp, with_user=True)


# ─────────────────────────────── подразделения ───────────────────────────────
@router.get("/departments")
def list_departments(principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    deps = db.scalars(select(Department).order_by(Department.name)).all()
    return [{"id": d.id, "name": d.name} for d in deps]


class DepartmentIn(BaseModel):
    name: str


@router.post("/departments")
def create_department(payload: DepartmentIn, principal: Principal = Depends(require_manager),
                      db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Название департамента не может быть пустым")
    if db.scalar(select(Department).where(Department.name == name)):
        raise HTTPException(status_code=409, detail=f"Департамент «{name}» уже есть")
    dep = Department(name=name)
    db.add(dep)
    audit(db, principal, "department_create", name)
    db.commit()
    return {"id": dep.id, "name": dep.name}


@router.put("/departments/{dep_id}")
def rename_department(dep_id: int, payload: DepartmentIn,
                      principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    dep = db.get(Department, dep_id)
    if not dep:
        raise HTTPException(status_code=404, detail="Департамент не найден")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Название департамента не может быть пустым")
    other = db.scalar(select(Department).where(Department.name == name, Department.id != dep_id))
    if other:
        raise HTTPException(status_code=409, detail=f"Департамент «{name}» уже есть")
    old = dep.name
    dep.name = name
    audit(db, principal, "department_rename", f"department:{dep_id}", {"before": old, "after": name})
    db.commit()
    return {"id": dep.id, "name": dep.name}


@router.delete("/departments/{dep_id}")
def delete_department(dep_id: int, principal: Principal = Depends(require_manager),
                      db: Session = Depends(get_db)):
    """Удалить департамент: у привязанных сотрудников поле очищается (история остаётся)."""
    dep = db.get(Department, dep_id)
    if not dep:
        raise HTTPException(status_code=404, detail="Департамент не найден")
    linked = db.scalars(select(Employee).where(Employee.department_id == dep_id)).all()
    for emp in linked:
        emp.department_id = None
    db.delete(dep)
    audit(db, principal, "department_delete", f"department:{dep_id}",
          {"name": dep.name, "unlinked_employees": len(linked)})
    db.commit()
    return {"ok": True, "unlinked_employees": len(linked)}


# ──────────────────────── службы/подразделения (справочник) ────────────────────────
@router.get("/subdivisions")
def list_subdivisions(principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    subs = db.scalars(select(Subdivision).order_by(Subdivision.name)).all()
    return [{"id": s.id, "name": s.name} for s in subs]


class SubdivisionIn(BaseModel):
    name: str


@router.post("/subdivisions")
def create_subdivision(payload: SubdivisionIn, principal: Principal = Depends(require_manager),
                       db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Название службы не может быть пустым")
    if db.scalar(select(Subdivision).where(Subdivision.name == name)):
        raise HTTPException(status_code=409, detail=f"Служба «{name}» уже есть")
    sub = Subdivision(name=name)
    db.add(sub)
    audit(db, principal, "subdivision_create", name)
    db.commit()
    return {"id": sub.id, "name": sub.name}


@router.put("/subdivisions/{sub_id}")
def rename_subdivision(sub_id: int, payload: SubdivisionIn,
                       principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Переименовать службу — у сотрудников значение обновляется следом."""
    sub = db.get(Subdivision, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Служба не найдена")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Название службы не может быть пустым")
    other = db.scalar(select(Subdivision).where(Subdivision.name == name, Subdivision.id != sub_id))
    if other:
        raise HTTPException(status_code=409, detail=f"Служба «{name}» уже есть")
    old = sub.name
    updated = 0
    for emp in db.scalars(select(Employee).where(Employee.subdivision == old)).all():
        emp.subdivision = name
        updated += 1
    sub.name = name
    audit(db, principal, "subdivision_rename", f"subdivision:{sub_id}",
          {"before": old, "after": name, "employees_updated": updated})
    db.commit()
    return {"id": sub.id, "name": sub.name, "employees_updated": updated}


@router.delete("/subdivisions/{sub_id}")
def delete_subdivision(sub_id: int, principal: Principal = Depends(require_manager),
                       db: Session = Depends(get_db)):
    """Удалить службу: у сотрудников, где она указана, поле очищается."""
    sub = db.get(Subdivision, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Служба не найдена")
    updated = 0
    for emp in db.scalars(select(Employee).where(Employee.subdivision == sub.name)).all():
        emp.subdivision = ""
        updated += 1
    db.delete(sub)
    audit(db, principal, "subdivision_delete", f"subdivision:{sub_id}",
          {"name": sub.name, "employees_cleared": updated})
    db.commit()
    return {"ok": True, "employees_cleared": updated}


# ──────────────────────────────── смены (словарь) ────────────────────────────────
def _shift_dict(s: ShiftType, revisions: int = 0) -> dict:
    return {
        "id": s.id, "code": s.code, "name": s.name, "display_code": s.display_code,
        "tzh_code": s.tzh_code, "kind": s.kind, "start_time": s.start_time, "end_time": s.end_time,
        "overnight": s.overnight, "color": s.color,
        "sort_order": s.sort_order, "is_working": s.is_working,
        "counts_as_worked": s.counts_as_worked, "is_default_off": s.is_default_off,
        "planned_hours": s.planned_hours, "active": s.active,
        "doc_type": s.doc_type or "", "deduct_from_bank": bool(s.deduct_from_bank),
        "punch_in_allowed": bool(s.punch_in_allowed), "punch_out_allowed": bool(s.punch_out_allowed),
        "archived": bool(s.archived_at) or not s.active,
        "archived_at": s.archived_at.isoformat() if s.archived_at else None,
        "revisions": revisions,
    }


@router.get("/shift-types")
def list_shift_types(include_archived: bool = False,
                     principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Словарь смен. Архивные (удалённые) скрыты: в прошлом они продолжают считаться,
    но в новых ячейках недоступны. include_archived=true — показать и их.
    Чтение — любому вошедшему (нужно батлерам для легенды графика), правки — менеджерам."""
    from ..models import ShiftRevision

    stmt = select(ShiftType).order_by(ShiftType.sort_order, ShiftType.id)
    if not include_archived:
        stmt = stmt.where(ShiftType.active.is_(True))
    types = db.scalars(stmt).all()
    counts: dict[int, int] = {}
    for rev in db.scalars(select(ShiftRevision).where(
            ShiftRevision.shift_type_id.in_([t.id for t in types]) if types else
            ShiftRevision.shift_type_id < 0)):
        counts[rev.shift_type_id] = counts.get(rev.shift_type_id, 0) + 1
    return [_shift_dict(t, counts.get(t.id, 0)) for t in types]


class ShiftTypeIn(BaseModel):
    code: str
    name: str
    short_code: str = ""        # единый код для сетки и табеля
    display_code: str = ""
    tzh_code: str = ""
    kind: str = "work"
    start_time: str = ""
    end_time: str = ""
    overnight: bool = False
    color: str = "#6b7280"
    sort_order: int = 100
    is_working: bool = True
    counts_as_worked: bool = True
    is_default_off: bool = False
    doc_type: str = ""              # какой документ печатаем по этому отсутствию
    deduct_from_bank: bool = False  # списывать часы из банка (выходной за часы, отпросился)
    punch_in_allowed: bool = True   # можно ли жать «Пришёл» во время этой смены/отсутствия
    punch_out_allowed: bool = True  # можно ли жать «Ушёл»
    effective_from: Optional[str] = None  # изменения вступают в силу с даты; прошлое не меняется


@router.post("/shift-types")
def create_shift_type(payload: ShiftTypeIn, principal: Principal = Depends(require_manager),
                      db: Session = Depends(get_db)):
    if db.scalar(select(ShiftType).where(ShiftType.code == payload.code)):
        raise HTTPException(status_code=409, detail="Такой код смены уже существует")
    data = payload.model_dump()
    if data.get("short_code"):
        data["display_code"] = data["tzh_code"] = data["short_code"]
    data.pop("short_code", None)
    data.pop("effective_from", None)
    st = ShiftType(**data)
    db.add(st)
    audit(db, principal, "shift_type_create", payload.code, payload.model_dump())
    db.commit()
    return _shift_dict(st)


@router.put("/shift-types/{type_id}")
def update_shift_type(type_id: int, payload: ShiftTypeIn,
                      principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Правка смены НЕ ломает прошлое: старые значения фиксируются ревизией,
    новые действуют с `effective_from` (по умолчанию — с сегодняшнего дня).
    Отработанные смены в прошлых месяцах считаются по прежним часам."""
    from ..models import ShiftRevision

    st = db.get(ShiftType, type_id)
    if not st:
        raise HTTPException(status_code=404, detail="Тип смены не найден")
    data = payload.model_dump()
    if data.get("short_code"):
        data["display_code"] = data["tzh_code"] = data["short_code"]
    data.pop("short_code", None)
    eff_raw = data.pop("effective_from", None)
    eff = _parse_date(eff_raw) or local_date()

    new_code = data.get("code") or st.code
    if new_code != st.code and db.scalar(select(ShiftType).where(
            ShiftType.code == new_code, ShiftType.id != st.id)):
        raise HTTPException(status_code=409, detail="Такой код смены уже существует")
    if st.is_default_off and not data.get("is_default_off", True):
        other = db.scalar(select(ShiftType).where(ShiftType.is_default_off.is_(True),
                                                  ShiftType.id != st.id))
        if other is None:
            raise HTTPException(status_code=409,
                                detail="Это единственная смена «выходной по умолчанию»: "
                                       "сначала отметьте признаком другую смену")

    changes = {f: (getattr(st, f), data[f]) for f in REV_FIELDS
               if f in data and getattr(st, f) != data[f]}
    if changes:
        # снимок прежних значений — они продолжат действовать для дат до `eff`
        freeze_before_update(db, st, eff)
        for k, v in data.items():
            setattr(st, k, v)
        add_revision(db, st, eff)
        audit(db, principal, "shift_type_update", st.code,
              {"changes": {k: [str(a), str(b)] for k, (a, b) in changes.items()},
               "effective_from": eff.isoformat()})
        db.flush()
        if eff <= local_date():
            # дни от даты вступления до сегодня пересчитываем по новым значениям
            recalc_range(db, eff, local_date(), commit=False)
    else:
        for k, v in data.items():
            setattr(st, k, v)
        audit(db, principal, "shift_type_update", st.code, payload.model_dump())
    db.commit()
    revisions = db.scalar(select(func.count(ShiftRevision.id)).where(
        ShiftRevision.shift_type_id == st.id)) or 0
    return _shift_dict(st, revisions)


@router.delete("/shift-types/{type_id}")
def delete_shift_type(type_id: int, principal: Principal = Depends(require_manager),
                      db: Session = Depends(get_db)):
    """«Удаление» смены из словаря = АРХИВАЦИЯ: прошлые графики и табели продолжают
    считаться по ней, но в новых ячейках она недоступна."""
    st = db.get(ShiftType, type_id)
    if not st:
        raise HTTPException(status_code=404, detail="Тип смены не найден")
    if st.archived_at or not st.active:
        raise HTTPException(status_code=409, detail="Смена уже в архиве")
    if st.is_default_off:
        raise HTTPException(status_code=409,
                            detail="Нельзя архивировать смену «выходной по умолчанию»: "
                                   "её использует базовый цикл. Сначала назначьте признак другой смене.")
    archive_shift(db, st)
    audit(db, principal, "shift_type_archive", st.code,
          {"note": "прошлые ячейки продолжают считаться по этой смене"})
    db.commit()
    return {"ok": True, "archived": True, "shift": _shift_dict(st)}


@router.post("/shift-types/{type_id}/restore")
def restore_shift_type(type_id: int, principal: Principal = Depends(require_manager),
                       db: Session = Depends(get_db)):
    """Вернуть смену из архива в словарь."""
    st = db.get(ShiftType, type_id)
    if not st:
        raise HTTPException(status_code=404, detail="Тип смены не найден")
    st.active = True
    st.archived_at = None
    audit(db, principal, "shift_type_restore", st.code)
    db.commit()
    return {"ok": True, "shift": _shift_dict(st)}


@router.get("/shift-types/{type_id}/revisions")
def shift_revisions(type_id: int, principal: Principal = Depends(require_manager),
                    db: Session = Depends(get_db)):
    """История значений смены: какие часы действовали в прошлом."""
    from ..models import ShiftRevision

    st = db.get(ShiftType, type_id)
    if not st:
        raise HTTPException(status_code=404, detail="Тип смены не найден")
    revs = db.scalars(select(ShiftRevision).where(
        ShiftRevision.shift_type_id == type_id).order_by(ShiftRevision.valid_from)).all()
    return {"current": _shift_dict(st),
            "revisions": [{"valid_from": r.valid_from.isoformat(),
                           **{f: getattr(r, f) for f in REV_FIELDS}} for r in revs]}
