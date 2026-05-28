"""Auto-generated interceptor verification for Naruto: Shinobi Clash.

Verifies every card that was restored from a slice-10 info-pulse stub now
either (a) fires its real effect (impl permanents + jutsu spells) or
(b) is a clean vanilla card with no setup_interceptors (re-stub guard).

See /test-interceptors. Run directly (HYPERDRAFT_STRICT=1 recommended):
    HYPERDRAFT_STRICT=1 python tests/test_naruto_interceptors.py
"""

import sys
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[1].as_posix())

import importlib.util
from pathlib import Path

from src.engine import Game, Event, EventType, ZoneType

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "naruto_cards", str(_ROOT / "src/cards/custom/naruto.py"))
_naruto = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_naruto)
NARUTO_CARDS = _naruto.NARUTO_CARDS

SKIPPED_CARDS = {}  # all 132 restored cards are covered below


class _Tgt:
    """Minimal Target stand-in for resolve-fn unit tests."""
    def __init__(self, tid, is_player):
        self.id = tid
        self.is_player = is_player


def _etb(game, pid, name):
    """Put a card onto the battlefield via ZONE_CHANGE so its ETB fires once."""
    cd = NARUTO_CARDS[name]
    obj = game.create_object(name=name, owner_id=pid, zone=ZoneType.HAND,
                             characteristics=cd.characteristics, card_def=None)
    obj.card_def = cd
    obj.zone = ZoneType.BATTLEFIELD
    game.emit(Event(type=EventType.ZONE_CHANGE,
                    payload={'object_id': obj.id, 'from_zone': f'hand_{pid}',
                             'to_zone': 'battlefield',
                             'from_zone_type': ZoneType.HAND,
                             'to_zone_type': ZoneType.BATTLEFIELD},
                    source=obj.id, controller=pid))
    return obj


def _new_game():
    g = Game()
    p1 = g.add_player("A")
    p2 = g.add_player("B")
    return g, p1, p2


# ---------------------------------------------------------------------------
# IMPL PERMANENTS — ETB effect must change life totals
# ---------------------------------------------------------------------------
def test_perm_curse_of_hatred():
    """Curse of Hatred: etb_lose_life 1 on ETB."""
    g, p1, p2 = _new_game()
    before = p2.life
    _etb(g, p1.id, 'Curse of Hatred')
    assert p2.life == before - 1, f"Curse of Hatred: expected opp -1 life, got {before - p2.life}"

def test_perm_explosive_tag_ninja():
    """Explosive Tag Ninja: etb_deal_damage 2 on ETB."""
    g, p1, p2 = _new_game()
    before = p2.life
    _etb(g, p1.id, 'Explosive Tag Ninja')
    assert p2.life == before - 2, f"Explosive Tag Ninja: expected opp -2 from damage, got {before - p2.life}"

def test_perm_rage_filled_jinchuriki():
    """Rage-Filled Jinchuriki: etb_deal_damage 2 on ETB."""
    g, p1, p2 = _new_game()
    before = p2.life
    _etb(g, p1.id, 'Rage-Filled Jinchuriki')
    assert p2.life == before - 2, f"Rage-Filled Jinchuriki: expected opp -2 from damage, got {before - p2.life}"

def test_perm_battle_frenzy():
    """Battle Frenzy: etb_deal_damage 1 on ETB."""
    g, p1, p2 = _new_game()
    before = p2.life
    _etb(g, p1.id, 'Battle Frenzy')
    assert p2.life == before - 1, f"Battle Frenzy: expected opp -1 from damage, got {before - p2.life}"

def test_perm_scroll_of_sealing():
    """Scroll of Sealing: etb_lose_life 1 on ETB."""
    g, p1, p2 = _new_game()
    before = p2.life
    _etb(g, p1.id, 'Scroll of Sealing')
    assert p2.life == before - 1, f"Scroll of Sealing: expected opp -1 life, got {before - p2.life}"

def test_perm_chakra_pills():
    """Chakra Pills: etb_gain_life 4 on ETB."""
    g, p1, p2 = _new_game()
    before = p1.life
    _etb(g, p1.id, 'Chakra Pills')
    assert p1.life == before + 4, f"Chakra Pills: expected +4 life, got {p1.life - before}"

