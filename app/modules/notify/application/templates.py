"""Действующие шаблоны разделов: переопределения из БД поверх доменных текстов.

Прикладная половина бывшей app/notify/templates.py (фаза C3): template_of /
save_template / templates_payload читают и пишут notify_templates (domain =
«night», «cars», …); пока записи нет — действует текст из DEFAULT_TEMPLATES
(домен notify).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.orm import NotifyTemplate
from ..domain.templates import (  # noqa: F401 — публичная граница
    DEFAULT_TEMPLATES,
    DOMAIN_TITLES,
    PLACEHOLDERS,
    render_template,
)


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
