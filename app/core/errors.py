"""Ошибки прикладного слоя.

Прикладной слой не знает про FastAPI и не бросает ``HTTPException``: он бросает эти
исключения с готовым текстом для пользователя. ``app/main.py`` переводит любое из них в
ответ одним обработчиком: статус — ``status_code`` класса, тело — ``{"detail": ...}``.
Модуль объявляет свои ошибки наследниками этих классов.
"""
from __future__ import annotations

from typing import Any


class ServiceError(Exception):
    """Отказ операции: сообщение предназначено пользователю."""

    status_code = 400

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return self.message

    @property
    def detail(self) -> Any:
        """Тело ответа под ключом ``detail``: текст либо словарь с данными для интерфейса."""
        return self.message


class Rejected(ServiceError):
    """Операция отклонена правилом → 400."""

    status_code = 400


class NotFound(ServiceError):
    """Объект не найден → 404."""

    status_code = 404


class Forbidden(ServiceError):
    """Недостаточно прав → 403."""

    status_code = 403


class Validation(ServiceError):
    """Некорректные данные запроса → 422."""

    status_code = 422


class Conflict(ServiceError):
    """Конфликт состояния (запись уже изменена, удалена или закрыта) → 409."""

    status_code = 409


class ConfirmationRequired(Conflict):
    """Операция выполнится только после подтверждения пользователя → 409.

    Тело ответа — словарь: данные для интерфейса и ``message`` с вопросом. Интерфейс
    показывает вопрос и повторяет запрос с подтверждением.
    """

    def __init__(self, message: str, **data: Any):
        super().__init__(message)
        self.data = data

    @property
    def detail(self) -> dict:
        return {**self.data, "message": self.message}


class Gone(ServiceError):
    """Объект навсегда недоступен (файл удалён по сроку хранения) → 410."""

    status_code = 410


class PayloadTooLarge(ServiceError):
    """Загружаемый файл больше лимита, который задают настройки объекта → 413."""

    status_code = 413
