"""Нужен ли батлер брони в ночь (§4.1) и вес места (§4.2) — чистые функции.

Правила — «или»: категория объекта, любой узел на пути объекта, VIP-код брони (архивный тоже),
«Особый гость» в брони или в любой брони её группы в эту ночь. Ручная отметка брони главнее
правил: «требуется» — нужен всегда, «гость отказался» — не нужен никогда."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

REQUIRED_REASON = "отмечено вручную"
DECLINED_REASON = "гость отказался"


@dataclass(frozen=True)
class EscortNeed:
    required: bool
    reasons: tuple[str, ...]
    declined: bool = False      # правила требуют батлера, а гость отказался


def escort_need(mode: str, *, category: tuple[str, bool], nodes: Sequence[tuple[str, bool]],
                code: tuple[str, str, bool] | None, specials: Sequence[str]) -> EscortNeed:
    """category=(title, escorted); nodes — путь объекта от корня [(title, escorted)];
    code=(code, title, escorted) или None; specials — короткие имена «Особых» брони и группы."""
    if mode == "required":
        return EscortNeed(True, (REQUIRED_REASON,))
    reasons: list[str] = []
    if category[1]:
        reasons.append(f"категория {category[0]}")
    reasons += [f"узел {title}" for title, escorted in nodes if escorted]
    if code is not None and code[2]:
        reasons.append(f"код {code[0]} — {code[1]}" if code[1] else f"код {code[0]}")
    reasons += [f"◆ Особый гость {name}" for name in specials]
    if mode == "declined":
        return EscortNeed(False, (DECLINED_REASON,), declined=bool(reasons))
    return EscortNeed(bool(reasons), tuple(reasons))


def place_weight(category_weight: float, code_factors: Iterable[float], special: bool,
                 special_factor: float) -> float:
    """Вес места: категория × max(коэффициенты кодов броней места; 1, если кодов нет) ×
    («Особый» в месте ? special_factor : 1) — «Особый» умножает один раз."""
    return round(category_weight * max(code_factors, default=1.0) * (special_factor if special else 1.0), 2)
