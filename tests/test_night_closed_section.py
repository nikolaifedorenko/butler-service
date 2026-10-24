"""Закрытая область ночного отчёта — только для чтения, пока её не переоткроют.

Переоткрыть закрытую область может тот, кто её закрыл, или супервайзер
(take_section, night.reopen_any). Но answer_item и add_item_photo проверяли только
статус отчёта: в закрытую область можно было дописать ответ и фото в обход этой
защиты (рецензия аудита 22.10.2026, P1). То же — удаление фото.

Что проверяется:
  * ответ, фото и удаление фото в закрытой области — 409;
  * после «взять в работу» (переоткрытия) — снова можно.
"""
from __future__ import annotations

PNG = b"\x89PNG\r\n\x1a\n" + b"\x44" * 64


def _area(client, rep) -> dict:
    r = client.get(f"/api/night/reports/{rep.id}")
    assert r.status_code == 200, r.text
    return next(s for s in r.json()["report"]["areas"] if s.get("items"))


def _upload(client, item_id: int):
    return client.post(f"/api/night/items/{item_id}/photo", files={"file": ("shot.png", PNG, "image/png")})


def test_closed_section_is_read_only(employee_client, open_shift):
    with open_shift() as rep:
        sec = _area(employee_client, rep)
        item_id = sec["items"][0]["id"]
        assert employee_client.post(f"/api/night/sections/{sec['id']}/take", json={}).status_code == 200
        r = _upload(employee_client, item_id)
        assert r.status_code == 200, r.text
        photo_id = r.json()["photo"]["id"]
        r = employee_client.post(f"/api/night/sections/{sec['id']}/close", json={"force_unanswered": True})
        assert r.status_code == 200, r.text

        r = employee_client.put(f"/api/night/items/{item_id}/answer", json={"answer": "bad", "comment": "x"})
        assert r.status_code == 409 and "закрыта" in r.json()["detail"], r.text
        r = _upload(employee_client, item_id)
        assert r.status_code == 409 and "закрыта" in r.json()["detail"], r.text
        r = employee_client.delete(f"/api/photos/{photo_id}")
        assert r.status_code in (403, 409) and "закрыта" in r.json()["detail"], r.text
        assert _area(employee_client, rep)["items"][0]["answer"] == ""

        # закрывший сам переоткрывает — правки снова доступны
        assert employee_client.post(f"/api/night/sections/{sec['id']}/take", json={}).status_code == 200
        r = employee_client.put(f"/api/night/items/{item_id}/answer", json={"answer": "ok", "comment": ""})
        assert r.status_code == 200, r.text
        assert employee_client.delete(f"/api/photos/{photo_id}").status_code == 200