def test_perm_sharingan_contact():
    """Sharingan Contact: etb_lose_life 1 on ETB."""
    g, p1, p2 = _new_game()
    before = p2.life
    _etb(g, p1.id, 'Sharingan Contact')
    assert p2.life == before - 1, f"Sharingan Contact: expected opp -1 life, got {before - p2.life}"

def test_perm_explosive_tag():
    """Explosive Tag: etb_deal_damage 2 on ETB."""
    g, p1, p2 = _new_game()
    before = p2.life
    _etb(g, p1.id, 'Explosive Tag')
    assert p2.life == before - 2, f"Explosive Tag: expected opp -2 from damage, got {before - p2.life}"

def test_perm_smoke_bomb():
    """Smoke Bomb: etb_lose_life 1 on ETB."""
    g, p1, p2 = _new_game()
    before = p2.life
    _etb(g, p1.id, 'Smoke Bomb')
    assert p2.life == before - 1, f"Smoke Bomb: expected opp -1 life, got {before - p2.life}"

def test_perm_akatsuki_hideout():
    """Akatsuki Hideout: etb_lose_life 1 on ETB."""
    g, p1, p2 = _new_game()
    before = p2.life
    _etb(g, p1.id, 'Akatsuki Hideout')
    assert p2.life == before - 1, f"Akatsuki Hideout: expected opp -1 life, got {before - p2.life}"

def test_perm_training_ground():
    """Training Ground: etb_gain_life 2 on ETB."""
    g, p1, p2 = _new_game()
    before = p1.life
    _etb(g, p1.id, 'Training Ground')
    assert p1.life == before + 2, f"Training Ground: expected +2 life, got {p1.life - before}"

def test_perm_chunin_exam_arena():
    """Chunin Exam Arena: etb_lose_life 1 on ETB."""
    g, p1, p2 = _new_game()
    before = p2.life
    _etb(g, p1.id, 'Chunin Exam Arena')
    assert p2.life == before - 1, f"Chunin Exam Arena: expected opp -1 life, got {before - p2.life}"

def test_perm_susanoo():
    """Susanoo: etb_lose_life 2 on ETB."""
    g, p1, p2 = _new_game()
    before = p2.life
    _etb(g, p1.id, 'Susanoo')
    assert p2.life == before - 2, f"Susanoo: expected opp -2 life, got {before - p2.life}"


# ---------------------------------------------------------------------------
# JUTSU SPELLS — resolve() must emit the expected event type
# ---------------------------------------------------------------------------
def test_spell_konoha_senbon():
    """Konoha Senbon: dmg 1 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Konoha Senbon'].resolve(targets, g.state)
    assert events, f"Konoha Senbon: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Konoha Senbon: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 1, f"Konoha Senbon: expected 1 damage"

def test_spell_amaterasu():
    """Amaterasu: dmg 4 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Amaterasu'].resolve(targets, g.state)
    assert events, f"Amaterasu: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Amaterasu: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 4, f"Amaterasu: expected 4 damage"

def test_spell_fire_ball_jutsu():
    """Fire Ball Jutsu: dmg 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Fire Ball Jutsu'].resolve(targets, g.state)
    assert events, f"Fire Ball Jutsu: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Fire Ball Jutsu: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 3, f"Fire Ball Jutsu: expected 3 damage"

def test_spell_rasengan():
    """Rasengan: dmg 4 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Rasengan'].resolve(targets, g.state)
    assert events, f"Rasengan: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Rasengan: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 4, f"Rasengan: expected 4 damage"

def test_spell_chidori():
    """Chidori: dmg 4 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Chidori'].resolve(targets, g.state)
    assert events, f"Chidori: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Chidori: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 4, f"Chidori: expected 4 damage"

def test_spell_rasenshuriken():
    """Rasenshuriken: dmg 5 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Rasenshuriken'].resolve(targets, g.state)
    assert events, f"Rasenshuriken: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Rasenshuriken: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 5, f"Rasenshuriken: expected 5 damage"

def test_spell_lightning_blade():
    """Lightning Blade: dmg 5 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Lightning Blade'].resolve(targets, g.state)
    assert events, f"Lightning Blade: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Lightning Blade: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 5, f"Lightning Blade: expected 5 damage"

def test_spell_fire_dragon_jutsu():
    """Fire Dragon Jutsu: dmg 5 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Fire Dragon Jutsu'].resolve(targets, g.state)
    assert events, f"Fire Dragon Jutsu: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Fire Dragon Jutsu: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 5, f"Fire Dragon Jutsu: expected 5 damage"

