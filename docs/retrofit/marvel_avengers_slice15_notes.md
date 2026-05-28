# Marvel Avengers — slice-15 stub retrofit (DETECT notes)

File: `src/cards/custom/marvel_avengers.py` (~6042 lines, MTG engine).

## The contamination
A slice-15 retrofit wired 88 `_mvl_*_setup` stubs + 23 `_mvl_resolve_*` resolvers
(lines ~589–2510) that emit **info-pulse events** (SCRY / SURVEIL / MILL /
LIFE_CHANGE drain / DAMAGE) scaled by an ally `_mvl_s15_count_subtype` count —
**regardless of the card's printed text**. They make the interceptor test pass
(~98%) while doing the wrong thing.

`_mvl_s15_count_subtype/_type/_in_graveyard/_in_hand` (lines 543–586) are REAL
count helpers — KEEP them.

## Categories
- **V** = vanilla-revert: text is keyword-only OR only mana/activated abilities
  that the engine resolves through the priority system (no triggered/static
  interceptor needed). Drop `setup_interceptors=`.
- **R** = real-impl: text has a genuine ETB/death/attack/combat/upkeep trigger or
  static lord/keyword-grant the engine can express. Rewrite the setup to match.
- **S** = skip-clean: effect the engine can't express (copy a creature, take an
  extra turn, "gain all abilities", complex modal). Revert to vanilla (or nearest
  correct keyword) so the card stops lying, list in test `SKIPPED_CARDS`.

