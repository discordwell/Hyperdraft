"""Post-construction reveal-time identity wiring for SCP anomalies.

Walks ``SCP_CARDS`` and mutates the assigned anomalies by setting
``scp_on_reveal`` (composed with any pre-existing hook), ``scp_seal_default``
(for antimemetic / cryptic cards that prefer face-down), and ``card.text``
(rules text describing the new mechanic).

Card_def instances are shared across all in-game copies, so mutation is
global by design. Idioms by archetype:

- ACW (Antimemetic Cold War) — cryptic mood, mirror-box/ritual protocols, sealed default
- KBO (Keter Blackout) — hostile reveal (breach), agitated mood
- GOI (GOI Frontline) — public reveal (secrecy hit)
- ETH (Ethics Reckoning) — seeded ethics-debt + suppress mood
- OAR (Oneiric Archives) — cryptic dream mood with briefing payout
- CORE — case-by-case match to printed flavor

Helpers used: ``_public_reveal``, ``_seeded_mood``, ``_hostile_reveal``,
``tax_own_pending``. Conditional branches check ``scp.site(...)`` values.
"""
from __future__ import annotations

from typing import Callable, Optional

from src.engine.types import (
    CardDefinition,
    Event,
    EventType,
    GameObject,
    GameState,
)
from src.engine import scp
from src.engine.scp import (
    _public_reveal,
    _seeded_mood,
    tax_own_pending,
)

# Reveal hook type: takes (GameObject, GameState) -> list[Event].
RevealHook = Callable[[GameObject, GameState], list[Event]]


def _compose(*hooks: Optional[RevealHook]) -> Optional[RevealHook]:
    """Compose reveal hooks so existing ones (e.g. ``_hostile_reveal``) still fire.

    None entries are dropped. Returns ``None`` if every hook is falsy.
    Otherwise returns a function that runs each hook in order and concatenates
    the event lists.
    """
    real = [h for h in hooks if h is not None]
    if not real:
        return None
    if len(real) == 1:
        return real[0]

    def composed(obj: GameObject, state: GameState) -> list[Event]:
        out: list[Event] = []
        for h in real:
            out.extend(h(obj, state) or [])
        return out

    return composed


