# Star Wars (SWG) slice-11 stub DETECT — Phase 0

Generated for `recover/interceptor-campaign` restore of `src/cards/custom/star_wars.py`.

- **186 cards** are wired to a `_swr_s11_*` info-pulse stub helper whose emitted
  events (SCRY/SURVEIL/MILL/LIFE_CHANGE/DAMAGE/DISCARD) do NOT match the card's rules text.
- **121 stub helper defs** to delete (the 4 `_swr_s11_count_*` query helpers are REAL — kept).
- **2 keyword-only** cards → vanilla-revert (drop setup_interceptors).
- **184 cards** need a real text-matching impl.

Note: any card whose text genuinely says scry/surveil/mill/gain-life on the correct trigger
would be CORRECT and is NOT in this list (the AST detector keys on the stub-helper wire, and
the stub helpers emit fixed info-pulses irrespective of text).

## By factory

- `make_creature`: 46
- `make_instant`: 38
- `make_sorcery`: 23
- `make_land`: 22
- `make_enchantment`: 12
- `make_equipment`: 12
- `make_vehicle`: 12
- `make_artifact`: 12
- `make_artifact_creature`: 9

## Keyword-only (vanilla-revert)

- L3756 **Gamorrean Guard** (`_swr_s11_etb_scry_drain_clone`): 'Menace.'
- L5909 **Nexu** (`_swr_s11_etb_scry_gain_beast`): 'Deathtouch, haste.'

## Stub-wired cards needing real impl (by helper)

### `_swr_s11_etb_artifact_bacta` — 1 cards
- L5353 **Bacta Tank**: '{2}, {T}: Remove all damage from target creature. You gain 2 life.'

### `_swr_s11_etb_artifact_carbonite` — 1 cards
- L5313 **Carbonite Prison**: 'When Carbonite Prison enters, exile target creature an opponent controls until Carbonite Prison leaves the bat'

### `_swr_s11_etb_artifact_factory` — 2 cards
- L5329 **Stormtrooper Barracks**: 'At the beginning of your upkeep, create a 2/1 black Human Empire Trooper creature token.'
- L5337 **Droid Foundry**: 'At the beginning of your upkeep, create a 1/1 colorless Droid artifact creature token. Droids you control get '

### `_swr_s11_etb_artifact_holocron` — 3 cards
- L5297 **Jedi Holocron**: '{T}: Add one mana of any color. Spend this mana only to cast creature spells or activate abilities of creature'
- L5305 **Sith Holocron**: '{T}, Pay 1 life: Add {B}{B}. {2}, {T}: Each opponent loses 1 life and you gain 1 life.'
- L5321 **Kyber Crystal**: '{T}: Add {C}. {T}, Sacrifice Kyber Crystal: Add one mana of any color. If you control a Jedi or Sith, add two '

### `_swr_s11_etb_artifact_hyperdrive` — 1 cards
- L5361 **Hyperdrive**: 'Vehicles you control have haste. {2}, {T}: Untap target Vehicle.'

### `_swr_s11_etb_artifact_jetpack` — 1 cards
- L5070 **Jetpack**: 'Equipped creature has flying and haste.'

### `_swr_s11_etb_artifact_remote` — 1 cards
- L5993 **Training Remote**: "{2}, {T}: Target creature you control gains first strike until end of turn. If it's a Jedi, it also gets +1/+1"

### `_swr_s11_etb_artifact_restraining` — 1 cards
- L6001 **Restraining Bolt**: "Enchant artifact creature. Enchanted creature can't attack or block and its activated abilities can't be activ"

### `_swr_s11_etb_artifact_shield` — 1 cards
- L5369 **Shield Generator**: 'Creatures you control have hexproof. {2}, Sacrifice Shield Generator: Creatures you control gain indestructibl'

### `_swr_s11_etb_artifact_vault` — 1 cards
- L5345 **Trade Federation Vault**: 'At the beginning of your upkeep, create a Treasure token. Sacrifice three Treasures: Draw two cards.'

### `_swr_s11_etb_eq_armor` — 2 cards
- L5052 **Mandalorian Armor**: 'Equipped creature gets +1/+3 and has protection from instants.'
- L5061 **Beskar Helmet**: 'Equipped creature gets +0/+2 and has hexproof.'

