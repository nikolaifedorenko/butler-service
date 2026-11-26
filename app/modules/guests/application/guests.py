"""Профили гостей и связи «кто кому» (§3.2), поиск по ФИО, телефону и полям с флагом
«искать». Ничего не коммитит — commit в роутере."""
from __future__ import annotations

import datetime as dt
import re
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.db import plain_json
from app.core.external import ExternalRef, external_of, find_external, set_external
from app.core.time import local_date
from app.modules.fund.application.catalog import FundGroup, Unit, UnitFlag
from app.modules.fund.application.fund import FundConflict, FundError, as_dict, changes
from app.modules.fund.application.fund_versions import fund_for
from app.modules.fund.application.locking import lock_module

from ..adapters.orm import CustomField, Guest, GuestLink, GuestPref
from ..domain.kinship import (
    check_parent,
    check_partner,
    check_spouse,
    child_title,
    parent_title,
    partner_title,
    spouse_title,
)
from .vip_codes import check_selectable, code_texts

GENDERS = ("m", "f", "")
PREF_KINDS = ("group", "flag", "unit")      # вид пожелания: узел фонда, флаг, объект
# вид связи → (подпись B в профиле A, подпись A в профиле B); parent — A родитель B, семейные
# (parent, spouse) подписываются по полу (domain/kinship.py), остальное родство вычисляется
LINK_KINDS = {
    "spouse": ("супруг(а)", "супруг(а)"),
    "partner": ("партнёр", "партнёр"),
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
                  "gender", "special", "vip_code_id", "note")


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
        if f.kind == "choice" and v not in f.choices:
            raise GuestError(f"Поле «{f.title}»: значения нет в списке")
        if f.kind == "text":
            v = str(v)[:500]
        out[code] = v
    return out


PREFERENCE_ORDER = ("allergy", "food", "habits")


def ordered_preferences(preferences: dict) -> dict:
    """Предпочтения в порядке показа: сначала поля формы, затем остальные по алфавиту."""
    rank = {key: i for i, key in enumerate(PREFERENCE_ORDER)}
    return dict(sorted(preferences.items(), key=lambda kv: (rank.get(kv[0], len(rank)), kv[0])))


def searchable_codes(db: Session, target: str) -> set[str]:
    return set(db.scalars(select(CustomField.code).where(CustomField.target == target,
                                                        CustomField.searchable.is_(True))))


def guest_search_text(g: Guest, searchable: set[str]) -> str:
    fields = g.fields
    parts = [g.last_name, g.first_name, g.middle_name, re.sub(r"\D", "", g.phone), g.email,
             *(str(v) for k, v in fields.items() if k in searchable)]
    # нижний регистр Python: SQLite lower() кириллицу не понижает
    return " ".join(p for p in parts if p).lower()[:1000]


def reindex_search(db: Session) -> int:
    """Пересчёт ``search_text`` гостей после изменения флага «искать по полю»; броней — там же,
    где они (``reservations.reindex_search``)."""
    codes = searchable_codes(db, "guest")
    n = 0
    for g in db.scalars(select(Guest)):
        g.search_text = guest_search_text(g, codes)
        n += 1
    db.flush()
    return n


def guest_dict(g: Guest) -> dict:
    return {**as_dict(g, PROFILE_FIELDS), "external": external_of(g),
            "birth_date": g.birth_date.isoformat() if g.birth_date else None,
            "phone_display": format_phone(g.phone),
            "preferences": ordered_preferences(g.preferences),
            "special_dates": g.special_dates,
            "fields": g.fields}