def test_spell_explosive_kunai():
    """Explosive Kunai: dmg 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Explosive Kunai'].resolve(targets, g.state)
    assert events, f"Explosive Kunai: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Explosive Kunai: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 2, f"Explosive Kunai: expected 2 damage"

def test_spell_lariat():
    """Lariat: dmg 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Lariat'].resolve(targets, g.state)
    assert events, f"Lariat: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Lariat: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 3, f"Lariat: expected 3 damage"

def test_spell_wind_enhanced_rasengan():
    """Wind-Enhanced Rasengan: dmg 5 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Wind-Enhanced Rasengan'].resolve(targets, g.state)
    assert events, f"Wind-Enhanced Rasengan: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Wind-Enhanced Rasengan: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 5, f"Wind-Enhanced Rasengan: expected 5 damage"

def test_spell_planetary_rasengan():
    """Planetary Rasengan: dmg 6 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Planetary Rasengan'].resolve(targets, g.state)
    assert events, f"Planetary Rasengan: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Planetary Rasengan: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 6, f"Planetary Rasengan: expected 6 damage"

def test_spell_frog_kumite():
    """Frog Kumite: dmg 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Frog Kumite'].resolve(targets, g.state)
    assert events, f"Frog Kumite: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Frog Kumite: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 3, f"Frog Kumite: expected 3 damage"

def test_spell_sannin_showdown():
    """Sannin Showdown: dmg 4 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Sannin Showdown'].resolve(targets, g.state)
    assert events, f"Sannin Showdown: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Sannin Showdown: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 4, f"Sannin Showdown: expected 4 damage"

def test_spell_eight_gates_release():
    """Eight Gates Release: dmg 4 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Eight Gates Release'].resolve(targets, g.state)
    assert events, f"Eight Gates Release: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Eight Gates Release: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 4, f"Eight Gates Release: expected 4 damage"

def test_spell_multi_shadow_clone_jutsu():
    """Multi Shadow Clone Jutsu: dmg 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Multi Shadow Clone Jutsu'].resolve(targets, g.state)
    assert events, f"Multi Shadow Clone Jutsu: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Multi Shadow Clone Jutsu: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 3, f"Multi Shadow Clone Jutsu: expected 3 damage"

def test_spell_burning_will():
    """Burning Will: dmg 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Burning Will'].resolve(targets, g.state)
    assert events, f"Burning Will: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Burning Will: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 3, f"Burning Will: expected 3 damage"

def test_spell_final_valley_battle():
    """Final Valley Battle: dmg 5 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Final Valley Battle'].resolve(targets, g.state)
    assert events, f"Final Valley Battle: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Final Valley Battle: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 5, f"Final Valley Battle: expected 5 damage"

def test_spell_healing_jutsu():
    """Healing Jutsu: heal 5 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = []
    events = NARUTO_CARDS['Healing Jutsu'].resolve(targets, g.state)
    assert events, f"Healing Jutsu: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Healing Jutsu: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 5, f"Healing Jutsu: expected +5 life"

def test_spell_rejuvenation_jutsu():
    """Rejuvenation Jutsu: heal 6 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = []
    events = NARUTO_CARDS['Rejuvenation Jutsu'].resolve(targets, g.state)
    assert events, f"Rejuvenation Jutsu: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Rejuvenation Jutsu: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 6, f"Rejuvenation Jutsu: expected +6 life"

def test_spell_hokage_monument():
    """Hokage Monument: heal 5 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = []
    events = NARUTO_CARDS['Hokage Monument'].resolve(targets, g.state)
    assert events, f"Hokage Monument: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Hokage Monument: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 5, f"Hokage Monument: expected +5 life"

def test_spell_wood_style_wall():
    """Wood Style: Wall: heal 4 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = []
    events = NARUTO_CARDS['Wood Style: Wall'].resolve(targets, g.state)
    assert events, f"Wood Style: Wall: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Wood Style: Wall: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 4, f"Wood Style: Wall: expected +4 life"

