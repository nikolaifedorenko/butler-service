"""Общие зависимости: локальное «объектовое» время, транслитерация, служебные хелперы."""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from zoneinfo import ZoneInfo

from .config import settings

TZ = ZoneInfo(settings.app_tz)

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def now_local() -> dt.datetime:
    """Текущее время объекта (наивный datetime в часовом поясе APP_TZ)."""
    return dt.datetime.now(TZ).replace(tzinfo=None)


def local_date() -> dt.date:
    return now_local().date()


def utc_to_local(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(TZ).replace(tzinfo=None)


def slugify_username(full_name: str, fallback: str = "user") -> str:
    """«Иванов Иван Иванович» → «ivanov.ivan.ivanovich»."""
    name = unicodedata.normalize("NFKD", (full_name or "").strip().lower())
    parts = [p for p in re.split(r"[\s\-.]+", name) if p]
    out = []
    for part in parts:
        translit = "".join(TRANSLIT.get(ch, ch if ch.isascii() and ch.isalnum() else "") for ch in part)
        if translit:
            out.append(translit)
    login = ".".join(out) if out else fallback
    return re.sub(r"[^a-z0-9._-]", "", login)[:48] or fallback


def month_name(month: int) -> str:
    names = ["январь", "февраль", "март", "апрель", "май", "июнь",
             "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
    return names[(month - 1) % 12]


WD_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def weekday_short(date: dt.date) -> str:
    return WD_SHORT[date.weekday()]
