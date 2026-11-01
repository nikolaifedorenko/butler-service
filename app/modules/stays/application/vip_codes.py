"""Справочник VIP-кодов гостя (спецификация правил сопровождения §3): код — текст из цифр
(«03» ≠ «3»), правило сопровождения и коэффициент нагрузки. Не версионируется; использованный код
не удаляется, а уходит в архив. Образец — справочник видов категорий (fund_drafts.save_kind).
Ничего не коммитит — commit в роутере."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.orm import Guest, Reservation, VipCode
from .fund import FundConflict, FundError
from .locking import lock_module

CODE_RE = re.compile(r"[0-9]{1,8}")
FACTOR_MIN, FACTOR_MAX = Decimal("0.1"), Decimal("99")
SORT_RANGE = (-100_000, 100_000)


def normalize_code(raw: str) -> str:
    """Код без пробелов по краям; только цифры, 1–8 знаков (ведущий ноль значим)."""
    code = raw.strip() if isinstance(raw, str) else ""
    if not CODE_RE.fullmatch(code):          # [0-9], не \d: арабские и прочие цифры — не код
        raise FundError("Код — от одной до восьми цифр")
    return code


def code_dict(c: VipCode) -> dict:
    return {"id": c.id, "code": c.code, "title": c.title, "escorted": bool(c.escorted),
            "factor": float(c.factor), "sort_order": c.sort_order, "archived": bool(c.archived)}


def all_codes(db: Session) -> list[VipCode]:
    return list(db.scalars(select(VipCode).order_by(VipCode.sort_order, VipCode.code)))


def _row(db: Session, code_id: int) -> VipCode:
    row = db.get(VipCode, code_id)
    if row is None:
        raise FundError("Кода нет в справочнике")
    return row


def _factor(v) -> Decimal:
    try:
        f = Decimal(str(v)) if not isinstance(v, bool) else None
    except InvalidOperation:
        f = None
    if f is None or not f.is_finite() or not FACTOR_MIN <= f <= FACTOR_MAX:
        raise FundError(f"Коэффициент — число от {FACTOR_MIN} до {FACTOR_MAX}")
    return f.quantize(Decimal("0.01"))


def _sort_order(v) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not SORT_RANGE[0] <= v <= SORT_RANGE[1]:
        raise FundError(f"Порядок — целое число от {SORT_RANGE[0]} до {SORT_RANGE[1]}")
    return v


def save_code(db: Session, data: dict, code_id: int | None) -> int:
    """Создаёт или правит код. Не заданное при правке остаётся прежним; у нового: пустое
    название, escorted = false, коэффициент 1, порядок 100. Занятый код — FundConflict."""
    lock_module(db)
    row = _row(db, code_id) if code_id is not None else None
    code = normalize_code(data.get("code", row.code if row else ""))
    title = str(data.get("title", row.title if row else "") or "").strip()
    if len(title) > 80:
        raise FundError("Название — не длиннее 80 символов")
    factor = _factor(data.get("factor", row.factor if row else 1))
    sort_order = _sort_order(data.get("sort_order", row.sort_order if row else 100))
    escorted = data.get("escorted", row.escorted if row else False)
    if not isinstance(escorted, bool):
        raise FundError("«Сопровождается» — да или нет")
    taken = db.scalar(select(VipCode.id).where(VipCode.code == code))
    if taken is not None and taken != code_id:
        raise FundConflict(f"Код «{code}» уже есть")
    if row is None:
        row = VipCode(archived=False)
        db.add(row)
    row.code, row.title, row.escorted, row.factor, row.sort_order = code, title, escorted, factor, sort_order
    db.flush()
    return row.id


def archive_code(db: Session, code_id: int, archived: bool) -> None:
    lock_module(db)
    _row(db, code_id).archived = archived
    db.flush()


def delete_code(db: Session, code_id: int) -> None:
    """Код, стоящий у гостя или в брони, не удаляется — FundConflict (отправьте в архив)."""
    lock_module(db)
    row = _row(db, code_id)
    used = (db.scalar(select(Guest.id).where(Guest.vip_code_id == code_id).limit(1)) is not None
            or db.scalar(select(Reservation.id).where(Reservation.vip_code_id == code_id).limit(1)) is not None)
    if used:
        raise FundConflict("Код используется — отправьте его в архив")
    db.delete(row)
    db.flush()


def check_selectable(db: Session, code_id: int | None, current: int | None) -> None:
    """Код можно выбрать для гостя или брони: он есть и не в архиве. Архивный, уже стоящий
    (code_id == current), можно оставить; выбрать заново — нельзя."""
    if code_id is None:
        return
    row = db.get(VipCode, code_id) if isinstance(code_id, int) and not isinstance(code_id, bool) else None
    if row is None:
        raise FundError("Кода нет в справочнике")
    if row.archived and code_id != current:
        raise FundError(f"Код «{row.code}» в архиве")
