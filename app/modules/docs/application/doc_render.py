"""Заявления сотрудников: виды, значения плейсхолдеров {field}, образец бланка.

Бланк загружается один раз (Настройки → «Шаблоны документов компании») и хранится модулем
exchange; при заполнении сохраняются шрифты, стили, колонтитулы и подложка бланка.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Optional

from app.core.format import hours_text
from app.core.time import local_date
from app.modules.exchange.application import documents
from app.modules.exchange.application.documents import Document, text
from app.modules.people.application import suggest_genitive

# допустимый код вида заявления (он же — имя файла бланка templates/<code>.docx)
CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")

DOC_TYPES = {
    "vacation_paid": "Заявление на ежегодный оплачиваемый отпуск",
    "vacation_unpaid": "Заявление на отпуск без сохранения заработной платы",
    "day_off_hours": "Заявление на выходной за ранее отработанные часы",
    "time_off_request": "Заявление об отсутствии на рабочем месте (отпросился на часть смены)",
}

# Привязка «вид отсутствия → вид заявления» живёт в словаре смен (ShiftType.doc_type),
# а для единой сущности «отпросился (выходной за часы)» выбирается по точке ввода —
# app/api/schedule.py::doc_type_of_absence. Хардкод-карты кодов смен здесь больше нет:
# она расходилась со словарём и не учитывала объединение двух видов в один (Q3, 12.10.2026).

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
    "intervals": "интервалы отсутствия одной строкой: «с 14:00 до 16:00 (2 ч)», а при "
                 "нескольких отлучках в день — перечислением «с 14:00 до 16:00 (2 ч) и "
                 "с 18:00 до 20:00 (2 ч)»",
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
    if n < 0:
        return "минус " + number_to_words(-n)
    if n == 0:
        return "ноль"
    # значения ≥ 1000 в заявлениях не встречаются, но не должны ронять рендер (раньше
    # _HUNDREDS[h] с h ≥ 10 давал IndexError → 500). «N тысяч» — запасной вариант.
    if n >= 1000:
        head = number_to_words(n // 1000) + " тысяч"
        return f"{head} {number_to_words(n % 1000)}" if n % 1000 else head
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
    return documents.template_path(doc_type)


def save_template(doc_type: str, data: bytes) -> dict:
    # код вида заявления из БД (statement_kinds); формат жёстко ограничиваем —
    # имя файла бланка строится из кода, посторонние символы недопустимы
    if not CODE_RE.match(doc_type or ""):
        raise ValueError(f"Некорректный код вида заявления: {doc_type!r}")
    path = documents.save_template(doc_type, data)
    return {"type": doc_type, "filename": path.name, "size": path.stat().st_size,
            "placeholders": sorted(scan_placeholders(path))}


def delete_template(doc_type: str) -> bool:
    return documents.delete_template(doc_type)


def scan_placeholders(path: Path) -> set[str]:
    return documents.template_placeholders(path)


def period_text(d1: dt.date, d2: dt.date) -> str:
    return date_ru(d1) if d1 == d2 else f"с {date_ru(d1)} по {date_ru(d2)}"


def period_text_words(d1: dt.date, d2: dt.date) -> str:
    return date_ru_words(d1) if d1 == d2 else f"с {date_ru_words(d1)} по {date_ru_words(d2)}"


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
    return documents.fill_template(doc_type, values, fallback_text)


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
    custom = doc_type not in SAMPLE_BODIES and (body_text or "").strip()
    if custom:
        return documents.write_docx(Document([text(line) for line in body_text.split("\n")]))
    head = ("{director}", "{company}", "от {position} {full_name_genitive}",
            "{subdivision} · {department}", "табельный номер {tab_number}, гражданство: {nationality}")
    return documents.write_docx(Document([
        *[text(line, align="right") for line in head],
        text("ЗАЯВЛЕНИЕ", bold=True, align="center"),
        text(SAMPLE_BODIES.get(doc_type, SAMPLE_BODIES["vacation_paid"])),
        text(""),
        text("{today}\t\t____________________ / {short_name} /"),
    ]))


# ─────────────────────────── PDF ───────────────────────────
def pdf_available() -> bool:
    return documents.pdf_mode() != "none"


def pdf_status() -> dict:
    mode = documents.pdf_mode()
    return {"mode": mode,
            "title": {"native": "встроенный рендер (шрифты DejaVu)",
                      "none": "недоступно"}.get(mode, mode),
            "error": "" if mode != "none" else (documents.pdf_error() or "не установлен reportlab")}
