"""Foundations Beyond (FBN) Starter Deck Factories.

Ten pinnacle starter decks, one per archetype.  Each builder returns a
30-card ``list[CardDefinition]`` drawn from ``FBN_CARDS``.  The deck label
convention requires every key to start with ``FBN_`` so that
``balance_loop.py`` filtering works correctly.

Composition per deck:
  - 12-14 Anomalies  (main threats)
  - 6-8  Personnel   (assigners)
  - 3-4  Facilities  (resources)
  - 4-5  Procedures  (one-shots)
  - 1    Mandate     (alt-win anchor, always the 30th card)

Design principle: every deck is a *pinnacle* of its archetype — the
strongest possible list, not a tutorial build.  Cards are chosen to
maximise the archetype's gameplay loop (see ``foundations_beyond.md``
section 3 for loop descriptions).
"""

from __future__ import annotations

from typing import Callable

from src.engine.types import CardDefinition

# Import all archetype card lists directly — avoids the circular
# FBN_CARDS dict until all ten archetype modules are loaded.
from .phyrexian_strain import PHYREXIAN_STRAIN_CARDS
from .eldrazi_apex import ELDRAZI_APEX_CARDS
from .dragon_conclave import DRAGON_CONCLAVE_CARDS
from .planeswalker_detention import PLANESWALKER_DETENTION_CARDS
from .demonic_pact_bureau import DEMONIC_PACT_BUREAU_CARDS
from .leyline_anomaly import LEYLINE_ANOMALY_CARDS
from .multiverse_rift import MULTIVERSE_RIFT_CARDS
from .lich_phylactery import LICH_PHYLACTERY_CARDS
from .wurm_apex import WURM_APEX_CARDS
from .spirit_archive import SPIRIT_ARCHIVE_CARDS


# ---------------------------------------------------------------------------
# Internal lookup helpers
# ---------------------------------------------------------------------------

def _idx(card_list: list[CardDefinition]) -> dict[str, CardDefinition]:
    """Build a name → card dict from a single archetype list."""
    return {c.name: c for c in card_list}


def _pick(pool: dict[str, CardDefinition], *names: str) -> list[CardDefinition]:
    """Return the CardDefinition for each name, in order.

    Raises KeyError with the offending name if any lookup fails.
    """
    result = []
    for n in names:
        if n not in pool:
            raise KeyError(
                f"FBN deck builder: card '{n}' not found in pool. "
                f"Available keys (first 10): {list(pool)[:10]}"
            )
        result.append(pool[n])
    return result


# ---------------------------------------------------------------------------
# 3.1  phyrexian_strain — Compleation slow-burn control-theft
#
# Pinnacle loop: open apex Praetor CV anomalies → stall with Mnestic anchors
# → compleation counters tick on opposing personnel each turn → at 3 counters
# the personnel changes controller → 3 swaps → alt-win fires.
#
# Composition: 13 A / 7 P / 4 F / 5 Pr / 1 M
# ---------------------------------------------------------------------------

def build_fbn_phyrexian_strain() -> list[CardDefinition]:
    """Pinnacle Phyrexian Strain deck — compleation_overrun alt-win engine."""
    pool = _idx(PHYREXIAN_STRAIN_CARDS)
    return _pick(
        pool,
        # ── Anomalies (13) ──────────────────────────────────────────────────
        # Mythic Praetor apex trio — core compleation engines
        "SCP-FBN-1140: Yawgmoth-Pattern Strain",      # CV 2 + breach splash
        "SCP-FBN-1141: Atraxa, Praetors' Conduit",    # CV 1 + on-reveal splash
        "SCP-FBN-1145: Elesh Norn, Mother of Machines",# CV 1 + lord +1 to all CVs
        # Rare Praetors — maximize compleation throughput
        "SCP-FBN-1142: Sheoldred, Whispering Strain",  # CV 1 + draw on compleat
        "SCP-FBN-1143: Vorinclex, Bio-Engineer Specimen",# CV 2 + 2x vs skill3+
        "SCP-FBN-1144: Jin-Gitaxias, Cognitive Vector", # CV 1 + opp discard on compleat
        "SCP-FBN-1146: Urabrask, Combustion Vector",    # CV 1 + instant-compleat low-skill
        # Uncommon spread vectors — fill the mid-curve
        "SCP-FBN-1138: The Compleated Liaison",         # CV 1, red_tape 1
        "SCP-FBN-1147: Skithiryx-Class Vector Carrier", # CV 1 + Brief on compleat
        "SCP-FBN-1148: The Phyresis Engine",            # CV 1, counters don't decay
        "SCP-FBN-1149: Memnarch-Pattern Aberration",    # CV 1 + archive on contain
        # Common baseline — early drops to start the clock
        "SCP-FBN-1150: Phyrexian Negator",              # breach suppress on compleat
        "SCP-FBN-1151: Compleation Vector Spawn",       # CV 1, 0 red_tape
        # ── Personnel (7) ────────────────────────────────────────────────────
        # Rare Mnestic leads — immune anchors that can't be stolen
        "Dr. Kassandra Volkov, Mnestic Quarantine Lead", # Mnestic, gain Brief on opp CV
        "Operative O5-3, Strain Containment Lead",       # Mnestic, remove 1 counter/turn
        # Uncommon specialists
        "Researcher Aramis, Vector Specialist",          # spread extra counter on compleat
        "Dr. Linna Halle, Phyresis Containment",         # Mnestic, self CV-immune
        "Dr. Volker Tiede, Praetor Specialist",          # clearance on compleat
        # Common support
        "Researcher Drei, Compleation Cartographer",     # maps strain → opp compleation counter
        "Operative O5-7, Strain Harvester",              # Mnestic, theft payoff (signature bomb)
        # ── Procedures (5) ───────────────────────────────────────────────────
        # Two rare closers
        "Praetor Pact Audit",               # instantly compleat highest-skill opp personnel
        "Class-IV Compleation Audit",       # +2 counters on ALL opp personnel
        # One rare defensive tool
        "Class-A Mnestic Inoculation, Pattern: Yawgmoth-Resistant",  # Mnestic + clear counters
        # Two uncommon tempo pieces
        "Vector Saturation Sweep",          # +1 counter on every opp personnel
        "Containment Breach Reversal: Phyresis Quarantine", # remove 2 counters (safety valve)
        # ── Facilities (4) ───────────────────────────────────────────────────
        "Sector-9 Compleation Quarantine Facility",  # contain+1, all CVs get +1 N
        "Oil Reclamation Tank Gamma",                # contain+1 research+1, archive on compleat
        "Atraxa Specimen Containment Cell",          # research+1, CV anomalies hazard+1
        "Vivisection Suite Vega-9",                  # research+1
        # ── Mandate (1) ──────────────────────────────────────────────────────
        "Mandate FBN-PCV: Compleation Containment Protocol",  # alt-win compleation_overrun
    )