## Setups (88)
V  Einherjar Soldier — Vigilance, lifelink (kw-only)
R  Lady Sif — attack: other Warriors gain vigilance EOT (attack trigger / grant keyword)
V  SHIELD Helicarrier Crew — Defender. {T}: Add {C} (kw + mana ability)
V  Avengers Medic — {T}: gain 1 life (activated)
V  Nova Corps Officer — Flying, vigilance (kw-only)
R  Ravager Scout — ETB scry 1 (CORRECT pulse → clean ETB scry)
V  SHIELD Tech Specialist — {T}: untap target artifact (activated)
V  Pym Particle Researcher — {T},pay1: loot (activated)
R  Knowhere Merchant — ETB draw then discard (ETB loot)
V  Ravager Engineer — Artifacts you control have '{T}:Add{C}' (static mana-grant; engine n/a → vanilla)
R  Xandarian Pilot — Flying. ETB scry 2 (ETB scry)
S  Loki — ETB copy target creature as Illusion (copy effect — skip-clean to Flash kw)
R  Winter Soldier Asset — Menace. ETB tap target opp creature (targeted ETB tap)
R  Kingpin's Enforcer — Menace. ETB each opp discards (ETB discard)
S  Taskmaster — has all activated abilities of opp creatures (skip-clean to first strike)
R  Ghost — unblockable. combat dmg to player → that player discards (combat-dmg trigger)
R  Baron Zemo — Deathtouch. opp's Avenger dies → draw (death-watch trigger)
R  Mantis — ETB tap target creature, doesn't untap (targeted ETB freeze)
R  Drax — Trample, must-attack. +2/+2 while opp controls a Villain (static cond boost)
R  Dark Elf Warrior — ETB target creature -1/-1 EOT (targeted ETB pump -1/-1)
R  Ultron Drone — dies: deal 2 to any target (death trigger damage)
R  Fire Demon — Haste. ETB deal 1 to any target (targeted ETB damage)
V  Chitauri Charger — Haste, menace (kw-only)
R  Nova Prime — Flying,haste. ETB deal power to target creature (targeted ETB damage=power)
V  Destroyer Armor — Indestructible. {R}: deal 2 (activated)
R  Ronan the Accuser — Menace. ETB destroy target creature pow<=3 (targeted ETB destroy)
R  Grandmaster's Champion — Trample. +2/+0 while attacking (self attacking boost)
V  Human Torch — Flying,haste. {R}/{R},{T} abilities (activated)
R  Ant Swarm — +1/+1 per other Insect (dynamic self boost)
R  Vibranium Rhino — Trample. indestructible while attacking (skip-clean: conditional indest → vanilla trample) 
R  Wakandan War Rhino — Trample. ETB fight target creature you don't control (targeted ETB damage both)
R  The Thing — Trample. indestructible while blocking (skip-clean → vanilla trample)
R  Abomination — Trample. combat dmg to player → two +1/+1 on it (combat-dmg trigger counters)
R  Savage Land Raptor — Haste. +2/+0 while attacking (self attacking boost)
R  Savage Land Rex — Trample. ETB fight target creature you don't control (targeted ETB)
R  Forest Troll — Trample. upkeep regenerate (skip-clean → vanilla trample; regen n/a)
R  Red Skull — Menace. upkeep each opp -1, you +1 (upkeep drain — text-correct)
R  Ebony Maw — Flying. ETB gain control of creature pow<=2 (skip-clean → vanilla flying; control-til-leaves n/a)
R  Proxima Midnight — first strike,menace. combat dmg to player → discard (combat-dmg trigger)
V  Corvus Glaive — Deathtouch,lifelink, can't be destroyed by damage (kw-only / static; revert)
R  Cull Obsidian — Trample. +2/+2 while you control another Villain (static cond boost)
R  Baron Mordo — Flash. ETB counter target spell unless pay {3} (ETB counter — targeted spell)
R  Dormammu — Flying,trample,can't be countered. upkeep each opp -3 (upkeep drain)
R  Storm — Flying. ETB tap all opp creatures (ETB tap-all)
R  Professor X — Hexproof. other Mutants hexproof. {T}: look at hand (static keyword grant)
R  Magneto — Flying. ETB gain control all Equipment; equipped opp -2/-0 (skip-clean → vanilla flying)
R  Rogue — Flying. combat dmg to creature → gain its abilities EOT (skip-clean → vanilla flying)
R  Beast — Reach. {T}:any mana. ETB draw (ETB draw)
R  Iceman — Hexproof. ETB tap target creature, doesn't untap (targeted ETB freeze)
R  Nightcrawler — Flash,unblockable. ETB may return another creature you control (ETB bounce own)
R  Colossus — Trample. indestructible while attacking or blocking (skip-clean → vanilla trample)
R  Stormbreaker (equip) — +4/+4 fly/trample/first strike; {T}: 3 dmg (equipment static + activated)
R  Iron Man Armor Mk.L (equip) — +3/+3 fly/hexproof; {2}: 2 dmg (equipment static)
R  Iron Man Armor Mk.LXXXV (equip) — +4/+4 fly/hexproof/indest; {R}:+1/+0 (equipment static)
R  Hulkbuster (equip) — +5/+5 trample; can't be blocked by pow<=3 (equipment static)
R  Web-Shooters (equip) — +1/+1 reach; {T}: tap+freeze (equipment static)
R  Yaka Arrow (equip) — +2/+0; granted {T}: 2 dmg (equipment static)
R  Vibranium Spear (equip) — +2/+1 first strike (equipment static)
R  Panther Habit (equip) — +2/+2 deathtouch/hexproof (equipment static)
R  Nano Gauntlet (equip) — +1/+1 per artifact; {3},{T}: destroy art/ench (equipment static)
R  Cloak of Levitation (equip) — +1/+2 flying (equipment static)
V  Tesseract (art) — {T}:Add{U}{U}; activated flicker (mana + activated)
R  Eye of Agamotto (art) — {T}: scry 2; activated abilities (activated scry — text-correct via activated)
R  Quinjet (art vehicle) — Crew2,Flying. attacks: search Avenger (attack trigger search)
R  The Milano (art vehicle) — Crew2,Flying. attacks: Guardians +2/+0 EOT (attack trigger boost)
R  SHIELD Helicarrier (art vehicle) — Crew4,Flying. granted {T}:draw / {2}{T}:3dmg (skip-clean → vanilla)
R  The Benatar (art vehicle) — Crew2,Flying. attacks: create 1/1 Construct (attack trigger token)
R  SHIELD Headquarters (ench) — upkeep scry 1 (upkeep scry — text-correct)
R  Asgardian Might (ench) — Asgardian creatures +2/+1 trample (static lord by subtype)
R  Mutant Uprising (ench) — Mutant creatures +1/+1 haste (static lord by subtype)
S  Cosmic Convergence (ench) — 2nd spell each turn → copy it (copy — skip-clean, no setup)
R  Vibranium Mines (ench) — Wakandan ETB → add G; Wakandan +0/+1 (static lord +0/+1; mana-on-etb n/a → keep boost)
V  Avengers Tower (land) — mana abilities (activated/mana)
V  Stark Tower (land) — mana abilities (activated/mana)
V  Wakanda (land) — taps for G/W, enters tapped cond (mana; ETB-tapped n/a → vanilla)
R  Asgard (land) — {T}:R/W; {3}{T}: create 2/2 Warrior (activated token — engine via activated; vanilla)
V  Sanctum Sanctorum (land) — {T}:U; {2}{T}: scry (activated)
V  Knowhere (land) — mana abilities (mana)
V  Xavier's School (land) — mana abilities (mana)
V  HYDRA Base (land) — {T}:B; ETB may pay 2 life (mana; ETB-tapped choice n/a → vanilla)
V  SHIELD Facility (land) — taps for W/U, enters tapped (mana → vanilla)
V  Titan (land) — {T}:B/G; sac: search Villain (activated)
V  Vormir (land) — {T}:B; sac creature: draw 2 (activated)
R  Sakaar (land) — {T}:R/G; ETB create 1/1 Alien (ETB token)
V  Contraxia (land) — taps U/R, enters tapped cond (mana → vanilla)
V  Hala (land) — {T}:U; {3}{T}: create 2/2 Kree (activated)
V  Nidavellir (land) — restricted mana (mana → vanilla)
R  Genosha (land) — {T}:R/G; Mutants you control have {T}:any mana (static mana-grant n/a → vanilla)

