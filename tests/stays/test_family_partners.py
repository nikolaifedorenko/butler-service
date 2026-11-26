"""Партнёры и бывшие в семье гостя (переработка семьи 23.11.2026): вид связи partner
(несколько действующих, флаг «бывшие»), новый супруг одной записью со снятием прежнего
брака (also_former_id), родня бывших браков/союзов в kin с пометкой via_former,
на табло — только действующая родня.
"""
from __future__ import annotations

from .helpers import API, make_guest


def _link(client, gid, kind, **body):
    r = client.post(f"{API}/guests/{gid}/links", json={"kind": kind, **body})
    return r


def test_partners_multiple_current_allowed(manager_client):
    g = make_guest(manager_client)
    p1 = make_guest(manager_client, "Партнеров")
    p2 = make_guest(manager_client, "Второпартнёров")
    assert _link(manager_client, g["id"], "partner", guest_id=p1["id"]).status_code == 200
    assert _link(manager_client, g["id"], "partner", guest_id=p2["id"]).status_code == 200
    fam = manager_client.get(f"{API}/guests/{g['id']}/family").json()
    assert len(fam["partners"]) == 2


def test_partner_former_flag_roundtrip(manager_client):
    g = make_guest(manager_client)
    p = make_guest(manager_client, "Бывшепартнёров")
    link = _link(manager_client, g["id"], "partner", guest_id=p["id"]).json()
    lid = link["links"][-1]["id"] if "links" in link else manager_client.get(
        f"{API}/guests/{g['id']}/family").json()["links"][-1]["id"]
    assert manager_client.patch(f"{API}/guest-links/{lid}", json={"former": True}).status_code == 200
    fam = manager_client.get(f"{API}/guests/{g['id']}/family").json()
    assert fam["partners"][0][2] is True
    # у партнёров эксклюзивности нет — снять «бывшие» можно всегда
    assert manager_client.patch(f"{API}/guest-links/{lid}", json={"former": False}).status_code == 200


def test_new_spouse_with_also_former_id(manager_client):
    g = make_guest(manager_client)
    first = make_guest(manager_client, "Первая")
    second = make_guest(manager_client, "Вторая")
    assert _link(manager_client, g["id"], "spouse", guest_id=first["id"]).status_code == 200
    # без also_former_id добавление второго действующего супруга заблокировано
    assert _link(manager_client, g["id"], "spouse", guest_id=second["id"]).status_code == 422
    fam = manager_client.get(f"{API}/guests/{g['id']}/family").json()
    old_link = next(ln for ln in fam["links"] if ln["kind"] == "spouse")
    # одной записью: новый супруг + прежний брак «бывшим»
    r = _link(manager_client, g["id"], "spouse", guest_id=second["id"], also_former_id=old_link["id"])
    assert r.status_code == 200, r.text
    fam = manager_client.get(f"{API}/guests/{g['id']}/family").json()
    spouses = {ln["b"] if ln["a"] == g["id"] else ln["a"]: ln["former"] for ln in fam["links"] if ln["kind"] == "spouse"}
    assert spouses[first["id"]] is True and spouses[second["id"]] is False


def test_also_former_id_rejects_foreign_link(manager_client):
    g = make_guest(manager_client)
    other = make_guest(manager_client, "Чужаков")
    p = make_guest(manager_client, "Посторонних")
    assert _link(manager_client, other["id"], "spouse", guest_id=p["id"]).status_code == 200
    fam_other = manager_client.get(f"{API}/guests/{other['id']}/family").json()
    foreign = next(ln for ln in fam_other["links"] if ln["kind"] == "spouse")
    new = make_guest(manager_client, "Новосупругов")
    r = _link(manager_client, g["id"], "spouse", guest_id=new["id"], also_former_id=foreign["id"])
    assert r.status_code == 422, r.text


def test_kin_marks_former_and_partner_relatives(manager_client):
    g = make_guest(manager_client)
    ex = make_guest(manager_client, "Бывших")
    ex_mother = make_guest(manager_client, "Тёщиных", special=False)
    # у бывшего супруга — мать; связь ex_mother → ex
    assert _link(manager_client, ex_mother["id"], "parent", guest_id=ex["id"]).status_code == 200
    assert _link(manager_client, g["id"], "spouse", guest_id=ex["id"]).status_code == 200
    fam = manager_client.get(f"{API}/guests/{g['id']}/family").json()
    link = next(ln for ln in fam["links"] if ln["kind"] == "spouse")
    assert manager_client.patch(f"{API}/guest-links/{link['id']}", json={"former": True}).status_code == 200
    fam = manager_client.get(f"{API}/guests/{g['id']}/family").json()
    kin = {k["person_id"]: k for k in fam["kin"]}
    # родня бывшего брака считается и помечается
    assert kin[ex_mother["id"]]["via_former"] is True
    # партнёр — с другим заголовком
    partner = make_guest(manager_client, "Союзных")
    assert _link(manager_client, g["id"], "partner", guest_id=partner["id"]).status_code == 200
    fam = manager_client.get(f"{API}/guests/{g['id']}/family").json()
    kin = {k["person_id"]: k for k in fam["kin"]}
    assert kin[partner["id"]]["title"] == "партнёр"
    assert kin[partner["id"]]["via_former"] is False


