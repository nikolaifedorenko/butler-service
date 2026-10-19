"""Медиа (фото и видео): хранение оригиналов на диске + срок хранения (настраиваемый).

Оригинал НЕ сжимается и не перекодировывается: байты как пришли, так и лежат.
Папка: data/uploads/YYYY/MM/<uuid>.<ext> (путь в БД — относительный от корня проекта).
Отдача файла — только авторизованным пользователям через /api/photos/{id}/file
(в статическую раздачу папка не выкладывается); видео отдаётся тем же маршрутом —
FileResponse в Starlette поддерживает Range, поэтому плеер перематывает файл.

Тип файла (photo|video) определяется по содержимому (магическим байтам), а не по
расширению: телефон присылает видео как .mp4/.mov/.webm, а «картинка» с чужим
расширением не должна попасть на диск как видео.

Лимиты задаёт объект («прочие правила»): photo_max_mb (12), video_max_mb (50 —
предел загрузки в Telegram Bot API), сроки хранения photo_retention_days и
video_retention_days (0 = хранить всегда). Устаревшие файлы удаляет
cleanup_photos() при старте сервера; запись в БД остаётся (файл помечается как
удалённый по сроку) — комментарии и история не теряются.
"""
from __future__ import annotations

import datetime as dt
import struct
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import audit
from .deps import now_local
from .models import Photo
from .services.errors import Forbidden, Gone, NotFound, PayloadTooLarge

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_ROOT = BASE_DIR / "data" / "uploads"

ALLOWED_EXT = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
               "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}

# Видео: те же правила хранения, но свой лимит размера и свой срок хранения.
ALLOWED_VIDEO_EXT = {"mp4": "video/mp4", "m4v": "video/x-m4v", "mov": "video/quicktime",
                     "webm": "video/webm", "mkv": "video/x-matroska", "3gp": "video/3gpp"}

MEDIA_TITLES = {"photo": "фото", "video": "видео"}

# HEIC/HEIF тоже начинается с ftyp, но браузеры его не показывают — не принимаем.
_HEIC_BRANDS = {b"heic", b"heix", b"heim", b"heis", b"mif1", b"msf1"}


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


def sniff_media(blob: bytes, filename: str = "") -> tuple[str, str]:
    """(тип "photo"|"video", расширение) — по содержимому, затем по имени файла.

    Видео принимается ТОЛЬКО по магическим байтам (ftyp → mp4/mov, EBML → webm/mkv):
    declared-расширение для видео не доверяем, иначе любой файл с именем .mp4 лёг бы
    на диск как видео. Для картинок прежнее поведение сохранено: если содержимое не
    распознано, но расширение из списка картинок — принимаем (редкие экзотические
    кодировки, которые sniff_image не знает).

    Пустой тип — файл не медиа (PDF, HEIC, произвольные байты).
    """
    img = sniff_image(blob)
    if img:
        return "photo", img
    head = blob[:16]
    declared = Path(filename or "").suffix.lower().lstrip(".")
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in _HEIC_BRANDS:
            return "", ""
        return "video", ("mov" if brand == b"qt  " else "mp4")
    if head[:4] == b"\x1aE\xdf\xa3":                     # EBML-контейнер: webm или mkv
        return "video", (declared if declared in ("webm", "mkv") else "webm")
    if declared in ALLOWED_EXT and not blob[:4].startswith(b"%PDF"):
        return "photo", declared
    return "", ""


def media_limits(db: Session) -> dict:
    """Настроенные объектом лимиты медиа: размер (МБ) и срок хранения (дни)."""
    from .schedule_helpers import load_rules

    r = load_rules(db)
    return {"photo_max_mb": r.get("photo_max_mb", 12), "video_max_mb": r.get("video_max_mb", 50),
            "photo_retention_days": r.get("photo_retention_days", 180),
            "video_retention_days": r.get("video_retention_days", 180)}


# Аварийный порог чтения потока: «0» в настройках означает «не ограничивать»,
# но читать бесконечно нельзя — дальше размер всё равно проверит save_photo()
# по лимиту своего типа файла.
HARD_MAX_MB = 500


def max_upload_bytes(db: Session) -> int:
    """Сколько байт читать из потока загрузки.

    Тип файла узнаём по содержимому, поэтому читаем по большему из лимитов
    (обычно видео): точнее размер проверит save_photo() уже для своего типа.
    """
    lim = media_limits(db)
    caps = [c if c > 0 else HARD_MAX_MB for c in (lim["photo_max_mb"], lim["video_max_mb"])]
    return max(caps) * 1024 * 1024


