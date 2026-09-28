"""Корпоративные шаблоны кадровых документов (.docx с плейсхолдерами {field}).

Шаблон загружается один раз (Настройки → «Шаблоны документов компании») и хранится
в папке templates/ рядом с проектом. При рендере сохраняются шрифты, стили,
колонтитулы и подложка шаблона: текст подставляется в существующие run'ы параграфов
(включая таблицы и колонтитулы), поэтому форматирование документа не меняется.
Плейсхолдеры, разбитые Word на несколько run («{full_» + «name}»), склеиваются.
"""
from __future__ import annotations

import datetime as dt
import io
import re
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

from .deps import local_date
from .names import suggest_genitive

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)

PH_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
# допустимый код вида заявления (он же — имя файла бланка templates/<code>.docx)
CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")

DOC_TYPES = {
    "vacation_paid": "Заявление на ежегодный оплачиваемый отпуск",
    "vacation_unpaid": "Заявление на отпуск без сохранения заработной платы",
    "day_off_hours": "Заявление на выходной за ранее отработанные часы",
    "time_off_request": "Заявление об отсутствии на рабочем месте (отпросился на часть смены)",
}

# какому виду отсутствия из словаря смен какой документ соответствует
DOC_TYPE_BY_SHIFT_CODE = {
    "VACATION": "vacation_paid",
    "VACATION_UNPAID": "vacation_unpaid",
    "TIMEOFF_HOURS": "day_off_hours",
    "AWAY_HOURS": "time_off_request",
}

PLACEHOLDER_HELP = {
    "company": "название организации",
    "director": "кому адресовано (шапка)",
    "full_name": "ФИО полностью (именительный: «Федоренко Николай Сергеевич»)",
    "full_name_genitive": "ФИО в родительном падеже («от Федоренко Николая Сергеевича»); "
                          "берётся из карточки сотрудника, если поле пустое — подставляется автоматически",
    "short_name": "Фамилия И.О.",
    "position": "должность на дату документа",
    "tab_number": "табельный номер",
    "group": "блок графика (Смена 1 / Смена 2 / Администрация)",
    "phone": "телефон сотрудника",
    "telegram": "логин Telegram",
    "email": "рабочая почта",
    "emergency_name": "экстренный контакт (имя)",
    "emergency_phone": "экстренный контакт (телефон)",
    "date_from": "начало периода (ДД.ММ.ГГГГ)",
    "date_to": "конец периода (ДД.ММ.ГГГГ)",
    "date_from_ru": "начало прописью: «01» октября 2026 г.",
    "date_to_ru": "конец прописью",
    "days": "количество календарных дней (цифрой)",
    "days_word": "количество прописью: двенадцать",
    "today": "дата составления (ДД.ММ.ГГГГ)",
    "today_ru": "дата составления прописью",
    "nationality": "гражданство сотрудника",
    "department": "департамент (из справочника подразделений)",
    "subdivision": "служба / подразделение из официальных документов "
                   "(«Служба управления виллами», «Служба приёма и размещения»)",
    "from_time": "время, с которого сотрудника не будет на рабочем месте (ЧЧ:ММ)",
    "until_time": "время, до которого сотрудника не будет (ЧЧ:ММ)",
    "hours": "сколько часов отсутствует (цифрой, например 2 или 2,5)",
    "hours_word": "сколько часов прописью: «два»",
    "period": "период одной строкой: «с 01.10.2026 по 05.10.2026» или «01.10.2026»",
    "period_ru": "период прописью: «с «01» октября 2026 г. по «05» октября 2026 г.»",
    "reason": "вид отсутствия из словаря (Отпуск, Выходной за часы, Отпросился…)",
    "note": "примечание из ячейки графика (номер приказа, причина)",
}

_ONES = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
         "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
         "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят",
         "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", " четыреста", "пятьсот", "шестьсот",
             "семьсот", "восемьсот", "девятьсот"]


def number_to_words(n: int) -> str:
    if n == 0:
        return "ноль"
    parts = []
    h, rest = divmod(n, 100)
    if h:
        parts.append(_HUNDREDS[h].strip())
    if rest >= 20:
        t, o = divmod(rest, 10)
        parts.append(_TENS[t])
        rest = o
    if rest:
        parts.append(_ONES[rest])
    return " ".join(p for p in parts if p)


MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def date_ru_words(d: dt.date) -> str:
    return f"«{d.day:02d}» {MONTHS_GEN[d.month - 1]} {d.year} г."


def date_ru(d: dt.date) -> str:
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


# ─────────────────────────── хранение шаблонов ───────────────────────────
def template_path(doc_type: str) -> Optional[Path]:
    p = TEMPLATES_DIR / f"{doc_type}.docx"
    return p if p.exists() else None


