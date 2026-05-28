# Attack on Titan — spice-pass s19 mismatch detection (Phase 0)

Detection method: instantiate each card, run setup_interceptors, fire a battery of synthetic
triggers (ETB / attack / death / upkeep / combat-damage), collect emitted EventType families,
and compare against the effect families implied by the cards rules text.

A card is a MISMATCH when its setup emits an info-pulse event (SCRY / SURVEIL / MILL /
LIFE_CHANGE drain / DRAW) that the text does NOT call for, OR the text calls for a hard effect
(CREATE_TOKEN / DAMAGE / DESTROY / PUMP / EXILE / SACRIFICE / DISCARD) that the setup never emits.

The s19 spice-pass applied three generic templates wholesale, ignoring each cards real text:
  - SHAPE 1 (ETB):    SCRY 1 + each opponent loses max(1,N) life per <subtype>
  - SHAPE 2 (attack): SCRY 1 + each opponent loses max(1,N) life per <subtype>
  - SHAPE 3 (ETB):    SURVEIL 1 + each opponent mills 2  (also DISCARD variants)
Some Titan variants emit DAMAGE + SCRY combat-spice on attack.

Count utilities (_aot_s19_count_subtype/_type/_in_graveyard/_in_hand) are REAL helpers — kept.

### VANILLA-REVERT (keyword-only / no effect text) ### 33
  'Oluo Bozado, Levi Squad'	setup=_aot_oluo_bozado_setup	emits=['LOSELIFE', 'SCRY']	text='First strike.'
  'Survey Corps Veteran'	setup=_aot_survey_corps_veteran_setup_s19	emits=['LOSELIFE', 'SCRY']	text='First strike.'
  'Military Police Officer'	setup=_aot_military_police_officer_setup_s19	emits=['LOSELIFE', 'SCRY']	text='Lifelink.'
  'Wall Defender'	setup=_aot_wall_defender_setup_s19	emits=['GAINLIFE', 'LOSELIFE', 'SCRY']	text=''
  'Interior Police'	setup=_aot_interior_police_setup_s19	emits=['DISCARD', 'SURVEIL']	text='Flash, deathtouch.'
  'Horse Mounted Scout'	setup=_aot_horse_mounted_scout_setup_s19	emits=['LOSELIFE', 'SCRY']	text='Haste.'
  'Pieck Finger, Cart Titan'	setup=_aot_pieck_finger_setup_s19	emits=['DISCARD', 'SURVEIL']	text='Vigilance, trample.'
  'Marleyan Spy'	setup=_aot_marleyan_spy_setup_s19	emits=['MILL', 'SURVEIL']	text='Flying.'
  'Military Tactician'	setup=_aot_military_tactician_setup_s19	emits=['MILL', 'SURVEIL']	text='Flash.'
  'Coastal Scout'	setup=_aot_coastal_scout_setup_s19	emits=['MILL', 'SURVEIL']	text='Flying.'
  'Reiner Braun, Armored Titan'	setup=_aot_reiner_braun_setup_s19	emits=['DAMAGE', 'SCRY']	text=''
  'Marleyan Warrior'	setup=_aot_marleyan_warrior_setup_s19	emits=['MILL', 'SURVEIL']	text='Menace.'
  'Marleyan Officer'	setup=_aot_marleyan_officer_setup_s19	emits=['MILL', 'SURVEIL']	text='Deathtouch.'
  'Infiltrator'	setup=_aot_infiltrator_setup_s19	emits=['MILL', 'SURVEIL']	text='Menace.'
  'Military Executioner'	setup=_aot_marleyan_officer_setup_s19	emits=['MILL', 'SURVEIL']	text='Deathtouch, menace.'
  'Pure Titan'	setup=_aot_pure_titan_setup_s19	emits=['DAMAGE', 'SCRY']	text='Trample.'
  'Abnormal Titan'	setup=_aot_abnormal_titan_setup_s19	emits=['DAMAGE', 'SCRY']	text='Haste, trample.'
  'Small Titan'	setup=_aot_small_titan_setup_s19	emits=['DAMAGE', 'SCRY']	text='Haste.'
  'Mindless Titan'	setup=_aot_mindless_titan_setup_s19	emits=['DAMAGE', 'SCRY']	text='Trample.'
  'Jaw Titan'	setup=_aot_jaw_titan_setup_s19	emits=['LOSELIFE', 'SCRY']	text='Haste, first strike.'
  'Wall Breaker'	setup=_aot_wall_breaker_setup_s19	emits=['LOSELIFE', 'SCRY']	text='Trample.'
  'Attack Titan Acolyte'	setup=_aot_attack_titan_acolyte_setup_s19	emits=['LOSELIFE', 'SCRY']	text='First strike.'
  'Yeagerist Soldier'	setup=_aot_yeagerist_soldier_setup_s19	emits=['LOSELIFE', 'SCRY']	text='Haste.'
  'Wall Titan'	setup=_aot_wall_defender_setup_s19	emits=['GAINLIFE', 'LOSELIFE', 'SCRY']	text=''
  'Forest Titan'	setup=_aot_forest_titan_setup_s19	emits=['DAMAGE', 'SCRY']	text='Reach, trample.'
  'Towering Titan'	setup=_aot_towering_titan_setup_s19	emits=['DAMAGE', 'SCRY']	text='Trample, reach.'
  'Primordial Titan'	setup=_aot_primordial_titan_setup_s19	emits=['DAMAGE', 'SCRY']	text='Trample.'
  'Titan Hunter'	setup=_aot_titan_hunter_setup_s19	emits=['GAINLIFE', 'LOSELIFE', 'SCRY']	text='Reach.'
  'Wild Horse'	setup=_aot_wild_horse_setup_s19	emits=['GAINLIFE', 'LOSELIFE', 'SCRY']	text='Haste.'
  'Porco Galliard, Jaw Titan'	setup=_aot_porco_galliard_setup_s19	emits=['LOSELIFE', 'SCRY']	text='Haste, first strike.'
  'Darius Zackly, Premier'	setup=_aot_darius_zackly_setup_s19	emits=['GAINLIFE', 'LOSELIFE', 'SCRY']	text='Vigilance.'
  'Onyankopon, Anti-Marleyan'	setup=_aot_onyankopon_setup_s19	emits=['DISCARD', 'SURVEIL']	text='Flying.'
  'Louise, Yeagerist Devotee'	setup=_aot_louise_yeagerist_setup_s19	emits=['LOSELIFE', 'SCRY']	text='First strike, haste.'

