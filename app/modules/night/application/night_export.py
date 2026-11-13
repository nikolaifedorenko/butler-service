"""Выгрузка ночного отчёта: описание документа для DOCX и PDF.

Формат — «сплошной поток»: сначала все области с пунктами по зонам обхода
(пункт, результат, комментарий/фото, ответственная служба), затем блок
«Проверка электрокаров» (все обходы ночи), «Недостатки смены» (что и кому
направлено, включая «Не проверено» и «Исправлено после отправки»), журнал
отправок службам и перехваты областей. Один документ на одну ночную смену.

Службы и отправки берутся из снимка отчёта (night_check_items.service_name,
notify_dispatches), поэтому выгрузка закрытой смены не меняется со временем.

Файл собирает модуль exchange: картинки вставляются уменьшенной копией по ширине колонки;
недоступные файлы (удалены по сроку хранения) помечаются текстом.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.media import BASE_DIR
from app.core.time import WD_SHORT
from app.modules.exchange.application.documents import (
    Document,
    Font,
    Paragraph,
    Picture,
    Run,
    Table,
    TCell,
    text,
    write_docx,
)

from .night import report_dict


def _fmt_ts(iso: Optional[str]) -> str:
    return iso.replace("T", " ")[:16] if iso else "—"


def _cell(value: str, *pictures: Picture) -> TCell:
    return TCell((Paragraph((Run(value),)), *pictures))


def _head(*titles: str) -> list[TCell]:
    return [TCell((text(t, bold=True),)) for t in titles]


def _photo(ph: dict, width_mm: float) -> Picture:
    """Фото из хранилища медиа; в таблице обхода каров колонка уже, чем у пунктов чек-листа."""
    rel = ph.get("path") or ""
    return Picture(str(BASE_DIR / rel) if rel else "", width_mm, f"[фото {ph['filename']} недоступно]")


def night_document(report_id_data: dict, photos: dict[int, list[dict]], *, company: str = "",
                   defects: Optional[dict] = None, dispatches: Optional[list[dict]] = None,
                   duty: str = "") -> Document:
    """Документ ночного отчёта.

    defects — результат night.defects_of() (позиции «Не ОК», «Не проверено» и
    «Исправлено после отправки»), dispatches — строки общего журнала отправок.
    """
    data = report_id_data
    blocks: list = [text("НОЧНОЙ ОТЧЁТ", bold=True, size=14, align="center")]
    wd = WD_SHORT[data["date_obj"].weekday()]
    blocks.append(text(f"{data['date_obj'].strftime('%d.%m.%Y')} ({wd}) · {data['shift_label']}"
                       + (f" · {company}" if company else ""), align="center"))
    status_line = ("Закрыт вручную" if data["close_reason"] == "manual"
                   else "Закрыт автоматически в 08:00" if data["close_reason"] == "auto"
                   else "Открыт · переоткрыт вручную — автозакрытие отключено"
                   if data.get("reopened_at")
                   else f"Открыт · закроется {_fmt_ts(data['deadline'])}")
    blocks.append(Paragraph((
        Run("Итог: ", bold=True),
        Run(f"{data['result_title'] if data['status'] == 'closed' else 'не подведён (смена идёт)'}"
            f" · {status_line} · областей закрыто {data['progress']['done']} из {data['progress']['total']}"
            f" · проверка электрокаров: {'выполнена' if data['cars_step_done'] else 'не завершена'}"))))

    # ── области, сгруппированные по зонам обхода (v2: зона → объекты → пункты) ──
    cur_zone = None
    for area in data["areas"]:
        if area["is_cars"]:
            continue
        zone_name = area.get("zone_name") or area.get("category") or "Без зоны"
        if zone_name != cur_zone:
            cur_zone = zone_name
            blocks.append(text(zone_name, bold=True, size=12))
        blocks.append(text(area["name"], bold=True, size=11))
        who = (f"Взял: {area['taken_by_name'] or '—'} с {_fmt_ts(area['taken_at'])}"
               if area["status"] != "free" else "Не проверялась")
        if area["closed_at"]:
            who += f" · закрыта {_fmt_ts(area['closed_at'])}"
        blocks.append(text(who, size=9))

        rows = [_head("Пункт проверки", "Результат", "Служба", "Комментарий / фото")]
        for item in area["items"]:
            lines = []
            if item["comment"]:
                lines.append(item["comment"])
            if item["answered_by_name"]:
                lines.append(f"— {item['answered_by_name']}, {_fmt_ts(item['answered_at'])}")
            rows.append([_cell(item["text"]), _cell(item["answer_title"]), _cell(item.get("service_name") or "—"),
                         _cell("\n".join(lines), *[_photo(ph, 60) for ph in photos.get(item["id"], [])])])
        blocks.append(Table(rows, (62, 22, 29, 52)))

    # ── электрокары ──
    cars = data.get("car_checks") or []
    blocks.append(text("Проверка электрокаров", bold=True, size=12))
    if not cars:
        blocks.append(text("Обход каров в эту смену не выполнялся." if not data["cars_step_done"]
                           else "Каров в списке нет."))
    else:
        rows = [_head("Время", "Кар", "Кто", "Найден", "Место / заряд", "Состояние, комментарий")]
        for c in cars:
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
            # место: при перепарковке показываем переход «где нашёл → куда переставил»
            found_loc = c.get("found_location") or ""
            if c.get("moved") and c["location"]:
                place = f"{found_loc or '—'} → {c['location']}"
            else:
                place = c["location"] or found_loc or "—"
            tail = "; ".join(state_bits) + (f"\n{c['comment']}" if c["comment"] else "")
            rows.append([_cell(_fmt_ts(c["checked_at"])), _cell(c["car_number"]), _cell(c["checker_name"] or "—"),
                         _cell("да" if c["found"] else "НЕТ"), _cell(f"{place} · {charge}"),
                         _cell(tail, *[_photo(ph, 44) for ph in c.get("photos", [])])])
        blocks.append(Table(rows, (26, 20, 30, 16, 36, 47)))

    # ── недостатки смены: что направлено службам (этап 5/6) ──
    items = (defects or {}).get("items") or []
    counts = (defects or {}).get("counts") or {}
    blocks.append(text("Недостатки смены", bold=True))
    if not items:
        blocks.append(text("Замечаний нет: все пункты проверены, результат «ОК»."))
    else:
        blocks.append(text(
            f"Всего позиций {counts.get('total', len(items))}: «Не ОК» {counts.get('bad', 0)}, "
            f"«Не проверено» {counts.get('unchecked', 0)}, исправлено после отправки "
            f"{counts.get('fixed_after_dispatch', 0)}"
            + (f" · ночные батлеры смены: {duty}" if duty else ""), size=9))
        rows = [_head("Служба", "Зона / объект", "Пункт", "Комментарий", "Статус")]
        for d in sorted(items, key=lambda x: (x.get("service_name") or "яяя", x.get("area") or "")):
            media = len(d.get("media") or [])
            status = ("исправлено после отправки" if d.get("fixed_after_dispatch")
                      else f"отправлено {_fmt_ts(d.get('dispatched_at'))}" if d.get("dispatched")
                      else "не отправлено")
            rows.append([_cell(d.get("service_name") or "Без службы"),
                         _cell(f"{d.get('zone') or '—'} · {d.get('area') or '—'}"),
                         _cell(f"{d.get('kind_title', '')}: {d.get('text', '')}"),
                         _cell((d.get("comment") or "—") + (f"\nвложений: {media}" if media else "")),
                         _cell(status)])
        blocks.append(Table(rows, (30, 36, 46, 33, 26)))
        blocks.append(text("Позиции «Не проверено» включаются в отчёт; исправленное после отправки повторно "
                           "не направляется и не отзывается.", size=9))

    # ── журнал отправок службам ──
    sends = dispatches or []
    blocks.append(text("Отправки службам", bold=True))
    if not sends:
        blocks.append(text("В эту смену ничего не отправлялось."))
    else:
        rows = [_head("Время", "Кто отправил", "Служба", "Канал", "Получатель", "Позиций / вложений / статус")]
        for d in sends:
            tail = f"{d.get('items_count', 0)} / {d.get('media_count', 0)} / " \
                   f"{'ОШИБКА' if d.get('status') == 'failed' else d.get('status_title', '')}"
            if d.get("attempts", 1) > 1:
                tail += f" (попыток: {d['attempts']})"
            if d.get("error"):
                tail += f"\n{d['error'][:200]}"
            rows.append([_cell(_fmt_ts(d.get("ts"))), _cell(d.get("actor_name") or "—"),
                         _cell(d.get("recipient_name") or "—"),
                         _cell(d.get("channel_title") or d.get("channel") or "—"), _cell(d.get("target") or "—"),
                         _cell(tail)])
        blocks.append(Table(rows, (24, 28, 28, 22, 30, 39)))

    # ── перехваты ──
    icepts = data.get("interceptions") or []
    if icepts:
        blocks.append(text("Перехваты областей", bold=True))
        rows = [_head("Время", "Область", "От кого → кому")]
        for x in icepts:
            rows.append([_cell(_fmt_ts(x["ts"])), _cell(x["area_name"]),
                         _cell(f"{x['from_user_name'] or '—'} → {x['to_user_name'] or '—'}")])
        blocks.append(Table(rows, (32, 60, 73)))

    return Document(blocks, font=Font("Times New Roman", 10.5))


def build_docx(report_id_data: dict, photos: dict[int, list[dict]], *, company: str = "",
               defects: Optional[dict] = None, dispatches: Optional[list[dict]] = None,
               duty: str = "") -> bytes:
    """Собрать .docx ночного отчёта."""
    return write_docx(night_document(report_id_data, photos, company=company, defects=defects,
                                     dispatches=dispatches, duty=duty))


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
