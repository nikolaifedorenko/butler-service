"""Настройки движка: версии справочников Т1–Т7, Т9, Т-Группы и модификаторы дня Т4."""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.format import normalize_hex_color
from app.core.permissions import require_perm

from ..adapters.orm import DayModifier, EngineSettingsVersion
from ..adapters.settings_codec import from_payload, to_payload
from ..adapters.sql_settings import SCOPE_GROUPS, SqlSettingsAdapter, base_version
from ..domain.settings.defaults import default_settings
from ..domain.settings.types import (
    MOD_COUNTS_IN_UT,
    MOD_DOUBLE,
    MOD_PLAN_EQUALS_FACT,
    MODIFIER_NAMES,
)
from ..domain.settings.validate import validate_settings
from ..domain.types.entities import Period
from ..domain.types.errors import ConfigError
from .formatting import error_text

router = APIRouter(prefix="/api/engine-settings", tags=["engine-settings"])
MODIFIER_TITLES = {"double_overtime": "Двойные переработки", "pays_overtime": "Оплачиваются ли переработки",
                   "plan_equals_fact": "План=Факт", "counts_in_ut": "Учитываются ли часы в УТ"}


@router.get("")
def get_settings(on: Optional[dt.date] = None, principal: Principal = Depends(require_perm("settings.view")),
                 db: Session = Depends(get_db)):
    day = on or dt.date.today()
    ver = base_version(db, day)
    payload = json.loads(ver.payload_json) if ver else to_payload(default_settings())
    versions = db.scalars(select(EngineSettingsVersion).order_by(EngineSettingsVersion.valid_from.desc(),
                                                                 EngineSettingsVersion.id.desc()).limit(50))
    return {"active": {"id": ver.id if ver else None, "valid_from": ver.valid_from.isoformat() if ver else None,
                       "payload": payload},
            "versions": [{"id": v.id, "valid_from": v.valid_from.isoformat(), "note": v.note,
                          "created_by": v.created_by_name, "created_at": v.created_at.isoformat()} for v in versions],
            "modifier_names": [{"name": n, "title": MODIFIER_TITLES[n]} for n in MODIFIER_NAMES]}


class SettingsIn(BaseModel):
    valid_from: dt.date
    payload: dict
    note: str = ""


def applies_from(valid_from: dt.date, granularity: str) -> dt.date:
    """Дата начала первого периода, который посчитается по новой версии.

    Версия выбирается по дате НАЧАЛА периода (`base_version(db, period.start)`), а не
    подневно, поэтому любая дата внутри периода эквивалентна началу следующего —
    интерфейс показывает эту дату ДО публикации, чтобы «действует с 12.10» не
    выглядело как «уже сегодня» (дефект D25, план §4.3).
    """
    from ..application.months import next_period, period_containing

    period = period_containing(valid_from, granularity)
    return period.start if period.start >= valid_from else next_period(period, granularity).start


def period_state_of(db: Session, start: dt.date) -> dict:
    """Закрыт ли период, начинающийся `start`, и доступен ли ему пересчёт."""
    from ..adapters.orm import PeriodClosing

    closed = db.scalar(select(func.max(PeriodClosing.period_start)))
    row = db.scalar(select(PeriodClosing).where(PeriodClosing.period_start == start).limit(1))
    return {"closed": row is not None,
            "last_closed_start": closed.isoformat() if closed else None,
            "recalc_available": row is not None and closed == start}


