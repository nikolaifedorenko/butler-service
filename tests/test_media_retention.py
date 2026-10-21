"""Сроки хранения медиа (аудит 21.10.2026, BUG-01; решение владельца В-8 — чистить раз в сутки)."""
from __future__ import annotations

import datetime as dt

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_photo_older_than_its_own_limit_is_removed(db, monkeypatch):
    """Фото 30 дней, видео 180: фото возрастом 60 дней удаляется (было — жило 180)."""
    from app.core import media
    from app.core.media import cleanup_photos, save_photo
    from app.core.time import now_local

    ph = save_photo(db, kind="night_item", ref_id=1, filename="old.png", blob=PNG,
                    user_id=None, user_name="")
    ph.created_at = now_local() - dt.timedelta(days=60)
    db.commit()
    monkeypatch.setattr(media, "_RULES_PROVIDER",
                        lambda db: {"photo_retention_days": 30, "video_retention_days": 180})
    assert cleanup_photos(db) >= 1
    db.refresh(ph)
    assert ph.path == ""          # файл удалён, запись осталась (история не теряется)


def test_media_cleanup_runs_once_a_day(app_stack, monkeypatch):
    """Фоновый поток чистит медиа не чаще раза в сутки (раньше — только при старте)."""
    from app.bootstrap import night_sync

    calls: list[int] = []
    monkeypatch.setattr("app.core.media.cleanup_photos", lambda db: calls.append(1) or 0)
    monkeypatch.setitem(night_sync._last_cleanup, "ts", 0.0)
    assert night_sync.run_media_cleanup_if_due() == 0
    assert night_sync.run_media_cleanup_if_due() is None     # сутки ещё не прошли
    assert calls == [1]
