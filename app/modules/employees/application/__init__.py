"""Application-слой employees — публичная граница модуля (R3/R4).

Ре-экспорт: модели каталога (catalog), группы графика и имена (domain),
функции трудоустройства (employment). ``lifecycle`` здесь НАМЕРЕННО не
ре-экспортируется: он импортирует границу timesheet (base_schedule, catalog),
а timesheet — границу employees; ре-экспорт создал бы цикл инициализации
пакетов. Потребители внутри модуля импортируют ``.lifecycle`` напрямую.
"""
from ..domain.groups import (  # noqa: F401
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
from ..domain.names import TRANSLIT, slugify_username, suggest_genitive  # noqa: F401
from .catalog import (  # noqa: F401
    Department,
    EmergencyContact,
    Employee,
    EmploymentPeriod,
    PositionHistory,
    StatementKind,
    Subdivision,
)
from .employment import (  # noqa: F401
    close_period,
    employed_on,
    employed_ranges,
    ensure_periods,
    is_employed,
    last_day,
    open_period,
    periods_of,
    ranges_from_periods,
)