### `_swr_s11_etb_eq_blaster` — 3 cards
- L5079 **Blaster Rifle**: "Equipped creature gets +1/+0 and has '{T}: This creature deals 2 damage to any target.'"
- L5088 **Bowcaster**: "Equipped creature gets +2/+0 and has '{T}: This creature deals 3 damage to target creature.' If equipped creat"
- L5098 **Electrostaff**: 'Equipped creature gets +1/+1 and has first strike. Whenever equipped creature blocks or becomes blocked by a c'

### `_swr_s11_etb_eq_goggles` — 1 cards
- L6009 **Thermal Imaging Goggles**: "Equipped creature can't be blocked by creatures with power 2 or less."

### `_swr_s11_etb_eq_saber` — 5 cards
- L4997 **Luke's Lightsaber**: 'Equipped creature gets +2/+0 and has first strike. If equipped creature is a Jedi, it gets +3/+0 instead.'
- L5008 **Darth Vader's Lightsaber**: 'Equipped creature gets +2/+0 and has menace. If equipped creature is a Sith, it gets +3/+0 and has deathtouch.'
- L5019 **Double-Bladed Lightsaber**: 'Equipped creature gets +2/+1 and has double strike. If equipped creature is a Jedi or Sith, it gets +3/+1 inst'
- L5029 **Lightsaber**: 'Equipped creature gets +2/+0 and has first strike.'
- L5039 **Darksaber**: 'Equipped creature gets +2/+2 and has menace. Other creatures you control with Equipment attached get +1/+0.'

### `_swr_s11_etb_land_dark` — 2 cards
- L5490 **Sith Temple**: '{T}: Add {B}. {T}, Pay 1 life: Add {B}{B}. Sith creatures you control get +1/+0.'
- L5498 **Death Star Hangar**: '{T}: Add {C}. {T}: Add {B}. Spend this mana only to cast artifact or Vehicle spells.'

### `_swr_s11_etb_land_hot` — 4 cards
- L5391 **Tatooine**: '{T}: Add {C}. {1}, {T}: Add {R}{R}.'
- L5414 **Mustafar**: '{T}: Add {B} or {R}. Whenever you cast a Sith spell, Mustafar deals 1 damage to each opponent.'
- L5453 **Geonosis**: '{T}: Add {R}. {2}{R}, {T}: Create a 1/1 colorless Droid Soldier artifact creature token.'
- L6035 **Mandalore**: '{T}: Add {R} or {W}. Mandalorian creatures you control get +0/+1.'

### `_swr_s11_etb_land_lush` — 7 cards
- L5398 **Endor Forest**: '{T}: Add {G}. {2}{G}, {T}: Create a 1/1 green Ewok creature token.'
- L5406 **Kashyyyk**: '{T}: Add {G}. Wookiee creatures you control get +0/+1.'
- L5422 **Dagobah**: '{T}: Add {G} or {U}. {2}, {T}: Scry 1.'
- L5437 **Naboo**: '{T}: Add {W}, {U}, or {G}. Naboo enters tapped.'
- L5467 **Cloud City**: '{T}: Add {U} or {R}. Vehicles you control get +0/+1.'
- L5482 **Jedi Temple**: "{T}: Add {W} or {U}. Jedi creatures you control have '{T}: Add {W} or {U}.'"
- L6043 **Bespin**: "{T}: Add {U}. Vehicles you control have '{T}: Add one mana of any color.'"

### `_swr_s11_etb_land_neutral` — 9 cards
- L5383 **Coruscant**: '{T}: Add {C}. {T}: Add {W} or {U}. Activate only if you control a creature.'
- L5430 **Hoth**: '{T}: Add {W}. {T}: Target creature gets -1/-0 until end of turn.'
- L5445 **Kamino**: '{T}: Add {U}. {3}{U}, {T}: Create a 2/2 white Human Clone Soldier creature token.'
- L5460 **Jakku**: '{T}: Add {C}. {2}, {T}: Return target artifact card from your graveyard to your hand.'
- L5475 **Mos Eisley Spaceport**: '{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast creature spells.'
- L5505 **Rebel Base**: '{T}: Add {W} or {R}. Rebel creatures you control get +0/+1.'
- L6020 **Scarif**: '{T}: Add {U} or {G}. {3}, {T}: Draw a card, then discard a card.'
- L6028 **Jedha**: '{T}: Add {W}. {2}{W}, {T}: Create a 1/1 white Human Rebel creature token.'
- L6050 **Lothal**: '{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast Rebel spells.'

