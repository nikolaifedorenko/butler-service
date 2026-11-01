"""Модели модуля «Шахматка» (спецификация §3). Кросс-модульных relationship нет (R6): связь
с сотрудниками — строковым FK на employees.id. Предупреждения не хранятся (§4.4), объект
строки покрытия — тоже (§3.4): оба вычисляются при чтении."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
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
from sqlalchemy import false as sa_false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.time import now_local

# ── 3.1 Фонд ───────────────────────────────────────────────────────────────


class Category(Base):
    """Категория: постоянна только id; код, название, вид, вес — в CategoryState версии фонда."""

    __tablename__ = "stays_categories"

    id: Mapped[int] = mapped_column(primary_key=True)


class Unit(Base):
    """Физический объект: постоянна только id; обозначение, категория, этаж — в UnitState."""

    __tablename__ = "stays_units"

    id: Mapped[int] = mapped_column(primary_key=True)


class FundGroup(Base):
    """Узел дерева фонда (корпус, этаж…): постоянна только id; название и родитель — в GroupState."""

    __tablename__ = "stays_fund_groups"

    id: Mapped[int] = mapped_column(primary_key=True)


class UnitFlag(Base):
    """Справочник флагов объекта. Не версионируется; использованный флаг архивируется."""

    __tablename__ = "stays_unit_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(80), unique=True)
    color: Mapped[str] = mapped_column(String(9), default="#3b6fd8")
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class CategoryKind(Base):
    """Справочник видов категорий (вилла, номер…). Не версионируется; использованный вид
    архивируется. expanded — раздел дерева шахматки с категорией этого вида раскрыт сразу."""

    __tablename__ = "stays_category_kinds"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(40), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    expanded: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class FundVersion(Base):
    """Версия фонда «с даты»: полный снимок категорий, узлов и объектов. Действует с вечера
    valid_from (§3.3). rev — счётчик правок черновика (оптимистичная блокировка)."""

    __tablename__ = "stays_fund_versions"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published')", name="ck_stays_fund_status"),
        # дата уникальна среди опубликованных (черновик на ту же дату заменяет версию); черновик один
        Index("uq_stays_fund_published_from", "valid_from", unique=True,
              sqlite_where=text("status = 'published'"), postgresql_where=text("status = 'published'")),
        Index("uq_stays_fund_one_draft", "status", unique=True,
              sqlite_where=text("status = 'draft'"), postgresql_where=text("status = 'draft'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    valid_from: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), default="draft")    # draft | published
    base_version_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_fund_versions.id"), nullable=True)
    rev: Mapped[int] = mapped_column(Integer, default=1)
    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    published_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


class CategoryState(Base):
    __tablename__ = "stays_category_states"
    __table_args__ = (UniqueConstraint("version_id", "code", name="uq_stays_cat_state_code"),)

    version_id: Mapped[int] = mapped_column(ForeignKey("stays_fund_versions.id"), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("stays_categories.id"), primary_key=True)
    code: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(120))
    kind_id: Mapped[int] = mapped_column(ForeignKey("stays_category_kinds.id"))
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("1"))
    escorted: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class GroupState(Base):
    __tablename__ = "stays_group_states"
    __table_args__ = (
        ForeignKeyConstraint(["version_id", "parent_id"],
                             ["stays_group_states.version_id", "stays_group_states.group_id"]),
    )

    version_id: Mapped[int] = mapped_column(ForeignKey("stays_fund_versions.id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("stays_fund_groups.id"), primary_key=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_fund_groups.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class UnitState(Base):
    __tablename__ = "stays_unit_states"
    __table_args__ = (
        UniqueConstraint("version_id", "label", name="uq_stays_unit_state_label"),
        ForeignKeyConstraint(["version_id", "category_id"],
                             ["stays_category_states.version_id", "stays_category_states.category_id"]),
        ForeignKeyConstraint(["version_id", "group_id"],
                             ["stays_group_states.version_id", "stays_group_states.group_id"]),
    )

    version_id: Mapped[int] = mapped_column(ForeignKey("stays_fund_versions.id"), primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("stays_units.id"), primary_key=True)
    label: Mapped[str] = mapped_column(String(40))
    category_id: Mapped[int] = mapped_column(Integer)
    group_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    floor: Mapped[str] = mapped_column(String(8), default="")


class UnitStateFlag(Base):
    """Строка есть — у объекта в версии флаг стоит; строки нет — не стоит."""

    __tablename__ = "stays_unit_state_flags"
    __table_args__ = (
        ForeignKeyConstraint(["version_id", "unit_id"],
                             ["stays_unit_states.version_id", "stays_unit_states.unit_id"],
                             ondelete="CASCADE"),
        Index("ix_stays_unit_state_flags_version_flag", "version_id", "flag_id"),
    )

    version_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flag_id: Mapped[int] = mapped_column(ForeignKey("stays_unit_flags.id", ondelete="RESTRICT"),
                                         primary_key=True)


class UnitLineage(Base):
    """«Из чего получился объект» (деление, объединение): 12134 → 1213 + 1214."""

    __tablename__ = "stays_unit_lineage"

    unit_id: Mapped[int] = mapped_column(ForeignKey("stays_units.id"), primary_key=True)
    predecessor_id: Mapped[int] = mapped_column(ForeignKey("stays_units.id"), primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("stays_fund_versions.id"))


class Ooo(Base):
    """OOO — объект не в продаже: интервал по половинам суток [start/start_half, end/end_half]
    (спецификация OOO и блоков §3). Позиция половины — pos(день, AM|PM)."""

    __tablename__ = "stays_ooo"
    __table_args__ = (
        CheckConstraint("start_half IN ('AM', 'PM')", name="ck_stays_ooo_start_half"),
        CheckConstraint("end_half IN ('AM', 'PM')", name="ck_stays_ooo_end_half"),
        Index("ix_stays_ooo_unit_start", "unit_id", "start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("stays_units.id"))
    start: Mapped[dt.date] = mapped_column(Date)
    end: Mapped[dt.date] = mapped_column(Date)
    start_half: Mapped[str] = mapped_column(String(2), default="AM")
    end_half: Mapped[str] = mapped_column(String(2), default="PM")
    reason: Mapped[str] = mapped_column(String(120), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class Block(Base):
    """Блок — резерв на категорию без привязки к объекту: количество по ночам и категориям
    лежит в BlockNight (спецификация OOO и блоков §3)."""

    __tablename__ = "stays_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120), default="")
    start: Mapped[dt.date] = mapped_column(Date)
    end: Mapped[dt.date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class BlockNight(Base):
    """Сколько объектов категории блок держит в ночь night (ночь D — от PM дня D до AM дня D+1)."""

    __tablename__ = "stays_block_nights"
    __table_args__ = (CheckConstraint("quantity >= 1", name="ck_stays_block_nights_quantity"),)

    block_id: Mapped[int] = mapped_column(ForeignKey("stays_blocks.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("stays_categories.id"), primary_key=True)
    night: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer)


class Label(Base):
    """Метка брони — цвет полосы на шахматке."""

    __tablename__ = "stays_labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(80), unique=True)
    color: Mapped[str] = mapped_column(String(9), default="#3b6fd8")


# ── 3.2 Гости ──────────────────────────────────────────────────────────────


class Guest(Base):
    """Профиль гостя. Уровень VIP/VVIP — свойство человека, переходит на все его брони."""

    __tablename__ = "stays_guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    last_name: Mapped[str] = mapped_column(String(80))
    first_name: Mapped[str] = mapped_column(String(80), default="")
    middle_name: Mapped[str] = mapped_column(String(80), default="")
    phone: Mapped[str] = mapped_column(String(24), default="")      # нормализованный: +79161234567
    email: Mapped[str] = mapped_column(String(120), default="")
    birth_date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    gender: Mapped[str] = mapped_column(String(1), default="")         # m | f | '' (не указан)
    level: Mapped[str] = mapped_column(String(8), default="regular")  # regular | vip | vvip
    preferences_json: Mapped[str] = mapped_column(Text, default="{}")
    special_dates_json: Mapped[str] = mapped_column(Text, default="[]")
    fields_json: Mapped[str] = mapped_column(Text, default="{}")
    note: Mapped[str] = mapped_column(Text, default="")
    external_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="")
    # нижний регистр Python: SQLite lower() кириллицу не понижает
    search_text: Mapped[str] = mapped_column(String(1000), default="")   # поиск подстрокой: индекс не помогает
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)


class GuestLink(Base):
    """Связь «кто кому»: одна строка, подпись для каждой стороны — LINK_KINDS. Семейные —
    только parent (A — родитель B) и spouse (former — бывшие); остальное родство вычисляется
    (domain/kinship.py)."""

    __tablename__ = "stays_guest_links"
    __table_args__ = (UniqueConstraint("guest_a_id", "guest_b_id", "kind", name="uq_stays_guest_link"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_a_id: Mapped[int] = mapped_column(ForeignKey("stays_guests.id"), index=True)
    guest_b_id: Mapped[int] = mapped_column(ForeignKey("stays_guests.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    former: Mapped[bool] = mapped_column(Boolean, default=False)


class GuestPref(Base):
    """Пожелание гостя к объекту: группа фонда, флаг или конкретный объект; priority — порядок (1 — главное)."""

    __tablename__ = "stays_guest_prefs"
    __table_args__ = (CheckConstraint("kind IN ('group', 'flag', 'unit')", name="ck_stays_guest_prefs_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("stays_guests.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))          # group | flag | unit
    ref_id: Mapped[int] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(Integer, default=1)


# ── 3.3 Брони ──────────────────────────────────────────────────────────────


class StayGroup(Base):
    """Группа совместного проживания: брони в одном объекте, каждая на своего гостя."""

    __tablename__ = "stays_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120), default="")


class Reservation(Base):
    """Бронь. number (Fidelio) не уникален: совместные брони. version — защита от
    одновременной правки (§9: второе сохранение получает 409)."""

    __tablename__ = "stays_reservations"
    __table_args__ = (Index("ix_stays_res_dates", "check_in", "check_out"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), default="", index=True)
    status: Mapped[str] = mapped_column(String(12), default="confirmed")
    check_in: Mapped[dt.date] = mapped_column(Date)
    check_out: Mapped[dt.date] = mapped_column(Date)
    early: Mapped[bool] = mapped_column(Boolean, default=False)
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("stays_categories.id"))
    paid_category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_categories.id"), nullable=True)
    label_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_labels.id"), nullable=True)
    customer: Mapped[str] = mapped_column(String(160), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    declined_butler: Mapped[bool] = mapped_column(Boolean, default=False)
    fields_json: Mapped[str] = mapped_column(Text, default="{}")
    external_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="")
    group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_groups.id"), nullable=True,
                                                    index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    search_text: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)


class Move(Base):
    """Переезд: с этой даты бронь живёт в другой категории (PoC §4.6)."""

    __tablename__ = "stays_moves"
    __table_args__ = (UniqueConstraint("reservation_id", "move_date", name="uq_stays_move"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stays_reservations.id"))
    move_date: Mapped[dt.date] = mapped_column(Date)
    category_id: Mapped[int] = mapped_column(ForeignKey("stays_categories.id"))


class Assignment(Base):
    """Часть сегмента брони → объект; pinned — закреплён вручную (PoC §4.8).

    seg_index — индекс части: сегмент * PIECE_BASE + номер части между границами версий фонда
    (ревизия 0011; спецификация версий §5). start_pos — начало части (позиция половинки, пишется
    у каждой строки): часть режется ещё и там, где заселённый гость переехал из-за OOO (ревизия
    0016), — читатели режут сегменты по границам версий и по start_pos строк брони.
    pin_unit_id — объект закрепления у закреплённой части без объекта (овербукинг под OOO, §4.4)."""

    __tablename__ = "stays_assignments"
    __table_args__ = (UniqueConstraint("reservation_id", "seg_index", name="uq_stays_assignment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stays_reservations.id"))
    seg_index: Mapped[int] = mapped_column(Integer)
    unit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_units.id"), nullable=True,
                                                   index=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    start_pos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pin_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("stays_units.id", name="fk_stays_assignments_pin_unit"), nullable=True)


class Occupant(Base):
    """Проживающий: гость брони со своими датами; main — главный на эти даты."""

    __tablename__ = "stays_occupants"

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stays_reservations.id"), index=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("stays_guests.id"), index=True)
    date_from: Mapped[dt.date] = mapped_column(Date)
    date_to: Mapped[dt.date] = mapped_column(Date)
    role: Mapped[str] = mapped_column(String(8), default="guest")   # main | guest


class Companion(Base):
    """Разовый сопровождающий брони без профиля: охрана, водитель, няня, животное."""

    __tablename__ = "stays_companions"

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stays_reservations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="other")
    description: Mapped[str] = mapped_column(String(255), default="")


class Logistics(Base):
    """Рейс, трансфер или автомобиль брони."""

    __tablename__ = "stays_logistics"

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stays_reservations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12), default="transfer")   # flight | transfer | car
    date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    time: Mapped[str] = mapped_column(String(5), default="")
    description: Mapped[str] = mapped_column(String(255), default="")


# ── 3.4 Покрытие батлерами ─────────────────────────────────────────────────


class Escort(Base):
    """Список «Сопровождают гостей»: кто из сотрудников может вести гостей."""

    __tablename__ = "stays_escorts"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CoverageLine(Base):
    """Строка покрытия: на дату батлер ведёт всю бронь, всю группу или выбранных
    гостей (stays_coverage_guests). Объект не хранится — он вычисляется."""

    __tablename__ = "stays_coverage"
    __table_args__ = (
        CheckConstraint("(reservation_id IS NULL) <> (group_id IS NULL)",
                        name="ck_stays_coverage_target"),
        Index("ix_stays_coverage_emp_day", "employee_id", "day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[dt.date] = mapped_column(Date, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    reservation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_reservations.id"),
                                                          nullable=True, index=True)
    group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_groups.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(8), default="manual")    # template | manual
    overnight: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[str] = mapped_column(String(255), default="")


class CoverageGuest(Base):
    """Выбранные гости строки покрытия; пусто — вся бронь или группа. Ссылка на гостя, а не
    на запись проживающего: при смене главного запись меняется, а батлер ведёт человека.
    Удаляется кодом вместе со строкой (на SQLite внешние ключи не проверяются)."""

    __tablename__ = "stays_coverage_guests"

    coverage_id: Mapped[int] = mapped_column(ForeignKey("stays_coverage.id"), primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("stays_guests.id"), primary_key=True)


# ── 3.5 Настройки и настраиваемые поля ─────────────────────────────────────


class CustomField(Base):
    """Настраиваемое поле гостя или брони; значения — в fields_json записи."""

    __tablename__ = "stays_fields"
    __table_args__ = (UniqueConstraint("target", "code", name="uq_stays_field"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(String(12))                 # guest | reservation
    code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(8), default="text")    # text | choice | bool | date
    choices_json: Mapped[str] = mapped_column(Text, default="[]")
    searchable: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class StaysSettings(Base):
    """Настройки модуля, одна строка id=1 (её заводит ревизия 0008)."""

    __tablename__ = "stays_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    vip_bonus: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("1"))
    vvip_bonus: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("2"))
    daily_limit: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("8"))
    # коды дня Табеля, при которых назначенному батлеру нужна подмена (отпуск, больничный…)
    replacement_codes: Mapped[str] = mapped_column(String(120), default="ОТ,ДО,Б,ОВ,К")
    # «Шахматка в эксплуатации» (§9.3): true — начальная загрузка («заменить всё») недоступна
    in_production: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
