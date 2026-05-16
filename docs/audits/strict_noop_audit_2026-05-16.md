# Strict Noop Audit — 2026-05-16

Authoritative count of `setup_interceptors` stubs whose body is functionally a no-op across all 12 real MTG sets. This document supersedes earlier counts in `engine_gaps.md` that were based on a stale `HELPER_NAMES` allow-list in `scripts/find_useless_stubs.py`.

## Methodology

Two independent audits were run side-by-side:

1. **`scripts/strict_noop_audit.py`** — pure AST structural check. Flags only functions whose body, modulo a leading docstring, is literally `return []`. No helper-name allowlist; cannot be wrong about an allowlist drift.
2. **`scripts/find_useless_stubs.py`** — allowlist-based classifier. Counts as noop any function that has no top-level helper call AND no Event emission. Updated 2026-05-16 to include all helpers shipped since Phase 5b (crime/saddle/plot/bend/eerie/survival/impending/disguise/shockland/ward/cost-reduction/cycling/saga/replacement/equipment/aura/activated-ability + 100 other names). Pre-fix HELPER_NAMES was missing all of these and over-reported noops at 573; post-fix value is 192.

The find script's 192 includes 23 functions with non-trivial bodies (closures defined but never registered with a helper) — these are functionally noops but not bare `return []`. The strict audit's 169 is the conservative lower bound. **The truth lies between**, with 169 strict + 23 = 192 functionally-useless setups.

## Headline numbers

| Audit                                  | Total noops |
|----------------------------------------|------------:|
| `find_useless_stubs.py` (pre-fix)      | 573         |
| `find_useless_stubs.py` (post-fix)     | 192         |
| `strict_noop_audit.py`                 | 169         |

That's a **3.0–3.4x correction** from the inflated baseline. The 573 number was driving Phase 5b prioritization and led to wasted sweeps targeting functions that were already correctly wired (just using helpers absent from the allowlist).

## Per-set breakdown

Below: strict-audit numbers (bare `return []`) per set, plus the find script's delta. `wired` is the count of all setup functions referenced via `setup_interceptors=` or `setup_in_graveyard=` in the file.

| Set | code | wired | strict-noop | delegated | find-script-noop |
|-----|------|------:|------------:|----------:|-----------------:|
| wilds_of_eldraine | WOE | 157 | 12 | 0 | 12 |
| lost_caverns_ixalan | LCI | 206 | 0 | 0 | 2 |
| murders_karlov_manor | MKM | 202 | 15 | 0 | 15 |
| outlaws_thunder_junction | OTJ | 202 | 13 | 4 | 13 |
| bloomburrow | BLB | 198 | 10 | 0 | 11 |
| duskmourn | DSK | 200 | 32 | 0 | 32 |
| foundations | FDN | 346 | 10 | 0 | 13 |
| edge_of_eternities | EOE | 171 | 12 | 2 | 13 |
| lorwyn_eclipsed | ECL | 194 | 24 | 0 | 34 |
| spider_man | SPM | 152 | 13 | 0 | 16 |
| avatar_tla | TLA | 197 | 15 | 0 | 17 |
| final_fantasy | FIN | 196 | 13 | 0 | 14 |
| **TOTAL** | | **2421** | **169** | **6** | **192** |

## True noops by mechanic blocker

Categorization is heuristic, applied by string-matching the strict-audit descriptors (which are themselves a mix of docstrings and inline `engine gap:` comments). One card may be blocked by multiple mechanics; we pick a primary.

### uncategorized (55 cards)

