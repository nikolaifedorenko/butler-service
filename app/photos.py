"""Фотографии: хранение оригиналов на диске + срок хранения (настраиваемый).

Оригинал НЕ сжимается и не перекодировается: байты как пришли, так и лежат.
Папка: data/uploads/YYYY/MM/<uuid>.<ext> (путь в БД — относительный от корня проекта).
Отдача файла — только авторизованным пользователям через /api/photos/{id}/file
(в статическую раздачу папка не выкладывается).

Срок хранения задаётся правилом photo_retention_days (0 = хранить всегда);
устаревшие файлы удаляет cleanup_photos() при старте сервера. Запись в БД остаётся
(фото помечается как удалённое по сроку) — комментарии и история не теряются.
"""
from __future__ import annotations

import datetime as dt
import struct
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .deps import now_local
from .models import Photo

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_ROOT = BASE_DIR / "data" / "uploads"

ALLOWED_EXT = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
               "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}


def sniff_image(blob: bytes) -> str:
    """Определить тип картинки по «магическим байтам» (imghdr удалён из Python 3.13)."""
    head = blob[:32]
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if head[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "webp"
    if head[:2] == b"BM":
        return "bmp"
    if len(head) >= 12 and head[4:8] in (b"ftyp",):        # HEIC/HEIF — не отдаём как картинку
        return ""
    try:                                                    # TIFF (little/big endian)
        if struct.unpack("<H", head[:2])[0] == 42 or struct.unpack(">H", head[:2])[0] == 42:
            return ""
    except struct.error:
        pass
    return ""


def _safe_ext(filename: str, blob: bytes) -> Optional[str]:
    """Расширение: сначала по содержимому, затем по имени файла — но только картинка."""
    sniffed = sniff_image(blob)
    if sniffed:
        return sniffed
    declared = Path(filename or "").suffix.lower().lstrip(".")
    return declared if declared in ALLOWED_EXT and not blob[:4].startswith(b"%PDF") else None


def save_photo(db: Session, *, kind: str, ref_id: int, filename: str, blob: bytes,
               user_id: Optional[int], user_name: str) -> Photo:
    """Сохранить оригинал на диск и зарегистрировать в БД."""
    ext = _safe_ext(filename, blob)
    if ext is None:
        raise ValueError("Можно загружать только изображения (JPG, PNG, GIF, WEBP, BMP)")
    rel_dir = Path("data") / "uploads" / f"{now_local():%Y}" / f"{now_local():%m}"
    target_dir = BASE_DIR / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    (target_dir / name).write_bytes(blob)
    photo = Photo(kind=kind, ref_id=ref_id, filename=Path(filename or name).name[:200],
                  path=str(rel_dir / name), size=len(blob),
                  uploaded_by=user_id, uploaded_by_name=user_name)
    db.add(photo)
    db.flush()
    return photo


def photo_url(p: Photo) -> str:
    return f"/api/photos/{p.id}/file"


def photos_of(db: Session, kind: str, ref_ids: list[int]) -> dict[int, list[dict]]:
    """Фото по связанным записям: {ref_id: [{id, url, filename, missing, ...}]}."""
    out: dict[int, list[dict]] = {}
    if not ref_ids:
        return out
    for p in db.scalars(select(Photo).where(Photo.kind == kind, Photo.ref_id.in_(ref_ids))
                        .order_by(Photo.id)):
        exists = bool(p.path) and (BASE_DIR / p.path).is_file()
        out.setdefault(p.ref_id, []).append({
            "id": p.id, "filename": p.filename, "size": p.size,
            "url": photo_url(p) if exists else "",
            "missing": not exists,
            "uploaded_by_name": p.uploaded_by_name or "",
            "created_at": p.created_at.isoformat(timespec="seconds") if p.created_at else None,
        })
    return out


def delete_photo_files(db: Session, kind: str, ref_ids: list[int]) -> None:
    """Удалить фото вместе с родительской записью (например, при удалении области из отчёта)."""
    if not ref_ids:
        return
    for p in db.scalars(select(Photo).where(Photo.kind == kind, Photo.ref_id.in_(ref_ids))):
        _unlink(p)
        db.delete(p)


def _unlink(p: Photo) -> None:
    try:
        if p.path:
            target = (BASE_DIR / p.path).resolve()
            if target.is_file() and target.is_relative_to(UPLOAD_ROOT.resolve()):
                target.unlink()
    except OSError:
        pass


def get_photo_file(db: Session, photo_id: int) -> tuple[Optional[Photo], Optional[Path], str]:
    """Для отдачи: (фото, абсолютный путь, mime). Файл обязан остаться внутри UPLOAD_ROOT."""
    p = db.get(Photo, photo_id)
    if p is None:
        return None, None, ""
    target = (BASE_DIR / p.path).resolve() if p.path else None
    if target is None or not target.is_file() or not target.is_relative_to(UPLOAD_ROOT.resolve()):
        return p, None, ""
    ext = target.suffix.lower().lstrip(".")
    return p, target, ALLOWED_EXT.get(ext, "application/octet-stream")


def retention_days(db: Session) -> int:
    """Настроенный срок хранения фото в днях (0 — хранить всегда)."""
    from .models import Setting

    s = db.get(Setting, "photo_retention_days")
    try:
        return max(0, int(float(s.value))) if s and s.value else 0
    except ValueError:
        return 0


def cleanup_photos(db: Session, days: Optional[int] = None) -> int:
    """Удалить файлы фото старше срока хранения. Возвращает число удалённых файлов."""
    days = retention_days(db) if days is None else days
    if days <= 0:
        return 0
    cutoff = now_local() - dt.timedelta(days=days)
    removed = 0
    for p in db.scalars(select(Photo).where(Photo.created_at < cutoff)):
        if p.path and (BASE_DIR / p.path).is_file():
            _unlink(p)
            removed += 1
            p.path = ""      # запись остаётся: файл удалён по сроку хранения
    if removed:
        db.commit()
    return removed