# ---------------------------------------------------------------------------
# 3.2  eldrazi_apex — Sacrifice-fueled annihilation (public_panic race)
#
# Pinnacle loop: dump cheap scion/spawn fodder → sacrifice into Brief
# → apex Annihilation Wave anomalies breach → redact + opposing breach climbs
# → opposing breach ≥ 12 → win.
#
# Composition: 14 A / 6 P / 4 F / 5 Pr / 1 M
# ---------------------------------------------------------------------------

def build_fbn_eldrazi_apex() -> list[CardDefinition]:
    """Pinnacle Eldrazi Apex deck — sacrifice-fueled breach acceleration."""
    pool = _idx(ELDRAZI_APEX_CARDS)
    return _pick(
        pool,
        # ── Anomalies (14) ───────────────────────────────────────────────────
        # Mythic apex trio — core Annihilation Wave engines
        "SCP-FBN-2271: Apollyon-Class Void Eater (Ulamog)",       # AW 2
        "SCP-FBN-2272: Apollyon-Class Hedron-Tilt (Kozilek)",     # AW 2 + Brief 1
        "SCP-FBN-2273: Apollyon-Class Reality-Eater (Emrakul)",   # AW 3 + contain breach+2
        # Rare escalation — mid-curve power
        "SCP-FBN-2280: Eldrazi Conscription Pattern",             # AW 1 + exhaust on breach
        "SCP-FBN-2281: Hedron-Caged Titan",                       # AW 2 + hazard scales w/ dossiers
        # Uncommon brood — sacrifice fodder that generates tempo
        "SCP-FBN-2276: Void Drone, Apollyon-Adjacent",            # AW 1
        "SCP-FBN-2277: Hedron Network Fragment",                  # Brief on sac
        "SCP-FBN-2278: Brood Tyrant Specimen",                    # AW 1
        "SCP-FBN-2279: Void Eel",                                 # AW 1
        "SCP-FBN-2282: Void Aberration",                          # AW 1
        # Common fodder — four cheap bodies for sacrifice fuel
        "SCP-FBN-2274: Apollyon Vector Spawn",                    # Brief on memory-hole
        "SCP-FBN-2275: Eldrazi Scion Pattern",                    # cost-reduction on memory-hole
        "SCP-FBN-2283: Apollyon-Adjacent Ingress",                # opp breach+1 on sac
        "SCP-FBN-2284: Reality-Hole Fragment",                    # draw on sac
        # ── Personnel (6) ─────────────────────────────────────────────────────
        # Two rares — specialist officers
        "Operative Kozilek-Liaison \"Cipher\"",    # AW +1 to wave N, research+contain
        "Class-A Emrakul Containment Specialist",  # contain+research, opp breach+1 on assign
        # Two uncommons
        "Researcher Drake-Ulamog Pact Interpreter",# Brief on sac, research 2
        "Dr. Hedron Calibrator",                   # Brief on Apollyon enter, research 2
        # Two commons
        "Researcher Voider \"Drone Five\"",        # opp breach+1 on sacrifice
        "Class-A Operative \"Hollowing\"",         # ready on sacrifice
        # ── Procedures (5) ────────────────────────────────────────────────────
        # Mythic closer
        "Class-V Reality-Tilt Audit",              # opp breach+3, breach+2, Brief 2
        # Two rares
        "Protocol: Hedron Network Activation",     # sac 3 anomalies, Brief per sac, AW+1
        "Void Bombardment",                        # redact 3 opp, your breach+2 (high-risk win-line)
        # One uncommon
        "Apollyon Vector Sacrifice",               # sac 1 anomaly, gain 2 Brief
        # One common
        "Hedron Audit",                            # look at top 3, put Eldrazi on top
        # ── Facilities (4) ────────────────────────────────────────────────────
        "Containment Site Ash-of-Zendikar",        # research+1, Eldrazi hazard+1
        "Void Approach Vector Suppression Site",   # research+1, archive on AW
        "Hedron Network Containment Grid",         # contain+1, archive on sac
        "Apollyon Convergence Array",              # signature bomb: fire all AW anomalies (self-breach cost)
        # ── Mandate (1) ───────────────────────────────────────────────────────
        "Mandate FBN-AVI: Apollyon Vector Inhibition",  # win on opp breach ≥ 12
    )


# ---------------------------------------------------------------------------
# 3.3  dragon_conclave — Dragon Hoard archive-engine midrange
#
# Pinnacle loop: contain/self-archive Dragons → Dragon Hoard +X to all tests
# → Spark Containment draws more cards → even bigger Dragons → 4 archives
# + Hoard test bonus makes every test trivial → thaumiel alt-win or tempo.
#
# Composition: 13 A / 7 P / 5 F / 4 Pr / 1 M
# ---------------------------------------------------------------------------

