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
import os
import shutil
import struct
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .audit import audit
from .db import Base
from .errors import Forbidden, Gone, NotFound, PayloadTooLarge
from .time import now_local

# app/core/media.py → корень проекта на ДВА уровня выше app (был app/photos.py —
# на один). data/uploads живёт в корне проекта — путь критичен для уже загруженных файлов.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_ROOT = BASE_DIR / "data" / "uploads"


class Photo(Base):
    """Фото и видео (комментарии к «Не ОК», замечания по возврату кара).

    Храним оригиналы на диске в data/uploads/YYYY/MM/, путь относительно BASE_DIR.
    media_type — "photo" (по умолчанию) или "video": у видео свой лимит размера
    (video_max_mb; 50 МБ — предел загрузки в Telegram Bot API) и свой срок хранения
    (video_retention_days). Колонка добавлена позже фото, поэтому у старых записей
    она пустая и трактуется как "photo".

    Срок хранения настраивается: старые файлы удаляет cleanup_photos() при старте
    сервера; запись остаётся (url пустой, missing=True) — комментарии не теряются.
    """

    __tablename__ = "photos"
    __table_args__ = (Index("ix_photos_kind_ref", "kind", "ref_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)   # night_item | car_return | car_check
    ref_id: Mapped[int] = mapped_column(Integer, index=True)    # id связанной записи
    filename: Mapped[str] = mapped_column(String(255), default="")
    path: Mapped[str] = mapped_column(String(400), default="")  # относительный путь от корня проекта
    size: Mapped[int] = mapped_column(Integer, default=0)
    media_type: Mapped[str] = mapped_column(String(8), default="photo")   # photo | video
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_by_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)

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


# Лимиты медиа хранятся в «прочих правилах объекта» (таблица settings), которой
# владеет прикладной слой. core не импортирует модули (R5), поэтому правила
# читаются через провайдера: bootstrap/registry.py регистрирует schedule_helpers.
# load_rules при старте; без провайдера действуют значения по умолчанию.
_RULES_PROVIDER = None


def set_rules_provider(fn) -> None:
    """Регистрирует функцию (db) -> dict «прочих правил объекта» (composition root)."""
    global _RULES_PROVIDER
    _RULES_PROVIDER = fn


def media_limits(db: Session) -> dict:
    """Настроенные объектом лимиты медиа: размер (МБ) и срок хранения (дни)."""
    r = _RULES_PROVIDER(db) if _RULES_PROVIDER is not None else {}
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


# ── потоковая загрузка (ревью 20.10.2026, P1-misc-4) ──────────────────────────
# Раньше интерфейсы делали `await file.read(limit + 1)` — до HARD_MAX_MB (500 МБ)
# в ОПЕРАТИВНОЙ памяти на запрос; несколько параллельных загрузок видео с телефона
# съедали память воркера. Теперь поток читается чанками сразу на диск, в памяти
# только первые SNIFF_BYTES для определения типа по магическим байтам.

SNIFF_BYTES = 64 * 1024          # магические байты всех поддерживаемых контейнеров — в начале
STREAM_CHUNK = 1024 * 1024         # 1 МБ


@dataclass(frozen=True)
class UploadRef:
    """Загруженный файл во временном каталоге: путь, размер и начало содержимого.

    Владеет файлом вызывающий код: save_photo_ref() переносит его в хранилище
    (или удаляет при отказе); при отказе ДО сохранения интерфейс обязан вызвать
    discard() (в try/finally — unlink(missing_ok=True) безопасен и после переноса).
    """

    filename: str
    tmp_path: Path
    size: int
    head: bytes        # первые SNIFF_BYTES — вход sniff_media

    def discard(self) -> None:
        Path(self.tmp_path).unlink(missing_ok=True)


async def read_upload_streaming(file, limit: int) -> UploadRef:
    """UploadFile (duck-typed: async .read(size), .filename) → временный файл.

    Превышение limit прерывает чтение СРАЗУ (PayloadTooLarge → 413, текст прежний —
    «Файл больше N МБ»); при любой ошибке временный файл удаляется.
    """
    fd, name = tempfile.mkstemp(prefix="butler-upload-")
    tmp = Path(name)
    head = b""
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = await file.read(STREAM_CHUNK)
                if not chunk:
                    break
                if len(head) < SNIFF_BYTES:
                    head += chunk[:SNIFF_BYTES - len(head)]
                size += len(chunk)
                if size > limit:
                    raise PayloadTooLarge(f"Файл больше {limit // (1024 * 1024)} МБ")
                out.write(chunk)
        return UploadRef(filename=file.filename or "photo.jpg", tmp_path=tmp,
                         size=size, head=head)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _sniff_and_limit(db: Session, head: bytes, filename: str, size: int,
                     media_type: str) -> tuple[str, str]:
    """Общая проверка save_photo/save_photo_ref: тип по содержимому + лимит своего типа."""
    detected, ext = sniff_media(head, filename)
    if not detected:
        raise ValueError("Можно загружать только изображения (JPG, PNG, GIF, WEBP, BMP) "
                         "или видео (MP4, MOV, WEBM, MKV, 3GP)")
    if media_type and media_type != detected:
        raise ValueError(f"Файл не похож на {MEDIA_TITLES.get(media_type, media_type)}")
    limit_mb = media_limits(db)["video_max_mb" if detected == "video" else "photo_max_mb"]
    if limit_mb > 0 and size > limit_mb * 1024 * 1024:
        raise PayloadTooLarge(f"Файл больше {limit_mb} МБ")
    return detected, ext


def _upload_dir() -> tuple[Path, Path]:
    """(абсолютный каталог, относительный от BASE_DIR) загрузок текущего месяца."""
    rel_dir = Path("data") / "uploads" / f"{now_local():%Y}" / f"{now_local():%m}"
    target_dir = BASE_DIR / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir, rel_dir


def save_photo_ref(db: Session, *, kind: str, ref_id: int, ref: UploadRef,
                   user_id: Optional[int], user_name: str, media_type: str = "") -> Photo:
    """Сохранить загруженный ПОТОКОМ файл (UploadRef): без копирования через память —
    временный файл ПЕРЕНОСИТСЯ в data/uploads/ (shutil.move). При любом отказе
    временный файл удаляется."""
    try:
        detected, ext = _sniff_and_limit(db, ref.head, ref.filename, ref.size, media_type)
        target_dir, rel_dir = _upload_dir()
        name = f"{uuid.uuid4().hex}.{ext}"
        shutil.move(str(ref.tmp_path), str(target_dir / name))
    except BaseException:
        ref.discard()
        raise
    photo = Photo(kind=kind, ref_id=ref_id, filename=Path(ref.filename or name).name[:200],
                  path=str(rel_dir / name), size=ref.size, media_type=detected,
                  uploaded_by=user_id, uploaded_by_name=user_name)
    db.add(photo)
    db.flush()
    return photo


def save_photo(db: Session, *, kind: str, ref_id: int, filename: str, blob: bytes,
               user_id: Optional[int], user_name: str, media_type: str = "") -> Photo:
    """Сохранить оригинал фото или видео на диск и зарегистрировать в БД (из байтов
    в памяти — тесты и мелкие файлы; продуктовые загрузки идут через
    read_upload_streaming + save_photo_ref).

    media_type можно не передавать — тип определится по содержимому; если передан,
    он обязан совпасть с определённым (защита от «видео, присланного как фото»).
    Размер проверяется по лимиту своего типа: PayloadTooLarge → 413.
    """
    detected, ext = _sniff_and_limit(db, blob, filename, len(blob), media_type)
    target_dir, rel_dir = _upload_dir()
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

# фото видно тому, кто видит раздел-владелец (аудит 21.10.2026, AUTHZ-07)
_VIEW_PERMS = {"night_item": ("night.view",), "car_return": ("cars.view",),
               "car_check": ("night.view", "cars.view")}


def resolve_photo_file(db: Session, photo_id: int, principal):
    """(фото, путь, mime) для отдачи оригинала.

    NotFound — фото нет в БД; Forbidden — нет права раздела, которому принадлежит фото;
    Gone — файл удалён по сроку хранения (запись в БД остаётся)."""
    from .permissions import principal_permissions

    p, path, mime = get_photo_file(db, photo_id)
    if p is None:
        raise NotFound("Фото не найдено")
    if not set(_VIEW_PERMS.get(p.kind, ())) & principal_permissions(db, principal):
        raise Forbidden("Нет доступа к этому фото")
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
