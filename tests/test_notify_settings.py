"""Общий слой доставки (этап 4): «Настройки → Чаты и Почта», каталог чатов, шаблоны.

Доставка — общая функциональность приложения, поэтому экран настроек живёт в
«Настройках» (право settings.edit), а не в справочнике ночного обхода.

Что проверяется:
  * права: параметры доставки видят и меняют только admin/manager (settings.edit);
    каталог чатов доступен и старшему батлеру — он закрепляет чаты за службами;
  * секреты не покидают сервер: в ответах маска, в аудит пишутся имена ключей;
    пустое поле секрета = «не менять», явное "clear" = очистить;
  * Telegram: getMe (проверка токена, в т.ч. ещё не сохранённого), getUpdates →
    общий каталог чатов, тестовое сообщение; ошибки транспорта → 502 без токена;
  * почта: тестовое письмо через подменённый SMTP (From/To/Subject/Message-ID),
    отказ при незаполненных параметрах;
  * шаблоны: свои у каждого раздела, предпросмотр, проверка плейсхолдеров,
    возврат к тексту по умолчанию;
  * закрепление чата за службой делает её готовой к отправке в чат.

Сеть в тестах подменяется: sender/mailer транспорта — заглушки.
"""
from __future__ import annotations

import pytest

TOKEN = "1234567890:AAEtestTESTtestTESTtestTESTtestTEST"


@pytest.fixture()
def fake_telegram(monkeypatch):
    """Подмена HTTP-вызова Bot API: возвращает заготовленные ответы и пишет запросы."""
    calls: list[dict] = []
    queue: dict[str, dict] = {}

    def sender(url, payload, files, timeout):
        method = url.rsplit("/", 1)[-1]
        calls.append({"url": url, "method": method, "payload": payload, "files": files,
                      "timeout": timeout})
        if method in queue:
            return queue[method]
        return {"ok": True, "result": []}

    monkeypatch.setattr("app.notify.transports.telegram.http_sender", sender)
    return {"calls": calls, "queue": queue}


@pytest.fixture()
def fake_smtp(monkeypatch):
    """Подмена SMTP: письма не уходят, но сохраняются для проверок."""
    sent: list[dict] = []

    def mailer(cfg, msg):
        sent.append({"host": cfg.smtp_host, "port": cfg.smtp_port, "security": cfg.smtp_security,
                     "from": msg["From"], "to": msg["To"], "cc": msg["Cc"],
                     "subject": msg["Subject"], "body": msg.get_content(),
                     "message_id": msg["Message-ID"], "attachments": len(list(msg.iter_attachments()))})

    monkeypatch.setattr("app.notify.transports.email.smtp_mailer", mailer)
    return sent


def _config(client) -> dict:
    r = client.get("/api/notify/config")
    assert r.status_code == 200, r.text
    return r.json()


def _put(client, **values) -> dict:
    r = client.put("/api/notify/config", json=values)
    assert r.status_code == 200, r.text
    return r.json()


def _service(client, name: str = "Техническая служба") -> dict:
    r = client.get("/api/night/services")
    assert r.status_code == 200, r.text
    return next(s for s in r.json()["services"] if s["name"] == name)


# ══════════════════════════════ права доступа ══════════════════════════════

def test_parametry_dostavki_tolko_s_pravom_settings_edit(employee_client, manager_client,
                                                         admin_client):
    """Токены и пароли — администратору и менеджеру объекта; супервайзеру нельзя."""
    for c in (employee_client, manager_client):
        assert c.get("/api/notify/config").status_code == 403
        assert c.put("/api/notify/config", json={"notify_smtp_host": "x"}).status_code == 403
        assert c.get("/api/notify/templates").status_code == 403
    assert admin_client.get("/api/notify/config").status_code == 200
    # каталог чатов нужен справочнику служб — он доступен и старшему батлеру
    assert manager_client.get("/api/notify/chats").status_code == 200
    assert employee_client.get("/api/notify/chats").status_code == 403


# ═══════════════════════════ секреты и сохранение ═══════════════════════════