@router.put("")
def put_settings(data: SettingsIn, principal: Principal = Depends(require_perm("settings.edit")),
                 db: Session = Depends(get_db)):
    try:
        st = from_payload(data.payload)
        validate_settings(st)
    except ConfigError as exc:
        # Редактор настроек валидирует ВВОД пользователя → 422 (в отличие от
        # центрального хэндлера ConfigError → 409 «повреждённое состояние»,
        # main.py §5.3); закреплено test_engine_settings_validation.
        raise HTTPException(status_code=422, detail=error_text(exc))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Некорректный формат настроек: {exc}")
    # Цвета кодов Табеля попадают во фронтенде в атрибут style="…" (пилюли кодов,
    # таймлайн) — произвольная строка там означает HTML/CSS-инъекцию, поэтому формат
    # жёсткий, как для цветов должностей и смен (normalize_hex_color). Заодно
    # канонизуем (нижний регистр) перед сохранением версии.
    for code, pol in (data.payload.get("day_code_policy") or {}).items():
        if not isinstance(pol, dict):
            continue
        color = pol.get("color")
        if color not in (None, ""):
            try:
                pol["color"] = normalize_hex_color(color, "#8a94a6")
            except ValueError as exc:
                raise HTTPException(status_code=422,
                                    detail=f"Цвет кода Табеля «{code}»: {exc}")
    _guard_removed_day_codes(data.payload, db)
    v = EngineSettingsVersion(valid_from=data.valid_from, payload_json=json.dumps(data.payload, ensure_ascii=False),
                              note=data.note[:255], created_by_name=principal.name)
    db.add(v)
    db.flush()
    audit(db, principal, "engine_settings", f"settings:{v.id}", {"valid_from": data.valid_from, "note": data.note})
    db.commit()
    start = applies_from(data.valid_from, st.period_granularity)
    return {"ok": True, "id": v.id, "applies_from": start.isoformat(),
            "period": period_state_of(db, start)}


def _guard_removed_day_codes(payload: dict, db: Session) -> None:
    """Удаление кода Табеля из справочника — с серверной защитой (16.10.2026).

    Владелец разрешил удалять коды из карточек «Коды Табеля», но версия, которая
    сломала бы расчёт, опубликована не будет: код, стоящий в Табеле, изъять нельзя
    (расчёт закрытых периодов сошёл бы с истории — UnknownDayCodeError,
    CHK-KNOWN-DAY-CODES), как и код, на который ссылается живой вид смены словаря
    (APP-SHIFT-CODE). Та же логика, что в strip_removed_day_codes для нормативных
    изъятий («С», «НВ», «НБ»), — только на публикации версии."""
    from ..adapters.orm import TabelDay

    new_codes = set((payload.get("day_code_policy") or {}).keys())
    prev = base_version(db, dt.date.today())
    if prev is None:
        return
    try:
        old_codes = set((json.loads(prev.payload_json).get("day_code_policy") or {}).keys())
    except (ValueError, TypeError, AttributeError):
        return
    removed = old_codes - new_codes
    if not removed:
        return
    used = sorted(set(db.scalars(select(TabelDay.code)
                                 .where(TabelDay.code.in_(removed)).distinct())))
    if used:
        listed = ", ".join(f"«{c}»" for c in used)
        raise HTTPException(status_code=422, detail=(
            f"Код {listed} нельзя удалить: в Табеле есть строки с ним. Сначала "
            "замените их другим кодом — на истории кода держится расчёт закрытых "
            "периодов."))


@router.get("/modifiers")
def list_modifiers(year: int, month: int, principal: Principal = Depends(require_perm("settings.view")),
                   db: Session = Depends(get_db)):
    first = dt.date(year, month, 1)
    last = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    rows = db.scalars(select(DayModifier).where(
        ((DayModifier.date >= first) & (DayModifier.date <= last)) | (DayModifier.period_start == first))
        .order_by(DayModifier.date, DayModifier.id))
    return [{"id": m.id, "name": m.name, "title": MODIFIER_TITLES.get(m.name, m.name), "value": m.value,
             "employee_id": m.employee_id, "group": m.group, "date": m.date.isoformat() if m.date else None,
             "period_start": m.period_start.isoformat() if m.period_start else None, "note": m.note,
             "created_by": m.created_by_name} for m in rows]


class ModifierIn(BaseModel):
    name: str
    value: str                       # "1" | "0" | "auto"
    employee_id: Optional[int] = None
    group: str = ""
    date: Optional[dt.date] = None
    period_start: Optional[dt.date] = None
    note: str = ""


