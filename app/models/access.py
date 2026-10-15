"""Права доступа: группы, участники, индивидуальные/ролевые/групповые гранты."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .common import utcnow


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
