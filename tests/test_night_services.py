"""Ночной отчёт v2 — этап 3: ответственные службы.

Служба — получатель недостатков: закрепляется за пунктом шаблона зоны, у отдельного
объекта переопределяется индивидуальной правкой, в отчёт попадает снимком
(service_id + service_name), поэтому переименование службы не меняет закрытые смены.

Что проверяется:
  * справочник служб виден всем ролям обхода, правки — только менеджменту;
  * каналы доставки: хотя бы один, у письма — ящик; готовность службы к отправке;
  * дубликат названия не проходит;
  * служба пункта шаблона зоны попадает в эффективный чек-лист и в снимок отчёта;
  * своя служба у объекта (индивидуальная правка) не затрагивает остальные объекты зоны;
  * переименование службы обновляет незакрытые смены и НЕ трогает закрытые;
  * отключение службы — мягкое: пункты и история остаются;
  * свой пункт объекта тоже может иметь службу.
"""
from __future__ import annotations

import pytest

VILLA_ZONE = "Семейные виллы"
TEST_PREFIX = "Тестовая служба"


@pytest.fixture(autouse=True)
def _uborka(db):
    """Тестовые службы удаляем из БД: API умеет только мягкое отключение."""
    yield
    from sqlalchemy import select, update

    from app.modules.night.application.catalog import (
        ChecklistItem,
        ChecklistOverride,
        NightCheckItem,
        ZoneChecklistItem,
    )
    from app.modules.notify.application.catalog import ResponsibilityService

    ids = [s.id for s in db.scalars(select(ResponsibilityService)
                                    .where(ResponsibilityService.name.like(f"{TEST_PREFIX}%")))]
    if ids:
        for model in (ZoneChecklistItem, ChecklistItem, ChecklistOverride, NightCheckItem):
            db.execute(update(model).where(model.service_id.in_(ids)).values(service_id=None))
        db.flush()
        for s in db.scalars(select(ResponsibilityService).where(ResponsibilityService.id.in_(ids))):
            db.delete(s)
        db.commit()


def _services(client) -> dict:
    r = client.get("/api/night/services")
    assert r.status_code == 200, r.text
    return r.json()


def _service(client, name: str) -> dict:
    return next(s for s in _services(client)["services"] if s["name"] == name)


def _create(client, name: str, **kw) -> dict:
    body = {"name": name, "sort_order": 900, "active": True, "use_telegram": True,
            "use_email": False, "email_to": "", "email_copy": "", "chat_ids": [], "note": ""}
    body.update(kw)
    r = client.post("/api/night/services", json=body)
    assert r.status_code == 200, r.text
    return r.json()["service"]


def _zone_id(client, name: str = VILLA_ZONE) -> int:
    r = client.get("/api/night/zones")
    assert r.status_code == 200, r.text
    return next(z["id"] for z in r.json()["zones"] if z["name"] == name)


def _zone_item(client, zone_id: int, text: str) -> dict:
    r = client.get(f"/api/night/zones/{zone_id}/items")
    assert r.status_code == 200, r.text
    return next(i for i in r.json()["items"] if i["text"] == text)


def _area_id(client, name: str) -> int:
    r = client.get("/api/night/areas")
    assert r.status_code == 200, r.text
    return next(a["id"] for a in r.json()["areas"] if a["name"] == name)


def _checklist(client, area_id: int) -> dict:
    r = client.get(f"/api/night/areas/{area_id}/checklist")
    assert r.status_code == 200, r.text
    return r.json()


def _override_of(client, area_id: int, zone_item_id: int) -> dict:
    """Текущая индивидуальная правка объекта — чтобы вернуть её после теста.

    Демо-данные общие на прогон: у «Виллы 4001» своя формулировка и своя служба
    заданы сидом, и их удаление сломало бы последующие тесты чек-листа зоны.
    """
    row = [i for i in _checklist(client, area_id)["zone_items"] if i["id"] == zone_item_id][0]
    return {"text": row["override_text"], "disabled": row["disabled"],
            "service_id": row["override_service_id"]}


def _restore_override(client, area_id: int, zone_item_id: int, before: dict) -> None:
    if before["text"] or before["disabled"] or before["service_id"]:
        assert client.put(f"/api/night/areas/{area_id}/overrides/{zone_item_id}",
                          json=before).status_code == 200
    else:
        client.delete(f"/api/night/areas/{area_id}/overrides/{zone_item_id}")


