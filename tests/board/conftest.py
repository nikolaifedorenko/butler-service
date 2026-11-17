"""Фикстуры шахматки (роли, «сегодня», демо-набор, батлеры) общие для каталогов fund, guests, board и stays:
определены в ``tests/stays/conftest.py``, здесь только подключены."""
from tests.stays.conftest import (  # noqa: F401 — фикстуры pytest
    assign_only_client,
    big_fund,
    butler_client,
    butlers,
    demo_small,
    mgmt_client,
    names_client,
    occupancy_client,
    own_reservation,
    today,
)
