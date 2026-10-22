"""Жизненный цикл сотрудника: перевод, смена блока графика, увольнение, повторный приём.

Вынесено из app/api/employees.py по образцу app/cars.py + тонкого cars_api.py
(ADR-0006): роутер занимается только HTTP (права, DTO, статусы), обработка и
бизнес-правила — здесь. Сервис не знает про FastAPI: ошибки — исключения
core.errors (main.py маппит их в статусы, тело ответа {"detail": …} не
меняется); audit и commit — часть use-case'а. Данные передаются примитивами и
dataclass'ом BlockChange, а не pydantic-DTO из api-слоя — направление
зависимостей api → services (контракт import-linter).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.auth_guards import can_manage_user
from app.core.errors import Conflict, NotFound, Validation
from app.core.roles import ROLE_EMPLOYEE
from app.core.time import local_date
from app.modules.cars.application.catalog import Car
from app.modules.timesheet.application.base_schedule import dump_pattern, validate_pattern_label
from app.modules.timesheet.application.catalog import BlockAssignment

from ..adapters.orm import Employee, PositionHistory
from ..domain.groups import GROUP_META, normalize_group
from .employment import close_period, open_period, periods_of


@dataclass
class BlockChange:
    """Данные перевода блока графика (роутер собирает из DTO)."""

    group: str
    kind: str = ""
    value: str = ""               # значение рабочего дня («Я 10,75») — ключ CFG-WINDOWS
    shift_code: str = ""          # легаси-поле старых паттернов, не используется
    cycle: str = ""
    anchor: Optional[str] = None
    off_weekdays: list[int] = field(default_factory=list)
    label: str = ""


# ─────────────────────────── общие помощники ───────────────────────────
# (используются и оставшимися в employees.py create/update — импорт оттуда)

def parse_date(value: Optional[str]) -> Optional[dt.date]:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise Validation("Дата должна быть в формате ГГГГ-ММ-ДД")


def touch_position(db: Session, emp: Employee, new_position: str, since: dt.date) -> None:
    """Закрыть текущую запись истории должностей и открыть новую (повышение/понижение/перевод)."""
    if (emp.position or "") == (new_position or ""):
        return
    cur = db.scalar(select(PositionHistory).where(
        PositionHistory.employee_id == emp.id, PositionHistory.end_date.is_(None)))
    if cur:
        cur.end_date = since - dt.timedelta(days=1)
    db.add(PositionHistory(employee_id=emp.id, position=new_position, start_date=since, end_date=None))


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


def touch_block(db: Session, emp: Employee, new_group: str, since: dt.date,
                pattern_json: str = "") -> None:
    """
    Перевод между блоками с произвольной датой: история с даты перевода перезаписывается.
    Все периоды, начинающиеся не позже `since`, заменяются новым открытым периодом;
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


def build_pattern_json(data: BlockChange) -> str:
    """Собрать и проверить индивидуальный шаблон блока из данных перевода."""
    group = normalize_group(data.group.strip())
    kind = (data.kind or GROUP_META.get(group, {}).get("kind") or "base").strip()
    if kind == "base":
        return ""
    pattern: dict = {"kind": kind}
    if data.value.strip():
        pattern["value"] = data.value.strip()
    if kind == "week5":
        pattern["off_weekdays"] = sorted({int(d) % 7 for d in data.off_weekdays})
    if kind == "cycle":
        pattern["cycle"] = (data.cycle or "").strip() or "3/3"
        if data.anchor:
            pattern["anchor"] = data.anchor
    if data.label.strip():
        pattern["label"] = data.label.strip()
    try:
        label = validate_pattern_label(pattern)
    except ValueError as exc:
        raise Validation(str(exc))
    if not pattern.get("label"):
        pattern["label"] = label
    return dump_pattern(pattern)


# ─────────────────────────────── use-case'ы ───────────────────────────────