def save_guest(db: Session, data: dict, gid: int | None) -> tuple[Guest, dict]:
    lock_module(db)        # слияние удаляет гостей: правка профиля не должна идти параллельно с ним
    if not isinstance(data.get("special", False), bool):
        raise GuestError("«Особый гость» — да или нет")
    if data.get("gender", "") not in GENDERS:
        raise GuestError("Пол гостя: мужской, женский или не указан")
    if gid is None:
        g = Guest()
        db.add(g)
        before: dict = {}
    else:
        found = db.get(Guest, gid)
        if found is None:
            raise GuestError("Гость не найден")
        g = found
        before = guest_dict(g)
    if "vip_code_id" in data:
        check_selectable(db, data["vip_code_id"], g.vip_code_id)       # архивный, уже стоящий, оставить можно
    for k in ("last_name", "first_name", "middle_name", "email", "gender", "special", "vip_code_id", "note"):
        if k in data:
            setattr(g, k, data[k])
    if "phone" in data:
        g.phone = normalize_phone(data["phone"])
    if "birth_date" in data:
        g.birth_date = data["birth_date"]
    if "preferences" in data:
        g.preferences = dict(data["preferences"] or {})
    if "special_dates" in data:
        g.special_dates = plain_json(data["special_dates"] or [])
    if "fields" in data:
        g.fields = validate_fields(db, "guest", data["fields"])
    g.search_text = guest_search_text(g, searchable_codes(db, "guest"))
    db.flush()
    return g, before


def upsert_guest(db: Session, ref: ExternalRef, data: dict) -> tuple[Guest, dict, bool]:
    """Гость из внешней системы: найден по «система, экземпляр, id» — обновляется, иначе создаётся.
    Правила те же, что у ``save_guest``. Возвращает гостя, снимок «до» (пустой у нового) и признак
    «создан». Повторный импорт той же выгрузки дубликатов не рождает."""
    lock_module(db)            # поиск и запись — под одним замком: два импорта не создадут двух гостей
    found = find_external(db, Guest, ref)
    g, before = save_guest(db, data, found.id if found else None)
    if found is None:
        set_external(g, ref)
        db.flush()
    return g, before, found is None


def guest_changes(before: dict, g: Guest) -> dict:
    return changes(before, guest_dict(g))


def links_of(db: Session, guest_id: int) -> list[dict]:
    rows = db.scalars(select(GuestLink).where(or_(GuestLink.guest_a_id == guest_id,
                                                  GuestLink.guest_b_id == guest_id))
                      .order_by(GuestLink.id)).all()
    other_ids = {r.guest_b_id if r.guest_a_id == guest_id else r.guest_a_id for r in rows}
    names = {g.id: g for g in db.scalars(select(Guest).where(Guest.id.in_(other_ids)))} if other_ids else {}
    texts = code_texts(db) if any(g.vip_code_id for g in names.values()) else {}
    out = []
    for r in rows:
        mine_is_a = r.guest_a_id == guest_id
        other = r.guest_b_id if mine_is_a else r.guest_a_id
        g = names.get(other)
        label = _link_label(r, mine_is_a, g.gender if g else "")
        out.append({"id": r.id, "guest_id": other, "kind": r.kind, "former": r.former, "label": label,
                    "marriage_start": r.marriage_start, "marriage_end": r.marriage_end,
                    "name": short_name(g) if g else "", "special": bool(g and g.special),
                    "vip_code": texts.get(g.vip_code_id, ("", False))[0] if g and g.vip_code_id else ""})
    return out


def _link_label(r: GuestLink, mine_is_a: bool, other_gender: str) -> str:
    """Подпись второй стороны: семейные — по её полу («дочь», «бывший муж»)."""
    if r.kind == "spouse":
        return spouse_title(other_gender, r.former)
    if r.kind == "partner":
        return partner_title(other_gender, r.former)
    if r.kind == "parent":
        return child_title(other_gender) if mine_is_a else parent_title(other_gender)
    return LINK_KINDS.get(r.kind, ("связь", "связь"))[0 if mine_is_a else 1]


def add_link(db: Session, guest_id: int, other_id: int, kind: str, former: bool = False) -> GuestLink:
    """Связь guest_id → other_id; parent — guest_id родитель other_id. Семейные проверяются
    по всему графу семьи (§4): не больше двух родителей, не стать своим предком, супруг — не
    предок и не потомок; ошибка — 422 с объяснением."""
    lock_module(db)        # проверки графа и вставка — под замком: две записи не пропустят третьего родителя
    return _add_link_locked(db, guest_id, other_id, kind, former)


