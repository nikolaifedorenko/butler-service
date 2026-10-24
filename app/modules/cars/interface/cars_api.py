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

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.media import UploadRef, max_upload_bytes, photos_of, read_upload_streaming
from app.core.permissions import has_perm, principal_permissions, require_perm

from ..adapters.orm import CarHistory
from ..application.cars import (
    ACTION_TITLES,
    STATUS_TITLES,
    CarConflict,
    CarInterceptAssigned,
    CarOpError,
    add_location,
    assign_employee,
    car_dict,
    create_car,
    edit_car,
    find_free_car,
    get_car,
    give_car,
    handover_car,
    list_locations,
    return_car,
    set_status,
    take_car,
    update_location,
)

router = APIRouter(prefix="/api/cars", tags=["cars"])

# Лимиты размера медиа задаёт объект (photo_max_mb / video_max_mb) — см. photos.media_limits()


def _err(e: CarOpError) -> HTTPException:
    if isinstance(e, CarInterceptAssigned):
        return HTTPException(status_code=409, detail={"interception": True, "message": str(e)})
    return HTTPException(status_code=409 if isinstance(e, CarConflict) else 400, detail=str(e))


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
def meta(db: Session = Depends(get_db), principal: Principal = Depends(require_perm("cars.view"))):
    """Справочные словари для интерфейса + права."""
    from ..application.cars import CHARGE_TITLES
    perms = principal_permissions(db, principal)

    return {
        "statuses": [{"code": k, "title": v} for k, v in STATUS_TITLES.items()],
        "actions": [{"code": k, "title": v} for k, v in ACTION_TITLES.items()],
        "charges": [{"code": k, "title": v} for k, v in CHARGE_TITLES.items() if k],
        # права раздела (18.10.2026): use — свои операции, issue — выдача/закрепление/
        # статус, manage — парк и справочник мест; can_manage/can_edit_park — легаси-алиасы
        "can_use": "cars.use" in perms,
        "can_issue": "cars.issue" in perms,
        "can_manage": "cars.manage" in perms,
        "can_edit_park": "cars.manage" in perms,
    }


@router.delete("/locations/{loc_id}")
def location_delete(loc_id: int, db: Session = Depends(get_db),
                    principal: Principal = Depends(require_perm("cars.manage"))):
    """Удаление места стоянки (18.10.2026): запрещено, пока место указано у активных
    каров — им нужно сначала сменить место; история хранит места текстом, поэтому
    удалённое место не ломает прошлые записи."""
    from ..adapters.orm import Car, CarLocation

    loc = db.get(CarLocation, loc_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="Место не найдено")
    used = db.scalar(select(Car).where(Car.active.is_(True), Car.location == loc.name))
    if used is not None:
        raise HTTPException(status_code=409, detail=(
            f"Место «{loc.name}» указано у активного кара №{used.number} — сначала "
            "измените место у кара (или отключите место вместо удаления)"))
    db.delete(loc)
    audit(db, principal, "car_location_delete", f"location:{loc_id}", {"name": loc.name})
    db.commit()
    return {"ok": True}


@router.get("/locations")
def locations(db: Session = Depends(get_db), principal: Principal = Depends(require_perm("cars.view"))):
    show_all = has_perm(db, principal, "cars.issue")     # неактивные места — супервайзеру и выше
    rows = list_locations(db)
    return {"locations": [r for r in rows if r["active"] or show_all]}


@router.post("/locations")
def location_add(payload: LocationIn, db: Session = Depends(get_db),
                 principal: Principal = Depends(require_perm("cars.manage"))):
    try:
        out = add_location(db, principal, payload.name)
    except CarOpError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(db, principal, "car_location_add", f"location:{out['id']}", payload.model_dump())
    db.commit()
    return out


@router.put("/locations/{loc_id}")
def location_update(loc_id: int, payload: LocationEditIn, db: Session = Depends(get_db),
                    principal: Principal = Depends(require_perm("cars.manage"))):
    try:
        out = update_location(db, principal, loc_id, name=payload.name or "",
                              active=payload.active)
    except CarOpError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(db, principal, "car_location_update", f"location:{loc_id}", payload.model_dump())
    db.commit()
    return out


