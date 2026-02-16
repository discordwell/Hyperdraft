# Hearthstone Card Implementation Bugs

## CRITICAL (crashes or silently broken)

- [x] C1. warlock.py — DISCARD payload uses `card_id` instead of `object_id` — FIXED
- [x] C2. warlock.py — LIFE_CHANGE payload uses `target: hero_id` instead of `player: controller` — FIXED
- [x] C3. warlock.py — Soulfire mana cost is "{1}", should be "{0}" — FIXED
- [x] C4. druid.py — `state.objects[mid].damage` missing `.state.` — FIXED (rewrote Healing Touch)
- [x] C5. shaman.py — Rockbiter Weapon mana cost is "{2}", should be "{1}" — FIXED
- [x] C6. shaman.py — Al'Akir missing "windfury" and "divine_shield" from keywords — FIXED
- [x] C7. hunter.py — PT_MODIFICATION uses wrong keys (`target`/`power` vs `object_id`/`power_mod`) — FIXED
- [x] C8. classic.py — Deathwing DISCARD uses `card_id` instead of `object_id` — FIXED
- [x] C9. mage.py — Cone of Cold mana cost is "{4}", should be "{3}" — FIXED

## HIGH (wrong behavior, game-impacting)

- [x] H1. hunter.py — All 4 secrets trigger infinitely — FIXED (converted to trigger_filter/trigger_effect)
- [x] H2. paladin.py — Repentance trigger_effect returns [] — FIXED (implements health-to-1)
- [x] H3. paladin.py — Redemption filter triggers on ANY minion death — FIXED (checks controller)
- [x] H4. paladin.py — Avenge filter triggers on ANY minion death — FIXED (checks controller)
- [x] H5. warrior.py — Upgrade! modifies weapon.state instead of player weapon stats — FIXED
- [x] H6. warlock.py — Mortal Coil always draws — FIXED (conditional on kill)
- [x] H7. warlock.py — Shadowflame hardcodes 3 damage — FIXED (sacrifices minion, uses its attack)
- [x] H8. mage.py — Pyroblast shadows `targets` param — FIXED (respects passed targets)
- [x] H9. shaman.py — Dust Devil missing windfury — FIXED
- [x] H10. shaman.py — Doomhammer missing Windfury — FIXED (equip-time Windfury + overload, cleanup on destroy)
- [x] H11. hunter.py — Tundra Rhino "Beasts have Charge" aura — FIXED (implemented interceptor)
- [x] H12. hunter.py — Leokk token missing +1 Attack aura — FIXED (uses leokk_setup from tokens.py)
- [x] H13. druid.py — Cenarius Treants are 2/4, should be 2/2 — FIXED
- [x] H14. priest.py — Holy Nova heals by direct mutation — FIXED (emits LIFE_CHANGE events)
- [x] H15. priest.py — Lightwell heals by direct mutation — FIXED (random target + events)
- [x] H16. priest.py — Circle of Healing heals by direct mutation — FIXED (emits events)
- [x] H17. priest.py — Northshire Cleric checks wrong key — FIXED (checks object_id)
- [x] H18. warlock.py — Doomguard battlecry mutates hand — FIXED (uses random.sample)
- [x] H19. paladin.py — Repentance filter too broad — FIXED (checks ZONE_CHANGE + minion type)
- [x] H20. warrior.py — Armorsmith directly mutates armor — FIXED (emits ARMOR_GAIN event)
- [x] H21. shaman.py — Rockbiter appends player ID — FIXED (appends hero_id)
- [x] H22. mage.py — Cone of Cold wrong effect (random vs targeted+adjacent) — FIXED (targeted + adjacent enemy minions)

## MEDIUM (incorrect but non-crashing)