def position_change(db: Session, principal: Principal, employee_id: int,
                    position: str, date: Optional[str]) -> Employee:
    """Перевод/повышение/понижение с произвольной даты."""
    emp = db.get(Employee, employee_id)
    if not emp:
        raise NotFound("Сотрудник не найден")
    if not position.strip():
        raise Validation("Укажите новую должность")
    since = parse_date(date) or local_date()
    touch_position(db, emp, position.strip(), since)
    emp.position = position.strip()
    audit(db, principal, "position_change", f"employee:{emp.id}",
          {"position": emp.position, "since": since.isoformat()})
    db.flush()          # commit — у обработчика (ARCH-01): аудит в той же транзакции
    return emp


def block_change(db: Session, principal: Principal, employee_id: int,
                 data: BlockChange, date: Optional[str]) -> Employee:
    """Перевод между блоками графика (Смена 1 ↔ Смена 2) с произвольной даты."""
    emp = db.get(Employee, employee_id)
    if not emp:
        raise NotFound("Сотрудник не найден")
    if not data.group.strip():
        raise Validation("Укажите блок графика")
    since = parse_date(date) or local_date()
    group = normalize_group(data.group.strip())
    pattern_json = build_pattern_json(data)
    touch_block(db, emp, group, since, pattern_json=pattern_json)
    emp.schedule_group = group
    # цикл сотрудника для «Продолжить график»: из индивидуального шаблона
    if data.kind == "cycle" or (pattern_json and '"kind": "cycle"' in pattern_json):
        emp.schedule_pattern = data.cycle.strip() or "3/3"
        emp.schedule_anchor = parse_date(data.anchor) or since
    elif group == "Пятидневка":
        emp.schedule_pattern = emp.schedule_pattern or "5/2"
    audit(db, principal, "block_change", f"employee:{emp.id}",
          {"group": emp.schedule_group, "since": since.isoformat(), "pattern": pattern_json})
    db.flush()          # commit — у обработчика (ARCH-01): аудит в той же транзакции
    return emp


def dismiss(db: Session, principal: Principal, employee_id: int,
            date: Optional[str]) -> Employee:
    """Увольнение (деактивация) с произвольной даты; история сохраняется."""
    emp = db.get(Employee, employee_id)
    if not emp:
        raise NotFound("Сотрудник не найден")
    can_manage_user(principal, emp.user, ROLE_EMPLOYEE)
    since = parse_date(date) or local_date()
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
    db.flush()          # commit — у обработчика (ARCH-01): аудит в той же транзакции
    return emp


def rehire(db: Session, principal: Principal, employee_id: int, date: Optional[str],
           position: str, block: Optional[BlockChange]) -> Employee:
    """Повторный приём уволенного сотрудника с произвольной даты.

    В графике будут видны: смены ДО увольнения, неактивные дни между периодами
    и активные дни после повторного приёма. Вся прошлая история сохраняется."""
    emp = db.get(Employee, employee_id)
    if not emp:
        raise NotFound("Сотрудник не найден")
    if emp.deleted_at:
        raise Conflict("Сотрудник помечен удалённым — сначала восстановите запись")
    since = parse_date(date) or local_date()

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
    if position.strip():
        touch_position(db, emp, position.strip(), since)
        emp.position = position.strip()
    if block is not None:
        group = normalize_group(block.group.strip())
        touch_block(db, emp, group, since, pattern_json=build_pattern_json(block))
        emp.schedule_group = group
    elif not db.scalar(select(BlockAssignment).where(
            BlockAssignment.employee_id == emp.id, BlockAssignment.end_date.is_(None))):
        touch_block(db, emp, normalize_group(emp.schedule_group) or "Смена 1", since)

    audit(db, principal, "employee_rehire", f"employee:{emp.id}", {"since": since.isoformat()})
    db.flush()          # commit — у обработчика (ARCH-01): аудит в той же транзакции
    return emp
