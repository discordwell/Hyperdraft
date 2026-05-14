"""
Phase 5b card-migration smoke test for the Universes Beyond MTG sets
(SPM, TLA, FIN).

Per-set spells that consume the ``targets`` parameter in their resolve_fn
should declare ``target_requirements`` so the priority system can emit a
PendingChoice when the cast arrives without pre-supplied targets.

This file does not exercise the full cast pipeline (that's covered by
``test_phase5b_cast_target_choice.py``); it asserts the declarative
contract: each migrated card's ``CardDefinition.target_requirements`` is a
non-empty list of ``TargetRequirement`` instances shaped per the card text.
Cards that were intentionally skipped (modal, divide-damage, exotic, or
resolve creates its own internal choice) are asserted to NOT carry a
target_requirements declaration so the audit stays honest.
"""

import importlib.util
import os
import sys

# Make project root importable regardless of where pytest runs from.
# tests/test_engine.py prepends ``/Users/discordwell/Projects/Hyperdraft`` to
# sys.path at import time. On a case-insensitive macOS filesystem that path
# is sibling to (but a distinct directory from) this worktree's project
# root, so any ``src.cards.*`` modules imported via the main path become
# cached and our worktree changes become invisible.
#
# Instead of fighting the package cache, we load each card module directly
# from THIS worktree's filesystem path and stash the loaded module under a
# local alias. The test functions then reference that alias.
_WORKTREE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _load_local_module(rel_path: str, alias: str):
    """Load a Python file directly from disk, bypassing the import cache."""
    full = os.path.join(_WORKTREE_ROOT, rel_path)
    spec = importlib.util.spec_from_file_location(alias, full)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


# Engine modules are stable across worktree boundaries — import them
# normally. Card modules are the ones we need pinned to our worktree.
if _WORKTREE_ROOT not in sys.path:
    sys.path.insert(0, _WORKTREE_ROOT)

from src.engine import CardType, ZoneType  # noqa: E402
from src.engine.targeting import TargetRequirement  # noqa: E402