### RE-IMPLEMENT (text has real effect) ### 28
  'Armin Arlert, Tactician'	setup=_aot_armin_arlert_tactician_setup_s19	emits=['DRAW', 'LOSELIFE', 'SCRY']	wants=['DRAW', 'SCRY']
      text='When Armin Arlert, Tactician enters the battlefield, scry 2 and draw a card.'
  'Erwin Smith, Commander'	setup=_aot_erwin_smith_commander_setup	emits=['LOSELIFE', 'SCRY']	wants=['DRAW']
      text='Vigilance. Whenever Erwin Smith, Commander attacks, draw a card.'
  'Sasha Blouse, Hunter'	setup=_aot_sasha_blouse_setup	emits=['LOSELIFE', 'SCRY']	wants=['GAINLIFE']
      text='Reach. When Sasha Blouse, Hunter enters the battlefield, you gain 2 life.'
  'Connie Springer, Loyal Friend'	setup=_aot_connie_springer_setup	emits=['LOSELIFE', 'SCRY']	wants=['DRAW']
      text='Haste. When Connie Springer dies, draw a card.'
  'Petra Ral, Levi Squad'	setup=_aot_petra_ral_setup	emits=['LOSELIFE', 'SCRY']	wants=['DRAW']
      text='Flying. When Petra Ral dies, draw a card.'
  'Garrison Soldier'	setup=_aot_garrison_soldier_setup_s19	emits=['GAINLIFE', 'LOSELIFE', 'SCRY']	wants=['GAINLIFE']
      text='Whenever Garrison Soldier blocks, you gain 2 life.'
  'Squad Captain'	setup=_aot_squad_captain_setup_s19	emits=['LOSELIFE', 'SCRY']	wants=['CREATE_TOKEN']
      text='When Squad Captain enters the battlefield, create a 1/1 white Human Scout Soldier creature token.'
  'Wall Garrison Elite'	setup=_aot_wall_garrison_elite_setup_s19	emits=['LOSELIFE', 'SCRY']	wants=['PUMP']
      text='Defender, vigilance. (Gets +0/+1 from its Wall training.)'
  'Shiganshina Citizen'	setup=_aot_shiganshina_citizen_setup_s19	emits=['GAINLIFE', 'LOSELIFE', 'SCRY']	wants=['GAINLIFE']
      text='When Shiganshina Citizen dies, you gain 2 life.'
  'Eldian Refugee'	setup=_aot_eldian_refugee_setup_s19	emits=['GAINLIFE', 'LOSELIFE', 'SCRY']	wants=['GAINLIFE']
      text='When Eldian Refugee enters the battlefield, you gain 1 life.'
  'Wall Cultist'	setup=_aot_wall_cultist_setup_s19	emits=['GAINLIFE', 'LOSELIFE', 'SCRY']	wants=['PUMP']
      text='Defender. (Gets +0/+1.)'
  'Intelligence Officer'	setup=_aot_intelligence_officer_setup_s19	emits=['MILL', 'SURVEIL']	wants=['SCRY']
      text='When Intelligence Officer enters the battlefield, scry 2.'
  'Survey Cartographer'	setup=_aot_survey_cartographer_setup_s19	emits=['MILL', 'SURVEIL']	wants=['SCRY']
      text='When Survey Cartographer enters the battlefield, scry 1.'
  'Wall Architect'	setup=_aot_wall_architect_setup_s19	emits=['REVEAL_HAND', 'SCRY']	wants=['CREATE_TOKEN']
      text='When Wall Architect enters the battlefield, create a 0/4 white Wall creature token with defender.'
  'Signal Corps Operator'	setup=_aot_signal_corps_operator_setup_s19	emits=['MILL', 'SURVEIL']	wants=['SCRY']
      text='When Signal Corps Operator enters the battlefield, scry 1.'
  'Supply Corps Quartermaster'	setup=_aot_supply_corps_quartermaster_setup_s19	emits=['DRAW', 'REVEAL_HAND', 'SCRY']	wants=['DRAW']
      text='When Supply Corps Quartermaster enters the battlefield, draw a card.'
  'Formation Analyst'	setup=_aot_formation_analyst_setup_s19	emits=['MILL', 'SURVEIL']	wants=['SCRY']
      text='Defender. When Formation Analyst enters the battlefield, scry 1.'
  'War Hammer Titan'	setup=_aot_war_hammer_titan_setup_s19	emits=['DAMAGE', 'SCRY']	wants=['CREATE_TOKEN']
      text='First strike, trample. Whenever War Hammer Titan attacks, create a 3/1 black Construct creature token with haste and first strike named Hammer Golem.'
  'Eldian Internment Guard'	setup=_aot_eldian_internment_setup_s19	emits=['DISCARD', 'SURVEIL']	wants=['GAINLIFE']
      text='Whenever another creature dies, you gain 1 life.'
  'Titan Horde'	setup=_aot_titan_horde_setup_s19	emits=['DAMAGE', 'SCRY']	wants=['CREATE_TOKEN']
      text='Trample. When Titan Horde enters the battlefield, create two 2/2 black Titan creature tokens.'
  'Crawling Titan'	setup=_aot_crawling_titan_setup_s19	emits=['DAMAGE', 'SCRY']	wants=['LOSELIFE']
      text='When Crawling Titan dies, each opponent loses 2 life.'
  'Paradis Farmer'	setup=_aot_paradis_farmer_setup_s19	emits=['GAINLIFE', 'LOSELIFE', 'SCRY']	wants=['GAINLIFE']
      text='When Paradis Farmer enters the battlefield, you gain 1 life.'
  'Forest Scout'	setup=_aot_forest_scout_setup_s19	emits=['GAINLIFE', 'LOSELIFE', 'SCRY']	wants=['SCRY']
      text='When Forest Scout enters the battlefield, scry 1.'
  'The Colossal Titan'	setup=_colossal_titan_legendary_setup	emits=['LOSELIFE']	wants=['DAMAGE', 'LOSELIFE']
      text='Trample. When The Colossal Titan enters the battlefield, it deals 6 damage to each creature your opponents control, destroys each land they control, and each opponent loses half their life, rounded up. (The Rumbling.)'
  'Hannes, Garrison Captain'	setup=_aot_garrison_soldier_setup_s19	emits=['GAINLIFE', 'LOSELIFE', 'SCRY']	wants=['GAINLIFE']
      text='Vigilance. Whenever Hannes blocks, you gain 2 life.'
  'Wall Rose Garrison'	setup=_aot_wall_defender_setup_s19	emits=['GAINLIFE', 'LOSELIFE', 'SCRY']	wants=['GAINLIFE']
      text='Whenever Wall Rose Garrison blocks, you gain 3 life.'
  'Yelena, True Believer'	setup=_aot_yelena_setup_s19	emits=['DISCARD', 'SURVEIL']	wants=['SCRY']
      text='Menace. When Yelena enters the battlefield, scry 2.'
  "Kaya, Sasha's Friend"	setup=_aot_kaya_setup_s19	emits=['GAINLIFE', 'LOSELIFE', 'SCRY']	wants=['GAINLIFE']
      text='When Kaya enters the battlefield, you gain 2 life.'


