"""Профили гостей и связи «кто кому» (§3.2), поиск по ФИО, телефону и полям с флагом
«искать». Ничего не коммитит — commit в роутере."""
from __future__ import annotations

import datetime as dt
import json
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..adapters.orm import CustomField, Guest, GuestLink, Reservation
from ..domain.kinship import check_parent, check_spouse, child_title, parent_title, spouse_title
from .fund import FundConflict, FundError, as_dict, changes
from .locking import lock_module

LEVELS = ("regular", "vip", "vvip")
GENDERS = ("m", "f", "")
# вид связи → (подпись B в профиле A, подпись A в профиле B); parent — A родитель B, семейные
# (parent, spouse) подписываются по полу (domain/kinship.py), остальное родство вычисляется
LINK_KINDS = {
    "spouse": ("супруг(а)", "супруг(а)"),
    "parent": ("ребёнок", "родитель"),
    "relative": ("родственник", "родственник"),
    "assistant": ("ассистент", "работодатель"),
    "security": ("охрана", "под охраной"),
    "driver": ("водитель", "пассажир"),
    "nanny": ("няня", "под присмотром"),
    "colleague": ("коллега", "коллега"),
    "other": ("другое", "другое"),
}
PHONE_RE = re.compile(r"^\+[1-9]\d{6,14}$")
PROFILE_FIELDS = ("id", "last_name", "first_name", "middle_name", "phone", "email", "birth_date",
                  "gender", "level", "note", "external_id", "source")


class GuestError(FundError):
    """Ошибка ввода профиля → 422."""


def normalize_phone(raw: str) -> str:
    """Телефон в E.164 (PoC): «8 (916) 123-45-67» → «+79161234567»; пусто — пусто."""
    s = (raw or "").strip()
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    if digits.startswith("00"):
        digits = digits[2:]
    if not s.startswith("+"):
        if len(digits) == 11 and digits.startswith("8"):
            digits = "7" + digits[1:]
        elif len(digits) == 10:
            digits = "7" + digits
    val = "+" + digits
    if not PHONE_RE.match(val):
        raise GuestError("Телефон должен быть в формате +7 999 123-45-67")
    return val


def format_phone(p: str) -> str:
    if p.startswith("+7") and len(p) == 12:
        return f"+7 {p[2:5]} {p[5:8]}-{p[8:10]}-{p[10:12]}"
    return p


def short_name(g: Guest) -> str:
    """«Орлов А.» — так фамилия видна на полосе шахматки (§8, уровень «с фамилиями»)."""
    return g.last_name + (f" {g.first_name[0]}." if g.first_name else "")


def validate_fields(db: Session, target: str, values: dict) -> dict:
    """Значения настраиваемых полей по их типу; неизвестный код — ошибка."""
    defs = {f.code: f for f in db.scalars(select(CustomField).where(CustomField.target == target))}
    out = {}
    for code, v in (values or {}).items():
        f = defs.get(code)
        if f is None:
            raise GuestError(f"Неизвестное поле: {code}")
        if v in (None, ""):
            continue
        if f.kind == "bool" and not isinstance(v, bool):
            raise GuestError(f"Поле «{f.title}»: нужно да или нет")
        if f.kind == "date":
            try:
                dt.date.fromisoformat(str(v))
            except ValueError:
                raise GuestError(f"Поле «{f.title}»: нужна дата") from None
        if f.kind == "choice" and v not in json.loads(f.choices_json or "[]"):
            raise GuestError(f"Поле «{f.title}»: значения нет в списке")
        if f.kind == "text":
            v = str(v)[:500]
        out[code] = v
    return out


def searchable_codes(db: Session, target: str) -> set[str]:
    return set(db.scalars(select(CustomField.code).where(CustomField.target == target,
                                                        CustomField.searchable.is_(True))))


def guest_search_text(g: Guest, searchable: set[str]) -> str:
    fields = json.loads(g.fields_json or "{}")
    parts = [g.last_name, g.first_name, g.middle_name, re.sub(r"\D", "", g.phone), g.email,
             *(str(v) for k, v in fields.items() if k in searchable)]
    # нижний регистр Python: SQLite lower() кириллицу не понижает
    return " ".join(p for p in parts if p).lower()[:1000]


def reservation_search_text(r: Reservation, searchable: set[str]) -> str:
    fields = json.loads(r.fields_json or "{}")
    parts = [r.number, r.customer, *(str(v) for k, v in fields.items() if k in searchable)]
    return " ".join(p for p in parts if p).lower()[:1000]


def reindex_search(db: Session) -> int:
    """Пересчёт search_text после изменения флага «искать по полю»."""
    g_codes, r_codes = searchable_codes(db, "guest"), searchable_codes(db, "reservation")
    n = 0
    for g in db.scalars(select(Guest)):
        g.search_text = guest_search_text(g, g_codes)
        n += 1
    for r in db.scalars(select(Reservation)):
        r.search_text = reservation_search_text(r, r_codes)
        n += 1
    db.flush()
    return n


def guest_dict(g: Guest) -> dict:
    return {**as_dict(g, PROFILE_FIELDS),
            "birth_date": g.birth_date.isoformat() if g.birth_date else None,
            "phone_display": format_phone(g.phone),
            "preferences": json.loads(g.preferences_json or "{}"),
            "special_dates": json.loads(g.special_dates_json or "[]"),
            "fields": json.loads(g.fields_json or "{}")}


