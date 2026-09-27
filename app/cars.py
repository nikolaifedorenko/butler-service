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
  * время — Europe/Moscow (naive, как Punch.ts).
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .deps import now_local
from .models import Car, CarHistory, CarLocation, Employee, Photo, User

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


class CarOpError(ValueError):
    """Ошибка операции с каром (текст показываем пользователю)."""


class CarInterceptAssigned(CarOpError):
    """Кар закреплён за другим сотрудником: мягкое предупреждение, решение за берущим."""

    def __init__(self, assigned_name: str):
        super().__init__(f"Закреплён за {assigned_name}. Всё равно взять?")
        self.assigned_name = assigned_name


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
    try:
        details = json.loads(h.details_json or "{}")
    except Exception:
        details = {}
    return {
        "id": h.id,
        "ts": h.ts.isoformat(timespec="seconds") if h.ts else None,
        "action": h.action,
        "action_title": ACTION_TITLES.get(h.action, h.action),
        "actor_name": h.actor_name or "",
        "person": h.person or "",
        "with_key": h.with_key,
        "location": h.location or "",
        "details": details,
        "photos": photos.get(h.id, []),
    }


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
        "assigned_name": _emp_label(car.assigned_employee) if car.assigned_employee else "",
        "note": car.note or "",
        "last_checked_at": car.last_checked_at.isoformat(timespec="seconds") if car.last_checked_at else None,
        "last_taken_at": car.last_taken_at.isoformat(timespec="seconds") if car.last_taken_at else None,
        "active": bool(car.active),
    }
    if extra:
        data.update(extra)
    return data


def add_history(db: Session, car: Car, action: str, principal, *, person: str = "",
                with_key: Optional[bool] = None, location: str = "",
                details: Optional[dict] = None) -> CarHistory:
    rec = CarHistory(
        car_id=car.id, ts=now_local(), action=action,
        actor_user_id=principal.user.id if principal else None,
        actor_name=(principal.name if principal else "system"),
        person=person, with_key=with_key, location=location,
        details_json=json.dumps(details or {}, ensure_ascii=False, default=str))
    db.add(rec)
    db.flush()
    return rec


# ─────────────────────────── операции над каром ───────────────────────────

def take_car(db: Session, car: Car, principal, *, ack_assigned: bool = False) -> dict:
    """«Взять кар» (ТЗ): свободный или стоящий на зарядке.

    Закрепление рекомендательное: если кар закреплён за другим сотрудником —
    мягкое предупреждение («Всё равно взять?»), при ack_assigned=True берём и
    записываем факт в историю. Жёстких блокировок нет. Один сотрудник — один кар."""
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
    assigned_emp = car.assigned_employee if car.assigned_to else None
    if assigned_emp is not None and (principal.employee is None or assigned_emp.id != principal.employee.id):
        if not ack_assigned:
            raise CarInterceptAssigned(assigned_emp.display_name)
    was_charging = car.status == "charging"
    car.status = "busy"
    car.on_charge = False
    car.holder_user_id = holder_uid
    car.holder_name = principal.name
    car.has_key = True          # ключ по умолчанию считается у взявшего
    car.last_taken_at = now_local()
    add_history(db, car, "take", principal, person=principal.name, with_key=True,
                location=car.location,
                details={"from_status": "charging" if was_charging else "free",
                         "taken_despite_assigned": _emp_label(assigned_emp) if assigned_emp else ""})
    return car_dict(car)


def handover_car(db: Session, car: Car, principal, *, employee_id: Optional[int], name: str,
                 with_key: bool = True, comment: str = "") -> dict:
    """Передать кар другому человеку (ТЗ «Отдал»).

    Внутренний сотрудник — по id; внешний — по ФИО (справочник внешних не ведём).
    Держателем становится тот, кому отдали; статус остаётся «Занят». Возврат отмечает
    принявший (любой пользователь, если принял внешний)."""
    if car.status not in ("busy", "charging"):
        raise CarOpError("Передать можно занятый кар (или стоящий на зарядке у держателя)")
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
    car.last_taken_at = now_local()
    add_history(db, car, "handover", principal, person=label, with_key=with_key,
                location=car.location, details={"from": prev_name, "comment": comment})
    return car_dict(car)


def give_car(db: Session, car: Car, principal, *, employee_id: Optional[int], name: str,
             with_key: bool = True) -> dict:
    """Выдать кар сотруднику (менеджер/супервайзер/админ). Внешним — по ФИО, без учётной записи."""
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
    car.last_taken_at = now_local()
    add_history(db, car, "give", principal, person=label, with_key=with_key,
                location=car.location, details={"from": prev_holder})
    return car_dict(car)