def test_spell_sage_training():
    """Sage Training: heal 4 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = []
    events = NARUTO_CARDS['Sage Training'].resolve(targets, g.state)
    assert events, f"Sage Training: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Sage Training: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 4, f"Sage Training: expected +4 life"

def test_spell_natural_rebirth():
    """Natural Rebirth: heal 8 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = []
    events = NARUTO_CARDS['Natural Rebirth'].resolve(targets, g.state)
    assert events, f"Natural Rebirth: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Natural Rebirth: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 8, f"Natural Rebirth: expected +8 life"

def test_spell_substitution_jutsu():
    """Substitution Jutsu: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Substitution Jutsu'].resolve(targets, g.state)
    assert events, f"Substitution Jutsu: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Substitution Jutsu: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Substitution Jutsu: expected opp -2 life"

def test_spell_will_of_fire():
    """Will of Fire: drain 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Will of Fire'].resolve(targets, g.state)
    assert events, f"Will of Fire: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Will of Fire: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -3, f"Will of Fire: expected opp -3 life"

def test_spell_gentle_fist():
    """Gentle Fist: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Gentle Fist'].resolve(targets, g.state)
    assert events, f"Gentle Fist: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Gentle Fist: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Gentle Fist: expected opp -2 life"

def test_spell_eight_trigrams_palm():
    """Eight Trigrams Palm: drain 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Eight Trigrams Palm'].resolve(targets, g.state)
    assert events, f"Eight Trigrams Palm: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Eight Trigrams Palm: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -3, f"Eight Trigrams Palm: expected opp -3 life"

def test_spell_protection_barrier():
    """Protection Barrier: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Protection Barrier'].resolve(targets, g.state)
    assert events, f"Protection Barrier: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Protection Barrier: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Protection Barrier: expected opp -2 life"

def test_spell_village_defense():
    """Village Defense: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Village Defense'].resolve(targets, g.state)
    assert events, f"Village Defense: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Village Defense: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Village Defense: expected opp -2 life"

def test_spell_konoha_reinforcements():
    """Konoha Reinforcements: drain 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Konoha Reinforcements'].resolve(targets, g.state)
    assert events, f"Konoha Reinforcements: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Konoha Reinforcements: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -3, f"Konoha Reinforcements: expected opp -3 life"

def test_spell_hidden_leaf_decree():
    """Hidden Leaf Decree: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Hidden Leaf Decree'].resolve(targets, g.state)
    assert events, f"Hidden Leaf Decree: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Hidden Leaf Decree: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Hidden Leaf Decree: expected opp -2 life"

def test_spell_demonic_illusion():
    """Demonic Illusion: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Demonic Illusion'].resolve(targets, g.state)
    assert events, f"Demonic Illusion: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Demonic Illusion: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Demonic Illusion: expected opp -2 life"

def test_spell_substitution():
    """Substitution: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Substitution'].resolve(targets, g.state)
    assert events, f"Substitution: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Substitution: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Substitution: expected opp -2 life"

def test_spell_water_wall():
    """Water Wall: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Water Wall'].resolve(targets, g.state)
    assert events, f"Water Wall: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Water Wall: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Water Wall: expected opp -2 life"

def test_spell_tsukuyomi():
    """Tsukuyomi: drain 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Tsukuyomi'].resolve(targets, g.state)
    assert events, f"Tsukuyomi: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Tsukuyomi: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -3, f"Tsukuyomi: expected opp -3 life"

def test_spell_soul_extraction():
    """Soul Extraction: drain 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Soul Extraction'].resolve(targets, g.state)
    assert events, f"Soul Extraction: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Soul Extraction: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -3, f"Soul Extraction: expected opp -3 life"

def test_spell_curse_mark_activation():
    """Curse Mark Activation: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Curse Mark Activation'].resolve(targets, g.state)
    assert events, f"Curse Mark Activation: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Curse Mark Activation: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Curse Mark Activation: expected opp -2 life"

def test_spell_death_seal():
    """Death Seal: drain 4 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Death Seal'].resolve(targets, g.state)
    assert events, f"Death Seal: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Death Seal: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -4, f"Death Seal: expected opp -4 life"

def test_spell_shadow_possession():
    """Shadow Possession: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Shadow Possession'].resolve(targets, g.state)
    assert events, f"Shadow Possession: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Shadow Possession: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Shadow Possession: expected opp -2 life"

