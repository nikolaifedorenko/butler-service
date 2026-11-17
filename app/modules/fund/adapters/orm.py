"""Модели модуля «Фонд» (спецификация версий фонда §3): объекты, категории и узлы дерева — постоянные
id; всё, что меняется «с даты», хранят снимки версии. Кросс-модульных relationship нет (R6): другие
модули ссылаются на таблицы строковым FK."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.time import Moment, now


class Category(Base):
    """Категория: постоянна только id; код, название, вид, вес — в CategoryState версии фонда."""

    __tablename__ = "fund_categories"

    id: Mapped[int] = mapped_column(primary_key=True)


class Unit(Base):
    """Физический объект: постоянна только id; обозначение, категория, этаж — в UnitState."""

    __tablename__ = "fund_units"

    id: Mapped[int] = mapped_column(primary_key=True)


class FundGroup(Base):
    """Узел дерева фонда (корпус, этаж…): постоянна только id; название и родитель — в GroupState."""

    __tablename__ = "fund_groups"

    id: Mapped[int] = mapped_column(primary_key=True)


class UnitFlag(Base):
    """Справочник флагов объекта. Не версионируется; использованный флаг архивируется."""

    __tablename__ = "fund_unit_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(80), unique=True)
    color: Mapped[str] = mapped_column(String(9), default="#3b6fd8")
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class CategoryKind(Base):
    """Справочник видов категорий (вилла, номер…). Не версионируется; использованный вид
    архивируется. expanded — раздел дерева шахматки с категорией этого вида раскрыт сразу."""

    __tablename__ = "fund_category_kinds"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(40), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    expanded: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class FundVersion(Base):
    """Версия фонда «с даты»: полный снимок категорий, узлов и объектов. Действует с вечера
    valid_from (§3.3). rev — счётчик правок черновика (оптимистичная блокировка)."""

    __tablename__ = "fund_versions"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published')", name="ck_fund_version_status"),
        # дата уникальна среди опубликованных (черновик на ту же дату заменяет версию); черновик один
        Index("uq_fund_published_from", "valid_from", unique=True,
              postgresql_where=text("status = 'published'")),
        Index("uq_fund_one_draft", "status", unique=True,
              postgresql_where=text("status = 'draft'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    valid_from: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), default="draft")    # draft | published
    base_version_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fund_versions.id"), nullable=True)
    rev: Mapped[int] = mapped_column(Integer, default=1)
    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(Moment, default=now)
    published_at: Mapped[Optional[dt.datetime]] = mapped_column(Moment, nullable=True)


class CategoryState(Base):
    __tablename__ = "fund_category_states"
    __table_args__ = (UniqueConstraint("version_id", "code", name="uq_fund_cat_state_code"),)

    version_id: Mapped[int] = mapped_column(ForeignKey("fund_versions.id"), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("fund_categories.id"), primary_key=True)
    code: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(120))
    kind_id: Mapped[int] = mapped_column(ForeignKey("fund_category_kinds.id"))
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("1"))
    escorted: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class GroupState(Base):
    __tablename__ = "fund_group_states"
    __table_args__ = (
        ForeignKeyConstraint(["version_id", "parent_id"],
                             ["fund_group_states.version_id", "fund_group_states.group_id"]),
    )

    version_id: Mapped[int] = mapped_column(ForeignKey("fund_versions.id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("fund_groups.id"), primary_key=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fund_groups.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    escorted: Mapped[bool] = mapped_column(Boolean, default=False)


class UnitState(Base):
    __tablename__ = "fund_unit_states"
    __table_args__ = (
        UniqueConstraint("version_id", "label", name="uq_fund_unit_state_label"),
        ForeignKeyConstraint(["version_id", "category_id"],
                             ["fund_category_states.version_id", "fund_category_states.category_id"]),
        ForeignKeyConstraint(["version_id", "group_id"],
                             ["fund_group_states.version_id", "fund_group_states.group_id"]),
    )

    version_id: Mapped[int] = mapped_column(ForeignKey("fund_versions.id"), primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("fund_units.id"), primary_key=True)
    label: Mapped[str] = mapped_column(String(40))
    category_id: Mapped[int] = mapped_column(Integer)
    group_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    floor: Mapped[str] = mapped_column(String(8), default="")


class UnitStateFlag(Base):
    """Строка есть — у объекта в версии флаг стоит; строки нет — не стоит."""

    __tablename__ = "fund_unit_state_flags"
    __table_args__ = (
        ForeignKeyConstraint(["version_id", "unit_id"],
                             ["fund_unit_states.version_id", "fund_unit_states.unit_id"],
                             ondelete="CASCADE"),
        Index("ix_fund_unit_state_flags_version_flag", "version_id", "flag_id"),
    )

    version_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flag_id: Mapped[int] = mapped_column(ForeignKey("fund_unit_flags.id", ondelete="RESTRICT"),
                                         primary_key=True)


class UnitLineage(Base):
    """«Из чего получился объект» (деление, объединение): 12134 → 1213 + 1214."""

    __tablename__ = "fund_unit_lineage"

    unit_id: Mapped[int] = mapped_column(ForeignKey("fund_units.id"), primary_key=True)
    predecessor_id: Mapped[int] = mapped_column(ForeignKey("fund_units.id"), primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("fund_versions.id"))