def return_car(db: Session, car: Car, principal, *, by_employee_id: Optional[int],
               by_name: str, location: str, charge: str, canopy: bool, condition: str,
               trash: bool, clean: bool, on_charge: bool, key_returned: Optional[bool],
               was_with_key: Optional[bool], comment: str, blob_photos: list[tuple[str, bytes]],
               force: bool = False) -> dict:
    """Возврат кара на парковку.

    Отмечает возврат тот, кто брал (внутренний пользователь), или любой сотрудник —
    если брал внешний. Супервайзер/менеджер/админ могут вернуть любой кар (force).
    Статус после возврата: замечания → «на обслуживании»; иначе на зарядке → «на зарядке»;
    иначе «свободен». Замечания (condition != ok или мусор/не убран) всегда приоритетнее.
    """
    manager = principal.role in ("supervisor", "manager", "admin")
    if not manager and not force:
        if car.holder_user_id and car.holder_user_id != principal.user.id:
            raise CarOpError("Возврат отмечает сотрудник, который брал кар "
                             "(или супервайзер/менеджер/администратор)")
        if not car.holder_user_id and car.holder_name:
            # брал внешний — отметить возврат может любой
            pass
    if on_charge and charge not in ("empty", "half"):
        raise CarOpError("На зарядке оставляют разряженный или полуразряженный кар — уточните заряд")
    by_uid, by_label = resolve_person(db, employee_id=by_employee_id, name=by_name) \
        if (by_employee_id or name) else (None, principal.name)
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
    for fname, fbytes in blob_photos:
        from .photos import save_photo
        save_photo(db, kind="car_return", ref_id=rec.id, filename=fname, blob=fbytes,
                   user_id=principal.user.id, user_name=principal.name)
    return car_dict(car)


def set_status(db: Session, car: Car, principal, status: str, note: str = "") -> dict:
    if status not in STATUS_TITLES:
        raise CarOpError(f"Неизвестный статус: {status}")
    if status == "busy" and not car.holder_user_id and not car.holder_name:
        raise CarOpError("Нельзя сделать кар «занят» без держателя — используйте «выдать»")
    if status in ("free", "disabled", "maintenance") and car.holder_user_id:
        raise CarOpError("Сначала оформите возврат: кар держит сотрудник")
    if status == "maintenance":
        if principal.role not in ("manager", "admin"):
            raise CarOpError("Завести кар на обслуживание может только менеджер или администратор")
    if car.status == "maintenance" and status != "maintenance":
        if principal.role not in ("manager", "admin"):
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
    return car_dict(car)


def assign_employee(db: Session, car: Car, principal, employee_id: Optional[int]) -> dict:
    """Закрепление (рекомендательное). Вызывается из карточки сотрудника."""
    emp = db.get(Employee, employee_id) if employee_id else None
    if employee_id and emp is None:
        raise CarOpError("Сотрудник не найден")
    if emp is not None:
        other = db.scalar(select(Car).where(Car.assigned_to == emp.id, Car.id != car.id))
        if other:
            raise CarOpError(f"За {emp.display_name} уже закреплён кар №{other.number} "
                             f"(один сотрудник — один кар). Сначала снимите его.")
    old_name = _emp_label(car.assigned_employee) if car.assigned_employee else ""
    car.assigned_to = emp.id if emp else None
    add_history(db, car, "assign", principal, person=_emp_label(emp),
                details={"from": old_name, "to": _emp_label(emp)})
    return car_dict(car)


def edit_car(db: Session, car: Car, principal, payload: dict) -> dict:
    """Правка карточки (номер, место, примечание). Статус — только через операции/set_status."""
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
    return car_dict(car)


def create_car(db: Session, principal, number: str, location: str = "") -> Car:
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

def list_locations(db: Session) -> list[dict]:
    """Справочник мест стоянки: активные + все (для админки)."""
    out = []
    for l in db.scalars(select(CarLocation).order_by(CarLocation.sort_order, CarLocation.id)):
        out.append({"id": l.id, "name": l.name, "sort_order": l.sort_order,
                    "active": bool(l.active), "builtin": bool(l.builtin)})
    return out


def add_location(db: Session, principal, name: str) -> dict:
    """Добавить место. Если такое уже есть (даже отключённое) — включаем существующее."""
    name = (name or "").strip()[:160]
    if not name:
        raise CarOpError("Введите название места")
    exists = db.scalar(select(CarLocation).where(CarLocation.name == name))
    if exists:
        exists.active = True
        return {"id": exists.id, "name": exists.name, "restored": True}
    loc = CarLocation(name=name)
    db.add(loc)
    db.flush()
    return {"id": loc.id, "name": loc.name}


