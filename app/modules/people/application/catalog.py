"""Публичная поверхность данных модуля people (граница R3/R4).

Другие модули импортируют модели отсюда (или из ``people.application``): ``adapters`` —
приватный слой модуля (R3).
"""
from ..adapters.orm import (  # noqa: F401
    Department,
    EmergencyContact,
    Employee,
    EmploymentPeriod,
    PositionHistory,
    Subdivision,
)
