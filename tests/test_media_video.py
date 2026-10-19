"""Медиа ночного отчёта v2 — этап 2: видео, настраиваемые лимиты, отдача с Range.

Что проверяется:
  * тип файла определяется по содержимому (магическим байтам): mp4/mov/webm — видео,
    png/jpg — фото, HEIC и PDF не принимаются вовсе;
  * видео сохраняется тем же механизмом, что фото (оригинал на диске), и отдаётся
    с поддержкой Range — иначе плеер в браузере не перематывает файл;
  * лимиты размера задаёт объект: photo_max_mb и video_max_mb раздельно
    (превышение → 413 с внятным текстом);
  * срок хранения свой у фото и у видео (photo_retention_days / video_retention_days);
  * `/api/photos/limits` доступен любому авторизованному пользователю — по нему
    интерфейс рисует подсказки у кнопок загрузки.
"""
from __future__ import annotations

import datetime as dt
from contextlib import contextmanager

import pytest

# минимальные «настоящие» заголовки контейнеров — sniff_media смотрит только на них
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x11" * 64
MOV = b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  " + b"\x22" * 64
WEBM = b"\x1aE\xdf\xa3" + b"\x33" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x44" * 64
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1" + b"\x55" * 64
PDF = b"%PDF-1.4\n" + b"\x00" * 64


@contextmanager
def _smena(db, freeze):
    """Открытый отчёт смены + уборка того, что создал тест.

    Отчёт берём за СЕГОДНЯШНЮЮ дату и создаём под заморозкой времени (23:00 —
    середина смены), а HTTP-запросы выполняем уже без freeze: FastAPI достраивает
    pydantic-схемы маршрутов лениво, и внутри freeze_time аннотация ``dt.date``
    подменена на ``FakeDate`` — схема не строится. Автозакрытие сегодняшней смены
    (08:00 следующих суток) ещё не наступило, поэтому ``sync_reports`` отчёт не
    закроет и загрузка остаётся разрешённой.

    Если отчёт за сегодня уже есть (создан другим тестом), мы его не удаляем —
    только возвращаем прежний статус и убираем свои файлы.
    """
    from sqlalchemy import select

    from app.models import NightAreaSection, NightCheckItem, NightReport, Photo
    from app.night import ensure_report
    from app.photos import unlink_photo

    shift_d = dt.date.today()
    existed = db.scalar(select(NightReport).where(NightReport.date == shift_d))
    prev_state = (existed.status, existed.closed_at) if existed else None
    with freeze(f"{shift_d.isoformat()} 23:00:00"):
        rep = ensure_report(db, shift_d)
    assert rep is not None, "отчёт смены не создан"
    created = existed is None
    rep.status, rep.closed_at = "open", None       # тесту нужен открытый отчёт
    db.commit()
    start = dt.datetime.now() - dt.timedelta(seconds=1)
    try:
        yield rep
    finally:
        sec_ids = [s.id for s in db.scalars(
            select(NightAreaSection).where(NightAreaSection.report_id == rep.id))]
        item_ids = ([i.id for i in db.scalars(select(NightCheckItem).where(
            NightCheckItem.section_id.in_(sec_ids)))] if sec_ids else [])
        for p in db.scalars(select(Photo).where(Photo.kind == "night_item",
                                                Photo.ref_id.in_(item_ids))):
            if created or (p.created_at and p.created_at >= start):
                unlink_photo(p)
                db.delete(p)
        db.flush()
        if created:
            for i in db.scalars(select(NightCheckItem).where(NightCheckItem.section_id.in_(sec_ids))):
                db.delete(i)
            db.flush()
            for s in db.scalars(select(NightAreaSection).where(NightAreaSection.report_id == rep.id)):
                db.delete(s)
            db.flush()
            fresh = db.get(NightReport, rep.id)
            if fresh is not None:
                db.delete(fresh)
        else:
            rep.status, rep.closed_at = prev_state
        db.flush()
        db.commit()


def _report(client, rep) -> dict:
    r = client.get(f"/api/night/reports/{rep.id}")
    assert r.status_code == 200, r.text
    return r.json()["report"]


def _items_of(client, rep, item_id: int | None = None) -> list[dict]:
    out = [i for s in _report(client, rep)["areas"] for i in (s.get("items") or [])]
    return out if item_id is None else [i for i in out if i["id"] == item_id]