def update_location(db: Session, principal, loc_id: int, *, name: str = "",
                    active: Optional[bool] = None) -> dict:
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
    return {"ok": True}


# ────────────────────── обход электрокаров внутри ночного отчёта ──────────────────────

def night_cars_state(db: Session, report) -> dict:
    """Состояние шага «Проверка электрокаров»: какие кары уже проверены в эту смену.

    В обход попадают ВСЕ активные кары; батлер отмечает только те, что смог взять
    (т.е. свободные на момент проверки). Отметка фиксирует фактическое время — если
    кар возьмут после проверки, супервайзер увидит это (taken_after_check)."""
    from .models import CarNightCheck

    checked = {c.car_id: c for c in db.scalars(
        select(CarNightCheck).where(CarNightCheck.report_id == report.id))}
    out = []
    for car in db.scalars(select(Car).where(Car.active.is_(True)).order_by(Car.number)):
        ch = checked.get(car.id)
        entry = {"car": car_dict(car), "checked": ch is not None, "check": None}
        if ch is not None:
            entry["check"] = {
                "id": ch.id, "found": bool(ch.found), "location": ch.location or "",
                "canopy": bool(ch.canopy), "charge": ch.charge or "",
                "on_charge": bool(ch.on_charge), "condition": ch.condition or "ok",
                "trash": bool(ch.trash), "clean": bool(ch.clean), "comment": ch.comment or "",
                "checker_name": ch.checker_name or "",
                "checked_at": ch.checked_at.isoformat(timespec="seconds") if ch.checked_at else None,
                "taken_after_check": bool(car.last_taken_at and ch.checked_at
                                          and car.last_taken_at > ch.checked_at),
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
                    trash: bool, clean: bool, comment: str) -> dict:
    """Отметка по кару в ходе ночного обхода (перезапись — last write wins).

    Замечания супервайзеру: «Не ОК» по техсостоянию и «кар не найден». Отсутствие
    тента — просто факт, в замечания не идёт. Отметки пишутся в общую базу: состояние
    карточки кара обновляется автоматически."""
    from .models import CarNightCheck

    if report.status == "closed":
        raise CarOpError("Смена закрыта — правки недоступны")
    if not car.active:
        raise CarOpError("Кар отключён — отмечать нельзя")
    ch = db.scalar(select(CarNightCheck).where(CarNightCheck.report_id == report.id,
                                               CarNightCheck.car_id == car.id))
    if ch is None:
        ch = CarNightCheck(report_id=report.id, car_id=car.id, car_number=car.number)
        db.add(ch)
    ch.car_number = car.number
    ch.checker_user_id = principal.user.id
    ch.checker_name = principal.name
    ch.found = bool(found)
    ch.location = (location or "").strip()[:160]
    ch.canopy = bool(canopy)
    ch.charge = charge if charge in ("full", "half", "empty") else ""
    ch.on_charge = bool(on_charge)
    ch.condition = "bad" if condition == "bad" else "ok"
    ch.trash = bool(trash)
    ch.clean = bool(clean)
    ch.comment = (comment or "")[:2000]
    if ch.found:      # «не найден» состояние карточки не меняет
        car.location = ch.location or car.location
        car.canopy = ch.canopy
        car.charge = ch.charge or car.charge
        car.on_charge = ch.on_charge
        car.condition = ch.condition
        car.trash = ch.trash
        car.clean = ch.clean
        if ch.condition == "bad" and car.status in ("free", "charging"):
            car.status = "maintenance"
        car.last_checked_at = ch.checked_at or now_local()
    add_history(db, car, "check", principal, person=principal.name, location=ch.location,
                details={"found": ch.found, "charge": ch.charge, "condition": ch.condition,
                         "trash": ch.trash, "clean": ch.clean, "comment": ch.comment})
    db.flush()
    return {"id": ch.id, "found": ch.found,
            "checked_at": ch.checked_at.isoformat(timespec="seconds") if ch.checked_at else None}


def finish_cars_step(db: Session, report, principal) -> dict:
    """Завершить шаг «Проверка электрокаров» (аналог закрытия области)."""
    if report.status == "closed":
        raise CarOpError("Смена закрыта — правки недоступны")
    report.cars_step_done = True
    return {"ok": True, "cars_step_done": True}
