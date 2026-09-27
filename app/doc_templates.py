"""Шаблоны документов (заявления на отпуск и т.п.) — редактируются в настройках.

Плейсхолдеры, которые подставляются при печати:
  {company}             — название организации
  {director}            — кому адресовано (должность + ФИО руководителя)
  {full_name}           — ФИО сотрудника полностью (именительный падеж)
  {full_name_genitive}  — ФИО в родительном падеже («от Федоренко Николая Сергеевича»)
  {short_name}          — Фамилия И.О.
  {position}            — должность
  {tab_number}          — табельный номер
  {date_from}           — начало периода (ДД.ММ.ГГГГ)
  {date_to}             — конец периода (ДД.ММ.ГГГГ)
  {days}                — количество календарных дней
  {today}               — дата составления (ДД.ММ.ГГГГ)
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Setting

DEFAULT_COMPANY = "ООО «Батлер Сервис»"
DEFAULT_DIRECTOR = "Генеральному директору ООО «Батлер Сервис»"

DEFAULT_TPL_VACATION = """{director}
{company}
от {full_name_genitive},
табельный номер {tab_number},
должность: {position}

ЗАЯВЛЕНИЕ

Прошу предоставить мне ежегодный оплачиваемый отпуск с {date_from} по {date_to} включительно на {days} календарных дней.

{today}

____________________ / {short_name} /
"""

DEFAULT_TPL_VACATION_UNPAID = """{director}
{company}
от {full_name_genitive},
табельный номер {tab_number},
должность: {position}

ЗАЯВЛЕНИЕ

Прошу предоставить мне отпуск без сохранения заработной платы с {date_from} по {date_to} включительно на {days} календарных дней по семейным обстоятельствам.

{today}

____________________ / {short_name} /
"""

DEFAULT_TPL_DAY_OFF = """{director}
{company}
от {full_name_genitive},
табельный номер {tab_number},
должность: {position}, {subdivision}

ЗАЯВЛЕНИЕ

Прошу предоставить мне день отдыха {date_from} в счёт ранее отработанного времени ({hours} ч переработки).

{today}

____________________ / {short_name} /
"""

DEFAULT_TPL_TIME_OFF = """{director}
{company}
от {full_name_genitive},
табельный номер {tab_number},
должность: {position}, {subdivision}

ЗАЯВЛЕНИЕ

Прошу разрешить мне отсутствовать на рабочем месте {date_from} с {from_time} до {until_time}
({hours} ч) по семейным обстоятельствам.

{today}

____________________ / {short_name} /
"""

KEYS = {
    "doc_company": DEFAULT_COMPANY,
    "doc_director": DEFAULT_DIRECTOR,
    "tpl_vacation": DEFAULT_TPL_VACATION,
    "tpl_vacation_unpaid": DEFAULT_TPL_VACATION_UNPAID,
    "tpl_day_off_hours": DEFAULT_TPL_DAY_OFF,
    "tpl_time_off_request": DEFAULT_TPL_TIME_OFF,
}


def load_doc_templates(db: Session) -> dict:
    raw = {s.key: s.value for s in db.scalars(select(Setting).where(Setting.key.in_(list(KEYS))))}
    out = {}
    for key, default in KEYS.items():
        out[key] = raw.get(key) or default
    return {
        "company": out["doc_company"],
        "director": out["doc_director"],
        "vacation": out["tpl_vacation"],
        "vacation_unpaid": out["tpl_vacation_unpaid"],
        "day_off_hours": out["tpl_day_off_hours"],
        "time_off_request": out["tpl_time_off_request"],
        "placeholders": ["{company}", "{director}", "{full_name}", "{short_name}", "{position}",
                         "{tab_number}", "{full_name_genitive}", "{date_from}", "{date_to}", "{days}",
                         "{today}", "{nationality}", "{department}", "{subdivision}",
                         "{from_time}", "{until_time}", "{hours}", "{hours_word}", "{period}",
                         "{period_ru}", "{reason}", "{note}"],
    }


def save_doc_templates(db: Session, payload: dict) -> dict:
    mapping = {
        "doc_company": payload.get("company", ""),
        "doc_director": payload.get("director", ""),
        "tpl_vacation": payload.get("vacation", ""),
        "tpl_vacation_unpaid": payload.get("vacation_unpaid", ""),
        "tpl_day_off_hours": payload.get("day_off_hours", ""),
        "tpl_time_off_request": payload.get("time_off_request", ""),
    }
    for key, value in mapping.items():
        row = db.get(Setting, key)
        if row is None:
            row = Setting(key=key, description="Шаблон документа")
            db.add(row)
        row.value = value if value not in ("", None) else KEYS[key]
    db.flush()
    return load_doc_templates(db)