- [x] M1. tokens.py — HEALING_TOTEM missing setup_interceptors — FIXED
- [x] M2. tokens.py — PANTHER token doesn't exist in Hearthstone — RESOLVED (valid Power of the Wild token; comment clarified)
- [x] M3. tokens.py — Unused CardType import — FIXED
- [x] M4. warrior.py — Commanding Shout missing "Draw a card" — FIXED
- [x] M5. warrior.py — Heroic Strike +4 attack never expires — FIXED (EOT cleanup with weapon-replacement safety)
- [x] M6. paladin.py — Hand of Protection directly mutates divine_shield — FIXED (KEYWORD_GRANT)
- [x] M7. paladin.py — Humility/Aldor directly mutate characteristics.power — FIXED (TRANSFORM events)
- [x] M8. paladin.py — Equality directly mutates toughness/damage — FIXED (TRANSFORM + LIFE_CHANGE)
- [x] M9. paladin.py — Noble Sacrifice doesn't redirect attack — FIXED (combat ATTACK_DECLARED redirection support)
- [x] M10. paladin.py — Sword of Justice has no interceptor — FIXED (summon interceptor, token IDs wired, durability handling)
- [x] M11. classic.py — Polymorph all direct mutation — FIXED (event-driven TRANSFORM)
- [x] M12. classic.py — Acidic Swamp Ooze weapon destroy direct mutation — FIXED (OBJECT_DESTROYED / WEAPON_EQUIP fallback)
- [x] M13. classic.py — Sunfury/Defender of Argus Taunt grant direct mutation — FIXED (KEYWORD_GRANT)
- [x] M14. hunter.py — Hunter's Mark uses DAMAGE instead of health-setting — FIXED (TRANSFORM to set toughness)
- [x] M15. hunter.py — Eaglehorn Bow durability trigger not implemented — FIXED (friendly secret reveal detection)
- [x] M16. hunter.py — Gladiator's Longbow Immune not implemented — FIXED (immune grant/removal lifecycle)
- [x] M17. shaman.py — Windfury spell directly mutates state — FIXED (KEYWORD_GRANT)
- [x] M18. shaman.py — Hex all direct mutation before TRANSFORM event — FIXED (event-driven TRANSFORM)
- [x] M19. shaman.py — Unbound Elemental trigger not implemented — FIXED (Overload card detection on play/cast)
- [x] M20. shaman.py — Ancestral Healing direct mutation — FIXED (LIFE_CHANGE + KEYWORD_GRANT taunt)
- [x] M21. druid.py — Healing Touch wrong payload — FIXED (rewrote as hero-only heal)
- [x] M22. priest.py — Lightwell always heals hero first — FIXED (random among all damaged)
- [x] M23. basic.py — Darkscale Healer heals by direct mutation — FIXED (emits events)
- [x] M24. warlock.py — Bane of Doom unconditionally summons — FIXED (conditional on kill)
- [x] M25. warlock.py — Power Overwhelming missing end-of-turn death — FIXED (targeted buff + EOT death interceptor)
- [x] M26. warlock.py — Demonfire missing friendly Demon branch — FIXED
- [x] M27. mage.py — Vaporize fragile state.events access — FIXED (uses triggering ATTACK_DECLARED event)
- [x] M28. mage.py — Mirror Entity finds target by reverse-iterating — FIXED (uses triggering minion event directly)
- [x] M29. shaman.py — Lava Burst in SHAMAN_BASIC, should be SHAMAN_CLASSIC — FIXED
- [x] M30. shaman.py — Windfury spell targets any minion, should target friendly only — FIXED

## LOW (stubs, cosmetic, minor inaccuracies)

- [x] L1-L20: Text-only stubs and unimplemented complex effects (Ragnaros, Ysera, Alexstrasza, Velen, Auchenai, etc.) — RETIRED (implemented)

## Also fixed (bonus catches during review)

- warlock.py — Power Overwhelming PT_MODIFICATION `target` → `object_id`
- warlock.py — Blood Imp PT_MODIFICATION `target` → `object_id`
- warlock.py — Bane of Doom CREATE_TOKEN payload restructured with proper `token` dict
- hunter.py — Scavenging Hyena `permanent_id` → `object_id` in filter
- hunter.py — Deadly Shot `target` → `object_id` in OBJECT_DESTROYED payload
- druid.py — Cenarius card text updated to match 2/2 Treants

## Test Results After Fixes

- HS full suite: `4698 passed` (`tests/test_hearthstone.py tests/test_hs_unhappy*.py`)
