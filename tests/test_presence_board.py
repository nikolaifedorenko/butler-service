"""Доска «кто на работе» и личный экран обязаны сходиться (дефект 15.10.2026).

Два исправления, закрытые этими тестами:
1. last_marks доски брал «последнюю отметку» как MAX(Punch.id) — по порядку
   СОЗДАНИЯ строк; отметки задним числом и сид (ночная сессия закрывается позже,
   чем создаётся IN следующей) оставляли доску в устаревшем состоянии.
2. Личный экран искал открытую сессию только в окне «план − 4 ч», а доска — по
   всей истории: при длинных сменах (сутки и более — норма, решение владельца
   15.10.2026, ADR-0009) экраны расходились. Теперь оба смотрят всю историю:
   открытая сессия = последняя по (ts, id) отметка является IN.
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


def _on_shift_personal(client, eid: int) -> bool:
    assert client.post("/api/auth/impersonate", json={"employee_id": eid}).status_code == 200
    try:
        return bool(client.get("/api/punches/status").json()["on_shift"])
    finally:
        assert client.post("/api/auth/impersonate/stop").status_code == 200


def test_last_mark_out_by_time_means_absent_everywhere(app_stack, manager_client):
    """Создано: OUT(ts=T-20) первым, IN(ts=T-30, задним числом) вторым.
    Последняя по времени — OUT: ни доска, ни личный экран не считают на работе."""
    c = manager_client
    eid = _new_employee(c)
    now = dt.datetime.now().replace(second=0, microsecond=0)
    assert c.post("/api/punches", json={
        "kind": "out", "employee_id": eid,
        "ts": (now - dt.timedelta(minutes=20)).isoformat(timespec="minutes")}).status_code == 200
    assert c.post("/api/punches", json={
        "kind": "in", "employee_id": eid,
        "ts": (now - dt.timedelta(minutes=30)).isoformat(timespec="minutes")}).status_code == 200

    assert not _on_board(c, eid), \
        "доска: сотрудник ушёл (последняя по времени отметка OUT), но показан на работе"
    assert not _on_shift_personal(c, eid), \
        "личный экран: расходится с доской — показывает открытую сессию при последней отметке OUT"


def test_last_mark_in_by_time_means_present_everywhere(app_stack, manager_client):
    """Обратное направление: IN(ts=T-5) создан ПЕРВЫМ, OUT задним числом
    (ts=T-15, раньше IN) вторым. Последняя по времени — IN: и доска, и личный
    экран показывают сотрудника на работе."""
    c = manager_client
    eid = _new_employee(c)
    now = dt.datetime.now().replace(second=0, microsecond=0)
    assert c.post("/api/punches", json={
        "kind": "in", "employee_id": eid,
        "ts": (now - dt.timedelta(minutes=5)).isoformat(timespec="minutes")}).status_code == 200
    assert c.post("/api/punches", json={
        "kind": "out", "employee_id": eid,
        "ts": (now - dt.timedelta(minutes=15)).isoformat(timespec="minutes")}).status_code == 200

    assert _on_board(c, eid), \
        "доска: последняя по времени отметка IN — сотрудник должен быть на работе"
    assert _on_shift_personal(c, eid), \
        "личный экран: расходится с доской — не видит открытую сессию"


def test_long_session_visible_on_personal_screen(app_stack, manager_client):
    """Решение владельца 15.10.2026: смена длительностью ~2 суток — норма.
    Открытый IN двухдневной давности личный экран обязан видеть (старое окно
    «план − 4 ч» его обрезало) и предлагать «Ушёл», как доска."""
    c = manager_client
    eid = _new_employee(c)
    now = dt.datetime.now().replace(second=0, microsecond=0)
    long_ago = (now - dt.timedelta(hours=49)).isoformat(timespec="minutes")
    assert c.post("/api/punches", json={
        "kind": "in", "employee_id": eid, "ts": long_ago}).status_code == 200

    assert _on_board(c, eid), "доска: длинная открытая сессия видна"
    assert _on_shift_personal(c, eid), \
        "личный экран: смена ~2 суток не видна из-за окна поиска — расхождение с доской"
