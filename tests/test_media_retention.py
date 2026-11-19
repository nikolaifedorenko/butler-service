"""Сроки хранения медиа."""
from __future__ import annotations

import datetime as dt

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_photo_older_than_its_own_limit_is_removed(db, monkeypatch):
    """Фото 30 дней, видео 180: фото возрастом 60 дней удаляется (было — жило 180)."""
    from app.core import media
    from app.core.media import cleanup_photos, save_photo
    from app.core.time import now

    ph = save_photo(db, kind="night_item", ref_id=1, filename="old.png", blob=PNG,
                    user_id=None, user_name="")
    ph.created_at = now() - dt.timedelta(days=60)
    db.commit()
    monkeypatch.setattr(media, "_RULES_PROVIDER",
                        lambda db: {"photo_retention_days": 30, "video_retention_days": 180})
    assert cleanup_photos(db) >= 1
    db.refresh(ph)
    assert ph.path == ""          # файл удалён, запись осталась (история не теряется)


def test_media_cleanup_is_a_daily_job(app_stack, monkeypatch):
    """Чистка медиа — задача очереди раз в сутки (раньше — поток, а до него только старт сервера)."""
    from app.bootstrap import modules
    from app.core.db import SessionLocal

    spec = next(s for s in modules.job_specs(modules.discover()) if s.name == "media_cleanup")
    assert spec.every_seconds == 24 * 3600
    calls: list[int] = []
    monkeypatch.setattr("app.core.media.cleanup_photos", lambda db: calls.append(1) or 3)
    handler = modules.job_handlers(modules.discover())["media_cleanup"]
    with SessionLocal() as db:
        assert handler(db, {}) == 3
    assert calls == [1]