def test_sekrety_maskiruyutsya_i_ne_popadayut_v_audit(admin_client, db):
    _put(admin_client, notify_telegram_token=TOKEN, notify_smtp_password="p@ssw0rd-secret")
    cfg = _config(admin_client)["config"]
    assert cfg["telegram"]["token_set"] is True
    assert cfg["telegram"]["token_masked"].endswith(TOKEN[-4:])
    assert TOKEN not in str(cfg) and "p@ssw0rd-secret" not in str(cfg)
    assert cfg["email"]["password_set"] is True

    # в аудит попадают имена изменённых ключей, а не значения
    from sqlalchemy import select

    from app.models import AuditLog
    rows = list(db.scalars(select(AuditLog).where(AuditLog.action == "notify_config_update")
                           .order_by(AuditLog.id.desc()).limit(3)))
    assert rows, "изменение настроек доставки не попало в аудит"
    blob = " ".join(r.payload_json or "" for r in rows)
    assert TOKEN not in blob and "p@ssw0rd-secret" not in blob
    assert "notify_telegram_token" in blob

    # очистка секретов — явной командой, а не пустым полем
    _put(admin_client, notify_telegram_token="")            # «не менять»
    assert _config(admin_client)["config"]["telegram"]["token_set"] is True
    _put(admin_client, notify_telegram_token="clear", notify_smtp_password="clear")
    cfg = _config(admin_client)["config"]
    assert cfg["telegram"]["token_set"] is False and cfg["email"]["password_set"] is False


def test_parametry_pochty_i_validaciya(admin_client):
    r = admin_client.put("/api/notify/config", json={"notify_smtp_security": "tls-или-что-то"})
    assert r.status_code == 400 and "none" in r.json()["detail"], r.text

    _put(admin_client, notify_smtp_host="smtp.resort.local", notify_smtp_port="2525",
         notify_smtp_security="none", notify_email_from="butler@resort.local",
         notify_email_reply_to="night@resort.local", notify_timeout="30")
    cfg = _config(admin_client)["config"]
    assert cfg["email"]["host"] == "smtp.resort.local" and cfg["email"]["port"] == 2525
    assert cfg["email"]["security"] == "none" and cfg["email"]["from"] == "butler@resort.local"
    assert cfg["timeout"] == 30
    assert cfg["ready"]["email"] is True          # сервер + отправитель заданы
    assert cfg["ready"]["telegram"] is False      # токен очищен предыдущим тестом

    # порт вне диапазона приводится к границе, а не роняет сохранение
    _put(admin_client, notify_smtp_port="999999")
    assert _config(admin_client)["config"]["email"]["port"] == 65535
    _put(admin_client, notify_smtp_port="2525")


# ═══════════════════════════════ Telegram ═══════════════════════════════

def test_proverka_tokena_getme(admin_client, fake_telegram):
    fake_telegram["queue"]["getMe"] = {"ok": True, "result": {"id": 77, "username": "mria_bot",
                                                              "first_name": "Мрия"}}
    # проверяем токен, который ещё не сохранён
    r = admin_client.post("/api/notify/telegram/check", json={"token": TOKEN})
    assert r.status_code == 200, r.text
    assert r.json()["bot"]["username"] == "mria_bot"
    call = fake_telegram["calls"][-1]
    assert call["method"] == "getMe" and TOKEN in call["url"]

    # ошибка Telegram → 502 с понятным текстом и БЕЗ токена
    fake_telegram["queue"]["getMe"] = {"ok": False, "error_code": 401, "description": "Unauthorized"}
    r = admin_client.post("/api/notify/telegram/check", json={"token": TOKEN})
    assert r.status_code == 502, r.text
    assert "401" in r.json()["detail"] and TOKEN not in r.json()["detail"]


def test_katalog_chatov_iz_getupdates(admin_client, manager_client, fake_telegram):
    fake_telegram["queue"]["getUpdates"] = {"ok": True, "result": [
        {"update_id": 1, "message": {"message_id": 1, "chat": {
            "id": -1001234567890, "type": "supergroup", "title": "Техслужба · Мрия",
            "username": "tech_mria"}, "text": "привет"}},
        {"update_id": 2, "channel_post": {"message_id": 5, "chat": {
            "id": -1009998887776, "type": "channel", "title": "Ночные батлеры"}}},
        {"update_id": 3, "message": {"message_id": 2, "chat": {
            "id": 555, "type": "private", "first_name": "Иван", "last_name": "Петров"}, "text": "start"}},
        {"update_id": 4, "message": {"message_id": 3, "chat": {
            "id": -1001234567890, "type": "supergroup", "title": "Техслужба · Мрия"}, "text": "ещё"}},
    ]}
    _put(admin_client, notify_telegram_token=TOKEN)
    r = admin_client.post("/api/notify/telegram/chats")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["added"] == 3 and body["seen"] == 3        # дубль чата не создаёт вторую запись

    chats = manager_client.get("/api/notify/chats").json()["chats"]   # каталог виден и супервайзеру
    by_id = {c["chat_id"]: c for c in chats}
    assert by_id[-1001234567890]["title"] == "Техслужба · Мрия"
    assert by_id[-1001234567890]["username"] == "tech_mria"
    assert by_id[-1001234567890]["kind"] == "supergroup"
    assert by_id[-1009998887776]["kind"] == "channel"
    assert by_id[555]["title"] == "Иван Петров"             # личный чат: имя из first/last_name

    # повторное обновление не плодит записи
    r2 = admin_client.post("/api/notify/telegram/chats")
    assert r2.json()["added"] == 0 and r2.json()["total"] == 3


