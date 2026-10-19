"""Ночной отчёт v2 — этап 5: экран «Недостатки смены», ручная отправка, общий журнал.

Правила (решения владельца от 19.10.2026), которые здесь закреплены тестами:
  * в отчёт попадают «Не ОК» И «Не проверено» (отдельный блок);
  * отправка только вручную: всё скопом или выборочно;
  * отправить может любой пользователь обхода (нового права нет);
  * отправленное помечается и повторно не уходит;
  * если недостаток исправили ПОСЛЕ отправки — ничего не отправляем (ни «исправлено»,
    ни отзыва);
  * каждая служба получает своё сообщение всем своим получателям (не объединяем);
  * журнал общий (notify_dispatches): раздел, получатель, канал, состав снимком,
    статус, ошибка, число попыток; неудачную доставку можно повторить.

Сеть подменяется: sender Telegram и SMTP-mailer — заглушки.
"""
from __future__ import annotations

import pytest

TOKEN = "999:TEST-token-for-dispatch-tests"
CHAT_TECH = -100111222333
CHAT_SEC = -100444555666

SERVICE_FIELDS = ("name", "sort_order", "active", "use_telegram", "use_email",
                  "email_to", "email_copy", "note")


@pytest.fixture()
def fake_telegram(monkeypatch):
    calls: list[dict] = []
    state = {"fail": False}

    def sender(url, payload, files, timeout):
        method = url.rsplit("/", 1)[-1]
        calls.append({"method": method, "payload": payload, "files": files})
        if state["fail"]:
            return {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}
        if method == "getUpdates":
            return {"ok": True, "result": []}
        return {"ok": True, "result": {"message_id": 1000 + len(calls)}}

    monkeypatch.setattr("app.notify.transports.telegram.http_sender", sender)
    return {"calls": calls, "state": state}


@pytest.fixture()
def fake_smtp(monkeypatch):
    sent: list[dict] = []
    state = {"fail": False}

    def mailer(cfg, msg):
        if state["fail"]:
            from app.notify.transports import TransportError
            raise TransportError("Почтовый сервер недоступен: SMTPException")
        sent.append({"to": msg["To"], "cc": msg["Cc"], "subject": msg["Subject"],
                     "body": msg.get_content(), "message_id": msg["Message-ID"],
                     "attachments": len(list(msg.iter_attachments()))})

    monkeypatch.setattr("app.notify.transports.email.smtp_mailer", mailer)
    return {"sent": sent, "state": state}


@pytest.fixture()
def channels(admin_client):
    """Транспорт настроен, у служб заполнены каналы; после теста — как было."""
    def _svc(name):
        rows = admin_client.get("/api/night/services").json()["services"]
        return next(s for s in rows if s["name"] == name)

    def _put(svc, **patch):
        body = {k: svc[k] for k in SERVICE_FIELDS}
        body["chat_ids"] = svc["chat_ids"]
        body.update(patch)
        r = admin_client.put(f"/api/night/services/{svc['id']}", json=body)
        assert r.status_code == 200, r.text
        return r.json()["service"]

    before = {n: _svc(n) for n in ("Техническая служба", "Хозяйственная служба", "Служба безопасности")}
    admin_client.put("/api/notify/config", json={
        "notify_telegram_token": TOKEN, "notify_smtp_host": "smtp.resort.local",
        "notify_smtp_port": "25", "notify_smtp_security": "none",
        "notify_email_from": "butler@resort.local"})
    _put(before["Техническая служба"], use_telegram=True, use_email=False,
         chat_ids=[CHAT_TECH], email_to="")
    _put(before["Хозяйственная служба"], use_telegram=False, use_email=True,
         chat_ids=[], email_to="hoz@resort.example", email_copy="night@resort.example")
    _put(before["Служба безопасности"], use_telegram=True, use_email=False,
         chat_ids=[CHAT_SEC], email_to="")
    yield {"tech": CHAT_TECH, "hoz": "hoz@resort.example", "sec": CHAT_SEC}
    for svc in before.values():
        _put(svc)
    admin_client.put("/api/notify/config", json={
        "notify_telegram_token": "clear", "notify_smtp_host": "", "notify_email_from": ""})


