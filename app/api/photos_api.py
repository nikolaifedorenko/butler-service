"""Канонические маршруты работы с загруженными фото: /api/photos/*.

Зачем отдельный роутер: `photos.photo_url()` формирует ссылку `/api/photos/{id}/file`,
и эту ссылку получают ВСЕ потребители (payload ночного отчёта, история возврата кара,
ответ загрузки). До появления этого модуля маршрут существовал только как
`/api/night/photos/{id}/file` — то есть каждая фотография отдавалась 404.

Маршруты-дубли в `/api/night/photos/*` оставлены для совместимости со старыми
ссылками и вызывают те же функции.

Доступ: любой авторизованный пользователь (фото ночного отчёта и возврата кара
не содержат персональных данных третьих лиц); удаление — автор либо менеджер и выше.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import Principal, audit, current_principal
from ..db import get_db
from ..models import Photo
from ..photos import get_photo_file, unlink_photo

router = APIRouter(prefix="/api/photos", tags=["photos"])


@router.get("/{photo_id}/file", operation_id="photo_file_get")
@router.head("/{photo_id}/file", operation_id="photo_file_head", include_in_schema=False)
def photo_file(photo_id: int, principal: Principal = Depends(current_principal),
               db: Session = Depends(get_db)):
    """Отдача оригинала фото. Только авторизованным; HEAD — для проверки доступности."""
    p, path, mime = get_photo_file(db, photo_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Фото не найдено")
    if path is None:
        raise HTTPException(status_code=410, detail="Файл удалён по сроку хранения")
    return FileResponse(str(path), media_type=mime or "application/octet-stream",
                        filename=p.filename or None,
                        headers={"Cache-Control": "private, max-age=86400"})


@router.delete("/{photo_id}")
def photo_delete(photo_id: int, principal: Principal = Depends(current_principal),
                 db: Session = Depends(get_db)):
    """Удалить фото: своё — любой пользователь, чужое — менеджер и выше."""
    p = db.get(Photo, photo_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Фото не найдено")
    if p.uploaded_by != principal.user.id and not principal.is_manager:
        raise HTTPException(status_code=403, detail="Можно удалять только свои фото")
    unlink_photo(p)
    db.delete(p)
    audit(db, principal, "photo_delete", f"photo:{photo_id}", {"kind": p.kind, "ref_id": p.ref_id})
    db.commit()
    return {"ok": True}
