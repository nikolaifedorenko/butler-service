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
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.time import now_local


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


class NotifyChat(Base):
    """Общий каталог чатов Telegram (этап 4).

    Список чатов НЕ вводится руками: бота добавляют в группы служб, и каталог
    обновляется через getUpdates («Настройки → Чаты и Почта»). Закрепление чата
    за службой — в карточке службы (ResponsibilityService.chat_ids), поэтому здесь
    только справочные данные: id, название, тип и когда чат видели последний раз.

    Таблица общая для всех разделов: чат «Техслужба» может быть получателем и
    недостатков ночного обхода, и замечаний по электрокарам.
    """

    __tablename__ = "notify_chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    # id чатов Telegram (-100…) больше 2³¹: в PostgreSQL нужен BIGINT (DB-06, 21.10.2026)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    username: Mapped[str] = mapped_column(String(120), default="")            # @username, если есть
    kind: Mapped[str] = mapped_column(String(24), default="group")            # group | supergroup | channel | private
    first_seen: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    last_seen: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)


class NotifyTemplate(Base):
    """Шаблон сообщения раздела (этап 4).

    Транспорт общий, а текст у каждого раздела свой: ночной отчёт пишет службам
    про недостатки, электрокары — про замечания при возврате. Плейсхолдеры
    ({date}, {service}, {items}, {duty}, …) подставляет app/notify/templates.py;
    список допустимых плейсхолдеров у раздела свой и показывается в настройках.

    Отсутствующая запись означает «текст по умолчанию» (DEFAULT_TEMPLATES).
    """

    __tablename__ = "notify_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String(32), unique=True, index=True)   # night | cars | …
    text: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)


class NotifyDispatch(Base):
    """ОБЩИЙ журнал отправок приложения (этап 5).

    Один журнал на все разделы: ``domain`` + ``ref_id`` указывают, откуда отправка
    (night → night_reports.id, cars → car_history.id и т. д.), поэтому экран журнала
    и повторная отправка работают одинаково для любого раздела.

    История не редактируется: запись создаётся один раз при отправке и хранит
    СНЯТОК того, что ушло (текст, получатель, состав недостатков, число вложений).
    Правки чек-листа после отправки запись не меняют — это и позволяет показать
    «исправлено после отправки» и ничего повторно не слать (решение владельца).

    status: queued | sending | sent | failed (outbox, 22.10.2026: строка пишется до сети,
    sending_at — когда её взяли в отправку); attempts — число попыток доставки,
    ошибка прошлой попытки остаётся в error. external_id — идентификатор во внешней системе
    (message_id Telegram или Message-ID письма): по нему отправку находит поддержка.
    """

    __tablename__ = "notify_dispatches"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String(32), index=True)      # night | cars | …
    ref_id: Mapped[int] = mapped_column(Integer, index=True)         # id записи раздела
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, index=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(120), default="")
    recipient_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("responsibility_services.id"), nullable=True, index=True)
    recipient_name: Mapped[str] = mapped_column(String(160), default="")
    channel: Mapped[str] = mapped_column(String(16), default="")     # telegram | email
    target: Mapped[str] = mapped_column(String(200), default="")     # chat_id или e-mail
    subject: Mapped[str] = mapped_column(String(200), default="")    # тема письма
    cc_json: Mapped[str] = mapped_column(Text, default="")           # снимок адресатов копии (для повтора, P1 20.10.2026)
    message: Mapped[str] = mapped_column(Text, default="")           # текст как ушёл
    items_json: Mapped[str] = mapped_column(Text, default="[]")      # снимок состава отправки
    media_json: Mapped[str] = mapped_column(Text, default="[]")      # id вложений (для повтора)
    media_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="sent")  # queued | sending | sent | failed
    sending_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    external_id: Mapped[str] = mapped_column(String(120), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=1)
