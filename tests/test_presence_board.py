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


def test_board_card_shift_today_hm_in_object_tz():
    """Дефект 16.10.2026: «По графику сегодня» в карточке Отметок резалось
    из сырых UTC-моментов shift_today — окно выводилось со сдвигом пояса
    (08:00–20:00 MSC показывались как 05:00–17:00). Доска отдаёт готовые
    shift_today_hm в часовом поясе объекта; UTC-моменты shift_today остаются
    источником для расчётов и не меняются."""
    from app.engine.domain.board.assemble_board import assemble_board
    from app.engine.domain.settings.defaults import default_settings
    from app.engine.domain.types.entities import Mark, Shift
    from app.engine.interface.views import board_dict

    utc = dt.timezone.utc
    day = dt.date.today()
    # смена 08:00–20:00 MSC = 05:00–17:00 UTC; отметка IN 09:00 MSC = 06:00 UTC
    s_start = dt.datetime.combine(day, dt.time(5, 0), tzinfo=utc)
    s_end = dt.datetime.combine(day, dt.time(17, 0), tzinfo=utc)
    mark = dt.datetime.combine(day, dt.time(6, 0), tzinfo=utc)
    now = dt.datetime.combine(day, dt.time(7, 0), tzinfo=utc)
    board = assemble_board([Mark("e1", mark, "in")],
                           [Shift("e1", s_start, s_end)], [], now,
                           default_settings())
    payload = board_dict(board, "Europe/Moscow")
    card = payload["open_session_cards"][0]
    assert card["shift_today_hm"] == [["08:00", "20:00"]], \
        "карточка Отметок: окно смены должно быть в поясе объекта, не в UTC"
    assert card["open_since_hm"] == "09:00"
    assert card["shift_today"][0][0].startswith(day.isoformat() + "T05:00"), \
        "shift_today — сырые UTC-моменты, контракт для расчётов не меняем"


def test_board_route_shift_today_hm_end_to_end(app_stack, manager_client):
    """Сквозная проверка маршрута: ручная смена 08:00–20:00 MSC в БД, отметка
    «пришёл» — карточка Отметок обязана показать окно в поясе объекта."""
    from app.core.time import TZ
    from app.models import ScheduleShift

    c = manager_client
    eid = _new_employee(c)
    day = dt.datetime.now(TZ).date()
    db = app_stack["SessionLocal"]()
    try:
        db.add(ScheduleShift(employee_id=eid, date=day,
                             start_utc=dt.datetime.combine(day, dt.time(5)),
                             end_utc=dt.datetime.combine(day, dt.time(17)),
                             source="manual"))
        db.commit()
    finally:
        db.close()
    ts = dt.datetime.now(TZ).replace(tzinfo=None).isoformat(timespec="minutes")
    assert c.post("/api/punches", json={"kind": "in", "employee_id": eid,
                                        "ts": ts}).status_code == 200
    cards = [x for x in c.get("/api/presence/board").json()["open_session_cards"]
             if x["employee_id"] == str(eid)]
    assert cards, "сотрудник с открытой сессией не попал на доску"
    assert cards[0]["shift_today_hm"] == [["08:00", "20:00"]], \
        "маршрут доски: окно смены отдаётся в поясе объекта"
