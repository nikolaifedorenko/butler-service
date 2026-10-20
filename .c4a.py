#!/usr/bin/env python3
"""C4a: создание границ employees + timesheet.catalog и переписывание импортов."""
import pathlib
import re
import sys

FAILS = []

def w(path, text):
    pathlib.Path(path).write_text(text, encoding="utf-8")
    print("создан:", path)

def rw(path, pairs, optional=False):
    p = pathlib.Path(path); t = p.read_text(encoding="utf-8"); n = 0
    for old, new in pairs:
        c = t.count(old)
        if c == 0:
            if not optional:
                FAILS.append(f"{path}: НЕ НАЙДЕНО {old[:80]!r}")
            continue
        t = t.replace(old, new); n += c
    p.write_text(t, encoding="utf-8")
    print(f"{path}: {n}")

def sed(path, patterns):
    p = pathlib.Path(path); t = p.read_text(encoding="utf-8"); n = 0
    for pat, rep in patterns:
        t, k = re.subn(pat, rep, t, flags=re.M); n += k
    p.write_text(t, encoding="utf-8")
    print(f"{path}: {n} (regex)")

EMP = "app/modules/employees"
TS = "app/modules/timesheet"

# ── 1. границы employees ──
w(f"{EMP}/__init__.py", '''"""Модуль employees — каталог персонала и жизненный цикл сотрудника (фаза C4).

Слои: domain (группы графика, склонение имён — чистые), application (каталог
моделей для других модулей, трудоустройство, жизненный цикл), ports (тривиальный
— контрактов пока нет), adapters (orm — Employee/Department/Subdivision/
StatementKind/EmergencyContact/PositionHistory/EmploymentPeriod), interface
(роутер «Сотрудники»).

Публичная поверхность (R3/R4): другие модули импортируют только
``employees.application`` (модели — через ``application.catalog``). Корневой
``__init__`` намеренно НЕ ре-экспортирует application: ``lifecycle`` импортирует
транзитный фасад ``app.models`` (Car, до фазы C4c), и ранний импорт application
из фасада создал бы цикл инициализации.
"""
''')
w(f"{EMP}/domain/__init__.py", '''"""Домен employees (R1, чистые функции): группы графика и склонение имён."""
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
''')
w(f"{EMP}/application/catalog.py", '''"""Публичная数据-поверхность модуля employees (граница R3/R4, фаза C4).

Другие модули и legacy-код импортируют модели каталога отсюда (или из
``employees.application``), а не из adapters напрямую: ``adapters`` — приватный
слой модуля (R3). Внутри модуля файлы импортируют ``..adapters.orm`` напрямую.
"""
from ..adapters.orm import (  # noqa: F401
    Department,
    EmergencyContact,
    Employee,
    EmploymentPeriod,
    PositionHistory,
    StatementKind,
    Subdivision,
)
'''.replace("数据", "данных"))
w(f"{EMP}/application/__init__.py", '''"""Application-слой employees — публичная граница модуля (R3/R4).

Ре-экспорт: модели каталога (catalog), группы графика и имена (domain),
функции трудоустройства (employment). ``lifecycle`` здесь НАМЕРЕННО не
ре-экспортируется: он импортирует транзитный фасад app.models (Car, до C4c),
и ре-экспорт создал бы риск цикла инициализации (фасад → employees → фасад);
потребители внутри модуля импортируют ``.lifecycle`` напрямую.
"""
from .catalog import (  # noqa: F401
    Department,
    EmergencyContact,
    Employee,
    EmploymentPeriod,
    PositionHistory,
    StatementKind,
    Subdivision,
)
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
''')
w(f"{EMP}/ports/__init__.py", '''"""Порты employees — тривиальный слой (контракты Protocol появятся по мере
вытаскивания use case'ов из lifecycle; фаза C4 переносит код «как есть»).''' + '"""\n')
w(f"{EMP}/adapters/__init__.py", '''"""Адаптеры employees: ORM-модели каталога (orm.py). Публичная поверхность —
application/catalog.py (R3)."""
''')
w(f"{EMP}/interface/__init__.py", '''"""Interface employees: роутер «Сотрудники» (employees.py)."""
''')

# ── 2. публичная поверхность timesheet (каталог моделей + адаптер настроек) ──
w(f"{TS}/application/catalog.py", '''"""Публичная данных-поверхность модуля timesheet (граница R3/R4, фаза C4).

Другие модули и legacy-код импортируют модели Табеля/Графика/движка и адаптер
настроек отсюда, а не из adapters напрямую (R3: чужие adapters — приватные).
Внутри модуля файлы импортируют ..adapters.* напрямую.
"""
from ..adapters.orm import (  # noqa: F401
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
from ..adapters.sql_settings import SqlSettingsAdapter, base_version  # noqa: F401
'''.replace("данных-поверхность", "данных-поверхность"))