def list_templates() -> list[dict]:
    out = []
    for key, title in DOC_TYPES.items():
        p = template_path(key)
        item = {"type": key, "title": title, "uploaded": p is not None,
                "filename": p.name if p else None,
                "size": p.stat().st_size if p else 0,
                "placeholders": sorted(scan_placeholders(p)) if p else []}
        out.append(item)
    return out


def save_template(doc_type: str, data: bytes) -> dict:
    # код вида заявления из БД (statement_kinds); формат жёстко ограничиваем —
    # имя файла бланка строится из кода, посторонние символы недопустимы
    if not CODE_RE.match(doc_type or ""):
        raise ValueError(f"Некорректный код вида заявления: {doc_type!r}")
    try:
        Document(io.BytesIO(data))          # валидация: это действительно docx
    except Exception as exc:
        raise ValueError(f"Файл не является корректным .docx: {exc}")
    path = TEMPLATES_DIR / f"{doc_type}.docx"
    path.write_bytes(data)
    return {"type": doc_type, "filename": path.name, "size": path.stat().st_size,
            "placeholders": sorted(scan_placeholders(path))}


def delete_template(doc_type: str) -> bool:
    p = template_path(doc_type)
    if p:
        p.unlink()
        return True
    return False


def scan_placeholders(path: Path) -> set[str]:
    doc = Document(str(path))
    found: set[str] = set()
    for text in _iter_texts(doc):
        found.update(PH_RE.findall(text))
    return found


