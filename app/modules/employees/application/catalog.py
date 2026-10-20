"""Публичная поверхность данных модуля employees (граница R3/R4, фаза C4).

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
