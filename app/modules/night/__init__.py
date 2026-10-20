"""Модуль night — ночной отчёт v2: зоны, объекты, чек-листы, недостатки смены,
электрокары ночного обхода, журнал и выгрузки (фаза C4, EXECUTION-SPEC-v2 §7).

Слои: application (жизненный цикл отчёта night.py, выгрузки night_export.py,
доставка службам night_notify.py, catalog — публичная поверхность моделей),
adapters (orm — модели night_*), interface (роутер night_api), domain/ports —
тривиальные (код перенесён «как есть», вытаскивание домена — отдельная задача).

Доставка — через notify.application (R3); электрокары — через cars (C4c,
пока транзитом G3 через app.cars/app.models).
"""
