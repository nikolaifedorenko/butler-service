"""API раздела «Сотрудники»: карточка, приём, переводы, увольнение, скрытие, справочники
департаментов и служб. Правила — в ``application/directory.py`` и ``application/lifecycle.py``."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.modules.people.application import group_choices as group_choices_list
from app.modules.people.application import suggest_genitive

from ..application import directory, lifecycle
from ..application.directory import DepartmentIn, EmployeeIn, SubdivisionIn
from .schemas import (
    DatedAction,
    DepartmentDeletedOut,
    EmployeeCreatedOut,
    EmployeeHistoryOut,
    EmployeeOut,
    EmployeeUserOut,
    GenitiveOut,
    NamedOut,
    RehireIn,
    SubdivisionDeletedOut,
    SubdivisionRenamedOut,
    SuggestGenitiveIn,
)

router = APIRouter(prefix="/api", tags=["directory"])
VIEW = require_perm("employees.view")
EDIT = require_perm("employees.edit")
DICTS = require_perm("settings.edit")


def _block(payload: DatedAction) -> lifecycle.BlockChange:
    return lifecycle.BlockChange(group=payload.group, kind=payload.kind, value=payload.value, cycle=payload.cycle,
                                 anchor=payload.anchor, off_weekdays=payload.off_weekdays, label=payload.label)


@router.get("/employees", response_model=list[EmployeeUserOut])
def list_employees(include_deleted: bool = False, principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    return directory.list_employees(db, include_deleted)


@router.get("/group-choices", response_model=list[dict[str, Any]])
def group_choices(principal: Principal = Depends(VIEW)):
    """Блоки графика и вид шаблона, который задаётся при переводе в блок."""
    return group_choices_list()


@router.post("/employees/suggest-genitive", response_model=GenitiveOut)
def suggest_genitive_api(payload: SuggestGenitiveIn, principal: Principal = Depends(VIEW)):
    """Подсказка родительного падежа ФИО; в карточке её можно исправить."""
    return {"genitive": suggest_genitive(payload.full_name.strip())}


@router.post("/employees", response_model=EmployeeCreatedOut)
def create_employee(payload: EmployeeIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Приём: сотрудник, учётная запись, должность, блок графика и период работы."""
    return directory.create_employee(db, principal, payload)


@router.put("/employees/{employee_id}", response_model=EmployeeUserOut)
def update_employee(employee_id: int, payload: EmployeeIn, principal: Principal = Depends(EDIT),
                    db: Session = Depends(get_db)):
    return directory.update_employee(db, principal, employee_id, payload)


@router.post("/employees/{employee_id}/position-change", response_model=EmployeeOut)
def position_change(employee_id: int, payload: DatedAction, principal: Principal = Depends(EDIT),
                    db: Session = Depends(get_db)):
    """Перевод на должность с произвольной даты."""
    return directory.employee_dict(lifecycle.position_change(db, principal, employee_id, payload.position, payload.date))


@router.post("/employees/{employee_id}/block-change", response_model=EmployeeOut)
def block_change(employee_id: int, payload: DatedAction, principal: Principal = Depends(EDIT),
                 db: Session = Depends(get_db)):
    """Перевод между блоками графика с произвольной даты."""
    return directory.employee_dict(lifecycle.block_change(db, principal, employee_id, _block(payload), payload.date))


@router.post("/employees/{employee_id}/dismiss", response_model=EmployeeUserOut)
def dismiss_employee(employee_id: int, payload: DatedAction, principal: Principal = Depends(EDIT),
                     db: Session = Depends(get_db)):
    """Увольнение с произвольной даты; история сохраняется."""
    return directory.employee_dict(lifecycle.dismiss(db, principal, employee_id, payload.date), with_user=True)


@router.post("/employees/{employee_id}/rehire", response_model=EmployeeUserOut)
def rehire_employee(employee_id: int, payload: RehireIn, principal: Principal = Depends(EDIT),
                    db: Session = Depends(get_db)):
    """Повторный приём уволенного с произвольной даты; прошлая история сохраняется."""
    block = _block(payload) if payload.group.strip() else None
    return directory.employee_dict(lifecycle.rehire(db, principal, employee_id, payload.date, payload.position, block),
                                   with_user=True)


@router.get("/employees/{employee_id}/history", response_model=EmployeeHistoryOut)
def employee_history(employee_id: int, principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    """История должностей, блоков графика и периодов работы."""
    return directory.employee_history(db, employee_id)


@router.post("/employees/{employee_id}/delete", response_model=EmployeeUserOut)
def delete_employee(employee_id: int, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Скрыть сотрудника из списков и графика; табель, отметки и аудит сохраняются."""
    return directory.delete_employee(db, principal, employee_id)


@router.get("/departments", response_model=list[NamedOut])
def list_departments(principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    return directory.list_departments(db)


@router.post("/departments", response_model=NamedOut)
def create_department(payload: DepartmentIn, principal: Principal = Depends(DICTS), db: Session = Depends(get_db)):
    return directory.create_department(db, principal, payload)


@router.put("/departments/{dep_id}", response_model=NamedOut)
def rename_department(dep_id: int, payload: DepartmentIn, principal: Principal = Depends(DICTS),
                      db: Session = Depends(get_db)):
    return directory.rename_department(db, principal, dep_id, payload)


@router.delete("/departments/{dep_id}", response_model=DepartmentDeletedOut)
def delete_department(dep_id: int, principal: Principal = Depends(DICTS), db: Session = Depends(get_db)):
    """Удалить департамент: у его сотрудников поле очищается."""
    return directory.delete_department(db, principal, dep_id)


@router.get("/subdivisions", response_model=list[NamedOut])
def list_subdivisions(principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    return directory.list_subdivisions(db)


@router.post("/subdivisions", response_model=NamedOut)
def create_subdivision(payload: SubdivisionIn, principal: Principal = Depends(DICTS), db: Session = Depends(get_db)):
    return directory.create_subdivision(db, principal, payload)


@router.put("/subdivisions/{sub_id}", response_model=SubdivisionRenamedOut)
def rename_subdivision(sub_id: int, payload: SubdivisionIn, principal: Principal = Depends(DICTS),
                       db: Session = Depends(get_db)):
    """Переименовать службу; у сотрудников значение обновляется следом."""
    return directory.rename_subdivision(db, principal, sub_id, payload)


@router.delete("/subdivisions/{sub_id}", response_model=SubdivisionDeletedOut)
def delete_subdivision(sub_id: int, principal: Principal = Depends(DICTS), db: Session = Depends(get_db)):
    """Удалить службу: у сотрудников, где она указана, поле очищается."""
    return directory.delete_subdivision(db, principal, sub_id)