def save_guest(db: Session, data: dict, gid: int | None) -> tuple[Guest, dict]:
    if data.get("level", "regular") not in LEVELS:
        raise GuestError("Уровень гостя: обычный, VIP или VVIP")
    if data.get("gender", "") not in GENDERS:
        raise GuestError("Пол гостя: мужской, женский или не указан")
    if gid is None:
        g = Guest()
        db.add(g)
        before: dict = {}
    else:
        g = db.get(Guest, gid)
        if g is None:
            raise GuestError("Гость не найден")
        before = guest_dict(g)
    for k in ("last_name", "first_name", "middle_name", "email", "gender", "level", "note", "external_id",
              "source"):
        if k in data:
            setattr(g, k, data[k])
    if "phone" in data:
        g.phone = normalize_phone(data["phone"])
    if "birth_date" in data:
        g.birth_date = data["birth_date"]
    if "preferences" in data:
        g.preferences_json = json.dumps(data["preferences"] or {}, ensure_ascii=False)
    if "special_dates" in data:
        g.special_dates_json = json.dumps(data["special_dates"] or [], ensure_ascii=False, default=str)
    if "fields" in data:
        g.fields_json = json.dumps(validate_fields(db, "guest", data["fields"]), ensure_ascii=False)
    g.search_text = guest_search_text(g, searchable_codes(db, "guest"))
    db.flush()
    return g, before


def guest_changes(before: dict, g: Guest) -> dict:
    return changes(before, guest_dict(g))


def links_of(db: Session, guest_id: int) -> list[dict]:
    rows = db.scalars(select(GuestLink).where(or_(GuestLink.guest_a_id == guest_id,
                                                  GuestLink.guest_b_id == guest_id))
                      .order_by(GuestLink.id)).all()
    other_ids = {r.guest_b_id if r.guest_a_id == guest_id else r.guest_a_id for r in rows}
    names = {g.id: g for g in db.scalars(select(Guest).where(Guest.id.in_(other_ids)))} if other_ids else {}
    out = []
    for r in rows:
        mine_is_a = r.guest_a_id == guest_id
        other = r.guest_b_id if mine_is_a else r.guest_a_id
        g = names.get(other)
        label = _link_label(r, mine_is_a, g.gender if g else "")
        out.append({"id": r.id, "guest_id": other, "kind": r.kind, "former": r.former, "label": label,
                    "name": short_name(g) if g else "", "level": g.level if g else "regular"})
    return out


def _link_label(r: GuestLink, mine_is_a: bool, other_gender: str) -> str:
    """Подпись второй стороны: семейные — по её полу («дочь», «бывший муж»)."""
    if r.kind == "spouse":
        return spouse_title(other_gender, r.former)
    if r.kind == "parent":
        return child_title(other_gender) if mine_is_a else parent_title(other_gender)
    return LINK_KINDS.get(r.kind, ("связь", "связь"))[0 if mine_is_a else 1]


def add_link(db: Session, guest_id: int, other_id: int, kind: str, former: bool = False) -> GuestLink:
    """Связь guest_id → other_id; parent — guest_id родитель other_id. Семейные проверяются
    по всему графу семьи (§4): не больше двух родителей, не стать своим предком, супруг — не
    предок и не потомок; ошибка — 422 с объяснением."""
    from .family import family_graph

    lock_module(db)        # проверки графа и вставка — под замком: две записи не пропустят третьего родителя
    if kind not in LINK_KINDS:
        raise GuestError("Неизвестный вид связи")
    if former and kind != "spouse":
        raise GuestError("«Бывшие» — только для супругов")
    if guest_id == other_id:
        raise GuestError("Гость не может быть связан сам с собой")
    if db.get(Guest, guest_id) is None or db.get(Guest, other_id) is None:
        raise GuestError("Гость не найден")
    pair = (GuestLink.guest_a_id == guest_id) & (GuestLink.guest_b_id == other_id)
    if kind == "spouse":       # супруги — связь без направления
        pair = pair | ((GuestLink.guest_a_id == other_id) & (GuestLink.guest_b_id == guest_id))
    if db.scalar(select(GuestLink.id).where(pair, GuestLink.kind == kind)) is not None:
        raise FundConflict("Такая связь уже есть")
    if kind in ("parent", "spouse"):
        graph = family_graph(db, {guest_id, other_id})
        err = (check_parent(other_id, guest_id, graph) if kind == "parent"
               else check_spouse(guest_id, other_id, graph))
        if not err and kind == "spouse" and not former:
            current = [x for x in (guest_id, other_id) if any(not f for _, f in graph.spouses.get(x, ()))]
            if current:
                err = "У гостя уже есть супруг(а)"
        if err:
            raise GuestError(err)
    row = GuestLink(guest_a_id=guest_id, guest_b_id=other_id, kind=kind, former=former)
    db.add(row)
    db.flush()
    return row


def delete_link(db: Session, link_id: int) -> GuestLink:
    lock_module(db)
    row = db.get(GuestLink, link_id)
    if row is None:
        raise GuestError("Связь не найдена")
    db.delete(row)
    db.flush()
    return row


def search_query(q: str) -> str:
    """Строка поиска: цифры телефона (8 → 7 в начале) или текст в нижнем регистре."""
    q = q.strip().lower()
    if re.fullmatch(r"[\d\s()+\-]+", q) and sum(c.isdigit() for c in q) >= 3:
        digits = re.sub(r"\D", "", q)
        return "7" + digits[1:] if digits.startswith("8") else digits
    return q


def search_guests(db: Session, q: str, limit: int = 30) -> list[Guest]:
    needle = search_query(q)
    if not needle:
        return []
    return list(db.scalars(select(Guest).where(Guest.search_text.contains(needle, autoescape=True))
                           .order_by(Guest.last_name, Guest.first_name, Guest.id).limit(limit)))
