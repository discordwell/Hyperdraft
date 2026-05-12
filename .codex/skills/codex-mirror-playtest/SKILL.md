---
name: codex-mirror-playtest
description: "Use when building, running, or auditing Codex-supported model-vs-model Hyperdraft playtests, especially parent-orchestrated GPT-5.5 vs GPT-5.5 matches without OpenAI API keys. Covers deterministic referee harnesses, legal action packets, hidden-information safety, subagent-safe coordination, player prompts, transcript logging, and balance interpretation for custom TCG modes."
metadata:
  short-description: Run Codex model-vs-model playtests
---

# Codex Mirror Playtest

## Purpose

Use this skill to turn a Hyperdraft game mode into a Codex-supported model-vs-model playtest loop. The target structure is:

```text
deterministic engine/referee -> legal action packet -> Codex player agent -> validated action -> referee
```

The game code must never call OpenAI APIs or require an API key. Codex itself provides the model players through subagents when the user explicitly asks for model-vs-model play.

## Hard Rules

- Do not add OpenAI API calls, SDK calls, API-key environment requirements, or shell commands that invoke a model service.
- The top-level Codex agent that can spawn and message agents is the live-match coordinator. A spawned subagent must not assume it can create player agents.
- The deterministic referee owns all hidden state, validates every action, applies every action, and logs every transition.
- Player agents receive only their seat packet. Do not give them repo access, logs with hidden information, opponent hand/library data, or implementation files.
- Legal actions must be enumerated with stable IDs. A player chooses an `action_id`; it does not invent game actions.
- If a player returns invalid JSON or an illegal action, allow one repair prompt with the validation error. If it still fails, apply a deterministic fallback such as heuristic choice or `END_TURN`.
- Spawn Codex player subagents only when the user explicitly asks for Codex/model-vs-model/5.5-vs-5.5 play. Otherwise, implement or audit the harness and stop before live agent play.

## Coordination Patterns

Use parent-orchestrated mirror play as the default:

```text
parent coordinator/referee
  -> player subagent A
  -> player subagent B
```

The parent initializes the match, creates packets, messages the active player subagent, validates the answer, applies the action, and logs the transcript. This is the preferred shape for actual GPT-5.5 vs GPT-5.5 play.

Use worker subagents for implementation or review, not for spawning:

```text
parent coordinator
  -> harness worker subagent
  -> evaluator subagent
  -> player subagent A
  -> player subagent B
```

The worker can write the legal-action module, packet serializer, tests, or transcript tools. The evaluator can review balance data. The parent still owns live player-agent orchestration.

The "main subagent plus mirror" pattern is relay-only:

```text
parent message bus
  -> referee worker subagent
  -> mirror/player subagent
```

Use this only when the parent is prepared to relay every packet and action. The referee worker emits a coordination request, the parent sends the packet to the mirror/player, then returns the chosen action to the referee worker. This is slower and more brittle than parent-orchestrated play because the worker cannot directly message the mirror.

## If You Are A Subagent

If this skill is invoked inside a spawned subagent:

- Implement, audit, or evaluate the harness normally.
- Do not try to spawn player agents or claim that live mirror play has started.
- If asked to run model-vs-model play, produce a concise coordination request for the parent instead of inventing a nested agent loop.

Use this format when you need the parent to relay to a player:

```text
COORDINATION_REQUEST
role: player|mirror|evaluator
model: gpt-5.5
seat: P1|P2|none
prompt: <exact prompt to send>
packet: <JSON packet or transcript summary>
expected_response: JSON with action_id and rationale
```

After the parent returns the response, validate it against the legal-action list before applying it.

## Harness Shape

For a new mode, prefer these artifacts:

```text
src/engine/<mode>_legal_actions.py
scripts/play/<mode>_codex_match.py
prompts/ultra_ai/<mode>_codex_player.md
tests/test_<mode>_codex_playtest.py
```

The legal-actions module should expose:

- `legal_<mode>_actions(game, player_id) -> list[dict]`
- `visible_<mode>_packet(game, player_id, legal_actions) -> dict`
- `validate_<mode>_action(game, player_id, action_id_or_payload) -> dict`

Each legal action should include:

- `id`: compact stable identifier for this packet.
- `type`: engine action type.
- `payload`: exact payload the referee will apply.
- `label`: concise human-readable action summary.
- optional `tags`: tactical labels such as `tempo`, `stabilize`, `combo`, `resource`, `lethal`, `risky`.

Keep the list useful, not exhaustive, when combinations explode. Include all mandatory actions plus tactically meaningful subsets, and always include an end-turn/pass action when legal.

## Packet Contract

A player packet should be valid JSON and include:

- `match_id`, `seed`, `turn`, `active_player`, `seat`
- public game state and public opponent state
- private state only for the receiving player
- current objective and win/loss conditions
- concise rules reminders for mode-specific mechanics
- `legal_actions`, where each entry has an `id`, `label`, `type`, and any public tactical annotations

Hidden-information tests are mandatory. A packet for one player must not include the other player's hand, deck order, unrevealed face-down cards, hidden choices, or private side-channel notes.

## Player Prompt

Player prompts should be short and strict:

```text
You are playing seat <P1/P2> in a Hyperdraft <mode> match.
Use only the packet provided in this message.
Choose exactly one legal action id.
Return JSON only:
{"action_id":"...", "rationale":"one concise sentence"}
```

For GPT-5.5 mirror play, create two player subagents with `model: "gpt-5.5"` only when the user explicitly asked for that model. The parent agent remains the referee/orchestrator.

## Running A Match

1. Initialize the deterministic match with explicit decks, pilots if any, and seed.
2. Generate the active player's visible packet and legal action list.
3. Send only that packet to the active player's Codex player agent.
4. Validate the returned JSON and action ID against the current legal list.
5. Apply the action through the existing engine or mode adapter.
6. Append a transcript entry containing packet hash, selected action, validation result, resulting public summary, and any repair/fallback.
7. Continue until terminal state, turn cap, or explicit stop condition.

Do not let player agents run scripts, inspect files, or see the full transcript during a match. If strategic memory is needed, pass a sanitized public summary plus that seat's own prior private decisions.

## Balance Use

Codex mirror matches are high-signal and expensive in orchestration time. Use them to calibrate decision quality, expose unintuitive rules, and test suspicious matchups. Use deterministic heuristic tournaments for volume.

Track at minimum:

- matchup and seat win rates
- turn counts and timeout/draw rates
- invalid-action and repair rates
- archetype-specific win conditions
- decisive swing actions or turns
- cards/actions selected much more or less often than expected

Treat a small Codex mirror sample as qualitative evidence unless it agrees with larger heuristic runs. Good balance conclusions explain both the numbers and the play patterns.

## Meta-Passes

When the user asks for polish loops or outside-the-box review, run a fresh evaluator after every fifth pass or another requested cadence. Give the evaluator only:

- current public rules/card summaries
- aggregate match and balance data
- known open questions
- no prior conclusions about what should change

Ask for concrete risks, degenerate strategies, missing archetypes, and unusual improvement proposals. Convert recommendations into testable hypotheses before changing cards or engine rules.

## Done Criteria

A Codex mirror playtest implementation is not done until:

- legal-action generation has tests for representative game states
- every generated action can be applied or is intentionally marked unavailable
- hidden-info packet tests pass
- transcript replay or deterministic seed reproduction exists
- invalid player output has a tested repair/fallback path
- at least one smoke match can run without model/API code inside the repo
