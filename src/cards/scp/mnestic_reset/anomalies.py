"""MNR anomaly sub-set.

24 anomalies for Mnestic Reset, themed on qntm's *There Is No Antimemetics
Division*: blind spots, memory holes, cognitive hazards, weaponized
forgetting. Most carry Antimeme N (decay without Mnestic personnel) and
many carry Cognitive Hazard X (opposing hand drain). A handful run bespoke
on-reveal hooks for flavor.

Composition (24 total):
- 16 unique motifs (1 card each) — includes the sample
  "MNR Five and Three-Eighths" which is referenced by name in
  ``tests/test_scp_tcg.py`` (sample fills the "recursive fractional space"
  motif slot).
- 4 "(Severe)" doubles — higher antimeme, higher curiosity, +1 red tape
- 4 "(Containment Critical)" mythics — Antimeme 4 + Cog Hazard 2-3, RT +2
"""

from __future__ import annotations

from src.engine import scp
from src.engine.types import CardDefinition, CardType

from .helpers import _antimeme, _cog_hazard, _mnr_card


# ---------------------------------------------------------------------------
# Sample card preserved verbatim — referenced by tests/test_scp_tcg.py.
# ---------------------------------------------------------------------------

_FIVE_AND_THREE_EIGHTHS = _antimeme(
    _cog_hazard(
        _mnr_card(
            "MNR Five and Three-Eighths",
            CardType.SCP_ANOMALY,
            containment=5,
            curiosity=4,
            hazard=2,
            red_tape=1,
            subtypes={"Antimemetic", "Recursive"},
            text=(
                "Antimeme 3: at end of your turn without a Mnestic personnel, "
                "gain a forget counter. At 3, this anomaly is forgotten. "
                "Cognitive Hazard 1: at the start of an opponent's turn without "
                "a Mnestic personnel, they discard a card."
            ),
            rarity="rare",
            archetype="antimeme_decay",
        ),
        x=1,
    ),
    n=3,
)


# ---------------------------------------------------------------------------
# 15 unique motifs (the sample at the top fills the 16th slot —
# "recursive fractional space").
# ---------------------------------------------------------------------------


# 1. Bystander Effect — a low-RT anomaly that taxes personnel attention.
_BYSTANDER_EFFECT = _antimeme(
    _mnr_card(
        "MNR Bystander Effect",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=3,
        hazard=1,
        red_tape=0,
        subtypes={"Antimemetic", "Social"},
        text=(
            "Antimeme 2. Nobody calls it in; everyone assumes someone else "
            "has. The witnesses are the containment failure."
        ),
        rarity="common",
        archetype="antimeme_decay",
    ),
    n=2,
)


