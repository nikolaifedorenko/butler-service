from __future__ import annotations

from ..types.errors import ConfigError
from .checks.v1 import check_v1
from .checks.v2 import check_v2
from .checks.v3 import check_v3
from .checks.v4 import check_v4
from .checks.v5 import check_v5
from .checks.v6 import check_v6
from .checks.v7 import check_v7
from .checks.v8 import check_v8
from .checks.v9 import check_v9
from .checks.v10 import check_v10
from .checks.v11 import check_v11
from .checks.v_gr import check_v_gr
from .types import Settings

RULES = (check_v1, check_v2, check_v3, check_v4, check_v5, check_v6, check_v7,
         check_v8, check_v9, check_v10, check_v11, check_v_gr)


def _collect(st: Settings) -> list:
    return [v for rule in RULES for v in rule(st)]


def validate_settings(st: Settings) -> Settings:
    """Все нарушения В1–В11, В-Гр сообщаются разом (ConfigError)."""
    violations = _collect(st)
    if violations:
        raise ConfigError(violations)
    return st
