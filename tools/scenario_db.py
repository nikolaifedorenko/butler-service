#!/usr/bin/env python3
"""Пересоздать пустую базу PostgreSQL для сценария интерфейса и напечатать её адрес.

    DATABASE_URL="$(python3 tools/scenario_db.py stays)"

Сервер — TEST_DATABASE_SERVER (по умолчанию локальный из docker-compose.yml:
`docker compose up -d db`), база — butler_scn_<имя>.
"""
from __future__ import annotations

import os
import re
import sys

from sqlalchemy import create_engine, text

SERVER = os.environ.get("TEST_DATABASE_SERVER", "postgresql+psycopg2://postgres:dev@127.0.0.1:54329")


def main() -> int:
    name = "butler_scn_" + re.sub(r"\W", "_", sys.argv[1])
    admin = create_engine(f"{SERVER}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as con:
            con.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            con.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:
        print(f"Нет PostgreSQL по адресу {SERVER}: запустите `docker compose up -d db` "
              f"или задайте TEST_DATABASE_SERVER ({type(exc).__name__})", file=sys.stderr)
        return 1
    print(f"{SERVER}/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
