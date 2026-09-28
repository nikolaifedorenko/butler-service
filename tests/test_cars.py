"""Электрокары: операции парка, права, история, ночной обход, отдача фото.

Модуль добавлен в проект последним и не имел ни одного теста; здесь закрыты
основные сценарии ТЗ и две найденные регрессии:
  * NameError в cars.return_car() — условие `(by_employee_id or name)` обращалось
    к несуществующей переменной, из-за чего ЛЮБОЙ возврат кара без явного
    employee_id (обычный случай: сотрудник возвращает свой кар) падал в 500;
  * отсутствующий маршрут /api/photos/{id}/file — photos.photo_url() всегда
    отдавал эту ссылку, а маршрут существовал только как /api/night/photos/…,
    поэтому каждое загруженное фото показывалось как 404.

Каждый тест возвращает парк в исходное состояние: демо-данные общие на прогон.
"""
from __future__ import annotations

RETURN_FORM = {"by_name": "", "location": "Парковка у главного входа", "charge": "half",
               "canopy": "true", "condition": "ok", "trash": "false", "clean": "true",
               "on_charge": "false", "comment": ""}


def _park(client) -> list[dict]:
    return client.get("/api/cars").json()["cars"]


def _car_by_number(client, number: str) -> dict:
    return next(c for c in _park(client) if c["number"] == number)


def _free_car(client) -> dict:
    cars = [c for c in _park(client) if c["status"] in ("free", "charging")]
    assert cars, "в демо-парке нет свободного кара"
    return cars[0]


def _return_car(client, car_id: int, **overrides) -> dict:
    form = {**RETURN_FORM, **overrides}
    r = client.post(f"/api/cars/{car_id}/return", data=form)
    return r


# ───────────────────────────── видимость и справочники ─────────────────────────────
def test_park_viden_vsem_rolyam(employee_client, manager_client):
    for c in (employee_client, manager_client):
        r = c.get("/api/cars")
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["cars"]) >= 5, "демо-парк не загружен"
        assert {"id", "number", "status", "status_title", "location", "charge_title"} <= set(data["cars"][0])


def test_meta_soderzhit_slovari_i_prava(employee_client, manager_client):
    emp = employee_client.get("/api/cars/meta").json()
    mgr = manager_client.get("/api/cars/meta").json()
    assert {s["code"] for s in emp["statuses"]} >= {"free", "busy", "charging", "maintenance"}
    assert emp["can_manage"] is False, "сотрудник не должен управлять парком"
    assert mgr["can_manage"] is True


def test_otkluchennye_kary_skryty_ot_sotrudnika(employee_client, admin_client):
    car = _car_by_number(admin_client, "5")
    r = admin_client.put(f"/api/cars/{car['id']}", json={"active": False})
    assert r.status_code == 200, r.text
    try:
        assert all(c["number"] != "5" for c in _park(employee_client)), \
            "отключённый кар виден сотруднику"
        assert any(c["number"] == "5" for c in _park(admin_client)), \
            "менеджмент должен видеть отключённые кары"
    finally:
        admin_client.put(f"/api/cars/{car['id']}", json={"active": True})


def test_mesta_stoyanki_crud(manager_client, admin_client):
    before = {loc["name"] for loc in manager_client.get("/api/cars/locations").json()["locations"]}
    r = manager_client.post("/api/cars/locations", json={"name": "Тестовый навес №42"})
    assert r.status_code == 200, r.text
    loc_id = r.json()["id"]
    try:
        names = {loc["name"] for loc in manager_client.get("/api/cars/locations").json()["locations"]}
        assert "Тестовый навес №42" in names and "Тестовый навес №42" not in before
        r = admin_client.put(f"/api/cars/locations/{loc_id}", json={"active": False})
        assert r.status_code == 200, r.text
    finally:
        admin_client.put(f"/api/cars/locations/{loc_id}", json={"active": False})


# ───────────────────────────── возврат кара (регрессия NameError) ─────────────────────────────
def test_vozvrat_svoego_kara_bez_by_poley(employee_client, manager_client):
    """Сотрудник возвращает СВОЙ кар, не указывая ни employee_id, ни ФИО.

    Именно этот путь падал с NameError (cars.py: `if (by_employee_id or name)`).
    """
    me = employee_client.get("/api/cars").json()["me"] or {}
    held_id = me.get("held")
    if not held_id:                       # если кар уже вернули предыдущие тесты — берём свободный
        car = _free_car(employee_client)
        r = employee_client.post(f"/api/cars/{car['id']}/take", json={"ack_assigned": False})
        assert r.status_code == 200, r.text
        held_id = car["id"]

    r = _return_car(employee_client, held_id, comment="оставил у главного входа")
    assert r.status_code == 200, f"возврат кара упал: {r.text}"
    car = r.json()["car"]
    assert car["status"] in ("free", "charging", "maintenance")
    assert car["holder_name"] == "", "держатель не очищен после возврата"
    assert car["holder_user_id"] is None