def test_spell_reaper_death_seal():
    """Reaper Death Seal: drain 5 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Reaper Death Seal'].resolve(targets, g.state)
    assert events, f"Reaper Death Seal: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Reaper Death Seal: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -5, f"Reaper Death Seal: expected opp -5 life"

def test_spell_painful_memories():
    """Painful Memories: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Painful Memories'].resolve(targets, g.state)
    assert events, f"Painful Memories: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Painful Memories: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Painful Memories: expected opp -2 life"

def test_spell_shinra_tensei():
    """Shinra Tensei: drain 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Shinra Tensei'].resolve(targets, g.state)
    assert events, f"Shinra Tensei: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Shinra Tensei: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -3, f"Shinra Tensei: expected opp -3 life"

def test_spell_uchiha_massacre():
    """Uchiha Massacre: drain 4 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Uchiha Massacre'].resolve(targets, g.state)
    assert events, f"Uchiha Massacre: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Uchiha Massacre: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -4, f"Uchiha Massacre: expected opp -4 life"

def test_spell_izanagi():
    """Izanagi: drain 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Izanagi'].resolve(targets, g.state)
    assert events, f"Izanagi: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Izanagi: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -3, f"Izanagi: expected opp -3 life"

def test_spell_summoning_jutsu():
    """Summoning Jutsu: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Summoning Jutsu'].resolve(targets, g.state)
    assert events, f"Summoning Jutsu: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Summoning Jutsu: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Summoning Jutsu: expected opp -2 life"

def test_spell_nature_energy():
    """Nature Energy: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Nature Energy'].resolve(targets, g.state)
    assert events, f"Nature Energy: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Nature Energy: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Nature Energy: expected opp -2 life"

def test_spell_forest_binding():
    """Forest Binding: drain 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Forest Binding'].resolve(targets, g.state)
    assert events, f"Forest Binding: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Forest Binding: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -3, f"Forest Binding: expected opp -3 life"

def test_spell_giant_growth_jutsu():
    """Giant Growth Jutsu: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Giant Growth Jutsu'].resolve(targets, g.state)
    assert events, f"Giant Growth Jutsu: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Giant Growth Jutsu: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Giant Growth Jutsu: expected opp -2 life"

def test_spell_sage_art_awakening():
    """Sage Art: Awakening: drain 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Sage Art: Awakening'].resolve(targets, g.state)
    assert events, f"Sage Art: Awakening: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Sage Art: Awakening: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -3, f"Sage Art: Awakening: expected opp -3 life"

def test_spell_mass_summoning():
    """Mass Summoning: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Mass Summoning'].resolve(targets, g.state)
    assert events, f"Mass Summoning: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Mass Summoning: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Mass Summoning: expected opp -2 life"

def test_spell_wood_style_deep_forest():
    """Wood Style: Deep Forest: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Wood Style: Deep Forest'].resolve(targets, g.state)
    assert events, f"Wood Style: Deep Forest: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Wood Style: Deep Forest: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Wood Style: Deep Forest: expected opp -2 life"

def test_spell_new_generation():
    """New Generation: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['New Generation'].resolve(targets, g.state)
    assert events, f"New Generation: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"New Generation: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"New Generation: expected opp -2 life"

def test_spell_bonds_of_friendship():
    """Bonds of Friendship: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Bonds of Friendship'].resolve(targets, g.state)
    assert events, f"Bonds of Friendship: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Bonds of Friendship: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Bonds of Friendship: expected opp -2 life"

def test_spell_shinobi_war():
    """Shinobi War: drain 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Shinobi War'].resolve(targets, g.state)
    assert events, f"Shinobi War: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Shinobi War: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -3, f"Shinobi War: expected opp -3 life"

def test_spell_infinite_tsukuyomi():
    """Infinite Tsukuyomi: drain 5 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Infinite Tsukuyomi'].resolve(targets, g.state)
    assert events, f"Infinite Tsukuyomi: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Infinite Tsukuyomi: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -5, f"Infinite Tsukuyomi: expected opp -5 life"

