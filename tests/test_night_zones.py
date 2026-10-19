"""Ночной отчёт v2 — этап 1: зоны обхода, шаблон чек-листа зоны, правки объекта.

Что проверяется (переработка ночного отчёта от 19.10.2026, навигация «зона → объект →
чек-лист»):
  * зоны — первый уровень обхода: справочник виден всем ролям, правки только менеджменту;
  * миграция: зоны вырастают из прежних «категорий» областей, идемпотентно;
  * чек-лист задаётся НА ЗОНУ (zone_checklist_items): у всех объектов зоны он одинаковый,
    новый пункт шаблона попадает в чек-листы всех объектов и в ещё не начатые смены;
  * индивидуальные особенности объекта (checklist_overrides): своя формулировка,
    отключение пункта; свой пункт объекта — checklist_items(area_id);
  * отчёт хранит СНЯМОК (эффективный чек-лист + название зоны): закрытые смены и отметки
    в начатых объектах правки справочников не меняют.

Демо-данные общие на прогон, поэтому каждый тест убирает за собой созданные записи.
"""
from __future__ import annotations

import datetime as dt
from contextlib import contextmanager

SHIFT_D = dt.date(2026, 5, 20)          # фиксированная смена: тесты не зависят от даты прогона
VILLA_ZONE = "Семейные виллы"


def _zones(client) -> list[dict]:
    r = client.get("/api/night/zones")
    assert r.status_code == 200, r.text
    return r.json()["zones"]


def _zone(client, name: str) -> dict:
    return next(z for z in _zones(client) if z["name"] == name)


def _areas(client, zone_id: int | None = None) -> list[dict]:
    r = client.get("/api/night/areas")
    assert r.status_code == 200, r.text
    out = r.json()["areas"]
    return [a for a in out if zone_id is None or a["zone_id"] == zone_id]


@contextmanager
def _smena(db, freeze, shift_d: dt.date = SHIFT_D):
    """Открытый отчёт фиксированной смены (время заморожено) + уборка за тестом.

    Смену берём прошлую и фиксируем время, иначе отчёт был бы закрыт и тест
    пропускался бы почти всегда. Удаляем созданные отметки/области и сам отчёт;
    журнал истории не редактируется по правилам ТЗ.
    """
    from sqlalchemy import select

    from app.models import NightAreaSection, NightCheckItem, NightReport
    from app.night import ensure_report

    with freeze(f"{shift_d.isoformat()} 23:00:00"):      # 02:00 МСК следующих суток — смена идёт
        rep = ensure_report(db, shift_d)
        assert rep is not None, "отчёт для идущей смены не создан"
        try:
            yield rep
        finally:
            sections = list(db.scalars(select(NightAreaSection)
                                       .where(NightAreaSection.report_id == rep.id)))
            for sec in sections:
                for ni in db.scalars(select(NightCheckItem)
                                     .where(NightCheckItem.section_id == sec.id)):
                    db.delete(ni)
                db.delete(sec)
            fresh = db.get(NightReport, rep.id)
            if fresh is not None:
                db.delete(fresh)
            db.commit()


def _payload(client, report_id: int) -> dict:
    r = client.get(f"/api/night/reports/{report_id}")
    assert r.status_code == 200, r.text
    return r.json()["report"]


def _sections_of_zone(rep: dict, zone_name: str) -> list[dict]:
    return [a for a in rep["areas"] if not a["is_cars"] and a["zone_name"] == zone_name]


def _texts(section: dict) -> list[str]:
    return [i["text"] for i in section["items"]]


# ─────────────────────────── справочник зон и права ───────────────────────────
def test_zony_vidny_vsem_rolyam(employee_client, manager_client):
    """Зоны нужны батлерам для обхода, поэтому справочник виден всем ролям."""
    for c in (employee_client, manager_client):
        zones = _zones(c)
        names = {z["name"] for z in zones}
        assert VILLA_ZONE in names, names
        villa = next(z for z in zones if z["name"] == VILLA_ZONE)
        assert villa["areas_total"] == 12, "в демо-зоне должно быть 12 однотипных вилл"
        assert villa["items_total"] >= 4, "у зоны нет шаблона чек-листа"