def _first_item(client, rep) -> int:
    items = _items_of(client, rep)
    assert items, "в отчёте нет пунктов чек-листа"
    return items[0]["id"]


def _upload(client, item_id: int, blob: bytes, name: str, mime: str):
    return client.post(f"/api/night/items/{item_id}/photo",
                       files={"file": (name, blob, mime)})


def _set_rules(admin_client, **rules) -> None:
    r = admin_client.put("/api/settings",
                         json=[{"key": k, "value": str(v)} for k, v in rules.items()])
    assert r.status_code == 200, r.text


# ═══════════════════════ определение типа по содержимому ═══════════════════════

@pytest.mark.parametrize("blob,name,expected", [
    (MP4, "obhod.mp4", ("video", "mp4")),
    (MOV, "obhod.mov", ("video", "mov")),
    (WEBM, "obhod.webm", ("video", "webm")),
    (WEBM, "obhod.mkv", ("video", "mkv")),      # EBML: webm и mkv различаются по имени
    (PNG, "shot.png", ("photo", "png")),
    (b"\xff\xd8\xff\xe0" + b"\x00" * 64, "shot.jpg", ("photo", "jpg")),
])
def test_sniff_media_opredelyaet_tip_po_baytam(blob, name, expected):
    from app.photos import sniff_media

    assert sniff_media(blob, name) == expected


@pytest.mark.parametrize("blob,name", [
    (HEIC, "photo.heic"),                       # HEIC: тоже ftyp, но браузеры его не показывают
    (PDF, "doc.pdf"),
    (b"PK\x03\x04" + b"\x00" * 64, "archive.zip"),
    (b"\x00" * 64, "video.mp4"),                # имя не спасает: содержимое не медиа
])
def test_ne_media_ne_prinimaem(blob, name):
    from app.photos import sniff_media

    assert sniff_media(blob, name) == ("", "")


# ═══════════════════════════════ загрузка видео ═══════════════════════════════

def test_video_zagruzhaetsya_i_otdayotsya_s_range(employee_client, db, freeze):
    with _smena(db, freeze) as rep:
        item_id = _first_item(employee_client, rep)
        r = _upload(employee_client, item_id, MP4, "obhod.mp4", "video/mp4")
        assert r.status_code == 200, r.text
        photo = r.json()["photo"]
        assert photo["media_type"] == "video"

        full = employee_client.get(photo["url"])
        assert full.status_code == 200
        assert full.headers["content-type"] == "video/mp4"
        assert full.content == MP4

        # Range — без него плеер не перематывает видео и не знает длительность
        part = employee_client.get(photo["url"], headers={"Range": "bytes=0-9"})
        assert part.status_code == 206, part.text
        assert part.content == MP4[:10]
        assert part.headers.get("content-range", "").startswith(f"bytes 0-9/{len(MP4)}")

        # в payload отчёта видео видно как медиа — интерфейс рисует ▶ вместо картинки
        assert _items_of(employee_client, rep, item_id)[0]["photos"][0]["media_type"] == "video"


def test_photo_i_video_lezhat_ryadom_u_punkta(employee_client, db, freeze):
    with _smena(db, freeze) as rep:
        item_id = _first_item(employee_client, rep)
        assert _upload(employee_client, item_id, PNG, "shot.png", "image/png").status_code == 200
        assert _upload(employee_client, item_id, MP4, "obhod.mp4", "video/mp4").status_code == 200
        kinds = sorted(p["media_type"] for p in _items_of(employee_client, rep, item_id)[0]["photos"])
        assert kinds == ["photo", "video"], kinds


def test_ne_media_otklonyaetsa_400(employee_client, db, freeze):
    with _smena(db, freeze) as rep:
        item_id = _first_item(employee_client, rep)
        r = _upload(employee_client, item_id, PDF, "doc.pdf", "application/pdf")
        assert r.status_code == 400, r.text
        assert "видео" in r.json()["detail"]


# ═════════════════════ настраиваемые лимиты размера ═════════════════════

