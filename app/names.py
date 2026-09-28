"""Склонение ФИО в родительный падеж («от кого?»).

В карточке сотрудника есть поле «ФИО в родительном падеже» — оно приоритетное.
Функция suggest_genitive() лишь *подсказывает* вариант по правилам русского языка
для типичных случаев (Иванов → Иванова, Федоренко → Федоренко, Анна → Анны,
Ильинична → Ильиничны, Толстая → Толстой). Подсказку всегда можно исправить
вручную: редкие и иностранные фамилии автоматика склоняет неидеально.

Порядок слов ожидается стандартный: Фамилия Имя Отчество.
"""
from __future__ import annotations

# Мужские имена на -а/-я: склоняются по «женскому» типу (Никита → Никиты),
# но пол сотрудника от них не определяется.
_MALE_A_NAMES = {"никита", "илья", "фома", "кузьма", "лука", "савва",
                 "данила", "гаврила", "тихоня", "ермило"}

# Слова женского рода на согласную (Любовь → Любови, а не «Любовя»).
_FEMALE_SOFT = {"любовь"}

# Имена с беглой гласной и прочие нерегулярные (Пётр → Петра, Лев → Льва).
_IRREGULAR = {"пётр": "петра", "петр": "петра", "лёв": "льва", "лев": "льва",
              "павел": "павла", "сон": "сна"}

# После этих букв в окончании пишем «и» вместо «ы» (Ольга → Ольги, Саша → Саши).
_SIBILANTS = "кгхжчшщй"

# Несклоняемые фамилии: на -ко, -их/-ых и пр.
_INDECLINABLE_LAST = ("ко", "их", "ых", "аго", "яго")

# Несклоняемые окончания (гласные, кроме а/я): Федоренко, Дюма? (нет — «а»), Хитрово, Гёте.
_INDECLINABLE_ENDS = "оеёуэюи"


def _looks_female(tokens: list[str]) -> bool:
    """Эвристика определения пола по фамилии и имени (нужна для склонения фамилии)."""
    if not tokens:
        return False
    if len(tokens) == 1:
        low = tokens[0].lower()
        return low.endswith(("ова", "ева", "ёва", "ина", "ына", "ая", "яя"))
    last, first = tokens[0].lower(), tokens[1].lower()
    if first in _MALE_A_NAMES:
        return False
    if last.endswith(("ова", "ева", "ёва", "ина", "ына", "ая", "яя")):
        return True
    if first in _FEMALE_SOFT:
        return True
    return first.endswith(("а", "я"))


def _decline(word: str, kind: str, female: bool) -> str:
    """kind: 'last' — фамилия, 'first' — имя, 'middle' — отчество, 'other' — прочее."""
    if not word:
        return word
    low = word.lower()
    if kind in ("first", "middle") and low in _IRREGULAR:
        irr = _IRREGULAR[low]
        return irr.capitalize() if word[:1].isupper() else irr   # Пётр → Петра, Лев → Льва
    if kind == "last" and not female:
        # прилагательные фамилии: Толстой → Толстого, Сухой → Сухого, Безуглий → Безуглого
        if low.endswith(("ой", "ый")):
            return word[:-2] + "ого"
        if low.endswith("ий"):
            return word[:-2] + "его"
    if kind == "last" and (low.endswith(_INDECLINABLE_LAST) or low.endswith(_INDECLINABLE_ENDS)):
        return word                                    # Федоренко, Седых, Хитрово
    end = low[-1]

    if end == "а":
        if kind == "last" and female:
            return word[:-1] + "ой"                    # Иванова → Ивановой, Путина → Путиной
        stem = word[:-1]
        return stem + ("и" if stem and stem[-1].lower() in _SIBILANTS else "ы")  # Анна → Анны, Ольга → Ольги

    if end == "я":
        if kind == "last" and low.endswith(("ая", "яя")):
            return word[:-2] + "ой"                    # Толстая → Толстой
        return word[:-1] + "и"                         # Илья → Ильи, Мария → Марии

    if end in _INDECLINABLE_ENDS:
        return word                                    # Хитрово, Гёте — не склоняются

    if end == "ь":
        if low in _FEMALE_SOFT:
            return word[:-1] + "и"                     # Любовь → Любови
        if female and kind == "last":
            return word                                # женские фамилии на -ь не склоняются
        return word[:-1] + "я"                         # Игорь → Игоря, Гоголь → Гоголя

    if end == "й":
        if female and kind == "last":
            return word
        return word[:-1] + "я"                         # Сергей → Сергея

    # обычный согласный
    if female and kind == "last":
        return word                                    # женские фамилии на согласную не склоняются
    return word + "а"                                  # Иванов → Иванова, Сергеевич → Сергеевича


def suggest_genitive(full_name: str) -> str:
    """Родительный падеж ФИО: «Федоренко Николай Сергеевич» → «Федоренко Николая Сергеевича»."""
    tokens = (full_name or "").split()
    if not tokens:
        return ""
    female = _looks_female(tokens)
    kinds = ["last", "first", "middle"][:len(tokens)]
    kinds += ["other"] * max(0, len(tokens) - 3)
    return " ".join(_decline(t, k, female) for t, k in zip(tokens, kinds, strict=False))