def test_spouse_still_exclusive_without_former(manager_client):
    g = make_guest(manager_client)
    a = make_guest(manager_client, "Супругов")
    b = make_guest(manager_client, "Двусупругов")
    assert _link(manager_client, g["id"], "spouse", guest_id=a["id"]).status_code == 200
    r = _link(manager_client, g["id"], "spouse", guest_id=b["id"])
    assert r.status_code == 422
    assert "уже есть супруг" in r.json()["detail"]


def test_partner_cannot_be_ancestor(manager_client):
    g = make_guest(manager_client)
    parent = make_guest(manager_client, "Родителей")
    assert _link(manager_client, parent["id"], "parent", guest_id=g["id"]).status_code == 200
    r = _link(manager_client, g["id"], "partner", guest_id=parent["id"])
    assert r.status_code == 422
    assert "предка или потомка" in r.json()["detail"]


def test_existing_child_link_rejects_stale_parent_selection(manager_client):
    child = make_guest(manager_client)
    former_parent = make_guest(manager_client)
    new_parent = make_guest(manager_client)
    original = _link(manager_client, former_parent["id"], "parent", guest_id=child["id"])
    assert original.status_code == 200, original.text
    assert manager_client.delete(f"{API}/guest-links/{original.json()['id']}").status_code == 200

    stale = _link(manager_client, new_parent["id"], "parent", guest_id=child["id"],
                  expected_parent_ids=[former_parent["id"]])
    assert stale.status_code == 409, stale.text
    family = manager_client.get(f"{API}/guests/{child['id']}/family").json()
    assert family["parents"] == []


def test_spouse_dates_survive_status_change_and_only_explicitly_clear(manager_client):
    g, spouse, child = [make_guest(manager_client) for _ in range(3)]
    created = _link(manager_client, g["id"], "spouse", guest_id=spouse["id"], marriage_start="2000-11-12")
    assert created.status_code == 200, created.text
    lid = created.json()["id"]
    for parent in (g, spouse):
        assert _link(manager_client, parent["id"], "parent", guest_id=child["id"]).is_success
        card = manager_client.get(f"{API}/guests/{parent['id']}/card").json()
        assert next(link for link in card["links"] if link["id"] == lid)["marriage_start"] == "2000-11-12"

    patch = manager_client.patch(f"{API}/guest-links/{lid}", json={"former": True, "marriage_end": "2024-10-10"})
    assert patch.status_code == 200, patch.text
    fam = manager_client.get(f"{API}/guests/{g['id']}/family").json()
    marriage = next(link for link in fam["links"] if link["id"] == lid)
    assert (marriage["former"], marriage["marriage_start"], marriage["marriage_end"]) == (
        True, "2000-11-12", "2024-10-10")
    assert sorted(fam["parents"]) == sorted([[child["id"], g["id"]], [child["id"], spouse["id"]]])

    cleared = manager_client.patch(f"{API}/guest-links/{lid}", json={"marriage_start": None}).json()
    assert cleared["former"] and cleared["marriage_start"] is None and cleared["marriage_end"] == "2024-10-10"
    current = manager_client.patch(f"{API}/guest-links/{lid}", json={"former": False}).json()
    assert not current["former"] and current["marriage_end"] is None


def test_marriage_dates_validate_kind_status_and_chronology(manager_client):
    g, spouse = [make_guest(manager_client) for _ in range(2)]
    for kind, params in (
        ("parent", {"marriage_start": "2000-10-11"}),
        ("spouse", {"marriage_end": "2025-11-12"}),
        ("spouse", {"former": True, "marriage_start": "2025-11-12", "marriage_end": "2025-11-11"}),
    ):
        resp = _link(manager_client, g["id"], kind, guest_id=spouse["id"], **params)
        assert resp.status_code == 422, resp.text
    created = _link(manager_client, g["id"], "spouse", guest_id=spouse["id"], former=True,
                    marriage_end="2025-11-12")
    assert created.status_code == 200, created.text
    bad = manager_client.patch(f"{API}/guest-links/{created.json()['id']}", json={"marriage_start": "2025-11-13"})
    assert bad.status_code == 422, bad.text


def test_family_focus_recalculates_titles_for_same_graph(manager_client):
    parent, child, sibling, outsider = [make_guest(manager_client) for _ in range(4)]
    for item in (child, sibling):
        assert _link(manager_client, parent["id"], "parent", guest_id=item["id"]).is_success
    url = f"{API}/guests/{child['id']}/family"
    original = manager_client.get(url).json()
    updated = manager_client.get(url, params={"focus_id": parent["id"]}).json()
    assert updated["people"] == original["people"]
    assert {item["person_id"] for item in updated["kin"]} == {child["id"], sibling["id"]}
    assert manager_client.get(url, params={"focus_id": outsider["id"]}).status_code == 404
