"""
Базовый цикл объекта и индивидуальные шаблоны блоков.

Что откуда берётся:
  * «Смена 1» / «Смена 2» — БАЗОВЫЙ ЦИКЛ ОБЪЕКТА из общих настроек (цикл + опорная дата
    + смена блока + противофаза). Одинаков для всех сотрудников блока, действует на все месяцы.
  * «Пятидневка» — выходные дни у каждого свои (вс/пн, пт/сб, сб/вс…), поэтому шаблон
    хранится в истории блоков сотрудника (BlockAssignment.pattern_json), а не в настройках.
  * «Другие смены» — индивидуальный цикл (3/3, 1/3, сутки через трое, «РРВВРВ») или ручное заполнение.

Ручные ячейки графика — ИСКЛЮЧЕНИЯ (отпуск, больничный, подмена) и перекрывают шаблон.
Смена берётся из словаря такой, какой она была в эту дату (см. app/shiftrev.py).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .groups import GROUP_META, normalize_group
from .models import BlockAssignment, Employee, Setting
from .schedule_patterns import parse_custom_cycle

DEFAULT_BASE = {
    "cycle": "2/2",
    "anchor": "2024-01-01",          # любой день в прошлом, когда Смена 1 была РАБОЧЕЙ
    # Смена 2 работает в противофазе со Сменой 1 — системное правило (18.10.2026),
    # не настройка. Значение рабочего дня («Я 10,75»…) живёт в шаблоне сотрудника.
    "groups": {
        "Смена 1": {},
        "Смена 2": {},
        "Пятидневка": {"off_weekdays": [5, 6]},
    },
}

PATTERN_KINDS = ("base", "week5", "cycle", "manual")


def load_base_config(db: Session) -> dict:
    raw = {s.key: s.value for s in db.scalars(select(Setting).where(
        Setting.key.in_(["base_cycle", "base_anchor", "base_groups"])))}
    cfg = json.loads(json.dumps(DEFAULT_BASE))
    if raw.get("base_cycle"):
        cfg["cycle"] = raw["base_cycle"]
    if raw.get("base_anchor"):
        cfg["anchor"] = raw["base_anchor"]
    if raw.get("base_groups"):
        try:
            groups = json.loads(raw["base_groups"])
        except json.JSONDecodeError:
            groups = {}
        # старые названия блоков («Администрация») приводим к текущим
        cfg["groups"] = {normalize_group(k): v for k, v in (groups or {}).items()}
    return cfg


def save_base_config(db: Session, cfg: dict) -> None:
    def _set(key: str, value: str, desc: str):
        row = db.get(Setting, key)
        if row is None:
            row = Setting(key=key, description=desc)
            db.add(row)
        row.value = value

    groups = {normalize_group(k): v for k, v in (cfg.get("groups") or {}).items()}
    _set("base_cycle", cfg.get("cycle", "2/2"), "Базовый цикл смен 1/2 (2/2, 3/3, custom:РРВВ…)")
    _set("base_anchor", cfg.get("anchor", "2024-01-01"), "Опорная дата: день, когда Смена 1 была рабочей")
    _set("base_groups", json.dumps(groups, ensure_ascii=False),
         "Настройки блоков: смена и фаза (инверсия) / выходные пятидневки по умолчанию")


def parse_pattern(raw: str) -> dict:
    """Индивидуальный шаблон из BlockAssignment.pattern_json (пусто — нет шаблона)."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    kind = data.get("kind") or ""
    if kind not in PATTERN_KINDS:
        return {}
    return data


def dump_pattern(pattern: Optional[dict]) -> str:
    if not pattern:
        return ""
    clean = {k: v for k, v in pattern.items() if v not in (None, "", [])}
    return json.dumps(clean, ensure_ascii=False) if clean else ""


def validate_pattern(pattern: dict) -> str:
    """Проверка индивидуального шаблона; возвращает человекочитаемое описание."""
    kind = pattern.get("kind") or "base"
    value = (pattern.get("value") or "").strip()
    tail = f", значение {value}" if value else ""
    if kind not in PATTERN_KINDS:
        raise ValueError(f"Неизвестный тип шаблона: {kind}")
    if kind == "week5":
        off = set(pattern.get("off_weekdays") or [])
        if not off:
            raise ValueError("Для пятидневки выберите хотя бы один выходной день недели")
        if len(off) > 3:
            raise ValueError("Слишком много выходных: для пятидневки их два (максимум три)")
        return "Пятидневка, выходные: " + ", ".join(
            ["пн", "вт", "ср", "чт", "пт", "сб", "вс"][d] for d in sorted(off)) + tail
    if kind == "cycle":
        cycle = (pattern.get("cycle") or "").strip()
        if cycle.startswith("custom:"):
            parse_custom_cycle(cycle[7:])
            return f"Цикл «{cycle[7:]}»" + tail
        if not re.fullmatch(r"\d+\s*/\s*\d+", cycle):
            raise ValueError("Цикл задаётся как 3/3, 1/3, 4/2 или custom:РРВВРВ")
        w, o = (int(x) for x in re.split(r"\s*/\s*", cycle))
        if w <= 0 or o <= 0:
            raise ValueError("В цикле должны быть и рабочие, и выходные дни")
        return f"Цикл {w}/{o}" + tail
    if kind == "manual":
        return "Ячейки заполняются вручную (автоматически график не строится)"
    return "Базовый цикл объекта" + tail


