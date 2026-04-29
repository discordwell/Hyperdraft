# MTG Real-Set Orphan Wiring — Engine Gaps

Aggregated from Phase 3 opus agent reports. Phase 2 (mechanical auto-wiring of trivial orphans) added ~140 wirings on top of these Phase 3 numbers — see git history of `src/cards/*.py` for the full diff.

## Per-set Phase 3 dispositions

| set | wired | fixed | consolidated | flagged | skipped | total |
|---|---|---|---|---|---|---|
| edge_of_eternities.py | 54 | 0 | 0 | 0 | 0 | 54 |
| final_fantasy.py | 16 | 0 | 0 | 9 | 0 | 25 |
| foundations.py | 25 | 0 | 0 | 0 | 1 | 26 |
| lost_caverns_ixalan.py | 1 | 0 | 0 | 0 | 0 | 1 |
| murders_karlov_manor.py | 3 | 1 | 0 | 0 | 9 | 13 |
| outlaws_thunder_junction.py | 0 | 0 | 2 | 1 | 0 | 3 |
| spider_man.py | 2 | 1 | 0 | 0 | 0 | 3 |
| wilds_of_eldraine.py | 7 | 0 | 0 | 0 | 0 | 7 |

**Totals:** wired=108, fixed=2, consolidated=2, flagged=10, skipped=10

## Engine gaps blocking these cards

Grouped by missing capability. Each entry lists the orphan setup function and card variable so engine work can be retargeted to unlock them.

### targeting + library search (1 cards)

- `final_fantasy.py` :: `sandworm_setup` (card `SANDWORM`) — Body is pure stub returning []. Card text requires destroying target land plus library search for basic land.

### library search + counter doubling + targeting (1 cards)

- `final_fantasy.py` :: `sazh_katzroy_setup` (card `SAZH_KATZROY`) — Body is pure stub returning []. Requires library search/reveal/may-put-into-hand and a counter-doubling attack trigger.

### life gained per-turn tracking (1 cards)

- `final_fantasy.py` :: `hope_estheim_setup` (card `HOPE_ESTHEIM`) — make_end_step_trigger helper does exist (briefing's unknown_helper flag was wrong) but body returns [] because per-turn life-gained tracking is unimplemented.

### library top-N look + may-put-onto-battlefield (1 cards)

- `final_fantasy.py` :: `ignis_scientia_setup` (card `IGNIS_SCIENTIA`) — Body is pure stub returning []. Requires look-at-top-N library and may-put-onto-battlefield-tapped.

### graveyard targeting + finality counter + 'during your turn' static effect (1 cards)

- `final_fantasy.py` :: `yuna_hope_of_spira_setup` (card `YUNA_HOPE_OF_SPIRA`) — make_end_step_trigger does exist (unknown_helper flag was wrong) but body returns []. Static keyword grant for trample/lifelink/ward to enchantment creatures is also unimplemented.

### temporary control change + targeting (1 cards)

- `final_fantasy.py` :: `zidane_tantalus_thief_setup` (card `ZIDANE_TANTALUS_THIEF`) — Body is pure stub returning []. Needs control change effects.

### targeting + equipment static bonus (1 cards)

- `final_fantasy.py` :: `lion_heart_setup` (card `LION_HEART`) — Body is pure stub returning []. Card needs ETB damage to any target plus equip-bonus +2/+1.

### land bounce targeting + additional land play + dynamic P/T per land (1 cards)

- `final_fantasy.py` :: `zell_dincht_setup` (card `ZELL_DINCHT`) — make_end_step_trigger exists (unknown_helper flag was wrong) but body returns []. Card also needs additional-land-play and dynamic +1/+0 per-land static.

### random graveyard exile + tapped copy-token creation (1 cards)

- `final_fantasy.py` :: `sin_spiras_punishment_setup` (card `SIN_SPIRAS_PUNISHMENT`) — Body wires ETB and attack triggers but both effect functions return []. Card needs random graveyard exile + token-copy creation.

### No crime tracking system in engine. Need either a CRIME_COMMITTED event emitted whenever a player targets an opponent, opponent's permanent, or card in opponent's graveyard, OR a way to attach interceptors to TARGET_DECLARED-style events. Also need 'once per turn' state tracking on the trigger. (1 cards)

- `outlaws_thunder_junction.py` :: `blood_hustler_setup` (card `BLOOD_HUSTLER`) — Body returns [] because crime tracking is not implemented. The function defines crime_effect but never returns an interceptor. Crime detection would require an engine-level CRIME_COMMITTED event or interceptor that hooks targeting events to detect when an opponent/their permanents/their graveyard are targeted. Per task rules ('stub → complete or flag', and 'flagged: needs engine; do NOT wire'), not wiring.