def add_links(db: Session, guest_id: int, kind: str, *, other_id: int | None = None, new_guest: dict | None = None,
              former: bool = False, other_is_parent: bool = False, also_parent_id: int | None = None,
              also_former_id: int | None = None, created_by: int | None = None,
              expected_parent_ids: list[int] | None = None, marriage_start: dt.date | None = None,
              marriage_end: dt.date | None = None) -> tuple[list[GuestLink], int]:
    """Связь из редактора дерева (§4) одной записью под одним замком → (связи, id второй стороны).
    Вторая сторона — существующий гость other_id или новый new_guest (фамилия, имя, пол);
    other_is_parent — она родитель guest_id (иначе guest_id — её родитель при kind=parent);
    also_parent_id — второй родитель того же ребёнка;
    expected_parent_ids — ранее показанные в форме родители существующего ребёнка;
    also_former_id — прежний брак гостя станет «бывшим» в той же записи (новый супруг:
    без этого добавление заблокировано правилом одного действующего супруга);
    created_by — батлер, который заводит нового человека: тот становится его «своим» (часть 4 §3).
    Любой отказ — исключение после частичных flush: вызывающий откатывает, не остаётся ни гостя, ни связи."""
    lock_module(db)
    _validate_marriage_dates(kind, former, marriage_start, marriage_end)
    if (other_id is None) == (new_guest is None):
        raise GuestError("Укажите гостя для связи: существующего или нового")
    if other_is_parent and kind != "parent":
        raise GuestError("«Родитель» — только для связи родитель — ребёнок")
    if also_parent_id is not None and (kind != "parent" or other_is_parent):
        raise GuestError("Второй родитель — только при добавлении ребёнка")
    if expected_parent_ids is not None:
        if kind != "parent" or other_is_parent or other_id is None:
            raise GuestError("Ожидаемые родители указываются только для существующего ребёнка")
        parents = list(db.scalars(select(GuestLink.guest_a_id).where(
            GuestLink.kind == "parent", GuestLink.guest_b_id == other_id)))
        if sorted(parents) != sorted(expected_parent_ids):
            raise FundConflict("Родительские связи изменились. Проверьте родителей и повторите сохранение")
    if also_parent_id is not None and also_parent_id == guest_id:
        raise GuestError("Второй родитель совпадает с первым")
    if also_former_id is not None and kind != "spouse":
        raise GuestError("«Бывшим» прежний брак может стать только у нового супруга")
    if db.get(Guest, guest_id) is None:
        raise GuestError("Гость не найден")
    if new_guest is not None:
        g = save_guest(db, {"middle_name": "", "phone": "", "email": "", "note": "", **new_guest}, None)[0]
        g.created_by_employee_id = created_by
        other_id = g.id
    assert other_id is not None     # ровно один из other_id / new_guest — проверено в начале
    a, b = (other_id, guest_id) if other_is_parent else (guest_id, other_id)
    prev_former = None
    if also_former_id is not None:
        # сначала прежний брак становится «бывшим» — тогда проверка «один действующий
        # супруг» у новой связи видит граф уже обновлённым и не отказывает
        prev_former = db.get(GuestLink, also_former_id)
        if prev_former is None or prev_former.kind != "spouse" or prev_former.former is not False \
                or guest_id not in (prev_former.guest_a_id, prev_former.guest_b_id):
            raise GuestError("Прежний брак не найден или не принадлежит гостю")
        prev_former.former = True
        db.flush()
    link = _add_link_locked(db, a, b, kind, former)
    link.marriage_start, link.marriage_end = marriage_start, marriage_end
    rows = [link]
    if also_parent_id is not None:
        rows.append(_add_link_locked(db, also_parent_id, other_id, "parent"))
    if prev_former is not None:
        rows.append(prev_former)
    return rows, other_id


