"""Общая часть API ночного отчёта: роутер и модели запросов хода смены.
Маршруты — в файлах по задачам, подключает их night_api.py."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/night", tags=["night"])


class DispatchIn(BaseModel):
    """Отправка недостатков службам — только вручную.

    mode="all" — всё, что ещё не отправлено; "selected" — только item_ids.
    service_ids сужает отправку до выбранных служб.
    """

    mode: str = "all"
    item_ids: list[int] = []
    service_ids: list[int] = []


class AnswerIn(BaseModel):
    answer: str          # ok | bad | ''
    comment: str = ""


class InterceptionAck(BaseModel):
    ack: bool = False    # подтверждение: перехватить объект, завершить шаг каров с непроверенными


class CloseSectionIn(BaseModel):
    force_unanswered: bool = False   # закрыть с неотмеченными пунктами или незакрытыми объектами
