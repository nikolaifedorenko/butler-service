"""SettingsPort (2.6): разрешённый по сроку действия неизменяемый набор настроек
для периода, включая ретроспективные исправления; версии сохраняются с результатом."""
from __future__ import annotations

from typing import Protocol

from ..domain.settings.types import Settings
from ..domain.types.entities import Period


class SettingsPort(Protocol):
    def load(self, period: Period) -> Settings: ...
