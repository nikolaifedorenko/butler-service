"""Шаблоны сообщений по разделам и подстановка плейсхолдеров — домен notify.

Чистая половина бывшей app/notify/templates.py (фаза C3): тексты разделов,
реестр плейсхолдеров, подстановка значений и блок списка недостатков. I/O нет
(R1); действующий текст с учётом переопределений из БД — application/templates.py.

Транспорт один на приложение, а текст у каждого раздела свой: ночной отчёт пишет
службам про недостатки смены, электрокары — про замечания при возврате кара. Сами разделы,
их тексты по умолчанию и плейсхолдеры объявляют модули в манифестах (ADR-0012).
Плейсхолдеры подставляются простой заменой: неизвестные остаются в тексте как есть,
чтобы опечатку было видно в предпросмотре, а не в отправленном сообщении.
"""
from __future__ import annotations


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
