"""Smoke tests for cross-game deckbuilder support.

Each supported game should expose its card pool through the same route surface
and validate decks against its own rules.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from src.server.main import app
from src.server.services import game_registry as gr
from src.server.services.deck_storage import deck_storage


client = TestClient(app)


def test_card_pool_sizes_match_registries():
    for game in gr.GAMES:
        r = client.get("/api/deckbuilder/cards/all", params={"game": game, "limit": 1})
        assert r.status_code == 200, f"{game}: {r.text}"
        body = r.json()
        assert body["total"] == len(gr.get_card_pool(game)), (
            f"{game} route returned {body['total']}, registry has {len(gr.get_card_pool(game))}"
        )


def test_card_lookup_per_game():
    """Looking up a known card in each game returns the right `game` tag."""
    samples = {
        "mtg": "Lightning Bolt",
        "finance": "Coupon Bill Vault",
        "minecraft": "Bed",
        "pokemon": None,         # filled below
        "yugioh": None,
        "hearthstone": None,
        "scp": None,
    }
    # Pick a real name from each pool for the games where we don't know one.
    for g in ("pokemon", "yugioh", "hearthstone", "scp"):
        pool = gr.get_card_pool(g)
        samples[g] = next(iter(pool.keys()))

    for game, card_name in samples.items():
        r = client.get(
            f"/api/deckbuilder/cards/{card_name}",
            params={"game": game},
        )
        assert r.status_code == 200, f"{game}/{card_name}: {r.text}"
        data = r.json()
        assert data["game"] == game
        assert data["name"] == card_name


def test_card_lookup_404_in_wrong_game():
    """A card present in game A is not found when queried under game B."""
    r = client.get("/api/deckbuilder/cards/Lightning Bolt", params={"game": "minecraft"})
    assert r.status_code == 404


def test_search_filters_by_game():
    """Searching with game=minecraft only returns minecraft cards (Bed exists,
    Lightning Bolt does not)."""
    r = client.post("/api/deckbuilder/cards/search", json={
        "game": "minecraft",
        "query": "Bed",
        "limit": 50,
    })
    assert r.status_code == 200
    names = {c["name"] for c in r.json()["cards"]}
    assert "Bed" in names
    assert "Lightning Bolt" not in names


def test_finance_card_listing_and_lookup_use_finance_pool():
    r = client.get("/api/deckbuilder/cards/all", params={"game": "finance", "limit": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == len(gr.get_card_pool("finance"))
    assert {c["game"] for c in body["cards"]} == {"finance"}
    assert all(c["domain"] in {"FINA", "FINM"} for c in body["cards"])

    r = client.get("/api/deckbuilder/cards/Coupon Bill Vault", params={"game": "finance"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["game"] == "finance"
    assert data["domain"] == "FINM"
    assert data["extras"]["liquidity_cost"] == 2


def test_validate_per_game_deck_size():
    """A 30-card deck is illegal in MTG (need 60) but legal in Hearthstone."""
    pool = gr.get_card_pool("hearthstone")
    name = next(iter(pool.keys()))
    main = [{"card": name, "qty": 2}] * 15  # 30 cards, 2-of each

    r = client.post(
        "/api/deckbuilder/decks/validate",
        json={"game": "hearthstone", "mainboard": main, "sideboard": []},
    )
    assert r.status_code == 200
    assert r.json()["is_valid"], r.json()

    r = client.post(
        "/api/deckbuilder/decks/validate",
        json={"game": "mtg", "mainboard": main, "sideboard": []},
    )
    body = r.json()
    # The HS card name is missing in MTG pool, so it'll be in missing_cards.
    assert body["is_valid"] is False
    assert body["missing_cards"]


def test_validate_minecraft_50_card_rule():
    """Minecraft is exactly 50 cards. 49 fails, 50 passes."""
    bed = [{"card": "Bed", "qty": 2}]
    main_49 = [{"card": "Bed", "qty": 1}] + [{"card": "Bed", "qty": 2}] * 24  # 1+48=49
    main_50 = [{"card": "Bed", "qty": 2}] * 25  # 50

    short = client.post(
        "/api/deckbuilder/decks/validate",
        json={"game": "minecraft", "mainboard": main_49, "sideboard": []},
    ).json()
    assert short["is_valid"] is False

    full = client.post(
        "/api/deckbuilder/decks/validate",
        json={"game": "minecraft", "mainboard": main_50, "sideboard": []},
    ).json()
    assert full["is_valid"] is True, full


def test_stats_minecraft_shows_material_distribution():
    main = [{"card": "Bed", "qty": 2}, {"card": "Iron Sword", "qty": 2}]
    r = client.post(
        "/api/deckbuilder/decks/stats",
        json={"game": "minecraft", "mainboard": main, "sideboard": []},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["card_count"] == 4
    extras = body["extras"]
    assert "material_distribution" in extras
    # Bed costs 2 wood; Iron Sword costs 2 iron. Total per 2 copies each:
    # 4 wood, 4 iron.
    assert extras["material_distribution"]["wood"] == 4
    assert extras["material_distribution"]["iron"] == 4


def test_save_and_list_filtered_by_game(tmp_path, monkeypatch):
    """Saving a Minecraft deck doesn't show up when listing MTG decks."""
    import sys
    from src.server.services.deck_storage import DeckStorageService
    from src.server.routes import deckbuilder as db_routes

    fresh_storage = DeckStorageService(data_dir=str(tmp_path / "decks"))
    # The route module imported `deck_storage` by name, so patch the routes
    # module's binding directly. (The services package re-exports the instance,
    # which shadows the submodule attribute in some import paths.)
    monkeypatch.setattr(db_routes, "deck_storage", fresh_storage)

    save = lambda body: client.post("/api/deckbuilder/decks", json=body).json()
    save({
        "game": "minecraft", "name": "Bed Stack",
        "archetype": "Stall", "colors": [], "description": "",
        "mainboard": [{"card": "Bed", "qty": 2}], "sideboard": [],
    })
    save({
        "game": "mtg", "name": "Mono-Red", "archetype": "Aggro",
        "colors": ["R"], "description": "",
        "mainboard": [{"card": "Lightning Bolt", "qty": 4}], "sideboard": [],
    })

    mtg_only = client.get("/api/deckbuilder/decks", params={"game": "mtg"}).json()
    mc_only = client.get("/api/deckbuilder/decks", params={"game": "minecraft"}).json()
    all_decks = client.get("/api/deckbuilder/decks").json()

    assert {d["name"] for d in mtg_only["decks"]} == {"Mono-Red"}
    assert {d["name"] for d in mc_only["decks"]} == {"Bed Stack"}
    assert {d["name"] for d in all_decks["decks"]} == {"Mono-Red", "Bed Stack"}


def test_unknown_game_falls_back_to_mtg():
    """Unknown game ids normalize to mtg so the API doesn't 500."""
    r = client.get("/api/deckbuilder/cards/all", params={"game": "tarot", "limit": 1})
    assert r.status_code == 200
    body = r.json()
    # Returns MTG pool size, not zero
    assert body["total"] == len(gr.get_card_pool("mtg"))


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