def _scope_form(data: ModifierIn) -> tuple:
    """Форма области действия записи (CHK-MODIFIER-SCOPE): кто × день/период."""
    return (bool(data.employee_id), bool(data.group), bool(data.date), bool(data.period_start))


def _conflicting(db: Session, data: ModifierIn, period: Optional[Period],
                 granularity: str) -> Optional[DayModifier]:
    """Запись того же уровня приоритета, матчащая те же дни (CHK-MODIFIER-CONFLICT).

    Ищем до сохранения: конфликт, обнаруженный при загрузке настроек, останавливает
    расчёт всех вкладок периода, а исправить его можно только здесь. Форма области
    задаёт уровень один-в-один (3.5), поэтому сравниваем её, а не номер уровня:
    доменный `scope_level` принимает `ModifierEntry`, которого на стороне записи ещё нет.
    """
    form = _scope_form(data)
    q = select(DayModifier).where(DayModifier.name == data.name,
                                  DayModifier.employee_id == data.employee_id,
                                  DayModifier.group == (data.group or ""))
    for other in db.scalars(q):
        if (bool(other.employee_id), bool(other.group), bool(other.date),
                bool(other.period_start)) != form:
            continue
        if data.date is not None:
            if other.date == data.date:
                return other
            continue
        if period is None or other.period_start is None:
            continue
        other_end = _period_end_of(other.period_start, granularity)
        if max(other.period_start, period.start) <= min(other_end, period.end):
            return other
    return None


def _granularity(db: Session, on: dt.date) -> str:
    ver = base_version(db, on)
    if ver is None:
        return "month"
    try:
        return json.loads(ver.payload_json).get("period_granularity", "month")
    except (ValueError, TypeError):
        return "month"


def _period_end_of(start: dt.date, granularity: str) -> dt.date:
    """Конец периода записи: месяц либо половина месяца по гранулярности (R36)."""
    nxt = dt.date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    month_end = nxt - dt.timedelta(days=1)
    if start.day == 16:
        return month_end
    if start.day == 1 and granularity != "month":
        return dt.date(start.year, start.month, 15)
    return month_end


@router.post("/modifiers")
def add_modifier(data: ModifierIn, principal: Principal = Depends(require_perm("settings.edit")),
                 db: Session = Depends(get_db)):
    if data.name not in MODIFIER_NAMES:
        raise HTTPException(status_code=422, detail="Неизвестный модификатор")
    if data.value not in ("1", "0", "auto") or (data.value == "auto" and data.name != "plan_equals_fact"):
        raise HTTPException(status_code=422, detail="Значение: 1 / 0 (для «План=Факт» ещё auto)")
    if bool(data.date) == bool(data.period_start):
        raise HTTPException(status_code=422, detail="Укажите либо день, либо период (1-е число месяца)")
    if data.employee_id and data.group:
        raise HTTPException(status_code=422, detail="Область — сотрудник ИЛИ группа")
    granularity = _granularity(db, data.period_start or data.date or dt.date.today())
    period = None if data.date else Period(data.period_start,
                                           _period_end_of(data.period_start, granularity))
    conflict = _conflicting(db, data, period, granularity)
    if conflict is not None:
        scope = (f"сотрудник #{conflict.employee_id}" if conflict.employee_id
                 else f"группа «{conflict.group}»" if conflict.group else "все сотрудники")
        when = (f"{conflict.date:%d.%m.%Y}" if conflict.date else
                f"период с {conflict.period_start:%d.%m.%Y}")
        raise HTTPException(status_code=409, detail={
            "message": (f"Конфликт правил: «{MODIFIER_TITLES.get(data.name, data.name)}» уже задано "
                        f"для области «{scope}», {when} (запись #{conflict.id}"
                        + (f", автор {conflict.created_by_name}" if conflict.created_by_name else "")
                        + "). Два правила одного уровня на один день останавливают расчёт "
                          "(CHK-MODIFIER-CONFLICT) — удалите прежнее или сузьте область."),
            "conflict_with": {"id": conflict.id, "name": conflict.name, "value": conflict.value,
                              "employee_id": conflict.employee_id, "group": conflict.group or None,
                              "date": conflict.date.isoformat() if conflict.date else None,
                              "period_start": conflict.period_start.isoformat()
                              if conflict.period_start else None,
                              "author": conflict.created_by_name or ""}})
    m = DayModifier(**{**data.model_dump(), "created_by_name": principal.name})
    db.add(m)
    db.flush()
    audit(db, principal, "day_modifier_create", f"modifier:{m.id}", data.model_dump())
    db.commit()
    return {"id": m.id}