# ── 3. импорты внутри перенесённых файлов ──
rw(f"{EMP}/application/employment.py", [
    ("from .models import Employee, EmploymentPeriod, utcnow",
     "from app.core.time import utcnow\n\nfrom ..adapters.orm import Employee, EmploymentPeriod"),
])
rw(f"{EMP}/application/lifecycle.py", [
    ("from ..core.audit import audit", "from app.core.audit import audit"),
    ("from ..core.auth import Principal", "from app.core.auth import Principal"),
    ("from ..core.auth_guards import can_manage_user", "from app.core.auth_guards import can_manage_user"),
    ("from ..core.errors import Conflict, NotFound, Validation", "from app.core.errors import Conflict, NotFound, Validation"),
    ("from ..core.time import local_date", "from app.core.time import local_date"),
    ("from ..employment import close_period, open_period, periods_of",
     "from .employment import close_period, open_period, periods_of"),
    ("from ..groups import GROUP_META, normalize_group",
     "from ..domain.groups import GROUP_META, normalize_group"),
    ("""from ..models import (
    ROLE_EMPLOYEE,
    BlockAssignment,
    Car,
    Employee,
    PositionHistory,
)""",
     """from app.core.roles import ROLE_EMPLOYEE
from app.models import Car  # транзит G3: до модуля cars (фаза C4c)
from app.modules.timesheet.application.catalog import BlockAssignment

from ..adapters.orm import Employee, PositionHistory"""),
    ("from ..modules.timesheet.application.base_schedule import dump_pattern, validate_pattern_label",
     "from app.modules.timesheet.application.base_schedule import dump_pattern, validate_pattern_label"),
])
rw(f"{TS}/application/shiftrev.py", [
    ("from .core.time import local_date", "from app.core.time import local_date"),
    ("from .models import ShiftRevision, ShiftType", "from ..adapters.orm import ShiftRevision, ShiftType"),
])

# ── 4. employees/interface/employees.py ──
rw(f"{EMP}/interface/employees.py", [
    ("from ..employment import open_period, periods_of", "from ..application.employment import open_period, periods_of"),
    ("from ..groups import group_choices as group_choices_list", "from ..application import group_choices as group_choices_list"),
    ("from ..groups import normalize_group", "from ..application import normalize_group"),
    ("""from ..models import (
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_MANAGER,
    BankAdjustment,
    BlockAssignment,
    Car,
    Department,
    EmergencyContact,
    Employee,
    PositionHistory,
    ShiftType,
    Subdivision,
    User,
    utcnow,
)""",
     """from app.core.identity import User
from app.core.roles import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_MANAGER
from app.core.time import utcnow
from app.models import Car  # транзит G3: до модуля cars (фаза C4c)
from app.modules.timesheet.application.catalog import BankAdjustment, BlockAssignment, ShiftType

from ..adapters.orm import Department, EmergencyContact, Employee, PositionHistory, Subdivision"""),
    ("from ..names import slugify_username, suggest_genitive", "from ..application import slugify_username, suggest_genitive"),
    ("from ..services import employee_lifecycle as lifecycle", "from ..application import lifecycle"),
    ("from ..services.employee_lifecycle import (", "from ..application.lifecycle import ("),
    ("from ..shiftrev import REV_FIELDS, add_revision, archive_shift, freeze_before_update",
     "from app.modules.timesheet.application.shiftrev import REV_FIELDS, add_revision, archive_shift, freeze_before_update"),
    ("from ..modules.timesheet.application.base_schedule import validate_pattern_label",
     "from app.modules.timesheet.application.base_schedule import validate_pattern_label"),
    ("from ..modules.timesheet.application.engine_common import (",
     "from app.modules.timesheet.application.engine_common import ("),
    ("from ..modules.timesheet.application import bank_adjustment",
     "from app.modules.timesheet.application import bank_adjustment"),
    ("from ..modules.timesheet.application.base_schedule import parse_pattern",
     "from app.modules.timesheet.application.base_schedule import parse_pattern"),
    ("from ..modules.timesheet.application.base_schedule import load_base_config, pattern_for_date",
     "from app.modules.timesheet.application.base_schedule import load_base_config, pattern_for_date"),
    ("from ..modules.timesheet.adapters.sql_settings import SqlSettingsAdapter",
     "from app.modules.timesheet.application.catalog import SqlSettingsAdapter"),
    ("from ..modules.timesheet.application.engine_common import day_code_rows",
     "from app.modules.timesheet.application.engine_common import day_code_rows"),
    ("from ..modules.timesheet.application.months import month_period",
     "from app.modules.timesheet.application.months import month_period"),
    ("from ..models import ShiftRevision", "from app.modules.timesheet.application.catalog import ShiftRevision"),
])
sed(f"{EMP}/interface/employees.py", [
    (r"^from \.\.core\.", "from app.core."),
    (r"^(\s+)from \.\.core\.", r"\1from app.core."),
])

