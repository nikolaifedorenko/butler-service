"""Модель данных системы учёта рабочего времени — пакет по поддоменам.

Раньше это был один файл app/models.py (808 строк). Разбиение механическое:
классы перенесены без изменений, этот файл — ре-экспортный фасад, поэтому все
существующие импорты `from ..models import X` продолжают работать.

SQLAlchemy разрешает межмодульные relationship() по имени класса в общем
реестре — важно лишь, чтобы все подмодули были импортированы (фасад это
гарантирует) до конфигурации мапперов.
"""
from ..db import Base  # noqa: F401 — исторически Base импортировали и из models
from .access import AccessGrant, AccessGroup, AccessGroupMember  # noqa: F401
from .audit import AuditLog  # noqa: F401
from .cars import Car, CarHistory, CarLocation, CarNightCheck  # noqa: F401
from .common import MANAGER_ROLES, ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_SUPERVISOR, utcnow  # noqa: F401
from .directory import (  # noqa: F401
    BankAdjustment,
    BlockAssignment,
    Department,
    DoublePayDay,
    EmergencyContact,
    Employee,
    EmploymentPeriod,
    PositionHistory,
    StatementKind,
    Subdivision,
    User,
    VipDoublePay,
)
from .engine_store import DayModifier, DeferredCarry, EngineSettingsVersion, PeriodClosing, Setting, TabelDay  # noqa: F401
from .media import Photo  # noqa: F401
from .night import (  # noqa: F401
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
from .punch import Punch  # noqa: F401
from .schedule import ScheduleAbsence, ScheduleShift, ShiftRevision, ShiftType  # noqa: F401

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
