"""AI for SCP: SECURE / CONTAIN / SUBVERT (asymmetric Foundation vs Chaos Insurgency).

One adapter, faction-branching `take_turn` — the asymmetry is intrinsic to the player's
seat (unlike the old SCP per-pilot dispatch). The turn manager calls
``take_turn(player_id, state, game)`` and expects the list of events produced.

Each turn the AI spends its 3 AP one action at a time: a priority chooser picks the single
best move, fires the real engine verb (scp.play_card / advance / contain / infiltrate /
activate_ability / gain_credits / draw_action), and loops until AP runs out.

Fog of war is respected: the InsurgencyAI targets using only *public* information about the
Foundation's board — that a cell has an anomaly, its advancement "heat" (token count), and
how many layers guard it — never the face-down card identities. It takes justified risks,
exactly as a human runner must.
"""

from __future__ import annotations

from src.engine import scp
from src.engine.types import CardType, GameState

SUPPORTED_SCP_DIFFICULTIES = frozenset({"easy", "medium", "hard"})


def validate_scp_difficulty(difficulty: str) -> str:
    norm = str(difficulty).strip().lower()
    if norm not in SUPPORTED_SCP_DIFFICULTIES:
        supported = ", ".join(sorted(SUPPORTED_SCP_DIFFICULTIES))
        raise ValueError(f"Unknown scp difficulty: {difficulty!r}. Supported: {supported}")
    return norm


# --------------------------------------------------------------------------- readers
def _hand_objs(state: GameState, pid: str) -> list:
    return [state.objects[o] for o in scp.hand_ids(state, pid) if o in state.objects]


def _of_kind(objs: list, kind: CardType) -> list:
    return [o for o in objs if getattr(o.card_def, "scp_kind", None) == kind]


def _cost(obj) -> int:
    return int(getattr(obj.card_def, "scp_cost", 0) or 0)


def _affordable(obj, r: dict) -> bool:
    return r["credits"] >= _cost(obj)


def _installed(state: GameState, ids: list, role: str) -> list:
    out = []
    for oid in ids:
        o = state.objects.get(oid)
        if o and getattr(o.state, "scp_role", None) == role:
            out.append(o)
    return out


