"""Выгрузка ночного отчёта: DOCX и PDF.

Формат — «сплошной поток»: сначала все области с пунктами по зонам обхода
(пункт, результат, комментарий/фото, ответственная служба), затем блок
«Проверка электрокаров» (все обходы ночи), «Недостатки смены» (что и кому
направлено, включая «Не проверено» и «Исправлено после отправки»), журнал
отправок службам и перехваты областей. Один документ на одну ночную смену.

Службы и отправки берутся из снимка отчёта (night_check_items.service_name,
notify_dispatches), поэтому выгрузка закрытой смены не меняется со временем.

PDF собирается из того же .docx встроенным движком (app/pdf_render.py):
если есть LibreOffice — через него, иначе reportlab. Картинки вставляются
оригиналами, но масштабируются по ширине страницы; недоступные файлы
(удалены по сроку хранения) помечаются текстом.
"""
from __future__ import annotations

import io
from typing import Optional

from sqlalchemy.orm import Session

from app.core.media import BASE_DIR
from app.core.time import WD_SHORT

from .night import report_dict


def _fmt_ts(iso: Optional[str]) -> str:
    return iso.replace("T", " ")[:16] if iso else "—"


def build_docx(report_id_data: dict, photos: dict[int, list[dict]], *, company: str = "",
               defects: Optional[dict] = None, dispatches: Optional[list[dict]] = None,
               duty: str = "") -> bytes:
    """Собрать .docx ночного отчёта (python-docx).

    defects — результат night.defects_of() (позиции «Не ОК», «Не проверено» и
    «Исправлено после отправки»), dispatches — строки общего журнала отправок.
    """
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
    p.add_run("Итог: ").bold = True
    p.add_run(f"{data['result_title'] if data['status'] == 'closed' else 'не подведён (смена идёт)'}"
              f" · {status_line} · областей закрыто {data['progress']['done']} из {data['progress']['total']}"
              f" · проверка электрокаров: {'выполнена' if data['cars_step_done'] else 'не завершена'}")

    # ── области, сгруппированные по зонам обхода (v2: зона → объекты → пункты) ──
    cur_zone = None
    for area in data["areas"]:
        if area["is_cars"]:
            continue
        zone_name = area.get("zone_name") or area.get("category") or "Без зоны"
        if zone_name != cur_zone:
            cur_zone = zone_name
            zh = doc.add_paragraph()
            zr = zh.add_run(zone_name)
            zr.bold = True
            zr.font.size = Pt(12)
        head = doc.add_paragraph()
        r = head.add_run(area["name"])
        r.bold = True
        r.font.size = Pt(11)
        who = (f"Взял: {area['taken_by_name'] or '—'} с {_fmt_ts(area['taken_at'])}"
               if area["status"] != "free" else "Не проверялась")
        if area["closed_at"]:
            who += f" · закрыта {_fmt_ts(area['closed_at'])}"
        doc.add_paragraph(who).runs[0].font.size = Pt(9)

        table = doc.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        for i, text in enumerate(("Пункт проверки", "Результат", "Служба", "Комментарий / фото")):
            hdr[i].paragraphs[0].add_run(text).bold = True
        for item in area["items"]:
            row = table.add_row().cells
            row[0].text = item["text"]
            row[1].text = item["answer_title"]
            row[2].text = item.get("service_name") or "—"
            cell = row[3]
            lines = []
            if item["comment"]:
                lines.append(item["comment"])
            if item["answered_by_name"]:
                lines.append(f"— {item['answered_by_name']}, {_fmt_ts(item['answered_at'])}")
            cell.text = "\n".join(lines)
            for ph in photos.get(item["id"], []):
                if not _image_cell(cell, ph):
                    cell.add_paragraph(f"[фото {ph['filename']} недоступно]")
        _autosize(table, (Cm(6.2), Cm(2.2), Cm(2.9), Cm(5.2)))

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
            if c.get("moved"):
                state_bits.append("перепаркован")
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
            # место: при перепарковке показываем переход «где нашёл → куда переставил»
            found_loc = c.get("found_location") or ""
            if c.get("moved") and c["location"]:
                place = f"{found_loc or '—'} → {c['location']}"
            else:
                place = c["location"] or found_loc or "—"
            row[4].text = f"{place} · {charge}"
            tail = "; ".join(state_bits) + (f"\n{c['comment']}" if c["comment"] else "")
            cell = row[5]
            cell.text = tail
            for ph in c.get("photos", []):
                if not _image_cell(cell, ph, width_cm=4.4):
                    cell.add_paragraph(f"[фото {ph['filename']} недоступно]")
        _autosize(table, (Cm(2.6), Cm(2.0), Cm(3.0), Cm(1.6), Cm(3.6), Cm(4.7)))

    # ── недостатки смены: что направлено службам (этап 5/6) ──
    rows = (defects or {}).get("items") or []
    counts = (defects or {}).get("counts") or {}
    head = doc.add_paragraph()
    head.add_run("Недостатки смены").bold = True
    if not rows:
        doc.add_paragraph("Замечаний нет: все пункты проверены, результат «ОК».")
    else:
        doc.add_paragraph(
            f"Всего позиций {counts.get('total', len(rows))}: «Не ОК» {counts.get('bad', 0)}, "
            f"«Не проверено» {counts.get('unchecked', 0)}, исправлено после отправки "
            f"{counts.get('fixed_after_dispatch', 0)}"
            + (f" · ночные батлеры смены: {duty}" if duty else "")).runs[0].font.size = Pt(9)
        table = doc.add_table(rows=1, cols=5)
        table.style = "Table Grid"
        for i, text in enumerate(("Служба", "Зона / объект", "Пункт", "Комментарий", "Статус")):
            table.rows[0].cells[i].paragraphs[0].add_run(text).bold = True
        for d in sorted(rows, key=lambda x: (x.get("service_name") or "яяя", x.get("area") or "")):
            row = table.add_row().cells
            row[0].text = d.get("service_name") or "Без службы"
            row[1].text = f"{d.get('zone') or '—'} · {d.get('area') or '—'}"
            row[2].text = f"{d.get('kind_title', '')}: {d.get('text', '')}"
            media = len(d.get("media") or [])
            row[3].text = (d.get("comment") or "—") + (f"\nвложений: {media}" if media else "")
            status = ("исправлено после отправки" if d.get("fixed_after_dispatch")
                      else f"отправлено {_fmt_ts(d.get('dispatched_at'))}" if d.get("dispatched")
                      else "не отправлено")
            row[4].text = status
        _autosize(table, (Cm(3.0), Cm(3.6), Cm(4.6), Cm(3.3), Cm(2.6)))
        doc.add_paragraph(
            "Позиции «Не проверено» включаются в отчёт; исправленное после отправки повторно "
            "не направляется и не отзывается.").runs[0].font.size = Pt(9)

    # ── журнал отправок службам ──
    sends = dispatches or []
    head = doc.add_paragraph()
    head.add_run("Отправки службам").bold = True
    if not sends:
        doc.add_paragraph("В эту смену ничего не отправлялось.")
    else:
        table = doc.add_table(rows=1, cols=6)
        table.style = "Table Grid"
        for i, text in enumerate(("Время", "Кто отправил", "Служба", "Канал", "Получатель",
                                  "Позиций / вложений / статус")):
            table.rows[0].cells[i].paragraphs[0].add_run(text).bold = True
        for d in sends:
            row = table.add_row().cells
            row[0].text = _fmt_ts(d.get("ts"))
            row[1].text = d.get("actor_name") or "—"
            row[2].text = d.get("recipient_name") or "—"
            row[3].text = d.get("channel_title") or d.get("channel") or "—"
            row[4].text = d.get("target") or "—"
            tail = f"{d.get('items_count', 0)} / {d.get('media_count', 0)} / " \
                   f"{'отправлено' if d.get('status') == 'sent' else 'ОШИБКА'}"
            if d.get("attempts", 1) > 1:
                tail += f" (попыток: {d['attempts']})"
            if d.get("error"):
                tail += f"\n{d['error'][:200]}"
            row[5].text = tail
        _autosize(table, (Cm(2.4), Cm(2.8), Cm(2.8), Cm(2.2), Cm(3.0), Cm(3.9)))

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