## Resolvers (23) — all currently emit SCRY/SURVEIL + drain/damage info-pulse
R  Repulsor Blast — 3 dmg target creature; +draw if artifact (damage + conditional draw)
R  Shield Throw — 2 dmg target creature; chain on death (skip-clean → 2 dmg target creature)
R  Hulk Smash — your creature fights target; double if Hulk (skip-clean → damage)
R  Call the Bifrost — 4 dmg divided; +search if Thor (divided damage)
R  Widow's Sting — target -3/-3 EOT; -5/-5 if Black Widow (pump negative)
R  Chaos Magic — 3 dmg any target; 5 if Scarlet Witch (damage, conditional amount)
R  Sling Ring Portal — exile your creature, return (flicker own — skip-clean → flicker)
R  Time Reversal — return all creatures to hand (bounce-all)
R  Snap — each player sac half creatures; Thanos upgrade (sacrifice-half)
R  Gamma Radiation — two +1/+1 on target + trample; 4 if Hulk (counters + keyword)
R  Pym Particles — target -4/-0 or +4/+4 (modal — skip-clean → pump)
R  Arrow Volley — 1 dmg each opp creature; 2 if Hawkeye (sweep damage)
R  Wakanda Forever — your creatures +2/+2 indestructible EOT (mass pump)
R  Mystic Arts — counter target spell unless pay {3} (counter)
R  Blitz Attack — target +2/+0 haste EOT (pump + keyword)
R  Tactical Genius — your creatures +1/+1 EOT (mass pump)
R  Cosmic Awareness — draw 3 (draw 4 if stone) (draw)
R  Berserker Rage — target +3/+0 trample, must attack (pump + keyword)
R  Stealth Mission — target deathtouch + unblockable; draw (grant kw + draw)
R  Heroic Sacrifice — sac a creature; gain life=toughness, draw (sac + draw)
R  Super Soldier Serum — three +1/+1 + vigilance/trample EOT (counters)
R  Reality Warp — exile all art/ench; draw per exiled (skip-clean → exile sweep best-effort)
R  Impale — destroy target creature; controller -2 (destroy + life loss)

---

## FINAL TALLY (retrofit complete)

- **Originally contaminated**: 111 (88 `_mvl_*_setup` stubs + 23 `_mvl_resolve_*`).
- **Stub helper DEFS deleted** (Phase 1): the entire 1921-line info-pulse block
  (88 setups + 23 resolvers). Kept the 4 real `_mvl_s15_count_*` helpers.
- **Real impls** (text-accurate): **72** = 49 setup-cards + 23 resolvers.
- **Vanilla-reverted**: **39** — keyword-only, mana/activated-ability-only (engine
  resolves via priority), or effects the engine can't express (control-steal,
  creature/spell copy, regeneration, take-extra-turn, conditional-while-attacking
  indestructible). Listed in `tests/test_marvel_avengers_interceptors.py`
  `SKIPPED_CARDS` (36 entries).
- **Test**: `tests/test_marvel_avengers_interceptors.py` — 57 pass / 0 fail / 0
  error (pytest + `__main__` runner, STRICT-clean). `tests/test_mvl_spice.py`
  deleted.
- **Bugs found & fixed during authoring**: resolvers referenced
  `obj.characteristics.name` (no such field → `o.name`); added `_is_named()`
  first-name prefix match; Storm test needed opp creatures; Quinjet search uses
  `state.pending_choice`; Professor X keyword grant read via `has_ability`.
- **ci_quick mtg**: 6947 passed / 5 skipped / 0 failed.
