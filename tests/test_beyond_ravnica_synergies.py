"""Beyond Ravnica Pokemon synergy-package checks."""

from src.cards.pokemon.beyond.ravnica import (
    BRV_SYNERGY_PACKAGES,
    GUILD_REGISTRIES,
    brv_synergy_package_errors,
)


def test_brv_synergy_packages_are_well_formed():
    assert brv_synergy_package_errors() == []


def test_brv_synergy_packages_cover_each_guild_ex():
    expected_focals = set()
    for registry in GUILD_REGISTRIES.values():
        for card in registry.values():
            if card.is_ex:
                expected_focals.add(card.name)

    assert set(BRV_SYNERGY_PACKAGES) == expected_focals


def test_brv_synergy_packages_include_resource_support():
    for focal, partners in BRV_SYNERGY_PACKAGES.items():
        focal_guild = focal.split(",", 1)[0].split(" ex", 1)[0]
        assert any(
            "Cluestone" in partner or "Signet" in partner
            for partner in partners
        ), focal_guild
        assert any("Blend Energy" in partner for partner in partners), focal_guild
