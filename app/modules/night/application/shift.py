"""Ход ночной смены: отчёт, объекты обхода, отметки пунктов, обход каров, закрытие смены.

Смену ведут батлеры: объект берут в работу, отмечают пункты и закрывают. Объект ведёт один
человек; другой может его перехватить — после подтверждения, с записью перехвата. Закрытый
объект и закрытая смена — только для чтения, пока их не переоткроют. Каждая операция — одна
транзакция вместе с записью аудита.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transactional
from app.core.errors import ConfirmationRequired, Conflict, NotFound, Rejected, Validation
from app.core.media import UploadRef, photos_of, save_photo_ref
from app.core.permissions import has_perm
from app.core.settings_store import Setting
from app.core.time import local_now, to_local
from app.modules.cars.application.cars import CarOpError, check_car_night, finish_cars_step, night_cars_state
from app.modules.cars.application.catalog import Car
from app.modules.exchange.application.documents import docx_to_pdf

from ..adapters.orm import NightAreaSection, NightCheckItem, NightInterception, NightReport
from .night import current_shift_date, finalize_report, report_dict, section_dict, shift_start
from .night_export import render_night_report_docx

# ─────────────────────────── общие проверки ───────────────────────────

def actor_name(principal: Principal) -> str:
    """Кто ведёт обход — для отчёта; вход «как сотрудник» помечается тем, кто вошёл на самом деле."""
    name = principal.employee.display_name if principal.employee is not None else principal.user.username
    return f"{principal.user.username} → как {name}" if principal.impersonated else name


def get_report(db: Session, report_id: int) -> NightReport:
    rep = db.get(NightReport, report_id)
    if rep is None:
        raise NotFound("Отчёт не найден")
    return rep


def _section(db: Session, section_id: int) -> NightAreaSection:
    sec = db.get(NightAreaSection, section_id)
    if sec is None:
        raise NotFound("Область не найдена")
    return sec


def _open_report(db: Session, report_id: int) -> NightReport:
    rep = get_report(db, report_id)
    if rep.status == "closed":
        raise Conflict(f"Смена {rep.date.strftime('%d.%m.%Y')} закрыта — правки недоступны")
    return rep


def _open_section(db: Session, section_id: int) -> NightAreaSection:
    """Объект открытой смены."""
    sec = _section(db, section_id)
    _open_report(db, sec.report_id)
    return sec


def _item_for_marks(db: Session, item_id: int) -> tuple[NightCheckItem, NightAreaSection]:
    """Пункт, который можно менять: смена открыта и объект не закрыт."""
    item = db.get(NightCheckItem, item_id)
    if item is None:
        raise NotFound("Пункт не найден")
    sec = _open_section(db, item.section_id)
    if sec.status == "done":
        when = f" в {to_local(sec.closed_at):%H:%M}" if sec.closed_at else ""
        raise Conflict(f"Область «{sec.name}» закрыта{when} — чтобы изменить отметки, переоткройте её")
    return item, sec


def _cars_section(rep: NightReport) -> NightAreaSection:
    for sec in rep.areas:
        if sec.area_id is None and sec.category == "cars":
            return sec
    raise NotFound("Шаг «Проверка электрокаров» не найден в отчёте")


def _take(sec: NightAreaSection, principal: Principal) -> None:
    sec.status = "taken"
    sec.taken_by = principal.user.id
    sec.taken_by_name = actor_name(principal)
    sec.taken_at = local_now()


# ─────────────────────────── чтение ───────────────────────────

def report_payload(db: Session, rep: NightReport) -> dict:
    """Отчёт для экрана хода смены: объекты с пунктами и фото, обход каров, перехваты."""
    data = report_dict(rep, db=db)
    item_ids = [i["id"] for s in data["areas"] for i in s.get("items", [])]
    photos = photos_of(db, "night_item", item_ids) if item_ids else {}
    for sec in data["areas"]:
        for item in sec.get("items", []):
            item["photos"] = photos.get(item["id"], [])
    return data


def current_report(db: Session) -> dict:
    """Отчёт текущей ночной смены. Чтение без записи: отчёт создаёт и закрывает фоновая
    синхронизация. Пока отчёта нет — пояснение, почему."""
    shift_d = current_shift_date()
    rep = db.scalar(select(NightReport).where(NightReport.date == shift_d))
    if rep is not None:
        return {"available": True, "report": report_payload(db, rep)}
    if local_now() < shift_start(shift_d):
        note = (f"Ночная смена {shift_d.strftime('%d.%m.%Y')} ещё не началась — "
                f"отчёт появится в 20:00. Прошлые смены — в «Архиве».")
    else:
        note = (f"Ночная смена {shift_d.strftime('%d.%m.%Y')} началась — отчёт создаётся; "
                f"обновите страницу через минуту. Прошлые смены — в «Архиве».")
    return {"available": False, "shift_date": shift_d.isoformat(), "note": note}


def list_reports(db: Session, limit: int = 60) -> list[dict]:
    """Архив отчётов с итогами, новые первыми; пункты объектов в список не входят."""
    query = (select(NightReport)
             .options(selectinload(NightReport.areas).selectinload(NightAreaSection.items))
             .order_by(NightReport.date.desc()).limit(max(1, min(limit, 365))))
    return [report_dict(rep, with_items=False) for rep in db.scalars(query)]


def report(db: Session, report_id: int) -> dict:
    return report_payload(db, get_report(db, report_id))


def cars_state(db: Session, report_id: int) -> dict:
    """Обход электрокаров за смену: кары и отметки."""
    return night_cars_state(db, get_report(db, report_id))


# ─────────────────────────── объекты обхода ───────────────────────────

@transactional
def take_section(db: Session, principal: Principal, section_id: int, *, ack: bool = False) -> dict:
    """Взять объект в работу. Объект, который ведёт другой, перехватывается после
    подтверждения (``ack``). Закрытый объект переоткрывает тот, кто его закрыл, или
    сотрудник с правом night.reopen_any."""
    sec = _open_section(db, section_id)
    me = principal.user.id
    if sec.status == "taken" and sec.taken_by == me:
        return {"section": section_dict(sec), "warning": None, "already": True}
    warning = None
    if sec.status == "taken" and sec.taken_by and sec.taken_by != me:
        if not ack:
            raise ConfirmationRequired(
                f"Эту область уже проверяет {sec.taken_by_name} (с {to_local(sec.taken_at):%H:%M}). "
                f"Продолжить? Отметка перейдёт вам.", interception=True)
        db.add(NightInterception(report_id=sec.report_id, section_id=sec.id,
                                 from_user_id=sec.taken_by, from_user_name=sec.taken_by_name,
                                 to_user_id=me, to_user_name=actor_name(principal)))
        warning = f"Вы перехватили область у {sec.taken_by_name}"
    if sec.status == "done":
        if me != sec.closed_by and not has_perm(db, principal, "night.reopen_any"):
            raise Conflict(f"Область закрыта в {to_local(sec.closed_at):%H:%M} — переоткрыть может "
                           f"тот, кто её закрыл, или супервайзер")
        sec.closed_at = None
        warning = "Область переоткрыта"
    _take(sec, principal)
    audit(db, principal, "night_section_take", f"section:{sec.id}",
          {"area": sec.name, "intercepted": bool(warning and "перехват" in warning)})
    return {"section": section_dict(sec), "warning": warning, "already": False}


@transactional
def close_section(db: Session, principal: Principal, section_id: int, *, force_unanswered: bool = False) -> dict:
    """Завершить проверку объекта. С неотмеченными пунктами — только после подтверждения
    (``force_unanswered``): они останутся «не отмечено»."""
    sec = _open_section(db, section_id)
    unanswered = len([i for i in sec.items if not i.answer])
    if unanswered and not force_unanswered:
        raise ConfirmationRequired(
            f"Не отмечено пунктов: {unanswered}. Они останутся как «не отмечено». Закрыть всё равно?",
            unanswered=unanswered)
    sec.status = "done"
    sec.closed_at = local_now()
    sec.closed_by = principal.user.id
    audit(db, principal, "night_section_close", f"section:{sec.id}", {"area": sec.name, "unanswered": unanswered})
    return section_dict(sec)


@transactional
def reopen_section(db: Session, principal: Principal, section_id: int) -> dict:
    sec = _open_section(db, section_id)
    sec.status = "taken"
    sec.closed_at = None
    audit(db, principal, "night_section_reopen", f"section:{section_id}")
    return section_dict(sec)


# ─────────────────────────── пункты ───────────────────────────

@transactional
def answer_item(db: Session, principal: Principal, item_id: int, answer: str, comment: str = "") -> dict:
    """Отметить пункт: ``ok``, ``bad`` или пусто (снять отметку). Действует последняя отметка.
    Отметка в свободном объекте берёт его в работу."""
    item, sec = _item_for_marks(db, item_id)
    if answer not in ("ok", "bad", ""):
        raise Rejected("Неизвестный ответ")
    item.answer = answer
    item.comment = comment[:2000]
    item.answered_by = principal.user.id
    item.answered_by_name = actor_name(principal)
    item.answered_at = local_now()
    if sec.status == "free":
        _take(sec, principal)
    audit(db, principal, "night_item_answer", f"item:{item_id}", {"answer": item.answer, "section_id": sec.id})
    return {"id": item.id, "answer": item.answer, "comment": item.comment}


@transactional
def add_item_photo(db: Session, principal: Principal, item_id: int, ref: UploadRef) -> dict:
    """Приложить к пункту фото или видео; файл уже лежит во временном каталоге."""
    item, _ = _item_for_marks(db, item_id)
    try:
        photo = save_photo_ref(db, kind="night_item", ref_id=item.id, ref=ref,
                               user_id=principal.user.id, user_name=actor_name(principal))
    except ValueError as exc:                    # файл — не изображение и не видео
        raise Rejected(str(exc)) from exc
    return {"id": photo.id, "url": f"/api/photos/{photo.id}/file", "media_type": photo.media_type or "photo"}


# ─────────────────────────── обход электрокаров ───────────────────────────

@transactional
def check_car(db: Session, principal: Principal, report_id: int, car_id: int, *, found: bool,
              found_location: str, moved: bool, location: str, canopy: bool, charge: str, on_charge: bool,
              condition: str, trash: bool, clean: bool, comment: str, photo_refs: list[UploadRef]) -> dict:
    """Отметить кар в обходе; действует последняя отметка. ``found_location`` — где кар найден,
    ``location`` — куда переставлен (``moved``). Отметка обновляет карточку кара; «не ОК» и
    «не найден» идут в замечания. Первая отметка берёт шаг обхода каров в работу."""
    rep = _open_report(db, report_id)
    car = db.get(Car, car_id)
    if car is None:
        raise NotFound("Кар не найден")
    sec = _cars_section(rep)
    try:
        result = check_car_night(db, rep, car, principal, found=found, found_location=found_location,
                                 moved=moved, location=location, canopy=canopy, charge=charge,
                                 on_charge=on_charge, condition=condition, trash=trash, clean=clean,
                                 comment=comment, photo_refs=photo_refs)
    except CarOpError as exc:
        raise Conflict(str(exc)) from exc
    except IntegrityError as exc:                # тот же кар отметили одновременно
        raise Conflict("Повторная отметка — обновите список") from exc
    except ValueError as exc:                    # файл — не изображение и не видео
        raise Rejected(str(exc)) from exc
    if sec.status == "free":
        _take(sec, principal)
    return result


@transactional
def finish_cars(db: Session, principal: Principal, report_id: int, *, ack: bool = False) -> dict:
    """Завершить шаг «Проверка электрокаров». С непроверенными карами — только после
    подтверждения (``ack``)."""
    rep = _open_report(db, report_id)
    state = night_cars_state(db, rep)
    if state["unchecked"] > 0 and not ack:
        raise ConfirmationRequired(f"Не проверено каров: {state['unchecked']}. Завершить шаг всё равно?",
                                   interception=False)
    try:
        result = finish_cars_step(db, rep, principal)
    except CarOpError as exc:
        raise Conflict(str(exc)) from exc
    sec = _cars_section(rep)
    if sec.status != "done":
        sec.status = "done"
        sec.closed_at = local_now()
        sec.closed_by = principal.user.id
    audit(db, principal, "night_cars_finish", f"report:{rep.id}",
          {"checked": state["checked"], "unchecked": state["unchecked"]})
    return result


# ─────────────────────────── закрытие смены ───────────────────────────

@transactional
def close_report(db: Session, principal: Principal, report_id: int, *, force: bool = False) -> dict:
    """Закрыть смену вручную. Незакрытые объекты или незавершённый обход каров — только
    после подтверждения (``force``): итог смены будет «неполный»."""
    rep = get_report(db, report_id)
    if rep.status == "closed":
        raise Conflict("Отчёт уже закрыт")
    unfinished = len([s for s in rep.areas if s.status != "done"])
    if (unfinished or not rep.cars_step_done) and not force:
        parts = []
        if unfinished:
            parts.append(f"незакрытых областей: {unfinished}")
        if not rep.cars_step_done:
            parts.append("шаг «Проверка электрокаров» не завершён")
        raise ConfirmationRequired("Смена будет неполной (" + ", ".join(parts) + "). Закрыть всё равно?",
                                   unanswered=unfinished)
    finalize_report(rep, reason="manual")
    audit(db, principal, "night_report_close", f"report:{rep.id}", {"result": rep.result})
    return report_payload(db, rep)


@transactional
def reopen_report(db: Session, principal: Principal, report_id: int) -> dict:
    """Переоткрыть закрытую смену для правок. Автозакрытие для неё выключается: повторно её
    закрывают вручную."""
    rep = get_report(db, report_id)
    if rep.status != "closed":
        raise Conflict("Отчёт не закрыт — переоткрывать нечего")
    rep.status = "open"
    rep.result = ""
    rep.closed_at = None
    rep.close_reason = ""
    rep.reopened_at = local_now()
    audit(db, principal, "night_report_reopen", f"report:{rep.id}", {})
    return report_payload(db, rep)


# ─────────────────────────── выгрузка ───────────────────────────

def _docx(db: Session, rep: NightReport) -> bytes:
    company = db.get(Setting, "doc_company")
    photos = photos_of(db, "night_item", [i.id for s in rep.areas for i in s.items])
    return render_night_report_docx(db, rep.id, company=(company.value if company and company.value else ""),
                                    photos_map=photos)


def export_docx(db: Session, report_id: int) -> tuple[bytes, str]:
    """Отчёт смены в DOCX: содержимое и имя файла."""
    rep = get_report(db, report_id)
    return _docx(db, rep), f"night-{rep.date.isoformat()}.docx"


def export_pdf(db: Session, report_id: int) -> tuple[bytes, str]:
    """Отчёт смены в PDF: содержимое и имя файла."""
    rep = get_report(db, report_id)
    name = f"night-{rep.date.isoformat()}.pdf"
    pdf, error = docx_to_pdf(_docx(db, rep), filename=name)
    if pdf is None:
        raise Validation(error or "PDF недоступен на этом сервере")
    return pdf, name
