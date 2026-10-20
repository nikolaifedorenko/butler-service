"""Ключ-значение хранилище общих настроек приложения (таблица ``settings``).

Кросс-модульное хранилище по образцу ``core/media`` (Photo, фаза C1): строки
таблицы читают и пишут несколько модулей — правила объекта и прочие правила
(timesheet), учётные данные доставки (notify), шаблоны документов (docs),
центр «Настройки» (settings). Владение одним модулем заставило бы остальных
импортировать чужие adapters (нарушение R3), поэтому модель — в core (фаза C3,
EXECUTION-SPEC-v2 §11.2 G5/R6: FK нет, relationship нет).

Секреты (токены/пароли) в значениях не хранятся в открытом виде дольше, чем
нужно: слой notify маскирует их в API (``public_config``), аудит не печатает.
"""
from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Setting(Base):
    """Ключ/значение — правила расчёта, редактируются в веб-интерфейсе."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Text, не String(255): здесь же хранятся шаблоны документов (tpl_*) — они длиннее
    # 255 символов, и PostgreSQL отклонял запись («value too long»), см. миграцию
    # migrate_settings_value_text (16.10.2026)
    value: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(String(255), default="")
