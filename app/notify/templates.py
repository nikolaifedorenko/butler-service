"""Шаблоны сообщений по разделам и подстановка плейсхолдеров.

Транспорт один на приложение, а текст у каждого раздела свой: ночной отчёт пишет
службам про недостатки смены, электрокары — про замечания при возврате кара.
Шаблон хранится в ``notify_templates`` (domain = «night», «cars», …); пока записи
нет — действует текст по умолчанию из ``DEFAULT_TEMPLATES``.

Плейсхолдеры подставляются простой заменой: неизвестные остаются в тексте как есть,
чтобы опечатку было видно в предпросмотре, а не в отправленном сообщении.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import NotifyTemplate

DOMAIN_TITLES = {
    "night": "Ночной отчёт — недостатки смены",
    "cars": "Электрокары — замечания при возврате",
}

DEFAULT_TEMPLATES = {
    "night": ("Ночной отчёт · смена {date} · {shift}\n"
              "{service}: прошу исправить:\n{items}\n\n"
              "Ночные батлеры смены: {duty}\n"
              "Отметил: {author}, {time}. Фото и видео — во вложении."),
    "cars": ("Электрокары · {date}\n"
             "Замечания при возврате кара №{car} ({service}):\n{items}\n\n"
             "Отметил: {author}, {time}. Фото — во вложении."),
}

# Что можно подставить в текст: подсказка в настройках и проверка предпросмотра.
PLACEHOLDERS = {
    "night": ["{date}", "{shift}", "{service}", "{items}", "{duty}", "{author}", "{time}"],
    "cars": ["{date}", "{service}", "{car}", "{items}", "{author}", "{time}"],
}


def render_template(text: str, ctx: dict) -> str:
    """Подставить значения контекста. Пустые значения дают прочерк, не дыру в тексте."""
    out = text or ""
    for key, value in ctx.items():
        out = out.replace("{" + key + "}", str(value) if value not in (None, "") else "—")
    return out


def items_block(rows: list[dict], *, numbered: bool = True) -> str:
    """Список недостатков для подстановки в {items}.

    rows — [{"area", "text", "comment"}]; комментарий батлера важен получателю
    («лампа мигает», «дверь не закрывается до конца»), поэтому он попадает в строку.
    """
    lines = []
    for i, r in enumerate(rows, start=1):
        where = f"{r.get('area') or '—'} · {r.get('text') or ''}".strip(" ·")
        comment = (r.get("comment") or "").strip()
        line = f"{where}{' — ' + comment if comment else ''}"
        lines.append(f"{i}. {line}" if numbered else f"• {line}")
    return "\n".join(lines) or "—"


def template_of(db: Session, domain: str) -> str:
    """Действующий текст шаблона раздела: свой, иначе по умолчанию."""
    row = db.scalar(select(NotifyTemplate).where(NotifyTemplate.domain == domain))
    if row is not None and row.text.strip():
        return row.text
    return DEFAULT_TEMPLATES.get(domain, "")


def save_template(db: Session, domain: str, text: str) -> NotifyTemplate:
    """Сохранить текст шаблона раздела. Пустой текст = вернуть вариант по умолчанию."""
    if domain not in DOMAIN_TITLES:
        raise ValueError("Неизвестный раздел уведомлений")
    row = db.scalar(select(NotifyTemplate).where(NotifyTemplate.domain == domain))
    clean = (text or "").strip()
    if row is None:
        if not clean or clean == DEFAULT_TEMPLATES[domain]:
            return NotifyTemplate(domain=domain, text="")     # не храним текст по умолчанию
        row = NotifyTemplate(domain=domain, text=clean)
        db.add(row)
    else:
        row.text = "" if clean == DEFAULT_TEMPLATES[domain] else clean
    db.flush()
    return row


def templates_payload(db: Session) -> list[dict]:
    """Шаблоны всех разделов для экрана настроек (с признаком «изменён»)."""
    stored = {t.domain: t.text for t in db.scalars(select(NotifyTemplate))}
    out = []
    for domain, title in DOMAIN_TITLES.items():
        text = stored.get(domain, "").strip() or DEFAULT_TEMPLATES[domain]
        out.append({"domain": domain, "title": title, "text": text,
                    "default": DEFAULT_TEMPLATES[domain],
                    "customized": bool(stored.get(domain, "").strip()),
                    "placeholders": PLACEHOLDERS.get(domain, [])})
    return out