def build_fbn_dragon_conclave() -> list[CardDefinition]:
    """Pinnacle Dragon Conclave deck — Dragon Hoard archive engine."""
    pool = _idx(DRAGON_CONCLAVE_CARDS)
    return _pick(
        pool,
        # ── Anomalies (13) ───────────────────────────────────────────────────
        # Mythic apex dragons — Hoard 2 + Spark containment payoffs
        "SCP-FBN-3001: Nicol Bolas, Class-V Apex Dracoform",    # Dragon Hoard 2, self-archive on contain
        "SCP-FBN-3003: Ugin, Class-V Spirit-Wyrm",              # Dragon + Spark Contain 1 + free archive
        # Rare dragons — high-impact mid-curve
        "SCP-FBN-3002: Niv-Mizzet, Class-IV Conduit",           # DH 1 + draw on Dragon contain
        "SCP-FBN-3005: Atarka, World Render",                    # DH 1 + opp breach+1 on contain
        "SCP-FBN-3006: Dragonlord Silumgar",                     # DH 1 + Spark Contain 1
        "SCP-FBN-3008: Ojutai, Soul of Winter",                  # DH 1 + clearance on contain
        "SCP-FBN-3009: Dragonlord Dromoka",                      # DH 1 + Spark Contain 1
        # Uncommon dragons — fill archive count quickly
        "SCP-FBN-3004: Sarkhan-Pattern Hunter",                  # DH 1
        "SCP-FBN-3007: Kolaghan, Storm's Fury",                  # DH 1
        "SCP-FBN-3012: Ancient Class-IV Wyrm",                   # DH 1 + high containment
        "SCP-FBN-3013: Dragon-of-Korlis, Containment Specimen",  # archive token on archive
        # Common dragons — cheap Hoard contributors
        "SCP-FBN-3010: Ramoth-Class Drake",                      # Dragon, cheap
        "SCP-FBN-3011: Class-III Wyrmling",                      # Dragon, 0 red_tape
        # ── Personnel (7) ─────────────────────────────────────────────────────
        # Rares — specialist leads
        "Dr. Sarkhan Vol, Dragonologist",          # scry 3 + archive Dragon on assign
        "Operative O5-7, Dracoform Specialist",    # Spark Contain 1, contain+research
        "Operative O5-12, Sky Patrol Coordinator", # +2 clearance per Dragon contain
        # Uncommons — support the archive engine
        "Researcher Ramoth, Hoard Auditor",        # clearance on archive
        "Dr. Ojiri Kaname, Wyrmkeeper",            # contain 2 backbone
        "Researcher Belora, Dragon Cartographer",  # archive top Dragon on assign
        # Common
        "Class-A Dragonologist 'Forge'",           # research+contain utility
        # ── Procedures (4) ────────────────────────────────────────────────────
        # Mythic finisher
        "Dragonhoard Cataclysm Audit",             # archive all Dragons + Hoard +1 permanent
        # Rare sweeper
        "Class-III Dracoform Sweep",               # each Dragon +2 hazard until EOT
        # Uncommons
        "Protocol: Dracoform Cataloging",          # archive from hand + Spark Contain trigger
        "Hoard Audit",                             # look at top 3, archive any Dragon
        # ── Facilities (5) ────────────────────────────────────────────────────
        "Dracoform Containment Hangar",            # contain+1, research+1, DH 1 base
        "Dragonlord Audit Chamber",                # contain+1, clearance+archive on Dragon contain
        "Eastern Wyrm Containment Bunker",         # contain+1, Dragon containment+1
        "Wyrmkeeper's Vault",                      # research+1, archive on Dragon archive
        "Dragon Audit Bureau",                     # research+1 baseline
        # ── Mandate (1) ───────────────────────────────────────────────────────
        "Mandate FBN-DCG: Dracoform Containment Grid",  # thaumiel win + Hoard test bonus
    )


# ---------------------------------------------------------------------------
# 3.4  planeswalker_detention — Spark Containment tempo-draw grid
#
# Pinnacle loop: contain opposing anomalies → Spark Containment N fires
# → clearance climbs → cross 6 threshold → extra paperwork draw → chain
# another Detention → thaumiel win (3 contained + 0 breach).
#
# Composition: 12 A / 7 P / 5 F / 5 Pr / 1 M
# ---------------------------------------------------------------------------

