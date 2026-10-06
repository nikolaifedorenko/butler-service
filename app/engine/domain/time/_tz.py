from functools import lru_cache
from zoneinfo import ZoneInfo


@lru_cache(maxsize=16)
def zone(tz: str) -> ZoneInfo:
    """Чистая функция-кэш: ZoneInfo по имени пояса (пояс приходит параметром)."""
    return ZoneInfo(tz)
