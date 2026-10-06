import datetime as dt


def check_aware(now: dt.datetime) -> None:
    """4.4: now — timezone-aware момент; naive datetime не допускается."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware UTC")