def build_fbn_planeswalker_detention() -> list[CardDefinition]:
    """Pinnacle Planeswalker Detention deck — Spark Containment draw-engine."""
    pool = _idx(PLANESWALKER_DETENTION_CARDS)
    return _pick(
        pool,
        # ── Anomalies (12) ───────────────────────────────────────────────────
        # Mythic planeswalkers — Spark Containment 2 payoffs
        "SCP-FBN-4001: Jace, Class-III Cognitive Manipulator",    # SC 2 + draw 2 on contain
        "SCP-FBN-4002: Liliana, Class-IV Necromantic Conduit",    # SC 2 + opp queue -1
        "SCP-FBN-4004: Teferi, Class-IV Temporal Adjuster",       # SC 2 + priority gain
        # Rare planeswalkers — Spark Containment 1-2 depth
        "SCP-FBN-4003: Chandra, Class-III Thaumic Ignition",      # SC 1 + redact on contain
        "SCP-FBN-4005: Garruk, Class-III Beastmaster",            # SC 1
        "SCP-FBN-4006: Sorin, Class-IV Necromantic Patron",       # SC 2
        "SCP-FBN-4007: Karn, Class-V Artifact Vector",            # SC 2 + clearance+2
        "SCP-FBN-4010: Vraska, Class-IV Gorgon-Spark",            # SC 1 + high containment
        # Uncommon planeswalkers — cycle and chain
        "SCP-FBN-4008: Tezzeret, Class-III Artifact Manipulator", # SC 1
        "SCP-FBN-4011: Kaya, Class-IV Spectral Investigator",     # SC 1, low red_tape
        "SCP-FBN-4012: The Wanderer, Class-IV Multiversal Asset", # SC 1
        # Common filler
        "SCP-FBN-4009: Class-II Aspirant Spark Carrier",          # SC 1, red_tape 1
        # ── Personnel (7) ─────────────────────────────────────────────────────
        # Mythic
        "Operative O5-Teferi \"Slow-Hand\"",      # SC 1 on turn, exhaust opp personnel
        # Rares
        "Operative O5-Chandra \"Hothead\"",       # SC 1, contain 2
        "Operative O5-Jace \"Mindwarden\"",       # archive from top 2 on assign
        "Operative O5-Liliana \"Bone-Reader\"",   # SC 1, contain 2
        # Uncommon
        "Researcher Tibalt, Junior Spark Auditor",# research+contain utility
        # Commons
        "Class-A Operative \"Detainee\"",         # contain 2 backbone
        "Detention Operative \"Caged\"",          # contain 1 cheap body
        # ── Procedures (5) ────────────────────────────────────────────────────
        # Rares — core detention engine
        "Planar Detention Protocol",              # contain opp anomaly + SC 2
        "Multiversal Detention Sweep",            # contain 2 opp anomalies + SC 2 per
        "Class-IV Spark Suppression Protocol",    # suppress breach + SC 1
        # Uncommons — sustain
        "Spark Audit",                            # clearance = contained anomaly count
        "Wanderer Recall Audit",                  # return contained anomaly + SC 1
        # ── Facilities (5) ────────────────────────────────────────────────────
        "Multiversal Detention Site Charlie",      # contain+1, SC triggers grant N+1 clearance
        "Planeswalker Containment Hub",            # contain+1, research+1, archive PW once/turn
        "Temporal Stasis Cell",                    # research+1, prevent 1 breach once/game
        "Thaumic Containment Grid",                # contain+1
        "Spark Audit Bureau",                      # research+1
        # ── Mandate (1) ───────────────────────────────────────────────────────
        "Mandate FBN-PD: Planeswalker Detention Doctrine", # thaumiel win + upkeep draw
    )


# ---------------------------------------------------------------------------
# 3.5  demonic_pact_bureau — Ethics-tempo Phylactery recursion
#
# Pinnacle loop: cast demons with Phylactery Audit baked in → they get
# memory-holed → Audit returns them for X ethics_debt → stack ethics_debt
# onto opponent via transfer procedures → 4 archives + secrecy 8+ → ethics_audit win.
#
# Composition: 13 A / 7 P / 4 F / 5 Pr / 1 M
# ---------------------------------------------------------------------------

def build_fbn_demonic_pact_bureau() -> list[CardDefinition]:
    """Pinnacle Demonic Pact Bureau deck — Phylactery Audit ethics engine."""
    pool = _idx(DEMONIC_PACT_BUREAU_CARDS)
    return _pick(
        pool,
        # ── Anomalies (13) ───────────────────────────────────────────────────
        # Mythic apex demons — Phylactery Audit 3 + massive effects
        "SCP-FBN-5001: Griselbrand, Class-V Diabolic Negotiator", # PA 3 + draw 3 on research
        "SCP-FBN-5002: Sheoldred-Pact, Class-V Whisperer",       # PA 2 + opp loses 2 on hole
        "SCP-FBN-5003: Bolas-Demon Variant",                      # PA 3 + ethics_debt + secrecy
        # Rare demons — PA 2 mid-curve
        "SCP-FBN-5004: Razaketh, Soul-Broker Specimen",           # PA 2 + opp ethics+1
        "SCP-FBN-5005: Liliana's Pact-Demon Variant",             # PA 1 + ethics-1 + archive
        "SCP-FBN-5006: Demon of Death's Gate",                    # PA 2
        "SCP-FBN-5010: Demonic Tutor Specimen",                   # PA 2 + tutor on contain
        # Uncommon demons — PA 1 filler
        "SCP-FBN-5007: Lord of the Pit, Containment Specimen",   # PA 1
        "SCP-FBN-5008: Mephidross Vampire-Pact",                  # PA 1
        "SCP-FBN-5009: Demon-Possessed Personnel File",           # PA 1 + archive on return
        "SCP-FBN-5011: Demon Lord's Audit Ledger",                # PA 1 low-hazard
        # Common demons — PA 1 cheap bodies
        "SCP-FBN-5012: Junior Pact-Imp",                          # PA 1, 0 red_tape
        "SCP-FBN-5013: Soul-Broker Apprentice",                   # ethics+1 on sacrifice
        # ── Personnel (7) ─────────────────────────────────────────────────────
        # Rare specialists
        "Dr. Faust, Pact Interpreter",            # transfer 1 ethics_debt to opp /turn
        "Operative 'Mark,' Pact Negotiator",      # ethics-1 on opp memory-hole
        # Uncommons
        "Operative O5-9, Ethics Officer",         # ethics-1 /turn (safety valve)
        "Researcher Bargainer 'Hand'",            # ethics+1 + draw on assign
        "Researcher Krell, Diabolic Linguist",    # clearance on Audit payment
        "Dr. Marlowe, Containment Theologian",    # research 2 backbone
        # Common
        "Class-A Operative 'Soul-Auditor'",       # research+contain utility
        # ── Procedures (5) ────────────────────────────────────────────────────
        # Mythic closer
        "Class-V Pact Sweep",                     # exhaust all opp personnel + opp ethics+2
        # Rare engine pieces
        "Demonic Tutor Audit",                    # tutor any anomaly + ethics+2
        "Pact Recall",                            # memory-hole + Phylactery Audit at half cost
        # Uncommon tempo
        "Faustian Re-Audit",                      # ethics+3 + draw 2 (resource burst)
        "Soul-Broker Audit",                      # opp ethics+2, your ethics-1
        # ── Facilities (4) ────────────────────────────────────────────────────
        "Pact Containment Vault",                 # contain+1, research+1, transfer ethics /turn
        "Soul-Reclamation Facility",              # contain+1, archive on Audit payment
        "Diabolic Audit Bureau",                  # research+1
        "Faustian Containment Cell",              # contain+1
        # ── Mandate (1) ───────────────────────────────────────────────────────
        "Mandate FBN-EA: Mercy Ledger Inversion", # ethics_audit win (4 archives + secrecy 8+)
    )


