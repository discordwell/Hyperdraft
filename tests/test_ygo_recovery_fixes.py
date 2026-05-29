"""
Regression tests for two engine bugs found in the post-recovery code review of
the interceptor-fix campaign (src/engine/yugioh_helpers.py):

1. get_ygo_atk / get_ygo_def did not floor effective ATK/DEF at 0, so a monster
   drained below 0 ATK would HEAL the defender on a direct attack.
2. add_from_gy_to_hand mutated the hand (and obj.zone) BEFORE its "card not
   found in any zone" guard, fabricating a phantom hand card while reporting
   (via an empty return) that nothing happened.

Run directly:  python tests/test_ygo_recovery_fixes.py
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ != "__main__":
    import pytest
    pytest.skip("Run directly: `python tests/test_ygo_recovery_fixes.py`",
                allow_module_level=True)


from src.engine.game import Game
from src.engine.types import ZoneType, EventType
from src.engine.yugioh_helpers import get_ygo_atk, add_from_gy_to_hand
from src.cards.yugioh.beyond.kamigawa.samurai import HAND_OF_HONOR


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
# Fix 1 — get_ygo_atk floors effective ATK at 0 (assertions robust to base ATK)
# =============================================================================
print("\n=== Fix 1: get_ygo_atk floors at 0 ===")
g, p1, _ = make_game()
m = place(g, HAND_OF_HONOR, p1)
base = get_ygo_atk(m, g.state)
check("baseline effective ATK is positive", base > 0, f"got {base}")

# partial drain (stays positive) — no flooring should occur
m.state.atk_bonus_eot = -(base // 2)
check("partial drain does NOT floor",
      get_ygo_atk(m, g.state) == base - (base // 2),
      f"got {get_ygo_atk(m, g.state)}, expected {base - (base // 2)}")

# over-drain below zero — must floor at 0, never negative
m.state.atk_bonus_eot = -(base + 1000)
check("over-drain floors at 0 (not negative)",
      get_ygo_atk(m, g.state) == 0,
      f"got {get_ygo_atk(m, g.state)}")


# =============================================================================
# Fix 2 — add_from_gy_to_hand guards before mutating (no phantom hand card)
# =============================================================================
print("\n=== Fix 2: add_from_gy_to_hand guards before mutating ===")
g, p1, _ = make_game()
orphan = place(g, HAND_OF_HONOR, p1, ZoneType.GRAVEYARD)
hand = g.state.zones[f"hand_{p1.id}"]
# Make it an orphan: present in state.objects but in NO zone.
for z in g.state.zones.values():
    while orphan.id in z.objects:
        z.objects.remove(orphan.id)
hand_before = list(hand.objects)
evs = add_from_gy_to_hand(g.state, p1.id, orphan.id)
check("orphan card_id -> returns no event", evs == [], f"got {evs}")
check("orphan card_id -> NOT appended to hand (no phantom card)",
      orphan.id not in hand.objects and hand.objects == hand_before)


# =============================================================================
# Fix 2b — a genuine GY->hand recovery still works (no behavior regression)
# =============================================================================
print("\n=== Fix 2b: real GY -> hand recovery still works ===")
g, p1, _ = make_game()
c = place(g, HAND_OF_HONOR, p1, ZoneType.GRAVEYARD)
gy = g.state.zones[f"graveyard_{p1.id}"]
hand = g.state.zones[f"hand_{p1.id}"]
check("setup: card is in GY", c.id in gy.objects)
evs = add_from_gy_to_hand(g.state, p1.id, c.id)
check("real recovery -> card now in hand", c.id in hand.objects)
check("real recovery -> card left the GY", c.id not in gy.objects)
check("real recovery -> emits exactly one YGO_DRAW event",
      len(evs) == 1 and evs[0].type == EventType.YGO_DRAW,
      f"got {[e.type.name for e in evs]}")


if __name__ == "__main__":
    print(f"\n{'='*52}")
    print(f"RESULTS: {_results['passed']} pass / {_results['failed']} fail")
    if _results['failures']:
        print("FAILURES: " + ", ".join(_results['failures']))
    print('='*52)
    sys.exit(1 if _results['failed'] else 0)
