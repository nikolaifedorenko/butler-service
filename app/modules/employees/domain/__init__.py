"""Домен employees (R1, чистые функции): группы графика и склонение имён."""
from .groups import (  # noqa: F401
    GROUP_FIVEDAY,
    GROUP_META,
    GROUP_ORDER,
    GROUP_OTHER,
    GROUP_SHIFT1,
    GROUP_SHIFT2,
    LEGACY_NAMES,
    group_choices,
    group_index,
    group_kind,
    normalize_group,
    sorted_groups,
)
from .names import TRANSLIT, slugify_username, suggest_genitive  # noqa: F401