@router.delete("/modifiers/{mod_id}")
def delete_modifier(mod_id: int, principal: Principal = Depends(require_perm("settings.edit")),
                    db: Session = Depends(get_db)):
    m = db.get(DayModifier, mod_id)
    if not m:
        raise HTTPException(status_code=404, detail="Модификатор не найден")
    audit(db, principal, "day_modifier_delete", f"modifier:{m.id}", {"name": m.name, "date": m.date})
    db.delete(m)
    db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# «Обзор» и «Проверитель» раздела настроек (план SETTINGS-UI-PROPOSAL, этапы 1–2)
#
# Домен остаётся чистым (спека 2.4): прикладные сверки «группы ↔ блоки» и
# «коды Табеля ↔ словарь смен» живут здесь, а не в domain/settings/checks —
# они про данные приложения, а не про конфигурацию расчёта.
# ══════════════════════════════════════════════════════════════════════════

# Куда вести из замечания: id под-экрана раздела «Настройки»
CHECK_SCREENS = {
    "CHK-WINDOW-KEY": "codes", "CHK-WINDOW-BOUNDS": "codes", "CHK-WINDOW-PLAN": "codes",
    "CHK-WINDOW-EXISTS": "codes", "CHK-CODES-EXIST": "calc", "CHK-CATEGORIES-COVER": "calc",
    "CHK-CASCADE-FULL": "calc", "CHK-PLACEMENT-FULL": "calc", "CHK-WEIGHTS-POSITIVE": "calc",
    "CHK-STEP-DIVIDES-60": "calc", "CHK-GRID": "calc", "CHK-DEFAULTS": "pay",
    "CHK-MODIFIER-SCOPE": "pay", "CHK-MODIFIER-TYPE": "pay", "CHK-MODIFIER-CONFLICT": "pay",
}
SETTINGS_ACTIONS = ("engine_settings", "day_modifier_create", "day_modifier_delete",
                    "settings_update", "base_cycle_update", "doc_templates_update",
                    "shift_type_create", "shift_type_update", "shift_type_archive",
                    "doublepay_add", "doublepay_delete", "vip_add", "vip_delete")
CHAIN_FORMS = {1: "сотрудник + день", 2: "сотрудник + период", 3: "группа + день",
               4: "группа + период", 5: "все + день", 6: "все + период",
               7: "глобальный дефолт"}


def _mod_value_text(name: str, value) -> str:
    if name == MOD_PLAN_EQUALS_FACT:
        return {"yes": "Да", "no": "Нет", "auto": "Авто (по коду Табеля)"}.get(str(value), str(value))
    if isinstance(value, str):
        return {"1": "Да", "0": "Нет", "auto": "Авто"}.get(value, value)
    return "Да" if value else "Нет"


def _mod_value_raw(value) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if value in ("yes", "no"):
        return "1" if value == "yes" else "0"
    return str(value)


def _scope_text(entry) -> str:
    who = f"сотрудник #{entry.employee_id}" if entry.employee_id else (
        f"группа «{entry.group}»" if entry.group else "все")
    when = f"{entry.day:%d.%m.%Y}" if entry.day else (
        f"{entry.period.start:%d.%m.%Y}–{entry.period.end:%d.%m.%Y}" if entry.period else "—")
    return f"{who}, {when}"