def _defects(client, rep) -> dict:
    r = client.get(f"/api/night/reports/{rep.id}/defects")
    assert r.status_code == 200, r.text
    return r.json()


def _items_of_service(client, rep, service_name: str, kind: str | None = None) -> list[dict]:
    d = _defects(client, rep)
    g = next((g for g in d["groups"] if g["service_name"] == service_name), None)
    rows = g["defects"] if g else []
    return [r for r in rows if kind is None or r["kind"] == kind]


def _answer(client, item_id: int, answer: str, comment: str = "") -> None:
    r = client.put(f"/api/night/items/{item_id}/answer",
                   json={"answer": answer, "comment": comment})
    assert r.status_code == 200, r.text


TECH_IDX = 1        # «Свет выключен» → Техническая служба
HOZ_IDX = 2         # «Вилла убрана» → Хозяйственная служба


def _report_item_ids(client, rep, area_name: str) -> list[dict]:
    r = client.get(f"/api/night/reports/{rep.id}")
    assert r.status_code == 200, r.text
    sec = next(s for s in r.json()["report"]["areas"] if s["name"] == area_name)
    return sec["items"]


# ═══════════════════════ состав отчёта о недостатках ═══════════════════════

def test_v_otchet_popadayut_ne_ok_i_ne_provereno(employee_client, open_shift):
    with open_shift() as rep:
        items = _report_item_ids(employee_client, rep, "Вилла 4003")
        _answer(employee_client, items[TECH_IDX]["id"], "bad", "Лампа мигает у входа")
        _answer(employee_client, items[0]["id"], "ok")

        d = _defects(employee_client, rep)
        kinds = {row["kind"] for row in d["items"]}
        assert kinds == {"bad", "unchecked"}, kinds
        bad = [row for row in d["items"] if row["kind"] == "bad"]
        assert len(bad) == 1 and bad[0]["comment"] == "Лампа мигает у входа"
        assert bad[0]["area"] == "Вилла 4003" and bad[0]["zone"] == "Семейные виллы"
        assert bad[0]["service_name"] == "Техническая служба"      # снимок службы из шаблона зоны
        assert d["counts"]["bad"] == 1 and d["counts"]["unchecked"] >= 1
        assert d["counts"]["total"] == d["counts"]["bad"] + d["counts"]["unchecked"] \
            + d["counts"]["fixed_after_dispatch"]
        # ночные батлеры смены — для плейсхолдера {duty}
        assert d["duty"] and d["duty"] != "—"
        assert d["template"]["text"] and "{items}" in d["template"]["text"]


def test_gruppy_po_sluzhbam_i_prichiny_otkaza(employee_client, open_shift):
    with open_shift() as rep:
        items = _report_item_ids(employee_client, rep, "Вилла 4003")
        _answer(employee_client, items[TECH_IDX]["id"], "bad", "не горит")
        d = _defects(employee_client, rep)
        names = [g["service_name"] for g in d["groups"]]
        assert "Техническая служба" in names
        tech = next(g for g in d["groups"] if g["service_name"] == "Техническая служба")
        assert tech["counts"]["sendable"] >= 1
        # чаты не закреплены → отправить нельзя, причина видна до отправки
        assert tech["ready"] is False
        assert any("чат" in p for p in tech["problems"]), tech["problems"]


# ═══════════════════════════════ отправка ═══════════════════════════════

