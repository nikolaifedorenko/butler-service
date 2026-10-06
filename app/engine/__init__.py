"""Расчётный движок учёта переработок и банка часов (спецификация v4).

Слои (чистая архитектура):
  domain       — чистое ядро: settle() и evaluate_flags(); не знает никого;
  ports        — Protocol-контракты доступа к данным и сохранению;
  application  — use case'ы view_period / close_period / recalculate;
  adapters     — реализации портов поверх БД прототипа (SQLAlchemy);
  interface    — человекочитаемые тексты и сериализация для HTTP.
"""