### `_swr_s11_etb_scry_damage_bounty` — 4 cards
- L3729 **Trandoshan Slaver**: 'Trample. When Trandoshan Slaver deals combat damage to a player, exile target creature that player controls un'
- L5805 **Aurra Sing, Sniper**: 'Reach. {T}: Aurra Sing deals 2 damage to target creature or planeswalker.'
- L5817 **Bossk, Trandoshan Hunter**: 'Trample. Whenever Bossk deals combat damage to a player, create a Treasure token for each creature that died t'
- L5829 **Fennec Shand, Elite Assassin**: 'Haste, first strike. Whenever Fennec Shand deals combat damage to a player, that player discards a card at ran'

### `_swr_s11_etb_scry_damage_mando` — 5 cards
- L4033 **Hunter's Code**: 'Bounty Hunter creatures you control get +1/+0 and have haste. Whenever a Bounty Hunter you control deals comba'
- L4042 **Arena Pit**: 'At the beginning of your upkeep, each player sacrifices a creature. Each player dealt damage this way by a cre'
- L4051 **Galactic Underworld**: 'Whenever a creature you control attacks alone, it gets +3/+0 until end of turn. At the beginning of your end s'
- L4909 **Mandalorian Forge-Master**: "When Mandalorian Forge-Master enters, create a colorless Equipment artifact token named Beskar Armor with 'Equ"
- L5841 **Death Watch Warrior**: 'Flying. When Death Watch Warrior enters, it deals 2 damage to each opponent.'

### `_swr_s11_etb_scry_discard_bounty` — 3 cards
- L3880 **Weequay Pirate**: 'When Weequay Pirate deals combat damage to a player, create a Treasure token.'
- L3926 **Pyke Enforcer**: 'First strike. {R}: Pyke Enforcer gets +1/+0 until end of turn.'
- L4931 **Hutt Crime Lord**: 'When Hutt Crime Lord enters, create two Treasure tokens. Sacrifice a creature: Hutt Crime Lord gains indestruc'

### `_swr_s11_etb_scry_discard_empire` — 2 cards
- L3565 **Galactic Empire**: 'Empire creatures you control get +1/+1. At the beginning of your end step, create a 2/1 black Human Empire Tro'
- L3574 **Rule of Two**: "You can't control more than two Sith creatures. Sith creatures you control get +2/+2 and have lifelink."

### `_swr_s11_etb_scry_drain_clone` — 2 cards
- L2147 **Coruscant Peacekeeper**: 'First strike. {1}{W}: Coruscant Peacekeeper gains lifelink until end of turn.'
- L5556 **Clone Captain Rex**: 'First strike. Other Clone creatures you control get +1/+1.'

### `_swr_s11_etb_scry_drain_empire` — 2 cards
- L5771 **Imperial Executioner**: 'Deathtouch. When Imperial Executioner enters, destroy target creature with power 2 or less.'
- L5931 **Captain Phasma**: 'First strike. Other Empire creatures you control get +1/+1. When Captain Phasma dies, create two 2/1 black Hum'

### `_swr_s11_etb_scry_drain_jedi` — 10 cards
- L2205 **Rebellion Sympathizer**: 'When Rebellion Sympathizer dies, create a 1/1 white Human Rebel Soldier creature token.'
- L2400 **Rebel Alliance**: 'Rebel creatures you control get +1/+1. At the beginning of your end step, if you control four or more Rebels, '
- L2409 **Jedi Sanctuary**: "Jedi creatures you control have hexproof and can't be sacrificed."
- L2568 **Jedi Scholar**: 'Whenever you scry, if you put one or more cards on the bottom of your library, draw a card.'
- L2790 **Jedi Investigator**: "Flash. When Jedi Investigator enters, look at target player's hand."
- L4920 **Force Sensitive**: 'When Force Sensitive enters, scry 2. Force 1 - Pay 1 life: Draw a card.'
- L5627 **Alderaanian Refugee**: 'When Alderaanian Refugee enters, you gain 2 life.'
- L5863 **Yaddle, Jedi Council Member**: 'Whenever you cast a creature spell, you may pay {G}. If you do, put a +1/+1 counter on target creature you con'
- L5955 **Ezra Bridger, Street Kid**: 'When Ezra Bridger enters, draw a card. Ezra Bridger gets +2/+2 as long as you control another Rebel.'
- L5967 **Kanan Jarrus, Blinded Master**: 'Vigilance, hexproof from creatures. Other Jedi and Rebel creatures you control get +1/+1.'