# ---------------------------------------------------------------------------
# 3.6  leyline_anomaly — Punish-tempo Leyline Saturation
#
# Pinnacle loop: drop Leyline Saturation anomalies → every opposing spell
# pumps your anomalies' hazard → Annihilation Wave on apex anomalies fires
# → redact + opp breach climbs → public_panic.
#
# Composition: 14 A / 6 P / 4 F / 5 Pr / 1 M
# ---------------------------------------------------------------------------

def build_fbn_leyline_anomaly() -> list[CardDefinition]:
    """Pinnacle Leyline Anomaly deck — Leyline Saturation spell-lock engine."""
    pool = _idx(LEYLINE_ANOMALY_CARDS)
    return _pick(
        pool,
        # ── Anomalies (14) ───────────────────────────────────────────────────
        # Mythic apex — LS 2 + Annihilation Wave
        "SCP-FBN-6001: Marit Lage, Dormant Class-V Ambient",          # LS 2 + AW 2
        # Rare leyline nodes — high-value saturation and interaction
        "SCP-FBN-6002: Dark Depths Containment Specimen",             # LS 1, transforms on breach
        "SCP-FBN-6003: Field of the Dead, Class-IV Necrotic Site",    # LS 2
        "SCP-FBN-6006: Mishra's Workshop, Class-III Thaumic Forge",   # LS 1 + Brief on opp proc
        "SCP-FBN-6008: Tabernacle at Pendrell Vale",                  # LS 1 + opp upkeep tax
        "SCP-FBN-6010: Eldrazi Temple, Cross-Class Vector",           # LS 1 + AW 1
        "SCP-FBN-6014: Class-IV Ley Network Knot",                    # LS 3 + AW 1 (power node)
        # Uncommon leyline anomalies
        "SCP-FBN-6004: Glacial Chasm, Class-III Stasis Zone",         # LS 1
        "SCP-FBN-6005: Maze of Ith, Class-III Spatial Distortion",    # LS 1 + exhaust on contain
        "SCP-FBN-6007: Bazaar of Baghdad Specimen",                   # LS 1
        "SCP-FBN-6012: Cabal Coffers, Class-IV Necrotic Geometry",    # LS 1
        "SCP-FBN-6013: Lake of the Dead",                             # LS 1
        # Common leyline anomalies
        "SCP-FBN-6009: Wasteland, Class-III Disruption",              # LS 1, cheap
        "SCP-FBN-6011: Strip Mine Specimen",                          # LS 1, cheap
        # ── Personnel (6) ─────────────────────────────────────────────────────
        # Rares
        "Dr. Aaron Yeats, Ley Network Specialist",    # Brief on opp procedure, contain+research
        "Operative \"Conduit-Cutter\"",               # suppress opp leyline /turn
        # Uncommons
        "Operative \"Bottleneck\"",                   # contain 2
        "Researcher Lin, Ambient Hazard Surveyor",    # draw on LS hazard bonus
        # Commons
        'Researcher Cartographer "Map"',              # contain+research utility
        'Class-A Operative "Survey"',                 # research 1 cheap body
        # ── Procedures (5) ────────────────────────────────────────────────────
        # Mythic lock
        "Class-V Saturation Lockdown",               # opp can't resolve procedures (pay ethics)
        # Rare sweeper
        "Containment Sweep: Ley Network Audit",       # exhaust all opp personnel
        # Uncommons
        "Ambient Saturation Sweep",                   # one-shot LS+2 boost on next opp proc
        "Bottleneck the Spell-Lane",                  # redact 1 + opp next proc costs +1
        # Common
        "Ambient Hazard Audit",                       # LS anomalies +1 hazard EOT
        # ── Facilities (4) ────────────────────────────────────────────────────
        "Leyline Containment Grid",                   # contain+1, research+1, LS triggers N+1
        "Saturation Reactor Core",                    # research+1, clearance on opp proc
        "Ley-Survey Bureau",                          # research+1
        "Ambient Containment Site Delta-7",           # contain+1
        # ── Mandate (1) ───────────────────────────────────────────────────────
        "Mandate FBN-LS: Ley Lockdown Doctrine",      # public_panic win, LS hazard cap+1
    )


# ---------------------------------------------------------------------------
# 3.7  multiverse_rift — Cascade chain via Planar Rift
#
# Pinnacle loop: contain own anomaly → Planar Rift X fires → exile top X
# → play any Anomaly free → that free play contains → chain another Rift
# → Brief keeps hand full → public_panic via burst tempo.
#
# Composition: 12 A / 7 P / 5 F / 5 Pr / 1 M
# ---------------------------------------------------------------------------

