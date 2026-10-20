"""Модуль timesheet — Табель, График, отметки и расчётный движок v7.1.

Бывший app/engine/ (расчётный движок) плюс табельные роутеры, хелперы и ORM-модели
(фаза C2, EXECUTION-SPEC-v2 §7). Слои (чистая архитектура):
  domain       — чистое ядро: settle() и evaluate_flags(); не знает никого;
  ports        — Protocol-контракты доступа к данным и сохранению;
  application  — use case'ы view_period / close_period / recalculate
                 + табельные хелперы (base_schedule, tabel_fill, engine_common, …);
  adapters     — реализации портов поверх БД (SQLAlchemy) + ORM-модели (orm.py);
  interface    — человекочитаемые тексты, сериализация и FastAPI-роутеры.
  bootstrap    — сборка движка при старте (бывший app/engine_bootstrap).
"""