def _set_zone_service(client, item: dict, service_id: int | None) -> None:
    r = client.put(f"/api/night/zone-items/{item['id']}", json={
        "text": item["text"], "sort_order": item["sort_order"], "active": item["active"],
        "service_id": service_id})
    assert r.status_code == 200, r.text


def _report_items(client, rep, zone_name: str | None = None) -> list[dict]:
    """Пункты отчёта; с zone_name — только объекты этой зоны.

    Фильтр по зоне обязателен, когда ищем пункт по тексту: одинаковые формулировки
    («Свет выключен») есть в шаблонах нескольких зон, а служба у них своя.
    """
    r = client.get(f"/api/night/reports/{rep.id}")
    assert r.status_code == 200, r.text
    return [i for s in r.json()["report"]["areas"]
            if zone_name is None or s.get("zone_name") == zone_name
            for i in (s.get("items") or [])]


# ══════════════════════════ справочник и права ══════════════════════════

def test_spravochnik_sluzhb_viden_vsem_rolyam(employee_client, manager_client):
    """Службы нужны батлерам (видно, кому уходит недостаток), поэтому справочник открыт всем."""
    for c in (employee_client, manager_client):
        data = _services(c)
        names = {s["name"] for s in data["services"]}
        assert {"Батлер-сервис", "Хозяйственная служба", "Техническая служба"} <= names, names
    assert _services(employee_client)["can_edit"] is False
    assert _services(manager_client)["can_edit"] is True


def test_pravki_sluzhb_tolko_u_menedzhmenta(employee_client):
    r = employee_client.post("/api/night/services", json={"name": f"{TEST_PREFIX} (без прав)",
                                                          "use_telegram": True})
    assert r.status_code == 403, r.text
    svc = _service(employee_client, "Батлер-сервис")
    assert employee_client.put(f"/api/night/services/{svc['id']}",
                               json={**svc, "name": "Переименовать не выйдет"}).status_code == 403
    assert employee_client.delete(f"/api/night/services/{svc['id']}").status_code == 403


def test_demo_sluzhby_zakrepleny_za_punktami_shablona(employee_client):
    """В демо-данных у каждого пункта шаблона зоны задана служба — иначе отправка невозможна."""
    zone_id = _zone_id(employee_client)
    items = employee_client.get(f"/api/night/zones/{zone_id}/items").json()["items"]
    assert items, "шаблон зоны пуст"
    without = [i["text"] for i in items if not i["service_id"]]
    assert not without, f"пункты без службы: {without}"
    by_name = {s["name"]: s for s in _services(employee_client)["services"]}
    assert by_name["Батлер-сервис"]["items_total"] > 0
    assert by_name["Батлер-сервис"]["ready_email"] is True      # канал «письмо» + ящик
    assert by_name["Батлер-сервис"]["ready_telegram"] is False  # чаты закрепляются позже (этап 4)


# ═══════════════════════ каналы и валидация службы ═══════════════════════

def test_kanalam_nuzhen_poluchatel(manager_client):
    r = manager_client.post("/api/night/services", json={
        "name": f"{TEST_PREFIX} без каналов", "use_telegram": False, "use_email": False})
    assert r.status_code == 400 and "канал" in r.json()["detail"], r.text

    r = manager_client.post("/api/night/services", json={
        "name": f"{TEST_PREFIX} без ящика", "use_telegram": False, "use_email": True,
        "email_to": ""})
    assert r.status_code == 400 and "ящик" in r.json()["detail"], r.text

    svc = _create(manager_client, f"{TEST_PREFIX} почтовая", use_telegram=False, use_email=True,
                  email_to="hozyayka@resort.example", email_copy="butler@resort.example")
    assert svc["ready_email"] is True and svc["ready_telegram"] is False and svc["ready"] is True
    assert svc["email_copy"] == "butler@resort.example"

    # чат включён, но чаты не закреплены → служба не готова к отправке (видно в справочнике)
    tg = _create(manager_client, f"{TEST_PREFIX} чат", use_telegram=True, use_email=False)
    assert tg["ready_telegram"] is False and tg["ready"] is False


def test_dublikat_nazvaniya_ne_prohodit(manager_client):
    _create(manager_client, f"{TEST_PREFIX} дубль")
    r = manager_client.post("/api/night/services", json={
        "name": f"{TEST_PREFIX} ДУБЛЬ", "use_telegram": True})     # регистр не спасает
    assert r.status_code == 409, r.text