# 2. Locked Filing Cabinet — antimemetic paperwork; bumps secrecy on reveal.
def _locked_cabinet_reveal(obj, state):
    """Filing the dossier creates a record that immediately misfiles itself."""
    s = scp.site(state, obj.controller)
    s["secrecy"] += 1
    return [scp.Event(
        type=scp.EventType.SCP_AUDIT,
        payload={
            "actor": obj.id,
            "target": obj.controller,
            "exposure": -1,
            "reason": "locked_cabinet_misfile",
            "secrecy": s["secrecy"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


_LOCKED_FILING_CABINET = _antimeme(
    _mnr_card(
        "MNR Locked Filing Cabinet",
        CardType.SCP_ANOMALY,
        containment=2,
        curiosity=2,
        hazard=1,
        red_tape=0,
        subtypes={"Antimemetic", "Object"},
        text=(
            "Antimeme 1. On reveal, secrecy +1 — the paperwork files itself "
            "before anyone reads the cover sheet."
        ),
        rarity="common",
        archetype="antimeme_decay",
    ),
    n=1,
)
_LOCKED_FILING_CABINET.scp_on_reveal = _locked_cabinet_reveal


# 3. Missing Floor — a large architectural blind spot.
_MISSING_FLOOR = _antimeme(
    _cog_hazard(
        _mnr_card(
            "MNR Missing Floor",
            CardType.SCP_ANOMALY,
            containment=6,
            curiosity=5,
            hazard=3,
            red_tape=2,
            subtypes={"Antimemetic", "Spatial"},
            text=(
                "Antimeme 3. Cognitive Hazard 1. The elevator buttons are "
                "correctly numbered. The architectural plans are correctly "
                "numbered. The floor is between 13 and 15."
            ),
            rarity="rare",
            archetype="antimeme_decay",
        ),
        x=1,
    ),
    n=3,
)


# 4. Anniversary Ghost — a recurring date you never quite mark.
_ANNIVERSARY_GHOST = _antimeme(
    _mnr_card(
        "MNR Anniversary Ghost",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=4,
        hazard=2,
        red_tape=1,
        subtypes={"Antimemetic", "Temporal"},
        text=(
            "Antimeme 2. Every year on this date, something happened. The "
            "duty roster has it crossed out. You wrote a note about it. "
            "The note is blank."
        ),
        rarity="uncommon",
        archetype="antimeme_decay",
    ),
    n=2,
)


# 5. Memory Reef — collective forgetting in a fixed location; cryptic mood.
_MEMORY_REEF = _cog_hazard(
    _antimeme(
        _mnr_card(
            "MNR Memory Reef",
            CardType.SCP_ANOMALY,
            containment=5,
            curiosity=5,
            hazard=3,
            red_tape=2,
            subtypes={"Antimemetic", "Spatial"},
            text=(
                "Antimeme 3. Cognitive Hazard 1. Walk in, walk out. The "
                "interview will not survive the doorway."
            ),
            rarity="rare",
            archetype="antimeme_decay",
        ),
        n=3,
    ),
    x=1,
)
_MEMORY_REEF.scp_on_reveal = scp._seeded_mood("cryptic", protocol="mirror_box")


# 6. Soft Erasure — gradual escalating antimeme.
_SOFT_ERASURE = _antimeme(
    _mnr_card(
        "MNR Soft Erasure",
        CardType.SCP_ANOMALY,
        containment=4,
        curiosity=3,
        hazard=2,
        red_tape=1,
        subtypes={"Antimemetic", "Memetic"},
        text=(
            "Antimeme 2. It starts with the surname. Then the first name. "
            "By the time anyone notices, the surname is gone too."
        ),
        rarity="uncommon",
        archetype="antimeme_decay",
    ),
    n=2,
)


# 7. The Director's Note — suggests a higher-up you can't name.
def _directors_note_reveal(obj, state):
    """The signature implies authority no one can verify; clearance +1."""
    s = scp.site(state, obj.controller)
    s["clearance"] += 1
    s["briefing"] += 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "directors_note",
            "clearance": s["clearance"],
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


_THE_DIRECTORS_NOTE = _antimeme(
    _mnr_card(
        "MNR The Director's Note",
        CardType.SCP_ANOMALY,
        containment=4,
        curiosity=4,
        hazard=2,
        red_tape=2,
        subtypes={"Antimemetic", "Document"},
        text=(
            "Antimeme 2. On reveal, clearance +1, Brief 1. The handwriting "
            "matches no one on staff. The signature is illegible. The "
            "instructions are followed."
        ),
        rarity="uncommon",
        archetype="antimeme_decay",
    ),
    n=2,
)
_THE_DIRECTORS_NOTE.scp_on_reveal = _directors_note_reveal


# 8. White Hallway Recall — déjà vu without the original event.
_WHITE_HALLWAY_RECALL = _antimeme(
    _mnr_card(
        "MNR White Hallway Recall",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=3,
        hazard=1,
        red_tape=1,
        subtypes={"Antimemetic", "Spatial"},
        text=(
            "Antimeme 2. You've been here before. The wall paint is fresh. "
            "The wall paint has always been fresh."
        ),
        rarity="common",
        archetype="antimeme_decay",
    ),
    n=2,
)


# 9. Cognitive Wedge — splits attention.
_COGNITIVE_WEDGE = _cog_hazard(
    _antimeme(
        _mnr_card(
            "MNR Cognitive Wedge",
            CardType.SCP_ANOMALY,
            containment=5,
            curiosity=4,
            hazard=3,
            red_tape=2,
            subtypes={"Antimemetic", "Cognitive"},
            text=(
                "Antimeme 2. Cognitive Hazard 1. While you're thinking "
                "about it, you cannot think about anything else. While "
                "you're not thinking about it, it doesn't exist."
            ),
            rarity="rare",
            archetype="antimeme_decay",
        ),
        n=2,
    ),
    x=1,
)


# 10. Stripped Conference Room — the meeting that didn't happen.
_STRIPPED_CONFERENCE_ROOM = _antimeme(
    _mnr_card(
        "MNR Stripped Conference Room",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=2,
        hazard=1,
        red_tape=1,
        subtypes={"Antimemetic", "Spatial"},
        text=(
            "Antimeme 1. The agenda is blank. The seats are warm. The "
            "minutes were taken by someone who is not in the directory."
        ),
        rarity="common",
        archetype="antimeme_decay",
    ),
    n=1,
)


# 11. Filed-Away Window — a window you've stopped seeing.
_FILED_AWAY_WINDOW = _antimeme(
    _mnr_card(
        "MNR Filed-Away Window",
        CardType.SCP_ANOMALY,
        containment=2,
        curiosity=3,
        hazard=1,
        red_tape=0,
        subtypes={"Antimemetic", "Object"},
        text=(
            "Antimeme 1. The blueprints show a wall. Everyone walks past "
            "the wall. The view from outside is excellent."
        ),
        rarity="common",
        archetype="antimeme_decay",
    ),
    n=1,
)


# 12. The Blank Folder — a missing case file; uses _public_reveal flavor.
_THE_BLANK_FOLDER = _cog_hazard(
    _antimeme(
        _mnr_card(
            "MNR The Blank Folder",
            CardType.SCP_ANOMALY,
            containment=4,
            curiosity=5,
            hazard=2,
            red_tape=2,
            subtypes={"Antimemetic", "Document"},
            text=(
                "Antimeme 2. Cognitive Hazard 1. On reveal, the cover-up "
                "fails (secrecy -1). The file exists in the index. The "
                "index exists. The file is empty."
            ),
            rarity="rare",
            archetype="antimeme_decay",
        ),
        n=2,
    ),
    x=1,
)
_THE_BLANK_FOLDER.scp_on_reveal = scp._public_reveal(1)


# 13. Counter-Mnestic — punishes Mnestic decks by reversing the shield.
def _counter_mnestic_reveal(obj, state):
    """Mnestic personnel are MORE vulnerable to this anomaly. Seed cryptic mood."""
    obj.state.scp_mood = "cryptic"
    if "feed_it_lies" not in obj.state.scp_protocols:
        obj.state.scp_protocols.append("feed_it_lies")
    s = scp.site(state, obj.controller)
    s["briefing"] += 1
    return [scp.Event(
        type=scp.EventType.SCP_MOOD_SHIFT,
        payload={
            "object_id": obj.id,
            "to": "cryptic",
            "protocol": "feed_it_lies",
            "briefing": s["briefing"],
            "seeded": True,
            "reason": "counter_mnestic",
        },
        source=obj.id,
        controller=obj.controller,
    )]


_COUNTER_MNESTIC = _cog_hazard(
    _antimeme(
        _mnr_card(
            "MNR Counter-Mnestic",
            CardType.SCP_ANOMALY,
            containment=6,
            curiosity=4,
            hazard=3,
            red_tape=2,
            subtypes={"Antimemetic", "Memetic"},
            text=(
                "Antimeme 3. Cognitive Hazard 1. The remembered version is "
                "the dangerous one. Mnestic personnel see it clearly — and "
                "cannot look away."
            ),
            rarity="rare",
            archetype="antimemetic",
        ),
        n=3,
    ),
    x=1,
)
_COUNTER_MNESTIC.scp_on_reveal = _counter_mnestic_reveal


# 14. The Quiet Hour — an hour each day nobody acts during.
_THE_QUIET_HOUR = _antimeme(
    _mnr_card(
        "MNR The Quiet Hour",
        CardType.SCP_ANOMALY,
        containment=4,
        curiosity=3,
        hazard=2,
        red_tape=1,
        subtypes={"Antimemetic", "Temporal"},
        text=(
            "Antimeme 2. Between 03:00 and 04:00 the staff are present, "
            "logged in, and accounted for. The cameras record nothing. "
            "Nothing is recorded by the cameras."
        ),
        rarity="uncommon",
        archetype="antimeme_decay",
    ),
    n=2,
)


# 15. Personnel Drift — researchers slowly forget who they are.
_PERSONNEL_DRIFT = _cog_hazard(
    _antimeme(
        _mnr_card(
            "MNR Personnel Drift",
            CardType.SCP_ANOMALY,
            containment=5,
            curiosity=5,
            hazard=3,
            red_tape=2,
            subtypes={"Antimemetic", "Memetic"},
            text=(
                "Antimeme 3. Cognitive Hazard 1. The roster is correct. The "
                "names on the badges are correct. The faces, on a long "
                "enough timescale, are not."
            ),
            rarity="rare",
            archetype="antimeme_decay",
        ),
        n=3,
    ),
    x=1,
)


# ---------------------------------------------------------------------------
# 4 "(Severe)" doubles — same motifs, larger Antimeme N, +1 red tape.
# ---------------------------------------------------------------------------


# Severe: Soft Erasure
_SOFT_ERASURE_SEVERE = _antimeme(
    _mnr_card(
        "MNR Soft Erasure (Severe)",
        CardType.SCP_ANOMALY,
        containment=5,
        curiosity=5,
        hazard=3,
        red_tape=2,
        subtypes={"Antimemetic", "Memetic"},
        text=(
            "Antimeme 3. Once the surname is gone, the badge stops "
            "matching. Once the badge stops matching, the door stops "
            "opening. Once the door stops opening, the office is empty."
        ),
        rarity="rare",
        archetype="antimeme_decay",
    ),
    n=3,
)


# Severe: Cognitive Wedge
_COGNITIVE_WEDGE_SEVERE = _cog_hazard(
    _antimeme(
        _mnr_card(
            "MNR Cognitive Wedge (Severe)",
            CardType.SCP_ANOMALY,
            containment=6,
            curiosity=5,
            hazard=4,
            red_tape=3,
            subtypes={"Antimemetic", "Cognitive"},
            text=(
                "Antimeme 3. Cognitive Hazard 2. Two simultaneous, "
                "incompatible certainties. The mind picks the wrong one."
            ),
            rarity="rare",
            archetype="antimeme_decay",
        ),
        n=3,
    ),
    x=2,
)


# Severe: The Blank Folder
_THE_BLANK_FOLDER_SEVERE = _cog_hazard(
    _antimeme(
        _mnr_card(
            "MNR The Blank Folder (Severe)",
            CardType.SCP_ANOMALY,
            containment=5,
            curiosity=6,
            hazard=3,
            red_tape=3,
            subtypes={"Antimemetic", "Document"},
            text=(
                "Antimeme 3. Cognitive Hazard 1. On reveal, secrecy -1. "
                "The folder is in a folder. The folder is in a folder. The "
                "folder is empty. The folder was always empty."
            ),
            rarity="rare",
            archetype="antimeme_decay",
        ),
        n=3,
    ),
    x=1,
)
_THE_BLANK_FOLDER_SEVERE.scp_on_reveal = scp._public_reveal(1)


# Severe: Counter-Mnestic
_COUNTER_MNESTIC_SEVERE = _cog_hazard(
    _antimeme(
        _mnr_card(
            "MNR Counter-Mnestic (Severe)",
            CardType.SCP_ANOMALY,
            containment=7,
            curiosity=5,
            hazard=4,
            red_tape=3,
            subtypes={"Antimemetic", "Memetic"},
            text=(
                "Antimeme 3. Cognitive Hazard 2. The clearer the memory, "
                "the larger the wound. Forgetting is the only treatment "
                "that has ever worked."
            ),
            rarity="rare",
            archetype="antimemetic",
        ),
        n=3,
    ),
    x=2,
)
_COUNTER_MNESTIC_SEVERE.scp_on_reveal = _counter_mnestic_reveal


# ---------------------------------------------------------------------------
# 4 "(Containment Critical)" mythics — Antimeme 4 + Cog Hazard 2-3.
# ---------------------------------------------------------------------------


# Mythic: Missing Floor
_MISSING_FLOOR_CRITICAL = _cog_hazard(
    _antimeme(
        _mnr_card(
            "MNR Missing Floor (Containment Critical)",
            CardType.SCP_ANOMALY,
            containment=7,
            curiosity=6,
            hazard=4,
            red_tape=4,
            subtypes={"Antimemetic", "Spatial"},
            text=(
                "Antimeme 4. Cognitive Hazard 2. The elevator goes there. "
                "The stairs do not. Nothing comes back up the stairs."
            ),
            rarity="mythic",
            archetype="antimeme_decay",
        ),
        n=4,
    ),
    x=2,
)


# Mythic: Memory Reef
_MEMORY_REEF_CRITICAL = _cog_hazard(
    _antimeme(
        _mnr_card(
            "MNR Memory Reef (Containment Critical)",
            CardType.SCP_ANOMALY,
            containment=7,
            curiosity=7,
            hazard=4,
            red_tape=4,
            subtypes={"Antimemetic", "Spatial"},
            text=(
                "Antimeme 4. Cognitive Hazard 2. The entire research wing "
                "is on the wrong side of the doorway. The doorway has "
                "always been the wrong side."
            ),
            rarity="mythic",
            archetype="antimeme_decay",
        ),
        n=4,
    ),
    x=2,
)
_MEMORY_REEF_CRITICAL.scp_on_reveal = scp._seeded_mood(
    "cryptic", protocol="mirror_box", briefing=1,
)


# Mythic: The Director's Note
def _directors_note_critical_reveal(obj, state):
    """Severe version: +2 clearance and Brief 2 — the policy is now binding."""
    s = scp.site(state, obj.controller)
    s["clearance"] += 2
    s["briefing"] += 2
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "directors_note_critical",
            "clearance": s["clearance"],
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


_THE_DIRECTORS_NOTE_CRITICAL = _cog_hazard(
    _antimeme(
        _mnr_card(
            "MNR The Director's Note (Containment Critical)",
            CardType.SCP_ANOMALY,
            containment=6,
            curiosity=6,
            hazard=4,
            red_tape=4,
            subtypes={"Antimemetic", "Document"},
            text=(
                "Antimeme 4. Cognitive Hazard 3. On reveal, clearance +2, "
                "Brief 2. The letterhead does not exist. The seal does not "
                "exist. The instructions are followed completely."
            ),
            rarity="mythic",
            archetype="antimemetic",
        ),
        n=4,
    ),
    x=3,
)
_THE_DIRECTORS_NOTE_CRITICAL.scp_on_reveal = _directors_note_critical_reveal


# Mythic: Personnel Drift
_PERSONNEL_DRIFT_CRITICAL = _cog_hazard(
    _antimeme(
        _mnr_card(
            "MNR Personnel Drift (Containment Critical)",
            CardType.SCP_ANOMALY,
            containment=7,
            curiosity=6,
            hazard=4,
            red_tape=4,
            subtypes={"Antimemetic", "Memetic"},
            text=(
                "Antimeme 4. Cognitive Hazard 2. The badge belongs to "
                "someone. The face belongs to someone. They are not the "
                "same person and they never were."
            ),
            rarity="mythic",
            archetype="antimeme_decay",
        ),
        n=4,
    ),
    x=2,
)


# ---------------------------------------------------------------------------
# Final list assembly.
# ---------------------------------------------------------------------------


ANOMALIES: list[CardDefinition] = [
    _FIVE_AND_THREE_EIGHTHS,
    # 16 unique motifs
    _BYSTANDER_EFFECT,
    _LOCKED_FILING_CABINET,
    _MISSING_FLOOR,
    _ANNIVERSARY_GHOST,
    _MEMORY_REEF,
    _SOFT_ERASURE,
    _THE_DIRECTORS_NOTE,
    _WHITE_HALLWAY_RECALL,
    _COGNITIVE_WEDGE,
    _STRIPPED_CONFERENCE_ROOM,
    _FILED_AWAY_WINDOW,
    _THE_BLANK_FOLDER,
    _COUNTER_MNESTIC,
    _THE_QUIET_HOUR,
    _PERSONNEL_DRIFT,
    # 4 Severe doubles
    _SOFT_ERASURE_SEVERE,
    _COGNITIVE_WEDGE_SEVERE,
    _THE_BLANK_FOLDER_SEVERE,
    _COUNTER_MNESTIC_SEVERE,
    # 4 Containment Critical mythics
    _MISSING_FLOOR_CRITICAL,
    _MEMORY_REEF_CRITICAL,
    _THE_DIRECTORS_NOTE_CRITICAL,
    _PERSONNEL_DRIFT_CRITICAL,
]
