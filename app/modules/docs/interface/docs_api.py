"""API видов заявлений, фирменных бланков и формирования заявления.
Правила — в ``application/statements.py``."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.core.auth import Principal, current_principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.core.schemas import ApiModel
from app.modules.exchange.application.documents import DOCX_MEDIA_TYPE

from ..application import statements
from ..application.print_page import PRINT_MEDIA_TYPE, PrintIn, print_page
from ..application.statements import KindIn, KindUpdate, RenderIn

router = APIRouter(prefix="/api/docs", tags=["docs"])
VIEW = require_perm("settings.view")
EDIT = require_perm("settings.edit")
_AUTH_CONTEXT_HEADER = "X-Butler-Auth-Context"


class KindTemplateOut(ApiModel):
    """Фирменный бланк вида."""

    uploaded: bool
    filename: Optional[str]
    size: int
    placeholders: list[str]


class KindOut(ApiModel):
    id: int
    code: str
    name: str
    text: str
    builtin: bool
    active: bool
    sort_order: int
    template: KindTemplateOut


class KindsOut(ApiModel):
    kinds: list[KindOut]
    placeholders: Any               # справка по плейсхолдерам
    pdf_available: bool
    pdf: Any                        # чем сервер собирает PDF


class KindDeletedOut(ApiModel):
    ok: bool = True
    shifts_cleared: int


class TemplateUploadedOut(ApiModel):
    ok: bool = True
    type: str
    filename: str
    size: int
    placeholders: list[str]         # плейсхолдеры, найденные в бланке


class TemplateRemovedOut(ApiModel):
    ok: bool = True
    removed: bool


def _attachment(content: bytes, name: str, media_type: str) -> Response:
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/kinds", response_model=KindsOut)
def list_kinds(principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    return statements.kinds_view(db)


@router.post("/kinds", response_model=KindOut)
def create_kind(payload: KindIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    return statements.create_kind(db, principal, payload)


@router.put("/kinds/{kind_id}", response_model=KindOut)
def update_kind(kind_id: int, payload: KindUpdate, principal: Principal = Depends(EDIT),
                db: Session = Depends(get_db)):
    return statements.update_kind(db, principal, kind_id, payload)


@router.delete("/kinds/{kind_id}", response_model=KindDeletedOut)
def delete_kind(kind_id: int, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Удалить вид заявления вместе с его бланком."""
    return {"shifts_cleared": statements.delete_kind(db, principal, kind_id)}


@router.get("/sample", response_class=Response)
def sample_template(type: str, principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    """Образец бланка с плейсхолдерами."""
    content, name = statements.sample(db, type)
    return _attachment(content, name, DOCX_MEDIA_TYPE)


@router.post("/templates", response_model=TemplateUploadedOut)
def upload_template(type: str, file: UploadFile, principal: Principal = Depends(EDIT),
                    db: Session = Depends(get_db)):
    """Загрузить фирменный бланк вида."""
    # читаем на байт больше лимита: превышение видно, а файл любого размера в память не попадает
    data = file.file.read(statements.TEMPLATE_MAX_BYTES + 1)
    return {"ok": True, **statements.upload_template(db, principal, type, data, file.filename)}


@router.delete("/templates", response_model=TemplateRemovedOut)
def remove_template(type: str, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    return {"removed": statements.remove_template(db, principal, type)}


@router.post("/render", response_class=Response)
def render(payload: RenderIn, principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    """Сформировать заявление сотрудника в DOCX или PDF."""
    return _attachment(*statements.render(db, principal, payload))


@router.post("/print", response_class=HTMLResponse, responses={
    200: {"headers": {_AUTH_CONTEXT_HEADER: {"schema": {"type": "string"}}}},
})
def print_document(payload: PrintIn, principal: Principal = Depends(current_principal)):
    """Страница для печати: чистый HTML документ (заявления, график сменности).

    Не сохраняет состояние; право — как у входа: печать доступна каждой роли.
    Данные клиент собирает шаблонами lit-html (экранирование на месте), поэтому
    body/css вставляются как есть; заголовок экранируется сервером."""
    assert principal.auth_context is not None   # current_principal проверил сессию из cookie
    return Response(print_page(payload), media_type=PRINT_MEDIA_TYPE,
                    headers={_AUTH_CONTEXT_HEADER: principal.auth_context})