def _add_link_locked(db: Session, guest_id: int, other_id: int, kind: str, former: bool = False) -> GuestLink:
    """Проверки и вставка связи; замок модуля уже взят вызывающим."""
    from .family import family_graph

    if kind not in LINK_KINDS:
        raise GuestError("Неизвестный вид связи")
    if former and kind not in ("spouse", "partner"):
        raise GuestError("«Бывшие» — только для супругов и партнёров")
    if guest_id == other_id:
        raise GuestError("Гость не может быть связан сам с собой")
    if db.get(Guest, guest_id) is None or db.get(Guest, other_id) is None:
        raise GuestError("Гость не найден")
    pair = (GuestLink.guest_a_id == guest_id) & (GuestLink.guest_b_id == other_id)
    if kind in ("spouse", "partner"):       # без направления
        pair = pair | ((GuestLink.guest_a_id == other_id) & (GuestLink.guest_b_id == guest_id))
    if db.scalar(select(GuestLink.id).where(pair, GuestLink.kind == kind)) is not None:
        raise FundConflict("Такая связь уже есть")
    if kind in ("parent", "spouse", "partner"):
        graph = family_graph(db, {guest_id, other_id})
        err = (check_parent(other_id, guest_id, graph) if kind == "parent"
               else check_partner(guest_id, other_id, graph) if kind == "partner"
               else check_spouse(guest_id, other_id, graph))
        if not err and kind == "spouse" and not former:
            # эксклюзивность — только у супругов; партнёров может быть несколько
            current = [x for x in (guest_id, other_id) if any(not f for _, f in graph.spouses.get(x, ()))]
            if current:
                err = "У гостя уже есть супруг(а)"
        if err:
            raise GuestError(err)
    row = GuestLink(guest_a_id=guest_id, guest_b_id=other_id, kind=kind, former=former)
    db.add(row)
    db.flush()
    return row


def _has_current_spouse(db: Session, guest_id: int, except_link: int) -> bool:
    return db.scalar(select(GuestLink.id).where(
        GuestLink.kind == "spouse", GuestLink.former.is_(False), GuestLink.id != except_link,
        or_(GuestLink.guest_a_id == guest_id, GuestLink.guest_b_id == guest_id))) is not None


def _validate_marriage_dates(kind: str, former: bool, start: dt.date | None, end: dt.date | None) -> None:
    if (start is not None or end is not None) and kind != "spouse":
        raise GuestError("Даты брака указываются только для супругов")
    if end is not None and not former:
        raise GuestError("Дата окончания указывается для завершённого брака")
    if start is not None and end is not None and end < start:
        raise GuestError("Дата окончания брака раньше даты начала")


def link_state(row: GuestLink) -> dict:
    return {"former": row.former, "marriage_start": row.marriage_start, "marriage_end": row.marriage_end}


def update_link(db: Session, link_id: int, patch: dict) -> tuple[GuestLink, dict]:
    """Изменить статус и даты за одну операцию под замком проверки действующего супруга."""
    lock_module(db)
    row = db.get(GuestLink, link_id, populate_existing=True)
    if row is None:
        raise GuestError("Связь не найдена")
    if row.kind not in ("spouse", "partner"):
        raise GuestError("Менять статус можно только у супругов и партнёров")
    if not patch:
        raise GuestError("Укажите статус или даты брака")
    before = link_state(row)
    former = patch.get("former", row.former)
    start = patch.get("marriage_start", row.marriage_start)
    end = patch.get("marriage_end", row.marriage_end if former else None)
    _validate_marriage_dates(row.kind, former, start, end)
    if row.kind == "spouse" and row.former and not former \
            and any(_has_current_spouse(db, x, row.id) for x in (row.guest_a_id, row.guest_b_id)):
        raise GuestError("У гостя уже есть супруг(а)")
    row.former, row.marriage_start, row.marriage_end = former, start, end
    db.flush()
    return row, before


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


@dataclass(frozen=True)
class TextSearch:
    """Текстовый поиск с учётом уровня видимости (решение 8). Полный уровень — по search_text:
    ФИО, цифры телефона, почта, поля с флагом «искать»; у брони — номер, заказчик, поля. Ниже —
    только ФИО гостя и номер брони: иначе по найденному можно было бы подобрать телефон или почту
    чужого гостя."""
    needle: str
    full: bool

    def guest(self, g: Guest) -> bool:
        return self.needle in ((g.search_text if self.full else g.name_text) or "")

    def reservation(self, r) -> bool:
        return self.needle in ((r.search_text if self.full else (r.number or "").lower()) or "")

    def text(self, s: str) -> bool:
        """Не персональные данные (обозначение объекта) — на любом уровне."""
        return self.needle in s.lower()


def text_search(q: str, full: bool) -> TextSearch | None:
    """None — пустой запрос. Ниже полного уровня цифры не превращаются в номер телефона."""
    needle = search_query(q) if full else q.strip().lower()
    return TextSearch(needle, full) if needle else None


def guest_search_column(full: bool):
    """Колонка поиска гостя в SQL: полный уровень — search_text, ниже — только ФИО."""
    return Guest.search_text if full else Guest.name_text