def _image_cell(cell, ph: dict, *, width_cm: float = 6.0) -> bool:
    """Вставить фото (оригинал) в ячейку таблицы; False — файла нет.

    `width_cm` — ширина картинки: в таблице обхода каров колонка «Состояние,
    комментарий» уже, чем у пунктов чек-листа."""
    from docx.shared import Cm

    rel = ph.get("path") or ""
    if not rel:
        return False
    target = BASE_DIR / rel
    if not target.is_file():
        return False
    para = cell.add_paragraph()
    try:
        para.add_run().add_picture(str(target), width=Cm(width_cm))
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
    from app.core.media import Photo

    ids = [p["id"] for items in photos.values() for p in items]
    by_id = {p.id: p for p in db.query(Photo).filter(Photo.id.in_(ids)).all()} if ids else {}
    for items in photos.values():
        for p in items:
            orig = by_id.get(p["id"])
            p["path"] = orig.path if orig and orig.path else ""
    return photos


def render_night_report_docx(db: Session, report_id: int, *, company: str = "",
                             photos_map: Optional[dict[int, list[dict]]] = None) -> bytes:
    """DOCX ночного отчёта (зоны и объекты + кары + недостатки + отправки + перехваты)."""
    from app.modules.notify.application.dispatch import dispatch_dict, journal_of

    from ..adapters.orm import NightReport
    from .night import defects_of, duty_of

    rep = db.get(NightReport, report_id)
    if rep is None:
        raise KeyError("Отчёт не найден")
    # db обязателен: без него report_dict() не собирает car_checks/interceptions,
    # и в документ попадали пустые блоки «Проверка электрокаров» и «Перехваты».
    data = report_dict(rep, db=db)
    data["date_obj"] = rep.date
    photos = _photo_payload(db, photos_map or {})
    # фото отметок каров живут внутри data["car_checks"] — дополняем их путём до файла
    _photo_payload(db, {c["id"]: c.get("photos") or [] for c in data.get("car_checks") or []})
    # недостатки и журнал отправок — из снимка смены: выгрузка закрытой смены стабильна
    defects = defects_of(db, rep)
    dispatches = [dispatch_dict(d) for d in journal_of(db, "night", rep.id, limit=200)]
    return build_docx(data, photos, company=company, defects=defects,
                      dispatches=dispatches, duty=duty_of(rep))