def save_photo(db: Session, *, kind: str, ref_id: int, filename: str, blob: bytes,
               user_id: Optional[int], user_name: str, media_type: str = "") -> Photo:
    """Сохранить оригинал фото или видео на диск и зарегистрировать в БД.

    media_type можно не передавать — тип определится по содержимому; если передан,
    он обязан совпасть с определённым (защита от «видео, присланного как фото»).
    Размер проверяется по лимиту своего типа: PayloadTooLarge → 413.
    """
    detected, ext = sniff_media(blob, filename)
    if not detected:
        raise ValueError("Можно загружать только изображения (JPG, PNG, GIF, WEBP, BMP) "
                         "или видео (MP4, MOV, WEBM, MKV, 3GP)")
    if media_type and media_type != detected:
        raise ValueError(f"Файл не похож на {MEDIA_TITLES.get(media_type, media_type)}")
    limit_mb = media_limits(db)["video_max_mb" if detected == "video" else "photo_max_mb"]
    if limit_mb > 0 and len(blob) > limit_mb * 1024 * 1024:
        raise PayloadTooLarge(f"Файл больше {limit_mb} МБ")
    rel_dir = Path("data") / "uploads" / f"{now_local():%Y}" / f"{now_local():%m}"
    target_dir = BASE_DIR / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    (target_dir / name).write_bytes(blob)
    photo = Photo(kind=kind, ref_id=ref_id, filename=Path(filename or name).name[:200],
                  path=str(rel_dir / name), size=len(blob), media_type=detected,
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
            # у записей до появления колонки media_type значение пустое → фото
            "media_type": p.media_type or "photo",
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
        unlink_photo(p)
        db.delete(p)


def unlink_photo(p: Photo) -> None:
    """Удалить файл фото с диска (запись в БД не трогает).

    Путь обязан остаться внутри UPLOAD_ROOT — иначе файл не удаляется (защита от
    подмены path в записи). Публичное имя: используется api/photos_api.py и api/night_api.py.
    """
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
    mime = ALLOWED_EXT.get(ext) or ALLOWED_VIDEO_EXT.get(ext)
    return p, target, mime or "application/octet-stream"


def retention_days(db: Session, media_type: str = "photo") -> int:
    """Настроенный срок хранения в днях (0 — хранить всегда); свой у фото и у видео."""
    lim = media_limits(db)
    return max(0, lim["video_retention_days" if media_type == "video" else "photo_retention_days"])


def cleanup_photos(db: Session, days: Optional[int] = None) -> int:
    """Удалить файлы медиа старше срока хранения. Возвращает число удалённых файлов.

    Срок свой у фото и у видео (video_retention_days): видео весит в десятки раз
    больше, поэтому объект может хранить его меньше. Параметр days — общая граница
    для обоих типов (используется тестами и ручной уборкой).
    """
    lim = media_limits(db)
    limits = {"photo": lim["photo_retention_days"], "video": lim["video_retention_days"]}
    if days is not None:
        limits = {"photo": days, "video": days}
    oldest = now_local() - dt.timedelta(days=max(limits.values()))
    removed = 0
    for p in db.scalars(select(Photo).where(Photo.created_at < oldest)):
        keep = limits.get(p.media_type or "photo", 0)
        if keep <= 0:
            continue                            # этот тип храним всегда
        if p.created_at and p.created_at >= now_local() - dt.timedelta(days=keep):
            continue                            # ещё не дорос до своего срока
        if p.path and (BASE_DIR / p.path).is_file():
            unlink_photo(p)
            removed += 1
            p.path = ""      # запись остаётся: файл удалён по сроку хранения
    if removed:
        db.commit()
    return removed


# ─────────────────── use-case'ы для API-слоя (15.10.2026) ───────────────────
# Общие для канонического /api/photos и алиасов в ночном отчёте: раньше
# night_api импортировал роут-функции photos_api (api → api), теперь оба
# модуля вызывают сервис (контракт import-linter «api-модули независимы»).

def resolve_photo_file(db: Session, photo_id: int):
    """(фото, путь, mime) для отдачи оригинала.

    NotFound — фото нет в БД; Gone — файл удалён по сроку хранения (запись
    в БД остаётся, комментарии и история не теряются)."""
    p, path, mime = get_photo_file(db, photo_id)
    if p is None:
        raise NotFound("Фото не найдено")
    if path is None:
        raise Gone("Файл удалён по сроку хранения")
    return p, path, mime


def delete_photo(db: Session, principal, photo_id: int) -> None:
    """Удалить фото: своё — любой пользователь, чужое — менеджер и выше."""
    photo = db.get(Photo, photo_id)
    if photo is None:
        raise NotFound("Фото не найдено")
    if photo.uploaded_by != principal.user.id and not principal.is_manager:
        raise Forbidden("Можно удалять только свои фото")
    unlink_photo(photo)
    db.delete(photo)
    audit(db, principal, "photo_delete", f"photo:{photo_id}",
          {"kind": photo.kind, "ref_id": photo.ref_id})
    db.commit()