def _app_checks(db: Session, payload: dict, day: dt.date) -> list[dict]:
    """Прикладные сверки D18/D19: то, что домен не знает (словарь смен, сотрудники, блоки)."""
    from app.groups import normalize_group

    from ..adapters.orm import Employee
    from ..application.base_schedule import load_base_config

    out: list[dict] = []
    codes = payload.get("day_code_policy") or {}

    # Значение рабочего дня — атрибут сотрудника (18.10.2026): без него цикл
    # не заполнит рабочие дни, поэтому подсвечиваем таких сотрудников заранее.
    from app.core.time import local_date

    from ..application.base_schedule import BlockIndex, pattern_for_date
    emps = list(db.scalars(select(Employee).where(Employee.deleted_at.is_(None))))
    if emps:
        cfg = load_base_config(db)
        index = BlockIndex.load(db, [e.id for e in emps])
        today = local_date()
        for e in emps:
            pat = pattern_for_date(db, e, today, cfg, index=index)
            if pat.get("kind") == "manual" or (pat.get("value") or "").strip():
                continue
            out.append({"code": "APP-EMP-NO-VALUE", "level": "warn", "screen": "employees",
                        "text": (f"У сотрудника «{e.full_name}» не задано значение рабочего "
                                 f"дня — рабочие дни не заполнятся из циклов. Выберите код "
                                 f"в карточке («Перевод в блок»)")})

    cfg_groups = set(payload.get("groups") or [])
    used = {normalize_group(e.schedule_group) for e in db.scalars(
        select(Employee).where(Employee.deleted_at.is_(None)))}
    blocks = set((load_base_config(db).get("groups") or {}).keys())
    for g in sorted(cfg_groups - used - blocks):
        out.append({"code": "APP-GROUP-UNUSED", "level": "warn", "screen": "groups",
                    "text": (f"Группа «{g}» есть в CFG-GROUPS, но не используется ни одним "
                             f"сотрудником и ни одним блоком базового цикла")})
    for g in sorted(used - cfg_groups):
        out.append({"code": "APP-GROUP-UNKNOWN", "level": "error", "screen": "groups",
                    "text": (f"У сотрудников указана группа «{g}», которой нет в CFG-GROUPS — "
                             f"расчёт остановится (CHK-GROUP-EXISTS)")})

    windows = payload.get("windows") or {}
    win_codes = {str(k).split(" ")[0] for k in windows}
    for code, row in codes.items():
        if bool(row.get("carries_hours")) and code not in win_codes:
            out.append({"code": "APP-CODE-NO-WINDOW", "level": "warn", "screen": "codes",
                        "text": (f"Код «{code}» несёт часы, но у него нет ни одного окна "
                                 f"(значения Табеля) — строку с таким кодом не сохранить")})

    # Справочники группы «Объект» (19.10.2026): ночной обход переехал в «Настройки»,
    # поэтому «Обзор» покрывает и его — пустой шаблон зоны и службы без канала доставки.
    # Места стоянки у каров НЕ проверяем: новый кар без места — норма (решение 18.10).
    out += _night_checks(db)
    return out


