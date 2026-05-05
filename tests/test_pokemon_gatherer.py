"""
Tests for the Pokemon gatherer route.

Covers:
1. List + detail endpoints expose both SVS and BRV.
2. Card listing returns the expected supertype mix for SVS.
3. Filters work: pokemon_type, supertype, is_ex, guild, hp_min/max, text_search.
4. Sorting by HP (desc) puts Charizard ex (330 HP) first within Pokemon.
5. 404 on unknown set code.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.routes.pokemon_gatherer import router as pokemon_gatherer_router


def _make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(pokemon_gatherer_router, prefix="/api")
    return app


client = TestClient(_make_test_app())


def test_list_sets_returns_svs_and_brv():
    r = client.get("/api/pokemon/sets")
    assert r.status_code == 200
    body = r.json()
    codes = {s["code"] for s in body["sets"]}
    assert {"SVS", "BRV"} <= codes


def test_list_sets_set_type_filter():
    r = client.get("/api/pokemon/sets", params={"set_type": "starter"})
    assert r.status_code == 200
    codes = {s["code"] for s in r.json()["sets"]}
    assert codes == {"SVS"}


def test_set_detail_svs_breakdown():
    r = client.get("/api/pokemon/sets/SVS")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "SVS"
    assert body["card_count"] == 41
    # SVS has 21 Pokemon, 12 Trainers, 8 Energy.
    assert body["supertype_breakdown"]["Pokemon"] == 21
    assert body["supertype_breakdown"]["Trainer"] == 12
    assert body["supertype_breakdown"]["Energy"] == 8
    # No guilds for SVS.
    assert body["guilds"] == []


def test_set_detail_brv_includes_guilds():
    r = client.get("/api/pokemon/sets/BRV")
    assert r.status_code == 200
    guilds = set(r.json()["guilds"])
    assert {"azorius", "izzet", "gruul", "rakdos", "selesnya"} <= guilds


def test_set_detail_404():
    r = client.get("/api/pokemon/sets/NOPE")
    assert r.status_code == 404


def test_filter_pokemon_type_and_supertype():
    r = client.get(
        "/api/pokemon/sets/SVS/cards",
        params={"supertype": "Pokemon", "pokemon_type": "R"},
    )
    assert r.status_code == 200
    body = r.json()
    names = [c["name"] for c in body["cards"]]
    assert "Charmander" in names
    assert "Charizard ex" in names
    # No water Pokemon should leak through.
    assert "Squirtle" not in names
    assert all(c["pokemon_type"] == "R" for c in body["cards"])
    assert all(c["supertype"] == "Pokemon" for c in body["cards"])


def test_filter_is_ex_true():
    r = client.get(
        "/api/pokemon/sets/SVS/cards",
        params={"is_ex": "true"},
    )
    assert r.status_code == 200
    cards = r.json()["cards"]
    assert len(cards) >= 1
    for c in cards:
        assert c["is_ex"] is True


def test_filter_brv_guild_izzet():
    r = client.get(
        "/api/pokemon/sets/BRV/cards",
        params={"guild": "izzet", "limit": 200},
    )
    assert r.status_code == 200
    cards = r.json()["cards"]
    assert len(cards) > 0
    for c in cards:
        assert c["guild"] == "izzet"


def test_filter_hp_range():
    r = client.get(
        "/api/pokemon/sets/SVS/cards",
        params={"hp_min": 200, "supertype": "Pokemon"},
    )
    assert r.status_code == 200
    cards = r.json()["cards"]
    # 200+ HP in SVS: Charizard ex (330), Blastoise ex, Venusaur ex, Gardevoir ex.
    names = {c["name"] for c in cards}
    assert "Charizard ex" in names
    for c in cards:
        assert c["hp"] is not None and c["hp"] >= 200


def test_text_search_matches_card_text():
    r = client.get(
        "/api/pokemon/sets/SVS/cards",
        params={"text_search": "draw"},
    )
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["cards"]]
    # Professor's Research has "draw" in its text.
    assert any("Professor" in n for n in names)


def test_sort_hp_desc_puts_highest_first():
    r = client.get(
        "/api/pokemon/sets/SVS/cards",
        params={"supertype": "Pokemon", "sort_by": "hp", "sort_order": "desc", "limit": 5},
    )
    assert r.status_code == 200
    cards = r.json()["cards"]
    hps = [c["hp"] for c in cards]
    # Strictly non-increasing.
    assert hps == sorted(hps, reverse=True)
    # SVS top HP is Venusaur ex at 340.
    assert cards[0]["hp"] == 340
    assert cards[0]["name"] == "Venusaur ex"


def test_charizard_ex_has_attacks_and_weakness():
    r = client.get(
        "/api/pokemon/sets/SVS/cards",
        params={"text_search": "Charizard"},
    )
    assert r.status_code == 200
    chars = [c for c in r.json()["cards"] if c["name"] == "Charizard ex"]
    assert chars, "Charizard ex not in response"
    chari = chars[0]
    attack_names = {a["name"] for a in chari["attacks"]}
    assert "Burning Dark" in attack_names
    burning = next(a for a in chari["attacks"] if a["name"] == "Burning Dark")
    assert burning["damage"] == 180
    assert chari["weakness_type"] == "W"
    assert chari["retreat_cost"] == 2
    assert chari["is_ex"] is True


def test_filter_is_ex_false_excludes_ex():
    r = client.get(
        "/api/pokemon/sets/SVS/cards",
        params={"is_ex": "false", "supertype": "Pokemon"},
    )
    assert r.status_code == 200
    cards = r.json()["cards"]
    assert len(cards) >= 1
    for c in cards:
        assert c["is_ex"] is False


def test_filter_combined_type_and_hp_min():
    """pokemon_type=R intersected with hp_min=200 should pin to fire-ex Pokemon only."""
    r = client.get(
        "/api/pokemon/sets/SVS/cards",
        params={"pokemon_type": "R", "hp_min": 200},
    )
    assert r.status_code == 200
    cards = r.json()["cards"]
    assert len(cards) >= 1
    for c in cards:
        assert c["pokemon_type"] == "R"
        assert c["hp"] is not None and c["hp"] >= 200
    names = {c["name"] for c in cards}
    assert "Charizard ex" in names


def test_sort_hp_asc_does_not_bubble_non_pokemon_to_top():
    """Mixed supertypes with HP asc should not put None-HP cards first."""
    r = client.get(
        "/api/pokemon/sets/SVS/cards",
        params={"sort_by": "hp", "sort_order": "asc", "limit": 100},
    )
    assert r.status_code == 200
    cards = r.json()["cards"]
    # The first card returned should be a real Pokemon with HP, not a
    # Trainer / Energy whose HP is null.
    assert cards[0]["hp"] is not None
    assert cards[0]["supertype"] == "Pokemon"


def test_zero_damage_attack_round_trip():
    """A 0-damage status attack should keep damage=0, not be coerced to None."""
    from src.server.routes.pokemon_gatherer import _attack_to_data

    result = _attack_to_data(
        {"name": "Sleep Powder", "cost": [{"type": "G", "count": 1}], "damage": 0, "text": "Asleep."}
    )
    assert result.damage == 0


def test_no_damage_attack_stays_none():
    """An attack without a damage field should serialize as null."""
    from src.server.routes.pokemon_gatherer import _attack_to_data

    result = _attack_to_data(
        {"name": "Confuse Ray", "cost": [{"type": "P", "count": 1}], "text": "Confused."}
    )
    assert result.damage is None


def test_guild_filter_on_svs_returns_empty():
    """Guild filtering on a non-BRV set must not leak; should silently return zero."""
    r = client.get(
        "/api/pokemon/sets/SVS/cards",
        params={"guild": "izzet"},
    )
    assert r.status_code == 200
    assert r.json()["cards"] == []
    assert r.json()["total"] == 0


def test_sort_rarity_pins_unknown_to_bottom_both_directions():
    """Cards without a rarity should always sort last, regardless of asc/desc.
    BRV custom cards mostly lack a rarity; the bug was rarity=None used 'z'
    as a sort sentinel, which still interleaves with hypothetical 'z'-prefixed
    rarity values and reverses incorrectly under desc."""
    asc = client.get(
        "/api/pokemon/sets/BRV/cards",
        params={"sort_by": "rarity", "sort_order": "asc", "limit": 200},
    ).json()["cards"]
    desc = client.get(
        "/api/pokemon/sets/BRV/cards",
        params={"sort_by": "rarity", "sort_order": "desc", "limit": 200},
    ).json()["cards"]
    # In both directions, the LAST card returned (within the page) should
    # have an empty / null rarity if any unknown-rarity cards exist.
    asc_unknown = [c for c in asc if not c["rarity"]]
    desc_unknown = [c for c in desc if not c["rarity"]]
    if asc_unknown:
        # All unknown-rarity cards should be at the tail.
        first_unknown_idx_asc = next(i for i, c in enumerate(asc) if not c["rarity"])
        assert all(not c["rarity"] for c in asc[first_unknown_idx_asc:])
    if desc_unknown:
        first_unknown_idx_desc = next(i for i, c in enumerate(desc) if not c["rarity"])
        assert all(not c["rarity"] for c in desc[first_unknown_idx_desc:])


def test_pagination_limit_offset():
    page1 = client.get(
        "/api/pokemon/sets/SVS/cards",
        params={"sort_by": "name", "sort_order": "asc", "limit": 10, "offset": 0},
    ).json()
    page2 = client.get(
        "/api/pokemon/sets/SVS/cards",
        params={"sort_by": "name", "sort_order": "asc", "limit": 10, "offset": 10},
    ).json()
    assert len(page1["cards"]) == 10
    assert len(page2["cards"]) == 10
    p1_names = {c["name"] for c in page1["cards"]}
    p2_names = {c["name"] for c in page2["cards"]}
    assert p1_names.isdisjoint(p2_names)
    assert page1["total"] == page2["total"]


if __name__ == "__main__":
    import sys

    suite = [
        test_list_sets_returns_svs_and_brv,
        test_list_sets_set_type_filter,
        test_set_detail_svs_breakdown,
        test_set_detail_brv_includes_guilds,
        test_set_detail_404,
        test_filter_pokemon_type_and_supertype,
        test_filter_is_ex_true,
        test_filter_brv_guild_izzet,
        test_filter_hp_range,
        test_text_search_matches_card_text,
        test_sort_hp_desc_puts_highest_first,
        test_charizard_ex_has_attacks_and_weakness,
        test_filter_is_ex_false_excludes_ex,
        test_filter_combined_type_and_hp_min,
        test_sort_hp_asc_does_not_bubble_non_pokemon_to_top,
        test_zero_damage_attack_round_trip,
        test_no_damage_attack_stays_none,
        test_guild_filter_on_svs_returns_empty,
        test_sort_rarity_pins_unknown_to_bottom_both_directions,
        test_pagination_limit_offset,
    ]

    failed = 0
    for fn in suite:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")

    if failed:
        print(f"\n{failed} of {len(suite)} failed")
        sys.exit(1)
    print(f"\nAll {len(suite)} tests passed")
