"""Поддомен «Доставка уведомлений»: общие сущности Telegram и почты (v2, 19.10.2026).

Решение владельца (19.10.2026): отправка сообщений — ОБЩАЯ функциональность
приложения, а не принадлежность ночного отчёта. Позже к ней подключат электрокары
(замечания при возврате), График и Табель (заявления, закрытие периода), отметки
(опоздания). Поэтому получатели и сущности транспорта живут здесь, а разделы
подключаются к ним со своими шаблонами и правилами выбора получателей.

Слои (см. docs/PROPOSAL-NIGHT-REPORT-V2.md, раздел 4.0):
  * модели — этот файл;
  * транспорт и отправка — пакет app/notify/ (не знает про разделы);
  * правило «кто получает» задаёт раздел (ночной отчёт — ответственные службы).

Этап 3: ResponsibilityService — ответственная служба (получатель недостатков).
Этап 4: NotifyChat (общий каталог чатов Telegram) и NotifyTemplate (шаблон раздела).
Этап 5: NotifyDispatch — общий журнал отправок.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..deps import now_local


class ResponsibilityService(Base):
    """Ответственная служба — получатель недостатков ночного обхода.

    Служба закрепляется за пунктом шаблона зоны (ZoneChecklistItem.service_id),
    у отдельного объекта её можно переопределить (ChecklistOverride.service_id).
    В отчёт служба попадает снимком (NightCheckItem.service_id/service_name),
    поэтому переименование службы не меняет закрытые смены.

    Каналы доставки — чекбоксы «чат» и/или «письмо» (решение владельца: можно оба,
    можно один). Чаты закрепляются за службой из ОБЩЕГО каталога чатов Telegram
    (NotifyChat, получается через getUpdates в «Настройки → Чаты и Почта»); ящик
    службы — основной получатель письма, email_copy — копия (несколько адресов
    через запятую).

    active=False — служба не предлагается новым пунктам и не участвует в новых
    отправках; история (журнал и снимки отчётов) не меняется.
    """

    __tablename__ = "responsibility_services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # каналы: чат Telegram и/или письмо
    use_telegram: Mapped[bool] = mapped_column(Boolean, default=False)
    use_email: Mapped[bool] = mapped_column(Boolean, default=False)
    email_to: Mapped[str] = mapped_column(String(200), default="")
    email_copy: Mapped[str] = mapped_column(String(400), default="")
    chat_ids: Mapped[str] = mapped_column(Text, default="[]")     # JSON-список chat_id
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)
