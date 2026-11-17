"""Публичная поверхность данных модуля guests (граница R3/R4): другие модули импортируют модели
гостей отсюда, а не из adapters."""
from ..adapters.orm import CustomField, Guest, GuestLink, GuestPref, VipCode  # noqa: F401
