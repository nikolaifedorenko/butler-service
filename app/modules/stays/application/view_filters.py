"""Общие для видов и списков параметры: ошибка ввода, фильтры (§7) и проверка объекта по ним.

Фильтры нужны и записывающим модулям (блоки, OOO), и представлениям, поэтому лежат отдельно от
``views``: тот, кто выше, их импортирует, а не наоборот.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from app.core.errors import Validation
from app.modules.fund.application.fund_versions import FundSnapshot

from .visibility import Level


class ViewError(Validation, ValueError):
    """Ошибка параметров вида → 422."""


@dataclass(frozen=True)
class BoardFilters:
    """Фильтры видов (§7): внутри измерения — «или», между измерениями — «и», флаги — все сразу.
    Узлы, категории, виды и флаги проверяются по фонду каждого дня (fund_match)."""
    group_ids: tuple[int, ...] = ()         # узлы дерева фонда: объекты их веток
    category_ids: tuple[int, ...] = ()
    flag_ids: tuple[int, ...] = ()
    kind_ids: tuple[int, ...] = ()          # виды категорий (справочник)
    floor: str | None = None
    escorted_only: bool = False             # шахматка и «Загрузка» — по объекту, «Брони» — по правилам брони
    special: bool = False                   # «◆ Особый гость» среди проживающих брони
    vip_code_ids: tuple[int, ...] = ()      # VIP-код брони — «или»
    employee_id: int | None = None          # «кто ведёт» — с задачи 14
    q: str = ""

    def for_level(self, level: Level) -> BoardFilters:
        """Поиск, «Особый гость» и VIP-код опираются на данные гостей: уровню occupancy они не
        применяются — иначе по ответу можно было бы подобрать фамилию или
        признак гостя."""
        return self if level != "occupancy" else replace(self, q="", special=False, vip_code_ids=(),
                                                         employee_id=None)


def fund_match(snap: FundSnapshot, unit_id: int | None, category_id: int | None, f) -> bool:
    """Проходит ли объект фильтры фонда (узел, категория, вид, флаги, этаж) в снимке дня.
    f — BoardFilters или DayFilters. Объекта нет в фонде дня — не проходит. Бронь без объекта
    (unit_id None) проверяется по категории; узел, флаги и этаж у неё не определены."""
    u = snap.units.get(unit_id) if unit_id is not None else None
    if unit_id is not None and u is None:
        return False
    if u is None and (f.group_ids or f.flag_ids or f.floor):
        return False
    cid = u.category_id if u is not None else category_id
    cat = snap.categories.get(cid)
    return ((not f.group_ids or bool(set(f.group_ids) & set(snap.unit_path(unit_id))))
            and (not f.category_ids or cid in f.category_ids)
            and (not f.kind_ids or (cat is not None and cat.kind_id in f.kind_ids))
            and (not f.flag_ids or set(f.flag_ids) <= u.flags)
            and (not f.floor or u.floor == f.floor))


REMOVED_PARAMS = ("building", "category_id", "kind", "kinds", "vip")


def fund_filter_dims(query_params, group_ids, category_ids, flag_ids, kind_ids, floor) -> dict:
    """Измерения фонда (§7) — повторяющиеся параметры запроса. Прежние одиночные параметры — 422, а
    не молча без фильтра: старый клиент иначе показал бы весь фонд как отфильтрованный."""
    old = [p for p in REMOVED_PARAMS if p in query_params]
    if old:
        raise ViewError(f"Параметр {', '.join(old)} больше не поддерживается: "
                        "group_ids, category_ids, flag_ids, kind_ids, special, vip_code_ids")
    return {"group_ids": tuple(group_ids), "category_ids": tuple(category_ids), "flag_ids": tuple(flag_ids),
            "kind_ids": tuple(kind_ids), "floor": floor or None}