def test_spell_talk_no_jutsu():
    """Talk no Jutsu: drain 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Talk no Jutsu'].resolve(targets, g.state)
    assert events, f"Talk no Jutsu: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Talk no Jutsu: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -3, f"Talk no Jutsu: expected opp -3 life"

def test_spell_water_prison_jutsu():
    """Water Prison Jutsu: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Water Prison Jutsu'].resolve(targets, g.state)
    assert events, f"Water Prison Jutsu: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Water Prison Jutsu: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Water Prison Jutsu: expected opp -2 life"

def test_spell_hidden_mist_jutsu():
    """Hidden Mist Jutsu: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Hidden Mist Jutsu'].resolve(targets, g.state)
    assert events, f"Hidden Mist Jutsu: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Hidden Mist Jutsu: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Hidden Mist Jutsu: expected opp -2 life"

def test_spell_water_dragon_jutsu():
    """Water Dragon Jutsu: dmg 3 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Water Dragon Jutsu'].resolve(targets, g.state)
    assert events, f"Water Dragon Jutsu: resolve emitted no events"
    assert events[0].type == EventType.DAMAGE, f"Water Dragon Jutsu: expected DAMAGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 3, f"Water Dragon Jutsu: expected 3 damage"

def test_spell_genjutsu_release():
    """Genjutsu: Release: drain 1 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Genjutsu: Release'].resolve(targets, g.state)
    assert events, f"Genjutsu: Release: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Genjutsu: Release: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -1, f"Genjutsu: Release: expected opp -1 life"

def test_spell_mind_confusion_jutsu():
    """Mind Confusion Jutsu: drain 1 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Mind Confusion Jutsu'].resolve(targets, g.state)
    assert events, f"Mind Confusion Jutsu: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Mind Confusion Jutsu: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -1, f"Mind Confusion Jutsu: expected opp -1 life"

def test_spell_water_style_training():
    """Water Style Training: drain 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = [[_Tgt(p2.id, True)]]
    events = NARUTO_CARDS['Water Style Training'].resolve(targets, g.state)
    assert events, f"Water Style Training: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Water Style Training: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == -2, f"Water Style Training: expected opp -2 life"

def test_spell_clone_jutsu():
    """Clone Jutsu: heal 2 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = []
    events = NARUTO_CARDS['Clone Jutsu'].resolve(targets, g.state)
    assert events, f"Clone Jutsu: resolve emitted no events"
    assert events[0].type == EventType.LIFE_CHANGE, f"Clone Jutsu: expected LIFE_CHANGE, got {events[0].type}"
    assert events[0].payload.get('amount') == 2, f"Clone Jutsu: expected +2 life"

