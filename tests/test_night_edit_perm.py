"""Право night.edit (19.10.2026): справочник ночного обхода — по ключу права, а не по роли.

Справочник обхода (зоны, объекты, чек-листы, службы) был единственным местом, где
доступ решала роль (is_manager = admin/manager/supervisor). Теперь это ключ каталога
PERMISSIONS: базово выдан тем же ролям (поведение не меняется), но его можно выдать
или снять грантом — группой или индивидуально («Настройки → Права доступа»).
Сам справочник переехал из модалки раздела «Ночной отчёт» в «Настройки → Ночной обход»
(docs/PROPOSAL-SETTINGS-IA-2026-10-19.md).

Тесты чистят за собой: демо-данные общих сценариев (test_night_services,
test_night_zones) не должны видеть хвостов.
"""
from __future__ import annotations

ZONE_NAME = "Тест-night.edit-зона"
AREA_NAME = "Тест-night.edit-объект"
SVC_NAME = "Тест-night.edit-служба"


def _cleanup(admin, ids: dict) -> None:
    """Убрать созданные сущности (зоны/объекты/службы удаляются мягко)."""
    if ids.get("item"):
        admin.delete(f"/api/night/zone-items/{ids['item']}")
    if ids.get("area"):
        admin.delete(f"/api/night/areas/{ids['area']}")
    if ids.get("zone"):
        admin.delete(f"/api/night/zones/{ids['zone']}")
    if ids.get("svc"):
        admin.delete(f"/api/night/services/{ids['svc']}")


def test_night_edit_v_kataloge_prav(admin_client):
    """Ключ в каталоге, у супервайзера по умолчанию есть, у батлера нет."""
    cat = admin_client.get("/api/access").json()
    keys = {p["key"]: p for p in cat["permissions"]}
    assert "night.edit" in keys
    assert keys["night.edit"]["section"] == "Ночной отчёт"
    gromova = next(u for u in cat["users"] if u["username"] == "gromova")   # supervisor
    ivanov = next(u for u in cat["users"] if u["username"] == "ivanov")     # employee
    assert "night.edit" in gromova["effective"]
    assert "night.edit" not in ivanov["effective"]


def test_supervisor_pravit_spravochnik(manager_client, employee_client):
    """Супервайзер (manager_client = gromova) справочник правит — как и раньше,
    когда доступ решала роль; батлер — только смотрит."""
    assert manager_client.get("/api/night/zones").json()["can_edit"] is True
    assert employee_client.get("/api/night/zones").json()["can_edit"] is False
    assert employee_client.get("/api/night/services").json()["can_edit"] is False

    r = manager_client.post("/api/night/zones", json={"name": ZONE_NAME, "sort_order": 950})
    assert r.status_code == 200, r.text
    zone_id = r.json()["id"]
    try:
        assert employee_client.post("/api/night/zones",
                                    json={"name": ZONE_NAME + " 2"}).status_code == 403
        r = manager_client.put(f"/api/night/zones/{zone_id}",
                               json={"name": ZONE_NAME, "sort_order": 951, "active": True})
        assert r.status_code == 200, r.text
    finally:
        assert manager_client.delete(f"/api/night/zones/{zone_id}").status_code == 200


def test_grant_vydaet_i_snimaet_dostup(admin_client, employee_client):
    """Индивидуальный грант: батлеру можно выдать night.edit и снять обратно."""
    cat = admin_client.get("/api/access").json()
    ivanov = next(u for u in cat["users"] if u["username"] == "ivanov")
    uid = ivanov["id"]
    created = []
    try:
        assert employee_client.post("/api/night/zones",
                                    json={"name": ZONE_NAME + " grant"}).status_code == 403
        r = admin_client.put(f"/api/access/users/{uid}/grants",
                             json={"grants": {"night.edit": "allow"}})
        assert r.status_code == 200, r.text
        assert "night.edit" in employee_client.get("/api/auth/me").json()["permissions"]
        assert employee_client.get("/api/night/zones").json()["can_edit"] is True
        r = employee_client.post("/api/night/zones",
                                 json={"name": ZONE_NAME + " grant", "sort_order": 960})
        assert r.status_code == 200, r.text
        created.append(r.json()["id"])
        # сняли грант — доступ снова закрыт
        admin_client.put(f"/api/access/users/{uid}/grants", json={"grants": {}})
        assert employee_client.post("/api/night/zones",
                                    json={"name": ZONE_NAME + " grant2"}).status_code == 403
    finally:
        admin_client.put(f"/api/access/users/{uid}/grants", json={"grants": {}})
        for zid in created:
            admin_client.delete(f"/api/night/zones/{zid}")


def test_health_sverdki_night(admin_client):
    """«Обзор» покрывает справочник обхода: зона с объектами, но без шаблона,
    и служба без настроенного канала доставки (APP-NIGHT-* / APP-SVC-*)."""
    ids: dict = {}
    try:
        r = admin_client.post("/api/night/zones", json={"name": ZONE_NAME + " health", "sort_order": 970})
        assert r.status_code == 200, r.text
        ids["zone"] = r.json()["id"]
        r = admin_client.post("/api/night/areas", json={
            "name": AREA_NAME, "zone_id": ids["zone"], "category": ZONE_NAME + " health",
            "sort_order": 970, "active": True})
        assert r.status_code == 200, r.text
        ids["area"] = r.json()["id"]

        d = admin_client.get("/api/engine-settings/health").json()
        hits = [c for c in d["checks"] if c["code"] == "APP-NIGHT-ZONE-NO-TEMPLATE"]
        assert any(ZONE_NAME in c["text"] and c["screen"] == "night" for c in hits), hits

        # пункт шаблона задали — замечание зоны уходит
        r = admin_client.post(f"/api/night/zones/{ids['zone']}/items",
                              json={"text": "Тестовый пункт health", "sort_order": 10, "active": True})
        assert r.status_code == 200, r.text
        ids["item"] = r.json()["id"]
        d = admin_client.get("/api/engine-settings/health").json()
        assert not any(ZONE_NAME in c["text"] and c["code"] == "APP-NIGHT-ZONE-NO-TEMPLATE"
                       for c in d["checks"]), d["checks"]

        # служба с невыбранным получателем: канал заявлен, но чат не закреплён
        r = admin_client.post("/api/night/services", json={
            "name": SVC_NAME + " health", "sort_order": 970, "active": True,
            "use_telegram": True, "use_email": False, "chat_ids": []})
        assert r.status_code == 200, r.text
        ids["svc"] = r.json()["id"]
        d = admin_client.get("/api/engine-settings/health").json()
        hits = [c for c in d["checks"] if c["code"] == "APP-SVC-NO-CHANNEL"]
        assert any(SVC_NAME in c["text"] and c["screen"] == "night" for c in hits), hits
    finally:
        _cleanup(admin_client, ids)