def search_guests(db: Session, q: str, limit: int = 30, within=None, full: bool = True) -> list[Guest]:
    """within — подзапрос id гостей, среди которых искать (свои гости батлера), или None — все;
    full=False — только по ФИО (ниже полного уровня, решение 8)."""
    ts = text_search(q, full)
    if ts is None:
        return []
    match = guest_search_column(full).contains(ts.needle, autoescape=True)
    date_text = q.strip()
    if full:
        if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", date_text):
            date_text = "-".join(reversed(date_text.split(".")))
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
            with suppress(ValueError):
                match = or_(match, Guest.birth_date == dt.date.fromisoformat(date_text))
    stmt = select(Guest).where(match)
    if within is not None:
        stmt = stmt.where(Guest.id.in_(within))
    return list(db.scalars(stmt.order_by(Guest.last_name, Guest.first_name, Guest.id).limit(limit)))


# ── Объединение дублей (addendum §3) ──────────────────────────────────────

# поля профиля, которые у оставляемого гостя заполняются из дубля, если у него пусто
MERGE_PROFILE = ("first_name", "middle_name", "phone", "email", "birth_date", "gender")
FAMILY_KINDS = ("parent", "spouse")


def _symmetric(kind: str) -> bool:
    """Связь без направления (супруги, родственники, коллеги): A–B и B–A — одна связь."""
    a, b = LINK_KINDS.get(kind, ("", "-"))
    return a == b


Plan = list[tuple[GuestLink, str, int, int, GuestLink | None]]


def plan_links(db: Session, keep_id: int, drop_id: int) -> Plan:
    """Что станет со связями дубля: (связь, итог, новая A, новая B, связь keep для «current»).
    Итог: moved — переносится; duplicate — такая уже есть у keep; removed — связь между ними;
    current — у keep с тем же человеком бывший брак, у дубля действующий: брак keep становится
    действующим, связь дубля удаляется. Семейные перенесённые связи проверяются по графу семьи
    тем же кодом, что и add_link; нарушение (третий родитель, цикл, второй действующий
    супруг) — FundConflict, до записи."""
    from .family import family_links, graph_of

    def sub(x: int) -> int:
        return keep_id if x == drop_id else x

    rows = list(db.scalars(select(GuestLink).where(or_(GuestLink.guest_a_id == drop_id,
                                                       GuestLink.guest_b_id == drop_id)).order_by(GuestLink.id)))
    existing = {(ln.guest_a_id, ln.guest_b_id, ln.kind): ln for ln in db.scalars(select(GuestLink).where(
        or_(GuestLink.guest_a_id == keep_id, GuestLink.guest_b_id == keep_id)))}
    family = [(ln.guest_a_id, ln.guest_b_id, ln.kind, ln.former) for ln in family_links(db, {keep_id, drop_id})
              if drop_id not in (ln.guest_a_id, ln.guest_b_id)]

    def conflict(err: str) -> FundConflict:
        return FundConflict(f"Объединение нарушит семейное дерево: {err}")

    def has_current_spouse(x: int) -> bool:
        return any(not f for _, f in graph_of(family).spouses.get(x, ()))

    plan: Plan = []
    for ln in rows:
        a, b = sub(ln.guest_a_id), sub(ln.guest_b_id)
        if a == b:
            plan.append((ln, "removed", a, b, None))
            continue
        mine = existing.get((a, b, ln.kind)) or (existing.get((b, a, ln.kind)) if _symmetric(ln.kind) else None)
        if mine is not None:
            if ln.kind == "spouse" and mine.former and not ln.former:      # действующий брак важнее бывшего
                if has_current_spouse(a) or has_current_spouse(b):
                    raise conflict("У гостя уже есть супруг(а)")
                family = [t for t in family if not (t[2] == "spouse" and {t[0], t[1]} == {a, b})]
                family.append((a, b, "spouse", False))
                plan.append((ln, "current", a, b, mine))
            else:
                plan.append((ln, "duplicate", a, b, None))
            continue
        if ln.kind in FAMILY_KINDS:
            graph = graph_of(family)
            err = check_parent(b, a, graph) if ln.kind == "parent" else check_spouse(a, b, graph)
            if not err and ln.kind == "spouse" and not ln.former and (has_current_spouse(a) or has_current_spouse(b)):
                err = "У гостя уже есть супруг(а)"
            if err:
                raise conflict(err)
            family.append((a, b, ln.kind, ln.former))
        existing[(a, b, ln.kind)] = ln
        plan.append((ln, "moved", a, b, None))
    return plan