def test_spell_tactical_retreat():
    """Tactical Retreat: draw 1 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = []
    events = NARUTO_CARDS['Tactical Retreat'].resolve(targets, g.state)
    assert events, f"Tactical Retreat: resolve emitted no events"
    assert events[0].type == EventType.DRAW, f"Tactical Retreat: expected DRAW, got {events[0].type}"

def test_spell_edo_tensei():
    """Edo Tensei: draw 1 jutsu resolve."""
    g, p1, p2 = _new_game()
    targets = []
    events = NARUTO_CARDS['Edo Tensei'].resolve(targets, g.state)
    assert events, f"Edo Tensei: resolve emitted no events"
    assert events[0].type == EventType.DRAW, f"Edo Tensei: expected DRAW, got {events[0].type}"


# ---------------------------------------------------------------------------
# VANILLA-REVERTED PERMANENTS — must have NO setup_interceptors (re-stub guard)
# ---------------------------------------------------------------------------
def test_vanilla_nara_shadow_user():
    """Nara Shadow User: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Nara Shadow User']
    assert cd.setup_interceptors is None, f"Nara Shadow User: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_barrier_team_ninja():
    """Barrier Team Ninja: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Barrier Team Ninja']
    assert cd.setup_interceptors is None, f"Barrier Team Ninja: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_konoha_alliance():
    """Konoha Alliance: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Konoha Alliance']
    assert cd.setup_interceptors is None, f"Konoha Alliance: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_shino_aburame():
    """Shino Aburame, Insect Master: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Shino Aburame, Insect Master']
    assert cd.setup_interceptors is None, f"Shino Aburame, Insect Master: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_kiba_inuzuka():
    """Kiba Inuzuka, Fang over Fang: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Kiba Inuzuka, Fang over Fang']
    assert cd.setup_interceptors is None, f"Kiba Inuzuka, Fang over Fang: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_mist_village_ninja():
    """Mist Village Ninja: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Mist Village Ninja']
    assert cd.setup_interceptors is None, f"Mist Village Ninja: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_genjutsu_specialist():
    """Genjutsu Specialist: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Genjutsu Specialist']
    assert cd.setup_interceptors is None, f"Genjutsu Specialist: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_water_clone():
    """Water Clone: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Water Clone']
    assert cd.setup_interceptors is None, f"Water Clone: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_sound_village_spy():
    """Sound Village Spy: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Sound Village Spy']
    assert cd.setup_interceptors is None, f"Sound Village Spy: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_mist_swordsman():
    """Mist Swordsman: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Mist Swordsman']
    assert cd.setup_interceptors is None, f"Mist Swordsman: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_sensor_ninja():
    """Sensor Ninja: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Sensor Ninja']
    assert cd.setup_interceptors is None, f"Sensor Ninja: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_genjutsu_web():
    """Genjutsu Web: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Genjutsu Web']
    assert cd.setup_interceptors is None, f"Genjutsu Web: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_hidden_mist():
    """Hidden Mist: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Hidden Mist']
    assert cd.setup_interceptors is None, f"Hidden Mist: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_zetsu():
    """Zetsu, White and Black: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Zetsu, White and Black']
    assert cd.setup_interceptors is None, f"Zetsu, White and Black: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_curse_mark_bearer():
    """Curse Mark Bearer: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Curse Mark Bearer']
    assert cd.setup_interceptors is None, f"Curse Mark Bearer: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_anbu_assassin():
    """ANBU Assassin: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['ANBU Assassin']
    assert cd.setup_interceptors is None, f"ANBU Assassin: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_forbidden_jutsu_user():
    """Forbidden Jutsu User: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Forbidden Jutsu User']
    assert cd.setup_interceptors is None, f"Forbidden Jutsu User: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_reanimated_shinobi():
    """Reanimated Shinobi: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Reanimated Shinobi']
    assert cd.setup_interceptors is None, f"Reanimated Shinobi: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_fire_style_user():
    """Fire Style User: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Fire Style User']
    assert cd.setup_interceptors is None, f"Fire Style User: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_uzumaki_descendant():
    """Uzumaki Descendant: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Uzumaki Descendant']
    assert cd.setup_interceptors is None, f"Uzumaki Descendant: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_shadow_clone():
    """Shadow Clone: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Shadow Clone']
    assert cd.setup_interceptors is None, f"Shadow Clone: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_taijutsu_specialist():
    """Taijutsu Specialist: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Taijutsu Specialist']
    assert cd.setup_interceptors is None, f"Taijutsu Specialist: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_lightning_blade_user():
    """Lightning Blade User: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Lightning Blade User']
    assert cd.setup_interceptors is None, f"Lightning Blade User: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_berserker_ninja():
    """Berserker Ninja: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Berserker Ninja']
    assert cd.setup_interceptors is None, f"Berserker Ninja: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_gamabunta():
    """Gamabunta, Toad Boss: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Gamabunta, Toad Boss']
    assert cd.setup_interceptors is None, f"Gamabunta, Toad Boss: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_manda():
    """Manda, Snake Boss: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Manda, Snake Boss']
    assert cd.setup_interceptors is None, f"Manda, Snake Boss: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_shukaku():
    """Shukaku, One-Tail: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Shukaku, One-Tail']
    assert cd.setup_interceptors is None, f"Shukaku, One-Tail: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_matatabi():
    """Matatabi, Two-Tails: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Matatabi, Two-Tails']
    assert cd.setup_interceptors is None, f"Matatabi, Two-Tails: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_isobu():
    """Isobu, Three-Tails: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Isobu, Three-Tails']
    assert cd.setup_interceptors is None, f"Isobu, Three-Tails: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_son_goku():
    """Son Goku, Four-Tails: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Son Goku, Four-Tails']
    assert cd.setup_interceptors is None, f"Son Goku, Four-Tails: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_gyuki():
    """Gyuki, Eight-Tails: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Gyuki, Eight-Tails']
    assert cd.setup_interceptors is None, f"Gyuki, Eight-Tails: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_toad_summon():
    """Toad Summon: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Toad Summon']
    assert cd.setup_interceptors is None, f"Toad Summon: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_snake_summon():
    """Snake Summon: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Snake Summon']
    assert cd.setup_interceptors is None, f"Snake Summon: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_forest_of_death_beast():
    """Forest of Death Beast: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Forest of Death Beast']
    assert cd.setup_interceptors is None, f"Forest of Death Beast: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_nature_chakra_user():
    """Nature Chakra User: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Nature Chakra User']
    assert cd.setup_interceptors is None, f"Nature Chakra User: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_sage_apprentice():
    """Sage Apprentice: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Sage Apprentice']
    assert cd.setup_interceptors is None, f"Sage Apprentice: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_giant_centipede():
    """Giant Centipede: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Giant Centipede']
    assert cd.setup_interceptors is None, f"Giant Centipede: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_forest_guardian():
    """Forest Guardian: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Forest Guardian']
    assert cd.setup_interceptors is None, f"Forest Guardian: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_sage_mode_enchantment():
    """Sage Mode: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Sage Mode']
    assert cd.setup_interceptors is None, f"Sage Mode: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_nature_chakra_field():
    """Nature Chakra Field: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Nature Chakra Field']
    assert cd.setup_interceptors is None, f"Nature Chakra Field: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_kunai():
    """Kunai: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Kunai']
    assert cd.setup_interceptors is None, f"Kunai: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_shuriken():
    """Shuriken: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Shuriken']
    assert cd.setup_interceptors is None, f"Shuriken: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_forbidden_scroll():
    """Forbidden Scroll: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Forbidden Scroll']
    assert cd.setup_interceptors is None, f"Forbidden Scroll: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_headband_of_the_leaf():
    """Headband of the Leaf: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Headband of the Leaf']
    assert cd.setup_interceptors is None, f"Headband of the Leaf: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_rinnegan_eye():
    """Rinnegan Eye: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Rinnegan Eye']
    assert cd.setup_interceptors is None, f"Rinnegan Eye: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_byakugan_eye():
    """Byakugan Eye: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Byakugan Eye']
    assert cd.setup_interceptors is None, f"Byakugan Eye: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_summoning_contract():
    """Summoning Contract: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Summoning Contract']
    assert cd.setup_interceptors is None, f"Summoning Contract: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_hidden_leaf_village():
    """Hidden Leaf Village: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Hidden Leaf Village']
    assert cd.setup_interceptors is None, f"Hidden Leaf Village: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_hidden_mist_village():
    """Hidden Mist Village: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Hidden Mist Village']
    assert cd.setup_interceptors is None, f"Hidden Mist Village: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_valley_of_the_end():
    """Valley of the End: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Valley of the End']
    assert cd.setup_interceptors is None, f"Valley of the End: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_mount_myoboku():
    """Mount Myoboku: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Mount Myoboku']
    assert cd.setup_interceptors is None, f"Mount Myoboku: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_uchiha_compound():
    """Uchiha Compound: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Uchiha Compound']
    assert cd.setup_interceptors is None, f"Uchiha Compound: expected no setup_interceptors (re-stubbed?)"

def test_vanilla_hyuga_compound():
    """Hyuga Compound: vanilla-reverted, no slice-10 setup."""
    cd = NARUTO_CARDS['Hyuga Compound']
    assert cd.setup_interceptors is None, f"Hyuga Compound: expected no setup_interceptors (re-stubbed?)"


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import traceback
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed, errors = [], [], []
    for name, t in tests:
        try:
            t()
            passed.append(name)
        except AssertionError as e:
            failed.append((name, str(e)))
        except Exception as e:
            errors.append((name, f"{type(e).__name__}: {e}"))
            traceback.print_exc()
    print("\n=== Interceptor verification: Naruto ===")
    print(f"  passed:  {len(passed)}")
    print(f"  failed:  {len(failed)}")
    print(f"  errors:  {len(errors)}")
    print(f"  skipped: {len(SKIPPED_CARDS)} (see SKIPPED_CARDS)")
    if failed:
        print("\n--- FAILURES ---")
        for name, msg in failed[:30]:
            print(f"  {name}: {msg}")
    if errors:
        print("\n--- ERRORS ---")
        for name, msg in errors[:30]:
            print(f"  {name}: {msg}")
    sys.exit(0 if not failed and not errors else 1)
