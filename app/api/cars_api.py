"""API справочника «Электрокары»: парк, операции (Взял/Передать/Вернул), история.

Правила из ТЗ:
  * взять можно свободный или стоящий на зарядке кар; закреплён за другим — предупреждение,
    но взять всё равно можно (закрепление рекомендательное);
  * один сотрудник — один кар (блокировка на уровне операций);
  * вернуть может тот, кто брал; если брал внешний (по ФИО) — любой; супервайзер и выше — всегда;
  * замечания при возврате → кар автоматически «на обслуживании», снять — только менеджер/админ;
  * история не редактируется и не удаляется;
  * время — Europe/Moscow.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, audit, current_principal, require_manager, require_supervisor
from ..cars import (ACTION_TITLES, CarInterceptAssigned, CarOpError, STATUS_TITLES,
                    add_location, assign_employee, car_dict, create_car, edit_car,
                    find_free_car, get_car, give_car, handover_car, list_locations,
                    return_car, set_status, take_car, update_location)
from ..db import get_db
from ..models import CarHistory, Employee
from ..photos import photos_of

router = APIRouter(prefix="/api/cars", tags=["cars"])

MAX_PHOTO_BYTES = 12 * 1024 * 1024   # оригиналы не сжимаем


def _err(e: CarOpError) -> HTTPException:
    if isinstance(e, CarInterceptAssigned):
        return HTTPException(status_code=409, detail={"interception": True, "message": str(e)})
    return HTTPException(status_code=400, detail=str(e))


class TakeIn(BaseModel):
    ack_assigned: bool = False


class HandoverIn(BaseModel):
    employee_id: Optional[int] = None
    name: str = ""
    with_key: bool = True
    comment: str = ""


class GiveIn(BaseModel):
    employee_id: Optional[int] = None
    name: str = ""
    with_key: bool = True


class AssignIn(BaseModel):
    employee_id: Optional[int] = None      # пусто / 0 — снять закрепление


class StatusIn(BaseModel):
    status: str
    note: str = ""


class CarIn(BaseModel):
    number: str
    location: str = ""


class CarEditIn(BaseModel):
    number: Optional[str] = None
    location: Optional[str] = None
    note: Optional[str] = None
    active: Optional[bool] = None


class LocationIn(BaseModel):
    name: str


class LocationEditIn(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None


@router.get("/meta")
def meta(principal: Principal = Depends(current_principal)):
    """Справочные словари для интерфейса + права."""
    from ..cars import CHARGE_TITLES

    return {
        "statuses": [{"code": k, "title": v} for k, v in STATUS_TITLES.items()],
        "actions": [{"code": k, "title": v} for k, v in ACTION_TITLES.items()],
        "charges": [{"code": k, "title": v} for k, v in CHARGE_TITLES.items() if k],
        "can_manage": principal.is_manager,          # добавлять места/карты — супервайзер+
        "can_edit_park": principal.role in ("admin", "manager"),
    }


@router.get("/locations")
def locations(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)):
    show_all = principal.role in ("admin", "manager", "supervisor")
    rows = list_locations(db)
    return {"locations": [r for r in rows if r["active"] or show_all]}


@router.post("/locations")
def location_add(payload: LocationIn, db: Session = Depends(get_db),
                 principal: Principal = Depends(require_supervisor)):
    try:
        out = add_location(db, principal, payload.name)
    except CarOpError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(db, principal, "car_location_add", f"location:{out['id']}", payload.model_dump())
    db.commit()
    return out


@router.put("/locations/{loc_id}")
def location_update(loc_id: int, payload: LocationEditIn, db: Session = Depends(get_db),
                    principal: Principal = Depends(require_manager)):
    try:
        out = update_location(db, principal, loc_id, name=payload.name or "",
                              active=payload.active)
    except CarOpError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(db, principal, "car_location_update", f"location:{loc_id}", payload.model_dump())
    db.commit()
    return out


@router.get("")
def park(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)):
    """Парк целиком (видно всем ролям). my_car_id — кар текущего пользователя."""
    from ..models import Car

    cars = []
    for car in db.scalars(select(Car).order_by(Car.number)):
        if not car.active and not principal.is_manager:
            continue              # отключённые кары («не видно») — только менеджменту
        cars.append(car_dict(car))
    mine = None
    if principal.employee is not None:
        free = find_free_car(db, principal.employee.id)
        mine = {"held": next((c["id"] for c in cars
                              if c["holder_user_id"] == principal.user.id), None),
               "free_recommended": free.id if free else None,
               "assigned": next((c["id"] for c in cars if c["assigned_to"] == principal.employee.id), None)}
    return {"cars": cars, "me": mine,
            "can_manage": principal.is_manager}


@router.post("")
def car_add(payload: CarIn, db: Session = Depends(get_db),
            principal: Principal = Depends(require_supervisor)):
    try:
        car = create_car(db, principal, payload.number, payload.location)
    except CarOpError as e:
        raise _err(e)
    audit(db, principal, "car_create", f"car:{car.id}", payload.model_dump())
    db.commit()
    return car_dict(car)


@router.put("/{car_id}")
def car_edit(car_id: int, payload: CarEditIn, db: Session = Depends(get_db),
             principal: Principal = Depends(require_manager)):
    try:
        car = get_car(db, car_id)
        out = edit_car(db, car, principal, payload.model_dump(exclude_none=True))
    except CarOpError as e:
        raise _err(e)
    audit(db, principal, "car_edit", f"car:{car_id}", payload.model_dump(exclude_none=True))
    db.commit()
    return out


@router.get("/{car_id}/history")
def car_history(car_id: int, limit: int = 200, db: Session = Depends(get_db),
                principal: Principal = Depends(current_principal)):
    """История кара: только добавление новых записей — правок и удалений нет."""
    from ..models import Car

    if db.get(Car, car_id) is None:
        raise HTTPException(status_code=404, detail="Кар не найден")
    rows = list(db.scalars(select(CarHistory).where(CarHistory.car_id == car_id)
                           .order_by(CarHistory.id.desc()).limit(min(limit, 500))))
    from ..cars import history_dict
    pmap = photos_of(db, "car_return", [h.id for h in rows])
    return {"history": [history_dict(h, pmap.get(h.id, [])) for h in rows]}


@router.post("/{car_id}/take")
def car_take(car_id: int, payload: TakeIn, db: Session = Depends(get_db),
             principal: Principal = Depends(current_principal)):
    try:
        car = get_car(db, car_id)
        out = take_car(db, car, principal, ack_assigned=payload.ack_assigned)
    except CarOpError as e:
        raise _err(e)
    audit(db, principal, "car_take", f"car:{car_id}", payload.model_dump())
    db.commit()
    return {"ok": True, "car": out}


@router.post("/{car_id}/handover")
def car_handover(car_id: int, payload: HandoverIn, db: Session = Depends(get_db),
                 principal: Principal = Depends(current_principal)):
    """Передать другому: внутренний — по id, внешний — по ФИО."""
    try:
        car = get_car(db, car_id)
        out = handover_car(db, car, principal, employee_id=payload.employee_id,
                           name=payload.name, with_key=payload.with_key, comment=payload.comment)
    except CarOpError as e:
        raise _err(e)
    audit(db, principal, "car_handover", f"car:{car_id}", payload.model_dump())
    db.commit()
    return {"ok": True, "car": out}


@router.post("/{car_id}/give")
def car_give(car_id: int, payload: GiveIn, db: Session = Depends(get_db),
             principal: Principal = Depends(require_supervisor)):
    """Выдать кар сотруднику (менеджмент; внутренний — по id, внешний — по ФИО)."""
    try:
        car = get_car(db, car_id)
        out = give_car(db, car, principal, employee_id=payload.employee_id,
                       name=payload.name, with_key=payload.with_key)
    except CarOpError as e:
        raise _err(e)
    audit(db, principal, "car_give", f"car:{car_id}", payload.model_dump())
    db.commit()
    return {"ok": True, "car": out}


@router.post("/{car_id}/return")
async def car_return(car_id: int,
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
                     principal: Principal = Depends(current_principal)):
    """Возврат кара (multipart): состояние + фото доказательств (оригиналы)."""
    blobs: list[tuple[str, bytes]] = []
    if file is not None:
        blob = await file.read(MAX_PHOTO_BYTES + 1)
        if len(blob) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="Файл больше 12 МБ")
        if blob:
            blobs.append((file.filename or "photo.jpg", blob))
    try:
        car = get_car(db, car_id)
        was_with_key = car.has_key
        out = return_car(db, car, principal, by_employee_id=by_employee_id, by_name=by_name,
                         location=location, charge=charge, canopy=canopy, condition=condition,
                         trash=trash, clean=clean, on_charge=on_charge,
                         key_returned=key_returned, was_with_key=was_with_key,
                         comment=comment, blob_photos=blobs)
    except CarOpError as e:
        raise _err(e)
    except ValueError as e:       # не-картинка в фото
        raise HTTPException(status_code=400, detail=str(e))
    audit(db, principal, "car_return", f"car:{car_id}",
          {"condition": condition, "on_charge": on_charge, "comment": comment})
    db.commit()
    return {"ok": True, "car": out}


@router.post("/{car_id}/assign")
def car_assign(car_id: int, payload: AssignIn, db: Session = Depends(get_db),
               principal: Principal = Depends(require_supervisor)):
    """Закрепление — рекомендательное; право супервайзера и выше (в ТЗ — в карточке сотрудника)."""
    try:
        car = get_car(db, car_id)
        out = assign_employee(db, car, principal, payload.employee_id)
    except CarOpError as e:
        raise _err(e)
    audit(db, principal, "car_assign", f"car:{car_id}", payload.model_dump())
    db.commit()
    return {"ok": True, "car": out}


@router.post("/{car_id}/status")
def car_set_status(car_id: int, payload: StatusIn, db: Session = Depends(get_db),
                   principal: Principal = Depends(require_supervisor)):
    """Ручная смена статуса (супервайзер+). Правила — в cars.set_status:
    «занят» без держателя нельзя; с занятого — только через возврат; обслуживание — только менеджер."""
    try:
        car = get_car(db, car_id)
        out = set_status(db, car, principal, payload.status, payload.note)
    except CarOpError as e:
        raise _err(e)
    audit(db, principal, "car_status", f"car:{car_id}", payload.model_dump())
    db.commit()
    return {"ok": True, "car": out}
