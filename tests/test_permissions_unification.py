"""Этап B — унификация прав (20.10.2026, docs/EXECUTION-SPEC-v2.md §5.2).

Ролевые зависимости require_manager/require_supervisor/require_admin удалены из
app/auth.py: единственный вход проверки прав — require_perm("<ключ>") из каталога
PERMISSIONS. Новые ключи: `night.close` (закрытие/переоткрытие смены и объектов)
и `employees.impersonate` («посмотреть глазами сотрудника») — базовая аудитория
та же, что у прежних ролевых проверок (supervisor+), поэтому поведение ролей по
умолчанию не изменилось, но право теперь выдаётся/снимается грантами.

Задокументированные УЖЕСТОЧЕНИЯ (сервер раньше был разрешал, чем интерфейс —
кнопки правок у супервайзера и так были скрыты):
* супервайзер теряет серверный ДОСТУП НА ЗАПИСЬ к настройкам и справочникам
  (settings/doc/doublepay/departments/subdivisions/shift-types) — теперь там
  `settings.edit`, которого у роли нет;
* супервайзер больше не видит неактивные (отключённые) кары — видимость парка
  для управления привязана к `cars.manage`.
Оба ужесточения снимаются грантом в «Настройках → Права доступа».

Inline-ветвления `principal.is_manager` (fact_api, punches, schedule, photos)
этапом B НЕ трогались — они переводятся на ключи в модульных фазах (этап C).
"""
from __future__ import annotations

import datetime as dt

# ───────────────────────── каталог и роли ─────────────────────────

def test_novye_klyuchi_v_kataloge(admin_client):
    cat = admin_client.get("/api/access").json()
    keys = {p["key"]: p for p in cat["permissions"]}
    assert "night.close" in keys and keys["night.close"]["section"] == "Ночной отчёт"
    assert "employees.impersonate" in keys and keys["employees.impersonate"]["section"] == "Сотрудники"
    gromova = next(u for u in cat["users"] if u["username"] == "gromova")    # supervisor
    ivanov = next(u for u in cat["users"] if u["username"] == "ivanov")      # employee
    assert {"night.close", "employees.impersonate"} <= set(gromova["effective"])
    assert not ({"night.close", "employees.impersonate"} & set(ivanov["effective"]))


def test_rolevyh_zavisimostey_bolshe_net():
    """require_manager/require_supervisor/require_admin удалены — только require_perm.

    Фаза C1 (20.10.2026): модуль переехал в app/core/auth.py — проверяем и новый
    путь, и отсутствие старого."""
    import importlib.util

    import app.core.auth as auth
    for name in ("require_manager", "require_supervisor", "require_admin"):
        assert not hasattr(auth, name), f"app/core/auth.{name} должен быть удалён"
    assert importlib.util.find_spec("app.auth") is None, "app/auth.py не должно существовать"


# ───────────────────────── ночная смена: night.close ─────────────────────────

def test_zakrytie_i_pereotkrytie_smeny(manager_client, employee_client, open_shift):
    with open_shift() as rep:
        rid = rep.id
        assert employee_client.post(f"/api/night/reports/{rid}/close").status_code == 403
        assert employee_client.post(f"/api/night/reports/{rid}/reopen").status_code == 403
        # супервайзер: переоткрытие открытого отчёта идемпотентно и разрешено
        assert manager_client.post(f"/api/night/reports/{rid}/reopen").status_code == 200
        # переоткрытие объекта — тот же ключ
        secs = manager_client.get(f"/api/night/reports/{rid}").json()["report"]["areas"]
        assert secs, "в отчёте нет объектов"
        r = manager_client.post(f"/api/night/sections/{secs[0]['id']}/reopen")
        assert r.status_code in (200, 409), r.text   # 409 — объект не был закрыт


# ───────────────────────── имперсонация: employees.impersonate ─────────────────────────

def test_voiti_kak_sotrudnik(manager_client, employee_client):
    demo = manager_client.get("/api/auth/employees-for-demo")
    assert demo.status_code == 200, demo.text
    ivanov = next(e for e in demo.json() if "Иванов" in e["full_name"])
    assert employee_client.get("/api/auth/employees-for-demo").status_code == 403
    assert employee_client.post("/api/auth/impersonate",
                                json={"employee_id": ivanov["id"]}).status_code == 403

    r = manager_client.post("/api/auth/impersonate", json={"employee_id": ivanov["id"]})
    assert r.status_code == 200, r.text
    me = manager_client.get("/api/auth/me").json()
    assert me["user"]["impersonated"] is True
    # второй страж (can_manage_user) не сломан: выход возвращает менеджера
    r = manager_client.post("/api/auth/impersonate/stop")
    assert r.status_code == 200, r.text
    assert manager_client.get("/api/auth/me").json()["user"]["impersonated"] is False


