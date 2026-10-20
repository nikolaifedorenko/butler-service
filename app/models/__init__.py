"""Модель данных системы учёта рабочего времени — пакет по поддоменам.

Раньше это был один файл app/models.py (808 строк). Разбиение механическое:
классы перенесены без изменений, этот файл — ре-экспортный фасад, поэтому все
существующие импорты `from ..models import X` продолжают работать.

SQLAlchemy разрешает межмодульные relationship() по имени класса в общем
реестре — важно лишь, чтобы все подмодули были импортированы (фасад это
гарантирует) до конфигурации мапперов.
"""
# Ядро (фаза C1, 20.10.2026): Base, идентичность (User, гранты), аудит и медиа
# переехали в app/core — фасад ре-экспортирует их, поэтому существующие импорты
# `from ..models import X` продолжают работать, а все модели регистрируются в
# общем реестре Base.metadata до create_all.
from ..core.audit import AuditLog  # noqa: F401
from ..core.db import Base  # noqa: F401 — исторически Base импортировали и из models
from ..core.identity import AccessGrant, AccessGroup, AccessGroupMember, User  # noqa: F401
from ..core.media import Photo  # noqa: F401
from ..core.roles import MANAGER_ROLES, ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_SUPERVISOR  # noqa: F401
from ..core.settings_store import Setting  # noqa: F401 — фаза C3: кросс-модульное key-value
from ..core.time import utcnow  # noqa: F401
from ..modules.cars.adapters.orm import Car, CarHistory, CarLocation, CarNightCheck  # noqa: F401 — фаза C4

# Фаза C2 (20.10.2026): модели Табеля/Графика/движка и каталога переехали в
# app/modules/timesheet/adapters/orm.py — фасад ре-экспортирует их (транзитный
# re-export по EXECUTION-SPEC-v2 §7 фаза 4; уменьшится в фазах C4–C6 и будет
# удалён вместе с пакетом app/models/).
from ..modules.employees.adapters.orm import (  # noqa: F401 — фаза C4: транзитный re-export
    Department,
    EmergencyContact,
    Employee,
    EmploymentPeriod,
    PositionHistory,
    StatementKind,
    Subdivision,
)
from ..modules.night.adapters.orm import (  # noqa: F401 — фаза C4: транзитный re-export
    ChecklistItem,
    ChecklistOverride,
    NightArea,
    NightAreaSection,
    NightCheckItem,
    NightInterception,
    NightReport,
    NightZone,
    ZoneChecklistItem,
)
from ..modules.notify.adapters.orm import (  # noqa: F401 — фаза C3: транзитный re-export
    NotifyChat,
    NotifyDispatch,
    NotifyTemplate,
    ResponsibilityService,
)
from ..modules.timesheet.adapters.orm import (  # noqa: F401
    BankAdjustment,
    BlockAssignment,
    DayModifier,
    DeferredCarry,
    DoublePayDay,
    EngineSettingsVersion,
    PeriodClosing,
    Punch,
    ScheduleAbsence,
    ScheduleShift,
    ShiftRevision,
    ShiftType,
    TabelDay,
    VipDoublePay,
)

__all__ = [
    "Base",
    "MANAGER_ROLES",
    "ROLE_ADMIN",
    "ROLE_EMPLOYEE",
    "ROLE_MANAGER",
    "ROLE_SUPERVISOR",
    "utcnow",
    "AccessGrant",
    "AccessGroup",
    "AccessGroupMember",
    "AuditLog",
    "Car",
    "CarHistory",
    "CarLocation",
    "CarNightCheck",
    "BankAdjustment",
    "BlockAssignment",
    "Department",
    "DoublePayDay",
    "EmergencyContact",
    "Employee",
    "EmploymentPeriod",
    "PositionHistory",
    "StatementKind",
    "Subdivision",
    "User",
    "VipDoublePay",
    "DayModifier",
    "DeferredCarry",
    "EngineSettingsVersion",
    "PeriodClosing",
    "Setting",
    "TabelDay",
    "Photo",
    "ChecklistItem",
    "ChecklistOverride",
    "NightArea",
    "NightAreaSection",
    "NightCheckItem",
    "NightInterception",
    "NightReport",
    "NightZone",
    "ZoneChecklistItem",
    "Punch",
    "ScheduleAbsence",
    "ScheduleShift",
    "ShiftRevision",
    "ShiftType",
]
