"""API раздела «Электрокары»: парк, операции (взять, передать, выдать, вернуть), история.

Правила — в ``application/cars.py``; роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.media import UploadRef, max_upload_bytes, read_upload_streaming
from app.core.permissions import require_perm
from app.core.schemas import Ok

from ..application import cars
from .schemas import (
    AssignIn,
    CarEditIn,
    CarIn,
    CarOperationOut,
    CarOut,
    GiveIn,
    HandoverIn,
    HistoryOut,
    LocationAddedOut,
    LocationEditIn,
    LocationIn,
    LocationsOut,
    MetaOut,
    ParkOut,
    StatusIn,
    TakeIn,
)

router = APIRouter(prefix="/api/cars", tags=["cars"])


@router.get("/meta", response_model=MetaOut)
def meta(db: Session = Depends(get_db), principal: Principal = Depends(require_perm("cars.view"))):
    """Справочные словари для интерфейса и права пользователя."""
    return cars.meta(db, principal)


@router.delete("/locations/{loc_id}", response_model=Ok)
def location_delete(loc_id: int, db: Session = Depends(get_db),
                    principal: Principal = Depends(require_perm("cars.manage"))):
    cars.delete_location(db, principal, loc_id)
    return Ok()


@router.get("/locations", response_model=LocationsOut)
def locations(db: Session = Depends(get_db), principal: Principal = Depends(require_perm("cars.view"))):
    return {"locations": cars.list_locations(db, principal)}


@router.post("/locations", response_model=LocationAddedOut)
def location_add(payload: LocationIn, db: Session = Depends(get_db),
                 principal: Principal = Depends(require_perm("cars.manage"))):
    return cars.add_location(db, principal, payload.name)


@router.put("/locations/{loc_id}", response_model=Ok)
def location_update(loc_id: int, payload: LocationEditIn, db: Session = Depends(get_db),
                    principal: Principal = Depends(require_perm("cars.manage"))):
    cars.update_location(db, principal, loc_id, name=payload.name, active=payload.active)
    return Ok()


@router.get("", response_model=ParkOut)
def park(db: Session = Depends(get_db), principal: Principal = Depends(require_perm("cars.view"))):
    """Парк целиком (видно всем ролям)."""
    return cars.park(db, principal)


@router.post("", response_model=CarOut)
def car_add(payload: CarIn, db: Session = Depends(get_db),
            principal: Principal = Depends(require_perm("cars.manage"))):
    return cars.create_car(db, principal, payload.number, payload.location)


@router.put("/{car_id}", response_model=CarOut)
def car_edit(car_id: int, payload: CarEditIn, db: Session = Depends(get_db),
             principal: Principal = Depends(require_perm("cars.manage"))):
    return cars.edit_car(db, principal, car_id, payload.model_dump(exclude_none=True))


@router.get("/{car_id}/history", response_model=HistoryOut)
def car_history(car_id: int, limit: int = 200, db: Session = Depends(get_db),
                principal: Principal = Depends(require_perm("cars.view"))):
    """История кара: записи только добавляются."""
    return {"history": cars.car_history(db, car_id, limit)}


@router.post("/{car_id}/take", response_model=CarOperationOut)
def car_take(car_id: int, payload: TakeIn, db: Session = Depends(get_db),
             principal: Principal = Depends(require_perm("cars.use"))):
    return {"car": cars.take_car(db, principal, car_id, ack_assigned=payload.ack_assigned)}


@router.post("/{car_id}/handover", response_model=CarOperationOut)
def car_handover(car_id: int, payload: HandoverIn, db: Session = Depends(get_db),
                 principal: Principal = Depends(require_perm("cars.use"))):
    """Передать другому: внутренний — по id, внешний — по ФИО."""
    return {"car": cars.handover_car(db, principal, car_id, employee_id=payload.employee_id, name=payload.name,
                                     with_key=payload.with_key, comment=payload.comment)}


@router.post("/{car_id}/give", response_model=CarOperationOut)
def car_give(car_id: int, payload: GiveIn, db: Session = Depends(get_db),
             principal: Principal = Depends(require_perm("cars.issue"))):
    """Выдать кар сотруднику: внутренний — по id, внешний — по ФИО."""
    return {"car": cars.give_car(db, principal, car_id, employee_id=payload.employee_id, name=payload.name,
                                 with_key=payload.with_key)}


@router.post("/{car_id}/return", response_model=CarOperationOut)
def car_return(car_id: int,
               by_employee_id: Optional[int] = Form(None),
               by_name: str = Form(""),
               location: str = Form(""),
               charge: str = Form("full"),
               canopy: bool = Form(True),
               condition: str = Form("ok"),
               trash: bool = Form(False),
               clean: bool = Form(True),
               on_charge: bool = Form(False),
               key_returned: Optional[bool] = Form(None),
               comment: str = Form(""),
               file: Optional[UploadFile] = File(None),
               db: Session = Depends(get_db),
               principal: Principal = Depends(require_perm("cars.use"))):
    """Возврат кара (multipart): состояние и фото."""
    refs: list[UploadRef] = []
    try:
        if file is not None:
            ref = read_upload_streaming(file, max_upload_bytes(db))     # сразу на диск, не в память
            if ref.size:
                refs.append(ref)
            else:
                ref.discard()
        car = cars.return_car(db, principal, car_id, by_employee_id=by_employee_id, by_name=by_name,
                              location=location, charge=charge, canopy=canopy, condition=condition,
                              trash=trash, clean=clean, on_charge=on_charge, key_returned=key_returned,
                              comment=comment, photo_refs=refs)
    finally:
        for ref in refs:
            ref.discard()       # файл, не перенесённый в хранилище из-за ошибки
    return {"car": car}


@router.post("/{car_id}/assign", response_model=CarOperationOut)
def car_assign(car_id: int, payload: AssignIn, db: Session = Depends(get_db),
               principal: Principal = Depends(require_perm("cars.issue"))):
    """Закрепление кара за сотрудником — рекомендательное."""
    return {"car": cars.assign_employee(db, principal, car_id, payload.employee_id)}


@router.post("/{car_id}/status", response_model=CarOperationOut)
def car_set_status(car_id: int, payload: StatusIn, db: Session = Depends(get_db),
                   principal: Principal = Depends(require_perm("cars.issue"))):
    """Ручная смена статуса."""
    return {"car": cars.set_status(db, principal, car_id, payload.status, payload.note)}
