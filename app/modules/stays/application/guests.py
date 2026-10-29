"""Профили гостей и связи «кто кому» (§3.2), поиск по ФИО, телефону и полям с флагом
«искать». Ничего не коммитит — commit в роутере."""
from __future__ import annotations

import datetime as dt
import json
import re

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from ..adapters.orm import CoverageGuest, CustomField, Guest, GuestLink, Occupant, Reservation
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


def guest_text(g: Guest, can_phone: bool) -> str:
    """Текст поиска по гостю. Телефон — персональные данные полного уровня: без права цифры
    телефона из текста убираются, иначе по ответу можно было бы подобрать номер."""
    text = g.search_text or ""
    digits = re.sub(r"\D", "", g.phone or "")
    return text if can_phone or not digits else text.replace(digits, "", 1)


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


# ── Объединение дублей (addendum §3) ──────────────────────────────────────

# поля профиля, которые у оставляемого гостя заполняются из дубля, если у него пусто
MERGE_PROFILE = ("first_name", "middle_name", "phone", "email", "birth_date", "gender", "external_id", "source")
FAMILY_KINDS = ("parent", "spouse")


def _symmetric(kind: str) -> bool:
    """Связь без направления (супруги, родственники, коллеги): A–B и B–A — одна связь."""
    a, b = LINK_KINDS.get(kind, ("", "-"))
    return a == b


Plan = list[tuple[GuestLink, str, int, int, GuestLink | None]]


def _plan_links(db: Session, keep_id: int, drop_id: int) -> Plan:
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


def _apply_links(db: Session, plan: Plan, keep_id: int) -> list[dict]:
    others = {a if b == keep_id else b for _, _, a, b, _ in plan}
    names = {g.id: short_name(g) for g in db.scalars(select(Guest).where(Guest.id.in_(others)))} if others else {}
    out = [{"guest_id": (a if b == keep_id else b), "name": names.get(a if b == keep_id else b, ""),
            "kind": ln.kind, "former": ln.former, "result": result} for ln, result, a, b, _ in plan]
    for ln, result, _, _, mine in plan:      # сначала удаления: перенос не должен задеть уникальность
        if result != "moved":
            db.delete(ln)
        if mine is not None:
            mine.former = False
    db.flush()
    for ln, result, a, b, _ in plan:
        if result == "moved":
            ln.guest_a_id, ln.guest_b_id = a, b
    db.flush()
    return out


def _nights_runs(rows: list[Occupant]) -> list[tuple[dt.date, dt.date, str]]:
    """Проживание одного человека в брони по ночам: главный, если хоть одна запись главная
    в эту ночь; подряд идущие ночи с одной ролью — одна запись."""
    roles: dict[dt.date, str] = {}
    for o in rows:
        d = o.date_from
        while d < o.date_to:
            roles[d] = "main" if o.role == "main" or roles.get(d) == "main" else "guest"
            d += dt.timedelta(days=1)
    runs: list[list] = []
    for d in sorted(roles):
        if runs and runs[-1][1] == d and runs[-1][2] == roles[d]:
            runs[-1][1] = d + dt.timedelta(days=1)
        else:
            runs.append([d, d + dt.timedelta(days=1), roles[d]])
    return [tuple(r) for r in runs]


def _merge_occupants(db: Session, keep_id: int, drop_id: int) -> list[dict]:
    """Записи «проживающий» дубля → оставляемому. Если оба живут в одной брони (Review Focus 1),
    их записи сливаются в записи одного человека: без дубля в составе, главный — там, где
    главным был любой из двух (двух главных на ночь у брони не бывает)."""
    drop_occ = list(db.scalars(select(Occupant).where(Occupant.guest_id == drop_id).order_by(Occupant.id)))
    rids = sorted({o.reservation_id for o in drop_occ})
    if not rids:
        return []
    keep_occ = list(db.scalars(select(Occupant).where(Occupant.guest_id == keep_id,
                                                      Occupant.reservation_id.in_(rids)).order_by(Occupant.id)))
    shared = {o.reservation_id for o in keep_occ}
    for o in drop_occ:
        if o.reservation_id not in shared:
            o.guest_id = keep_id
    for rid in sorted(shared):
        rows = [o for o in keep_occ + drop_occ if o.reservation_id == rid]
        runs = _nights_runs(rows)
        for o in rows:
            db.delete(o)
        db.add_all(Occupant(reservation_id=rid, guest_id=keep_id, date_from=a, date_to=b, role=role)
                   for a, b, role in runs)
    out = []
    for r in db.scalars(select(Reservation).where(Reservation.id.in_(rids)).order_by(Reservation.id)):
        r.version += 1                       # открытая форма брони со старым составом получит 409
        out.append({"id": r.id, "number": r.number, "shared": r.id in shared})
    db.flush()
    return out