def test_vozvrat_s_zamechaniyami_perevodit_na_obsluzhivanie(manager_client, admin_client):
    car = _free_car(manager_client)
    r = manager_client.post(f"/api/cars/{car['id']}/take", json={"ack_assigned": False})
    assert r.status_code == 200, r.text
    try:
        r = _return_car(manager_client, car["id"], condition="bad", comment="спущено колесо")
        assert r.status_code == 200, r.text
        assert r.json()["car"]["status"] == "maintenance", \
            "замечания при возврате обязаны перевести кар в «на обслуживании»"
    finally:
        admin_client.post(f"/api/cars/{car['id']}/status", json={"status": "free", "note": "тест"})


def test_vozvrat_na_zaryadke_s_polnym_zaryadom_otklonen(manager_client, admin_client):
    car = _free_car(manager_client)
    r = manager_client.post(f"/api/cars/{car['id']}/take", json={"ack_assigned": False})
    assert r.status_code == 200, r.text
    try:
        r = _return_car(manager_client, car["id"], on_charge="true", charge="full")
        assert r.status_code == 400, f"ожидался отказ, получено {r.status_code}: {r.text}"
        assert "заряд" in r.json()["detail"]
    finally:
        _return_car(manager_client, car["id"])


def test_vozvrat_na_zaryadke_s_razryazhennym_zaryadom(manager_client, admin_client):
    car = _free_car(manager_client)
    r = manager_client.post(f"/api/cars/{car['id']}/take", json={"ack_assigned": False})
    assert r.status_code == 200, r.text
    try:
        r = _return_car(manager_client, car["id"], on_charge="true", charge="empty")
        assert r.status_code == 200, r.text
        assert r.json()["car"]["status"] == "charging"
    finally:
        admin_client.post(f"/api/cars/{car['id']}/status", json={"status": "free", "note": "тест"})


# ───────────────────────────── правила «один кар» и права ─────────────────────────────
def test_vtoroy_kar_vzyat_nelzya(employee_client):
    """«Один сотрудник — один кар»: пока есть держимый, второй взять нельзя."""
    me = employee_client.get("/api/cars").json()["me"] or {}
    held_id = me.get("held")
    if not held_id:                       # берём сами, чтобы тест не зависел от порядка
        car = _free_car(employee_client)
        r = employee_client.post(f"/api/cars/{car['id']}/take", json={"ack_assigned": False})
        assert r.status_code == 200, r.text
        held_id = car["id"]
    try:
        other = next(c for c in _park(employee_client)
                     if c["id"] != held_id and c["status"] in ("free", "charging"))
        r = employee_client.post(f"/api/cars/{other['id']}/take", json={"ack_assigned": False})
        assert r.status_code == 400, r.text
        detail = r.json()["detail"].lower()
        assert "один сотрудник" in detail or "верните" in detail
    finally:
        _return_car(employee_client, held_id)


def test_vzyat_kar_s_zaryadki_mozhno(manager_client, admin_client):
    car = next((c for c in _park(manager_client) if c["status"] == "charging"), None)
    created = False
    if car is None:                       # создаём условие сами: свободный кар → «на зарядке»
        car = _free_car(manager_client)
        r = admin_client.post(f"/api/cars/{car['id']}/status", json={"status": "charging", "note": "тест"})
        assert r.status_code == 200, r.text
        created = True
    r = manager_client.post(f"/api/cars/{car['id']}/take", json={"ack_assigned": False})
    assert r.status_code == 200, f"кар на зарядке должен быть доступен: {r.text}"
    try:
        assert r.json()["car"]["status"] == "busy"
    finally:
        _return_car(manager_client, car["id"])
        admin_client.post(f"/api/cars/{car['id']}/status",
                          json={"status": "free" if created else "charging", "note": "тест"})


def test_peredacha_drugomu_lichno(manager_client, admin_client):
    car = _free_car(manager_client)
    r = manager_client.post(f"/api/cars/{car['id']}/take", json={"ack_assigned": False})
    assert r.status_code == 200, r.text
    try:
        r = manager_client.post(f"/api/cars/{car['id']}/handover",
                                json={"employee_id": None, "name": "Внешний Тест Тестович",
                                      "with_key": True, "comment": "на время обхода"})
        assert r.status_code == 200, r.text
        after = r.json()["car"]
        assert after["holder_name"] == "Внешний Тест Тестович"
        assert after["status"] == "busy"
    finally:
        admin_client.post(f"/api/cars/{car['id']}/status", json={"status": "free", "note": "тест"})


