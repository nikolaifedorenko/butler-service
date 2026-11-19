"""Роутер медиа (G1, фаза C4): Канонические маршруты работы с загруженными фото: /api/photos/*.

Зачем отдельный роутер: `photos.photo_url()` формирует ссылку `/api/photos/{id}/file`,
и эту ссылку получают ВСЕ потребители (payload ночного отчёта, история возврата кара,
ответ загрузки). До появления этого модуля маршрут существовал только как
`/api/night/photos/{id}/file` — то есть каждая фотография отдавалась 404.

Дубли `/api/night/photos/*` удалены: ни интерфейс, ни выгрузки,
ни сообщения службам на них не ссылаются.

Доступ: просмотр — право раздела, к которому относится фото (night.view, cars.view);
удаление — автор либо право media.delete_any; фото закрытого ночного отчёта не удаляется.

Здесь же — `/api/photos/limits`: настроенные объектом лимиты медиа (размер фото и
видео, сроки хранения). Они нужны интерфейсу для подсказок у кнопок загрузки во
всех разделах, поэтому отдаются любому авторизованному пользователю.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy.orm import Session

from ..core.auth import Principal, current_principal
from ..core.db import get_db
from ..core.media import delete_photo as delete_photo_usecase
from ..core.media import media_limits, resolve_photo_file
from ..core.schemas import ApiModel, Ok

router = APIRouter(prefix="/api/photos", tags=["photos"])


class MediaLimitsOut(ApiModel):
    """Лимиты медиа, которые задаёт объект; 0 — без ограничения."""

    photo_max_mb: float = Field(description="наибольший размер фото, МБ")
    video_max_mb: float = Field(description="наибольший размер видео, МБ")
    photo_retention_days: int
    video_retention_days: int


@router.get("/limits", operation_id="photo_limits_get", response_model=MediaLimitsOut)
def photo_limits(principal: Principal = Depends(current_principal),
                 db: Session = Depends(get_db)):
    """Лимиты медиа для интерфейса: размер фото/видео (МБ) и сроки хранения (дни)."""
    return media_limits(db)


@router.get("/{photo_id}/file", operation_id="photo_file_get", response_class=FileResponse)
@router.head("/{photo_id}/file", operation_id="photo_file_head", include_in_schema=False,
             response_class=FileResponse)
def photo_file(photo_id: int, principal: Principal = Depends(current_principal),
               db: Session = Depends(get_db)):
    """Отдача оригинала фото. Только авторизованным; HEAD — для проверки доступности."""
    p, path, mime = resolve_photo_file(db, photo_id, principal)
    return FileResponse(str(path), media_type=mime or "application/octet-stream",
                        filename=p.filename or None,
                        headers={"Cache-Control": "private, max-age=86400"})


@router.delete("/{photo_id}", response_model=Ok)
def photo_delete(photo_id: int, principal: Principal = Depends(current_principal),
                 db: Session = Depends(get_db)):
    """Удалить фото: своё — любой пользователь, чужое — право media.delete_any."""
    delete_photo_usecase(db, principal, photo_id)
    return Ok()