class BlockIndex:
    """Записи блоков (block_assignments) в памяти: поиск без SQL.

    Зачем: сборка сетки графика и пересчёт диапазона спрашивают «в каком блоке
    сотрудник в эту дату» для КАЖДОЙ ячейки — это сотни однотипных запросов.
    Индекс загружает записи одним запросом (или строится из уже выбранных строк)
    и повторяет правило SQL: подходит запись со start_date <= date и
    (end_date is NULL или end_date >= date), берётся последняя по start_date.
    """

    def __init__(self, by_emp: dict[int, list[BlockAssignment]]):
        self._by_emp = by_emp

    @classmethod
    def load(cls, db: Session, emp_ids: Optional[list[int]] = None) -> BlockIndex:
        if emp_ids is not None and not emp_ids:
            return cls({})
        stmt = select(BlockAssignment)
        if emp_ids is not None:
            stmt = stmt.where(BlockAssignment.employee_id.in_(emp_ids))
        return cls.from_assignments(db.scalars(stmt))

    @classmethod
    def from_assignments(cls, assignments) -> BlockIndex:
        by_emp: dict[int, list[BlockAssignment]] = {}
        for a in assignments:
            by_emp.setdefault(a.employee_id, []).append(a)
        return cls(by_emp)

    def for_date(self, emp_id: int, date: dt.date) -> Optional[BlockAssignment]:
        best = None
        for a in self._by_emp.get(emp_id, ()):
            if a.start_date <= date and (a.end_date is None or a.end_date >= date):
                if best is None or a.start_date > best.start_date:
                    best = a
        return best


def assignment_for_date(db: Session, emp: Employee, date: dt.date,
                        index: Optional[BlockIndex] = None) -> Optional[BlockAssignment]:
    if index is not None:
        return index.for_date(emp.id, date)
    return db.scalar(select(BlockAssignment).where(
        BlockAssignment.employee_id == emp.id,
        BlockAssignment.start_date <= date,
        (BlockAssignment.end_date.is_(None)) | (BlockAssignment.end_date >= date),
    ).order_by(BlockAssignment.start_date.desc()))


def group_for_date(db: Session, emp: Employee, date: dt.date,
                   index: Optional[BlockIndex] = None) -> str:
    """Группа (блок) сотрудника на конкретную дату — по истории переводов между блоками."""
    a = assignment_for_date(db, emp, date, index=index)
    return normalize_group(a.group if a else (emp.schedule_group or ""))


def pattern_for_date(db: Session, emp: Employee, date: dt.date,
                     cfg: Optional[dict] = None, index: Optional[BlockIndex] = None) -> dict:
    """Эффективный шаблон сотрудника в дату: индивидуальный важнее общих настроек блока."""
    cfg = cfg or load_base_config(db)
    a = assignment_for_date(db, emp, date, index=index)
    group = normalize_group(a.group) if a else normalize_group(emp.schedule_group or "")
    own = parse_pattern(a.pattern_json) if a is not None else {}
    gcfg = (cfg.get("groups") or {}).get(group) or {}
    kind = own.get("kind") or GROUP_META.get(group, {}).get("kind") or "base"

    pat = {
        "kind": kind,
        "group": group,
        # значение рабочего дня (ключ CFG-WINDOWS, «Я 10,75»): своё из истории
        # переводов, иначе значение блока из общих настроек (18.10.2026)
        "value": own.get("value") or gcfg.get("value") or "",
        "shift_code": own.get("shift_code") or gcfg.get("shift_code") or "",
        # Смена 2 — всегда противофаза: системное правило, не настройка (18.10.2026)
        "invert": bool(own.get("invert", gcfg.get("invert", False)))
        or group == "Смена 2",
        "cycle": own.get("cycle") or "",
        "anchor": own.get("anchor") or "",
        "off_weekdays": list(own.get("off_weekdays") or gcfg.get("off_weekdays") or []),
        "label": own.get("label") or "",
    }
    if kind == "week5" and not pat["off_weekdays"]:
        pat["off_weekdays"] = [5, 6]
    return pat


def working_flag(cfg: dict, pat: dict, date: dt.date) -> bool:
    """Рабочий ли день по шаблону. Устойчиво к любой опорной дате (прошлой и будущей):
    фаза считается через математический остаток, отрицательные индексы корректны."""
    kind = pat.get("kind") or "base"

    if kind == "week5":
        off_weekdays = set(pat.get("off_weekdays") or [5, 6])
        return date.weekday() not in off_weekdays

    cycle = (pat.get("cycle") or "").strip() or (cfg.get("cycle") or "2/2")
    anchor_raw = pat.get("anchor") or cfg.get("anchor") or "2024-01-01"
    try:
        anchor = dt.date.fromisoformat(str(anchor_raw))
    except ValueError:
        anchor = dt.date(2024, 1, 1)
    idx = (date - anchor).days

    if cycle.startswith("custom:"):
        seq = parse_custom_cycle(cycle[7:])
        return seq[idx % len(seq)]
    m = re.fullmatch(r"(\d+)\s*/\s*(\d+)", cycle)
    if not m:
        raise ValueError(f"Некорректный цикл: {cycle}")
    work_n, off_n = int(m.group(1)), int(m.group(2))
    if work_n <= 0 or work_n + off_n <= 0:
        raise ValueError(f"Некорректный цикл: {cycle}")
    flag = (idx % (work_n + off_n)) < work_n
    return (not flag) if pat.get("invert") else flag


def is_working_date(db: Session, emp: Employee, date: dt.date, cfg: Optional[dict] = None,
                    index: Optional[BlockIndex] = None) -> bool:
    """Рабочий ли день по графику (без учёта ручных ячеек)."""
    cfg = cfg or load_base_config(db)
    pat = pattern_for_date(db, emp, date, cfg, index=index)
    if pat.get("kind") == "manual":
        return False
    try:
        return working_flag(cfg, pat, date)
    except ValueError:
        return False
