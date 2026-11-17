"""Чтение загруженного файла с ограничением размера."""
from __future__ import annotations

from fastapi import UploadFile

from .errors import PayloadTooLarge


def read_upload(file: UploadFile, cap: int) -> bytes:
    """Содержимое файла; больше ``cap`` байт — 413. Лимит проверяется до чтения файла целиком."""
    too_large = PayloadTooLarge(f"Файл больше {cap // 1024 // 1024} МБ")
    if file.size is not None and file.size > cap:
        raise too_large
    data = file.file.read(cap + 1)           # с запасом в байт
    if len(data) > cap:
        raise too_large
    return data
