"""Идентичность и гранты прав: User, группы доступа, гранты (ядро, R5).

Перенесено из app/models/directory.py (User) и app/models/access.py (гранты)
в фазе C1 (20.10.2026): эти таблицы — фундамент аутентификации и прав, их
используют core.auth и core.permissions, поэтому модели живут в core.
Управление грантами (интерфейс «Права доступа») — модуль access (этап C4),
он импортирует эти модели из core (направление «модуль → core» разрешено).

Связь User.employee объявлена строкой и разрешается реестром SQLAlchemy:
Employee живёт в моделях каталога (будущий модуль employees), core его не
импортирует (R5). Фасад app/models/__init__ гарантирует, что все модели
зарегистрированы до конфигурации мапперов.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .roles import ROLE_EMPLOYEE
from .time import utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20), default=ROLE_EMPLOYEE)
    employee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    token_version: Mapped[int] = mapped_column(Integer, default=0)

    employee: Mapped[Optional[Employee]] = relationship(back_populates="user")  # noqa: F821


class AccessGroup(Base):
    """Группа прав доступа (произвольная: «Старшие смены», «Бухгалтерия» …)."""

    __tablename__ = "access_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class AccessGroupMember(Base):
    __tablename__ = "access_group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_access_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("access_groups.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)


class AccessGrant(Base):
    """Право: для группы ИЛИ для пользователя; effect allow/deny. Индивидуальное — сильнее группового."""

    __tablename__ = "access_grants"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("access_groups.id"), nullable=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="")       # переопределение базовой роли
    permission: Mapped[str] = mapped_column(String(48))
    effect: Mapped[str] = mapped_column(String(8), default="allow")  # allow | deny
