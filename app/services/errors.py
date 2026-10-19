"""Доменные ошибки сервисного слоя.

Сервисы не знают про FastAPI и не бросают HTTPException: они бросают эти
исключения с готовым текстом для пользователя, а `app/main.py` маппит их
в HTTP-статусы обработчиками (NotFound→404, Forbidden→403, Validation→422,
Conflict→409, Gone→410). Тело ответа остаётся прежним — `{"detail": текст}`,
поэтому контракты API и тесты не меняются.

Исключение (переходное, зафиксировано в ADR-0006): `app/auth.py:can_manage_user`
исторически бросает HTTPException(403) и используется как единый страж прав
из многих мест — сервисы вызывают его как есть.
"""
from __future__ import annotations


class ServiceError(Exception):
    """Базовая ошибка use-case'а: сообщение предназначено пользователю."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


class NotFound(ServiceError):
    """Объект не найден → 404."""


class Forbidden(ServiceError):
    """Недостаточно прав → 403."""


class Validation(ServiceError):
    """Некорректные данные запроса → 422."""


class Conflict(ServiceError):
    """Конфликт состояния (например, запись уже удалена/закрыта) → 409."""


class Gone(ServiceError):
    """Объект навсегда недоступен (файл удалён по сроку хранения) → 410."""


class PayloadTooLarge(ServiceError):
    """Загружаемый файл больше настроенного лимита → 413.

    Лимиты задаёт объект («прочие правила»: photo_max_mb, video_max_mb), поэтому
    проверка размера живёт в сервисном слое рядом с сохранением файла, а не
    константой в api-модуле."""
