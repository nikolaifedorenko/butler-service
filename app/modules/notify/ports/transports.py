"""Порт транспорта доставки: контракт сбоя (TransportError).

Реализации — adapters/transports (Telegram Bot API и SMTP/MS Exchange, единственные
места, где приложение выходит в сеть). Оба транспорта принимают необязательный
«отправитель» (sender / mailer): в тестах его подменяют заглушкой, поэтому прогон
не зависит от интернета. Приложение и журнал работают с TransportError через этот
порт, не зная о транспорте (фаза C3).
"""
from __future__ import annotations


class TransportError(Exception):
    """Сбой доставки: сеть, неверный токен, отказ сервера, недозволенный отправитель.

    Сообщение предназначено пользователю и попадает в журнал отправок (колонка
    error), поэтому в нём не должно быть ни токена, ни пароля.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return self.message
