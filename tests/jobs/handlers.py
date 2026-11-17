"""Обработчики для проверки подключения задач из манифестов."""
CALLS: list[int] = []


def record(_db, _payload) -> None:
    CALLS.append(1)