def _merge_coverage(db: Session, keep_id: int, drop_id: int) -> int:
    """Строки покрытия, где дубль выбран явно, — на оставляемого (без повтора в строке)."""
    lines = set(db.scalars(select(CoverageGuest.coverage_id).where(CoverageGuest.guest_id == drop_id)))
    if not lines:
        return 0
    both = set(db.scalars(select(CoverageGuest.coverage_id).where(CoverageGuest.guest_id == keep_id,
                                                                  CoverageGuest.coverage_id.in_(lines))))
    if both:
        db.execute(delete(CoverageGuest).where(CoverageGuest.guest_id == drop_id,
                                               CoverageGuest.coverage_id.in_(both)))
    db.execute(update(CoverageGuest).where(CoverageGuest.guest_id == drop_id).values(guest_id=keep_id))
    return len(lines)


def _fill_missing(mine: dict, theirs: dict) -> list[str]:
    added = [k for k, v in theirs.items() if v not in (None, "") and mine.get(k) in (None, "")]
    mine.update({k: theirs[k] for k in added})
    return added


def _merge_profile(keep: Guest, drop: Guest) -> dict:
    """Значения оставляемого побеждают; недостающее берётся у дубля. Уровень VIP/VVIP дубля
    переходит, только если у оставляемого — обычный; примечания — оба, через перевод строки."""
    profile = [k for k in MERGE_PROFILE if not getattr(keep, k) and getattr(drop, k)]
    for k in profile:
        setattr(keep, k, getattr(drop, k))
    if keep.level == "regular" and drop.level != "regular":
        keep.level = drop.level
        profile.append("level")
    note = (drop.note or "").strip()
    if note and note not in (keep.note or ""):
        keep.note = f"{keep.note.rstrip()}\n{note}" if (keep.note or "").strip() else note
        profile.append("note")
    prefs = json.loads(keep.preferences_json or "{}")
    pref_added = _fill_missing(prefs, json.loads(drop.preferences_json or "{}"))
    keep.preferences_json = json.dumps(prefs, ensure_ascii=False)
    fields = json.loads(keep.fields_json or "{}")
    fields_added = _fill_missing(fields, json.loads(drop.fields_json or "{}"))
    keep.fields_json = json.dumps(fields, ensure_ascii=False)
    dates = json.loads(keep.special_dates_json or "[]")
    dates_added = [d for d in json.loads(drop.special_dates_json or "[]") if d not in dates]
    keep.special_dates_json = json.dumps(dates + dates_added, ensure_ascii=False)
    return {"profile": profile, "preferences": pref_added, "fields": fields_added, "special_dates": dates_added}


def _not_carried(dropped: dict, kept: dict) -> dict:
    """Что из профиля дубля не перешло оставляемому (значения keep победили) — только это
    пишется в журнал: персональных данных в аудите — не больше необходимого."""
    out: dict = {}
    for k, v in dropped.items():
        if k in ("id", "phone_display") or v in (None, "", [], {}) or (k == "level" and v == "regular"):
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


def merge_guests(db: Session, keep_id: int, drop_id: int) -> dict:
    """Объединить дубль drop в keep (addendum §3): проживания, строки покрытия, связи,
    предпочтения, особые даты, настраиваемые поля переходят к keep, профиль drop удаляется.
    Ввод — 422, нарушение семейного дерева — 409; все проверки — до первой записи.
    Предпросмотр — этот же код с откатом (preview.run_operation). Ничего не коммитит."""
    lock_module(db)
    if keep_id == drop_id:
        raise GuestError("Нельзя объединить гостя с самим собой")
    keep, drop = db.get(Guest, keep_id), db.get(Guest, drop_id)
    if keep is None or drop is None:
        raise GuestError("Гость не найден")
    plan = _plan_links(db, keep_id, drop_id)
    dropped = guest_dict(drop)
    reservations = _merge_occupants(db, keep_id, drop_id)
    coverage = _merge_coverage(db, keep_id, drop_id)
    links = _apply_links(db, plan, keep_id)
    merged = _merge_profile(keep, drop)
    db.delete(drop)
    db.flush()
    keep.search_text = guest_search_text(keep, searchable_codes(db, "guest"))
    db.flush()
    return {"keep_id": keep_id, "drop_id": drop_id, "not_carried": _not_carried(dropped, guest_dict(keep)),
            "moves": {"reservations": reservations, "links": links, "coverage": coverage, **merged}}
