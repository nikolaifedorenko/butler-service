"""Общая часть API ночного отчёта: роутер, входные модели, служебные функции.
Маршруты — в файлах по задачам (шаг 6.5 аудита), подключает их night_api.py."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.media import photos_of

from ..adapters.orm import NightAreaSection, NightReport
from ..application.night import report_dict

router = APIRouter(prefix="/api/night", tags=["night"])

# Лимиты размера медиа задаёт объект (photo_max_mb / video_max_mb) — см. photos.media_limits()


# ─────────────────────────── входные модели ───────────────────────────

class AreaIn(BaseModel):
    name: str
    category: str = ""
    zone_id: Optional[int] = None     # зона обхода (v2): чек-лист зоны действует для объекта
    sort_order: int = 100
    active: bool = True


class ZoneIn(BaseModel):
    name: str
    sort_order: int = 100
    active: bool = True


class ZoneItemIn(BaseModel):
    text: str
    sort_order: int = 100
    active: bool = True
    service_id: Optional[int] = None   # ответственная служба: кто получает недостаток


class OverrideIn(BaseModel):
    """Индивидуальная правка пункта шаблона зоны у конкретного объекта."""
    text: str = ""                       # своя формулировка ('' = как в шаблоне зоны)
    disabled: bool = False               # пункт у этого объекта не проверяется
    service_id: Optional[int] = None     # своя служба (None = как в шаблоне зоны)


class ItemIn(BaseModel):
    text: str
    sort_order: int = 100
    active: bool = True
    service_id: Optional[int] = None   # ответственная служба своего пункта объекта


class DispatchIn(BaseModel):
    """Ручная отправка недостатков службам (этап 5).

    mode="all" — всё, что ещё не отправлено; "selected" — только item_ids.
    service_ids сужает отправку до выбранных служб (кнопка «Отправить службе»).
    Автоотправки нет: ни закрытие объекта, ни закрытие смены ничего не шлют.
    """
    mode: str = "all"
    item_ids: list[int] = []
    service_ids: list[int] = []


class ServiceIn(BaseModel):
    """Ответственная служба: каналы доставки и получатели (этап 3).

    chat_ids — закрепление чатов из ОБЩЕГО каталога Telegram (получается в
    «Настройки → Чаты и Почта»), поэтому здесь только их числовые id.
    """
    name: str
    sort_order: int = 100
    active: bool = True
    use_telegram: bool = False
    use_email: bool = False
    email_to: str = ""
    email_copy: str = ""
    chat_ids: list[int] = []
    note: str = ""


class AnswerIn(BaseModel):
    answer: str          # ok | bad | ''
    comment: str = ""


class InterceptionAck(BaseModel):
    ack: bool = False    # подтверждение перехвата области у другого батлера


class CloseSectionIn(BaseModel):
    force_unanswered: bool = False   # закрыть область с неотмеченными пунктами (ТЗ разрешает)


# Отметка кара в ночном обходе приходит multipart-формой (поля + фото), как возврат
# кара в разделе «Электрокары» — поэтому входной Pydantic-модели здесь нет:
# поля объявлены в сигнатуре report_car_check() через Form(...).


# ─────────────────────────── служебное ───────────────────────────

def _principal_name(pr: Principal) -> str:
    name = pr.employee.display_name if pr.employee is not None else pr.user.username
    # «как сотрудник» — с пометкой, кто вошёл на самом деле (решение владельца В-3)
    return f"{pr.user.username} → как {name}" if pr.impersonated else name


def _get_report(db: Session, report_id: int) -> NightReport:
    rep = db.get(NightReport, report_id)
    if rep is None:
        raise HTTPException(status_code=404, detail="Отчёт не найден")
    return rep


def _get_section(db: Session, section_id: int) -> NightAreaSection:
    sec = db.get(NightAreaSection, section_id)
    if sec is None:
        raise HTTPException(status_code=404, detail="Область не найдена")
    return sec


def _guard_open(rep: NightReport) -> None:
    if rep.status == "closed":
        raise HTTPException(status_code=409,
                            detail=f"Смена {rep.date.strftime('%d.%m.%Y')} закрыта — правки недоступны")


def _guard_section_open(sec) -> None:
    """Закрытая область — только для чтения: правки — после переоткрытия («Переоткрыть» или
    «взять в работу» закрывшим/супервайзером) (рецензия аудита 22.10.2026, P1)."""
    if sec.status == "done":
        when = f" в {sec.closed_at:%H:%M}" if sec.closed_at else ""
        raise HTTPException(status_code=409, detail=(
            f"Область «{sec.name}» закрыта{when} — чтобы изменить отметки, переоткройте её"))


def _report_payload(db: Session, rep: NightReport) -> dict:
    """Отчёт + снимок обхода каров/перехватов + фото к пунктам (для экрана хода смены)."""
    data = report_dict(rep, db=db)
    item_ids = [i["id"] for s in data["areas"] for i in s.get("items", [])]
    pmap = photos_of(db, "night_item", item_ids) if item_ids else {}
    for s in data["areas"]:
        for it in s.get("items", []):
            it["photos"] = pmap.get(it["id"], [])
    return data