def test_prava_na_spravochnik_zon(employee_client, manager_client):
    """Правки зон — по праву night.edit (19.10.2026; раньше — роль is_manager);
    батлер только смотрит."""
    assert employee_client.post("/api/night/zones", json={"name": "Зона батлера"}).status_code == 403
    r = manager_client.post("/api/night/zones", json={"name": "Тестовая зона", "sort_order": 900})
    assert r.status_code == 200, r.text
    zone_id = r.json()["id"]
    try:
        assert employee_client.put(f"/api/night/zones/{zone_id}",
                                   json={"name": "Переименовано"}).status_code == 403
        assert employee_client.delete(f"/api/night/zones/{zone_id}").status_code == 403
        r = manager_client.put(f"/api/night/zones/{zone_id}",
                               json={"name": "Тестовая зона 2", "sort_order": 901, "active": True})
        assert r.status_code == 200, r.text
        # дубль названия недопустим
        assert manager_client.post("/api/night/zones",
                                   json={"name": "Тестовая зона 2"}).status_code == 409
        r = manager_client.delete(f"/api/night/zones/{zone_id}")
        assert r.status_code == 200 and r.json()["ok"] is True
        assert next(z for z in _zones(manager_client) if z["id"] == zone_id)["active"] is False
    finally:
        from app.db import SessionLocal
        from app.models import NightZone
        db = SessionLocal()
        try:
            z = db.get(NightZone, zone_id)
            if z is not None:
                db.delete(z)
                db.commit()
        finally:
            db.close()


# ─────────────────────────── миграция зон из категорий ───────────────────────────
def test_migraciya_zon_iz_kategoriy_idempotentna(db):
    """migrate_night_zones(): зоны из «категорий» областей, повторный вызов ничего не плодит."""
    from sqlalchemy import func, select

    from app.migrations import migrate_night_zones
    from app.models import NightArea, NightZone

    migrate_night_zones()
    first = db.scalar(select(func.count()).select_from(NightZone))
    areas_with_zone = db.scalar(select(func.count()).select_from(NightArea)
                                .where(NightArea.zone_id.is_not(None)))
    migrate_night_zones()
    assert db.scalar(select(func.count()).select_from(NightZone)) == first, \
        "повторная миграция создала дубликаты зон"
    assert db.scalar(select(func.count()).select_from(NightArea)
                     .where(NightArea.zone_id.is_not(None))) == areas_with_zone
    assert areas_with_zone == db.scalar(select(func.count()).select_from(NightArea)), \
        "не все области привязаны к зонам"


# ─────────────────────────── шаблон чек-листа зоны ───────────────────────────
def test_shablon_zony_odinakov_dlya_vseh_obektov(manager_client, db, freeze):
    """У всех вилл зоны один чек-лист — кроме объектов с индивидуальными правками."""
    with _smena(db, freeze) as rep:
        data = _payload(manager_client, rep.id)
        villas = _sections_of_zone(data, VILLA_ZONE)
        assert len(villas) == 12, f"в отчёт попало {len(villas)} вилл вместо 12"
        base = ["Витражи закрыты", "Свет выключен", "Вилла убрана", "Вилла укомплектована"]

        by_name = {v["name"]: v for v in villas}
        # обычный объект: ровно шаблон зоны
        assert _texts(by_name["Вилла 4003"]) == base, _texts(by_name["Вилла 4003"])
        # индивидуальная формулировка + свой пункт объекта (демо-данные сидинга)
        t4001 = _texts(by_name["Вилла 4001"])
        assert "Вилла убрана (включая детскую комнату)" in t4001, t4001
        assert "Вилла убрана" not in t4001, "своя формулировка не заменила текст шаблона"
        assert "Детская кроватка установлена и исправна" in t4001, t4001
        # отключённый у объекта пункт шаблона в чек-лист не попадает
        t4002 = _texts(by_name["Вилла 4002"])
        assert "Вилла укомплектована" not in t4002, t4002
        assert len(t4002) == len(base) - 1, t4002