def apply_links(db: Session, plan: Plan, keep_id: int) -> list[dict]:
    others = {a if b == keep_id else b for _, _, a, b, _ in plan}
    names = {g.id: short_name(g) for g in db.scalars(select(Guest).where(Guest.id.in_(others)))} if others else {}
    out = [{"guest_id": (a if b == keep_id else b), "name": names.get(a if b == keep_id else b, ""),
            "kind": ln.kind, "former": ln.former, "result": result} for ln, result, a, b, _ in plan]
    for ln, result, _, _, mine in plan:      # сначала удаления: перенос не должен задеть уникальность
        if result != "moved":
            db.delete(ln)
        if mine is not None:
            mine.former = False
            mine.marriage_start = ln.marriage_start or mine.marriage_start
            mine.marriage_end = None
    db.flush()
    for ln, result, a, b, _ in plan:
        if result == "moved":
            ln.guest_a_id, ln.guest_b_id = a, b
    db.flush()
    return out


def fill_missing(mine: dict, theirs: dict) -> list[str]:
    added = [k for k, v in theirs.items() if v not in (None, "") and mine.get(k) in (None, "")]
    mine.update({k: theirs[k] for k in added})
    return added


def merge_profile(db: Session, keep: Guest, drop: Guest) -> dict:
    """Значения оставляемого побеждают; недостающее берётся у дубля. «Особый гость» — если он
    у любого из двоих; VIP-код дубля переходит, только если у оставляемого его нет; примечания —
    оба, через перевод строки."""
    profile = [k for k in MERGE_PROFILE if not getattr(keep, k) and getattr(drop, k)]
    for k in profile:
        setattr(keep, k, getattr(drop, k))
    if keep.ext_id is None and drop.ext_id is not None:
        # внешний идентификатор уникален: сначала он снимается с дубля (запись в базу), потом ставится оставляемому
        ref = ExternalRef(system=drop.ext_system, instance=drop.ext_instance, id=drop.ext_id)
        drop.ext_id = None
        db.flush()
        set_external(keep, ref)
        profile.append("external")
    if drop.special and not keep.special:
        keep.special = True
        profile.append("special")
    if keep.vip_code_id is None and drop.vip_code_id is not None:
        keep.vip_code_id = drop.vip_code_id
        profile.append("vip_code_id")
    note = (drop.note or "").strip()
    if note and note not in (keep.note or ""):
        keep.note = f"{keep.note.rstrip()}\n{note}" if (keep.note or "").strip() else note
        profile.append("note")
    prefs = dict(keep.preferences)
    pref_added = fill_missing(prefs, drop.preferences)
    keep.preferences = prefs
    fields = dict(keep.fields)
    fields_added = fill_missing(fields, drop.fields)
    keep.fields = fields
    dates = list(keep.special_dates)
    dates_added = [d for d in drop.special_dates if d not in dates]
    keep.special_dates = dates + dates_added
    return {"profile": profile, "preferences": pref_added, "fields": fields_added, "special_dates": dates_added}


def not_carried(dropped: dict, kept: dict) -> dict:
    """Что из профиля дубля не перешло оставляемому (значения keep победили) — только это
    пишется в журнал: персональных данных в аудите — не больше необходимого."""
    out: dict = {}
    lost: Any
    for k, v in dropped.items():
        if k in ("id", "phone_display") or v in (None, "", [], {}) or v is False:
            continue
        if isinstance(v, dict):
            lost = {kk: vv for kk, vv in v.items() if vv not in (None, "") and kept[k].get(kk) != vv}
        elif isinstance(v, list):
            lost = [x for x in v if x not in kept[k]]
        elif k == "note":
            lost = v if v.strip() not in (kept[k] or "") else None
        else:
            lost = v if kept[k] != v else None
        if lost:
            out[k] = lost
    return out


MAX_PREFS = 20
MAX_PRIORITY = 1000
_PREF_REFS = {"group": FundGroup, "flag": UnitFlag, "unit": Unit}