def build_fbn_multiverse_rift() -> list[CardDefinition]:
    """Pinnacle Multiverse Rift deck — Planar Rift cascade chain engine."""
    pool = _idx(MULTIVERSE_RIFT_CARDS)
    return _pick(
        pool,
        # ── Anomalies (12) ───────────────────────────────────────────────────
        # Mythic apex — Planar Rift 3 closers
        "SCP-FBN-7001: Karn, Class-V Multiversal Vagrant",     # Rift 3 + Brief 2 on contain
        "SCP-FBN-7002: Time Spiral, Class-V Temporal Cataclysm",# Rift 3 + opp breach+1
        "SCP-FBN-7003: Apocalypse, Class-V Multiverse-Reset",   # Rift 2 + redact 2 on breach
        # Rare rift anomalies
        "SCP-FBN-7004: Class-IV Planar Rift, Stable",           # Rift 2 + Brief 1
        "SCP-FBN-7009: Class-IV Multiverse Bleed",              # Rift 2
        # Uncommon rift anomalies — chain links
        "SCP-FBN-7005: Class-III Rift Fragment",                # Rift 1
        "SCP-FBN-7007: Phyrexian Invasion Footprint",           # Rift 1
        "SCP-FBN-7008: Slivers (Class-III, Isolated Specimen)", # Rift 1
        "SCP-FBN-7010: Rift-Walker Specimen",                   # Rift 1
        "SCP-FBN-7011: Cascade Pre-Echo",                       # hazard+1 per contain
        # Common rift anomalies — cheap chain starters
        "SCP-FBN-7006: Pre-Mending Rift Specimen",              # Rift 1, 0 red_tape
        "SCP-FBN-7012: Class-III Vagrant",                      # Brief 1 on contain
        # ── Personnel (7) ─────────────────────────────────────────────────────
        # Rares
        "Operative O5-Karn-Liaison \"Walker\"",    # Rift 1 grant to all anomalies
        "Dr. Teferi, Rift-Stabilization Lead",     # Brief /turn, research+contain
        # Uncommons
        "Researcher Rift-Walker \"Drift\"",        # Brief on assign
        "Operative \"Cascade\"",                   # contain 2 backbone
        "Class-A Multiversal Cartographer",        # research 2
        # Commons
        "Researcher \"Aperture\"",                 # research+contain utility
        "Operative \"Aperture-2\"",                # contain 1 cheap body
        # ── Procedures (5) ────────────────────────────────────────────────────
        # Rare chain triggers
        "Rift Stabilization Protocol",             # contain anomaly + Rift 3
        "Multiversal Containment Sweep",           # contain opp anomaly + Rift 3
        "Class-IV Rift Audit",                     # contain own anomaly + Rift 2
        # Uncommon sustain
        "Cascade Audit",                           # look top 5, play 1 Anomaly free
        # Common Brief engine
        "Brief: Apertures Holding",                # Brief 2
        # ── Facilities (5) ────────────────────────────────────────────────────
        "Multiversal Rift Containment Array",       # contain+1, Rift X exiles X+1
        "Containment Aperture Alpha",               # contain+1, research+1, archive on free-play
        "Apertures Bureau",                         # research+1, contain+1
        "Class-IV Containment Hub",                 # research+1
        "Rift-Wall Containment",                    # contain+1
        # ── Mandate (1) ───────────────────────────────────────────────────────
        "Mandate FBN-MR: Multiversal Rift Protocol", # public_panic win, Rift X → X+1
    )


# ---------------------------------------------------------------------------
# 3.8  lich_phylactery — Memory-hole recursion engine
#
# Pinnacle loop: open Phylactery Audit anomalies → opponent memory-holes
# → Audit offer fires → pay X ethics, card returns → audit counter +1 →
# 4 audits → phylactery_chain alt-win. Mnestic personnel as anchors.
#
# Composition: 13 A / 7 P / 4 F / 5 Pr / 1 M
# ---------------------------------------------------------------------------

def build_fbn_lich_phylactery() -> list[CardDefinition]:
    """Pinnacle Lich Phylactery deck — Phylactery Audit recursion chain."""
    pool = _idx(LICH_PHYLACTERY_CARDS)
    return _pick(
        pool,
        # ── Anomalies (13) ───────────────────────────────────────────────────
        # Mythic lich apex — Phylactery Audit 3 + Mnestic
        "SCP-FBN-8001: Liliana, Class-V Lich-Form",              # PA 3 + Mnestic
        "SCP-FBN-8004: Atraxa-Lich Pattern Variant",             # PA 3 + Mnestic
        # Rare liches — PA 2 high-value
        "SCP-FBN-8002: Mikaeus the Unhallowed, Lich Specimen",   # PA 2 + opp breach+1 on return
        "SCP-FBN-8003: Endrek Sahr, Necrotic Engineer Specimen", # PA 2
        "SCP-FBN-8005: Demonic Animator-Pact Specimen",          # PA 2
        "SCP-FBN-8006: Class-IV Lich-Vessel",                    # PA 2
        "SCP-FBN-8008: Necropotence Specimen",                   # PA 2 + draw on audit pay
        # Uncommon lich anomalies — PA 1 recursion fuel
        "SCP-FBN-8007: Class-III Phylactery-Bound Wraith",       # PA 1
        "SCP-FBN-8009: Class-III Reanimator Pattern",            # PA 1
        "SCP-FBN-8012: Class-IV Wraith-Network",                 # PA 1
        "SCP-FBN-8013: Death's Auditor",                         # PA 1 + Mnestic
        # Common lich anomalies — PA 1 cheap bodies
        "SCP-FBN-8010: Bone-Vessel, Animated",                   # PA 1, 0 red_tape
        "SCP-FBN-8011: Recurring Lich-Fragment",                 # PA 1, curiosity 2
        # ── Personnel (7) ─────────────────────────────────────────────────────
        # Rares
        "Dr. Aliz Volgrim, Mnestic Necrologist",          # Mnestic + PA 2, research+contain
        "Operative O5-Liliana \"Lich-Liaison\"",          # Mnestic + PA 1, contain 2
        # Uncommons
        "Class-A Necromantic Cartographer",               # research 2
        "Researcher \"Knell\"",                           # PA 1, contain 2
        "Dr. Veska, Containment Theologian",              # research 2
        # Commons
        "Researcher \"Bonemark\"",                        # PA 1, research 1
        "Operative \"Phylactery-Hand\"",                  # Mnestic, contain 1
        # ── Procedures (5) ────────────────────────────────────────────────────
        # Mythic mass recursion
        "Class-V Phylactery Resurrection",                # return 2 Phylactery cards from forgotten
        # Rare recursion engine
        "Lich-Chain Audit",                               # archive if 3+ in forgotten + ethics
        # Uncommons
        "Phylactery Activation Protocol",                 # return any Phylactery card from forgotten
        "Mnestic Necromancy Audit",                       # grant Mnestic + PA 1 to all personnel
        "Memory-Hole Counter-Audit",                      # gain clearance when opp memory-holes yours
        # ── Facilities (4) ────────────────────────────────────────────────────
        "Lich Containment Vault",                         # contain+1, research+1, PA costs -1
        "Mnestic Necropolis Site",                        # contain+1, all personnel become Mnestic
        "Phylactery Audit Bureau",                        # research+1
        "Necromancer's Containment Chamber",              # contain+1
        # ── Mandate (1) ───────────────────────────────────────────────────────
        "Mandate FBN-PC: Phylactery Chain Doctrine",      # phylactery_chain alt-win (4 audits)
    )


