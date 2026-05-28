# Dragon Ball Z (DBZ) — Phase 0 DETECT: slice-4 + slice-14 info-pulse stub audit

Date: 2026-05-28. Branch off `recover/interceptor-campaign`.

## Summary

`src/cards/custom/dragon_ball.py` was contaminated by two retrofit commits:
- `47a2c5cb` DBZ slice-4 thin-bust (17 vanilla cards lifted to depth-3)
- `b1ab58e9` DBZ slice-14 median lift (157 vanilla cards lifted to depth-7)

These added ~3,870 lines: 90 `_dbz_*_setup` stub functions + 65 `_dbz_resolve_*` stub
handlers, all emitting **info-pulse events (SCRY/SURVEIL/MILL/LIFE_CHANGE/DAMAGE/DISCARD)**
organized by mechanical "SHAPE" groups, ignoring real card identity. For 157 cards the
retrofit also **rewrote the card `text`** to launder the stub (e.g. Kamehameha's original
"deals 5 damage to any target. If you control Goku, it deals 7..." became "Scry 1; each
opponent takes 5 damage").

Pre-contamination baseline = commit `330a99c5` (parent of slice-4), 4,184 lines, 0 stub
helpers. The 157 affected cards were text-only (cast-dispatch) or genuinely vanilla there.

KEPT (real, not stubs): `_dbz_s14_count_subtype/type/in_graveyard/in_hand`,
`_dbz_s14_active_caster`, and the 4 real per-card setups defined post-retrofit
(`goku_setup`, `shenron_wish_granter_setup`, etc. — present in baseline too).
Shenron's `o.characteristics.name` guard is left untouched per brief.

## Cards emitting ONLY info-pulse events not matching text (157 total)

### A. Vanilla in baseline — keyword/stat-only (46) → VANILLA-REVERT

- `AJISA_TREE` (Ajisa Tree) ← `_dbz_ajisa_tree_setup`
- `ANALYSIS_DRONE` (Analysis Drone) ← `_dbz_analysis_drone_setup`
- `ANDROID_19` (Android 19, Energy Absorber) ← `_dbz_android_19_setup`
- `ANDROID_20` (Android 20, Dr. Gero) ← `_dbz_android_20_setup`
- `ANDROID_21` (Android 21, Hunger Incarnate) ← `_dbz_android_21_setup`
- `CAPSULE_CORP_DRONE` (Capsule Corp Drone) ← `_dbz_capsule_drone_setup`
- `CELL_JUNIOR` (Cell Junior) ← `_dbz_cell_junior_setup`
- `CRANE_SCHOOL_STUDENT` (Crane School Student) ← `_dbz_crane_student_setup`
- `DABURA` (Dabura, Demon King) ← `_dbz_dabura_setup`
- `DODORIA` (Dodoria, Frieza's Elite) ← `_dbz_dodoria_setup`
- `ENERGY_ABSORBER` (Energy Absorber) ← `_dbz_energy_absorber_setup`
- `FRIEZA_SOLDIER` (Frieza Soldier) ← `_dbz_frieza_soldier_setup`
- `GIANT_NAMEKIAN` (Giant Namekian) ← `_dbz_giant_namekian_setup`
- `GINYU` (Captain Ginyu) ← `_dbz_ginyu_setup`
- `GOHAN_SSJ2` (Gohan, Super Saiyan 2) ← `_dbz_gohan_ssj2_setup`
- `GOKU_BLACK` (Goku Black, Zero Mortal Plan) ← `_dbz_goku_black_setup`
- `GOKU_ULTRA_INSTINCT` (Goku, Ultra Instinct) ← `_dbz_goku_ui_setup`
- `GOLDEN_FRIEZA` (Frieza, Golden Form) ← `_dbz_golden_frieza_setup`
- `GREAT_APE` (Great Ape) ← `_dbz_great_ape_setup`
- `JEICE` (Jeice) ← `_dbz_jeice_setup`
- `JIREN` (Jiren, The Strongest) ← `_dbz_jiren_setup`
- `KEFLA` (Kefla, Potara Fusion) ← `_dbz_kefla_setup`
- `MAJIN_BUU` (Majin Buu, Innocent Evil) ← `_dbz_majin_buu_setup`
- `MAJIN_MINION` (Majin Minion) ← `_dbz_majin_minion_setup`
- `MAJIN_VEGETA` (Vegeta, Majin) ← `_dbz_majin_vegeta_setup`
- `NAMEKIAN_ELDER` (Namekian Elder) ← `_dbz_namekian_elder_setup`
- `NAMEKIAN_HEALER` (Namekian Healer) ← `_dbz_namekian_healer_setup`
- `NAMEKIAN_WARRIOR` (Namekian Warrior) ← `_dbz_namekian_warrior_setup`
- `NAMEK_FISH` (Giant Namek Fish) ← `_dbz_namek_fish_setup`
- `OTHERWORLD_FIGHTER` (Otherworld Fighter) ← `_dbz_otherworld_fighter_setup`
- `PORUNGA` (Porunga, Namekian Dragon) ← `_dbz_porunga_setup`
- `RAGING_SAIYAN` (Raging Saiyan) ← `_dbz_raging_saiyan_setup`
- `RECOOME` (Recoome) ← `_dbz_recoome_setup`
- `RED_RIBBON_SCOUT` (Red Ribbon Scout) ← `_dbz_red_ribbon_scout_setup`
- `REPAIR_BOT` (Repair Bot) ← `_dbz_repair_bot_setup`
- `SAIBAMAN` (Saibaman) ← `_dbz_saibaman_setup`
- `SAIYAN_CHILD` (Saiyan Child) ← `_dbz_saiyan_child_setup`
- `SAIYAN_ELITE` (Saiyan Elite) ← `_dbz_saiyan_elite_setup`
- `SAIYAN_POD_PILOT` (Saiyan Pod Pilot) ← `_dbz_saiyan_pod_pilot_setup`
- `SCIENTIST` (Capsule Corp Scientist) ← `_dbz_scientist_setup`
- `SHENRON` (Shenron, Eternal Dragon) ← `_dbz_shenron_setup`
- `TURTLE_SCHOOL_STUDENT` (Turtle School Student) ← `_dbz_turtle_student_setup`
- `WHIS` (Whis, Angel Attendant) ← `_dbz_whis_setup`
- `WORLD_CHAMPION` (World Tournament Champion) ← `_dbz_world_champion_setup`
- `ZAMASU` (Zamasu, Divine Justice) ← `_dbz_zamasu_setup`
- `ZARBON` (Zarbon, Frieza's Elite) ← `_dbz_zarbon_setup`

### B. Instant/Sorcery with rich text in baseline (61) → RESTORE TEXT + real resolve where helper exists

- `ABSORPTION` (Absorption) ← `_dbz_resolve_absorption`
- `AFTERIMAGE` (Afterimage) ← `_dbz_resolve_afterimage`
- `ANDROID_CONSTRUCTION` (Android Construction) ← `_dbz_resolve_android_construction`
- `BIG_BANG_ATTACK` (Big Bang Attack) ← `_dbz_resolve_big_bang_attack`
- `BURNING_ATTACK` (Burning Attack) ← `_dbz_resolve_burning_attack`
- `CANDY_BEAM` (Candy Beam) ← `_dbz_resolve_candy_beam`
- `DEATH_BALL` (Death Ball) ← `_dbz_resolve_death_ball`
- `DEATH_BEAM` (Death Beam) ← `_dbz_resolve_death_beam`
- `DESTRUCTO_DISC` (Destructo Disc) ← `_dbz_resolve_destructo_disc`
- `DIVINE_PROTECTION` (Divine Protection) ← `_dbz_resolve_divine_protection`
- `DRAGON_BALL_SUMMON` (Dragon Ball Summon) ← `_dbz_resolve_dragon_ball_summon`
- `DRAGON_BALL_WISH` (Dragon Ball Wish) ← `_dbz_resolve_dragon_ball_wish`
- `ENERGY_ANALYSIS` (Energy Analysis) ← `_dbz_resolve_energy_analysis`
- `ENERGY_BARRIER` (Energy Barrier) ← `_dbz_resolve_energy_barrier`
- `ENERGY_DRAIN` (Energy Drain) ← `_dbz_resolve_energy_drain`
- `ERASER_CANNON` (Eraser Cannon) ← `_dbz_resolve_eraser_cannon`
- `EXPLOSIVE_WAVE` (Explosive Wave) ← `_dbz_resolve_explosive_wave`
- `FINAL_EXPLOSION` (Final Explosion) ← `_dbz_resolve_final_explosion`
- `FINAL_FLASH` (Final Flash) ← `_dbz_resolve_final_flash`
- `FINGER_BEAM` (Finger Beam) ← `_dbz_resolve_finger_beam`
- `FUSE` (Fuse) ← `_dbz_resolve_fuse`
- `GALICK_GUN` (Galick Gun) ← `_dbz_resolve_galick_gun`
- `GENOCIDE_ATTACK` (Genocide Attack) ← `_dbz_resolve_genocide_attack`
- `HELLZONE_GRENADE` (Hellzone Grenade) ← `_dbz_resolve_hellzone_grenade`
- `HOPE_OF_EARTH` (Hope of Earth) ← `_dbz_resolve_hope_of_earth`
- `HUMAN_EXTINCTION_ATTACK` (Human Extinction Attack) ← `_dbz_resolve_human_extinction`
- `INSTANT_TRANSMISSION_BLUE` (Instant Transmission) ← `_dbz_resolve_instant_transmission_blue`
- `INSTANT_TRANSMISSION_WHITE` (Heroic Rescue) ← `_dbz_resolve_instant_transmission`
- `KAMEHAMEHA` (Kamehameha) ← `_dbz_resolve_kamehameha`
- `KIAI_SHOUT` (Kiai Shout) ← `_dbz_resolve_kiai_shout`
- `KI_EXPLOSION` (Ki Explosion) ← `_dbz_resolve_ki_explosion`
- `KI_SENSE` (Ki Sense) ← `_dbz_resolve_ki_sense`
- `MAJIN_CURSE` (Majin Curse) ← `_dbz_resolve_majin_curse`
- `MASENKO` (Masenko) ← `_dbz_resolve_masenko`
- `NAMEKIAN_FUSION` (Namekian Fusion) ← `_dbz_resolve_namekian_fusion`
- `NAMEKIAN_REGENERATION` (Namekian Regeneration) ← `_dbz_resolve_namek_regen`
- `NATURE_BARRIER` (Nature's Barrier) ← `_dbz_resolve_nature_barrier`
- `OMEGA_BLASTER` (Omega Blaster) ← `_dbz_resolve_omega_blaster`
- `OOZARU_RAMPAGE` (Oozaru Rampage) ← `_dbz_resolve_oozaru_rampage`
- `PHOTON_WAVE` (Photon Wave) ← `_dbz_resolve_photon_wave`
- `PLANET_DESTRUCTION` (Planet Destruction) ← `_dbz_resolve_planet_destruction`
- `PLANET_NAMEK` (Planet Namek's Blessing) ← `_dbz_resolve_planet_namek`
- `POWER_BALL` (Power Ball) ← `_dbz_resolve_power_ball`
- `RAISE_SAIBAMEN` (Raise Saibamen) ← `_dbz_resolve_raise_saibamen`
- `RED_RIBBON_RESEARCH` (Red Ribbon Research) ← `_dbz_resolve_red_ribbon_research`
- `REGROWTH` (Regrowth) ← `_dbz_resolve_regrowth`
- `RESURRECTION_F` (Resurrection) ← `_dbz_resolve_resurrection`
- `REVIVAL` (Revival) ← `_dbz_resolve_revival`
- `SAIYAN_INVASION` (Saiyan Invasion) ← `_dbz_resolve_saiyan_invasion`
- `SAIYAN_RAGE` (Saiyan Rage) ← `_dbz_resolve_saiyan_rage`
- `SENZU_HEAL` (Senzu Heal) ← `_dbz_resolve_senzu_heal`
- `SOLAR_FLARE_TECHNIQUE` (Solar Flare) ← `_dbz_resolve_solar_flare`
- `SOLAR_KAMEHAMEHA` (Solar Kamehameha) ← `_dbz_resolve_solar_kamehameha`
- `SPECIAL_BEAM_CANNON` (Special Beam Cannon) ← `_dbz_resolve_special_beam_cannon`
- `SPIRIT_BOMB` (Spirit Bomb) ← `_dbz_resolve_spirit_bomb`
- `SUPERNOVA` (Supernova) ← `_dbz_resolve_supernova`
- `TECHNOLOGY_ADVANCEMENT` (Technology Advancement) ← `_dbz_resolve_tech_advancement`
- `TRAINING_COMPLETE` (Training Complete) ← `_dbz_resolve_training_complete`
- `VANISH` (Vanish) ← `_dbz_resolve_vanish`
- `WORLD_TOURNAMENT` (World Tournament) ← `_dbz_resolve_world_tournament`
- `ZENKAI_BOOST` (Zenkai Boost) ← `_dbz_resolve_zenkai_boost`

### C. Permanent with text in baseline (50) → RESTORE TEXT; real setup where helper exists, else text-only (baseline state)

- `BARDOCK` (Bardock, Father of Goku) ← `_dbz_bardock_setup`
- `BATTLE_RAGE` (Battle Rage) ← `_dbz_battle_rage_ench_setup`
- `CAPSULE` (Capsule) ← `_dbz_capsule_setup`
- `CAPSULE_CORP` (Capsule Corporation) ← `_dbz_capsule_corp_land_setup`
- `CAPSULE_TECHNOLOGY` (Capsule Technology) ← `_dbz_capsule_tech_ench_setup`
- `CELL_GAMES_ARENA` (Cell Games Arena) ← `_dbz_cell_games_arena_setup`
- `DARK_ENERGY` (Dark Energy) ← `_dbz_dark_energy_ench_setup`
- `DRAGON_BALL_FIVE` (Five-Star Dragon Ball) ← `_dbz_dragon_ball_setup`
- `DRAGON_BALL_FOUR` (Four-Star Dragon Ball) ← `_dbz_dragon_ball_setup`
- `DRAGON_BALL_ONE` (One-Star Dragon Ball) ← `_dbz_dragon_ball_setup`
- `DRAGON_BALL_SEVEN` (Seven-Star Dragon Ball) ← `_dbz_dragon_ball_setup`
- `DRAGON_BALL_SIX` (Six-Star Dragon Ball) ← `_dbz_dragon_ball_setup`
- `DRAGON_BALL_THREE` (Three-Star Dragon Ball) ← `_dbz_dragon_ball_setup`
- `DRAGON_BALL_TWO` (Two-Star Dragon Ball) ← `_dbz_dragon_ball_setup`
- `DRAGON_RADAR` (Dragon Radar) ← `_dbz_dragon_radar_setup`
- `ENERGY_FIELD` (Energy Field) ← `_dbz_energy_field_ench_setup`
- `FRIEZA_SPACESHIP` (Frieza's Spaceship) ← `_dbz_frieza_spaceship_setup`
- `FUSION_EARRINGS` (Fusion Earrings) ← `_dbz_fusion_earrings_setup`
- `FUTURE_TRUNKS` (Future Trunks, Time Warrior) ← `_dbz_future_trunks_warrior_setup`
- `GOKU_SUPER_SAIYAN` (Goku, Super Saiyan) ← `_dbz_goku_ssj_setup`
- `GRAVITY_CHAMBER` (Gravity Chamber) ← `_dbz_gravity_chamber_setup`
- `HEALING_AURA` (Healing Aura) ← `_dbz_healing_aura_ench_setup`
- `HYPERBOLIC_TIME_CHAMBER` (Hyperbolic Time Chamber) ← `_dbz_hyperbolic_chamber_land_setup`
- `INFINITE_ENERGY` (Infinite Energy) ← `_dbz_infinite_energy_ench_setup`
- `KAIS_BLESSING` (Kai's Blessing) ← `_dbz_kais_blessing_setup`
- `KAME_HOUSE` (Kame House) ← `_dbz_kame_house_setup`
- `KING_KAIS_PLANET` (King Kai's Planet) ← `_dbz_king_kai_planet_setup`
- `KORIN_TOWER` (Korin Tower) ← `_dbz_korin_tower_setup`
- `LOOKOUT` (The Lookout) ← `_dbz_lookout_setup`
- `MAJIN_BUU_HOUSE` (Majin Buu's House) ← `_dbz_majin_buu_house_setup`
- `NAMEK_WILDS` (Namek Wilds) ← `_dbz_namek_wilds_ench_setup`
- `NIMBUS_CLOUD` (Nimbus Cloud) ← `_dbz_nimbus_setup`
- `OTHERWORLD` (Otherworld) ← `_dbz_otherworld_ench_setup`
- `OTHERWORLD_ARENA` (Otherworld Tournament Arena) ← `_dbz_otherworld_arena_setup`
- `PLANET_NAMEK_LAND` (Planet Namek) ← `_dbz_planet_namek_land_setup`
- `PLANET_VEGETA` (Planet Vegeta) ← `_dbz_planet_vegeta_setup`
- `POTARA_EARRINGS` (Potara Earrings) ← `_dbz_potara_setup`
- `POWER_POLE` (Power Pole) ← `_dbz_power_pole_setup`
- `RED_RIBBON_HQ` (Red Ribbon Army HQ) ← `_dbz_red_ribbon_hq_setup`
- `SCOUTER` (Scouter) ← `_dbz_scouter_setup`
- `SENZU_BEAN` (Senzu Bean) ← `_dbz_senzu_bean_setup`
- `SERPENT_ROAD` (Snake Way) ← `_dbz_serpent_road_setup`
- `SPACE_POD` (Saiyan Space Pod) ← `_dbz_space_pod_setup`
- `SUPER_BUU` (Super Buu, Absorber) ← `_dbz_super_buu_setup`
- `TIME_MACHINE` (Time Machine) ← `_dbz_time_machine_setup`
- `TURTLE_SHELL` (Turtle Shell) ← `_dbz_turtle_shell_setup`
- `VEGETA_SUPER_SAIYAN` (Vegeta, Super Saiyan) ← `_dbz_vegeta_ssj_setup`
- `WEIGHTED_CLOTHING` (Weighted Clothing) ← `_dbz_weighted_clothing_setup`
- `WORLD_TOURNAMENT_ARENA` (World Tournament Arena) ← `_dbz_tournament_arena_setup`
- `Z_SWORD` (Z-Sword) ← `_dbz_z_sword_setup`