def _night_checks(db: Session) -> list[dict]:
    """Сверки справочника ночного обхода для экрана «Обзор»."""
    from app.models import ResponsibilityService
    from app.models.night import NightArea, NightZone, ZoneChecklistItem

    out: list[dict] = []
    zones = {z.id: z.name for z in db.scalars(
        select(NightZone).where(NightZone.active.is_(True)))}
    if zones:
        areas_by_zone = dict(db.execute(
            select(NightArea.zone_id, func.count(NightArea.id))
            .where(NightArea.active.is_(True), NightArea.zone_id.is_not(None))
            .group_by(NightArea.zone_id)).all())
        with_items = set(db.scalars(select(ZoneChecklistItem.zone_id)
                                    .where(ZoneChecklistItem.active.is_(True)).distinct()))
        for zid, zname in sorted(zones.items(), key=lambda kv: kv[1]):
            if areas_by_zone.get(zid) and zid not in with_items:
                out.append({"code": "APP-NIGHT-ZONE-NO-TEMPLATE", "level": "warn", "screen": "night",
                            "text": (f"Зона «{zname}»: в шаблоне чек-листа нет активных пунктов — "
                                     f"объекты зоны ({areas_by_zone[zid]}) проверяются только по "
                                     f"индивидуальным пунктам. Задайте шаблон в «Настройки → Ночной обход»")})
    for s in db.scalars(select(ResponsibilityService)
                        .where(ResponsibilityService.active.is_(True))
                        .order_by(ResponsibilityService.sort_order, ResponsibilityService.id)):
        chats = json.loads(s.chat_ids or "[]")
        tg_ready = bool(s.use_telegram and chats)
        mail_ready = bool(s.use_email and "@" in (s.email_to or ""))
        if not (tg_ready or mail_ready):
            out.append({"code": "APP-SVC-NO-CHANNEL", "level": "warn", "screen": "night",
                        "text": (f"Ответственная служба «{s.name}»: канал доставки не настроен — "
                                 f"недостатки по её пунктам никуда не отправляются "
                                 f"(«Настройки → Ночной обход → Службы»)")})
    return out


@router.get("/health")
def get_health(on: Optional[dt.date] = None, principal: Principal = Depends(require_perm("settings.view")),
               db: Session = Depends(get_db)):
    """Здоровье конфигурации + паспорт объекта для экрана «Обзор».

    Два слоя: (1) доменные проверки уровня 1 на payload действующей версии —
    те же CHK-*, что останавливают расчёт, но показанные ДО сохранения;
    (2) прикладные сверки (группы ↔ блоки, коды ↔ словарь смен, коды ↔ окна).
    """
    from app.core.audit import AuditLog
    from app.core.time import utc_to_local

    from ..application.months import period_containing
    from .formatting import config_violation_text

    day = on or dt.date.today()
    ver = base_version(db, day)
    payload = json.loads(ver.payload_json) if ver else to_payload(default_settings())
    checks: list[dict] = []
    try:
        validate_settings(from_payload({**payload, "modifiers": []}))
    except ConfigError as exc:
        for code, data in exc.violations:
            checks.append({"code": code, "level": "error", "screen": CHECK_SCREENS.get(code, "expert"),
                           "text": config_violation_text(code, dict(data))})
    except (KeyError, ValueError, TypeError) as exc:
        checks.append({"code": "CHK-PAYLOAD", "level": "error", "screen": "expert",
                       "text": f"Версия справочников повреждена: {exc}"})
    checks += _app_checks(db, payload, day)

    first = day.replace(day=1)
    last = dt.date(day.year + (day.month == 12), day.month % 12 + 1, 1) - dt.timedelta(days=1)
    active_rules = list(db.scalars(select(DayModifier).where(
        ((DayModifier.date >= first) & (DayModifier.date <= last)) | (DayModifier.period_start == first))))
    upcoming: list[dict] = []
    for v in db.scalars(select(EngineSettingsVersion).where(EngineSettingsVersion.valid_from > day)
                        .order_by(EngineSettingsVersion.valid_from).limit(10)):
        upcoming.append({"kind": "version", "date": v.valid_from.isoformat(), "screen": "calc",
                         "text": f"версия #{v.id}" + (f" — {v.note}" if v.note else "")})
    for m in db.scalars(select(DayModifier).where(
            or_(DayModifier.date > day, DayModifier.period_start > day))
            .order_by(DayModifier.date, DayModifier.id).limit(15)):
        who = (f"сотрудник #{m.employee_id}" if m.employee_id
               else f"группа «{m.group}»" if m.group else "все")
        upcoming.append({"kind": "rule", "screen": "pay",
                         "date": (m.date or m.period_start).isoformat(),
                         "text": f"правило #{m.id}: {MODIFIER_TITLES.get(m.name, m.name)} = "
                                 f"{_mod_value_text(m.name, m.value)}, {who}"})
    upcoming.sort(key=lambda x: x["date"])

    since = dt.datetime.combine(day - dt.timedelta(days=30), dt.time(0))
    recent = []
    for r in db.scalars(select(AuditLog).where(AuditLog.action.in_(SETTINGS_ACTIONS),
                                               AuditLog.ts >= since)
                        .order_by(AuditLog.ts.desc(), AuditLog.id.desc()).limit(12)):
        ts = utc_to_local(r.ts)
        recent.append({"ts": ts.isoformat(timespec="seconds") if ts else "", "actor": r.actor_name,
                       "action": r.action, "target": r.target})

    granularity = payload.get("period_granularity", "month")
    current = period_containing(day, granularity)
    from ..adapters.orm import PeriodClosing
    last_closed = db.scalar(select(func.max(PeriodClosing.period_start)))

    return {"on": day.isoformat(),
            "periods": {"granularity": granularity,
                        "current": {"start": current.start.isoformat(),
                                    "end": current.end.isoformat()},
                        "last_closed_start": last_closed.isoformat() if last_closed else None},
            "version": {"id": ver.id if ver else None,
                        "valid_from": ver.valid_from.isoformat() if ver else None,
                        "note": ver.note if ver else "",
                        "created_by": ver.created_by_name if ver else "",
                        "created_at": utc_to_local(ver.created_at).isoformat(timespec="seconds")
                        if ver and ver.created_at else ""},
            "stats": {"tz": payload.get("tz", ""), "step_minutes": payload.get("step_minutes"),
                      "period_granularity": payload.get("period_granularity", "month"),
                      "late_limit_minutes": payload.get("late_limit_minutes"),
                      "day_limit_minutes": payload.get("day_limit_minutes"),
                      "codes": len(payload.get("day_code_policy") or {}),
                      "windows": len(payload.get("windows") or {}),
                      "groups": len(payload.get("groups") or []),
                      "weights": len(payload.get("weights") or {}),
                      "rules_active": len(active_rules),
                      "rules_upcoming": sum(1 for u in upcoming if u["kind"] == "rule"),
                      "global_defaults": payload.get("global_defaults") or {}},
            "checks": checks, "upcoming": upcoming, "recent": recent}