# ---------------------------------------------------------------------------
# 3.9  wurm_apex — Tame-the-giant Wurm Devourer engine
#
# Pinnacle loop: drop high-hazard Wurm Devourer anomalies → run research
# tests → instead of curiosity, swap -2 hazard / +2 containment (taming)
# → 3 tamed wurms → wurm_apex_tamed alt-win fires.
#
# Composition: 14 A / 6 P / 4 F / 5 Pr / 1 M
# ---------------------------------------------------------------------------

def build_fbn_wurm_apex() -> list[CardDefinition]:
    """Pinnacle Wurm Apex deck — Wurm Devourer taming engine."""
    pool = _idx(WURM_APEX_CARDS)
    return _pick(
        pool,
        # ── Anomalies (14) ───────────────────────────────────────────────────
        # Mythic apex wurms — Wurm Devourer + Annihilation Wave
        "SCP-FBN-9001: Worldspine Wurm, Class-V Apollyon Fauna",  # WD + AW 2
        "SCP-FBN-9002: Pelakka Wurm, Class-IV Apollyon Fauna",    # WD
        "SCP-FBN-9010: Class-V Apex Wurm",                        # WD + AW 2
        # Rare wurms — Wurm Devourer + optional Annihilation Wave
        "SCP-FBN-9003: Engulfing Slagwurm, Class-IV Containment", # WD + AW 1
        "SCP-FBN-9004: Penumbra Wurm, Class-III Specimen",        # WD
        "SCP-FBN-9005: Hellkite-Specimen, Class-IV",              # WD + AW 1
        "SCP-FBN-9006: Ghalta, Primal Hunger Specimen",           # WD
        "SCP-FBN-9014: Apex Reclamation Wurm",                    # WD + archive + clearance on contain
        # Uncommon wurms — Wurm Devourer mid-curve
        "SCP-FBN-9007: Yargle, Vile Containment Subject",         # WD + high hazard
        "SCP-FBN-9009: Wurm Coil Engine, Class-IV Forge-Wurm",   # WD
        "SCP-FBN-9011: Cradle Wurm Specimen",                     # WD
        "SCP-FBN-9012: Spitting Earth Wurm",                      # WD
        # Common wurms — Wurm Devourer cheap taming targets
        "SCP-FBN-9008: Class-III Wurmling",                       # WD, 0 red_tape
        "SCP-FBN-9013: Underground Wurm-Tunnel Specimen",         # WD, cheap
        # ── Personnel (6) ─────────────────────────────────────────────────────
        # Rares
        "Dr. Heyok, Megafauna Specialist",         # auto-pass test on Wurm Devourer anomaly
        "Operative O5-15, Apex Asset Coordinator", # archive on tame
        # Uncommons
        "Researcher Kram, Megafauna Veterinarian", # research 2
        "Class-A Megafauna Specialist",            # research+contain
        # Commons
        'Researcher "Tamer"',                      # research 2
        'Operative "Wurmtongue"',                  # contain 1 cheap
        # ── Procedures (5) ────────────────────────────────────────────────────
        # Mythic mass taming
        "Class-V Apex Sweep",                      # Wurm Devourer fires twice on all WD anomalies
        # Rares
        "Apex Sedation Protocol",                  # auto-pass test on WD anomaly
        "Megafauna Audit",                         # all WD anomalies hazard-1 / containment+1
        # Uncommons
        "Tame the Giant",                          # trigger WD on highest-hazard wurm
        "Apex Habitat Audit",                      # clearance per tamed wurm
        # ── Facilities (4) ────────────────────────────────────────────────────
        "Apex Megafauna Habitat",                  # contain+1, research+1, wurm hazard+1
        "Apex Reclamation Site",                   # research+1, archive on tame
        "Containment Pit Vault",                   # contain+1
        "Megafauna Audit Bureau",                  # research+1
        # NOTE: "SCP-FBN-9099: Apex Pacification Reactor" (taming-accelerant bomb)
        # is built + tested but NOT decked — /card-fire-debug shows it never fires
        # because this archetype self-destructs in ~3.5 turns and never tames a
        # wurm (no taming-aware pilot). Swap it in once the archetype is rescued.
        # ── Mandate (1) ───────────────────────────────────────────────────────
        "Mandate FBN-WAT: Wurm Apex Tamed Doctrine",  # wurm_apex_tamed alt-win (3 tamed)
    )