### `_swr_s11_etb_scry_drain_rebel` — 6 cards
- L2158 **Resistance Commander**: 'When Resistance Commander enters, create a 1/1 white Human Rebel Soldier creature token. Rebel creatures you c'
- L4887 **Rebel Commando Team**: 'Trample. When Rebel Commando Team enters, create a 1/1 white Human Rebel Soldier creature token.'
- L5568 **Bail Organa**: 'When Bail Organa enters, search your library for a Rebel creature card with mana value 2 or less, reveal it, p'
- L5580 **Mon Mothma**: 'Rebel spells you cast cost {1} less to cast. At the beginning of your end step, if you control three or more R'
- L5943 **Sabine Wren, Mandalorian Artist**: 'Haste. When Sabine Wren enters, you may destroy target artifact. If you do, Sabine Wren deals 2 damage to its '
- L5979 **Hera Syndulla, Ghost Captain**: 'Flying. Pilot - When Hera Syndulla crews a Vehicle, that Vehicle gets +2/+2 and gains vigilance until end of t'

### `_swr_s11_etb_scry_gain_beast` — 9 cards
- L4352 **Felucia Beast**: "Trample. Felucia Beast can't be blocked by creatures with power 2 or less."
- L4396 **Gungan Warrior**: 'When Gungan Warrior enters, add {G}.'
- L4407 **Yavin Jungle Cat**: "Haste. Yavin Jungle Cat can't be blocked by more than one creature."
- L4418 **Endor Wildlife**: 'When Endor Wildlife dies, you gain 3 life.'
- L4429 **Sarlacc Pit Spawn**: 'Defender, reach. When Sarlacc Pit Spawn blocks a creature, exile that creature at end of combat.'
- L4536 **Ewok Village**: "At the beginning of your upkeep, create a 1/1 green Ewok creature token. Ewoks you control have '{T}: Add {G}."
- L4545 **Kashyyyk Homeland**: 'Wookiee creatures you control get +2/+2 and have vigilance. Whenever a Wookiee you control deals combat damage'
- L4554 **The Living Force**: 'Whenever a creature enters under your control, you gain 1 life. {2}{G}: Create a 1/1 green Beast creature toke'
- L5897 **Rancor**: "Trample. Rancor can't be blocked by creatures with power 2 or less."

### `_swr_s11_etb_scry_gain_ewok` — 1 cards
- L5886 **Ewok Shaman**: '{T}: Add {G}. {2}{G}, {T}: Target creature you control gets +2/+2 until end of turn.'

### `_swr_s11_etb_scry_gain_wookiee` — 1 cards
- L5875 **Wookiee Berserker**: 'Trample. Wookiee Berserker gets +2/+0 as long as a creature died this turn.'

### `_swr_s11_etb_scry_reveal` — 3 cards
- L2733 **Coruscant Archivist**: '{1}{U}, {T}: Draw a card, then discard a card. If you discarded a creature card, draw another card.'
- L4385 **Naboo Ranger**: 'When Naboo Ranger enters, search your library for a basic land card, reveal it, put it into your hand, then sh'
- L4898 **Separatist Commander**: 'When Separatist Commander enters, each opponent discards a card. Then you draw a card.'

### `_swr_s11_etb_starship_falcon` — 5 cards
- L3767 **Podracer**: 'Haste. Pilot - When Podracer crews a Vehicle, that Vehicle gains haste until end of turn.'
- L5158 **Millennium Falcon**: 'Flying, haste. Whenever Millennium Falcon deals combat damage to a player, draw two cards.'
- L5200 **Slave I**: 'Flying. Whenever Slave I deals combat damage to a player, exile target creature that player controls until Sla'
- L5251 **Podracer**: 'Haste. Podracer can attack the turn it enters. At the beginning of your end step, sacrifice Podracer unless yo'
- L5261 **The Razor Crest**: 'Flying. Whenever The Razor Crest deals combat damage to a player, create a Treasure token. You may pay {2}: Pu'

