"""Внешний идентификатор «система, экземпляр, id» (шаг 5е): запись находится по тройке,
повторный импорт обновляет, а не дублирует; уникальность держит база."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.external import ExternalRef
from app.modules.guests.adapters.orm import Guest
from app.modules.guests.application import guests
from app.modules.stays.adapters.orm import Reservation
from app.modules.stays.application import guest_merge, reservations

from .helpers import API, create_res, make_category, make_guest, uniq


def _ref(system: str = "fidelio", instance: str = "", ext_id: str | None = None) -> ExternalRef:
    return ExternalRef(system=system, instance=instance, id=ext_id or uniq())


def _data(last: str) -> dict:
    """Профиль целиком, как его присылает форма (без внешнего идентификатора)."""
    return {"last_name": last + uniq(), "first_name": "", "middle_name": "", "phone": "", "email": "",
            "gender": "", "special": False, "note": "", "vip_code_id": None}


def _count(db, model, ref: ExternalRef) -> int:
    return db.scalar(select(func.count()).select_from(model).where(
        model.ext_system == ref.system, model.ext_instance == ref.instance, model.ext_id == ref.id))


def test_guest_upsert_creates_then_updates(db):
    ref = _ref()
    g1, before, created = guests.upsert_guest(db, ref, _data("Первый"))
    assert created and before == {}
    g2, before2, created2 = guests.upsert_guest(db, ref, _data("Второй"))
    assert not created2 and g2.id == g1.id and before2["last_name"].startswith("Первый")
    assert g2.last_name.startswith("Второй") and _count(db, Guest, ref) == 1
    assert guests.guest_dict(g2)["external"] == {"system": "fidelio", "instance": "", "id": ref.id}


def test_instances_and_systems_do_not_clash(db):
    ext = uniq()
    ids = {guests.upsert_guest(db, _ref(s, i, ext), _data("Раздельный"))[0].id
           for s, i in (("fidelio", ""), ("fidelio", "second"), ("other", ""))}
    assert len(ids) == 3


def test_database_refuses_second_row_with_same_triple(db):
    ref = _ref()
    guests.upsert_guest(db, ref, _data("Один"))
    db.add(Guest(last_name="Дубль", ext_system=ref.system, ext_instance=ref.instance, ext_id=ref.id))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_hand_made_records_have_no_external_id(manager_client, db):
    a, b = make_guest(manager_client), make_guest(manager_client)      # без внешнего id — сколько угодно
    assert a["external"] is None and b["external"] is None


def test_merge_moves_external_id_to_kept_guest(db):
    ref = _ref()
    keep = guests.save_guest(db, _data("Остаётся"), None)[0]
    drop, _, _ = guests.upsert_guest(db, ref, _data("Уходит"))
    out = guest_merge.merge_guests(db, keep.id, drop.id)
    assert "external" in out["moves"]["profile"]
    db.refresh(keep)
    assert keep.ext_id == ref.id and _count(db, Guest, ref) == 1


def test_reservation_upsert_creates_then_replaces(manager_client, manager_role_client, db):
    cat = make_category(manager_role_client, n_units=2)
    guest = make_guest(manager_client)
    base = db.get(Reservation, create_res(manager_client, cat, "2047-03-10", "2047-03-12",
                                          [(guest["id"], "main", None, None)])["id"])
    doc = reservations.doc_of(db, base)
    doc["occupants"] = [{k: v for k, v in o.items() if k != "id"} for o in doc["occupants"]]
    doc["number"] = "X" + uniq()
    ref = _ref()
    r1, before, created = reservations.upsert_reservation(db, ref, doc)
    assert created and before == {} and r1.id != base.id and r1.ext_id == ref.id
    doc2 = {**doc, "customer": "Новый заказчик"}
    r2, before2, created2 = reservations.upsert_reservation(db, ref, doc2)
    assert not created2 and r2.id == r1.id and r2.customer == "Новый заказчик"
    assert _count(db, Reservation, ref) == 1
    assert reservations.reservation_dict(db, r2)["external"]["id"] == ref.id


def test_api_returns_external_object_or_null(manager_client, manager_role_client, db):
    cat = make_category(manager_role_client, n_units=1)
    guest = make_guest(manager_client)
    res = create_res(manager_client, cat, "2047-04-10", "2047-04-12", [(guest["id"], "main", None, None)])
    assert res["external"] is None
    r = manager_client.get(f"{API}/guests/{guest['id']}")
    assert r.status_code == 200 and r.json()["external"] is None
