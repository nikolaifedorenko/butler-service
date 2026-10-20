"""Публичная поверхность данных модуля cars (граница R3/R4, фаза C4).

Модели каров импортируют: night (CarNightCheck), employees (Employee.assigned_car
— TYPE_CHECKING), legacy-фасад app/models. Внутри модуля — ..adapters.orm напрямую.
"""
from ..adapters.orm import Car, CarHistory, CarLocation, CarNightCheck  # noqa: F401
