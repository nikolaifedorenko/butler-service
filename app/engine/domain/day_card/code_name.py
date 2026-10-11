"""Имя кода УТ (CFG-WEIGHTS, единая нотация): `<категория>` + пустая строка при весе 1,
иначе десятичная запись веса слитно («ДЯ», «ДН», «ДЯ2», «ДН2»)."""
from __future__ import annotations


def code_name(category_code: str, weight: int) -> str:
    return category_code + ("" if weight == 1 else str(weight))