def test_punkt_shablona_zony_popadaet_vo_vse_obekty(manager_client, db, freeze):
    """Новый пункт шаблона зоны — во все объекты зоны и в ещё не начатые смены."""
    zone = _zone(manager_client, VILLA_ZONE)
    r = manager_client.post(f"/api/night/zones/{zone['id']}/items",
                            json={"text": 'Тест: балкон закрыт', "sort_order": 95})
    assert r.status_code == 200, r.text
    item_id = r.json()["id"]
    try:
        assert r.json()["sections_refreshed"] >= 0
        with _smena(db, freeze, dt.date(2026, 5, 21)) as rep:
            data = _payload(manager_client, rep.id)
            villas = _sections_of_zone(data, VILLA_ZONE)
            assert len(villas) == 12
            for v in villas:
                assert "Тест: балкон закрыт" in _texts(v), f"пункта нет у {v['name']}"
            # пункт шаблона зоны — не в других зонах
            others = [a for a in data["areas"] if not a["is_cars"] and a["zone_name"] != VILLA_ZONE]
            assert others, "в отчёте нет других зон"
            for a in others:
                assert "Тест: балкон закрыт" not in _texts(a), a["name"]
    finally:
        r = manager_client.delete(f"/api/night/zone-items/{item_id}")
        assert r.status_code == 200, r.text


def test_pravka_teksta_punkta_zony_obnovlyaet_nezakrytye_smeny(manager_client, db, freeze):
    """Правка пункта шаблона обновляет текст в незакрытых сменах, закрытые не трогает."""
    zone = _zone(manager_client, VILLA_ZONE)
    r = manager_client.post(f"/api/night/zones/{zone['id']}/items",
                            json={"text": "Тест: свет в подвале", "sort_order": 96})
    item_id = r.json()["id"]
    try:
        with _smena(db, freeze, dt.date(2026, 5, 22)) as rep:
            before = _payload(manager_client, rep.id)
            villa = _sections_of_zone(before, VILLA_ZONE)[0]
            assert "Тест: свет в подвале" in _texts(villa)
            # отметим пункт, чтобы проверить сохранение ответа при правке текста
            item = next(i for i in villa["items"] if i["text"] == "Тест: свет в подвале")
            r2 = manager_client.put(f"/api/night/items/{item['id']}/answer",
                                    json={"answer": "bad", "comment": "лампа мигает"})
            assert r2.status_code == 200, r2.text

            r3 = manager_client.put(f"/api/night/zone-items/{item_id}",
                                    json={"text": "Тест: свет в подвале выключен",
                                          "sort_order": 96, "active": True})
            assert r3.status_code == 200, r3.text
            after = _payload(manager_client, rep.id)
            villa2 = _sections_of_zone(after, VILLA_ZONE)[0]
            assert "Тест: свет в подвале выключен" in _texts(villa2), _texts(villa2)
            # ответ батлера не потерян
            kept = next(i for i in villa2["items"] if i["id"] == item["id"])
            assert kept["answer"] == "bad" and kept["comment"] == "лампа мигает"
    finally:
        manager_client.delete(f"/api/night/zone-items/{item_id}")


