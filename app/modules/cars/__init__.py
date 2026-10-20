"""Модуль cars — электрокары: парк, заряд/возврат, места, история и ночная
проверка каров (фаза C4, EXECUTION-SPEC-v2 §7).

Слои: application (сервис cars.py + catalog — публичная поверхность моделей),
adapters (orm — модели car_*), interface (роутер cars_api), domain/ports —
тривиальные (код перенесён «как есть»). Ночной обход каров связан с модулем
night через night.application.catalog (CarNightCheck.report — TYPE_CHECKING, R6).
"""
