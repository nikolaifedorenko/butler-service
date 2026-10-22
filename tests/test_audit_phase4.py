"""Фаза 4 аудита (22.10.2026): мёртвый код и наследие.

* DEAD-01 — удаление объекта обхода убирает пункты открытых смен каскадом; их фото раньше
  оставались записями-сиротами с файлами на диске (delete_photo_files не вызывался).
"""
from __future__ import annotations

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f"
       b"\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


def test_delete_area_removes_item_photos(manager_client, db, open_shift):
    from app.core.media import BASE_DIR, Photo, save_photo
    from app.modules.night.application.catalog import NightArea, NightAreaSection, NightCheckItem

    with open_shift() as rep:
        area = NightArea(name="Тест DEAD-01: объект на удаление", sort_order=999)
        db.add(area)
        db.flush()
        sec = NightAreaSection(report_id=rep.id, area_id=area.id, name=area.name)
        sec.items.append(NightCheckItem(text="Свет выключен"))
        db.add(sec)
        db.flush()
        photo = save_photo(db, kind="night_item", ref_id=sec.items[0].id, filename="p.png",
                           blob=PNG, user_id=None, user_name="")
        db.commit()
        path, photo_id = BASE_DIR / photo.path, photo.id
        assert path.exists()
        try:
            r = manager_client.delete(f"/api/night/areas/{area.id}")
            assert r.status_code == 200 and r.json()["sections_removed"] == 1, r.text
            db.expire_all()
            assert db.get(Photo, photo_id) is None
            assert not path.exists()
        finally:
            path.unlink(missing_ok=True)
            db.rollback()
            db.delete(db.get(NightArea, area.id))
            db.commit()


def test_api_docs_flag(client, monkeypatch):
    """OPS-04: при API_DOCS=0 (прод) Swagger и схема API не отдаются; ReDoc выключен всегда,
    /redoc уходит в оболочку SPA."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app import main

    assert client.get("/api/openapi.json").status_code == 200          # тесты — API_DOCS=1
    assert "redoc" not in client.get("/redoc").text.lower()
    monkeypatch.setattr(main.settings, "api_docs", False)
    off = TestClient(FastAPI(**main._docs_urls()))
    assert off.get("/api/docs").status_code == 404
    assert off.get("/api/openapi.json").status_code == 404