@router.get("")
def park(db: Session = Depends(get_db), principal: Principal = Depends(require_perm("cars.view"))):
    """Парк целиком (видно всем ролям). my_car_id — кар текущего пользователя."""
    from ..adapters.orm import Car

    # Видимость неактивных каров и can_manage — по одному ключу cars.manage
    # (этап B, 20.10.2026): раньше фильтр был ролевым (is_manager) и супервайзер
    # видел отключённые кары, не имея прав управления парком.
    perms = principal_permissions(db, principal)
    can_manage = "cars.manage" in perms
    cars = []
    for car in db.scalars(select(Car).order_by(Car.number)):
        if not car.active and not can_manage:
            continue              # отключённые кары («не видно») — только управлению парком
        cars.append(car_dict(car))
    mine = None
    if principal.employee is not None:
        free = find_free_car(db, principal.employee.id)
        mine = {"held": next((c["id"] for c in cars
                              if c["holder_user_id"] == principal.user.id), None),
               "free_recommended": free.id if free else None,
               "assigned": next((c["id"] for c in cars if c["assigned_to"] == principal.employee.id), None)}
    return {"cars": cars, "me": mine, "can_manage": can_manage}


@router.post("")
def car_add(payload: CarIn, db: Session = Depends(get_db),
            principal: Principal = Depends(require_perm("cars.manage"))):
    try:
        car = create_car(db, principal, payload.number, payload.location)
    except CarOpError as e:
        raise _err(e)
    audit(db, principal, "car_create", f"car:{car.id}", payload.model_dump())
    db.commit()
    return car_dict(car)


@router.put("/{car_id}")
def car_edit(car_id: int, payload: CarEditIn, db: Session = Depends(get_db),
             principal: Principal = Depends(require_perm("cars.manage"))):
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
                principal: Principal = Depends(require_perm("cars.view"))):
    """История кара: только добавление новых записей — правок и удалений нет."""
    from ..adapters.orm import Car

    if db.get(Car, car_id) is None:
        raise HTTPException(status_code=404, detail="Кар не найден")
    rows = list(db.scalars(select(CarHistory).where(CarHistory.car_id == car_id)
                           .order_by(CarHistory.id.desc()).limit(max(1, min(limit, 500)))))
    from ..application.cars import history_dict
    # history_dict() принимает КАРТУ фото {ref_id: [...]} и сам достаёт нужные:
    # раньше сюда передавался уже раскрытый список (pmap.get(h.id, [])), из-за чего
    # любой запрос истории кара падал в AttributeError → 500.
    pmap = photos_of(db, "car_return", [h.id for h in rows])
    return {"history": [history_dict(h, pmap) for h in rows]}


@router.post("/{car_id}/take")
def car_take(car_id: int, payload: TakeIn, db: Session = Depends(get_db),
             principal: Principal = Depends(require_perm("cars.use"))):
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
                 principal: Principal = Depends(require_perm("cars.use"))):
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
             principal: Principal = Depends(require_perm("cars.issue"))):
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
    """Возврат кара (multipart): состояние + фото доказательств (оригиналы)."""
    # BUG-03 (решение владельца В-11): «кто вернул» за другого — только с правом выдачи
    if (by_employee_id or by_name.strip()) and not has_perm(db, principal, "cars.issue"):
        raise HTTPException(status_code=403, detail="Указать, кто вернул кар, может только "
                                                    "сотрудник с правом выдачи каров")
    refs: list[UploadRef] = []
    try:
        car = get_car(db, car_id)
        was_with_key = car.has_key
        if file is not None:
            limit = max_upload_bytes(db)
            # потоковая загрузка: чанки сразу на диск, не в память (P1 20.10.2026)
            ref = read_upload_streaming(file, limit)
            if ref.size:
                refs.append(ref)
            else:
                ref.discard()
        out = return_car(db, car, principal, by_employee_id=by_employee_id, by_name=by_name,
                         location=location, charge=charge, canopy=canopy, condition=condition,
                         trash=trash, clean=clean, on_charge=on_charge,
                         key_returned=key_returned, was_with_key=was_with_key,
                         comment=comment, photo_refs=refs)
    except CarOpError as e:
        raise _err(e)
    except ValueError as e:       # не-картинка в фото
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        for ref in refs:
            ref.discard()   # не потреблённые при ошибке; потреблённые уже перенесены (missing_ok)
    audit(db, principal, "car_return", f"car:{car_id}",
          {"condition": condition, "on_charge": on_charge, "comment": comment})
    db.commit()
    return {"ok": True, "car": out}


@router.post("/{car_id}/assign")
def car_assign(car_id: int, payload: AssignIn, db: Session = Depends(get_db),
               principal: Principal = Depends(require_perm("cars.issue"))):
    """Закрепление — рекомендательное; право cars.issue (супервайзер и выше)."""
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
                   principal: Principal = Depends(require_perm("cars.issue"))):
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