# ── 5. timesheet: потребители groups/employment/names → employees.application ──
TS_FILES = [
    f"{TS}/adapters/sql_timesheet.py", f"{TS}/adapters/sql_employment.py",
    f"{TS}/adapters/sql_settings.py", f"{TS}/application/engine_common.py",
    f"{TS}/application/tabel_fill.py", f"{TS}/application/base_schedule.py",
    f"{TS}/interface/tabel_api.py", f"{TS}/interface/punches.py",
    f"{TS}/interface/schedule.py", f"{TS}/interface/engine_settings_api.py",
    f"{TS}/interface/fact_api.py", f"{TS}/interface/mgmt_api.py",
    f"{TS}/interface/presence_api.py", f"{TS}/interface/doublepay.py",
]
for f in TS_FILES:
    p = pathlib.Path(f)
    if not p.exists():
        continue
    t = p.read_text(encoding="utf-8")
    t2 = re.sub(r"^(\s*)from app\.groups import", r"\1from app.modules.employees.application import", t, flags=re.M)
    t2 = re.sub(r"^(\s*)from app\.employment import", r"\1from app.modules.employees.application import", t2, flags=re.M)
    t2 = re.sub(r"^(\s*)from app\.names import", r"\1from app.modules.employees.application import", t2, flags=re.M)
    if t2 != t:
        p.write_text(t2, encoding="utf-8")
        print(f, "-> employees.application")

# timesheet orm-импорты Employee/BlockAssignment в sql_timesheet: BlockAssignment свой, Employee — чужой
rw(f"{TS}/adapters/sql_timesheet.py", [
    ("from .orm import BlockAssignment, Employee, TabelDay",
     "from app.modules.employees.application import Employee\n\nfrom .orm import BlockAssignment, TabelDay"),
], optional=True)
rw(f"{TS}/adapters/sql_employment.py", [
    ("from .orm import Employee, EmploymentPeriod",
     "from app.modules.employees.application import Employee, EmploymentPeriod"),
], optional=True)
rw(f"{TS}/application/engine_common.py", [
    ("from ..adapters.orm import Employee, EmploymentPeriod, PeriodClosing",
     "from app.modules.employees.application import Employee, EmploymentPeriod\n\nfrom ..adapters.orm import PeriodClosing"),
], optional=True)
rw(f"{TS}/application/tabel_fill.py", [
    ("from ..adapters.orm import Employee, TabelDay",
     "from app.modules.employees.application import Employee\n\nfrom ..adapters.orm import TabelDay"),
], optional=True)
rw(f"{TS}/application/base_schedule.py", [
    ("from ..adapters.orm import BlockAssignment, Employee",
     "from app.modules.employees.application import Employee\n\nfrom ..adapters.orm import BlockAssignment"),
], optional=True)
rw(f"{TS}/bootstrap.py", [
    ("from .adapters.orm import Employee, EngineSettingsVersion, TabelDay",
     "from app.modules.employees.application import Employee\n\nfrom .adapters.orm import EngineSettingsVersion, TabelDay"),
], optional=True)

# ── 6. legacy-потребители ──
rw("app/grid_docx.py", [("from .groups import sorted_groups", "from app.modules.employees.application import sorted_groups")])
rw("app/doc_render.py", [("from .names import suggest_genitive", "from app.modules.employees.application import suggest_genitive")])
rw("app/models/cars.py", [("from .directory import Employee", "from app.modules.employees.application.catalog import Employee")])
rw("app/models/__init__.py", [
    ("""from ..modules.timesheet.adapters.orm import (  # noqa: F401
    BankAdjustment,
    BlockAssignment,
    DayModifier,
    DeferredCarry,
    Department,
    DoublePayDay,
    EmergencyContact,
    Employee,
    EmploymentPeriod,
    EngineSettingsVersion,
    PeriodClosing,
    PositionHistory,
    Punch,
    ScheduleAbsence,
    ScheduleShift,
    ShiftRevision,
    ShiftType,
    StatementKind,
    Subdivision,
    TabelDay,
    VipDoublePay,
)""",
     """from ..modules.employees.adapters.orm import (  # noqa: F401 — фаза C4: транзитный re-export
    Department,
    EmergencyContact,
    Employee,
    EmploymentPeriod,
    PositionHistory,
    StatementKind,
    Subdivision,
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
)"""),
])
rw("app/bootstrap/registry.py", [
    ("""    from app.modules.notify.adapters import orm as notify_orm  # noqa: F401
    from app.modules.timesheet.adapters import orm  # noqa: F401""",
     """    from app.modules.employees.adapters import orm as employees_orm  # noqa: F401
    from app.modules.notify.adapters import orm as notify_orm  # noqa: F401
    from app.modules.timesheet.adapters import orm  # noqa: F401"""),
    ("    from app.models import Employee\n", "    from app.modules.employees.adapters.orm import Employee\n"),
])
rw("app/main.py", [
    ("""from .api import (
    access_api,
    audit_api,
    auth_routes,
    cars_api,
    docs_api,
    employees,
    night_api,
    photos_api,
    settings_api,
)""",
     """from .api import (
    access_api,
    audit_api,
    auth_routes,
    cars_api,
    docs_api,
    night_api,
    photos_api,
    settings_api,
)
from .modules.employees.interface import employees"""),
])

if FAILS:
    print("\n!! ПРОБЛЕМЫ:")
    for f in FAILS:
        print(" ", f)
    sys.exit(1)
print("\nвсе замены применены")