def test_nesushchestvuyushchaya_sluzhba_u_punkta_400(manager_client):
    zone_id = _zone_id(manager_client)
    item = _zone_item(manager_client, zone_id, "Свет выключен")
    r = manager_client.put(f"/api/night/zone-items/{item['id']}", json={
        "text": item["text"], "sort_order": item["sort_order"], "active": True,
        "service_id": 999999})
    assert r.status_code == 400 and "не найдена" in r.json()["detail"], r.text


# ═══════════════════ служба в чек-листе и в снимке отчёта ═══════════════════

def test_sluzhba_punkta_shablona_popadaet_v_otchet(manager_client, employee_client, open_shift):
    zone_id = _zone_id(manager_client)
    item = _zone_item(manager_client, zone_id, "Свет выключен")
    svc = _create(manager_client, f"{TEST_PREFIX} свет", use_telegram=True)
    _set_zone_service(manager_client, item, svc["id"])
    try:
        # служба видна в шаблоне зоны и в эффективном чек-листе каждого объекта зоны
        assert _zone_item(manager_client, zone_id, "Свет выключен")["service_name"] == svc["name"]
        cl = _checklist(manager_client, _area_id(manager_client, "Вилла 4003"))
        eff = [i for i in cl["effective"] if i["text"] == "Свет выключен"]
        assert eff and eff[0]["service_id"] == svc["id"] and eff[0]["service_name"] == svc["name"]

        # и снимком — в отчёте смены (батлер видит, кому уходит недостаток)
        with open_shift() as rep:
            rows = [i for i in _report_items(employee_client, rep, VILLA_ZONE)
                    if i["text"] == "Свет выключен"]
            assert len(rows) == 12, f"вилл в зоне 12, пунктов в отчёте {len(rows)}"
            assert all(i["service_name"] == svc["name"] for i in rows)
            # у зоны с такой же формулировкой служба своя — снимок её не задел
            other = [i for i in _report_items(employee_client, rep, "Президентские виллы")
                     if i["text"] == "Свет выключен"]
            assert other and all(i["service_name"] != svc["name"] for i in other)
    finally:
        _set_zone_service(manager_client, _zone_item(manager_client, zone_id, "Свет выключен"),
                          item.get("service_id"))


def test_svoya_sluzhba_u_obekta_ne_trogaet_zonu(manager_client, open_shift):
    zone_id = _zone_id(manager_client)
    item = _zone_item(manager_client, zone_id, "Вилла убрана")
    svc = _create(manager_client, f"{TEST_PREFIX} детская", use_email=True,
                  email_to="butler@resort.example")
    area_4001 = _area_id(manager_client, "Вилла 4001")
    area_4003 = _area_id(manager_client, "Вилла 4003")
    before = _checklist(manager_client, area_4003)
    before_4001 = _override_of(manager_client, area_4001, item["id"])   # правка из демо-данных

    r = manager_client.put(f"/api/night/areas/{area_4001}/overrides/{item['id']}", json={
        "text": "Вилла убрана (включая детскую комнату)", "disabled": False,
        "service_id": svc["id"]})
    assert r.status_code == 200, r.text
    eff = {i["text"]: i for i in r.json()["effective"]}
    own = eff["Вилла убрана (включая детскую комнату)"]
    assert own["service_id"] == svc["id"] and own["service_own"] is True

    # у соседнего объекта зоны служба осталась как в шаблоне
    other = _checklist(manager_client, area_4003)
    other_item = [i for i in other["zone_items"] if i["id"] == item["id"]][0]
    assert other_item["override_service_id"] is None
    assert other_item["effective_service_id"] == item["service_id"]
    assert [i["text"] for i in other["effective"]] == [i["text"] for i in before["effective"]]

    # сброс правки возвращает службу шаблона зоны
    assert manager_client.delete(
        f"/api/night/areas/{area_4001}/overrides/{item['id']}").status_code == 200
    cl = _checklist(manager_client, area_4001)
    row = [i for i in cl["zone_items"] if i["id"] == item["id"]][0]
    assert row["effective_service_id"] == item["service_id"]

    _restore_override(manager_client, area_4001, item["id"], before_4001)


