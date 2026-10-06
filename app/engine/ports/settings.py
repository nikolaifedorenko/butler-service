from typing import Protocol

from ..domain.settings.types import Settings
from ..domain.types.entities import Period


class SettingsPort(Protocol):
    def load(self, period: Period) -> Settings: ...
