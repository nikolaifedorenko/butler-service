"""validate_settings — композиция проверок уровня 1 (5.3): все нарушения сообщаются
разом (ConfigError). Вход — только Settings; проверки, требующие строк Табеля,
здесь запрещены (12.21)."""
from __future__ import annotations

from ..types.errors import ConfigError
from .checks.cascade_full import check_cascade_full
from .checks.categories_cover import check_categories_cover
from .checks.codes_exist import check_codes_exist
from .checks.defaults import check_defaults
from .checks.grid import check_grid
from .checks.modifier_conflict import check_modifier_conflict
from .checks.modifier_scope import check_modifier_scope
from .checks.modifier_type import check_modifier_type
from .checks.placement_full import check_placement_full
from .checks.step_divides_60 import check_step_divides_60
from .checks.weights_positive import check_weights_positive
from .checks.window_bounds import check_window_bounds
from .checks.window_key import check_window_key
from .checks.window_plan import check_window_plan
from .types import Settings

CHECKS = (check_window_plan, check_window_bounds, check_window_key, check_categories_cover,
          check_codes_exist, check_cascade_full, check_weights_positive, check_step_divides_60,
          check_grid, check_placement_full, check_defaults, check_modifier_scope,
          check_modifier_type, check_modifier_conflict)


def validate_settings(st: Settings) -> None:
    violations = [v for check in CHECKS for v in check(st)]
    if violations:
        raise ConfigError(violations)