### `_swr_s11_etb_starship_gunship` — 2 cards
- L5241 **Republic Gunship**: 'Flying. When Republic Gunship enters, create a 2/2 white Human Clone Soldier creature token.'
- L5272 **Y-Wing Bomber**: 'Flying. When Y-Wing Bomber attacks, it deals 2 damage to target creature defending player controls.'

### `_swr_s11_etb_starship_scout` — 3 cards
- L5169 **X-Wing Starfighter**: 'Flying. When X-Wing Starfighter attacks, it deals 1 damage to any target.'
- L5179 **TIE Fighter**: 'Flying. When TIE Fighter dies, it deals 2 damage to any target.'
- L5211 **Speeder Bike**: "Haste. Speeder Bike can't be blocked by creatures with power 3 or greater."

### `_swr_s11_etb_starship_walker` — 3 cards
- L5189 **Star Destroyer**: "Flying, vigilance. Star Destroyer can't be blocked except by creatures with flying."
- L5221 **AT-AT Walker**: "Trample. AT-AT Walker can't be blocked by creatures with power 2 or less."
- L5231 **AT-ST Walker**: 'Menace. When AT-ST Walker attacks, it deals 1 damage to each creature defending player controls.'

### `_swr_s11_etb_surveil_mill_droid` — 11 cards
- L2550 **Protocol Droid**: '{T}: Add {U}. Spend this mana only to cast artifact spells.'
- L2616 **Battle Droid**: 'When Battle Droid dies, you may pay {1}. If you do, create a 1/1 colorless Droid Soldier artifact creature tok'
- L2627 **Probe Droid**: "Flying. When Probe Droid enters, look at target opponent's hand."
- L2744 **Holo-Projector Droid**: "{T}: Create a token that's a copy of target creature you control, except it's an illusion in addition to its o"
- L2906 **Droid Factory**: "At the beginning of your upkeep, create a 1/1 colorless Droid creature token. Droids you control have '{T}: Ad"
- L2915 **Jedi Archives**: 'Whenever you cast an instant or sorcery spell, scry 1. {2}{U}: Draw a card. Activate only once each turn.'
- L3834 **Separatist Battle Droid**: 'Haste. When Separatist Battle Droid dies, it deals 1 damage to any target.'
- L5649 **BB-8, Loyal Astromech**: "When BB-8 enters, scry 2. {T}: Target Vehicle you control can't be blocked this turn."
- L5661 **K-2SO, Reprogrammed**: 'When K-2SO enters, draw two cards, then discard a card. K-2SO can block any number of creatures.'
- L5673 **Super Battle Droid**: 'When Super Battle Droid enters, create a 1/1 colorless Droid Soldier artifact creature token.'
- L5684 **Tactical Droid**: 'Other Droid creatures you control get +0/+1. {T}: Scry 1.'

### `_swr_s11_etb_surveil_mill_sith` — 5 cards
- L3425 **Dark Side Adept**: 'Dark Side - At the beginning of your upkeep, if you have less than 10 life, each opponent loses 1 life and you'
- L4873 **Darth Sidious, Puppetmaster**: 'At the beginning of your upkeep, gain control of target creature with the least power. At the beginning of eac'
- L5747 **Darth Bane, Rule Creator**: 'Menace, lifelink. At the beginning of your upkeep, you may sacrifice another creature. If you do, put two +1/+'
- L5759 **Grand Inquisitor**: 'Flying, deathtouch. Whenever Grand Inquisitor deals combat damage to a player, that player exiles a creature c'
- L5782 **Snoke, Supreme Leader**: 'At the beginning of your upkeep, each opponent loses 2 life. You gain life equal to the life lost this way.'