def _iter_texts(doc):
    def walk_paragraphs(paras):
        for p in paras:
            yield "".join(r.text for r in p.runs) or p.text

    yield from walk_paragraphs(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from walk_paragraphs(cell.paragraphs)
    for section in doc.sections:
        for hf in (section.header, section.footer):
            yield from walk_paragraphs(hf.paragraphs)


# ─────────────────────────── подстановка значений ───────────────────────────
def _set_run_text_multiline(run, text: str) -> None:
    lines = text.split("\n")
    run.text = lines[0]
    for extra in lines[1:]:
        br = run._r.makeelement(qn("w:br"), {})
        run._r.append(br)
        t = run._r.makeelement(qn("w:t"), {})
        t.set(qn("xml:space"), "preserve")
        t.text = extra
        run._r.append(t)


def _fill_paragraph(p, values: dict) -> None:
    runs = p.runs
    if not runs:
        if PH_RE.search(p.text or ""):
            values_only = PH_RE.sub(lambda m: str(values.get(m.group(1), m.group(0))), p.text)
            p.text = values_only
        return
    full = "".join(r.text for r in runs)
    if not PH_RE.search(full):
        return
    new = PH_RE.sub(lambda m: str(values.get(m.group(1), m.group(0))), full)
    if new == full:
        return
    _set_run_text_multiline(runs[0], new)      # форматирование первого run сохраняется
    for r in runs[1:]:
        r.text = ""


def fill_docx(doc, values: dict) -> None:
    for p in doc.paragraphs:
        _fill_paragraph(p, values)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    _fill_paragraph(p, values)
    for section in doc.sections:
        for hf in (section.header, section.footer):
            for p in hf.paragraphs:
                _fill_paragraph(p, values)


def period_text(d1: dt.date, d2: dt.date) -> str:
    return date_ru(d1) if d1 == d2 else f"с {date_ru(d1)} по {date_ru(d2)}"


def period_text_words(d1: dt.date, d2: dt.date) -> str:
    return date_ru_words(d1) if d1 == d2 else f"с {date_ru_words(d1)} по {date_ru_words(d2)}"


def hours_text(value: float) -> str:
    v = round(float(value or 0), 2)
    return str(int(v)) if abs(v - int(v)) < 1e-9 else f"{v:g}".replace(".", ",")


def build_values(employee, date_from: dt.date, date_to: dt.date, extra: Optional[dict] = None) -> dict:
    days = (date_to - date_from).days + 1
    today = local_date()
    extra = dict(extra or {})
    dep_name = ""
    dep = getattr(employee, "department", None)
    if dep is not None:
        dep_name = getattr(dep, "name", "") or ""
    try:
        hours_val = float(extra.get("hours") or 0)
    except (TypeError, ValueError):
        hours_val = 0.0
    values = {
        "company": extra.get("company", "") if extra else "",
        "director": extra.get("director", "") if extra else "",
        "full_name": employee.full_name,
        "full_name_genitive": (getattr(employee, "full_name_genitive", "") or "").strip()
                              or suggest_genitive(employee.full_name),
        "short_name": employee.short_name or employee.full_name,
        "position": employee.position or "",
        "tab_number": employee.tab_number or "",
        "group": employee.schedule_group or "",
        "phone": employee.phone or "",
        "telegram": employee.telegram or "",
        "email": employee.email or "",
        "emergency_name": employee.emergency_name or "",
        "emergency_phone": employee.emergency_phone or "",
        "nationality": (getattr(employee, "nationality", "") or "").strip(),
        "department": dep_name,
        "subdivision": (getattr(employee, "subdivision", "") or "").strip(),
        "date_from": date_ru(date_from),
        "date_to": date_ru(date_to),
        "date_from_ru": date_ru_words(date_from),
        "date_to_ru": date_ru_words(date_to),
        "days": days,
        "days_word": number_to_words(days),
        "today": date_ru(today),
        "today_ru": date_ru_words(today),
        "period": period_text(date_from, date_to),
        "period_ru": period_text_words(date_from, date_to),
        "from_time": extra.get("from_time") or "",
        "until_time": extra.get("until_time") or "",
        "hours": hours_text(hours_val),
        "hours_word": number_to_words(int(round(hours_val))) if hours_val else "",
        "reason": extra.get("reason") or "",
        "note": extra.get("note") or "",
    }
    if extra:
        for k, v in extra.items():
            values.setdefault(k, v)
    return values


def render_docx(doc_type: str, values: dict, fallback_text: str) -> bytes:
    path = template_path(doc_type)
    if path is not None:
        doc = Document(str(path))
    else:
        doc = Document()
        for line in fallback_text.split("\n"):
            doc.add_paragraph(line)
    fill_docx(doc, values)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ─────────────────────────── образец шаблона ───────────────────────────
SAMPLE_BODIES = {
    "vacation_paid": "Прошу предоставить мне ежегодный оплачиваемый отпуск "
                     "продолжительностью {days} ({days_word}) календарных дней "
                     "с {date_from_ru} по {date_to_ru} включительно.",
    "vacation_unpaid": "Прошу предоставить мне отпуск без сохранения заработной платы "
                       "продолжительностью {days} ({days_word}) календарных дней "
                       "с {date_from_ru} по {date_to_ru} по семейным обстоятельствам.",
    "day_off_hours": "Прошу предоставить мне день отдыха {date_from_ru} "
                     "в счёт ранее отработанного времени ({hours} ч переработки).",
    "time_off_request": "Прошу разрешить мне отсутствовать на рабочем месте {date_from_ru} "
                         "с {from_time} до {until_time} ({hours} ч) по семейным обстоятельствам. "
                         "Указанное время прошу учесть как отсутствие по согласованию.",
}


def build_sample_docx(doc_type: str, body_text: str = "") -> bytes:
    """Образец .docx-шаблона с плейсхолдерами.
    Скачивается из настроек: пользователь открывает его в Word/Pages/LibreOffice,
    заменяет на свой фирменный бланк (шрифты, логотип, колонтитулы), сохраняя
    плейсхолдеры {в фигурных скобках}, и загружает обратно.

    Для встроенных видов — эталонная шапка и типовая формулировка (богатый набор
    плейсхолдеров). Для пользовательских видов — их собственный текст из карточки
    вида: сразу видно, как документ выглядит без фирменного бланка."""
    doc = Document()
    custom = doc_type not in SAMPLE_BODIES and (body_text or "").strip()
    if custom:
        for line in body_text.split("\n"):
            doc.add_paragraph(line)
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()
    for line in ("{director}", "{company}",
                 "от {position} {full_name_genitive}",
                 "{subdivision} · {department}",
                 "табельный номер {tab_number}, гражданство: {nationality}"):
        p = doc.add_paragraph(line)
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    title = doc.add_paragraph("ЗАЯВЛЕНИЕ")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        run.bold = True
    doc.add_paragraph(SAMPLE_BODIES.get(doc_type, SAMPLE_BODIES["vacation_paid"]))
    doc.add_paragraph("")
    p = doc.add_paragraph("{today}\t\t____________________ / {short_name} /")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ─────────────────────────── PDF ───────────────────────────
# Реализация вынесена в app/pdf_render.py: сначала пробуем LibreOffice (точный вид бланка),
# затем встроенный рендер reportlab (работает везде, кириллица — шрифты DejaVu из assets/fonts).
def pdf_available() -> bool:
    from .pdf_render import pdf_mode
    return pdf_mode() != "none"


def pdf_mode() -> str:
    from .pdf_render import pdf_mode as _mode
    return _mode()


def pdf_status() -> dict:
    from .pdf_render import native_error
    from .pdf_render import pdf_mode as _mode
    mode = _mode()
    return {"mode": mode,
            "title": {"libreoffice": "LibreOffice (точный вид бланка)",
                      "native": "встроенный рендер (шрифты DejaVu)",
                      "none": "недоступно"}.get(mode, mode),
            "error": "" if mode != "none" else (native_error() or "нет ни LibreOffice, ни reportlab")}


def docx_to_pdf(docx_bytes: bytes, filename: str = "document.pdf") -> Optional[bytes]:
    from .pdf_render import docx_to_pdf as _to_pdf
    data, _mode = _to_pdf(docx_bytes, filename)
    return data
