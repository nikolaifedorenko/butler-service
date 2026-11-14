"""Адрес БД: DATABASE_URL → POSTGRES_* (с экранированием); только PostgreSQL.

Prod-compose подставлял POSTGRES_PASSWORD в DATABASE_URL как есть: «@ : / # %» в пароле
ломали разбор адреса, и приложение не подключалось.
"""
from __future__ import annotations

import os
import pathlib
import re
import tomllib

import pytest
from sqlalchemy.engine import make_url

from app.core.config import Settings

ROOT = pathlib.Path(__file__).resolve().parents[1]
NASTY = "p@ss:w/rd#1%?&="
# адрес тестовой базы — до автофикстуры, которая убирает DATABASE_URL из окружения
TEST_DB_URL = os.environ.get("DATABASE_URL", "")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """conftest задаёт DATABASE_URL тестовой базы — он главнее, здесь его быть не должно."""
    for var in ("DATABASE_URL", "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER",
                "POSTGRES_PASSWORD", "POSTGRES_DB"):
        monkeypatch.delenv(var, raising=False)


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_explicit_database_url_wins():
    url = "postgresql+psycopg2://u:p@other:5432/x"
    assert _settings(database_url=url, postgres_host="db").database_url == url


def test_database_is_required():
    with pytest.raises(ValueError, match="POSTGRES_HOST"):
        _settings()


@pytest.mark.parametrize("url", ["sqlite:///x.db", "mysql://u:p@h/x"])
def test_only_postgresql_is_supported(url):
    with pytest.raises(ValueError, match="только PostgreSQL"):
        _settings(database_url=url)


def test_postgres_parts_are_escaped():
    url = make_url(_settings(postgres_host="db", postgres_user="u@1", postgres_password=NASTY,
                             postgres_db="tt/prod", postgres_port=6543).database_url)
    assert (url.drivername, url.host, url.port) == ("postgresql+psycopg2", "db", 6543)
    assert (url.username, url.password, url.database) == ("u@1", NASTY, "tt/prod")


def test_empty_postgres_password_is_omitted():
    url = make_url(_settings(postgres_host="db").database_url)
    assert url.password is None and url.username == "timetrack"


def test_prod_compose_builds_url_in_app():
    compose = (ROOT / "docker-compose.prod.yml").read_text()
    env = compose[compose.index("x-app-env:"):compose.index("services:")]
    code = "\n".join(line.split("#", 1)[0] for line in env.splitlines())
    assert "DATABASE_URL" not in code, "пароль снова подставляется в URL без экранирования"
    for var in ("POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        assert re.search(rf"^\s+{var}:", code, re.M), var


def test_dockerfile_installs_from_lock_and_postgres_driver_required():
    dockerfile = (ROOT / "Dockerfile").read_text()
    code = "\n".join(line.split("#", 1)[0] for line in dockerfile.splitlines())
    assert "|| echo" not in code, "сбой установки зависимостей снова глотается"
    assert "uv sync --frozen --no-dev" in code, "образ ставит зависимости не из uv.lock"
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    assert any(d.startswith("psycopg2-binary") for d in deps), "драйвер PostgreSQL — обязательная зависимость"
    assert "SQLITE" not in code


def test_driver_receives_raw_password():
    """psycopg2 получает пароль байт в байт: экранирование снимает SQLAlchemy."""
    pytest.importorskip("psycopg2")       # драйвер — в образе и в CI-джобе postgres
    from sqlalchemy import create_engine

    url = make_url(_settings(postgres_host="db", postgres_password=NASTY).database_url)
    _, kwargs = create_engine(url).dialect.create_connect_args(url)
    assert kwargs["password"] == NASTY and kwargs["host"] == "db" and kwargs["dbname"] == "timetrack"


@pytest.mark.skipif(not TEST_DB_URL.startswith("postgresql"),
                    reason="настоящий PostgreSQL — в CI-джобе postgres")
def test_connects_to_postgres_with_nasty_password(db):
    """CI, PostgreSQL 16: роль с паролем «@ : / # % ? & =» подключается по адресу из POSTGRES_*."""
    from sqlalchemy import create_engine, text

    real = make_url(TEST_DB_URL)
    role = "tt_nasty_pw"
    db.execute(text(f"DROP ROLE IF EXISTS {role}"))
    db.execute(text(f"CREATE ROLE {role} LOGIN PASSWORD '{NASTY}'"))   # в NASTY нет кавычек
    db.commit()
    try:
        url = _settings(postgres_host=real.host, postgres_port=real.port or 5432, postgres_user=role,
                        postgres_password=NASTY, postgres_db=real.database).database_url
        eng = create_engine(url)
        with eng.connect() as con:
            assert con.execute(text("select current_user")).scalar() == role
        eng.dispose()
    finally:
        db.execute(text(f"DROP ROLE IF EXISTS {role}"))
        db.commit()
