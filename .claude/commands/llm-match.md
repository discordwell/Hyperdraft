---
description: Run one LLM-vs-LLM Clankers match. Spawns a local harness server and two parallel Claude Code subagents, one per seat. Cache-aware (one long-lived agent per seat instead of per-decision subprocess).
argument-hint: <deck_p1> <deck_p2> [--max-turns 40] [--out logs/<match>.json]
---

# /llm-match — Clankers LLM-vs-LLM via parallel Claude Code agents

You are the orchestrator. Your job: run one Clankers match where both seats
are piloted by independent Claude Code subagents (via the `Agent` tool),
not by `claude -p` subprocesses.

## Architecture (vs the per-decision tournament adapter)

```
You (orchestrator)
  ├─► Bash: spawn `python scripts/play/clankers_local_match.py ...`
  │         (read "LISTEN: <port>" from stdout)
  │
  └─► Single message with 2 Agent calls (parallel):
       ├─ Agent("p1 pilot") — Claude Code subagent, full tools
       │    └─ Bash loop: curl /pending → curl POST /action → curl /done
       │
       └─ Agent("p2 pilot") — Claude Code subagent, full tools
            └─ Bash loop: same pattern, opposite seat
       
Both agents finish when /done returns done=true.
Harness exits after writing the result JSON.
```

The agents stay alive for the entire game — their context (system prompt
brief + strategy doc) gets cached, so per-decision latency is much lower
than the per-call shellout pattern in `clankers_llm_tournament.py`.

## Pre-flight

1. Validate the two deck arguments are in `CLAN_STARTER_DECKS` (currently
   `CLAN_forge`, `CLAN_ethos`, `CLAN_mirth`, `CLAN_bulwark`).
2. Pick an output path (default `logs/llm_match_<deck_p1>_vs_<deck_p2>.json`).
3. Confirm `prompts/ultra_ai/clankers.md` and `docs/strategy/clankers.md`
   exist (the agents need them).

## Workflow

### 1. Spawn the harness in background

```bash
PYTHONPATH=. python scripts/play/clankers_local_match.py \\
    --deck-p1 <DECK_P1> --deck-p2 <DECK_P2> \\
    --max-turns 40 \\
    --json-out <OUT_PATH> 2>&1
```

Use `run_in_background: true` with Bash. Wait for the harness to print
`LISTEN: <port>` (poll the output file via Read, with a 30s budget).
Capture the port.

The harness URL is `http://127.0.0.1:<port>`. The agents will need it.

### 2. Spawn two parallel pilot agents

**Single message with two `Agent` tool calls** so they run concurrently.
Each agent is briefed the same way EXCEPT for which seat it plays:

> You are Claude Code, piloting the `<p1|p2>` seat in a Clankers match
> running on `http://127.0.0.1:<PORT>`. Your assigned deck is `<DECK>`.
>
> ## Read these BEFORE acting (load them into your context once):
> - `prompts/ultra_ai/clankers.md` — full action protocol + per-deck strategy
> - `docs/strategy/clankers.md` — persistent strategy notes
>
> ## Loop (use Bash for every step):
>
> ```
> while true:
>     done=$(curl -s http://127.0.0.1:<PORT>/done)
>     if echo "$done" | jq -e '.done == true' > /dev/null; then
>         echo "Game over: $done"
>         break
>     fi
>     pending=$(curl -s "http://127.0.0.1:<PORT>/pending?player_id=<SEAT>")
>     if echo "$pending" | jq -e '.pending == null' > /dev/null; then
>         sleep 2
>         continue
>     fi
>     # Pending has a decision for you. Compute the response, then POST it.
>     # See the kind-specific schemas below.
> done
> ```
>
> ## Pending decision kinds + response schemas
>
> **IMPORTANT**: every `*_slot` field must be a **1-indexed INTEGER**, not an
> object ID string. The harness's /action endpoint returns HTTP 422 with a
> clear error message if you pass strings or out-of-range numbers — read
> the error response body and retry with corrected slots.
>
> When `/pending` returns `{"pending": {"kind": "<kind>", ...}}`:
>
> **`choose_assemble_action`**: respond with `{"value": {"slot": <int>}}`.
> Slot 0 = pass; slots 1..N pick from the `legal_actions` array.
>
> **`choose_attackers`**: respond with `{"value": {"slots": [<int>, ...]}}`.
> Each entry is a 1-indexed integer slot into `candidates`. Pass `{"slots": []}`
> to skip attacking. NEVER pass obj_id strings.
>
> **`choose_blockers`**: respond with
> `{"value": {"blocks": [{"attacker_slot": <int>, "blocker_slot": <int>}, ...]}}`.
> Both fields are 1-indexed INTEGERS:
>   - `attacker_slot` indexes the `attackers` list (1..N)
>   - `blocker_slot` indexes the `defenders` list (1..N)
> Each defender can only block one attacker.
> Example: `{"blocks": [{"attacker_slot": 1, "blocker_slot": 2}]}` = blocker
> #2 blocks attacker #1. If you pass `"obj_xyz123"` as `attacker_slot`, the
> harness rejects with 422 and the block is NOT applied (= unblocked damage
> to your Core).
>
> **`choose_refill`**: respond with `{"value": {"take": <bool>}}`.
>
> **`choose_target`**: respond with `{"value": {"slot": <int>}}`. 1-indexed slot
> into `candidates`.
>
> ## Strategy
>
> Apply the per-deck plan from the brief. Specifically for your seat:
> - `CLAN_forge`: brick — drop big chassis on curve; alpha when ahead.
> - `CLAN_ethos`: control — cycle Transients; survive turn 5; close late.
> - `CLAN_mirth`: swarm — flood Synchronize chassis; chip with Self-Mobile.
> - `CLAN_bulwark`: artillery — stack armor; race deathclock.
>
> Refill decisions: take it unless library < 12 AND you're winning.
> Block lethal threats; let chip damage through.
>
> ## End
>
> When you observe `done=true`, print a 2-line summary (winner, your turn-count) and exit.

### 3. Wait for both agents AND the harness to complete

Each Agent call blocks until that subagent finishes. Both will finish at
roughly the same time (when /done returns done=true). The harness exits
on its own after writing the JSON.

### 4. Read the result

Read `<OUT_PATH>`. It contains `{deck_p1, deck_p2, winner, loser, turns, error, port}`.

### 5. Report

Print a 3-line summary to the user:
- Winner + losing deck + turns + harness wall time
- Any error from the harness
- Path to the JSON

## Notes

- **One match at a time**. The harness binds a port and holds a single
  GameState — running multiple matches in parallel means multiple
  `/llm-match` invocations, each with their own port.
- **Cache amortization**: each subagent's full brief (the ~170-line
  `prompts/ultra_ai/clankers.md` + 150-line strategy doc) is read ONCE
  at agent start; subsequent Bash tool calls get prompt-cache hits on
  the system prompt for the remainder of the game. Expected: 5-10×
  cheaper than the per-decision `claude -p` adapter.
- **Idle timeout**: harness self-exits after `--idle-timeout` seconds
  (default 600) with no /action POSTs — handles dead subagents.
- **Heuristic fallback**: if a subagent's decision times out (300s per
  decision), the harness substitutes a hard-tier `ClankersAIAdapter`
  decision and continues. The game always completes.
- **Tournament mode** (multiple invocations): run `/llm-match` in a
  loop from the orchestrator; each invocation is independent.
