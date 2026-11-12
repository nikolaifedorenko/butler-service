"""Блоки графика (группы строк в сетке) и их шаблоны.

Блоков четыре:
  * «Смена 1» и «Смена 2» — считаются БАЗОВЫМ ЦИКЛОМ ОБЪЕКТА из общих настроек
    (2/2, 3/3 … в противофазе), одинаково для всех сотрудников блока;
  * «Пятидневка» — у каждого сотрудника СВОИ выходные (у начальника вс/пн,
    у бэк-специалиста сб/вс), поэтому шаблон хранится в истории блоков, а не в настройках;
  * «Другие смены» — контейнер для индивидуальных графиков: 3/3, 1/3, сутки через трое,
    произвольный цикл «РРВВРВ» или полностью ручное заполнение.

Индивидуальный шаблон лежит в BlockAssignment.pattern_json и имеет приоритет
над общими настройками блока.
"""
from __future__ import annotations

GROUP_SHIFT1 = "Смена 1"
GROUP_SHIFT2 = "Смена 2"
GROUP_FIVEDAY = "Пятидневка"
GROUP_OTHER = "Другие смены"

LEGACY_NAMES = {"Администрация": GROUP_FIVEDAY, "администрация": GROUP_FIVEDAY,
                "Админ": GROUP_FIVEDAY, "admin": GROUP_FIVEDAY}

GROUP_ORDER = [GROUP_SHIFT1, GROUP_SHIFT2, GROUP_FIVEDAY, GROUP_OTHER]

# kind — какой шаблон задаётся при переводе сотрудника в блок:
#   base   — базовый цикл объекта из настроек (противофаза смен 1/2)
#   week5  — пятидневка: выбираются выходные дни недели и смена
#   cycle  — индивидуальный цикл: 3/3, 1/3, 4/2, произвольная строка «РРВВ»
GROUP_META = {
    GROUP_SHIFT1: {"kind": "base", "title": "Смена 1",
                   "hint": "Дневная смена, базовый цикл объекта (2/2, 3/3…) в противофазе со Сменой 2"},
    GROUP_SHIFT2: {"kind": "base", "title": "Смена 2",
                   "hint": "Вторая (в т.ч. ночная) смена, базовый цикл объекта в противофазе со Сменой 1"},
    GROUP_FIVEDAY: {"kind": "week5", "title": "Пятидневка",
                    "hint": "Пять рабочих дней в неделю; выходные выбираются для каждого сотрудника "
                            "(вс/пн, пт/сб, сб/вс…)"},
    GROUP_OTHER: {"kind": "cycle", "title": "Другие смены",
                  "hint": "Индивидуальный график: 3/3, 1/3, сутки через трое, произвольный цикл «РРВВ» "
                          "или ручное заполнение ячеек"},
}


def normalize_group(name: str | None) -> str:
    """«Администрация» → «Пятидневка» (старые базы и старые названия блоков)."""
    raw = (name or "").strip()
    return LEGACY_NAMES.get(raw, raw)


def group_kind(group: str | None) -> str:
    return GROUP_META.get(normalize_group(group), {}).get("kind", "base")


def group_choices() -> list[dict]:
    """Список блоков для интерфейса (порядок = порядок строк в сетке)."""
    return [{"name": g, "kind": GROUP_META[g]["kind"], "title": GROUP_META[g]["title"],
             "hint": GROUP_META[g]["hint"]} for g in GROUP_ORDER]


def group_index(name: str | None) -> int:
    g = normalize_group(name)
    return GROUP_ORDER.index(g) if g in GROUP_ORDER else len(GROUP_ORDER)


def sorted_groups(names) -> list[str]:
    return sorted(set(names), key=lambda n: (group_index(n), n or ""))