def test_vydacha_i_zakreplenie_tolko_menedzhmentu(employee_client, manager_client):
    car = _free_car(employee_client)
    assert employee_client.post(f"/api/cars/{car['id']}/give",
                                json={"name": "Кто-то"}).status_code == 403
    assert employee_client.post(f"/api/cars/{car['id']}/assign",
                                json={"employee_id": None}).status_code == 403
    assert employee_client.post(f"/api/cars/{car['id']}/status",
                                json={"status": "free"}).status_code == 403
    r = manager_client.post(f"/api/cars/{car['id']}/assign", json={"employee_id": None})
    assert r.status_code == 200, r.text


def test_istoriya_ne_pusta_i_soderzhit_deystviya(manager_client, admin_client):
    car = _free_car(manager_client)
    r = manager_client.post(f"/api/cars/{car['id']}/take", json={"ack_assigned": False})
    assert r.status_code == 200, r.text
    try:
        _return_car(manager_client, car["id"])
        hist = manager_client.get(f"/api/cars/{car['id']}/history").json()["history"]
        actions = [h["action"] for h in hist]
        assert "take" in actions and "return" in actions, actions[:6]
        assert all({"ts", "action_title", "actor_name"} <= set(h) for h in hist)
    finally:
        admin_client.post(f"/api/cars/{car['id']}/status", json={"status": "free", "note": "тест"})


# ───────────────────────────── фото: маршрут отдачи существует ─────────────────────────────
def test_marshrut_otdachi_foto_sushchestvuet(employee_client):
    """/api/photos/{id}/file обязан существовать: на него ссылается photos.photo_url().

    До появления app/api/photos_api.py маршрут был только /api/night/photos/{id}/file,
    поэтому любая ссылка на фото отдавала 404 «Not Found» (маршрут не найден).
    Здесь различаем «маршрута нет» (detail == 'Not Found') и «фото не найдено».
    """
    r = employee_client.get("/api/photos/999999/file")
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Фото не найдено", \
        f"похоже, маршрута /api/photos/{{id}}/file нет: {r.json()}"
    # алиас в ночном модуле продолжает работать
    r2 = employee_client.get("/api/night/photos/999999/file")
    assert r2.status_code == 404 and r2.json()["detail"] == "Фото не найдено"


def test_foto_bez_vhoda_ne_otdayotsya(client):
    assert client.get("/api/photos/1/file").status_code == 401


# ───────────────────────────── ночной обход электрокаров ─────────────────────────────
def test_nochnoy_obhod_karov_i_zavershenie_shaga(manager_client, db, freeze):
    """Шаг «Проверка электрокаров» внутри ночного отчёта: отметка по кару и завершение шага.

    Отчёт создаём на фиксированную прошлую смену с замороженным временем, чтобы тест
    не зависел от того, в какой час суток запущен прогон (иначе смена закрыта и тест
    пропускался бы почти всегда).
    """
    import datetime as dt

    from sqlalchemy import select

    from app.models import CarNightCheck, NightReport
    from app.night import ensure_report

    shift_d = dt.date(2026, 5, 12)
    created_ids: list[int] = []
    try:
        with freeze("2026-05-12 23:00:00"):      # 02:00 МСК 13.05 — смена 12.05 идёт
            rep = ensure_report(db, shift_d)
            assert rep is not None, "отчёт для идущей смены не создан"
            created_ids.append(rep.id)

            state = manager_client.get(f"/api/night/reports/{rep.id}/cars").json()
            assert state["total"] >= 1, "в обход не попал ни один активный кар"
            assert state["cars_step_done"] is False
            entry = next((e for e in state["list"] if not e["checked"]), state["list"][0])
            car = entry["car"]

            r = manager_client.post(f"/api/night/reports/{rep.id}/cars/{car['id']}/check", json={
                "found": True, "location": car["location"] or "Парковка у главного входа",
                "canopy": True, "charge": "half", "on_charge": False, "condition": "ok",
                "trash": False, "clean": True, "comment": "проверка тестом"})
            assert r.status_code == 200, r.text

            after = manager_client.get(f"/api/night/reports/{rep.id}/cars").json()
            checked = next(e for e in after["list"] if e["car"]["id"] == car["id"])
            assert checked["checked"] is True
            assert checked["check"]["comment"] == "проверка тестом"
            assert after["checked"] == state["checked"] + 1

            r = manager_client.post(f"/api/night/reports/{rep.id}/cars/finish", json={"ack": True})
            assert r.status_code == 200, r.text
            assert r.json()["cars_step_done"] is True
            # карточка кара обновлена отметкой обхода (общая база, а не снимок отчёта)
            fresh = next(c for c in _park(manager_client) if c["id"] == car["id"])
            assert fresh["charge"] == "half"
            assert fresh["last_checked_at"] is not None
    finally:
        for rep_id in created_ids:
            for ch in db.scalars(select(CarNightCheck).where(CarNightCheck.report_id == rep_id)):
                db.delete(ch)
            rep = db.get(NightReport, rep_id)
            if rep is not None:
                db.delete(rep)          # каскад убирает области и пункты
        db.commit()
