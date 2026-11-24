"""Контракт самостоятельного раздела «Гости» для нестандартных наборов прав."""
from __future__ import annotations

import uuid

import pytest

from app.core.identity import AccessGrant
from tests.stays.conftest import _role_user


@pytest.mark.parametrize(
    ("permissions", "directory", "create"),
    [
        (("stays.guests",), True, False),
        (("stays.edit",), False, True),
        (("stays.guests", "stays.edit"), True, True),
        ((), False, False),
    ],
)
def test_guests_section_capability_matrix(app_stack, db, permissions, directory, create):
    suffix = uuid.uuid4().hex[:8]
    role = f"gmx_{suffix}"
    db.add_all(AccessGrant(role=role, permission=permission, effect="allow") for permission in permissions)
    db.commit()
    client = _role_user(app_stack, f"guests_{suffix}", role)

    me = client.get("/api/auth/me").json()
    assert ("guests" in {item["id"] for item in me["menu"]}) is (directory or create)
    assert (client.get("/api/stays/guests/list").status_code == 200) is directory
    assert (client.get("/api/stays/guests", params={"q": "нет"}).status_code == 200) is directory
    response = client.post("/api/stays/guests", json={"last_name": f"Матрица{suffix}"})
    assert (response.status_code == 200) is create