# ---------------------------------------------------------------------------
# 3.10 spirit_archive — Ambient-hazard Leyline + Phylactery Audit grind
#
# Pinnacle loop: open Leyline Saturation spirits → opposing procedures pump
# ambient hazard → spirits breach → spirits get memory-holed → Phylactery
# Audit returns them → slow grind to public_panic.
#
# Composition: 13 A / 7 P / 4 F / 5 Pr / 1 M
# ---------------------------------------------------------------------------

def build_fbn_spirit_archive() -> list[CardDefinition]:
    """Pinnacle Spirit Archive deck — Leyline Saturation + Phylactery Audit grind."""
    pool = _idx(SPIRIT_ARCHIVE_CARDS)
    return _pick(
        pool,
        # ── Anomalies (13) ───────────────────────────────────────────────────
        # Mythic spirit apex — LS 2 + PA 2 dual-mechanic anchors
        "SCP-FBN-A001: Geist of Saint Traft, Class-IV Spectral Asset",# LS 2 + PA 2
        # Rare spirits — LS+PA combos and key interaction
        "SCP-FBN-A002: Kira, Great Glass-Spinner Specimen",      # LS 1 + PA 1
        "SCP-FBN-A005: Yuriko-Pattern Ninja-Spirit",             # PA 1 + redact on reveal
        "SCP-FBN-A006: Phyrexian Negator, Spirit-Pattern",       # PA 2
        "SCP-FBN-A010: Class-IV Specter-Conduit",                # LS 2 + PA 2 (power node)
        "SCP-FBN-A013: Class-IV Spectral Aggregation",           # LS 2
        # Uncommon spirits — LS and PA depth
        "SCP-FBN-A003: Phantasmal Image, Class-III Phantom",     # PA 1
        "SCP-FBN-A004: Mikokoro, Center of the Sea Specimen",    # LS 1
        "SCP-FBN-A008: Class-III Memory-Wraith",                 # PA 1 + LS 1
        "SCP-FBN-A009: Spectral Cartographer Anomaly",           # LS 1
        "SCP-FBN-A012: Wraithform Specimen",                     # LS 1
        # Common spirits — cheap recursive bodies
        "SCP-FBN-A007: Class-III Wraith Specimen",               # PA 1, 0 red_tape
        "SCP-FBN-A011: Ectoplasmic Resonance Pattern",           # PA 1, cheap
        # ── Personnel (7) ─────────────────────────────────────────────────────
        # Rare leads
        "Dr. Mira Hollis, Spectral Medium",        # Brief on opp procedure, contain+research
        "Dr. Sven, Medium-Containment Lead",       # PA 1, research+contain
        # Uncommons
        "Researcher Aleko, Ecto-thaumic Surveyor", # research 2
        'Operative "Ghosthand"',                   # contain 2
        'Researcher "Veilreader"',                 # research 2
        # Commons
        "Class-A Spectral Cartographer",           # research+contain utility
        'Operative "Phantom-Hand"',                # contain 1 cheap body
        # ── Procedures (5) ────────────────────────────────────────────────────
        # Mythic combined burst
        "Ghost-Mass Audit",                        # LS N → N+1 until EOT + PA 1 to all personnel
        # Rares
        "Spectral Containment Sweep",              # contain opp + LS 1 trigger
        "Class-IV Spectral Audit",                 # return PA card from forgotten + LS 1
        # Uncommons
        "Ectoplasmic Saturation Pulse",            # LS 1 + redact 1
        "Phantom Recall Audit",                    # PA 2 grant to all personnel
        # ── Facilities (4) ────────────────────────────────────────────────────
        "Spirit Containment Array",                # contain+1, research+1, LS triggers N+1
        "Ambient Specter Detention Site",          # contain+1, LS 1 on opp anomaly contain
        "Specter Audit Bureau",                    # research+1
        "Ectoplasmic Containment Chamber",         # contain+1
        # ── Mandate (1) ───────────────────────────────────────────────────────
        "Mandate FBN-SAS: Spectral Ambient Saturation Doctrine",  # public_panic + LS N+1
    )


# ---------------------------------------------------------------------------
# Public factory registry
# ---------------------------------------------------------------------------

FBN_STARTER_DECK_FACTORIES: dict[str, Callable[[], list[CardDefinition]]] = {
    "FBN_phyrexian_strain": build_fbn_phyrexian_strain,
    "FBN_eldrazi_apex": build_fbn_eldrazi_apex,
    "FBN_dragon_conclave": build_fbn_dragon_conclave,
    "FBN_planeswalker_detention": build_fbn_planeswalker_detention,
    "FBN_demonic_pact_bureau": build_fbn_demonic_pact_bureau,
    "FBN_leyline_anomaly": build_fbn_leyline_anomaly,
    "FBN_multiverse_rift": build_fbn_multiverse_rift,
    "FBN_lich_phylactery": build_fbn_lich_phylactery,
    "FBN_wurm_apex": build_fbn_wurm_apex,
    "FBN_spirit_archive": build_fbn_spirit_archive,
}

__all__ = [
    "FBN_STARTER_DECK_FACTORIES",
    "build_fbn_phyrexian_strain",
    "build_fbn_eldrazi_apex",
    "build_fbn_dragon_conclave",
    "build_fbn_planeswalker_detention",
    "build_fbn_demonic_pact_bureau",
    "build_fbn_leyline_anomaly",
    "build_fbn_multiverse_rift",
    "build_fbn_lich_phylactery",
    "build_fbn_wurm_apex",
    "build_fbn_spirit_archive",
]
