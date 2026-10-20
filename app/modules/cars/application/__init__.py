"""Application-слой cars — публичная граница модуля (R3/R4): сервис cars.py
импортируют подмодулем (from app.modules.cars.application.cars import …),
модели — через catalog."""
from .catalog import Car, CarHistory, CarLocation, CarNightCheck  # noqa: F401