def _hostile_reveal(amount: int) -> RevealHook:
    """Local mirror of ``src.cards.scp._hostile_reveal`` (avoids circular import)."""

    def reveal(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["breach"] += amount
        return [Event(
            type=EventType.SCP_BREACH_TICK,
            payload={"player": obj.controller, "amount": amount, "reason": "reveal"},
            source=obj.id,
            controller=obj.controller,
        )]

    return reveal


def _ethics_seed(amount: int) -> RevealHook:
    """Seed ethics debt on reveal (ETH archetype). Emits an SCP_ETHICS_SPENT marker."""

    def reveal(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["ethics_debt"] = max(0, s["ethics_debt"] + amount)
        return [Event(
            type=EventType.SCP_ETHICS_SPENT,
            payload={
                "player": obj.controller,
                "amount": amount,
                "mode": "ethics_seeded",
                "source": obj.id,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return reveal


def _tax_own_pending_hook(amount: int) -> RevealHook:
    """Wrap ``tax_own_pending`` (engine helper) as a reveal hook."""

    def reveal(obj: GameObject, state: GameState) -> list[Event]:
        return tax_own_pending(state, obj.controller, amount, source=obj.id)

    return reveal


def _briefing_grant(amount: int = 1) -> RevealHook:
    """Reveal hook that adds ``amount`` briefing tokens. Emits an SCP_MOOD_SHIFT marker."""

    def reveal(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["briefing"] += amount
        return [Event(
            type=EventType.SCP_MOOD_SHIFT,
            payload={
                "object_id": obj.id,
                "briefing": s["briefing"],
                "reason": "briefing_grant",
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return reveal


def _breach_branch(*, high: RevealHook, low: RevealHook, threshold: int = 5) -> RevealHook:
    """Pick a branch based on current breach (``high`` if breach >= threshold)."""

    def reveal(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        if s["breach"] >= threshold:
            return high(obj, state) or []
        return low(obj, state) or []

    return reveal


def _set(card: CardDefinition, *, text: str, hook: Optional[RevealHook], sealed_default: bool = False) -> None:
    """Apply the three writes (compose with any existing hook)."""
    card.scp_on_reveal = _compose(card.scp_on_reveal, hook) if hook else card.scp_on_reveal
    card.text = text
    if sealed_default:
        card.scp_seal_default = True


# ---------------------------------------------------------------------------
# CORE anomaly wiring (19 cards).
# ---------------------------------------------------------------------------


def _apply_core(cards: dict[str, CardDefinition]) -> None:
    if (c := cards.get("The Concrete Saint")):
        # NOTE: kept hazard- and secrecy-neutral on reveal so existing
        # suppression / fast-track baseline tests pass. Briefing tokens are
        # off-axis from breach/secrecy and provide a soft research boost.
        _set(
            c,
            text="On reveal, gain 1 briefing token. (Easy to study, dangerous to ignore.)",
            hook=_briefing_grant(1),
        )
    if (c := cards.get("Recursive Hallway")):
        _set(
            c,
            text="On reveal, add 1 paperwork to each of your other pending dossiers. (Loops paperwork as well as people.)",
            hook=_tax_own_pending_hook(1),
        )
    if (c := cards.get("Singing Vending Machine")):
        _set(
            c,
            text="On reveal, set mood cooperative and gain 1 briefing token. (High research payoff, low containment difficulty.)",
            hook=_seeded_mood("cooperative", briefing=1),
        )
    if (c := cards.get("Door That Opens Sideways")):
        # NOTE: mood-only (no seeded protocol) so existing protocol contradiction
        # test still sees the door's protocol list start empty.
        _set(
            c,
            text="On reveal, set mood cryptic. (Containment is mostly deciding where the room is.)",
            hook=_seeded_mood("cryptic"),
            sealed_default=True,
        )
    if (c := cards.get("Oracle Mold")):
        _set(
            c,
            text="On reveal, set mood cryptic and gain 1 briefing token. (Predicts which staff member will make the mistake.)",
            hook=_seeded_mood("cryptic", briefing=1),
        )
    if (c := cards.get("Rain Inside the Elevator")):
        _set(
            c,
            text="On reveal, set mood docile. (A gentle anomaly unless ignored.)",
            hook=_seeded_mood("docile"),
        )
    if (c := cards.get("Hostile Nursery Rhyme")):
        _set(
            c,
            text="On reveal, set mood agitated; secrecy -1. (Excellent archives, bad dreams.)",
            hook=_compose(_seeded_mood("agitated"), _public_reveal(1)),
        )
    if (c := cards.get("Borrowed Moon")):
        _set(
            c,
            text=(
                "On reveal, branch on breach: if breach >= 5, breach +2; "
                "otherwise gain 1 briefing token. (A large containment ask with a rich research profile.)"
            ),
            hook=_breach_branch(
                high=_hostile_reveal(2),
                low=_briefing_grant(1),
            ),
        )
    if (c := cards.get("Basement Ocean")):
        _set(
            c,
            text="On reveal, secrecy -1 and breach +1. (The tide table is classified.)",
            hook=_compose(_public_reveal(1), _hostile_reveal(1)),
        )
    if (c := cards.get("Paperclip Colony")):
        _set(
            c,
            text="On reveal, add 1 paperwork to each of your other pending dossiers. (Cheap to contain but multiplies in reports.)",
            hook=_tax_own_pending_hook(1),
        )
    if (c := cards.get("Red Room Static")):
        _set(
            c,
            text="On reveal, set mood cryptic. Secrecy -1. (Every recording edits itself.)",
            hook=_compose(_seeded_mood("cryptic"), _public_reveal(1)),
        )
    if (c := cards.get("Patient Zero of Yesterday")):
        _set(
            c,
            text="On reveal, breach +1 and ethics debt +1. (Research asks why the outbreak already happened.)",
            hook=_compose(_hostile_reveal(1), _ethics_seed(1)),
        )
    if (c := cards.get("Clockwork Saint")):
        _set(
            c,
            text="On reveal, set mood docile and gain 1 briefing token. (Hard shell, clean containment reward.)",
            hook=_seeded_mood("docile", briefing=1),
        )
    if (c := cards.get("The Mirror That Interviews You")):
        _set(
            c,
            text="On reveal, set mood cryptic. Apply ritual_diagram. (It knows which questions to ask.)",
            hook=_seeded_mood("cryptic", protocol="ritual_diagram"),
            sealed_default=True,
        )
    if (c := cards.get("Antimemetic Orchard")):
        _set(
            c,
            text="On reveal, set mood cryptic. Apply mirror_box. (Hard to remember, very worth archiving.)",
            hook=_seeded_mood("cryptic", protocol="mirror_box"),
            sealed_default=True,
        )
    if (c := cards.get("Containment Door Zero")):
        _set(
            c,
            text=(
                "On reveal, branch on breach: if breach >= 5, breach +1 and add 1 paperwork "
                "to each of your other pending dossiers; otherwise set mood cooperative."
            ),
            hook=_breach_branch(
                high=_compose(_hostile_reveal(1), _tax_own_pending_hook(1)),
                low=_seeded_mood("cooperative"),
            ),
        )
    if (c := cards.get("The Helpful Knife")):
        _set(
            c,
            text="On reveal, set mood cooperative and ethics debt +1. (Always volunteers. That is the problem.)",
            hook=_compose(_seeded_mood("cooperative"), _ethics_seed(1)),
        )
    if (c := cards.get("Unlicensed Heaven")):
        _set(
            c,
            text="On reveal, breach +2 and ethics debt +2. (High-risk alternate cosmology.)",
            hook=_compose(_hostile_reveal(2), _ethics_seed(2)),
        )
    if (c := cards.get("Moth in the Camera")):
        # NOTE: tax-only (no briefing/secrecy/breach delta) — many baseline
        # tests open Moth first and then probe site values. tax-own-pending
        # is a no-op when no other pending dossiers exist, so the starter
        # anomaly stays inert in isolation but bites when piled up with peers.
        _set(
            c,
            text="On reveal, add 1 paperwork to each of your other pending dossiers. (Starter anomaly for research-focused decks.)",
            hook=_tax_own_pending_hook(1),
        )


# ---------------------------------------------------------------------------
# ACW anomaly wiring (16 cards) — antimemetic / redaction.
# ---------------------------------------------------------------------------


def _apply_acw(cards: dict[str, CardDefinition]) -> None:
    # Default ACW idiom: seeded cryptic + mirror_box, sealed default. Per-card
    # variation comes from briefing and additional secrecy/paperwork taxes.
    pattern = [
        ("ACW Null Choir Anomaly", _seeded_mood("cryptic", protocol="mirror_box"), True,
         "On reveal, set mood cryptic. Apply mirror_box."),
        ("ACW Paperless Witness Anomaly",
         _compose(_seeded_mood("cryptic", protocol="mirror_box"), _public_reveal(1)),
         True,
         "On reveal, set mood cryptic. Apply mirror_box. Secrecy -1."),
        ("ACW Vanishing Orchard Anomaly",
         _compose(_seeded_mood("cryptic"), _tax_own_pending_hook(1)),
         True,
         "On reveal, set mood cryptic. Add 1 paperwork to each of your other pending dossiers."),
        ("ACW Mnemonic Siege Anomaly",
         _compose(_seeded_mood("cryptic", protocol="ritual_diagram"), _tax_own_pending_hook(1)),
         True,
         "On reveal, set mood cryptic. Apply ritual_diagram. Add 1 paperwork to each of your other pending dossiers."),
        ("ACW Unwritten Treaty Anomaly",
         _seeded_mood("cryptic", protocol="mirror_box", briefing=1),
         True,
         "On reveal, set mood cryptic. Apply mirror_box. Gain 1 briefing token."),
        ("ACW Static Pilgrim Anomaly",
         _compose(_seeded_mood("cryptic"), _public_reveal(1)),
         True,
         "On reveal, set mood cryptic. Secrecy -1."),
        ("ACW Backmask City Anomaly",
         _compose(_seeded_mood("cryptic", protocol="mirror_box"), _tax_own_pending_hook(1)),
         True,
         "On reveal, set mood cryptic. Apply mirror_box. Add 1 paperwork to each of your other pending dossiers."),
        ("ACW Cipher Hospital Anomaly",
         # NOTE: this card has an existing _hostile_reveal(1) — compose with it.
         _seeded_mood("cryptic", protocol="mirror_box"),
         True,
         "On reveal, set mood cryptic. Apply mirror_box. Breach +1 (already wired)."),
        ("ACW Ghost Ledger Anomaly",
         _compose(_seeded_mood("cryptic"), _tax_own_pending_hook(1)),
         True,
         "On reveal, set mood cryptic. Add 1 paperwork to each of your other pending dossiers."),
        ("ACW Negative Portrait Anomaly",
         _seeded_mood("cryptic", protocol="mirror_box"),
         True,
         "On reveal, set mood cryptic. Apply mirror_box."),
        ("ACW White Noise Saint Anomaly",
         _seeded_mood("cryptic", briefing=1),
         True,
         "On reveal, set mood cryptic. Gain 1 briefing token."),
        ("ACW Absent Jury Anomaly",
         _compose(_seeded_mood("cryptic"), _public_reveal(1)),
         True,
         "On reveal, set mood cryptic. Secrecy -1."),
        ("ACW Hollow Survey Anomaly",
         _seeded_mood("cryptic", protocol="mirror_box"),
         True,
         "On reveal, set mood cryptic. Apply mirror_box."),
        ("ACW Memory Quarantine Anomaly",
         _seeded_mood("cryptic", protocol="ritual_diagram", briefing=1),
         True,
         "On reveal, set mood cryptic. Apply ritual_diagram. Gain 1 briefing token."),
        ("ACW Dead Language Anomaly",
         _compose(_seeded_mood("cryptic"), _public_reveal(1)),
         True,
         "On reveal, set mood cryptic. Secrecy -1."),
        ("ACW Blind Library Anomaly",
         # Existing _hostile_reveal(1) — compose with cryptic.
         _seeded_mood("cryptic", protocol="mirror_box"),
         True,
         "On reveal, set mood cryptic. Apply mirror_box. Breach +1 (already wired)."),
    ]
    for name, hook, sealed, text in pattern:
        if (c := cards.get(name)):
            _set(c, text=text, hook=hook, sealed_default=sealed)


# ---------------------------------------------------------------------------
# KBO anomaly wiring (16 cards) — Keter / hostile + agitated mood.
# ---------------------------------------------------------------------------


def _apply_kbo(cards: dict[str, CardDefinition]) -> None:
    pattern = [
        ("KBO Ashen Giant Anomaly",
         _compose(_seeded_mood("agitated"), _hostile_reveal(2)),
         "On reveal, set mood agitated. Breach +2."),
        ("KBO Mercy Guillotine Anomaly",
         _compose(_seeded_mood("agitated"), _hostile_reveal(2), _ethics_seed(1)),
         "On reveal, set mood agitated. Breach +2. Ethics debt +1."),
        ("KBO Broken Halo Anomaly",
         _compose(_seeded_mood("agitated"), _hostile_reveal(1)),
         "On reveal, set mood agitated. Breach +1."),
        ("KBO Red Siren Anomaly",
         _compose(_seeded_mood("agitated"), _public_reveal(2)),
         "On reveal, set mood agitated. Secrecy -2."),
        ("KBO Iron Nursery Anomaly",
         _compose(_seeded_mood("agitated"), _hostile_reveal(1), _tax_own_pending_hook(1)),
         "On reveal, set mood agitated. Breach +1. Add 1 paperwork to each of your other pending dossiers."),
        ("KBO Twelve-Minute God Anomaly",
         _compose(_seeded_mood("agitated"), _hostile_reveal(3)),
         "On reveal, set mood agitated. Breach +3."),
        ("KBO Containment Furnace Anomaly",
         _compose(_seeded_mood("agitated"), _hostile_reveal(1)),
         "On reveal, set mood agitated. Breach +1."),
        ("KBO Wild Crown Anomaly",
         _compose(_seeded_mood("agitated"), _hostile_reveal(2)),
         "On reveal, set mood agitated. Breach +2."),
        ("KBO Nightquake Engine Anomaly",
         # Existing _hostile_reveal(1) — compose with mood + extra breach.
         _compose(_seeded_mood("agitated"), _hostile_reveal(2)),
         "On reveal, set mood agitated. Breach +3 (1 already wired + 2)."),
        ("KBO Coffin Star Anomaly",
         _compose(_seeded_mood("agitated"), _hostile_reveal(2), _public_reveal(1)),
         "On reveal, set mood agitated. Breach +2. Secrecy -1."),
        ("KBO Burning Elevator Anomaly",
         _compose(_seeded_mood("agitated"), _hostile_reveal(1)),
         "On reveal, set mood agitated. Breach +1."),
        ("KBO Last Shepherd Anomaly",
         _breach_branch(
             high=_compose(_seeded_mood("agitated"), _hostile_reveal(2)),
             low=_seeded_mood("agitated"),
         ),
         "On reveal, set mood agitated. If breach >= 5, breach +2."),
        ("KBO Cathedral Breach Anomaly",
         _compose(_seeded_mood("agitated"), _hostile_reveal(2)),
         "On reveal, set mood agitated. Breach +2."),
        ("KBO Blackout Leviathan Anomaly",
         _compose(_seeded_mood("agitated"), _hostile_reveal(3)),
         "On reveal, set mood agitated. Breach +3."),
        ("KBO Crisis Glass Anomaly",
         _compose(_seeded_mood("agitated"), _hostile_reveal(1), _public_reveal(1)),
         "On reveal, set mood agitated. Breach +1. Secrecy -1."),
        ("KBO Dead Switch Anomaly",
         _breach_branch(
             high=_compose(_seeded_mood("agitated"), _hostile_reveal(3)),
             low=_compose(_seeded_mood("agitated"), _hostile_reveal(1)),
         ),
         "On reveal, set mood agitated. Breach +1, or +3 if breach >= 5."),
    ]
    for name, hook, text in pattern:
        if (c := cards.get(name)):
            _set(c, text=text, hook=hook)


# ---------------------------------------------------------------------------
# GOI anomaly wiring (16 cards) — public-leak (secrecy drop).
# ---------------------------------------------------------------------------


def _apply_goi(cards: dict[str, CardDefinition]) -> None:
    pattern = [
        ("GOI Broken Auction Anomaly", _public_reveal(2),
         "On reveal, secrecy -2."),
        ("GOI Black Market Reliquary Anomaly", _compose(_public_reveal(1), _ethics_seed(1)),
         "On reveal, secrecy -1. Ethics debt +1."),
        ("GOI Glass Insurgency Anomaly", _public_reveal(2),
         "On reveal, secrecy -2."),
        ("GOI Parahuman Picket Anomaly", _public_reveal(1),
         "On reveal, secrecy -1."),
        ("GOI Smuggled Eden Anomaly", _compose(_public_reveal(1), _seeded_mood("cooperative")),
         "On reveal, secrecy -1. Set mood cooperative."),
        ("GOI Counterfeit Oracle Anomaly", _compose(_public_reveal(1), _seeded_mood("cryptic")),
         "On reveal, secrecy -1. Set mood cryptic."),
        ("GOI Public Leak Cell Anomaly", _public_reveal(3),
         "On reveal, secrecy -3."),
        ("GOI Warehouse Gospel Anomaly", _compose(_public_reveal(1), _hostile_reveal(1)),
         "On reveal, secrecy -1. Breach +1."),
        ("GOI Static Broadcast Anomaly",
         # Existing _hostile_reveal(1) — compose with public reveal.
         _public_reveal(2),
         "On reveal, secrecy -2. Breach +1 (already wired)."),
        ("GOI Crowded Safehouse Anomaly", _compose(_public_reveal(1), _tax_own_pending_hook(1)),
         "On reveal, secrecy -1. Add 1 paperwork to each of your other pending dossiers."),
        ("GOI Anomalous Embassy Anomaly", _public_reveal(2),
         "On reveal, secrecy -2."),
        ("GOI Hostile Benefactor Anomaly", _compose(_public_reveal(1), _ethics_seed(1)),
         "On reveal, secrecy -1. Ethics debt +1."),
        ("GOI Litigation Cult Anomaly", _compose(_public_reveal(1), _tax_own_pending_hook(2)),
         "On reveal, secrecy -1. Add 2 paperwork to each of your other pending dossiers."),
        ("GOI Witness Riot Anomaly", _public_reveal(3),
         "On reveal, secrecy -3."),
        ("GOI Borderless Site Anomaly", _public_reveal(2),
         "On reveal, secrecy -2."),
        ("GOI Raid Calendar Anomaly",
         _breach_branch(
             high=_public_reveal(3),
             low=_public_reveal(1),
             threshold=3,
         ),
         "On reveal, secrecy -1, or -3 if breach >= 3."),
    ]
    for name, hook, text in pattern:
        if (c := cards.get(name)):
            _set(c, text=text, hook=hook)


# ---------------------------------------------------------------------------
# ETH anomaly wiring (16 cards) — ethics-debt seeding.
# ---------------------------------------------------------------------------


def _apply_eth(cards: dict[str, CardDefinition]) -> None:
    pattern = [
        ("ETH Confession Engine Anomaly", _ethics_seed(2),
         "On reveal, ethics debt +2."),
        ("ETH Borrowed Body Anomaly", _compose(_ethics_seed(1), _public_reveal(1)),
         "On reveal, ethics debt +1. Secrecy -1."),
        ("ETH Clean-Room Tribunal Anomaly", _compose(_ethics_seed(1), _seeded_mood("docile")),
         "On reveal, ethics debt +1. Set mood docile."),
        ("ETH Kind Knife Anomaly", _compose(_seeded_mood("cooperative"), _ethics_seed(2)),
         "On reveal, set mood cooperative. Ethics debt +2."),
        ("ETH Witness Garden Anomaly", _compose(_ethics_seed(1), _seeded_mood("cooperative", briefing=1)),
         "On reveal, ethics debt +1. Set mood cooperative. Gain 1 briefing token."),
        ("ETH Aftercare Ward Anomaly", _compose(_ethics_seed(1), _seeded_mood("docile")),
         "On reveal, ethics debt +1. Set mood docile."),
        ("ETH Debt Chapel Anomaly", _ethics_seed(2),
         "On reveal, ethics debt +2."),
        ("ETH Humane Blacksite Anomaly", _compose(_ethics_seed(2), _public_reveal(1)),
         "On reveal, ethics debt +2. Secrecy -1."),
        ("ETH Consent Simulator Anomaly",
         # Existing _hostile_reveal(1) — compose with ethics seed.
         _ethics_seed(2),
         "On reveal, ethics debt +2. Breach +1 (already wired)."),
        ("ETH Red Line Codex Anomaly", _compose(_ethics_seed(1), _seeded_mood("agitated")),
         "On reveal, ethics debt +1. Set mood agitated."),
        ("ETH Volunteer Bell Anomaly", _compose(_ethics_seed(1), _seeded_mood("cooperative")),
         "On reveal, ethics debt +1. Set mood cooperative."),
        ("ETH Burden Archive Anomaly", _compose(_ethics_seed(2), _briefing_grant(1)),
         "On reveal, ethics debt +2. Gain 1 briefing token."),
        ("ETH Patient Sun Anomaly", _compose(_ethics_seed(1), _seeded_mood("docile", briefing=1)),
         "On reveal, ethics debt +1. Set mood docile. Gain 1 briefing token."),
        ("ETH Audit Cathedral Anomaly", _compose(_ethics_seed(1), _tax_own_pending_hook(1)),
         "On reveal, ethics debt +1. Add 1 paperwork to each of your other pending dossiers."),
        ("ETH Moral Injury Anomaly", _compose(_ethics_seed(2), _hostile_reveal(1)),
         "On reveal, ethics debt +2. Breach +1."),
        ("ETH White Budget Anomaly",
         _breach_branch(
             high=_compose(_ethics_seed(2), _public_reveal(1)),
             low=_ethics_seed(1),
             threshold=4,
         ),
         "On reveal, ethics debt +1, or +2 and secrecy -1 if breach >= 4."),
    ]
    for name, hook, text in pattern:
        if (c := cards.get(name)):
            _set(c, text=text, hook=hook)


# ---------------------------------------------------------------------------
# OAR anomaly wiring (16 cards) — mood-cryptic / dream with briefing.
# ---------------------------------------------------------------------------


def _apply_oar(cards: dict[str, CardDefinition]) -> None:
    pattern = [
        ("OAR Lucid Whale Anomaly", _seeded_mood("cryptic", briefing=1),
         False, "On reveal, set mood cryptic. Gain 1 briefing token."),
        ("OAR Moonlit Ward Anomaly", _seeded_mood("cooperative", briefing=1),
         False, "On reveal, set mood cooperative. Gain 1 briefing token."),
        ("OAR Somnambulist Court Anomaly", _seeded_mood("cryptic", protocol="ritual_diagram"),
         True, "On reveal, set mood cryptic. Apply ritual_diagram."),
        ("OAR Dream Cartographer Anomaly", _seeded_mood("cryptic", briefing=2),
         False, "On reveal, set mood cryptic. Gain 2 briefing tokens."),
        ("OAR Nightmare Orchard Anomaly", _compose(_seeded_mood("agitated"), _hostile_reveal(1)),
         False, "On reveal, set mood agitated. Breach +1."),
        ("OAR Velvet Alarm Anomaly", _seeded_mood("docile", briefing=1),
         False, "On reveal, set mood docile. Gain 1 briefing token."),
        ("OAR Glass Pillow Anomaly", _seeded_mood("cooperative", protocol="no_eye_contact"),
         True, "On reveal, set mood cooperative. Apply no_eye_contact."),
        ("OAR Hypnagogic Door Anomaly", _seeded_mood("cryptic", protocol="mirror_box"),
         True, "On reveal, set mood cryptic. Apply mirror_box."),
        ("OAR Waking Labyrinth Anomaly",
         # Existing _hostile_reveal(1) — compose with cryptic + briefing.
         _seeded_mood("cryptic", briefing=1),
         False, "On reveal, set mood cryptic. Gain 1 briefing token. Breach +1 (already wired)."),
        ("OAR REM Cathedral Anomaly", _seeded_mood("cryptic", protocol="ritual_diagram", briefing=1),
         True, "On reveal, set mood cryptic. Apply ritual_diagram. Gain 1 briefing token."),
        ("OAR Drowsing Archive Anomaly", _compose(_seeded_mood("cryptic"), _briefing_grant(1)),
         False, "On reveal, set mood cryptic. Gain 1 briefing token."),
        ("OAR Murmur Lake Anomaly", _seeded_mood("cryptic", briefing=1),
         True, "On reveal, set mood cryptic. Gain 1 briefing token."),
        ("OAR Imaginary Elevator Anomaly", _seeded_mood("cryptic", protocol="mirror_box"),
         True, "On reveal, set mood cryptic. Apply mirror_box."),
        ("OAR Somatic Star Anomaly", _seeded_mood("cooperative", briefing=1),
         False, "On reveal, set mood cooperative. Gain 1 briefing token."),
        ("OAR Nap Protocol Anomaly", _seeded_mood("docile", protocol="no_eye_contact", briefing=1),
         True, "On reveal, set mood docile. Apply no_eye_contact. Gain 1 briefing token."),
        ("OAR Dream-Static Choir Anomaly",
         _breach_branch(
             high=_compose(_seeded_mood("agitated"), _hostile_reveal(1)),
             low=_seeded_mood("cryptic", briefing=1),
             threshold=4,
         ),
         False, "On reveal, set mood cryptic and gain 1 briefing token, or set mood agitated with breach +1 if breach >= 4."),
    ]
    for name, hook, sealed, text in pattern:
        if (c := cards.get(name)):
            _set(c, text=text, hook=hook, sealed_default=sealed)


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


def apply_reveal_identity(cards: dict[str, CardDefinition]) -> None:
    """Wire reveal-time identity (mood, secrecy, breach, ethics, paperwork) for
    bare anomaly cards. Idempotent for non-targeted cards.
    """
    _apply_core(cards)
    _apply_acw(cards)
    _apply_kbo(cards)
    _apply_goi(cards)
    _apply_eth(cards)
    _apply_oar(cards)
