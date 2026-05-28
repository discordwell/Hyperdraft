"""
Explicit ATK/DEF lord swing tests for the Beyond Kamigawa YGO set.

Background — the /test-interceptors audit flagged several lord cards (Konda's
Banner-Bearer, Mothrider Samurai, Brothers Yamazaki, Hand of Honor, Hand of
Cruelty, Otawara Imperial Stronghold, The Wandering Emperor) as "interceptor
registered but no events emitted". The audit heuristic was wrong: lord ATK
swings flow through QUERY_POWER TRANSFORM interceptors at READ time — they
never emit pipeline events.

However, while validating this we found a REAL bug: ``yugioh_combat.py`` and
``yugioh_turn.py`` were reading ATK/DEF directly from ``card_def.atk`` /
``card_def.def_val``, bypassing the QUERY_POWER interceptors entirely. So
while the interceptors were correctly registered, they had no observable
effect during combat. Fixed by routing combat through ``get_ygo_atk`` /
``get_ygo_def`` (src/engine/yugioh_helpers.py).

This test suite covers the correct read pattern (effective ATK via
``get_ygo_atk``) for every lord-style card flagged in the audit, plus a
combat-integration test that shows the boosts actually decide damage.

Run directly:

    python tests/test_ygo_lord_atk_swings.py
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ != "__main__":
    import pytest
    pytest.skip("Run directly: `python tests/test_ygo_lord_atk_swings.py`",
                allow_module_level=True)


from src.engine.game import Game
from src.engine.types import ZoneType
from src.engine.yugioh_helpers import get_ygo_atk, get_ygo_def

from src.cards.yugioh.beyond.kamigawa.samurai import (
    HAND_OF_HONOR, HAND_OF_CRUELTY,
    KONDAS_BANNER_BEARER, MOTHRIDER_SAMURAI, BROTHERS_YAMAZAKI,
    OTAWARA_IMPERIAL_STRONGHOLD, THE_WANDERING_EMPEROR,
    ISAMARU_HOUND_OF_KONDA, RONIN_HOUNDMASTER, SOKENZAN_RENEGADE,
)


# =============================================================================
# Mini-harness — keep wholly self-contained so the suite runs as a script
# =============================================================================

_results = {'passed': 0, 'failed': 0, 'failures': []}


def check(name: str, condition: bool, hint: str = ""):
    if condition:
        _results['passed'] += 1
        print(f"  PASS: {name}")
    else:
        _results['failed'] += 1
        _results['failures'].append(name)
        print(f"  FAIL: {name}" + (f"  ({hint})" if hint else ""))


def make_game():
    g = Game(mode="yugioh")
    p1 = g.add_player("p1")
    p2 = g.add_player("p2")
    return g, p1, p2


def place(g, card_def, player, zone=ZoneType.MONSTER_ZONE):
    return g.create_object(
        card_def.name, player.id, zone,
        copy.deepcopy(card_def.characteristics), card_def,
    )


# =============================================================================
# Test 1 — Hand of Honor (Bushido lord, +200 ATK while another Samurai exists)
# =============================================================================

print("\n=== Test 1: Hand of Honor (Bushido +200 ATK self-boost) ===")

# Solo: no other Samurai → no boost.
g, p1, _ = make_game()
honor = place(g, HAND_OF_HONOR, p1)
check("Hand of Honor solo == 1700 (printed)",
      get_ygo_atk(honor, g.state) == 1700,
      f"got {get_ygo_atk(honor, g.state)}")

# Pair: HAND_OF_HONOR sees HAND_OF_CRUELTY as another Samurai → +200.
g, p1, _ = make_game()
honor = place(g, HAND_OF_HONOR, p1)
cruelty = place(g, HAND_OF_CRUELTY, p1)
check("Hand of Honor + Hand of Cruelty: Honor == 1900 (1700+200 bushido)",
      get_ygo_atk(honor, g.state) == 1900,
      f"got {get_ygo_atk(honor, g.state)}")
check("Hand of Cruelty also gets symmetric bushido pump (1900)",
      get_ygo_atk(cruelty, g.state) == 1900,
      f"got {get_ygo_atk(cruelty, g.state)}")


# =============================================================================
# Test 2 — Konda's Banner-Bearer (team-lord, +200 ATK to OTHER Samurai only)
# =============================================================================

print("\n=== Test 2: Konda's Banner-Bearer team-lord ===")

g, p1, _ = make_game()
banner = place(g, KONDAS_BANNER_BEARER, p1)
check("Banner-Bearer solo == 1500 (doesn't pump self)",
      get_ygo_atk(banner, g.state) == 1500,
      f"got {get_ygo_atk(banner, g.state)}")

# Add a Samurai (Hand of Honor): Banner-Bearer stays at 1500 (affect_self=False);
# Honor jumps to 1700 + 200 (Banner-Bearer team lord) + 200 (own bushido sees Banner) = 2100.
honor = place(g, HAND_OF_HONOR, p1)
check("Banner-Bearer with 1 ally still == 1500 (no self-pump)",
      get_ygo_atk(banner, g.state) == 1500,
      f"got {get_ygo_atk(banner, g.state)}")
check("Hand of Honor under Banner-Bearer == 2100 (1700+200 banner +200 bushido)",
      get_ygo_atk(honor, g.state) == 2100,
      f"got {get_ygo_atk(honor, g.state)}")

# Add a second Samurai (Hand of Cruelty). ``make_bushido`` is
# ``make_archetype_lord(atk_bonus=200)`` which scales PER OTHER. With Banner
# + Cruelty on field, Honor's own bushido counts 2 other Samurai → +400. Plus
# Banner-Bearer's team-lord adds +200. So Honor: 1700 + 400 + 200 = 2300.
cruelty = place(g, HAND_OF_CRUELTY, p1)
check("Hand of Honor w/ Banner + Cruelty == 2300 (1700 + 400 bushido + 200 banner)",
      get_ygo_atk(honor, g.state) == 2300,
      f"got {get_ygo_atk(honor, g.state)}")
check("Hand of Cruelty under Banner-Bearer == 2300 (symmetric)",
      get_ygo_atk(cruelty, g.state) == 2300,
      f"got {get_ygo_atk(cruelty, g.state)}")


# =============================================================================
# Test 3 — Brothers Yamazaki (no ATK swing; effect is destruction prevention)
# =============================================================================

print("\n=== Test 3: Brothers Yamazaki (no ATK swing, prevent battle destroy) ===")

g, p1, _ = make_game()
b1 = place(g, BROTHERS_YAMAZAKI, p1)
check("Brothers Yamazaki solo == 1800",
      get_ygo_atk(b1, g.state) == 1800,
      f"got {get_ygo_atk(b1, g.state)}")

b2 = place(g, BROTHERS_YAMAZAKI, p1)
check("Brothers Yamazaki x2 == 1800 each (no ATK pump, just battle protection)",
      get_ygo_atk(b1, g.state) == 1800 and get_ygo_atk(b2, g.state) == 1800,
      f"got {get_ygo_atk(b1, g.state)}, {get_ygo_atk(b2, g.state)}")
# Note: the protection interceptor IS registered (verified in test_beyond_kamigawa).
# This test confirms the audit's "ATK swing" claim is wrong for Brothers Yamazaki.


# =============================================================================
# Test 4 — Mothrider Samurai (+1500 ATK during damage step vs Lv 5+)
# =============================================================================

print("\n=== Test 4: Mothrider Samurai (battle-conditional +1500 ATK vs Lv5+) ===")

g, p1, _ = make_game()
mothrider = place(g, MOTHRIDER_SAMURAI, p1)
check("Mothrider Samurai alone == 1500 (no battle context)",
      get_ygo_atk(mothrider, g.state) == 1500,
      f"got {get_ygo_atk(mothrider, g.state)}")

# Battle vs Lv 4: still no pump.
g, p1, p2 = make_game()
mothrider = place(g, MOTHRIDER_SAMURAI, p1)
lv4_opp = place(g, HAND_OF_HONOR, p2)  # Lv 4
check("Mothrider vs Lv4 opponent == 1500 (no pump)",
      get_ygo_atk(mothrider, g.state, battle_opponent_id=lv4_opp.id) == 1500,
      f"got {get_ygo_atk(mothrider, g.state, battle_opponent_id=lv4_opp.id)}")

# Battle vs Lv 5+: +1500 ATK.
g, p1, p2 = make_game()
mothrider = place(g, MOTHRIDER_SAMURAI, p1)
lv5_opp = place(g, THE_WANDERING_EMPEROR, p2)  # rank 4 Xyz — has level == 4
# Need an actual Lv 5+. Use a Synchro/large body. Construct a fake Lv6:
from src.cards.yugioh.beyond.kamigawa.samurai import HEIKO_YAMAZAKI  # Lv 6
g, p1, p2 = make_game()
mothrider = place(g, MOTHRIDER_SAMURAI, p1)
lv6_opp = place(g, HEIKO_YAMAZAKI, p2)
check("Mothrider vs Lv6 opponent == 3000 (1500+1500 damage-step pump)",
      get_ygo_atk(mothrider, g.state, battle_opponent_id=lv6_opp.id) == 3000,
      f"got {get_ygo_atk(mothrider, g.state, battle_opponent_id=lv6_opp.id)}")


# =============================================================================
# Test 5 — Otawara Imperial Stronghold (Link, +500/+500 per Samurai per archetype_lord)
# =============================================================================

print("\n=== Test 5: Otawara Imperial Stronghold (+500/+500 archetype_lord) ===")

g, p1, _ = make_game()
oto = place(g, OTAWARA_IMPERIAL_STRONGHOLD, p1)
check("Otawara solo == 1900 (no other Samurai → no pump)",
      get_ygo_atk(oto, g.state) == 1900,
      f"got {get_ygo_atk(oto, g.state)}")

# With one Samurai: Otawara gets +500 ATK / +500 DEF (per other count).
ally = place(g, HAND_OF_HONOR, p1)
check("Otawara + 1 ally Samurai == 2400 ATK (1900+500)",
      get_ygo_atk(oto, g.state) == 2400,
      f"got {get_ygo_atk(oto, g.state)}")
check("Otawara + 1 ally Samurai == 500 DEF (0+500)",
      get_ygo_def(oto, g.state) == 500,
      f"got {get_ygo_def(oto, g.state)}")


# =============================================================================
# Test 6 — Isamaru, Hand of Honor's small-body bushido (+400)
# =============================================================================

print("\n=== Test 6: Isamaru bushido +400 with another Samurai ===")

g, p1, _ = make_game()
isamaru = place(g, ISAMARU_HOUND_OF_KONDA, p1)
check("Isamaru solo == 800",
      get_ygo_atk(isamaru, g.state) == 800,
      f"got {get_ygo_atk(isamaru, g.state)}")

ally = place(g, HAND_OF_HONOR, p1)
check("Isamaru with 1 other Samurai == 1200 (800+400 bushido)",
      get_ygo_atk(isamaru, g.state) == 1200,
      f"got {get_ygo_atk(isamaru, g.state)}")


# =============================================================================
# Test 7 — Ronin Houndmaster bushido (+300)
# =============================================================================

print("\n=== Test 7: Ronin Houndmaster bushido +300 ===")

g, p1, _ = make_game()
ronin = place(g, RONIN_HOUNDMASTER, p1)
check("Ronin solo == 1900",
      get_ygo_atk(ronin, g.state) == 1900,
      f"got {get_ygo_atk(ronin, g.state)}")

ally = place(g, HAND_OF_HONOR, p1)
check("Ronin with 1 other Samurai == 2200 (1900+300)",
      get_ygo_atk(ronin, g.state) == 2200,
      f"got {get_ygo_atk(ronin, g.state)}")


# =============================================================================
# Test 8 — Sokenzan Renegade bushido (+200)
# =============================================================================

print("\n=== Test 8: Sokenzan Renegade bushido +200 ===")

g, p1, _ = make_game()
sok = place(g, SOKENZAN_RENEGADE, p1)
check("Sokenzan solo == 1900",
      get_ygo_atk(sok, g.state) == 1900,
      f"got {get_ygo_atk(sok, g.state)}")

ally = place(g, HAND_OF_HONOR, p1)
check("Sokenzan with 1 other Samurai == 2100 (1900+200)",
      get_ygo_atk(sok, g.state) == 2100,
      f"got {get_ygo_atk(sok, g.state)}")


# =============================================================================
# Test 9 — Combat integration: lord boost actually decides damage
# =============================================================================

print("\n=== Test 9: Combat uses effective ATK (lord boost wins fight) ===")

from src.engine.yugioh_combat import YugiohCombatManager
from src.engine.yugioh_types import YGOPosition

g, p1, p2 = make_game()
# Hand of Honor is 1700 — alone it ties an opponent with 1700.
# With Cruelty as ally, it becomes 1900 — now wins vs 1700.
honor = place(g, HAND_OF_HONOR, p1)
cruelty = place(g, HAND_OF_CRUELTY, p1)
honor.state.ygo_position = 'face_up_atk'
honor.state.face_down = False
cruelty.state.ygo_position = 'face_up_atk'
cruelty.state.face_down = False
# Opponent has Mothrider Samurai (1500 base) face-up ATK.
opp = place(g, MOTHRIDER_SAMURAI, p2)
opp.state.ygo_position = 'face_up_atk'
opp.state.face_down = False

# Combat: Honor (1900 effective) vs opp (1500). Honor wins, opp destroyed, 400 dmg.
combat = YugiohCombatManager(g.state)
combat.state = g.state
p2_lp_before = g.state.players[p2.id].lp
_events = combat.resolve_attack(p1.id, honor.id, opp.id, p2.id)
p2_lp_after = g.state.players[p2.id].lp

# Find opponent in graveyard.
opp_gy = g.state.zones.get(f"graveyard_{p2.id}")
assert opp_gy is not None
opp_in_gy = opp.id in opp_gy.objects
check("Combat: lord-boosted Honor destroys raw Mothrider (1900 > 1500)",
      opp_in_gy,
      "opp should be in graveyard")
check("Combat: 400 LP dealt to p2 (1900-1500)",
      p2_lp_before - p2_lp_after == 400,
      f"got delta {p2_lp_before - p2_lp_after}")


# =============================================================================
# Test 10 — Without ally: same Honor vs Mothrider only does 200 LP (no lord)
# =============================================================================

print("\n=== Test 10: Without lord support, Honor only beats Mothrider by 200 ===")

g, p1, p2 = make_game()
honor = place(g, HAND_OF_HONOR, p1)  # solo: 1700
honor.state.ygo_position = 'face_up_atk'
honor.state.face_down = False
opp = place(g, MOTHRIDER_SAMURAI, p2)  # 1500
opp.state.ygo_position = 'face_up_atk'
opp.state.face_down = False

combat = YugiohCombatManager(g.state)
combat.state = g.state
p2_lp_before = g.state.players[p2.id].lp
combat.resolve_attack(p1.id, honor.id, opp.id, p2.id)
p2_lp_after = g.state.players[p2.id].lp

check("Combat: solo Honor (1700) beats Mothrider (1500) by 200 LP",
      p2_lp_before - p2_lp_after == 200,
      f"got delta {p2_lp_before - p2_lp_after}")


# =============================================================================
# Summary
# =============================================================================

print()
print("=" * 60)
print(f"PASSED: {_results['passed']}    FAILED: {_results['failed']}")
if _results['failures']:
    for name in _results['failures']:
        print(f"  - {name}")
print("=" * 60)

if _results['failed']:
    sys.exit(1)