- **WOE** `virtue_of_knowledge_setup` (L4940, wilds_of_eldraine.py) — Permanent ETB triggers double for permanents you control.
- **WOE** `raging_battle_mouse_setup` (L5372, wilds_of_eldraine.py) — Second spell each turn costs {1} less; celebration combat +1/+1 EOT.
- **WOE** `verdant_outrider_setup` (L5477, wilds_of_eldraine.py) — {1}{G}: This creature can't be blocked by creatures with power 2 or less this turn.
- **WOE** `virtue_of_strength_setup` (L5483, wilds_of_eldraine.py) — Tapping a basic land for mana produces three times as much.
- **MKM** `doorkeeper_thrull_setup` (L2048, murders_karlov_manor.py) — Artifacts and creatures entering don't cause abilities to trigger
- **MKM** `delney_streetwise_lookout_setup` (L2054, murders_karlov_manor.py) — Creatures with power 2 or less can't be blocked by power 3+. Ability triggers twice.
- **MKM** `assemble_the_players_setup` (L5603, murders_karlov_manor.py) — Look at top of library; once/turn cast creature with power 2 or less from top.
- **MKM** `burden_of_proof_setup` (L6059, murders_karlov_manor.py) — Aura: conditional P/T based on whether enchanted creature is your Detective.
- **MKM** `pompous_gadabout_setup` (L6923, murders_karlov_manor.py) — During your turn hexproof; can't be blocked by creatures without name.
- **MKM** `leyline_of_the_guildpact_setup` (L7348, murders_karlov_manor.py) — Opening-hand on battlefield. Each nonland permanent is all colors. Lands every basic land type.
- **OTJ** `archangel_of_tithes_setup` (L2126, outlaws_thunder_junction.py) — Flying. Tax-attack/tax-block static abilities.
- **OTJ** `bristlepack_sentry_setup` (L2978, outlaws_thunder_junction.py) — Defender; conditional attack permission.
- **OTJ** `kambal_profiteering_mayor_setup` (L3527, outlaws_thunder_junction.py) — Token ETB triggers (mirror your opponent's; drain on yours).
- **OTJ** `lilah_undefeated_slickshot_setup` (L3584, outlaws_thunder_junction.py) — Prowess; multicolored instant/sorcery -> exile and plot instead.
- **BLB** `mockingbird_setup` (L2633, bloomburrow.py) — engine gap: enter-as-copy with X mana value cap
- **DSK** `patched_plaything_setup` (L1705, duskmourn.py) — Enters with two -1/-1 counters if cast from hand.
- **DSK** `shardmages_rescue_setup` (L1796, duskmourn.py) — Aura — entered-this-turn hexproof + +1/+1 on enchanted.
- **DSK** `creeping_peeper_setup` (L2242, duskmourn.py) — {T}: Add {U}, restricted-use mana for enchantments / unlock / face-up.
- **DSK** `grievous_wound_setup` (L2901, duskmourn.py) — Enchant player — can't gain life, half-life-on-damage.
- **DSK** `aleyline_of_resonance_setup` (L3351, duskmourn.py) — A-version: pay {1} to copy.
- **DSK** `zimone_allquestioning_setup` (L4482, duskmourn.py) — End step — if a land entered and prime # of lands, create Primo + counters.
- **DSK** `terramorphic_expanse_setup` (L4696, duskmourn.py) — {T}+sac: search basic land tapped.
- **FDN** `fishing_pole_setup` (L7385, foundations.py) — engine gap: equipment with granted ability and untap trigger
- **FDN** `desecration_demon_setup` (L8719, foundations.py) — engine gap: combat-step opponent may sacrifice
- **EOE** `mechan_shieldmate_setup` (L2452, edge_of_eternities.py) — Defender; can attack as though it didn't have defender if an artifact entered this turn.
- **EOE** `mmmenon_the_right_hand_setup` (L2458, edge_of_eternities.py) — Flying; look at top; cast artifacts from top; artifacts you control tap for {U} (specific use).
- **EOE** `moonlit_meditation_setup` (L2464, edge_of_eternities.py) — Aura: first time you would create tokens each turn, create copies of enchanted permanent instead.
- **EOE** `uthros_psionicist_setup` (L2517, edge_of_eternities.py) — The second spell you cast each turn costs {2} less.
- **EOE** `requiem_monolith_setup` (L2657, edge_of_eternities.py) — {T}: until EOT, target creature gains 'when damaged, controller draws cards and loses life'.
- **EOE** `xuifit_osteoharmonist_setup` (L2705, edge_of_eternities.py) — {T}: Return target creature card from your GY to BF as a Skeleton, no abilities.
- **EOE** `frenzied_baloth_setup` (L2958, edge_of_eternities.py) — Trample, haste; uncounterable; creatures uncounterable; combat damage uncovered.
- **EOE** `the_eternity_elevator_setup` (L3347, edge_of_eternities.py) — {T}: Add CCC. Station 20+: {T}: Add X mana of any one color (X = charge counters).
- **EOE** `survey_mechan_setup` (L3354, edge_of_eternities.py) — Flying; hexproof; {10},sac: 3 dmg to any target + target player draws 3 + gains 3 life.
- **EOE** `adagia_windswept_bastion_setup` (L3375, edge_of_eternities.py) — Land enters tapped; {T}: Add W; Station 12+ | {3}{W},{T}: copy target artifact/enchantment as legendary token.
- **ECL** `twinflame_travelers_setup` (L1489, lorwyn_eclipsed.py) — Static: Triggered abilities of other Elementals trigger an additional time.
- **ECL** `champion_of_the_weird_setup` (L2141, lorwyn_eclipsed.py) — Behold-a-Goblin cost on cast; LtB return.
- **ECL** `mornsong_aria_setup` (L2190, lorwyn_eclipsed.py) — Static: players can't draw or gain life. Draw step: lose 3, tutor.
- **ECL** `bloom_tender_setup` (L2446, lorwyn_eclipsed.py) — Vivid tap-for-mana: produce one of each color (engine gap).
- **ECL** `bristlebane_outrider_setup` (L2451, lorwyn_eclipsed.py) — +2/+0 if another creature entered this turn; can't be blocked by power<=2.
- **ECL** `shimmerwilds_growth_setup` (L2652, lorwyn_eclipsed.py) — Aura on a land: grants color and extra mana (engine gap).
- **ECL** `chitinous_graspling_setup` (L2755, lorwyn_eclipsed.py) — Static: reach (granted via baseline keyword); changeling already a keyword.
- **ECL** `gangly_stompling_setup` (L2825, lorwyn_eclipsed.py) — Trample + changeling — both already on card text (no extra interceptors).
- **ECL** `mischievous_sneakling_setup` (L2873, lorwyn_eclipsed.py) — Flash + changeling — already on card text.
- **ECL** `prideful_feastling_setup` (L2878, lorwyn_eclipsed.py) — Lifelink + changeling — already on card text.
- **SPM** `multiversal_passage_setup` (L3354, spider_man.py) — (no descriptor)
- **SPM** `oscorp_industries_setup` (L3366, spider_man.py) — (no descriptor)
- **TLA** `katara_the_fearless_setup` (L1719, avatar_tla.py) — If a triggered ability of an Ally you control triggers, that ability triggers an additional time.
- **TLA** `foggy_swamp_vinebender_setup` (L3668, avatar_tla.py) — Can't be blocked by power 2 or less (engine gap).
- **TLA** `great_divide_guide_setup` (L3675, avatar_tla.py) — Each land and Ally has '{T}: Add one mana of any color' (engine gap).
- **FIN** `demon_wall_ff_setup` (L3927, final_fantasy.py) — Demon Wall: defender + can attack if has counter (stub).
- **FIN** `a_realm_reborn_ff_setup` (L4621, final_fantasy.py) — A Realm Reborn: Other permanents you control have {T}: Add any color (stub).
- **FIN** `absolute_virtue_ff_setup` (L4861, final_fantasy.py) — Absolute Virtue: protection from each opponent (stub).
- **FIN** `aettir_and_priwen_ff_setup` (L5180, final_fantasy.py) — Aettir and Priwen Equipment: equipped creature has base P/T = your life total (stub).
- **FIN** `the_masamune_ff_setup` (L5246, final_fantasy.py) — The Masamune Equipment: extra combat damage triggers if equipped attacking (stub).
- **FIN** `cloud_planets_champion_ff_setup` (L5368, final_fantasy.py) — Cloud, Planet's Champion: when equipped, double strike + indestructible during your turn (stub).

### activated-misc (36 cards)

- **WOE** `embereth_veteran_setup` (L5290, wilds_of_eldraine.py) — Activated: {1}, sac self: Young Hero Role token attached to another creature.
- **WOE** `food_fight_setup` (L5296, wilds_of_eldraine.py) — Artifacts you control gain a sacrificial activated ability.
- **WOE** `goddric_cloaked_reveler_setup` (L5302, wilds_of_eldraine.py) — Haste; celebration: becomes Dragon 4/4 flying with activated ability.
- **WOE** `agatha_of_the_vile_cauldron_setup` (L5533, wilds_of_eldraine.py) — Activated abilities of creatures you control cost {X} less, where X is Agatha's power; activated team buff.
- **MKM** `tenth_district_hero_setup` (L5930, murders_karlov_manor.py) — Activated abilities to become Detective then Mileva legendary.
- **MKM** `leering_onlooker_setup` (L6422, murders_karlov_manor.py) — Flying. Activated graveyard ability creates two 1/1 black Bats.
- **MKM** `hedge_whisperer_setup` (L6865, murders_karlov_manor.py) — May skip untap. Activated: animate land 5/5 while tapped.
- **MKM** `gravestone_strider_setup` (L7544, murders_karlov_manor.py) — Activated mana ability (once/turn). Activated graveyard exile-target.
- **OTJ** `high_noon_setup` (L2198, outlaws_thunder_junction.py) — Each player can't cast more than one spell each turn; activated damage.
- **OTJ** `colossal_rattlewurm_setup` (L3034, outlaws_thunder_junction.py) — Conditional flash; trample; activated graveyard-exile tutor.
- **BLB** `baylen_the_haymaker_setup` (L4269, bloomburrow.py) — engine gap: three activated abilities with "tap N untapped tokens you control"
- **BLB** `lilysplash_mentor_setup` (L4541, bloomburrow.py) — engine gap: activated {1}{G}{U} sorcery-speed flicker-with-+1/+1 ability
- **BLB** `mudflat_village_setup` (L5105, bloomburrow.py) — engine gap: restricted mana ability ({B} for creature spells); activated
- **BLB** `rockface_village_setup` (L5111, bloomburrow.py) — engine gap: restricted mana ability; activated {R}{T} sorcery-speed tribal
- **DSK** `balustrade_wurm_setup` (L3616, duskmourn.py) — Trample, haste; Delirium activated reanimate.
- **FDN** `reassembling_skeleton_setup` (L7638, foundations.py) — Phase 5b sweep: setup on battlefield is a noop; the activated graveyard
- **FDN** `suspicious_shambler_setup` (L8255, foundations.py) — Phase 5b sweep: on-battlefield setup intentionally empty; the activated
- **ECL** `dawnhand_dissident_setup` (L2149, lorwyn_eclipsed.py) — Activated tap+blight abilities (engine gap).
- **ECL** `meek_attack_setup` (L2344, lorwyn_eclipsed.py) — Activated cheat creature into play and sacrifice EOT (engine gap).
- **ECL** `kirol_attentive_firstyear_setup` (L2837, lorwyn_eclipsed.py) — Tap-two-creatures activated copy ability (engine gap).
- **ECL** `stoic_groveguide_setup` (L2923, lorwyn_eclipsed.py) — Activated graveyard ability: create Elf token (engine gap).
- **ECL** `tam_mindful_firstyear_setup` (L3002, lorwyn_eclipsed.py) — Static hexproof from each color; activated all-colors (engine gap).
- **SPM** `beetle_legacy_criminal_setup` (L1903, spider_man.py) — Activated graveyard ability (Aftermath-style).
- **SPM** `venom_evil_unleashed_setup` (L2287, spider_man.py) — Deathtouch + activated graveyard ability.
- **SPM** `radioactive_spider_setup` (L2620, spider_man.py) — Reach + deathtouch + activated tutor.
- **SPM** `morbius_the_living_vampire_setup` (L2849, spider_man.py) — Flying/vigilance/lifelink + activated graveyard "look at top 3, hand 1."
- **SPM** `bagel_and_schmear_setup` (L3023, spider_man.py) — Activated abilities only.
- **TLA** `water_tribe_rallier_setup` (L2330, avatar_tla.py) — Waterbend {5}: tutor from top 4 (engine gap activated + waterbend).
- **TLA** `flexible_waterbender_setup` (L2353, avatar_tla.py) — Waterbend {3}: base power/toughness 5/2 EOT (engine gap activated + base stat swap).
- **TLA** `geyser_leaper_setup` (L2359, avatar_tla.py) — Waterbend {4}: loot. Engine gap (activated + waterbend).
- **TLA** `yue_the_moon_spirit_setup` (L2710, avatar_tla.py) — Waterbend {5}, {T}: cast a noncreature spell free (engine gap activated + waterbend).
- **TLA** `merchant_of_many_hats_setup` (L2984, avatar_tla.py) — Battlefield-side has no abilities; activated ability lives in the
- **TLA** `trusty_boomerang_setup` (L4268, avatar_tla.py) — Equipped creature has {1}, {T}: tap creature, return Boomerang (engine gap granted activated).
- **TLA** `fire_nation_palace_setup` (L4289, avatar_tla.py) — ETB tapped unless basic. Activated firebending 4 grant (engine gap).
- **FIN** `ether_ff_setup` (L3545, final_fantasy.py) — Ether: activated ability with delayed copy trigger (stub).
- **FIN** `the_wandering_minstrel_ff_setup` (L5067, final_fantasy.py) — The Wandering Minstrel: lands enter untapped + combat trigger if 5+ Towns + activated boost (stub).

### modal-mid-resolve (11 cards)

- **WOE** `three_bowls_of_porridge_setup` (L5984, wilds_of_eldraine.py) — Modal activated: damage / tap / sac for life.
- **OTJ** `riku_of_many_paths_setup` (L3784, outlaws_thunder_junction.py) — Whenever you cast a modal spell, choose up to X modes.
- **DSK** `leyline_of_transformation_setup` (L2286, duskmourn.py) — Choose a creature type; all your creatures (and creature spells, hand cards) gain it.
- **DSK** `silent_hallcreeper_setup` (L2505, duskmourn.py) — Unblockable; on combat damage to player, modal effect (one-of-three, no repeats).
- **FDN** `sorcerous_spyglass_setup` (L9236, foundations.py) — engine gap: choose-name + activation prohibition
- **ECL** `collective_inferno_setup` (L2248, lorwyn_eclipsed.py) — Choose-a-type then double damage (engine gap).
- **ECL** `chronicle_of_victory_setup` (L3023, lorwyn_eclipsed.py) — As-enters type choice; static +2/+2 + first strike + trample to type.
- **ECL** `dawnblessed_pennant_setup` (L3031, lorwyn_eclipsed.py) — As-enters type choice; type ETB life gain (engine gap).
- **ECL** `gathering_stone_setup` (L3052, lorwyn_eclipsed.py) — As-enters type choice + cost reduction + library look (engine gap).
- **TLA** `zuko_conflicted_setup` (L4171, avatar_tla.py) — Beg of first main: choose unchosen mode and lose 2 life (engine gap).
- **FIN** `phoenix_down_ff_setup` (L3341, final_fantasy.py) — Phoenix Down: activated ability with modal choice (stub).

### activated-from-graveyard (8 cards)

- **WOE** `dutiful_griffin_setup` (L4312, wilds_of_eldraine.py) — Activated ability from graveyard to return self to hand.
- **WOE** `redtooth_vanguard_setup` (L5465, wilds_of_eldraine.py) — Whenever an enchantment you control enters, optional pay to return self from gy to hand.
- **BLB** `wishing_well_setup` (L2806, bloomburrow.py) — engine gap: chained {T}: counter -> gy-cast (mana-value-matching) + grave-to-exile replacement
- **BLB** `bonebind_orator_setup` (L2830, bloomburrow.py) — engine gap: activated ability with cost "{3}{B}, exile self from gy" — no
- **DSK** `undead_sprinter_setup` (L1337, duskmourn.py) — Can be cast from graveyard if a non-Zombie creature died this turn.
- **FDN** `muldrotha_the_gravetide_setup` (L7870, foundations.py) — engine gap: cast-from-graveyard (one of each permanent type) requires
- **EOE** `timeline_culler_setup` (L2672, edge_of_eternities.py) — Haste; warp from graveyard.
- **TLA** `wolfbat_setup` (L3102, avatar_tla.py) — Whenever you draw second card each turn, may pay {B} to return this from GY (engine gap).

### cycling-typecycling (8 cards)

- **MKM** `topiary_panther_setup` (L6970, murders_karlov_manor.py) — Trample. Basic landcycling {1}{G}.
- **DSK** `shepherding_spirits_setup` (L1819, duskmourn.py) — Flying + plainscycling — only static keywords, no triggered ability.
- **DSK** `daggermaw_megalodon_setup` (L2257, duskmourn.py) — Vigilance + islandcycling 2 — keyword-only.
- **DSK** `spectral_snatcher_setup` (L3002, duskmourn.py) — Ward — discard a card. Swampcycling 2 — keyword-only.
- **DSK** `slavering_branchsnapper_setup` (L3945, duskmourn.py) — Trample; forestcycling 2 — keyword-only.
- **TLA** `giant_koi_setup` (L2365, avatar_tla.py) — Waterbend {3}: unblockable EOT (engine gap). Islandcycling {2} (engine gap).
- **TLA** `sabertooth_mooselion_setup` (L3816, avatar_tla.py) — Reach. Forestcycling {2} (engine gap cycling activated ability).
- **FIN** `hill_gigas_ff_setup` (L4145, final_fantasy.py) — Hill Gigas: trample/haste keywords already on stat; cycling stub.

### replacement (7 cards)

- **WOE** `ashiok_wicked_manipulator_setup` (L5120, wilds_of_eldraine.py) — Planeswalker with replacement effect + 3 abilities.
- **DSK** `the_mindskinner_setup` (L2370, duskmourn.py) — Unblockable + replace damage to opponents with mill.
- **FDN** `herald_of_eternal_dawn_setup` (L6987, foundations.py) — engine gap: can't-lose / opponents-can't-win replacement effect
- **FDN** `high_fae_trickster_setup` (L7060, foundations.py) — engine gap: cast-as-flash replacement
- **FDN** `omniscience_setup` (L7578, foundations.py) — engine gap: free-cast replacement for owner
- **ECL** `mirrormind_crown_setup` (L3057, lorwyn_eclipsed.py) — Token replacement (engine gap).
- **SPM** `superior_spiderman_setup` (L2990, spider_man.py) — Enter as a copy of a graveyard creature (replacement).

### keyword-only-vanilla (4 cards)

- **OTJ** `akul_the_unrepentant_setup` (L3348, outlaws_thunder_junction.py) — Flying, trample (kw); activated 3-sac put-creature-from-hand.
- **OTJ** `ghired_mirror_of_the_wilds_setup` (L3471, outlaws_thunder_junction.py) — Haste (kw); grants nontoken creatures a tap-copy-token ability.
- **DSK** `piranha_fly_setup` (L2469, duskmourn.py) — Flying; enters tapped — keyword-only/state-only.
- **DSK** `fear_of_being_hunted_setup` (L3210, duskmourn.py) — Haste; must-be-blocked. Keyword-only.

### planeswalker (4 cards)

- **MKM** `kaya_spirits_justice_setup` (L7326, murders_karlov_manor.py) — Planeswalker; passive token-becomes-copy when creatures exiled. Loyalty abilities.
- **OTJ** `jace_reawakened_setup` (L4275, outlaws_thunder_junction.py) — Planeswalker with cast-restriction and loyalty abilities.
- **DSK** `kaito_bane_of_nightmares_setup` (L4203, duskmourn.py) — Planeswalker — ninjutsu, conditional creature, loyalty abilities.
- **ECL** `ajani_outland_chaperone_setup` (L1741, lorwyn_eclipsed.py) — Planeswalker abilities: token creation, damage, and library scan.

### cast-from-other-zone (3 cards)

- **OTJ** `the_key_to_the_vault_setup` (L2394, outlaws_thunder_junction.py) — Equipment combat-damage trigger -> impulse exile + free cast.
- **DSK** `charred_foyer_setup` (L3192, duskmourn.py) — Room — upkeep impulse exile / cast-from-exile {0} once per turn.
- **DSK** `norin_swift_survivalist_setup` (L3357, duskmourn.py) — Can't block; on becoming blocked, may exile + impulse.

### type-overwrite-aura (3 cards)

- **BLB** `sugar_coat_setup` (L2696, bloomburrow.py) — engine gap: Aura that overwrites types and abilities of enchanted permanent
- **FDN** `imprisoned_in_the_moon_setup` (L7555, foundations.py) — engine gap: full type-overwriting aura (strips abilities, becomes
- **SPM** `spiderman_no_more_setup` (L2181, spider_man.py) — Aura: enchanted creature becomes 1/1 Citizen with defender, loses other abilities/types.

### additional-cost-on-cast (2 cards)

- **DSK** `fear_of_isolation_setup` (L2280, duskmourn.py) — Additional cost: bounce a permanent. Flying. No ETB trigger to wire.
- **DSK** `fear_of_exposure_setup` (L3656, duskmourn.py) — Additional cost: tap two; Trample.

### alt-cost-cast (2 cards)

- **OTJ** `kellan_the_kid_setup` (L3533, outlaws_thunder_junction.py) — Flying, lifelink (kw); cast-from-not-hand may free-cast or play a land.
- **DSK** `leyline_of_mutation_setup` (L3825, duskmourn.py) — Alt cost WUBRG for any spell.

### combat-damage-swap (2 cards)

- **EOE** `tapestry_warden_setup` (L1894, edge_of_eternities.py) — Each creature you control with toughness greater than power assigns combat damage equal to toughness.
- **FIN** `kain_traitorous_dragoon_ff_setup` (L3970, final_fantasy.py) — Kain: Jump (during your turn -> flying) + combat damage swap (stub).

### convoke (2 cards)

- **DSK** `dazzling_theater_setup` (L1429, duskmourn.py) — Room (Dazzling Theater / Prop Room) — convoke grant + untap-on-other-untap.
- **DSK** `the_wandering_rescuer_setup` (L2062, duskmourn.py) — Flash + Convoke + Double strike + 'other tapped you control have hexproof'.

### discard-cost-activated (2 cards)

- **ECL** `ironshield_elf_setup` (L2185, lorwyn_eclipsed.py) — Activated discard ability: indestructible EOT and tap (engine gap).
- **SPM** `stegron_the_dinosaur_man_setup` (L2485, spider_man.py) — Menace + activated discard-self pump-to-Dinosaur. No persistent triggers.

### face-down-manifest (2 cards)

- **DSK** `stay_hidden_stay_silent_setup` (L2511, duskmourn.py) — Aura — tap on ETB; doesn't untap. Activated: shuffle + manifest dread.
- **DSK** `unable_to_scream_setup` (L2534, duskmourn.py) — Aura — enchanted is 0/2 Toy artifact, can't be turned face up if face down.

### gain-control (2 cards)

- **MKM** `coerced_to_kill_setup` (L7159, murders_karlov_manor.py) — Aura: gain control of enchanted; base 1/1 with deathtouch + Assassin type.
- **OTJ** `eriette_the_beguiler_setup` (L3465, outlaws_thunder_junction.py) — Lifelink; aura-attach -> gain control while enchanted.

### ward (2 cards)

- **MKM** `axebane_ferox_setup` (L6792, murders_karlov_manor.py) — Deathtouch, haste, ward(collect evidence 4).
- **TLA** `the_unagi_of_kyoshi_island_setup` (L2606, avatar_tla.py) — Ward-Waterbend {4} (engine gap). Whenever opp draws second card, draw two.

### ability-removal (1 cards)

- **DSK** `duskmourns_domination_setup` (L2263, duskmourn.py) — Aura — control + -3/-0 + lose abilities on enchanted.

### as-enters-choice (1 cards)

- **ECL** `rimefire_torque_setup` (L2030, lorwyn_eclipsed.py) — As-enters chosen-type charge counters; tap copy spell (engine gap).

### collect-evidence-cost (1 cards)

- **MKM** `conspiracy_unraveler_setup` (L6090, murders_karlov_manor.py) — Flying; alternative cost via collect evidence 10.

### control-transfer-aura (1 cards)

- **FIN** `stiltzkin_moogle_merchant_ff_setup` (L3372, final_fantasy.py) — Stiltzkin: lifelink + activated control transfer (stub).

### delirium (1 cards)

- **DSK** `osseous_sticktwister_setup` (L2957, duskmourn.py) — Lifelink + Delirium end-step: each opp may sac/discard or take damage = power.

### dream-counter (1 cards)

- **ECL** `goliath_daydreamer_setup` (L2262, lorwyn_eclipsed.py) — Cast + attack triggers around dream-counter exile (engine gap).

### gift (1 cards)

- **BLB** `jolly_gerbils_setup` (L2269, bloomburrow.py) — engine gap: "whenever you give a gift" hook

### infinity-stone (1 cards)

- **SPM** `the_soul_stone_setup` (L2275, spider_man.py) — Tap for {B}, harness ability, then upkeep reanimate (Infinity Stone mechanic).

### legend-rule (1 cards)

- **SPM** `spiderverse_setup` (L2479, spider_man.py) — Spiders ignore legend rule; copy spells cast from non-hand. Once per turn.

### mount-saddle (1 cards)

- **DSK** `bedhead_beastie_setup` (L3149, duskmourn.py) — Menace + mountaincycling 2 — keyword-only.

### offspring (1 cards)

- **BLB** `rustshield_rampager_setup` (L4111, bloomburrow.py) — engine gap: Offspring + power<=2 unblockability

### spell-copy (1 cards)

- **DSK** `leyline_of_resonance_setup` (L3345, duskmourn.py) — Spell-copy on cast targeting single own creature.

### tap-multiple-creatures-cost (1 cards)

- **SPM** `supportive_parents_setup` (L2718, spider_man.py) — Mana ability: tap two creatures for any color.

### vehicle (1 cards)

- **FIN** `the_lunar_whale_ff_setup` (L3621, final_fantasy.py) — The Lunar Whale Vehicle: stub (top of library / play, crew).

## Delegated setups (real-by-reference, formerly mis-classified)

These functions delegate wholesale to another wired setup. They are *not* noops; they reuse the same logic. Listed because they show up in the find-script `delegated` column and confirm the new classifier works.

### OTJ (outlaws_thunder_junction)

- `botanical_sanctum_setup` (L4255) — 
- `concealed_courtyard_setup` (L4259) — 
- `inspiring_vantage_setup` (L4263) — 
- `spirebluff_canal_setup` (L4267) — 

### EOE (edge_of_eternities)

- `synthesizer_labship_setup` (L2498) — Station 9+: becomes a creature with flying + vigilance.
- `galvanizing_sawship_setup` (L2712) — Station 3+: becomes a creature with flying + haste.

## Next-wave candidates — wirable with existing helpers

Cards that are currently strict-noop but where the engine already exposes everything needed. A focused wave could pick these up.

| # | set | card | mechanic | unblocking helper |
|---|-----|------|----------|-------------------|
| 1 | DSK | Spectral Snatcher | Ward — discard a card. Swampcycling 2. | `make_ward(obj, custom_cost='Discard a card')` + `make_cycling_setup` with `typecycling='Swamp'` |
| 2 | DSK | Daggermaw Megalodon | Vigilance + islandcycling 2 — keyword-only. | `make_cycling_setup('{2}', typecycling='Island')` |
| 3 | DSK | Shepherding Spirits | Flying + plainscycling. | `make_cycling_setup` with `typecycling='Plains'` |
| 4 | DSK | Bedhead Beastie | Menace + mountaincycling 2. | `make_cycling_setup` with `typecycling='Mountain'` |
| 5 | DSK | Slavering Branchsnapper | Trample + forestcycling 2. | `make_cycling_setup` with `typecycling='Forest'` |
| 6 | TLA | Sabertooth Mooselion | Reach. Forestcycling {2}. | `make_cycling_setup('{2}', typecycling='Forest')` |
| 7 | DSK | Piranha Fly | Flying; enters tapped. | Set `enters_tapped=True` on the card def (no interceptor needed). Setup should be removed entirely or kept as a noop with a comment. |
| 8 | FDN | Omniscience | Cast spells from hand without paying. | `make_cost_reduction(obj, applies_to='spell-cast', amount=999, self_only=False)` — self-only=False applies to controller-only spells; existing cost_query infra supports this. |
| 9 | FDN | Fishing Pole | Equipment with granted activated ability + untap trigger. | `make_equipment_setup` accepts keywords/subtypes; combine with `make_granted_activated_ability`. |
| 10 | MKM | Axebane Ferox | Deathtouch, haste, ward(collect evidence 4). | Existing `make_ward(custom_cost='Collect evidence 4')` — `collect_evidence` helper exists; thread it through ward custom-cost. |

Notes on lower-confidence candidates (not in top 10):

- **ECL** lots of `make_pump_self_ability` + `_make_main_phase_trigger` side-effect setups — already wired via side-effects, but counted as find-noops because they `return []` after a side-effect helper. The post-fix `find_useless_stubs.py` now correctly excludes these. (Examples: `flamechain_mauler`, `timid_shieldbearer`.)
- **SPM** `kravens_cats`, `inner_demons_gangsters`, `merciless_enforcers` — same pattern, side-effect `make_pump_self_ability` / `make_activated_ability`. The post-fix classifier correctly counts these as real.
- **EOE** `ragost_deft_gastronaut` — uses `type_grant_interceptor` (not in our allowlist) — could be wired with `register_*` helper or moved to a recognised shape.

## Cross-script diff

Functions flagged by `find_useless_stubs.py` but NOT by `strict_noop_audit.py` (i.e. the function has a non-trivial body but still registers nothing):

| set | function | note |
|-----|----------|------|
| LCI | `deepfathom_echo_setup` | Combat-start trigger defined as closure but never registered |
| LCI | `akawalli_setup` | Descend 4 — closure defined, never registered |
| BLB | `pawpatch_recruit_setup` | Opponent-target-detection closure defined, never registered |
| FDN | `crusader_of_odric_setup` | Sweep-related closure, never registered |
| FDN | `elenda_saint_of_dusk_setup` | Static ability closure, never registered |
| FDN | `enigma_drake_setup` | Static P/T closure, never registered |
| EOE | `ragost_deft_gastronaut_setup` | Type grant via non-allowlisted helper |
| ECL | `(10 others)` | Mostly side-effect `make_pump_self_ability` + `_make_main_phase_trigger` |
| SPM | `(3 others)` | Side-effect `make_pump_self_ability` / `make_activated_ability` |
| TLA | `earth_kingdom_protectors_setup` | Activated sac-grant — uses side-effect helper |
| TLA | `swampsnare_trap_setup` | Aura — delegated through `_aura(...)(obj, state)` — actually real |
| FIN | `coeurl_ff_setup` | Activated tap-target — uses side-effect helper |

Most of these are **already-real** side-effect helper invocations that were miscounted by the pre-fix `find_useless_stubs.py`. The remaining handful (LCI's deepfathom_echo/akawalli, BLB's pawpatch_recruit, FDN's elenda_saint_of_dusk) *are* functional noops in the same sense as bare `return []` — they have closures with logic but never register anything. They could be promoted to strict-noop in a future audit refinement.

## Scripts

- `scripts/strict_noop_audit.py` — authoritative AST-based audit (pure structural)
- `scripts/find_useless_stubs.py` — allowlist-based audit with side-effect detection

Run either with no arguments to print the per-set table. Add `--verbose` (strict) or read source (find) for the full per-function list.

