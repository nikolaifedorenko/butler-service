"""Справочник «Электрокары»: парк, статусы, история, выдача/передача/возврат.

Правила из ТЗ:
  * кар можно взять свободный, занятый или стоящий на зарядке — статусы различаются,
    «на зарядке» это отдельный статус (кар может понадобиться владельцу);
  * один сотрудник — один закреплённый кар; закрепление рекомендательное, ставится
    в КАРТОЧКЕ СОТРУДНИКА (право супервайзера и выше), здесь только отображается;
  * при выдаче кара внутреннему сотруднику с его согласия оформляется ПЕРЕДАЧА:
    кар остаётся занятым, меняется держатель, возврат отмечает новый держатель;
  * внешние сотрудники (без учётной записи) — по ФИО; возврат отмечает любой;
  * замечания по возврату → кар автоматически «на обслуживании»; снять с обслуживания
    может только менеджер/администратор;
  * история — журнал: не редактируется и не удаляется, добавляются новые записи;
  * время — моменты с поясом; в ответах API — местное время объекта.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import plain_json, transactional
from app.core.errors import Forbidden, NotFound, Rejected
from app.core.media import UploadRef, photos_of, save_photo_ref
from app.core.permissions import has_perm, principal_permissions
from app.core.time import local_iso, local_now
from app.modules.people.application import Employee

from ..adapters.orm import Car, CarHistory, CarLocation

STATUS_TITLES = {
    "free": "свободен",
    "busy": "занят",
    "charging": "на зарядке",
    "maintenance": "на обслуживании",
    "disabled": "отключён",
}
ACTION_TITLES = {
    "create": "Кар добавлен в справочник",
    "take": "Взят с парковки",
    "give": "Выдан",
    "handover": "Передача (с согласия держателя)",
    "handover_return": "Возврат после передачи",
    "return": "Возврат на парковку",
    "status": "Изменение статуса вручную",
    "assign": "Закрепление сотрудника",
    "check": "Проверка в ночном обходе",
    "intercept": "Перехват области проверки",
    "maintenance_off": "Снят с обслуживания",
    "edit": "Карточка обновлена",
}
CHARGE_TITLES = {"full": "полный", "half": "половина", "empty": "разряжен", "": "—"}


class CarOpError(Rejected):
    """Операция с каром отклонена правилом → 400."""


class CarConflict(CarOpError):
    """Кар изменил параллельный запрос → 409, клиенту обновить экран."""

    status_code = 409


class CarInterceptAssigned(CarOpError):
    """Кар закреплён за другим сотрудником: мягкое предупреждение, решение за берущим → 409."""

    status_code = 409

    def __init__(self, assigned_name: str):
        super().__init__(f"Закреплён за {assigned_name}. Всё равно взять?")
        self.assigned_name = assigned_name

    @property
    def detail(self) -> dict:
        return {"interception": True, "message": self.message}


def _emp_label(e: Optional[Employee]) -> str:
    return e.display_name if e else ""


def get_car(db: Session, car_id: int) -> Car:
    car = db.get(Car, car_id)
    if car is None:
        raise CarOpError("Кар не найден")
    return car


def _held_by(db: Session, user_id: Optional[int], *, exclude: Optional[int] = None) -> Optional[Car]:
    """Кар, который пользователь сейчас держит (busy/charging/maintenance)."""
    if not user_id:
        return None
    q = select(Car).where(Car.holder_user_id == user_id)
    if exclude:
        q = q.where(Car.id != exclude)
    return db.scalar(q)


def find_free_car(db: Session, employee_id: int) -> Optional[Car]:
    """Свободный кар для сотрудника (для кнопки «Взять свободный кар» в «Мои отметки»).
    Сначала — закрепленный за ним, затем первый свободный."""
    emp = db.get(Employee, employee_id)
    if emp is None:
        return None
    if _held_by(db, emp.user.id if emp.user else None):
        return None   # у сотрудника уже есть кар — второй брать нельзя
    assigned = db.scalar(select(Car).where(Car.assigned_to == employee_id,
                                            Car.status == "free", Car.active.is_(True)))
    if assigned:
        return assigned
    return db.scalar(select(Car).where(Car.status == "free", Car.active.is_(True))
                     .order_by(Car.number))


def resolve_person(db: Session, *, employee_id: Optional[int], name: str) -> tuple[Optional[int], str]:
    """Внутренний сотрудник (по id) или внешний (по ФИО-строке)."""
    if employee_id:
        emp = db.get(Employee, employee_id)
        if emp is None:
            raise CarOpError("Сотрудник не найден")
        uid = emp.user.id if emp.user else None
        return uid, _emp_label(emp)
    nm = (name or "").strip()
    if not nm:
        raise CarOpError("Укажите сотрудника (из списка) или ФИО внешнего сотрудника")
    return None, nm[:120]


def history_dict(h: CarHistory, photos: dict[int, list[dict]]) -> dict:
    """Запись истории для API.

    `photos` — КАРТА {history_id: [фото…]} (обычно результат photos.photos_of()).
    Список фото конкретной записи функция достаёт сама; передавать сюда уже
    раскрытый список нельзя (см. регрессию в tests/test_cars.py).
    """
    details = h.details
    return {
        "id": h.id,
        "ts": local_iso(h.ts, "seconds"),
        "action": h.action,
        "action_title": ACTION_TITLES.get(h.action, h.action),
        "actor_name": h.actor_name or "",
        "person": h.person or "",
        "with_key": h.with_key,
        "location": h.location or "",
        "details": details,
        "photos": photos.get(h.id, []),
    }


def _assigned_name(car: Car) -> str:
    """Имя закреплённого сотрудника (R6: вместо кросс-модульной
    связи Car.assigned_employee — db.get по assigned_to из сессии объекта;
    identity map делает повторные чтения в списке бесплатными)."""
    if not car.assigned_to:
        return ""
    sess = object_session(car)
    emp = sess.get(Employee, car.assigned_to) if sess is not None else None
    return _emp_label(emp) if emp else ""


def car_dict(car: Car, *, extra: Optional[dict] = None) -> dict:
    data = {
        "id": car.id, "number": car.number, "status": car.status,
        "status_title": STATUS_TITLES.get(car.status, car.status),
        "location": car.location or "", "charge": car.charge,
        "charge_title": CHARGE_TITLES.get(car.charge, car.charge or "—"),
        "on_charge": bool(car.on_charge), "canopy": bool(car.canopy),
        "condition": car.condition or "ok", "trash": bool(car.trash), "clean": bool(car.clean),
        "has_key": bool(car.has_key),
        "holder_user_id": car.holder_user_id, "holder_name": car.holder_name or "",
        "assigned_to": car.assigned_to,
        "assigned_name": _assigned_name(car),
        "note": car.note or "",
        "last_checked_at": local_iso(car.last_checked_at, "seconds"),
        "last_taken_at": local_iso(car.last_taken_at, "seconds"),
        "active": bool(car.active),
    }
    if extra:
        data.update(extra)
    return data


def add_history(db: Session, car: Car, action: str, principal, *, person: str = "",
                with_key: Optional[bool] = None, location: str = "",
                details: Optional[dict] = None) -> CarHistory:
    rec = CarHistory(
        car_id=car.id, ts=local_now(), action=action,
        actor_user_id=principal.user.id if principal else None,
        actor_name=(principal.actor_label if principal else "system"),
        person=person, with_key=with_key, location=location,
        details=plain_json(details or {}))
    db.add(rec)
    try:
        db.flush()
    except IntegrityError as e:
        # ux_cars_holder_user_id / ux_cars_assigned_to: параллельный запрос уже дал (закрепил)
        # этому человеку другой кар
        if "assigned_to" in str(e.orig):
            raise CarConflict("За сотрудником уже закреплён другой кар (один сотрудник — один кар) "
                              "— обновите экран") from e
        if "holder_user_id" not in str(e.orig):
            raise
        raise CarConflict("У сотрудника уже есть кар (один сотрудник — один кар) — обновите экран") from e
    return rec


# ─────────────────────────── операции над каром ───────────────────────────

@transactional
def take_car(db: Session, principal: Principal, car_id: int, *, ack_assigned: bool = False) -> dict:
    """«Взять кар» (ТЗ): свободный или стоящий на зарядке.

    Закрепление рекомендательное: если кар закреплён за другим сотрудником —
    мягкое предупреждение («Всё равно взять?»), при ack_assigned=True берём и
    записываем факт в историю. Жёстких блокировок нет. Один сотрудник — один кар."""
    car = get_car(db, car_id)
    if car.status == "maintenance":
        raise CarOpError("Кар на обслуживании — взять нельзя (снять с обслуживания может менеджер)")
    if car.status == "disabled":
        raise CarOpError("Кар отключён — взять нельзя")
    if car.status not in ("free", "charging"):
        raise CarOpError(f"Кар {STATUS_TITLES.get(car.status, car.status)}"
                         f" ({car.holder_name or 'держатель не указан'}) — сначала оформите возврат")
    holder_uid = principal.user.id
    other = _held_by(db, holder_uid, exclude=car.id)
    if other:
        raise CarOpError(f"У вас уже есть кар №{other.number} — по правилу «один сотрудник — один кар» "
                         f"сначала верните его")
    assigned_emp = db.get(Employee, car.assigned_to) if car.assigned_to else None
    if assigned_emp is not None and (principal.employee is None or assigned_emp.id != principal.employee.id):
        if not ack_assigned:
            raise CarInterceptAssigned(assigned_emp.display_name)
    was_charging = car.status == "charging"
    # CONC-01: два «взять» одного кара — проходит тот, чей UPDATE первым застал прочитанный статус
    claimed = db.execute(update(Car).where(Car.id == car.id, Car.status == car.status)
                         .values(status="busy").execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        raise CarConflict("Кар только что взял другой сотрудник — обновите экран")
    car.status = "busy"
    car.on_charge = False
    car.holder_user_id = holder_uid
    car.holder_name = principal.name
    car.has_key = True          # ключ по умолчанию считается у взявшего
    car.last_taken_at = local_now()
    add_history(db, car, "take", principal, person=principal.name, with_key=True,
                location=car.location,
                details={"from_status": "charging" if was_charging else "free",
                         "taken_despite_assigned": _emp_label(assigned_emp) if assigned_emp else ""})
    audit(db, principal, "car_take", f"car:{car.id}", {"ack_assigned": ack_assigned})
    return car_dict(car)


@transactional
def handover_car(db: Session, principal: Principal, car_id: int, *, employee_id: Optional[int], name: str,
                 with_key: bool = True, comment: str = "") -> dict:
    """Передать кар другому человеку (ТЗ «Отдал»).

    Внутренний сотрудник — по id; внешний — по ФИО (справочник внешних не ведём).
    Держателем становится тот, кому отдали; статус остаётся «Занят». Возврат отмечает
    принявший (любой пользователь, если принял внешний)."""
    car = get_car(db, car_id)
    if car.status not in ("busy", "charging"):
        raise CarOpError("Передать можно занятый кар (или стоящий на зарядке у держателя)")
    # как и возврат: передаёт тот, у кого кар сейчас, либо право cars.override (супервайзер+)
    override = has_perm(db, principal, "cars.override")
    if not override and car.holder_user_id and car.holder_user_id != principal.user.id:
        raise CarOpError("Передать кар может сотрудник, у которого он сейчас "
                         "(или супервайзер/менеджер/администратор)")
    uid, label = resolve_person(db, employee_id=employee_id, name=name)
    if uid == car.holder_user_id:
        raise CarOpError("Кар уже за этим сотрудником")
    prev_name = car.holder_name
    if uid:
        other = db.scalar(select(Car).where(Car.holder_user_id == uid, Car.id != car.id))
        if other:
            raise CarOpError(f"У {label} уже есть кар №{other.number} (один сотрудник — один кар)")
    car.holder_user_id = uid
    car.holder_name = label
    car.status = "busy"
    car.has_key = with_key
    car.last_taken_at = local_now()
    add_history(db, car, "handover", principal, person=label, with_key=with_key,
                location=car.location, details={"from": prev_name, "comment": comment})
    audit(db, principal, "car_handover", f"car:{car.id}",
          {"employee_id": employee_id, "name": name, "with_key": with_key, "comment": comment})
    return car_dict(car)


@transactional
def give_car(db: Session, principal: Principal, car_id: int, *, employee_id: Optional[int], name: str,
             with_key: bool = True) -> dict:
    """Выдать кар сотруднику (право выдачи). Внешним — по ФИО, без учётной записи."""
    car = get_car(db, car_id)
    if car.status == "maintenance":
        raise CarOpError("Кар на обслуживании — выдать нельзя (снять с обслуживания может менеджер)")
    if car.status == "disabled":
        raise CarOpError("Кар отключён — выдать нельзя")
    uid, label = resolve_person(db, employee_id=employee_id, name=name)
    if uid:
        other = db.scalar(select(Car).where(Car.holder_user_id == uid, Car.id != car.id))
        if other:
            raise CarOpError(f"У {label} уже есть кар №{other.number} (один сотрудник — один кар)")
    prev_holder = car.holder_name
    car.holder_user_id = uid
    car.holder_name = label
    car.status = "busy"
    car.has_key = with_key
    car.last_taken_at = local_now()
    add_history(db, car, "give", principal, person=label, with_key=with_key,
                location=car.location, details={"from": prev_holder})
    audit(db, principal, "car_give", f"car:{car.id}", {"employee_id": employee_id, "name": name, "with_key": with_key})
    return car_dict(car)


@transactional
def return_car(db: Session, principal: Principal, car_id: int, *, by_employee_id: Optional[int],
               by_name: str, location: str, charge: str, canopy: bool, condition: str,
               trash: bool, clean: bool, on_charge: bool, key_returned: Optional[bool],
               comment: str, photo_refs: list[UploadRef]) -> dict:
    """Возврат кара на парковку.

    Отмечает возврат тот, кто брал (внутренний пользователь), или любой сотрудник —
    если брал внешний. Супервайзер/менеджер/админ могут вернуть любой кар (force).
    Статус после возврата: замечания → «на обслуживании»; иначе на зарядке → «на зарядке»;
    иначе «свободен». Замечания (condition != ok или мусор/не убран) всегда приоритетнее.
    Указать, что кар вернул кто-то другой, может только сотрудник с правом выдачи.
    """
    if (by_employee_id or by_name.strip()) and not has_perm(db, principal, "cars.issue"):
        raise Forbidden("Указать, кто вернул кар, может только сотрудник с правом выдачи каров")
    car = get_car(db, car_id)
    was_with_key = car.has_key
    override = has_perm(db, principal, "cars.override")
    if not override:
        if car.holder_user_id and car.holder_user_id != principal.user.id:
            raise CarOpError("Возврат отмечает сотрудник, который брал кар "
                             "(или супервайзер/менеджер/администратор)")
        if not car.holder_user_id and car.holder_name:
            # брал внешний — отметить возврат может любой
            pass
    by_uid, by_label = resolve_person(db, employee_id=by_employee_id, name=by_name) \
        if (by_employee_id or by_name) else (None, principal.name)
    was_handover = bool(db.scalar(select(CarHistory).where(
        CarHistory.car_id == car.id, CarHistory.action == "handover")
        .order_by(CarHistory.id.desc()).limit(1))
        and (car.holder_user_id == principal.user.id))
    bad = condition != "ok" or trash or not clean
    car.status = "maintenance" if bad else ("charging" if on_charge else "free")
    car.location = location or car.location
    car.charge = charge
    car.canopy = canopy
    car.condition = condition
    car.trash = trash
    car.clean = clean
    car.on_charge = bool(on_charge) and not bad
    if key_returned is None:
        # вопрос про ключ задавали только если кар отдавали/взят был с ключом; иначе не меняем
        car.has_key = False if was_with_key else car.has_key
    else:
        car.has_key = not key_returned      # ключ не вернули — остался у держателя
    car.holder_user_id = None
    car.holder_name = ""
    car.note = comment[:255] if comment else car.note
    rec = add_history(db, car, "handover_return" if was_handover else "return", principal,
                      person=by_label, with_key=key_returned, location=car.location,
                      details={"charge": charge, "canopy": canopy, "condition": condition,
                               "trash": trash, "clean": clean, "on_charge": bool(car.on_charge),
                               "key_returned": key_returned, "comment": comment,
                               "auto_maintenance": bad})
    for ref in photo_refs:
        # файл уже на диске во временном каталоге: в хранилище он переносится без чтения в память
        try:
            save_photo_ref(db, kind="car_return", ref_id=rec.id, ref=ref,
                           user_id=principal.user.id, user_name=principal.actor_label)
        except ValueError as exc:                # файл — не изображение и не видео
            raise CarOpError(str(exc)) from exc
    audit(db, principal, "car_return", f"car:{car.id}",
          {"condition": condition, "on_charge": on_charge, "comment": comment})
    return car_dict(car)


@transactional
def set_status(db: Session, principal: Principal, car_id: int, status: str, note: str = "") -> dict:
    """Ручная смена статуса: «занят» без держателя нельзя; с занятого — только через возврат;
    обслуживание заводит и снимает только сотрудник с правом cars.maintenance."""
    car = get_car(db, car_id)
    if status not in STATUS_TITLES:
        raise CarOpError(f"Неизвестный статус: {status}")
    if status == "busy" and not car.holder_user_id and not car.holder_name:
        raise CarOpError("Нельзя сделать кар «занят» без держателя — используйте «выдать»")
    if status in ("free", "disabled", "maintenance") and car.holder_user_id:
        raise CarOpError("Сначала оформите возврат: кар держит сотрудник")
    maintenance = has_perm(db, principal, "cars.maintenance")      # менеджер и администратор
    if status == "maintenance" and not maintenance:
        raise CarOpError("Завести кар на обслуживание может только менеджер или администратор")
    if car.status == "maintenance" and status != "maintenance" and not maintenance:
        raise CarOpError("Снять кар с обслуживания может только менеджер или администратор")
    old = car.status
    car.status = status
    if status == "charging":
        car.on_charge = True
        car.charge = car.charge or "half"
    elif status in ("free", "maintenance", "disabled"):
        car.on_charge = False
    add_history(db, car, "maintenance_off" if old == "maintenance" and status != "maintenance"
                else "status", principal, location=car.location,
                details={"from": old, "to": status, "note": note})
    audit(db, principal, "car_status", f"car:{car.id}", {"status": status, "note": note})
    return car_dict(car)


@transactional
def assign_employee(db: Session, principal: Principal, car_id: int, employee_id: Optional[int]) -> dict:
    """Закрепление (рекомендательное); пустой employee_id снимает его."""
    car = get_car(db, car_id)
    emp = db.get(Employee, employee_id) if employee_id else None
    if employee_id and emp is None:
        raise CarOpError("Сотрудник не найден")
    if emp is not None:
        other = db.scalar(select(Car).where(Car.assigned_to == emp.id, Car.id != car.id))
        if other:
            raise CarOpError(f"За {emp.display_name} уже закреплён кар №{other.number} "
                             f"(один сотрудник — один кар). Сначала снимите его.")
    old_name = _assigned_name(car)
    car.assigned_to = emp.id if emp else None
    add_history(db, car, "assign", principal, person=_emp_label(emp),
                details={"from": old_name, "to": _emp_label(emp)})
    audit(db, principal, "car_assign", f"car:{car.id}", {"employee_id": employee_id})
    return car_dict(car)


@transactional
def edit_car(db: Session, principal: Principal, car_id: int, payload: dict) -> dict:
    """Правка карточки (номер, место, примечание). Статус — только через операции/set_status."""
    car = get_car(db, car_id)
    number = (payload.get("number") or car.number).strip()
    if number != car.number:
        exists = db.scalar(select(Car).where(Car.number == number))
        if exists:
            raise CarOpError(f"Кар с номером «{number}» уже есть")
        car.number = number[:40]
    if "location" in payload:
        car.location = (payload.get("location") or "").strip()[:160]
    if "note" in payload:
        car.note = (payload.get("note") or "").strip()[:255]
    if "active" in payload:
        car.active = bool(payload["active"])
    add_history(db, car, "edit", principal, details=payload)
    audit(db, principal, "car_edit", f"car:{car.id}", payload)
    return car_dict(car)


@transactional
def create_car(db: Session, principal: Principal, number: str, location: str = "") -> dict:
    car = register_car(db, principal, number, location)
    audit(db, principal, "car_create", f"car:{car.id}", {"number": number, "location": location})
    return car_dict(car)


def register_car(db: Session, principal: Optional[Principal], number: str, location: str = "") -> Car:
    """Завести кар в парке с записью в его историю. Часть операции: транзакцию ведёт вызывающий."""
    number = (number or "").strip()
    if not number:
        raise CarOpError("Укажите номер кара (строка — номера бывают разные)")
    if len(number) > 40:
        raise CarOpError("Номер слишком длинный (максимум 40 символов)")
    if db.scalar(select(Car).where(Car.number == number)):
        raise CarOpError(f"Кар с номером «{number}» уже есть")
    car = Car(number=number, location=(location or "").strip()[:160], status="free")
    db.add(car)
    db.flush()
    add_history(db, car, "create", principal, location=car.location)
    return car


# ─────────────────────────── места парковки (справочник) ───────────────────────────

def list_locations(db: Session, principal: Principal) -> list[dict]:
    """Справочник мест стоянки; отключённые места видит только сотрудник с правом выдачи."""
    show_all = has_perm(db, principal, "cars.issue")
    return [{"id": loc.id, "name": loc.name, "sort_order": loc.sort_order,
             "active": bool(loc.active), "builtin": bool(loc.builtin)}
            for loc in db.scalars(select(CarLocation).order_by(CarLocation.sort_order, CarLocation.id))
            if loc.active or show_all]


@transactional
def add_location(db: Session, principal: Principal, name: str) -> dict:
    """Добавить место. Если такое уже есть (даже отключённое) — включаем существующее."""
    requested = {"name": name}
    name = (name or "").strip()[:160]
    if not name:
        raise CarOpError("Введите название места")
    loc = db.scalar(select(CarLocation).where(CarLocation.name == name))
    restored = loc is not None
    if loc is None:
        loc = CarLocation(name=name)
        db.add(loc)
        db.flush()
    else:
        loc.active = True
    audit(db, principal, "car_location_add", f"location:{loc.id}", requested)
    return {"id": loc.id, "name": loc.name, "restored": restored}


@transactional
def update_location(db: Session, principal: Principal, loc_id: int, *, name: Optional[str] = None,
                    active: Optional[bool] = None) -> None:
    """Переименовать/отключить место. Переименование обновляет текст в карточках каров."""
    loc = db.get(CarLocation, loc_id)
    if loc is None:
        raise CarOpError("Место не найдено")
    nm = (name or "").strip()[:160]
    if nm and nm != loc.name:
        if db.scalar(select(CarLocation).where(CarLocation.name == nm)):
            raise CarOpError("Такое место уже есть")
        old = loc.name
        loc.name = nm
        for car in db.scalars(select(Car).where(Car.location == old)):
            car.location = nm
    if active is not None:
        loc.active = bool(active)
    audit(db, principal, "car_location_update", f"location:{loc_id}", {"name": name, "active": active})


@transactional
def delete_location(db: Session, principal: Principal, loc_id: int) -> None:
    """Удалить место стоянки. Пока место указано у активного кара — нельзя: сначала у кара
    меняют место. История хранит места текстом, прошлые записи удаление не затрагивает."""
    loc = db.get(CarLocation, loc_id)
    if loc is None:
        raise NotFound("Место не найдено")
    used = db.scalar(select(Car).where(Car.active.is_(True), Car.location == loc.name))
    if used is not None:
        raise CarConflict(f"Место «{loc.name}» указано у активного кара №{used.number} — сначала "
                          "измените место у кара (или отключите место вместо удаления)")
    db.delete(loc)
    audit(db, principal, "car_location_delete", f"location:{loc_id}", {"name": loc.name})


# ─────────────────────────── чтение: парк, история, словари ───────────────────────────

def meta(db: Session, principal: Principal) -> dict:
    """Словари для интерфейса и права пользователя в разделе."""
    perms = principal_permissions(db, principal)
    return {
        "statuses": [{"code": k, "title": v} for k, v in STATUS_TITLES.items()],
        "actions": [{"code": k, "title": v} for k, v in ACTION_TITLES.items()],
        "charges": [{"code": k, "title": v} for k, v in CHARGE_TITLES.items() if k],
        # use — свои операции, issue — выдача, закрепление и статус, manage — парк и места;
        # can_edit_park — прежнее имя can_manage, его ещё читает интерфейс
        "can_use": "cars.use" in perms,
        "can_issue": "cars.issue" in perms,
        "can_manage": "cars.manage" in perms,
        "can_edit_park": "cars.manage" in perms,
    }


def park(db: Session, principal: Principal) -> dict:
    """Парк целиком. Отключённые кары видит только управление парком; me — кары пользователя."""
    can_manage = "cars.manage" in principal_permissions(db, principal)
    cars = [car_dict(car) for car in db.scalars(select(Car).order_by(Car.number))
            if car.active or can_manage]
    mine = None
    if principal.employee is not None:
        free = find_free_car(db, principal.employee.id)
        mine = {"held": next((c["id"] for c in cars if c["holder_user_id"] == principal.user.id), None),
                "free_recommended": free.id if free else None,
                "assigned": next((c["id"] for c in cars if c["assigned_to"] == principal.employee.id), None)}
    return {"cars": cars, "me": mine, "can_manage": can_manage}


def car_history(db: Session, car_id: int, limit: int = 200) -> list[dict]:
    """История кара, новые записи первыми. Записи только добавляются."""
    if db.get(Car, car_id) is None:
        raise NotFound("Кар не найден")
    rows = list(db.scalars(select(CarHistory).where(CarHistory.car_id == car_id)
                           .order_by(CarHistory.id.desc()).limit(max(1, min(limit, 500)))))
    photos = photos_of(db, "car_return", [h.id for h in rows])
    return [history_dict(h, photos) for h in rows]


# ────────────────────── обход электрокаров внутри ночного отчёта ──────────────────────

def night_cars_state(db: Session, report) -> dict:
    """Состояние шага «Проверка электрокаров»: какие кары уже проверены в эту смену.

    В обход попадают ВСЕ активные кары; батлер отмечает только те, что смог взять
    (т.е. свободные на момент проверки). Отметка фиксирует фактическое время — если
    кар возьмут после проверки, супервайзер увидит это (taken_after_check)."""
    from ..adapters.orm import CarNightCheck

    checked = {c.car_id: c for c in db.scalars(
        select(CarNightCheck).where(CarNightCheck.report_id == report.id))}
    pmap = photos_of(db, "car_check", [c.id for c in checked.values()])
    out = []
    for car in db.scalars(select(Car).where(Car.active.is_(True)).order_by(Car.number)):
        ch = checked.get(car.id)
        entry = {"car": car_dict(car), "checked": ch is not None, "check": None}
        if ch is not None:
            entry["check"] = {
                "id": ch.id, "found": bool(ch.found), "location": ch.location or "",
                "found_location": ch.found_location or "", "moved": bool(ch.moved),
                "canopy": bool(ch.canopy), "charge": ch.charge or "",
                "on_charge": bool(ch.on_charge), "condition": ch.condition or "ok",
                "trash": bool(ch.trash), "clean": bool(ch.clean), "comment": ch.comment or "",
                "checker_name": ch.checker_name or "",
                "checked_at": local_iso(ch.checked_at, "seconds"),
                "taken_after_check": bool(car.last_taken_at and ch.checked_at
                                          and car.last_taken_at > ch.checked_at),
                "photos": pmap.get(ch.id, []),
            }
        out.append(entry)
    total = len(out)
    done = sum(1 for e in out if e["checked"])
    problems = [e for e in out if e["check"] and (not e["check"]["found"] or e["check"]["condition"] != "ok")]
    return {"report_id": report.id, "cars_step_done": bool(report.cars_step_done),
            "total": total, "checked": done, "unchecked": total - done,
            "problems": len(problems), "list": out}


def check_car_night(db: Session, report, car: Car, principal, *, found: bool, location: str,
                    canopy: bool, charge: str, on_charge: bool, condition: str,
                    trash: bool, clean: bool, comment: str,
                    photo_refs: Optional[list[UploadRef]] = None,
                    found_location: str = "", moved: bool = False) -> dict:
    """Отметка по кару в ходе ночного обхода (перезапись — last write wins).

    Замечания супервайзеру: «Не ОК» по техсостоянию и «кар не найден». Отсутствие
    тента — просто факт, в замечания не идёт. Отметки пишутся в общую базу: состояние
    карточки кара обновляется автоматически.

    Два места: `found_location` — где батлер нашёл кар, `location` —
    где оставил. Кар мог стоять не там, что в карточке (её место устарело), а найденный
    кар батлер мог ПЕРЕПАРКОВАТЬ — тогда `moved=True`, и место в карточке кара
    меняется на новое. Перепарковка — факт, а не замечание: в счётчик «замечаний»
    не попадает, но видна в обходе, в истории кара (прежнее место → новое) и в выгрузке.

    `photo_refs` — снимки с телефона (как в окне возврата кара): оригиналы
    сохраняются в хранилище фото с kind="car_check" и привязываются к отметке.
    Отметка одна на смену, поэтому повторное сохранение добавляет новый снимок
    к прежним (старые можно удалить крестиком в окне отметки)."""
    from ..adapters.orm import CarNightCheck

    if report.status == "closed":
        raise CarOpError("Смена закрыта — правки недоступны")
    if not car.active:
        raise CarOpError("Кар отключён — отмечать нельзя")
    ch = db.scalar(select(CarNightCheck).where(CarNightCheck.report_id == report.id,
                                               CarNightCheck.car_id == car.id))
    if ch is None:
        ch = CarNightCheck(report_id=report.id, car_id=car.id, car_number=car.number)
        db.add(ch)
    # время отметки обновляется при КАЖДОМ сохранении (перезапись — last write wins):
    # иначе повторная отметка оставалась с checked_at первой, а вместе с ней старели
    # car.last_checked_at и флаг «кар взяли после проверки»
    ch.checked_at = local_now()
    ch.car_number = car.number
    ch.checker_user_id = principal.user.id
    ch.checker_name = principal.actor_label
    ch.found = bool(found)
    ch.found_location = (found_location or "").strip()[:160]
    ch.location = (location or "").strip()[:160]
    # перепарковка имеет смысл, только если кар найден и указано новое место
    ch.moved = bool(moved) and ch.found and bool(ch.location)
    ch.canopy = bool(canopy)
    ch.charge = charge if charge in ("full", "half", "empty") else ""
    ch.on_charge = bool(on_charge)
    ch.condition = "bad" if condition == "bad" else "ok"
    ch.trash = bool(trash)
    ch.clean = bool(clean)
    ch.comment = (comment or "")[:2000]
    place_before = car.location or ""
    if ch.found:      # «не найден» состояние карточки не меняет
        car.location = (ch.location if ch.moved else ch.found_location) or car.location
        car.canopy = ch.canopy
        car.charge = ch.charge or car.charge
        car.on_charge = ch.on_charge
        car.condition = ch.condition
        car.trash = ch.trash
        car.clean = ch.clean
        if ch.condition == "bad" and car.status in ("free", "charging"):
            car.status = "maintenance"
        car.last_checked_at = ch.checked_at   # свежее время отметки (см. выше)
    add_history(db, car, "check", principal, person=principal.name, location=car.location,
                details={"found": ch.found, "charge": ch.charge, "condition": ch.condition,
                         "trash": ch.trash, "clean": ch.clean, "comment": ch.comment,
                         "photos": len(photo_refs or []),
                         # перепарковка: где нашёл → где оставил (прежнее место карточки)
                         "moved": ch.moved, "found_location": ch.found_location,
                         "location_from": place_before if ch.moved else ""})
    db.flush()          # нужен id отметки — фото привязываются к ней (kind="car_check")
    for ref in (photo_refs or []):
        save_photo_ref(db, kind="car_check", ref_id=ch.id, ref=ref,
                       user_id=principal.user.id, user_name=principal.actor_label)
    return {"id": ch.id, "found": ch.found,
            "checked_at": local_iso(ch.checked_at, "seconds")}


def finish_cars_step(db: Session, report, principal) -> dict:
    """Завершить шаг «Проверка электрокаров» (аналог закрытия области)."""
    if report.status == "closed":
        raise CarOpError("Смена закрыта — правки недоступны")
    report.cars_step_done = True
    return {"ok": True, "cars_step_done": True}