def test_testovoe_soobshchenie_v_chat(admin_client, fake_telegram):
    _put(admin_client, notify_telegram_token=TOKEN)
    fake_telegram["queue"]["sendMessage"] = {"ok": True, "result": {"message_id": 42}}
    r = admin_client.post("/api/notify/telegram/test", json={"chat_id": -1001234567890})
    assert r.status_code == 200 and r.json()["message_id"] == 42, r.text
    call = fake_telegram["calls"][-1]
    assert call["payload"]["chat_id"] == -1001234567890
    assert "butler-service" in call["payload"]["text"]

    # чат не найден (бота не добавили в группу) — понятная ошибка, не 500
    fake_telegram["queue"]["sendMessage"] = {"ok": False, "error_code": 400,
                                             "description": "Bad Request: chat not found"}
    r = admin_client.post("/api/notify/telegram/test", json={"chat_id": 1})
    assert r.status_code == 502 and "не добавлен" in r.json()["detail"], r.text


def test_bez_tokena_dostavka_ne_vyzyvaet_set(admin_client, fake_telegram):
    _put(admin_client, notify_telegram_token="clear")
    r = admin_client.post("/api/notify/telegram/test", json={"chat_id": 1})
    assert r.status_code == 502 and "токен" in r.json()["detail"].lower(), r.text
    assert not fake_telegram["calls"], "без токена запрос в сеть всё же ушёл"


# ═════════════════════════════════ почта ═════════════════════════════════

def test_testovoe_pismo_cherez_exchange(admin_client, fake_smtp):
    _put(admin_client, notify_smtp_host="smtp.resort.local", notify_smtp_port="25",
         notify_smtp_security="none", notify_email_from="butler@resort.local",
         notify_email_reply_to="night@resort.local")
    r = admin_client.post("/api/notify/email/test", json={"to": "tech@resort.local, sec@resort.local"})
    assert r.status_code == 200, r.text
    assert r.json()["message_id"]
    assert len(fake_smtp) == 1
    sent = fake_smtp[0]
    assert sent["host"] == "smtp.resort.local" and sent["port"] == 25
    assert sent["security"] == "none"                       # релей без авторизации
    assert sent["from"] == "butler@resort.local"
    assert "tech@resort.local" in sent["to"] and "sec@resort.local" in sent["to"]
    assert "Тестовое письмо" in sent["subject"]
    assert "butler@resort.local" in sent["body"]


def test_pismo_bez_parametrov_ne_otpravlyaetsya(admin_client, fake_smtp):
    _put(admin_client, notify_smtp_host="", notify_email_from="")
    r = admin_client.post("/api/notify/email/test", json={"to": "tech@resort.local"})
    assert r.status_code == 502, r.text
    assert not fake_smtp

    _put(admin_client, notify_smtp_host="smtp.resort.local", notify_email_from="butler@resort.local")
    r = admin_client.post("/api/notify/email/test", json={"to": "не-адрес"})
    assert r.status_code == 400 and "адрес" in r.json()["detail"].lower(), r.text
    assert not fake_smtp


# ═══════════════════════════════ шаблоны ═══════════════════════════════

