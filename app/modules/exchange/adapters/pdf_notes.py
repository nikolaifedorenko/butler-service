"""Переносит табуляцию примечаний из XLSX и заменяет крупный значок PDF на маленький уголок."""
from __future__ import annotations

from io import BytesIO

from pypdf import PdfWriter
from pypdf.errors import PyPdfError
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from ..ports import PdfUnavailable


def _rect(*coords: float) -> ArrayObject:
    return ArrayObject(FloatObject(value) for value in coords)


def compact_notes(content: bytes, notes: dict[str, str]) -> bytes:
    if not notes:
        return content
    try:
        writer = PdfWriter(clone_from=BytesIO(content))
        appearance = DecodedStreamObject()
        appearance.update({
            NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): _rect(0, 0, 4.5, 4.5), NameObject("/Resources"): DictionaryObject(),
        })
        appearance.set_data(b"0.26 0.36 0.48 rg 0 4.5 m 4.5 4.5 l 4.5 0 l h f\n")
        appearance_ref = writer._add_object(appearance)
        seen: set[str] = set()
        for page in writer.pages:
            for ref in page.get("/Annots", []):
                note = ref.get_object()
                if note.get("/Subtype") != "/Text":
                    continue
                anchor = str(note.get("/T"))
                if anchor not in notes:
                    continue
                seen.add(anchor)
                left, _, _, top = map(float, note["/Rect"])
                note.update({
                    NameObject("/Contents"): TextStringObject(notes[anchor]),
                    NameObject("/T"): TextStringObject("Шахматка"),
                    NameObject("/Rect"): _rect(left - 2.8, top - 5.4, left + 1.7, top - .9),
                    NameObject("/F"): NumberObject(0),
                    NameObject("/AP"): DictionaryObject({NameObject("/N"): appearance_ref}),
                })
        if notes.keys() != seen:
            raise PdfUnavailable("сервис PDF не перенёс все примечания шахматки.")
        output = BytesIO()
        writer.write(output)
    except (PyPdfError, ValueError, TypeError, KeyError) as exc:
        raise PdfUnavailable("сервис PDF вернул документ с некорректными аннотациями.") from exc
    return output.getvalue()