def test_otpravka_vsey_smuny_vsem_sluzhbam(employee_client, admin_client, open_shift,
                                            channels, fake_telegram, fake_smtp):
    with open_shift() as rep:
        v4003 = _report_item_ids(employee_client, rep, "Вилла 4003")
        _answer(employee_client, v4003[TECH_IDX]["id"], "bad", "Свет не выключен в холле")
        _answer(employee_client, v4003[HOZ_IDX]["id"], "bad", "Уборка не завершена")

        tech_row = _defects(employee_client, rep)
        ids = [row["id"] for g in tech_row["groups"] for row in g["defects"]
               if row["kind"] == "bad" and row["sendable"]]
        r = employee_client.post(f"/api/night/reports/{rep.id}/dispatch",
                                 json={"mode": "selected", "item_ids": ids})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["sent"] == 2 and body["failed"] == 0, body      # чат технике + письмо хозяйственной
        assert body["marked"] == 2

        # чат — службе с каналом «чат», письмо — службе с каналом «письмо»
        tg = [c for c in fake_telegram["calls"] if c["method"] == "sendMessage"]
        assert any(c["payload"]["chat_id"] == channels["tech"] for c in tg)
        assert any("Свет не выключен в холле" in c["payload"]["text"] for c in tg)
        assert any("Ночные батлеры смены" in c["payload"]["text"] for c in tg)
        mail = fake_smtp["sent"]
        assert mail and channels["hoz"] in mail[0]["to"]
        assert "night@resort.example" in mail[0]["cc"]            # копия службы
        assert "Уборка не завершена" in mail[0]["body"]
        assert "Ночной отчёт" in mail[0]["subject"]

        # отправленное помечено и повторно не уходит
        d = _defects(employee_client, rep)
        assert d["counts"]["dispatched"] == 2
        sent_rows = [row for g in d["groups"] for row in g["defects"] if row["dispatched"]]
        assert len(sent_rows) == 2 and all(row["dispatched_at"] for row in sent_rows)
        assert all(not row["sendable"] for row in sent_rows)

        r2 = employee_client.post(f"/api/night/reports/{rep.id}/dispatch",
                                  json={"mode": "selected", "item_ids": ids})
        assert r2.status_code == 422 and "уже отправлено" in r2.json()["detail"], r2.text


