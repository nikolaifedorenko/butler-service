"""Выгрузка ночного отчёта: DOCX и PDF.

Формат — «сплошной поток»: сначала все области с пунктами (ответ, комментарий, фото),
затем блок «Проверка электрокаров» (все обходы ночи) и служебные разделы
(перехваты областей, замечания). Один документ на одну ночную смену.

PDF собирается из того же .docx встроенным движком (app/pdf_render.py):
если есть LibreOffice — через него, иначе reportlab. Картинки вставляются
оригиналами, но масштабируются по ширине страницы; недоступные файлы
(удалены по сроку хранения) помечаются текстом.
"""
from __future__ import annotations

import io
from typing import Optional

from sqlalchemy.orm import Session

from .deps import WD_SHORT
from .night import report_dict
from .photos import BASE_DIR, photo_url


def _fmt_ts(iso: Optional[str]) -> str:
    return iso.replace("T", " ")[:16] if iso else "—"


def build_docx(report_id_data: dict, photos: dict[int, list[dict]], *, company: str = "") -> bytes:
    """Собрать .docx ночного отчёта (python-docx)."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    data = report_id_data
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(10.5)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("НОЧНОЙ ОТЧЁТ")
    run.bold = True
    run.font.size = Pt(14)
    wd = WD_SHORT[data["date_obj"].weekday()]
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run(f"{data['date_obj'].strftime('%d.%m.%Y')} ({wd}) · {data['shift_label']}"
                + (f" · {company}" if company else ""))
    status_line = ("Закрыт вручную" if data["close_reason"] == "manual"
                   else "Закрыт автоматически в 08:00" if data["close_reason"] == "auto"
                   else f"Открыт · закроется {_fmt_ts(data['deadline'])}")
    p = doc.add_paragraph()
    p.add_run(f"Итог: ").bold = True
    p.add_run(f"{data['result_title'] if data['status'] == 'closed' else 'не подведён (смена идёт)'}"
              f" · {status_line} · областей закрыто {data['progress']['done']} из {data['progress']['total']}"
              f" · проверка электрокаров: {'выполнена' if data['cars_step_done'] else 'не завершена'}")

    # ── области ──
    for area in data["areas"]:
        if area["is_cars"]:
            continue
        head = doc.add_paragraph()
        r = head.add_run(f"{area['name']}" + (f" · {area['category']}" if area["category"] else ""))
        r.bold = True
        r.font.size = Pt(12)
        who = (f"Взял: {area['taken_by_name'] or '—'} с {_fmt_ts(area['taken_at'])}"
               if area["status"] != "free" else "Не проверялась")
        if area["closed_at"]:
            who += f" · закрыта {_fmt_ts(area['closed_at'])}"
        doc.add_paragraph(who).runs[0].font.size = Pt(9)

        table = doc.add_table(rows=1, cols=3)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        for i, text in enumerate(("Пункт проверки", "Результат", "Комментарий / фото")):
            hdr[i].paragraphs[0].add_run(text).bold = True
        for item in area["items"]:
            row = table.add_row().cells
            row[0].text = item["text"]
            row[1].text = item["answer_title"]
            cell = row[2]
            lines = []
            if item["comment"]:
                lines.append(item["comment"])
            if item["answered_by_name"]:
                lines.append(f"— {item['answered_by_name']}, {_fmt_ts(item['answered_at'])}")
            cell.text = "\n".join(lines)
            for ph in photos.get(item["id"], []):
                img = _image_cell(cell, ph)
                if img is None:
                    cell.add_paragraph(f"[фото {ph['filename']} недоступно]")
        _autosize(table, (Cm(7.5), Cm(2.6), Cm(6.4)))

    # ── электрокары ──
    cars = data.get("car_checks") or []
    head = doc.add_paragraph()
    r = head.add_run("Проверка электрокаров")
    r.bold = True
    r.font.size = Pt(12)
    if not cars:
        doc.add_paragraph("Обход каров в эту смену не выполнялся." if not data["cars_step_done"]
                          else "Каров в списке нет.")
    else:
        table = doc.add_table(rows=1, cols=6)
        table.style = "Table Grid"
        for i, text in enumerate(("Время", "Кар", "Кто", "Найден", "Место / заряд", "Состояние, комментарий")):
            table.rows[0].cells[i].paragraphs[0].add_run(text).bold = True
        for c in cars:
            row = table.add_row().cells
            charge = {"full": "полный", "half": "половина", "empty": "разряжен"}.get(c["charge"], "—")
            state_bits = []
            if not c["canopy"]:
                state_bits.append("без тента")
            state_bits.append("на зарядке" if c["on_charge"] else "не на зарядке")
            state_bits.append("исправен" if c["condition"] == "ok" else "ЕСТЬ ЗАМЕЧАНИЯ")
            if c["trash"]:
                state_bits.append("мусор")
            if not c["clean"]:
                state_bits.append("не убран")
            row[0].text = _fmt_ts(c["checked_at"])
            row[1].text = c["car_number"]
            row[2].text = c["checker_name"] or "—"
            row[3].text = "да" if c["found"] else "НЕТ"
            row[4].text = f"{c['location'] or '—'} · {charge}"
            tail = "; ".join(state_bits) + (f"\n{c['comment']}" if c["comment"] else "")
            row[5].text = tail
        _autosize(table, (Cm(2.6), Cm(2.0), Cm(3.0), Cm(1.6), Cm(3.6), Cm(4.7)))

    # ── перехваты ──
    icepts = data.get("interceptions") or []
    if icepts:
        head = doc.add_paragraph()
        head.add_run("Перехваты областей").bold = True
        table = doc.add_table(rows=1, cols=3)
        table.style = "Table Grid"
        for i, text in enumerate(("Время", "Область", "От кого → кому")):
            table.rows[0].cells[i].paragraphs[0].add_run(text).bold = True
        for x in icepts:
            row = table.add_row().cells
            row[0].text = _fmt_ts(x["ts"])
            row[1].text = x["area_name"]
            row[2].text = f"{x['from_user_name'] or '—'} → {x['to_user_name'] or '—'}"
        _autosize(table, (Cm(3.2), Cm(6.0), Cm(7.3)))

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _image_cell(cell, ph: dict) -> bool:
    """Вставить фото (оригинал) в ячейку таблицы; False — файла нет."""
    from docx.shared import Cm

    rel = ph.get("path") or ""
    if not rel:
        return False
    target = BASE_DIR / rel
    if not target.is_file():
        return False
    para = cell.add_paragraph()
    try:
        para.add_run().add_picture(str(target), width=Cm(6.0))
    except Exception:
        return False
    return True


def _autosize(table, widths) -> None:
    """Фиксированные ширины колонок (иначе Word растягивает таблицу как попало)."""
    from docx.shared import Cm  # noqa: F401

    table.autofit = False
    for row in table.rows:
        for idx, w in enumerate(widths):
            if idx < len(row.cells):
                row.cells[idx].width = w


def _photo_payload(db: Session, photos: dict[int, list[dict]]) -> dict[int, list[dict]]:
    """Добавляем в ответ фото абсолютный путь для вставки в .docx."""
    from .models import Photo

    ids = [p["id"] for items in photos.values() for p in items]
    by_id = {p.id: p for p in db.query(Photo).filter(Photo.id.in_(ids)).all()} if ids else {}
    for items in photos.values():
        for p in items:
            orig = by_id.get(p["id"])
            p["path"] = orig.path if orig and orig.path else ""
    return photos


def render_night_report_docx(db: Session, report_id: int, *, company: str = "",
                             photos_map: Optional[dict[int, list[dict]]] = None) -> bytes:
    """DOCX ночного отчёта (области + кары + перехваты)."""
    from .models import NightReport

    rep = db.get(NightReport, report_id)
    if rep is None:
        raise KeyError("Отчёт не найден")
    data = report_dict(rep)
    data["date_obj"] = rep.date
    photos = _photo_payload(db, photos_map or {})
    return build_docx(data, photos, company=company)