def test_shablony_svoy_u_kazhdogo_razdela(admin_client):
    tpls = admin_client.get("/api/notify/templates").json()["templates"]
    domains = {t["domain"] for t in tpls}
    assert domains == {"night", "cars"}, domains
    night = next(t for t in tpls if t["domain"] == "night")
    assert night["customized"] is False and "{items}" in night["text"]
    assert "{items}" in night["placeholders"] and "{car}" not in night["placeholders"]

    r = admin_client.put("/api/notify/templates/night", json={
        "text": "Служба {service}: найдено за смену {date}:\n{items}\nБатлеры: {duty}"})
    assert r.status_code == 200 and r.json()["customized"] is True, r.text
    saved = next(t for t in admin_client.get("/api/notify/templates").json()["templates"]
                 if t["domain"] == "night")
    assert saved["customized"] is True and "{duty}" in saved["text"]

    # предпросмотр подставляет образцовые значения — видно, что уйдёт получателю
    p = admin_client.post("/api/notify/templates/night/preview", json={"text": saved["text"]})
    assert p.status_code == 200, p.text
    text = p.json()["text"]
    assert "{service}" not in text and "Техническая служба" in text and "{items}" not in text

    # неизвестный плейсхолдер ловим при сохранении, а не после отправки
    r = admin_client.put("/api/notify/templates/night", json={"text": "Срок: {deadline}"})
    assert r.status_code == 400 and "{deadline}" in r.json()["detail"], r.text

    # возврат к тексту по умолчанию
    r = admin_client.put("/api/notify/templates/night", json={"text": night["default"]})
    assert r.status_code == 200 and r.json()["customized"] is False, r.text

    assert admin_client.put("/api/notify/templates/unknown", json={"text": "x"}).status_code == 404


# ══════════════════════ чистые функции слоя доставки ══════════════════════

def test_render_i_katalog_bez_seti():
    """Рендер шаблона, список недостатков и разбор getUpdates — без сети и БД."""
    from app.notify.chats import chats_from_updates
    from app.notify.templates import items_block, render_template
    from app.notify.transports.email import split_addresses

    assert render_template("{service}: {items}", {"service": "Техслужба", "items": ""}) \
        == "Техслужба: —"                       # пустое значение не оставляет дыру
    assert "{oops}" in render_template("{oops}", {})   # неизвестный плейсхолдер виден

    block = items_block([{"area": "Вилла 4001", "text": "Свет выключен", "comment": "мигает"},
                         {"area": "Лобби", "text": "Чистота пола", "comment": ""}])
    assert block.splitlines()[0] == "1. Вилла 4001 · Свет выключен — мигает"
    assert block.splitlines()[1] == "2. Лобби · Чистота пола"

    assert split_addresses("a@x.ru, b@x.ru; c@x.ru d@x.ru") == ["a@x.ru", "b@x.ru", "c@x.ru", "d@x.ru"]
    assert split_addresses("не-адрес") == []

    chats = chats_from_updates([
        {"message": {"chat": {"id": -100, "type": "group", "title": "Группа"}}},
        {"edited_message": {"chat": {"id": -100, "type": "group", "title": "Группа 2"}}},
        {"my_chat_member": {"chat": {"id": -200, "type": "supergroup", "title": "Супер"}}},
        {"message": {"chat": {"id": "не-число"}}},
        "мусор",
    ])
    assert [c["chat_id"] for c in chats] == [-100, -200]
    assert chats[0]["title"] == "Группа 2"        # последнее увиденное название


def test_zakreplenie_chata_delaet_sluzhbu_gotovoy(admin_client):
    """Чаты берутся из общего каталога, закрепляются — в карточке службы."""
    svc = _service(admin_client, "Хозяйственная служба")
    assert svc["use_telegram"] is True and svc["ready_telegram"] is False
    r = admin_client.put(f"/api/night/services/{svc['id']}", json={
        **{k: svc[k] for k in ("name", "sort_order", "active", "use_telegram", "use_email",
                               "email_to", "email_copy", "note")},
        "chat_ids": [-1001234567890]})
    assert r.status_code == 200, r.text
    updated = r.json()["service"]
    assert updated["chat_ids"] == [-1001234567890] and updated["ready_telegram"] is True

    # каталог показывает, за кем закреплён чат
    chats = admin_client.get("/api/notify/chats").json()["chats"]
    row = next((c for c in chats if c["chat_id"] == -1001234567890), None)
    assert row is not None and "Хозяйственная служба" in row["used_by"]

    # возвращаем как было
    admin_client.put(f"/api/night/services/{svc['id']}", json={
        **{k: svc[k] for k in ("name", "sort_order", "active", "use_telegram", "use_email",
                               "email_to", "email_copy", "note")}, "chat_ids": []})