class SCPAIAdapter:
    """Faction-branching heuristic AI. Construct per game (stateless across turns)."""

    def __init__(self, difficulty: str = "medium"):
        self.difficulty = validate_scp_difficulty(difficulty)

    async def take_turn(self, player_id: str, state: GameState, game) -> list:
        faction = scp.faction_of(state, player_id)
        chooser = (self._foundation_action if faction == scp.FOUNDATION
                   else self._insurgency_action)
        events: list = []
        for _ in range(24):  # safety cap; the choosers always act while AP remains
            if game.is_game_over():
                break
            r = scp.ensure_scp_state(state, player_id)
            if r["ap"] <= 0:
                break
            acted, evs = chooser(game, player_id, state, r)
            if not acted:
                break
            events.extend(evs or [])
        return events

    # ===================================================================== FOUNDATION
    def _foundation_action(self, game, pid, state, r):
        objs = _hand_objs(state, pid)
        cells = r["cells"]
        advancing = []  # (anomaly_obj, cell)
        for cell in cells:
            aid = cell.get("anomaly")
            a = state.objects.get(aid) if aid else None
            if a and getattr(a.state, "scp_status", None) == "advancing":
                advancing.append((a, cell))
        real_advancing = [(a, c) for (a, c) in advancing if int(getattr(a.card_def, "scp_value", 0)) > 0]

        # 1. Contain any *real* anomaly that has met its threshold — never leave points stealable.
        for (a, cell) in real_advancing:
            thr = int(getattr(a.card_def, "scp_threshold", 0))
            if int(getattr(a.state, "scp_advancement", 0)) >= thr:
                ok, _m, evs = scp.contain(game, pid, a.id)
                if ok:
                    return True, evs

        # 2. Stay solvent.
        if r["credits"] < 2:
            ok, _m, evs = scp.gain_credits(game, pid)
            if ok:
                return True, evs

        # 3. Start a win-con if none is advancing.
        anomaly_cards = _of_kind(objs, CardType.SCP_ANOMALY)
        real_anoms = [o for o in anomaly_cards if not getattr(o.card_def, "scp_trap", False)]
        traps = [o for o in anomaly_cards if getattr(o.card_def, "scp_trap", False)]
        if not real_advancing and real_anoms:
            card = min(real_anoms, key=lambda o: (_cost(o), int(getattr(o.card_def, "scp_threshold", 0))))
            if _affordable(card, r):
                ok, _m, evs = scp.play_card(game, pid, card.id)
                if ok:
                    return True, evs

        # 4. Defend an undefended advancing anomaly (hard/medium only).
        layer_cards = _of_kind(objs, CardType.SCP_LAYER)
        if layer_cards and self.difficulty != "easy":
            for (a, cell) in (real_advancing + advancing):
                if len(cell["layers"]) < 1:
                    lc = max(layer_cards, key=lambda o: int(getattr(o.card_def, "scp_strength", 0)))
                    if _affordable(lc, r):
                        ok, _m, evs = scp.play_card(game, pid, lc.id, target=("cell", cell["id"]))
                        if ok:
                            return True, evs

        # 5. Lay an early economy engine.
        asset_cards = _of_kind(objs, CardType.SCP_ASSET)
        if asset_cards and len(r["assets"]) < 2:
            ac = min(asset_cards, key=_cost)
            if _affordable(ac, r):
                ok, _m, evs = scp.play_card(game, pid, ac.id)
                if ok:
                    return True, evs

        # 6. Advance the lead real anomaly toward its lock.
        if real_advancing and r["credits"] >= 1:
            lead = max(real_advancing, key=lambda ac: int(getattr(ac[0].state, "scp_advancement", 0)))
            ok, _m, evs = scp.advance(game, pid, lead[0].id)
            if ok:
                return True, evs

        # 6b. Bait: drop a trap next to a real threat, and advance it a little so it reads as live.
        if traps and 1 <= len(advancing) < 3:
            tc = traps[0]
            if _affordable(tc, r):
                ok, _m, evs = scp.play_card(game, pid, tc.id)
                if ok:
                    return True, evs
        for (a, cell) in advancing:
            if int(getattr(a.card_def, "scp_value", 0)) == 0 and int(getattr(a.state, "scp_advancement", 0)) < 2 and r["credits"] >= 1:
                ok, _m, evs = scp.advance(game, pid, a.id)
                if ok:
                    return True, evs

        # 7. A useful operation.
        op = self._pick_foundation_operation(state, pid, objs, r)
        if op is not None and _affordable(op, r):
            ok, _m, evs = scp.play_card(game, pid, op.id)
            if ok:
                return True, evs

        # 8. Activate an asset ability.
        act_id = self._pick_foundation_activation(state, pid, r)
        if act_id:
            ok, _m, evs = scp.activate_ability(game, pid, act_id)
            if ok:
                return True, evs

        # 9. Draw if thin, else bank Funding.
        if len(scp.hand_ids(state, pid)) < 3:
            ok, _m, evs = scp.draw_action(game, pid)
            if ok:
                return True, evs
        ok, _m, evs = scp.gain_credits(game, pid)
        return (True, evs) if ok else (False, [])

    def _pick_foundation_operation(self, state, pid, objs, r):
        ops = _of_kind(objs, CardType.SCP_OPERATION)
        if not ops:
            return None
        iid = scp.insurgency_id(state)
        ir = scp.ensure_scp_state(state, iid) if iid else {}
        opp_rig = len(ir.get("rig", [])) if ir else 0
        have_layers = any(cell["layers"] for cell in r["cells"])
        by_name = {o.name: o for o in ops}

        def find(substr):
            for name, o in by_name.items():
                if substr in name.lower():
                    return o
            return None

        if len(scp.hand_ids(state, pid)) < 2:
            audit = find("audit")
            if audit:
                return audit
        if have_layers and opp_rig >= 1:
            lock = find("lockdown")
            if lock:
                return lock
        if opp_rig >= 1:
            red = find("redaction")
            if red:
                return red
        return find("amnestics") or ops[0]

    def _pick_foundation_activation(self, state, pid, r):
        assets = _installed(state, r["assets"], "asset")
        thin_hand = len(scp.hand_ids(state, pid)) < 3
        iid = scp.insurgency_id(state)
        ir = scp.ensure_scp_state(state, iid) if iid else {}
        opp_rig = len(ir.get("rig", [])) if ir else 0
        for o in assets:
            cd = o.card_def
            if not callable(getattr(cd, "scp_ability", None)):
                continue
            text = (cd.text or "").lower()
            cost = int(getattr(cd, "scp_ability_cost", 0) or 0)
            if r["credits"] < cost:
                continue
            if "draw" in text and thin_hand:
                return o.id
            if "expose" in text and opp_rig >= 1 and int(ir.get("exposed", 0)) < 2:
                return o.id
        return None

    # ===================================================================== INSURGENCY
    def _insurgency_action(self, game, pid, state, r):
        objs = _hand_objs(state, pid)
        fid = scp.foundation_id(state)
        fr = scp.ensure_scp_state(state, fid) if fid else None

        # Public read of the Foundation's cells (no face-down identities).
        targets = []  # (cell, advancement, n_layers)
        if fr:
            for cell in fr["cells"]:
                if not cell.get("anomaly"):
                    continue
                a = state.objects.get(cell["anomaly"])
                adv = int(getattr(a.state, "scp_advancement", 0)) if a else 0
                n_layers = len([l for l in cell["layers"] if state.objects.get(l)])
                targets.append((cell, adv, n_layers))

        # 1. Free an undefended anomaly — a sure steal.
        for (cell, adv, n_layers) in targets:
            if n_layers == 0:
                ok, _m, evs = scp.infiltrate(game, pid, ("cell", cell["id"]))
                if ok:
                    return True, evs

        # 2. Build the rig — broaden breaker coverage.
        op_cards = _of_kind(objs, CardType.SCP_OPERATIVE)
        rig_types = {getattr(o.card_def, "scp_breaks", None)
                     for o in _installed(state, r["rig"], "operative")}
        if op_cards and (len(r["rig"]) < 3 or len(rig_types) < 2):
            missing = [o for o in op_cards if getattr(o.card_def, "scp_breaks", None) not in rig_types]
            pick = min(missing or op_cards, key=_cost)
            if _affordable(pick, r):
                ok, _m, evs = scp.play_card(game, pid, pick.id)
                if ok:
                    return True, evs

        # 3. Economy when low.
        if r["credits"] < 4:
            econ_id = self._pick_insurgency_econ_activation(state, r)
            if econ_id:
                ok, _m, evs = scp.activate_ability(game, pid, econ_id)
                if ok:
                    return True, evs
            tool_cards = _of_kind(objs, CardType.SCP_TOOL)
            if tool_cards:
                tc = min(tool_cards, key=_cost)
                if _affordable(tc, r):
                    ok, _m, evs = scp.play_card(game, pid, tc.id)
                    if ok:
                        return True, evs

        # 4. Strike a hot, defended cell before it locks (need a rig + enough bank to boost).
        if r["rig"]:
            hot = sorted([t for t in targets if t[1] >= 3], key=lambda t: (t[1], -t[2]), reverse=True)
            for (cell, adv, n_layers) in hot:
                if r["credits"] >= 2 * max(1, n_layers):
                    ok, _m, evs = scp.infiltrate(game, pid, ("cell", cell["id"]))
                    if ok:
                        return True, evs

        # 5. Push the Total Breach clock when it's already moving.
        events_in_hand = _of_kind(objs, CardType.SCP_EVENT)
        breach_events = [o for o in events_in_hand if "breach" in (o.card_def.text or "").lower()]
        if breach_events and fr and fr["total_breach"] >= 2:
            be = min(breach_events, key=_cost)
            if _affordable(be, r):
                ok, _m, evs = scp.play_card(game, pid, be.id)
                if ok:
                    return True, evs

        # 6. Otherwise extract value from a cheap event (draw / mill / econ).
        if events_in_hand:
            ec = min(events_in_hand, key=_cost)
            if _affordable(ec, r):
                ok, _m, evs = scp.play_card(game, pid, ec.id)
                if ok:
                    return True, evs

        # 7. Draw if thin, else bank Cells.
        if len(scp.hand_ids(state, pid)) < 3:
            ok, _m, evs = scp.draw_action(game, pid)
            if ok:
                return True, evs
        ok, _m, evs = scp.gain_credits(game, pid)
        return (True, evs) if ok else (False, [])

    def _pick_insurgency_econ_activation(self, state, r):
        for o in _installed(state, r["rig"], "tool"):
            cd = o.card_def
            if not callable(getattr(cd, "scp_ability", None)):
                continue
            text = (cd.text or "").lower()
            if "gain" in text and "cell" in text:
                if r["credits"] >= int(getattr(cd, "scp_ability_cost", 0) or 0):
                    return o.id
        return None


class DispatchSCPAIAdapter:
    """Maps player_id → SCPAIAdapter, for per-seat difficulty in tournaments/tests."""

    def __init__(self, adapters: dict):
        self.adapters = adapters

    async def take_turn(self, player_id: str, state: GameState, game) -> list:
        return await self.adapters[player_id].take_turn(player_id, state, game)