### `_swr_s11_resolve_black_v1` — 4 cards
- L3456 **Imperial Execution**: "Destroy target creature. Its controller loses life equal to that creature's toughness."
- L3474 **Fear Itself**: "Target creature can't block this turn. Its controller loses 2 life."
- L3503 **Imperial Bombardment**: 'Each creature gets -2/-2 until end of turn. You may sacrifice a creature. If you do, draw two cards.'
- L3512 **Harvest Despair**: 'Each opponent sacrifices a creature. If you control a Sith, each opponent also discards a card.'

### `_swr_s11_resolve_black_v2` — 3 cards
- L4944 **Balance of the Force**: 'Destroy target creature with the greatest power. You gain life equal to its power.'
- L4982 **Devastation of Alderaan**: 'Destroy all lands target player controls. That player may search their library for two basic land cards and pu'
- L5794 **Dark Ritual of the Sith**: 'Add {B}{B}{B}. You lose 1 life.'

### `_swr_s11_resolve_black_v3` — 4 cards
- L3447 **Dark Side Corruption**: 'Target creature gets -2/-2 until end of turn. You lose 2 life.'
- L3483 **Betrayal**: 'Destroy target creature. If it was legendary, draw two cards.'
- L3494 **Order 66**: 'Destroy all creatures. You lose 1 life for each creature you controlled that was destroyed this way.'
- L3521 **Conscription**: "Return target creature card from your graveyard to the battlefield. It's a black Empire Trooper in addition to"

### `_swr_s11_resolve_blue_v1` — 4 cards
- L2848 **Force Vision**: 'Look at the top four cards of your library. Put one into your hand and the rest on the bottom of your library '
- L2857 **Tech Override**: 'Counter target artifact spell. Draw a card.'
- L2886 **Clone Army**: "For each creature you control, create a token that's a copy of that creature. Those tokens gain haste. Exile t"
- L2895 **Hologram Transmission**: 'Scry 3, then draw a card.'

### `_swr_s11_resolve_blue_v2` — 3 cards
- L2803 **Jedi Mind Trick**: 'Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn.'
- L2830 **Hyperspace Jump**: "Return all creatures you control to their owner's hands. Draw a card for each creature returned this way."
- L2877 **Memory Wipe**: 'Target player puts the top eight cards of their library into their graveyard. Draw two cards.'

### `_swr_s11_resolve_blue_v3` — 3 cards
- L2821 **Holographic Decoy**: 'Counter target spell unless its controller pays {2}. If you control a Droid, counter that spell unless its con'
- L2839 **Sensor Scramble**: 'Counter target activated or triggered ability.'
- L2868 **Droid Fabrication**: 'Create three 1/1 colorless Droid creature tokens. Draw a card for each artifact you control.'

### `_swr_s11_resolve_green_v1` — 3 cards
- L4478 **Jungle Growth**: 'Put two +1/+1 counters on target creature. It gains trample until end of turn.'
- L4498 **Call of the Wild**: 'Create a 4/4 green Beast creature token with trample. Then create a 2/2 green Beast creature token.'
- L4507 **Ewok Uprising**: 'Create four 1/1 green Ewok creature tokens. Ewoks you control gain trample until end of turn.'

### `_swr_s11_resolve_green_v2` — 3 cards
- L4442 **Wookiee Rage**: "Target creature gets +4/+4 until end of turn. If it's a Wookiee, it also gains trample until end of turn."
- L4460 **Ewok Trap**: "Tap target creature. It doesn't untap during its controller's next untap step. If you control an Ewok, draw a "
- L4525 **Rampant Growth**: 'Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.'

### `_swr_s11_resolve_green_v3` — 3 cards
- L4469 **Natural Camouflage**: 'Target creature gains hexproof and indestructible until end of turn.'
- L4487 **Primal Connection**: 'Draw cards equal to the greatest power among creatures you control.'
- L5920 **Beast Call**: 'Search your library for a Beast creature card with mana value 4 or less, reveal it, put it into your hand, the'

### `_swr_s11_resolve_red_v1` — 5 cards
- L3939 **Blaster Bolt**: 'Blaster Bolt deals 3 damage to target creature.'
- L3975 **Reckless Assault**: 'Creatures you control get +2/+0 until end of turn. They attack this turn if able.'
- L4013 **Rage of the Arena**: 'Creatures you control get +2/+0 and gain trample until end of turn. They must attack this turn if able.'
- L4962 **Unity of the Rebellion**: 'Creatures you control get +2/+0 and gain vigilance until end of turn.'
- L5852 **Wrist Rocket**: 'Wrist Rocket deals 2 damage to any target. If you control a Mandalorian, it deals 3 damage instead.'

