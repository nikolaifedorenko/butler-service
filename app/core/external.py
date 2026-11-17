"""Внешний идентификатор записи: «система, экземпляр, id» (ADR-0013, раздел о внешних идентификаторах).

Запись, пришедшая из другой системы (Fidelio и т. п.), помнит, откуда она: ``ext_system`` — система,
``ext_instance`` — какой именно её экземпляр (пустая строка, пока экземпляр один), ``ext_id`` — её
номер в этой системе. Тройка уникальна: повторный импорт находит запись и обновляет её, а не создаёт
вторую. Запись, заведённая руками, ``ext_id`` не имеет — уникальность на неё не действует (NULL в
уникальном индексе PostgreSQL не равны друг другу).

``ext_system`` бывает и без ``ext_id``: так демо-данные помечены «demo».
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .schemas import ApiModel


class ExternalRefColumns:
    """Три колонки внешнего идентификатора; уникальный индекс по ним объявляет сама таблица."""

    ext_system: Mapped[str] = mapped_column(String(24), default="", server_default="")
    ext_instance: Mapped[str] = mapped_column(String(40), default="", server_default="")
    ext_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class ExternalRef(ApiModel):
    """Внешний идентификатор в запросах и ответах API."""

    system: str
    instance: str = ""
    id: str


def external_of(row: ExternalRefColumns) -> Optional[dict]:
    """Идентификатор записи для ответа API; ``None``, если запись заведена не из внешней системы."""
    if row.ext_id is None:
        return None
    return {"system": row.ext_system, "instance": row.ext_instance, "id": row.ext_id}


def find_external[T: ExternalRefColumns](db: Session, model: type[T], ref: ExternalRef) -> Optional[T]:
    """Запись с таким внешним идентификатором (не больше одной: тройка уникальна)."""
    return db.scalar(select(model).where(model.ext_system == ref.system, model.ext_instance == ref.instance,
                                         model.ext_id == ref.id))


def set_external(row: ExternalRefColumns, ref: ExternalRef) -> None:
    row.ext_system, row.ext_instance, row.ext_id = ref.system, ref.instance, ref.id
