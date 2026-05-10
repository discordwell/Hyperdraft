# Minecraft TCG - Tricky Trials Expansion (MCT)

## Scope

- Added `MCT`, a 200-card Minecraft TCG expansion.
- Mechanics: Trial, Tame, Pulse, Echo, Raid, Voyage.
- Starter candidates: `trial_chambers`, `tamed_trails`, `copper_pulse`, `deep_dark_echo`, `bastion_raid`, `end_voyage`.
- Build-around focal cards: Chamber Champion, Pack Leader, Redstone Titan, Echo Warden, Piglin Warboss, Ender Sovereign.

## Mechanics

- Trial: rewards Trial/Chamber/grid permanents. Uses existing `mc_on_play`, `mc_turn_bonus`, and dynamic attack hooks.
- Tame: Animal/Friend pack scaling, healing, tokens, and lords.
- Pulse: `mc_on_event` reactions to `MC_MATERIAL_SPEND` with redstone.
- Echo: `mc_on_event` reactions to mob deaths.
- Raid: Hostile/Raider attack pressure and night payoffs.
- Voyage: End/Aerial/diamond ramp and premium-resource finishers.

## Balance Passes

1. Capability pass 1: all six MCT focal packages failed; top-end costs were too hard to cast against Raider.
2. Capability pass 2: lowered focal costs. Piglin Warboss passed; others still failed or were too volatile.
3. Capability pass 3: taught Minecraft AI to value MCT bootstrap/draw actions. Pack Leader passed; focal capability remained noisy.
4. Deck tournament pass 4: End Voyage overperformed at 71.4%; Copper Pulse was 0%. Raised Ender Sovereign cost and put a real Copper finisher into the starter.
5. Deck tournament pass 5: four MCT decks clustered at 42.9%, but Tamed Trails lagged. Added pack pressure and cheaper Tame lords.
6. Deck tournament pass 6: Tamed Trails overshot in a small sample. Deferred further action pending a larger run.
7. Deck tournament pass 7: Tamed Trails and Raider were 64.3%; Trial and End were too low. Nerfed Pack Leader/Best Friends, buffed Chamber Champion and Ender Sovereign access.
8. Deck tournament pass 8: Trial/Copper/Tame were in range; Deep Dark Echo lagged. Buffed Echo bodies and removal.
9. Deck tournament pass 9: best-to-worst spread tightened to 14.3 points in the 8-deck sample. Piglin Warboss still had zero deck-level plays.
10. Deck tournament pass 10/final larger checks: made Warboss easier to cast; ran 112-game matrices. Current final2 ranking: End Voyage 60.7%, Tamed Trails 57.1%, Trial Chambers/Raider 46.4%, Builder 28.6%, Deep Dark/Bastion 25.0%, Copper Pulse 17.9%.

## Final Candidate Decks

- `end_voyage`: current best MCT candidate in the larger final2 run. Wins through cheapened Ender Sovereign, Dragon Herald, End Ship, and Aerial pressure.
- `tamed_trails`: strong go-wide pack deck. Pack Leader and Stable Master are the primary engines.
- `trial_chambers`: best-balanced midrange candidate from pass 9 and still competitive in final2.
- `deep_dark_echo`: playable but under target; Echo Warden and Sonic Boom improved cast/impact but still trail the top decks.
- `bastion_raid`: interactive but under target; Warboss is now castable, but the deck still struggles to convert attacks.
- `copper_pulse`: all cards are being played, but the deck remains the main residual balance risk because Pulse value is not translating into enough lethal pressure.

## Logs

- Capability: `logs/minecraft_mct_capability_pass*.json`, `logs/minecraft_mct_capability_final_*.json`
- Deck tournaments: `logs/minecraft_mct_decktourney_pass4.json` through `logs/minecraft_mct_decktourney_pass10.json`
- Larger final matrices: `logs/minecraft_mct_decktourney_final.json`, `logs/minecraft_mct_decktourney_final2.json`

## Residual Risks

- Capability harness focal-in-opener results are highly volatile and sometimes disagree with deck telemetry. Deck-level card stats were more useful for MCT.
- Copper Pulse still needs another design pass if it must be a top-tier deck; current cards are cast, but the archetype lacks enough closing pressure.
- Bastion Raid has many expensive combat cards that the AI still underplays in some matrices.
- Final ranking is AI-bias dependent (`balanced`). A passive-econ or aggro-bias matrix may reshuffle the meta.