# ─────────────────────────── индивидуальные правки объекта ───────────────────────────
def test_individualnye_pravki_obekta(manager_client, db, freeze):
    """Своя формулировка и отключение пункта у одного объекта; сброс возвращает шаблон."""
    zone = _zone(manager_client, VILLA_ZONE)
    area = next(a for a in _areas(manager_client, zone["id"]) if a["name"] == "Вилла 4003")
    items = manager_client.get(f"/api/night/zones/{zone['id']}/items").json()["items"]
    vit = next(i for i in items if i["text"] == "Витражи закрыты")
    light = next(i for i in items if i["text"] == "Свет выключен")

    with _smena(db, freeze, dt.date(2026, 5, 23)) as rep:
        # своя формулировка
        r = manager_client.put(f"/api/night/areas/{area['id']}/overrides/{vit['id']}",
                               json={"text": "Витражи и балконные двери закрыты", "disabled": False})
        assert r.status_code == 200, r.text
        # отключение пункта
        r = manager_client.put(f"/api/night/areas/{area['id']}/overrides/{light['id']}",
                               json={"text": "", "disabled": True})
        assert r.status_code == 200, r.text

        data = _payload(manager_client, rep.id)
        sec = next(a for a in data["areas"] if a["area_id"] == area["id"])
        texts = _texts(sec)
        assert "Витражи и балконные двери закрыты" in texts, texts
        assert "Витражи закрыты" not in texts, texts
        assert "Свет выключен" not in texts, texts
        # у соседнего объекта зоны чек-лист не изменился
        other = next(a for a in _sections_of_zone(data, VILLA_ZONE) if a["name"] == "Вилла 4004")
        assert "Витражи закрыты" in _texts(other) and "Свет выключен" in _texts(other)

        # счётчик индивидуальных правок виден в справочнике зоны
        zd = manager_client.get(f"/api/night/zones/{zone['id']}/items").json()
        assert next(i for i in zd["items"] if i["id"] == vit["id"])["overrides"] == 1
        assert next(i for i in zd["items"] if i["id"] == light["id"])["overrides"] == 1

        # сброс — пункт снова как в шаблоне зоны
        r = manager_client.delete(f"/api/night/areas/{area['id']}/overrides/{vit['id']}")
        assert r.status_code == 200 and r.json()["sections_refreshed"] >= 1, r.text
        r = manager_client.delete(f"/api/night/areas/{area['id']}/overrides/{light['id']}")
        assert r.status_code == 200 and r.json()["sections_refreshed"] >= 1, r.text
        data = _payload(manager_client, rep.id)
        sec = next(a for a in data["areas"] if a["area_id"] == area["id"])
        assert _texts(sec) == ["Витражи закрыты", "Свет выключен", "Вилла убрана",
                               "Вилла укомплектована"], _texts(sec)


def test_pravka_punkta_chuzhoi_zony_otklonyaetsya(manager_client):
    """Нельзя править пункт чужой зоны: защита от переноса пункта между зонами."""
    zones = _zones(manager_client)
    assert len(zones) >= 2
    other = next(z for z in zones if z["name"] != VILLA_ZONE)
    item = manager_client.post(f"/api/night/zones/{other['id']}/items",
                               json={"text": "Тест: пункт другой зоны"}).json()
    villa_area = next(a for a in _areas(manager_client, _zone(manager_client, VILLA_ZONE)["id"])
                      if a["name"] == "Вилла 4005")
    try:
        r = manager_client.put(f"/api/night/areas/{villa_area['id']}/overrides/{item['id']}",
                               json={"text": "чужой пункт", "disabled": False})
        assert r.status_code == 400, r.text
        assert "не из шаблона зоны" in r.json()["detail"]
    finally:
        manager_client.delete(f"/api/night/zone-items/{item['id']}")


# ─────────────────────────── снимок отчёта: зоны и прогресс ───────────────────────────
def test_otchet_soderzhit_zony_i_snimok_nazvaniya(manager_client, db, freeze):
    """В отчёте — прогресс по зонам и снимок названия зоны у каждой области."""
    with _smena(db, freeze, dt.date(2026, 5, 24)) as rep:
        data = _payload(manager_client, rep.id)
        assert data["zones"], "в отчёте нет списка зон"
        villa = next(z for z in data["zones"] if z["name"] == VILLA_ZONE)
        assert villa["areas_total"] == 12 and villa["items_total"] == 12 * 4, villa
        assert villa["done"] + villa["taken"] + villa["free"] == villa["areas_total"]
        # шаг «Проверка электрокаров» в зоны не входит
        assert all(z["name"] != "Проверка электрокаров" for z in data["zones"])
        assert any(a["is_cars"] for a in data["areas"])
        # снимок зоны у области
        sec = next(a for a in data["areas"] if a["name"] == "Вилла 4006")
        assert sec["zone_name"] == VILLA_ZONE and sec["zone_id"] == villa["zone_id"]

        # отметка меняет прогресс зоны
        item = next(i for i in sec["items"] if i["text"] == "Витражи закрыты")
        r = manager_client.put(f"/api/night/items/{item['id']}/answer",
                               json={"answer": "bad", "comment": "не закрыт"})
        assert r.status_code == 200, r.text
        data2 = _payload(manager_client, rep.id)
        villa2 = next(z for z in data2["zones"] if z["name"] == VILLA_ZONE)
        assert villa2["items_bad"] == 1 and villa2["items_answered"] == 1, villa2