def _rule_source(db: Session, entry, day: dt.date, version_id) -> dict:
    """Откуда взялась выигравшая запись: ручное правило, календарь, ВИП или версия."""
    from ..adapters.orm import DoublePayDay, VipDoublePay

    emp_id = int(entry.employee_id) if entry.employee_id else None
    q = select(DayModifier).where(DayModifier.name == entry.name,
                                  DayModifier.employee_id == emp_id,
                                  DayModifier.group == (entry.group or ""))
    for row in db.scalars(q):
        same_day = entry.day is not None and row.date == entry.day
        same_period = (entry.period is not None and row.period_start == entry.period.start)
        if same_day or same_period:
            return {"kind": "rule", "id": row.id, "author": row.created_by_name or "",
                    "note": row.note or "",
                    "text": f"правило #{row.id}" + (f" · {row.note}" if row.note else "")
                            + (f" · добавил(а) {row.created_by_name}" if row.created_by_name else "")}
    if entry.name == MOD_DOUBLE:
        scope_title = {"shift": "сменщики", "week5": "пятидневка", "all": "все"}
        for d in db.scalars(select(DoublePayDay).where(DoublePayDay.date == day)):
            if entry.group in SCOPE_GROUPS.get(d.scope, (None,)):
                return {"kind": "calendar", "id": d.id, "author": "", "note": d.note or "",
                        "text": (f"производственный календарь: день двойной оплаты "
                                 f"({scope_title.get(d.scope, d.scope)})"
                                 + (f" · {d.note}" if d.note else ""))}
        if emp_id:
            v = db.scalar(select(VipDoublePay).where(VipDoublePay.employee_id == emp_id,
                                                     VipDoublePay.start_date <= day,
                                                     VipDoublePay.end_date >= day))
            if v:
                return {"kind": "vip", "id": v.id, "author": "", "note": v.note or "",
                        "text": f"ВИП-период {v.start_date:%d.%m.%Y}–{v.end_date:%d.%m.%Y}"
                                + (f" · {v.note}" if v.note else "")}
    return {"kind": "static", "id": None, "author": "", "note": "",
            "text": f"статическое правило версии #{version_id}" if version_id
            else "статическое правило справочников по умолчанию"}


