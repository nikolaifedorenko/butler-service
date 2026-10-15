"""Доска «кто на работе» и личный экран обязаны сходиться (дефект 15.10.2026).

Батч-запрос доски last_marks брал «последнюю отметку» как MAX(Punch.id) —
по порядку СОЗДАНИЯ строк. Отметки задним числом (менеджер правит забытый уход)
и сид (ночная сессия закрывается позже, чем начинается новая смена) пишут строки
вне порядка ts: доска показывала «на работе с …» сотрудника, который уже ушёл,
пока личный экран (выборка по ts) показывал «не на работе». Тесты гоняют оба
направления расходения через API end-to-end.
"""
from __future__ import annotations

import datetime as dt


def _new_employee(client) -> int:
    r = client.post("/api/employees", json={
        "full_name": "Регрессия Доски Тестовый",
        "hired_at": (dt.date.today() - dt.timedelta(days=40)).isoformat(),
        "role": "employee",
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _on_board(client, eid: int) -> bool:
    cards = client.get("/api/presence/board").json()["open_session_cards"]
    return str(eid) in {c["employee_id"] for c in cards}


def test_board_time_order_wins_over_write_order_out_last(app_stack, manager_client):
    """Создано: OUT(ts=T-20) первым, IN(ts=T-30, задним числом) вторым.
    По времени последняя отметка — OUT: ни доска, ни личный экран не считают
    сотрудника на работе."""
    c = manager_client
    eid = _new_employee(c)
    now = dt.datetime.now().replace(second=0, microsecond=0)
    out_ts = (now - dt.timedelta(minutes=20)).isoformat(timespec="minutes")
    in_ts = (now - dt.timedelta(minutes=30)).isoformat(timespec="minutes")
    assert c.post("/api/punches", json={"kind": "out", "employee_id": eid,
                                        "ts": out_ts}).status_code == 200
    assert c.post("/api/punches", json={"kind": "in", "employee_id": eid,
                                        "ts": in_ts}).status_code == 200

    assert not _on_board(c, eid), \
        "доска: сотрудник ушёл (последняя по времени отметка OUT), но показан на работе"

    assert c.post("/api/auth/impersonate", json={"employee_id": eid}).status_code == 200
    me = c.get("/api/punches/status").json()
    assert not me["on_shift"], "личный экран: открытой сессии быть не должно"
    assert c.post("/api/auth/impersonate/stop").status_code == 200


def test_board_time_order_wins_over_write_order_in_last(app_stack, manager_client):
    """Обратное направление: IN создан ПЕРВЫМ, OUT задним числом (ts РАНЬШЕ IN)
    вторым. По времени последняя отметка — IN: доска обязана показать сотрудника
    на работе (старый MAX(id) говорил «ушёл»).

    Личный экран сверяем только если отметки попали в его окно (±WINDOW_BEFORE_H
    к началу смены): окно личного экрана УЖЕ истории доски — это отдельная
    проектировочная норма (текущая смена), а не дефект расхождения."""
    from app.api.punches import WINDOW_BEFORE_H

    c = manager_client
    eid = _new_employee(c)
    now = dt.datetime.now().replace(second=0, microsecond=0)

    assert c.post("/api/auth/impersonate", json={"employee_id": eid}).status_code == 200
    me0 = c.get("/api/punches/status").json()
    assert c.post("/api/auth/impersonate/stop").status_code == 200
    if me0.get("planned_start"):
        since = dt.datetime.fromisoformat(me0["planned_start"]) \
            - dt.timedelta(hours=WINDOW_BEFORE_H)
    else:
        since = dt.datetime(now.year, now.month, now.day) - dt.timedelta(hours=12)
    in_dt = max(now - dt.timedelta(minutes=5), since + dt.timedelta(minutes=12))
    check_personal = in_dt <= now and in_dt > since + dt.timedelta(minutes=12)
    out_dt = in_dt - dt.timedelta(minutes=10)

    assert c.post("/api/punches", json={"kind": "in", "employee_id": eid,
                                        "ts": in_dt.isoformat(timespec="minutes")}).status_code == 200
    assert c.post("/api/punches", json={"kind": "out", "employee_id": eid,
                                        "ts": out_dt.isoformat(timespec="minutes")}).status_code == 200

    assert _on_board(c, eid), \
        "доска: последняя по времени отметка IN — сотрудник должен быть на работе"

    if check_personal:
        assert c.post("/api/auth/impersonate", json={"employee_id": eid}).status_code == 200
        me = c.get("/api/punches/status").json()
        assert me["on_shift"], "личный экран: сессия открыта (on_shift) — согласен с доской"
        assert c.post("/api/auth/impersonate/stop").status_code == 200