def prefs_of(db: Session, guest_id: int) -> list[dict]:
    """Пожелания гостя к объекту (часть 2 §5), главные — первыми; подписи — по фонду сегодня,
    выбывшее из фонда — «#id». priority: больше — важнее."""
    rows = list(db.scalars(select(GuestPref).where(GuestPref.guest_id == guest_id)
                           .order_by(GuestPref.priority.desc(), GuestPref.id)))
    if not rows:
        return []
    today = local_date()
    timeline = fund_for(db, today, today)
    snap = timeline.on(today) if timeline.parts else None
    flags = {f.id: f.title for f in db.scalars(select(UnitFlag).where(
        UnitFlag.id.in_([r.ref_id for r in rows if r.kind == "flag"])))}

    def title(r: GuestPref) -> str:
        if r.kind == "flag":
            return flags.get(r.ref_id, f"#{r.ref_id}")
        if snap is not None and r.kind == "group" and r.ref_id in snap.groups:
            return " / ".join(snap.path_titles(r.ref_id))
        unit = timeline.unit(r.ref_id, today) if r.kind == "unit" and snap is not None else None
        return unit.label if unit is not None else f"#{r.ref_id}"
    return [{"kind": r.kind, "ref_id": r.ref_id, "priority": r.priority, "title": title(r)} for r in rows]


def save_prefs(db: Session, guest_id: int, prefs: list[dict]) -> list[dict]:
    """Заменить пожелания гостя целиком: [{kind, ref_id, priority}]. Ввод — 422 (вид, повтор
    вида и объекта, несуществующий узел, флаг или объект), всё под замком модуля: пожелания
    читает распределение. Ничего не коммитит."""
    lock_module(db)
    if db.get(Guest, guest_id) is None:
        raise GuestError("Гость не найден")
    if len(prefs) > MAX_PREFS:
        raise GuestError(f"Пожеланий не больше {MAX_PREFS}")
    seen: set[tuple[str, int]] = set()
    for p in prefs:
        if p["kind"] not in PREF_KINDS:
            raise GuestError("Вид пожелания: узел, флаг или объект")
        if not 1 <= p["priority"] <= MAX_PRIORITY:
            raise GuestError(f"Приоритет — от 1 до {MAX_PRIORITY}")
        key = (p["kind"], p["ref_id"])
        if key in seen:
            raise GuestError("Одно и то же пожелание указано дважды")
        seen.add(key)
        if db.get(_PREF_REFS[p["kind"]], p["ref_id"]) is None:
            raise GuestError({"group": "Узла фонда нет", "flag": "Флага нет", "unit": "Объекта нет"}[p["kind"]])
    db.execute(delete(GuestPref).where(GuestPref.guest_id == guest_id))
    db.add_all(GuestPref(guest_id=guest_id, kind=p["kind"], ref_id=p["ref_id"], priority=p["priority"]) for p in prefs)
    db.flush()
    return prefs_of(db, guest_id)


def merge_prefs(db: Session, keep_id: int, drop_id: int) -> int:
    """Пожелания дубля — оставляемому без повторов: тот же вид и объект — приоритет keep.
    Массовыми запросами, как покрытие: без связи в ORM порядок с удалением гостя не определён."""
    mine = {(p.kind, p.ref_id) for p in db.scalars(select(GuestPref).where(GuestPref.guest_id == keep_id))}
    theirs = list(db.scalars(select(GuestPref).where(GuestPref.guest_id == drop_id)))
    dup = [p.id for p in theirs if (p.kind, p.ref_id) in mine]
    if dup:
        db.execute(delete(GuestPref).where(GuestPref.id.in_(dup)))
    db.execute(update(GuestPref).where(GuestPref.guest_id == drop_id).values(guest_id=keep_id))
    # не больше MAX_PREFS (иначе карточку нельзя сохранить): остаются самые важные
    ids = list(db.scalars(select(GuestPref.id).where(GuestPref.guest_id == keep_id)
                          .order_by(GuestPref.priority.desc(), GuestPref.id)))
    if len(ids) > MAX_PREFS:
        db.execute(delete(GuestPref).where(GuestPref.id.in_(ids[MAX_PREFS:])))
    return len(theirs) - len(dup)