def test_limity_razmera_zadayutsya_obektom(admin_client, employee_client, db, freeze):
    with _smena(db, freeze) as rep:
        item_id = _first_item(employee_client, rep)

        lim = employee_client.get("/api/photos/limits")          # доступно и батлеру, не только менеджеру
        assert lim.status_code == 200, lim.text
        assert lim.json() == {"photo_max_mb": 12, "video_max_mb": 50,
                              "photo_retention_days": 180, "video_retention_days": 180}

        # уменьшаем лимит видео до 1 МБ и шлём 2 МБ — 413 с внятным текстом
        big = MP4[:20] + b"\x00" * (2 * 1024 * 1024)
        _set_rules(admin_client, video_max_mb=1)
        assert employee_client.get("/api/photos/limits").json()["video_max_mb"] == 1
        r = _upload(employee_client, item_id, big, "big.mp4", "video/mp4")
        assert r.status_code == 413, r.text
        assert "1 МБ" in r.json()["detail"]

        # фото того же размера своим лимитом не ограничено (photo_max_mb = 12)
        assert _upload(employee_client, item_id, PNG + b"\x00" * (2 * 1024 * 1024),
                       "big.png", "image/png").status_code == 200

        _set_rules(admin_client, video_max_mb=50)


def test_limit_deystvuet_na_svoy_tip(admin_client, employee_client, db, freeze):
    """video_max_mb не мешает фото и наоборот; 0 = не ограничивать."""
    with _smena(db, freeze) as rep:
        item_id = _first_item(employee_client, rep)
        _set_rules(admin_client, photo_max_mb=0, video_max_mb=1)
        huge_png = PNG + b"\x00" * (3 * 1024 * 1024)
        assert _upload(employee_client, item_id, huge_png, "huge.png", "image/png").status_code == 200
        assert _upload(employee_client, item_id, MP4[:20] + b"\x00" * (2 * 1024 * 1024),
                       "big.mp4", "video/mp4").status_code == 413
        _set_rules(admin_client, photo_max_mb=12, video_max_mb=50)


# ═══════════════════════ срок хранения: свой у видео ═══════════════════════

def test_srok_hraneniya_svoy_u_foto_i_video(admin_client, employee_client, db, freeze):
    from app.models import Photo
    from app.photos import cleanup_photos, media_limits, photos_of, retention_days, save_photo

    _set_rules(admin_client, photo_retention_days=90, video_retention_days=0)
    db.expire_all()
    assert retention_days(db) == 90 and retention_days(db, "video") == 0
    assert media_limits(db)["video_max_mb"] == 50

    photo = save_photo(db, kind="night_item", ref_id=1, filename="a.png", blob=PNG,
                       user_id=None, user_name="тест")
    video = save_photo(db, kind="night_item", ref_id=1, filename="a.mp4", blob=MP4,
                       user_id=None, user_name="тест")
    assert photo.media_type == "photo" and video.media_type == "video"
    old = dt.datetime.now() - dt.timedelta(days=100)     # «состариваем» оба файла
    photo.created_at = old
    video.created_at = old
    db.commit()
    try:
        removed = cleanup_photos(db)
        db.refresh(photo)
        db.refresh(video)
        assert removed == 1
        assert photo.path == ""                          # фото удалено по сроку
        assert video.path != ""                          # видео храним всегда (0 дней)
        assert db.get(Photo, video.id) is not None       # запись в БД остаётся

        # удалённый по сроку файл отдаётся как missing (не 404) — комментарии целы
        by_id = {r["id"]: r for r in photos_of(db, "night_item", [1])[1]}
        assert by_id[photo.id]["missing"] is True and by_id[photo.id]["url"] == ""
        assert by_id[video.id]["missing"] is False
    finally:
        # сначала убираем файлы и записи своей сессией, потом возвращаем правила
        # через API: иначе два незакоммиченных соединения блокируют SQLite
        from app.photos import unlink_photo
        for p in (photo, video):
            fresh = db.get(Photo, p.id)
            if fresh is not None:
                unlink_photo(fresh)
                db.delete(fresh)
        db.commit()
        _set_rules(admin_client, photo_retention_days=180, video_retention_days=180)
        assert employee_client.get("/api/photos/limits").json() == {
            "photo_max_mb": 12, "video_max_mb": 50,
            "photo_retention_days": 180, "video_retention_days": 180}


def test_video_nelzya_prislat_kak_foto(db):
    """media_type, заявленный вызывающим кодом, обязан совпасть с содержимым."""
    from app.photos import save_photo

    with pytest.raises(ValueError):
        save_photo(db, kind="night_item", ref_id=1, filename="a.mp4", blob=MP4,
                   user_id=None, user_name="тест", media_type="photo")
    db.rollback()