# Pinned-to-worktree card modules.
_spm = _load_local_module(
    "src/cards/spider_man.py", "_ub_migration_spm"
)
_tla = _load_local_module(
    "src/cards/avatar_tla.py", "_ub_migration_tla"
)
_fin = _load_local_module(
    "src/cards/final_fantasy.py", "_ub_migration_fin"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require(card_def, *, count=None, count_type='exactly',
             types=None, zones=None, controller=None,
             includes_players=None):
    """Assert a card declares the expected single target requirement."""
    reqs = getattr(card_def, 'target_requirements', None)
    assert reqs, f"{card_def.name}: expected target_requirements, got {reqs!r}"
    assert all(isinstance(r, TargetRequirement) for r in reqs), \
        f"{card_def.name}: every requirement must be a TargetRequirement"
    if count is not None:
        # If count is a list/tuple, validate per requirement.
        if isinstance(count, (list, tuple)):
            assert len(reqs) == len(count), \
                f"{card_def.name}: expected {len(count)} requirements, got {len(reqs)}"
            for i, c in enumerate(count):
                assert reqs[i].count == c, \
                    f"{card_def.name}[{i}]: count={reqs[i].count} != {c}"
        else:
            assert len(reqs) == 1, \
                f"{card_def.name}: expected 1 requirement, got {len(reqs)}"
            assert reqs[0].count == count, \
                f"{card_def.name}: count={reqs[0].count} != {count}"
    if count_type is not None and not isinstance(count, (list, tuple)):
        assert reqs[0].count_type == count_type, \
            f"{card_def.name}: count_type={reqs[0].count_type} != {count_type}"
    if types is not None:
        actual = reqs[0].filter.types
        assert actual == types, \
            f"{card_def.name}: filter.types={actual} != {types}"
    if zones is not None:
        actual = reqs[0].filter.zones
        assert actual == zones, \
            f"{card_def.name}: filter.zones={actual} != {zones}"
    if controller is not None:
        actual = reqs[0].filter.controller
        assert actual == controller, \
            f"{card_def.name}: filter.controller={actual} != {controller}"
    if includes_players is not None:
        actual = reqs[0].filter.includes_players
        assert actual == includes_players, \
            f"{card_def.name}: filter.includes_players={actual} != {includes_players}"


def _no_requirements(card_def):
    """Assert a card was NOT migrated (modal, exotic, or self-targeting)."""
    reqs = getattr(card_def, 'target_requirements', None)
    assert not reqs, \
        f"{card_def.name}: did not expect target_requirements, got {reqs!r}"


# ---------------------------------------------------------------------------
# SPM (Spider-Man)
# ---------------------------------------------------------------------------

def test_spm_villainous_wrath_targets_opponent():
    spm = _spm
    reqs = spm.VILLAINOUS_WRATH.target_requirements
    assert reqs and len(reqs) == 1
    f = reqs[0].filter
    # target opponent => player_filter(controller='opponent')
    # player_filter sets types=None and zones=[]
    assert f.types is None, f"player target requires types=None, got {f.types}"
    assert f.controller == 'opponent'
    assert reqs[0].count == 1


def test_spm_modal_spells_remain_unmigrated():
    """Modal spells (Choose one) handle target picking inside their mode
    functions, so the card-level target_requirements stays None."""
    spm = _spm
    for card in (spm.SPECTACULAR_TACTICS, spm.SCHOOL_DAZE,
                 spm.SECRET_IDENTITY, spm.HEROES_HANGOUT,
                 spm.SCOUT_THE_CITY):
        _no_requirements(card)


# ---------------------------------------------------------------------------
# TLA (Avatar)
# ---------------------------------------------------------------------------

def test_tla_resolves_use_internal_target_choices_no_migration():
    """All TLA resolve_fns create their own PendingChoice via
    ``create_target_choice``; none consume the ``targets`` parameter, so
    none qualify for Phase 5b declarative migration in this batch.
    """
    tla = _tla
    for card in (tla.ENTER_THE_AVATAR_STATE, tla.OCTOPUS_FORM,
                 tla.PILLAR_LAUNCH, tla.COMBUSTION_TECHNIQUE,
                 tla.THE_LAST_AGNI_KAI, tla.ALLIES_AT_LAST,
                 tla.ROCKY_REBUKE, tla.SPIRIT_WATER_REVIVAL,
                 tla.HEARTLESS_ACT, tla.SEISMIC_SENSE,
                 tla.FIRE_NATION_ATTACKS, tla.ACCUMULATE_WISDOM,
                 tla.DAY_OF_BLACK_SUN, tla.AIRBENDERS_REVERSAL):
        _no_requirements(card)


# ---------------------------------------------------------------------------
# FIN (Final Fantasy)
# ---------------------------------------------------------------------------

def test_fin_slash_of_light_targets_creature():
    fin = _fin
    _require(fin.SLASH_OF_LIGHT, count=1, types={CardType.CREATURE})


def test_fin_magic_damper_targets_own_creature():
    fin = _fin
    _require(fin.MAGIC_DAMPER, count=1, types={CardType.CREATURE},
             controller='you')


def test_fin_evil_reawakened_targets_graveyard_creature():
    fin = _fin
    _require(fin.EVIL_REAWAKENED, count=1,
             types={CardType.CREATURE},
             zones=[ZoneType.GRAVEYARD],
             controller='you')


def test_fin_fight_on_targets_up_to_two_graveyard_creatures():
    fin = _fin
    reqs = fin.FIGHT_ON.target_requirements
    assert reqs and len(reqs) == 1
    r = reqs[0]
    assert r.count == 2
    assert r.count_type == 'up_to'
    assert r.filter.types == {CardType.CREATURE}
    assert r.filter.zones == [ZoneType.GRAVEYARD]
    assert r.filter.controller == 'you'


def test_fin_haste_magic_targets_creature():
    fin = _fin
    _require(fin.HASTE_MAGIC, count=1, types={CardType.CREATURE})


def test_fin_nibelheim_aflame_targets_own_creature():
    fin = _fin
    _require(fin.NIBELHEIM_AFLAME, count=1, types={CardType.CREATURE},
             controller='you')


def test_fin_blitzball_shot_targets_creature():
    fin = _fin
    _require(fin.BLITZBALL_SHOT, count=1, types={CardType.CREATURE})


def test_fin_chocobo_kick_targets_own_and_opponent_creature():
    fin = _fin
    reqs = fin.CHOCOBO_KICK.target_requirements
    assert reqs and len(reqs) == 2
    # First req: target your creature
    assert reqs[0].filter.types == {CardType.CREATURE}
    assert reqs[0].filter.controller == 'you'
    assert reqs[0].count == 1
    # Second req: target opponent's creature
    assert reqs[1].filter.types == {CardType.CREATURE}
    assert reqs[1].filter.controller == 'opponent'
    assert reqs[1].count == 1


def test_fin_skip_flags_modal_exotic_and_internal_choice():
    """Skipped FIN cards must NOT carry target_requirements:
    - Modal (Aerith Rescue Mission, Battle Menu, Poison the Waters,
      Opera Love Song, Suplex, Rydia's Return)
    - Tiered (Restoration Magic, Ice Magic, Vincent's Limit Break,
      Fire Magic, Thunder Magic, Tifa's Limit Break)
    - Exotic / internal target choice: Self-Destruct ("another target"
      cross-exclusion not modelled), Louisoix's Sacrifice (target
      activated/triggered ability — ability targeting not supported),
      Reach the Horizon / From Father to Son / Commune with Beavers
      (library searches, no spell-target involved).

    Note: UNEXPECTED_REQUEST was migrated in Phase 5b follow-up to use
    ``target_requirements=[target_creature(controller='opponent')]``.
    """
    fin = _fin
    skipped = [
        # Modal
        fin.AERITH_RESCUE_MISSION, fin.BATTLE_MENU,
        fin.POISON_THE_WATERS, fin.OPERA_LOVE_SONG,
        fin.SUPLEX, fin.RYDIAS_RETURN,
        # Tiered
        fin.RESTORATION_MAGIC, fin.ICE_MAGIC,
        fin.VINCENTS_LIMIT_BREAK, fin.FIRE_MAGIC,
        fin.THUNDER_MAGIC, fin.TIFAS_LIMIT_BREAK,
        # Exotic / internal choice
        fin.SELFDESTRUCT, fin.LOUISOIXS_SACRIFICE,
        fin.REACH_THE_HORIZON,
        fin.FROM_FATHER_TO_SON, fin.COMMUNE_WITH_BEAVERS,
    ]
    for card in skipped:
        _no_requirements(card)


if __name__ == "__main__":
    test_spm_villainous_wrath_targets_opponent()
    print("PASS  test_spm_villainous_wrath_targets_opponent")
    test_spm_modal_spells_remain_unmigrated()
    print("PASS  test_spm_modal_spells_remain_unmigrated")
    test_tla_resolves_use_internal_target_choices_no_migration()
    print("PASS  test_tla_resolves_use_internal_target_choices_no_migration")
    test_fin_slash_of_light_targets_creature()
    print("PASS  test_fin_slash_of_light_targets_creature")
    test_fin_magic_damper_targets_own_creature()
    print("PASS  test_fin_magic_damper_targets_own_creature")
    test_fin_evil_reawakened_targets_graveyard_creature()
    print("PASS  test_fin_evil_reawakened_targets_graveyard_creature")
    test_fin_fight_on_targets_up_to_two_graveyard_creatures()
    print("PASS  test_fin_fight_on_targets_up_to_two_graveyard_creatures")
    test_fin_haste_magic_targets_creature()
    print("PASS  test_fin_haste_magic_targets_creature")
    test_fin_nibelheim_aflame_targets_own_creature()
    print("PASS  test_fin_nibelheim_aflame_targets_own_creature")
    test_fin_blitzball_shot_targets_creature()
    print("PASS  test_fin_blitzball_shot_targets_creature")
    test_fin_chocobo_kick_targets_own_and_opponent_creature()
    print("PASS  test_fin_chocobo_kick_targets_own_and_opponent_creature")
    test_fin_skip_flags_modal_exotic_and_internal_choice()
    print("PASS  test_fin_skip_flags_modal_exotic_and_internal_choice")
    print("\nAll Phase 5b UB-migration smoke tests passed.")