def test_pereimenovanie_zony_ne_trogaet_zakrytuyu_smenu(manager_client, db, freeze):
    """Переименование зоны обновляет только открытые смены: закрытые остаются снимком."""
    r = manager_client.post("/api/night/zones", json={"name": "Тест: зона на переименование"})
    zone_id = r.json()["id"]
    area_r = manager_client.post("/api/night/areas", json={
        "name": "Тест: объект зоны переименования", "zone_id": zone_id, "sort_order": 990,
        "active": True})
    area_id = area_r.json()["id"]
    try:
        with _smena(db, freeze, dt.date(2026, 5, 25)) as rep:
            before = _payload(manager_client, rep.id)
            assert any(z["name"] == "Тест: зона на переименование" for z in before["zones"])
            # закрываем смену — дальше она только для чтения
            r2 = manager_client.post(f"/api/night/reports/{rep.id}/close",
                                     json={"force_unanswered": True})
            assert r2.status_code == 200, r2.text

            r3 = manager_client.put(f"/api/night/zones/{zone_id}",
                                    json={"name": "Тест: зона переименована",
                                          "sort_order": 990, "active": True})
            assert r3.status_code == 200, r3.text
            after = _payload(manager_client, rep.id)
            names = {z["name"] for z in after["zones"]}
            assert "Тест: зона на переименование" in names, names
            assert "Тест: зона переименована" not in names, \
                "название зоны в закрытой смене изменилось — нарушен снимок"
    finally:
        manager_client.delete(f"/api/night/areas/{area_id}")
        manager_client.delete(f"/api/night/zones/{zone_id}")
        from app.db import SessionLocal
        from app.models import NightArea, NightZone
        dbx = SessionLocal()
        try:
            a = dbx.get(NightArea, area_id)
            if a is not None:
                dbx.delete(a)
            z = dbx.get(NightZone, zone_id)
            if z is not None:
                dbx.delete(z)
            dbx.commit()
        finally:
            dbx.close()


def test_seriya_obektov_poluchaet_shablon_zony(manager_client, db, freeze):
    """Мастер серии: созданные объекты сразу проверяются по чек-листу зоны."""
    zone = _zone(manager_client, VILLA_ZONE)
    r = manager_client.post("/api/night/areas/bulk", json={
        "prefix": "Тест-вилла ", "start": 9101, "count": 3, "zone_id": zone["id"],
        "category": zone["name"]})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 3, r.text
    created = [a for a in _areas(manager_client, zone["id"]) if a["name"].startswith("Тест-вилла ")]
    try:
        assert len(created) == 3
        for a in created:
            assert a["effective_total"] == zone["items_total"], \
                f"у {a['name']} чек-лист зоны не применился: {a['effective_total']}"
        with _smena(db, freeze, dt.date(2026, 5, 26)) as rep:
            data = _payload(manager_client, rep.id)
            villa_zone = next(z for z in data["zones"] if z["name"] == VILLA_ZONE)
            assert villa_zone["areas_total"] == 15, villa_zone
            sec = next(a for a in data["areas"] if a["name"] == "Тест-вилла 9101")
            assert len(_texts(sec)) == zone["items_total"], _texts(sec)
    finally:
        for a in created:
            manager_client.delete(f"/api/night/areas/{a['id']}")
        from app.db import SessionLocal
        from app.models import NightArea
        dbx = SessionLocal()
        try:
            for a in created:
                row = dbx.get(NightArea, a["id"])
                if row is not None:
                    dbx.delete(row)
            dbx.commit()
        finally:
            dbx.close()