def test_ne_otmechennoe_ukhodit_vmeste_so_vsem(employee_client, admin_client, open_shift,
                                               channels, fake_telegram, fake_smtp):
    """Решение владельца: «Не проверено» включается в отчёт отдельным блоком.

    Отправка «всё скопом» забирает и замечания, и неотмеченные пункты; службы без
    заполненного канала не получают ничего, но причины видны в ответе (skipped).
    """
    with open_shift() as rep:
        items = _report_item_ids(employee_client, rep, "Вилла 4003")
        _answer(employee_client, items[TECH_IDX]["id"], "bad", "не горит")
        r = employee_client.post(f"/api/night/reports/{rep.id}/dispatch", json={"mode": "all"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["marked"] >= 20, body["marked"]              # неотмеченные пункты тоже ушли
        tech = next(d for d in body["dispatches"] if d["recipient_name"] == "Техническая служба")
        kinds = {i["kind"] for i in tech["items"]}
        assert kinds == {"bad", "unchecked"}, kinds
        assert "Не проверено" not in tech["message"] and "не горит" in tech["message"]
        # у служб без канала отправки нет, но причина видна
        skipped = {s["service_name"]: s["problems"] for s in body["skipped"]}
        assert "Батлер-сервис" in skipped and any("чат" in p for p in skipped["Батлер-сервис"])


def test_vyborochnaya_otpravka_i_otpravka_sluzhbe(employee_client, admin_client, open_shift,
                                                  channels, fake_telegram, fake_smtp):
    with open_shift() as rep:
        # два замечания одной службе — в разных объектах зоны (в одном объекте
        # пункт «Свет выключен» всего один)
        for area, note in (("Вилла 4003", "первый"), ("Вилла 4004", "второй")):
            items = _report_item_ids(employee_client, rep, area)
            _answer(employee_client, items[TECH_IDX]["id"], "bad", note)
        tech = _items_of_service(employee_client, rep, "Техническая служба", "bad")
        assert len(tech) == 2, [t["text"] for t in tech]

        r = employee_client.post(f"/api/night/reports/{rep.id}/dispatch",
                                 json={"mode": "selected", "item_ids": [tech[0]["id"]]})
        assert r.status_code == 200, r.text
        assert r.json()["marked"] == 1
        texts = [c["payload"]["text"] for c in fake_telegram["calls"] if c["method"] == "sendMessage"]
        assert any("первый" in t for t in texts) and not any("второй" in t for t in texts)

        # вторая отправка — только оставшейся службе
        # отправка одной службе: только её позиции, и уже отправленное не дублируется
        rest = [t["id"] for t in _items_of_service(employee_client, rep, "Техническая служба", "bad")
                if t["sendable"]]
        r2 = employee_client.post(f"/api/night/reports/{rep.id}/dispatch",
                                  json={"mode": "selected", "item_ids": rest,
                                        "service_ids": [tech[0]["service_id"]]})
        assert r2.status_code == 200 and r2.json()["marked"] == 1, r2.text
        assert all(d["recipient_name"] == "Техническая служба" for d in r2.json()["dispatches"])


def test_ispravlennoe_posle_otpravki_bolshe_ne_ushlo(employee_client, admin_client, open_shift,
                                                     channels, fake_telegram, fake_smtp):
    with open_shift() as rep:
        v4003 = _report_item_ids(employee_client, rep, "Вилла 4003")
        item_id = v4003[TECH_IDX]["id"]
        _answer(employee_client, item_id, "bad", "не горит")
        assert employee_client.post(f"/api/night/reports/{rep.id}/dispatch",
                                    json={"mode": "selected", "item_ids": [item_id]}).status_code == 200
        calls_before = len([c for c in fake_telegram["calls"] if c["method"] == "sendMessage"])

        # исправили после отправки: ничего не шлём и не отзываем
        _answer(employee_client, item_id, "ok")
        d = _defects(employee_client, rep)
        row = next((r for g in d["groups"] for r in g["defects"] if r["id"] == item_id), None)
        assert row is not None, "исправленная позиция пропала из отчёта"
        assert row["fixed_after_dispatch"] is True and row["sendable"] is False
        r2 = employee_client.post(f"/api/night/reports/{rep.id}/dispatch",
                                  json={"mode": "selected", "item_ids": [item_id]})
        assert r2.status_code == 422, r2.text
        assert len([c for c in fake_telegram["calls"] if c["method"] == "sendMessage"]) == calls_before


def test_bez_nastroennoy_dostavki_otpravka_409(employee_client, admin_client, open_shift):
    admin_client.put("/api/notify/config", json={
        "notify_telegram_token": "clear", "notify_smtp_host": "", "notify_email_from": ""})
    with open_shift() as rep:
        items = _report_item_ids(employee_client, rep, "Вилла 4003")
        _answer(employee_client, items[TECH_IDX]["id"], "bad", "не горит")
        r = employee_client.post(f"/api/night/reports/{rep.id}/dispatch", json={"mode": "all"})
        assert r.status_code == 409 and "Чаты и Почта" in r.json()["detail"], r.text


def test_predprosmotr_nichego_ne_otpravlyaet(employee_client, admin_client, open_shift,
                                             channels, fake_telegram, fake_smtp):
    with open_shift() as rep:
        items = _report_item_ids(employee_client, rep, "Вилла 4003")
        _answer(employee_client, items[TECH_IDX]["id"], "bad", "мигает лампа")
        r = employee_client.post(f"/api/night/reports/{rep.id}/defects/preview",
                                 json={"mode": "all"})
        assert r.status_code == 200, r.text
        msgs = r.json()["messages"]
        assert msgs and any("мигает лампа" in m["message"] for m in msgs)
        assert all("{items}" not in m["message"] for m in msgs)
        assert not fake_telegram["calls"] and not fake_smtp["sent"]
        assert _defects(employee_client, rep)["counts"]["dispatched"] == 0


def test_sboi_dostavki_vidny_v_zhurnale_i_povtoryayutsya(employee_client, admin_client,
                                                         open_shift, channels,
                                                         fake_telegram, fake_smtp):
    with open_shift() as rep:
        items = _report_item_ids(employee_client, rep, "Вилла 4003")
        _answer(employee_client, items[TECH_IDX]["id"], "bad", "не горит")
        fake_telegram["state"]["fail"] = True
        item_id = items[TECH_IDX]["id"]
        r = employee_client.post(f"/api/night/reports/{rep.id}/dispatch",
                                 json={"mode": "selected", "item_ids": [item_id]})
        assert r.status_code == 200, r.text
        assert r.json()["failed"] == 1 and r.json()["marked"] == 0     # не отправили — не помечаем

        journal = employee_client.get(f"/api/night/reports/{rep.id}/dispatches").json()["dispatches"]
        failed_rows = [row for row in journal if row["status"] == "failed"]
        # журнал общий и не редактируется: в нём могут быть строки прошлых отправок,
        # поэтому смотрим на свою попытку
        assert failed_rows and journal[0]["status"] == "failed"
        # ошибка транспорта в журнале — человекочитаемая (без токена и без сырого ответа)
        assert any("Чат не найден" in row["error"] for row in failed_rows), \
            [row["error"] for row in failed_rows]
        # позиция осталась неотправленной — можно повторить
        row = next(r for g in _defects(employee_client, rep)["groups"] for r in g["defects"]
                   if r["id"] == item_id)
        assert row["sendable"] is True and row["dispatched"] is False

        fake_telegram["state"]["fail"] = False
        retry = admin_client.post(f"/api/notify/dispatches/{failed_rows[0]['id']}/resend")
        assert retry.status_code == 200, retry.text
        row = retry.json()["dispatch"]
        assert row["status"] == "sent" and row["attempts"] == 2 and row["external_id"]

        # успешную доставку повторить нельзя
        assert admin_client.post(f"/api/notify/dispatches/{row['id']}/resend").status_code == 409


def test_obshchiy_zhurnal_dlya_razdelov(admin_client, employee_client, open_shift,
                                        channels, fake_telegram, fake_smtp):
    with open_shift() as rep:
        items = _report_item_ids(employee_client, rep, "Вилла 4003")
        item_id = items[TECH_IDX]["id"]
        _answer(employee_client, item_id, "bad", "не горит")
        assert employee_client.post(f"/api/night/reports/{rep.id}/dispatch",
                                    json={"mode": "selected", "item_ids": [item_id]}).status_code == 200
        rows = admin_client.get("/api/notify/dispatches?domain=night").json()["dispatches"]
        assert rows and rows[0]["domain"] == "night" and rows[0]["ref_id"] == rep.id
        assert rows[0]["items_count"] >= 1 and rows[0]["recipient_name"]
        # журнал приложения — менеджменту; батлер видит журнал своей смены
        assert employee_client.get("/api/notify/dispatches").status_code == 403
        assert employee_client.get(f"/api/night/reports/{rep.id}/dispatches").status_code == 200


def test_otpravit_mozhet_lyuboy_polzovatel_obhoda(employee_client, admin_client, open_shift,
                                                  channels, fake_telegram, fake_smtp):
    """Нового права не вводили: отправляет тот, кто ведёт обход (решение владельца)."""
    with open_shift() as rep:
        items = _report_item_ids(employee_client, rep, "Вилла 4003")
        item_id = items[TECH_IDX]["id"]
        _answer(employee_client, item_id, "bad", "не горит")
        r = employee_client.post(f"/api/night/reports/{rep.id}/dispatch",
                                 json={"mode": "selected", "item_ids": [item_id]})
        assert r.status_code == 200, r.text
        journal = employee_client.get(f"/api/night/reports/{rep.id}/dispatches").json()["dispatches"]
        assert journal and journal[0]["actor_name"]


def test_vlozheniya_uhodyat_vmeste_s_soobshcheniem(employee_client, admin_client, open_shift,
                                                  channels, fake_telegram, fake_smtp):
    """Фото и видео отметки прикрепляются к сообщению службы."""
    png = b"\x89PNG\r\n\x1a\n" + b"\x01" * 64
    with open_shift() as rep:
        items = _report_item_ids(employee_client, rep, "Вилла 4003")
        item_id = items[TECH_IDX]["id"]
        _answer(employee_client, item_id, "bad", "трещина на витраже")
        up = employee_client.post(f"/api/night/items/{item_id}/photo",
                                  files={"file": ("tresh.png", png, "image/png")})
        assert up.status_code == 200, up.text

        d = _defects(employee_client, rep)
        row = next(r for g in d["groups"] for r in g["defects"] if r["id"] == item_id)
        assert len(row["media"]) == 1 and row["media"][0]["media_type"] == "photo"

        r = employee_client.post(f"/api/night/reports/{rep.id}/dispatch",
                                 json={"mode": "selected", "item_ids": [item_id]})
        assert r.status_code == 200, r.text
        media_calls = [c for c in fake_telegram["calls"] if c["method"] == "sendPhoto"]
        assert media_calls and media_calls[0]["files"]["photo"][1] == png
        journal = employee_client.get(f"/api/night/reports/{rep.id}/dispatches").json()["dispatches"]
        tech_row = next(x for x in journal if x["recipient_name"] == "Техническая служба")
        assert tech_row["media_count"] == 1
