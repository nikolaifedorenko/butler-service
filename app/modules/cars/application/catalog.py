"""Публичная поверхность данных модуля cars (граница R3/R4, фаза C4).

Модели каров импортируют модули night и employees через их application-границы
(R3); кросс-модульных relationship нет — только строковые FK.
"""
from ..adapters.orm import Car, CarHistory, CarLocation, CarNightCheck  # noqa: F401
