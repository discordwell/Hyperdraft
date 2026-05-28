# Princess Catholicon (FINC) — slice-16 contamination detection (Phase 0)

Strict text-vs-effect audit of `src/cards/custom/princess_catholicon.py`.

## Ground truth

The pre-contamination original is commit `ef060e3d` (267 cards, all of the
flagged cards were genuinely **vanilla** — descriptive `text=` only, no
`setup_interceptors`/`resolve`). Later "spice" slices (5, 5.5, 16) rewrote both
the card TEXT and added fabricated `setup`/`resolve` emitting an info-pulse
template (SCRY/SURVEIL/MILL + "each opponent loses N life"). Slice-16
(`b35cff9c`) was the largest: +2,324 lines.

The instruction's suggested baseline `607662b2` (slice-5.5) is itself a
contamination slice, so `ef060e3d` is used as ground truth for original text.

## Category A — slice-16 stub contamination (117 cards) — REVERT

These 117 cards had **clean vanilla original text**, rewritten by slice-16 to
the info-pulse template, with fabricated `setup_interceptors`/`resolve`
functions emitting SCRY/SURVEIL/LIFE_CHANGE that do NOT match original text.

- All 117 originals were vanilla (no setup/resolve). Fix = revert `text=` to
  original + drop the slice-16 `setup_interceptors`/`resolve`.
- 73 distinct `setup` fns + 44 distinct `resolve` fns to delete (+ shared
  `_finc_s16_active_caster`). Each defined once, referenced once → safe bulk-delete.

Const list (117): ADAMANTOISE, ALL_MATERIA, ARISE, ASSASSIN, AUTO_LIFE,
BALAMB_GARDEN, BEHEMOTH, BIG_GUARD, BIO, BLACK_CHOCOBO, BLIZZARD, BOMB,
BREAK_SPELL, CACTUAR, CALCULATOR, CATOBLEPAS, CELSIUS, CHEMIST, CHOCOBO_KNIGHT,
CHOCOBO_SAGE, CID_HIGHWIND, CRYSTAL_TOWER, CURAGA, CURE_MAGE, CURE_MATERIA,
CURE_NATURE, DARK, DARKGA, DEATH_SPELL, DEMI, DEVOUT, DISPEL_MAGIC, DOOM, DRAIN,
ENEMY_SKILL_MATERIA, ESUNA, EVOKER, FAITH, FAT_CHOCOBO, FIGARO_CASTLE, FIGHTER,
FIRA, FIRAGA, FIRE, FIRE_ELEMENTAL, FIRE_MATERIA, FLARE, FLOAT, FORGOTTEN_CAPITAL,
GEOMANCER, GHOST, GOBLIN, GRAVITY, HASTE_SPELL, HIGHWIND, HOLY, ICE_MATERIA,
IRON_GIANT, IVALICE, JENOVA, KNIGHTS_OF_ROUND_MATERIA, LICH, LIFE, LIFESTREAM,
LIGHT_WARRIOR, LIGHTNING_MATERIA, LUCRECIA_CRESCENT, MALBORO, MASTER_MATERIA,
MELTDOWN, METEOR, MIDGAR_ZOLOM, MIGHTY_GUARD, MOOGLE_KNIGHT, MOOGLE_SCHOLAR,
MORBOL, MYSTIC_KNIGHT, NARSHE, NIBELHEIM, NINJA, OCHU_DANCE, OMEGA_WEAPON, ORACLE,
OSMOSE, POISON, PROTECT, QUAKE, QUICK, RANGER, RED_CHOCOBO, REGEN, SAGE, SAMURAI,
SANCTUM_GUARDIAN, SCHOLAR, SHELL, SHINRA_EXECUTIVE, SLOW, STOP, SUMMON_CHOCOBO,
SUMMON_MATERIA, SYLPH, TELEPORT, THUNDAGA, THUNDER, TINY_BRONCO, TONBERRY,
TURKS_OPERATIVE, ULTIMA, VAMPIRE, WALL, WARRIOR, WATER_ELEMENTAL, WATER, WATERGA,
WILD_GROWTH, WUTAI_NINJA.

## Category C — legit cards (NOT contamination) — KEEP

- **Phase A1 (commit 39089ca6)**: SEPHIROTH_AVATAR, CECIL_HARVEY — designed
  Limit-Break mythics; genuine text; KEEP.
- **Balance buff (commit 9e655dd4)**: APPRENTICE_SCHOLAR, CADET_KNIGHT,
  CADET_MAGE, JUNIOR_SUMMONER, PIXIE_MAGE, RECRUIT_SOLDIER, ROYAL_KNIGHT,
  TRANCE_MAGE — designed commons whose text GENUINELY says scry/gain/drain.
  Setups match text → CORRECT; KEEP.
- **Slice-5.5 axis-flip (commit 607662b2)**: BLACK_MAGE_CALAMITY,
  CID_GARLOND_MAGITEK, CID_HIGHWIND_SKY_ENGINE, CID_POLLENDINA_ADAMANT,
  CLOUD_STRIFE_OMNISLASH, MATERIA_MASTERY_CRESCENDO, SEPHIROTH_REUNION,
  TIFA_FINAL_HEAVEN, WHITE_MAGE_TRINITY, YUNA_SENDING_RITUAL — designed modal /
  damage / counter-distribution cards; effect matches text. KEEP (out of
  slice-16 scope).

## Tests to delete from `tests/test_finc_spice.py`

- Cat-A scry/drain block (~lines 663-941: moogle_knight…geomancer, 17 tests).
- Entire "Slice-16 median-lift tests" section (~lines 1366-2131:
  `_s16_*` helpers + all `test_s16_*`).
- KEEP Phase A1 / balance / slice-5.5 test blocks.
