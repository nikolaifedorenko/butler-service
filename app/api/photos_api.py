"""Канонические маршруты работы с загруженными фото: /api/photos/*.

Зачем отдельный роутер: `photos.photo_url()` формирует ссылку `/api/photos/{id}/file`,
и эту ссылку получают ВСЕ потребители (payload ночного отчёта, история возврата кара,
ответ загрузки). До появления этого модуля маршрут существовал только как
`/api/night/photos/{id}/file` — то есть каждая фотография отдавалась 404.

Маршруты-дубли в `/api/night/photos/*` оставлены для совместимости со старыми
ссылками и вызывают те же функции.

Доступ: любой авторизованный пользователь (фото ночного отчёта и возврата кара
не содержат персональных данных третьих лиц); удаление — автор либо менеджер и выше.

Здесь же — `/api/photos/limits`: настроенные объектом лимиты медиа (размер фото и
видео, сроки хранения). Они нужны интерфейсу для подсказок у кнопок загрузки во
всех разделах, поэтому отдаются любому авторизованному пользователю.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..core.auth import Principal, current_principal
from ..core.db import get_db
from ..core.media import delete_photo as delete_photo_usecase
from ..core.media import media_limits, resolve_photo_file

router = APIRouter(prefix="/api/photos", tags=["photos"])


@router.get("/limits", operation_id="photo_limits_get")
def photo_limits(principal: Principal = Depends(current_principal),
                 db: Session = Depends(get_db)):
    """Лимиты медиа для интерфейса: размер фото/видео (МБ) и сроки хранения (дни)."""
    return media_limits(db)


@router.get("/{photo_id}/file", operation_id="photo_file_get")
@router.head("/{photo_id}/file", operation_id="photo_file_head", include_in_schema=False)
def photo_file(photo_id: int, principal: Principal = Depends(current_principal),
               db: Session = Depends(get_db)):
    """Отдача оригинала фото. Только авторизованным; HEAD — для проверки доступности."""
    p, path, mime = resolve_photo_file(db, photo_id)
    return FileResponse(str(path), media_type=mime or "application/octet-stream",
                        filename=p.filename or None,
                        headers={"Cache-Control": "private, max-age=86400"})


@router.delete("/{photo_id}")
def photo_delete(photo_id: int, principal: Principal = Depends(current_principal),
                 db: Session = Depends(get_db)):
    """Удалить фото: своё — любой пользователь, чужое — менеджер и выше."""
    delete_photo_usecase(db, principal, photo_id)
    return {"ok": True}