## Phase 1 — root-cause & remediation strategy

ROOT CAUSE (confirmed by orphan analysis): the s19 spice-pass did NOT delete the
correct per-card setups. For each affected card it created a parallel spice variant
(`_aot_<card>_setup` or `_aot_<card>_setup_s19`) emitting one of the three generic
templates, and re-pointed `setup_interceptors=` to that variant — leaving the
ORIGINAL correct setup defined but orphaned (107 orphaned defs found, ~90 of which
are correct card setups shadowed by a spice twin).

No single shared stub-helper exists to bulk-delete; the spice is 99 individually
named setup defs. The count utilities `_aot_s19_count_subtype/_type/_in_graveyard/
_in_hand` ARE shared and ARE real — KEEP.

REMEDIATION: re-point each of the 59 mismatched card defs from its spice variant
back to its orphaned correct original (verified to exist + emit text-matching events
for all 59). Then bulk-delete the now-unreferenced spice variant defs via script.
The Colossal Titan was a detector false-positive (its setup already emits
DAMAGE+DESTROY+halve; probe only saw LOSELIFE because the minimal board had no
opponent permanents) — LEFT UNTOUCHED.

59 cards: 27 re-implement (real effect restored), 32 vanilla-revert (keyword/
mechanic-only original restored, e.g. Reiner Titan Shift, Wall defenders).
