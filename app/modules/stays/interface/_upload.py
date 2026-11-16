"""Чтение загруженного файла с ограничением размера."""
from __future__ import annotations

from fastapi import UploadFile

from app.core.errors import PayloadTooLarge

from ..application import fund_xlsx as fx


def read_upload(file: UploadFile) -> bytes:
    """Содержимое файла; больше лимита — 413. Лимит проверяется до чтения файла целиком."""
    cap = fx.MAX_FILE_BYTES
    too_large = PayloadTooLarge(f"Файл больше {cap // 1024 // 1024} МБ")
    if file.size is not None and file.size > cap:
        raise too_large
    data = file.file.read(cap + 1)           # с запасом в байт
    if len(data) > cap:
        raise too_large
    return data