### `_swr_s11_resolve_red_v2` — 4 cards
- L3465 **Sith Lightning**: 'Sith Lightning deals 3 damage to target creature or planeswalker. You gain 3 life.'
- L3984 **Disintegrate**: 'Disintegrate deals X damage to any target. If a creature dealt damage this way would die this turn, exile it i'
- L4004 **Bounty Collection**: 'Destroy target creature. Create a Treasure token for each Bounty Hunter you control.'
- L4022 **Hired Guns**: 'Create two 3/2 red Human Bounty Hunter creature tokens with haste.'

### `_swr_s11_resolve_red_v3` — 4 cards
- L3948 **Thermal Detonator**: 'Thermal Detonator deals 4 damage to target creature or planeswalker. If that creature or planeswalker would di'
- L3957 **Aggressive Negotiations**: 'Target creature you control gets +2/+0 and gains first strike until end of turn. It must attack this turn if a'
- L3966 **Bounty Posted**: "Target creature can't block this turn. If you control a Bounty Hunter, Bounty Posted deals 2 damage to that cr"
- L3995 **Orbital Strike**: 'Orbital Strike deals 4 damage to each creature and each player.'

### `_swr_s11_resolve_scry_gain_ally` — 2 cards
- L4451 **Forest Ambush**: "Target creature you control fights target creature you don't control."
- L4516 **Force of Nature**: 'Put four +1/+1 counters on target creature you control. It gains trample and hexproof until end of turn.'

### `_swr_s11_resolve_scry_gain_drain` — 2 cards
- L4973 **Galactic Senate Decree**: "Choose one - Destroy target creature; or counter target spell; or return target permanent to its owner's hand."
- L5638 **Force Barrier**: 'Prevent all damage that would be dealt to creatures you control this turn. If you control a Jedi, draw a card.'

### `_swr_s11_resolve_surveil_discard` — 1 cards
- L3438 **Force Choke**: 'Target creature gets -3/-3 until end of turn. If you control a Sith, it gets -5/-5 instead.'

### `_swr_s11_resolve_surveil_mill` — 3 cards
- L2812 **Force Push**: "Return target creature to its owner's hand. If you control a Jedi, scry 1."
- L4953 **Force Lightning**: 'Force Lightning deals 4 damage to any target. If you control a Sith, Force Lightning deals 6 damage instead.'
- L5736 **Force Illusion**: "Create a token that's a copy of target creature you control, except it's an illusion with 'Sacrifice this crea"

### `_swr_s11_resolve_white_v1` — 3 cards
- L2291 **Force Protection**: "Target creature you control gains indestructible until end of turn. If it's a Jedi, you also gain 3 life."
- L2318 **Hope Renewed**: 'You gain 4 life. Light Side - If you have 10 or more life, draw a card.'
- L2374 **Evacuation Plan**: "Return up to two target creatures you control to their owner's hand. You gain 3 life."

### `_swr_s11_resolve_white_v2` — 3 cards
- L2336 **Light of the Force**: 'Exile target creature with power 4 or greater. Its controller gains life equal to its toughness.'
- L2347 **Call to Arms**: 'Create four 1/1 white Human Rebel Soldier creature tokens. You gain 1 life for each creature you control.'
- L2356 **Liberation Day**: 'Destroy all creatures with power 4 or greater. You gain 2 life for each creature destroyed this way.'

### `_swr_s11_resolve_white_v3` — 3 cards
- L2309 **Jedi Reflexes**: "Target creature gains first strike until end of turn. If it's a Jedi, it also gains lifelink until end of turn"
- L2327 **Defensive Formation**: 'Creatures you control get +0/+2 until end of turn. Untap those creatures.'
- L2365 **Jedi Training**: 'Target creature becomes a Jedi in addition to its other types and gets +1/+1 until end of turn. Draw a card.'

### `_swr_s11_resolve_white_v4` — 1 cards
- L2300 **Rebel Ambush**: 'Create three 1/1 white Human Rebel Soldier creature tokens. They gain haste until end of turn.'