# ───────────────────────── настройки: чтение vs запись ─────────────────────────

def test_supervisor_chitaet_no_ne_pishet(manager_client, admin_client):
    """Сервер приведён в соответствие с интерфейсом: без settings.edit — только чтение."""
    # чтение доступно (settings.view / employees.view у супервайзера есть)
    assert manager_client.get("/api/settings").status_code == 200
    assert manager_client.get("/api/docs/kinds").status_code == 200
    assert manager_client.get("/api/departments").status_code == 200
    assert manager_client.get("/api/subdivisions").status_code == 200
    assert manager_client.get("/api/doublepay").status_code == 200
    # запись — только settings.edit
    r = manager_client.put("/api/settings/doc", json={"company": "X", "director": "Y"})
    assert r.status_code == 403, r.text
    assert manager_client.delete("/api/docs/kinds/999999").status_code == 403
    assert manager_client.delete("/api/departments/999999").status_code == 403
    assert manager_client.delete("/api/subdivisions/999999").status_code == 403
    assert manager_client.delete("/api/doublepay/days/999999").status_code == 403
    assert manager_client.delete("/api/shift-types/999999").status_code == 403
    # у админа право есть — запрос проходит гейт и упирается в 404 (объекта нет)
    assert admin_client.delete("/api/docs/kinds/999999").status_code == 404


def test_grant_vozvrashchaet_supervisoru_zapis(admin_client, manager_client):
    """Ужесточение снимается грантом: выдали settings.edit — запись снова работает."""
    cat = admin_client.get("/api/access").json()
    gromova = next(u for u in cat["users"] if u["username"] == "gromova")
    uid = gromova["id"]
    try:
        assert admin_client.put(f"/api/access/users/{uid}/grants",
                                json={"grants": {"settings.edit": "allow"}}).status_code == 200
        r = manager_client.delete("/api/docs/kinds/999999")
        assert r.status_code == 404, r.text      # гейт пройден, объекта нет
    finally:
        admin_client.put(f"/api/access/users/{uid}/grants", json={"grants": {}})
    assert manager_client.delete("/api/docs/kinds/999999").status_code == 403


# ───────────────────────── каталог чатов: night.edit достаточно ─────────────────────────

def test_katalog_chatov_dostupen_derzhatelyu_night_edit(manager_client, employee_client):
    """Карточка службы (Ночной обход) закрепляет чаты — каталог виден с night.edit."""
    assert manager_client.get("/api/notify/chats").status_code == 200
    assert employee_client.get("/api/notify/chats").status_code == 403


# ───────────────────────── экспорт Графика: schedule.edit ─────────────────────────

def test_excel_grafika(manager_client, employee_client):
    today = dt.date.today()
    url = f"/api/schedule/xlsx?year={today.year}&month={today.month}"
    r = manager_client.get(url)
    assert r.status_code == 200 and len(r.content) > 2000, r.status_code
    assert employee_client.get(url).status_code == 403


# ───────────────────────── парк: неактивные кары — только cars.manage ─────────────────────────

def test_neaktivnye_kary_vidny_tolko_upravleniyu_parkom(admin_client, manager_client,
                                                        manager_role_client):
    cars = admin_client.get("/api/cars").json()["cars"]
    car = next(c for c in cars if c["active"])
    cid = car["id"]
    try:
        r = admin_client.put(f"/api/cars/{cid}", json={"active": False})
        assert r.status_code == 200, r.text
        sup_ids = {c["id"] for c in manager_client.get("/api/cars").json()["cars"]}
        mgr_ids = {c["id"] for c in manager_role_client.get("/api/cars").json()["cars"]}
        adm_ids = {c["id"] for c in admin_client.get("/api/cars").json()["cars"]}
        assert cid not in sup_ids, "супервайзер без cars.manage не должен видеть неактивный кар"
        assert cid in mgr_ids and cid in adm_ids
    finally:
        assert admin_client.put(f"/api/cars/{cid}", json={"active": True}).status_code == 200