@router.get("/rules/resolve")
def resolve_rules(employee_id: int, date: dt.date, name: Optional[str] = None,
                  principal: Principal = Depends(require_perm("settings.view")),
                  db: Session = Depends(get_db)):
    """«Проверитель»: какое значение правила подействовало для сотрудника в день и почему.

    Приоритет 1–7 считается ДОМЕНОМ (`resolve_modifier_trace`) — тем же кодом, что и
    расчёт; здесь добавляются только объяснение источника и цепочка уровней.
    """
    from app.groups import normalize_group

    from ..adapters.orm import Employee, TabelDay
    from ..application.months import period_containing
    from ..domain.settings.resolve_modifier import resolve_modifier_trace
    from ..domain.types.entities import Day

    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    if name is not None and name not in MODIFIER_NAMES:
        raise HTTPException(status_code=422, detail="Неизвестный модификатор")
    granularity = _granularity(db, date)
    period = period_containing(date, granularity)
    # ConfigError → 422 — централизованный хэндлер main.py (§5.3)
    st = SqlSettingsAdapter(db).load(period)

    row = db.scalar(select(TabelDay).where(TabelDay.employee_id == employee_id, TabelDay.date == date))
    group = normalize_group(emp.schedule_group) or "Другие смены"
    code = row.code if row else ""
    day = Day(date, code or "В", int(row.plan_minutes) if row else 0, str(employee_id), group)
    out = []
    for mod in ([name] if name else list(MODIFIER_NAMES)):
        if mod == MOD_COUNTS_IN_UT and code not in st.day_code_policy:
            out.append({"name": mod, "title": MODIFIER_TITLES[mod], "value": None, "text": "—",
                        "level": None, "source": {"kind": "none", "id": None, "author": "", "note": "",
                                                  "text": ("В Табеле нет строки за этот день — "
                                                           "значение не разрешается")},
                        "chain": []})
            continue
        res = resolve_modifier_trace(mod, day, st)
        if res.entry is None:
            source = ({"kind": "code_column", "id": None, "author": "", "note": "",
                       "text": f"колонка «Учитывается в УТ» кода «{code}» (CFG-DAY-CODES)"}
                      if mod == MOD_COUNTS_IN_UT else
                      {"kind": "global_default", "id": None, "author": "", "note": "",
                       "text": f"глобальный дефолт версии #{st.versions[0][1:]}"
                               if st.versions and st.versions[0].startswith("v")
                               else "глобальный дефолт справочников"})
        else:
            source = _rule_source(db, res.entry, date,
                                  int(st.versions[0][1:]) if st.versions
                                  and st.versions[0].startswith("v") else None)
        out.append({"name": mod, "title": MODIFIER_TITLES[mod], "value": _mod_value_raw(res.value),
                    "text": _mod_value_text(mod, res.value), "level": res.level,
                    "scope": None if res.entry is None else _scope_text(res.entry),
                    "source": source,
                    "chain": [{"level": lv, "form": CHAIN_FORMS[lv], "hit": lv == res.level}
                              for lv in range(1, 8)]})
    return {"employee": {"id": emp.id, "name": emp.display_name or emp.full_name,
                         "full_name": emp.full_name, "group": group},
            "date": date.isoformat(), "code": code, "plan_minutes": int(row.plan_minutes) if row else 0,
            "period": {"start": period.start.isoformat(), "end": period.end.isoformat(),
                       "granularity": granularity},
            "version": {"id": int(st.versions[0][1:]) if st.versions and st.versions[0].startswith("v")
                        else None},
            "modifiers": out}