def test_pravka_tolko_sluzhby_sohranyaet_pravku(manager_client):
    """Правка объекта живёт, даже если изменена только служба (без своей формулировки)."""
    zone_id = _zone_id(manager_client)
    item = _zone_item(manager_client, zone_id, "Витражи закрыты")
    area = _area_id(manager_client, "Вилла 4005")
    svc = _create(manager_client, f"{TEST_PREFIX} витражи", use_telegram=True)
    before = _override_of(manager_client, area, item["id"])
    r = manager_client.put(f"/api/night/areas/{area}/overrides/{item['id']}",
                           json={"text": "", "disabled": False, "service_id": svc["id"]})
    assert r.status_code == 200, r.text
    row = [i for i in _checklist(manager_client, area)["zone_items"] if i["id"] == item["id"]][0]
    assert row["override_service_id"] == svc["id"]
    assert row["effective_text"] == item["text"]        # формулировка как в шаблоне
    _restore_override(manager_client, area, item["id"], before)


# ═════════════════ снимок: переименование и закрытые смены ═════════════════

def test_pereimenovanie_sluzhby_ne_menyaet_zakrytye_smeny(manager_client, db, open_shift):
    from app.modules.night.application.catalog import NightReport

    zone_id = _zone_id(manager_client)
    item = _zone_item(manager_client, zone_id, "Свет выключен")
    svc = _create(manager_client, f"{TEST_PREFIX} старое имя", use_telegram=True)
    _set_zone_service(manager_client, item, svc["id"])
    try:
        with open_shift() as rep:
            rep_id = rep.id
            assert [i for i in _report_items(manager_client, rep, VILLA_ZONE)
                    if i["text"] == "Свет выключен"][0]["service_name"] == svc["name"]
            # «закрываем» смену напрямую: автозакрытие в тестах не ждём
            row = db.get(NightReport, rep_id)
            row.status, row.result = "closed", "full"
            db.commit()

            r = manager_client.put(f"/api/night/services/{svc['id']}", json={
                "name": f"{TEST_PREFIX} новое имя", "sort_order": svc["sort_order"],
                "active": True, "use_telegram": True, "use_email": False, "email_to": "",
                "email_copy": "", "chat_ids": [], "note": ""})
            assert r.status_code == 200, r.text
            # закрытая смена — снимок: название службы остаётся прежним
            assert [i for i in _report_items(manager_client, rep)
                    if i["text"] == "Свет выключен"][0]["service_name"] == svc["name"]
    finally:
        _set_zone_service(manager_client, _zone_item(manager_client, zone_id, "Свет выключен"),
                          item.get("service_id"))


def test_otklyuchenie_sluzhby_myagkoe(manager_client):
    zone_id = _zone_id(manager_client)
    item = _zone_item(manager_client, zone_id, "Вилла укомплектована")
    svc = _create(manager_client, f"{TEST_PREFIX} на отключение", use_telegram=True)
    _set_zone_service(manager_client, item, svc["id"])

    r = manager_client.delete(f"/api/night/services/{svc['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["items_total"] >= 1                 # видно, сколько пунктов придётся переназначить
    row = _service(manager_client, f"{TEST_PREFIX} на отключение")
    assert row["active"] is False
    # пункт службу не потерял — история и снимки целы
    assert _zone_item(manager_client, zone_id, "Вилла укомплектована")["service_id"] == svc["id"]

    _set_zone_service(manager_client, _zone_item(manager_client, zone_id, "Вилла укомплектована"),
                      item.get("service_id"))


def test_svoy_punkt_obekta_so_sluzhboy(manager_client):
    area = _area_id(manager_client, "Вилла 4007")
    svc = _create(manager_client, f"{TEST_PREFIX} кроватка", use_email=True,
                  email_to="butler@resort.example")
    r = manager_client.post(f"/api/night/areas/{area}/items", json={
        "text": "Детская кроватка исправна", "sort_order": 95, "active": True,
        "service_id": svc["id"]})
    assert r.status_code == 200, r.text
    item_id = r.json()["id"]
    try:
        own = [i for i in _checklist(manager_client, area)["own_items"] if i["id"] == item_id][0]
        assert own["service_name"] == svc["name"]
        # id своего пункта и пункта шаблона зоны — из разных таблиц и могут совпасть,
        # поэтому смотрим на src
        eff = [i for i in _checklist(manager_client, area)["effective"]
               if i["src"] == "area" and i["id"] == item_id]
        assert eff and eff[0]["service_id"] == svc["id"]
    finally:
        assert manager_client.delete(f"/api/night/items/{item_id}").status_code == 200
