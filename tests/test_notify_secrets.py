"""Секреты уведомлений шифруются в БД ключом NOTIFY_SECRET_KEY (решение владельца 25.10.2026).

Токен бота и пароль SMTP лежали в таблице settings открытым текстом: кто получил копию
базы или бэкап, получал и их (рецензия аудита 22.10.2026).

Что проверяется:
  * в БД — только шифротекст с префиксом enc:v1:, токена в нём нет; приложение его читает;
  * секрет, сохранённый до шифрования, при старте шифруется;
  * ключ не подходит (потерян, сменился) — секрет «не задан», просим ввести заново;
  * смена ключа «новый,старый»: при старте перешифровка новым, старый больше не нужен;
  * без ключа секрет не сохранить (400 с подсказкой), старый открытый — читается;
  * ключ не в формате Fernet — отказ на старте.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.settings_store import Setting

TOKEN = "123456:SECRET-TOKEN-abcdefghijklmnop"
KEY = "notify_telegram_token"


@pytest.fixture
def clean_token(admin_client, db):
    yield
    db.rollback()
    row = db.get(Setting, KEY)
    if row is not None:
        db.delete(row)
        db.commit()


def _stored(db) -> str:
    db.expire_all()
    row = db.get(Setting, KEY)
    return row.value if row else ""


def test_saved_secret_is_ciphertext_and_readable(admin_client, db, clean_token):
    from app.modules.notify.application.config import load_config

    r = admin_client.put("/api/notify/config", json={KEY: TOKEN})
    assert r.status_code == 200, r.text
    stored = _stored(db)
    assert stored.startswith("enc:v1:") and TOKEN not in stored and "SECRET" not in stored
    assert load_config(db).telegram_token == TOKEN
    cfg = admin_client.get("/api/notify/config").json()["config"]
    assert cfg["telegram"]["token_set"] is True and cfg["unreadable"] == []
    assert TOKEN not in str(cfg)


def test_legacy_plaintext_secret_is_encrypted_at_startup(db, clean_token):
    from app.modules.notify.application.config import SECRET_KEYS, load_config
    from app.modules.notify.application.secrets import encrypt_stored_secrets

    db.add(Setting(key=KEY, value=TOKEN))             # как хранилось до 25.10.2026
    db.commit()
    assert load_config(db).telegram_token == TOKEN     # и до перешифровки читается
    assert encrypt_stored_secrets(db, SECRET_KEYS) == 1
    db.commit()
    assert _stored(db).startswith("enc:v1:") and load_config(db).telegram_token == TOKEN


def test_wrong_key_makes_secret_unreadable(admin_client, db, clean_token, monkeypatch):
    from app.modules.notify.application.config import load_config, public_config

    assert admin_client.put("/api/notify/config", json={KEY: TOKEN}).status_code == 200
    monkeypatch.setattr(settings, "notify_secret_key", Fernet.generate_key().decode())
    cfg = load_config(db)
    assert cfg.telegram_token == "" and cfg.unreadable == (KEY,)
    assert public_config(cfg)["telegram"]["token_set"] is False
    assert public_config(cfg)["unreadable"] == [KEY]


def test_key_rotation_reencrypts_with_new_key(admin_client, db, clean_token, monkeypatch):
    from app.modules.notify.application.config import SECRET_KEYS, load_config
    from app.modules.notify.application.secrets import encrypt_stored_secrets

    old = settings.notify_secret_key
    assert admin_client.put("/api/notify/config", json={KEY: TOKEN}).status_code == 200
    new = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "notify_secret_key", f"{new},{old}")
    before = _stored(db)
    assert load_config(db).telegram_token == TOKEN          # старым ключом читается
    assert encrypt_stored_secrets(db, SECRET_KEYS) == 1
    db.commit()
    assert _stored(db) != before
    monkeypatch.setattr(settings, "notify_secret_key", new)  # старый ключ убран
    assert load_config(db).telegram_token == TOKEN


def test_no_key_refuses_to_store_secret(admin_client, db, clean_token, monkeypatch):
    from app.modules.notify.application.config import SECRET_KEYS, load_config
    from app.modules.notify.application.secrets import encrypt_stored_secrets

    monkeypatch.setattr(settings, "notify_secret_key", "")
    r = admin_client.put("/api/notify/config", json={KEY: TOKEN})
    assert r.status_code == 400 and "NOTIFY_SECRET_KEY" in r.json()["detail"], r.text
    assert _stored(db) == ""
    db.add(Setting(key=KEY, value=TOKEN))
    db.commit()
    assert encrypt_stored_secrets(db, SECRET_KEYS) == 0       # без ключа не трогаем
    assert load_config(db).telegram_token == TOKEN            # доставка не ломается


def test_malformed_key_fails_at_startup(monkeypatch):
    from app.modules.notify.application.secrets import check_key_config

    monkeypatch.setattr(settings, "notify_secret_key", "not-a-fernet-key")
    with pytest.raises(RuntimeError, match="NOTIFY_SECRET_KEY"):
        check_key_config()
