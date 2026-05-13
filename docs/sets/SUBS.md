# SUBS — Submarine Fleet (Depths Set 1)

## 1. Set Identity

**Set code:** `SUBS` · **Set module:** `submarine_fleet` (under `src/cards/depths/`) · **Theme:** WWII U-boat warfare reimagined as a card game where stealth is a depth-band coordinate and ordnance is a finite resource.

**Design statement:** SUBS is the engine's first set and so its job is to *teach* the depth ladder, the two-pool charge economy, and the stealth-vs-detection sub-game while still rewarding deck construction. Every archetype answers the depth question differently: Wolfpack rushes the surface bands and burns Torpedo, Silent Hunter sits at DEEP and weaponises detection cost, Carrier swarms the periscope band with cheap Drones, and Deep-Strike hoards Sonar all game then dives a finisher onto the Flagship's lap. The set is intentionally light on Doctrines (only ~3 per archetype) so first-game players get to feel the depth and detection systems before the persistent-effect layer comes online.

---

## 2. Set-specific Mechanics

### SILENT RUNNING
Detecting this Vessel costs +1 Sonar. (Cumulative with depth difficulty.) Already an engine keyword (`depths_combat.detection_cost`).

### WOLFPACK N
Whenever this Vessel attacks, if you control N or more other attacking Submarines, [bonus]. Triggers off `EventType.ATTACK_DECLARED`; counts attacking allies via `obj.state.attacking == True`.

### CHARGE-SWAP {nT/mS}
Activated abilities that explicitly convert one charge pool to the other (`{2T} → +1 SC`, `{2S} → +1 TC`), or hybrid `{X(T/S)}` costs payable from either pool.

### CRUSH-DIVE
When this Vessel changes depth, [bonus]. Triggers on `DEPTHS_DIVE` and `DEPTHS_SURFACE_VESSEL`. Bonus may scale with bands traversed.

### SHADOW-COUNT
Bonus equal to the number of opposing undetected Vessels. Static or one-shot. Scans battlefield for opposing Vessels with `state.detected == False`.

---

## 3. Archetypes (4 fixed)

### Wolfpack — *Kriegsmarine Wolfpack* (steel grey-blue)
Cheap Submarines flood SURFACE/PERISCOPE turns 1-3, then saturate-attack the Flagship while WOLFPACK N scales every attacker. Heavy Torpedo, light Sonar.
**Key cards:** Pack Leader U-99, Wolfpack Doctrine, Saturation Strike, Admiral Dönitz, U-Boat Wolf-cub.

### Silent Hunter — *Coastal Defense Force* (deep teal / sonar cyan)
Slow Submarines with SILENT RUNNING sit at DEEP/MID where detection costs 3-4 Sonar each. Weaponises that arithmetic with Crew that punish failed pings and Doctrines that turn undetected threats into per-turn Flagship damage. Even split, slight Sonar lean.
**Key cards:** U-Class Stalker, Iron Discipline, Echo Chamber Mate, Type-XXI Phantom, Sonar Jammer.

### Carrier — *Pacific Auxiliary Fleet* (oxidized brass / olive)
A Carrier sits at PERISCOPE producing Drone tokens (1/1 surface) every turn. Floods board with cheap Drones; relies on saturation Drone attacks plus anthems and sacrifice payoffs (Kamikaze Run). Front-loaded Torpedo.
**Key cards:** Escort Carrier, Fleet Carrier "Hiryu", Carrier Air Wing Doctrine, Kamikaze Run, Dive Bomber Squadron.

### Deep-Strike — *Special Operations* (abyss black / chromium accents)
Combo / control. Stalls 4-5 turns with Mines and chump-blockers, hoarding Sonar. Then a single huge Vessel (Black Demon X-7, Triton-Class) dives from SURFACE to CRUSH in one turn and detonates. Sonar-heavy.
**Key cards:** Triton-Class, Black Demon X-7, Crush-Depth Doctrine, Battery Reroute, Bathyscaphe Pilot.

---

## 4. Card list (150 cards)

Cost notation: T = Torpedo, S = Sonar; e.g. `{2T,1S}` = 2 Torpedo + 1 Sonar. Hybrid `{X(T/S)}` = X from either pool. P/H = Power/Hull. Depth column applies to Vessels and Mines.

Archetype codes: **WP** (Wolfpack), **SH** (Silent Hunter), **CR** (Carrier), **DS** (Deep-Strike), **N** (Neutral).

### Wolfpack — 30 cards

| name | type | cost | P/H | depth | arch | rules text |
|------|------|------|-----|-------|------|------------|
| U-Boat Wolf-cub | Vessel — Submarine | {1T} | 2/1 | SURFACE | WP | Vanilla. *Cheap pack body.* |
| Sea Wolf Scout | Vessel — Submarine | {1T} | 1/2 | SURFACE | WP | When this attacks alongside another attacking Submarine, draw 1. |
| Pack Runner | Vessel — Submarine | {2T} | 2/2 | SURFACE | WP | **Wolfpack 1**: +1 power EOT. |
| Coastal Raider | Vessel — Submarine | {2T} | 3/1 | SURFACE | WP | Vanilla. |
| Frenzied Torpedo Mate | Crew | {1T} | — | — | WP | Equipped Submarine gets +1/+0. |
| Brass Conduit Mate | Crew | {1T} | — | — | WP | Equipped Submarine gets +0/+1 and **silent_running**. |
| Pack Leader U-99 | Vessel — Submarine | {3T} | 3/3 | SURFACE | WP | **Wolfpack 2**: your attacking Submarines get +1 power EOT. |
| Type-VII Veteran | Vessel — Submarine | {3T} | 3/3 | PERISCOPE | WP | Whenever this attacks, gain 1 Torpedo Charge. |
| Echo Repeater | Vessel — Submarine | {2T,1S} | 2/3 | PERISCOPE | WP | When this attacks alongside another attacking Submarine, that other Submarine gets **homing** EOT. |
| Iron Bow Crew | Crew | {2T} | — | — | WP | Equipped Submarine gets +2/+0 and "Whenever it attacks, gain 1 TC." |
| Kapitänleutnant Kretschmer | Vessel — Submarine | {3T,1S} | 4/3 | PERISCOPE | WP | **Wolfpack 1**: opponent loses 1 Sonar. |
| Saturation Strike | Action | {2T} | — | — | WP | Your attacking Submarines get +2/+0 EOT. |
| Wolfpack Doctrine | Doctrine | {3T} | — | — | WP | Your Submarines get +1/+0. |
| Iron Cross Pennant | Doctrine | {2T,1S} | — | — | WP | Whenever 2+ Submarines you control attack, draw 1. |
| Forward Torpedo Tube | Weapon | {1T} | — | — | WP | Equipped: {1T}: deal 1 to a target Vessel. *3 charge counters; sinks at 0.* |
| Wire-Guided Spread | Weapon | {2T} | — | — | WP | Equipped: {1T}: deal 2 to target Vessel within 2 bands. |
| Surface Skirmisher | Vessel — Submarine | {2T} | 3/2 | SURFACE | WP | Vanilla aggressor. |
| Convoy Hunter | Vessel — Submarine | {3T} | 4/2 | SURFACE | WP | Whenever this deals damage to a Flagship, draw 1. |
| Dönitz's Recall | Action | {1T,1S} | — | — | WP | Untap up to 2 attacking Submarines you control. |
| Loaded Tubes | Action | {1T} | — | — | WP | Target Submarine gets +3/+0 and **homing** EOT. |
| Iron Coffin Veteran | Vessel — Submarine | {2T} | 2/3 | PERISCOPE | WP | When sunk, deal 1 to opposing Flagship. |
| Hammerhead U-505 | Vessel — Submarine | {4T} | 5/3 | PERISCOPE | WP | **Wolfpack 3**: deals double damage EOT. |
| Pack Mind Officer | Crew | {2S} | — | — | WP | Equipped Submarine has **Wolfpack 1**: pack gains +0/+1 EOT. |
| Surface Strike Doctrine | Doctrine | {3T,1S} | — | — | WP | At your end step, if 2+ Submarines you control attacked this turn, deal 1 to opposing Flagship. |
| Reload at Dock | Action | {1T} | — | — | WP | Untap target Submarine and remove all damage from it. |
| Gunnery Officer | Crew | {1T,1S} | — | — | WP | Equipped Submarine has **homing**. |
| Coordinated Strike | Action | {3T} | — | — | WP | Up to 3 target Submarines you control gain **Wolfpack 1** EOT and untap. |
| Kriegsmarine Banner | Doctrine | {2T} | — | — | WP | Your Submarines that entered this turn lose summoning sickness. |
| Type-IX Long Hunter | Vessel — Submarine | {4T,1S} | 4/5 | MID | WP | **Wolfpack 2**: gain 2 Torpedo. |
| Admiral Dönitz | Vessel — Submarine, Legendary | {5T,1S} | 6/6 | PERISCOPE | WP | When this attacks alongside 3+ Submarines, your attacking Submarines deal +2 damage EOT. |

### Silent Hunter — 30 cards

| name | type | cost | P/H | depth | arch | rules text |
|------|------|------|-----|-------|------|------------|
| Periscope Recon | Vessel — Submarine | {1T} | 1/2 | PERISCOPE | SH | **Silent Running**. |
| Listening Post | Vessel — Submarine | {1S} | 0/3 | MID | SH | **defender**, **silent_running**. |
| Diesel Whisper | Vessel — Submarine | {2T,1S} | 2/3 | MID | SH | **Silent Running**. Whenever an opposing detection attempt against this fails, draw 1. |
| Echo Chamber Mate | Crew | {2S} | — | — | SH | Equipped Vessel has **silent_running**; whenever a detection attempt against equipped fails, draw 1. |
| Cold Hull Engineer | Crew | {1S} | — | — | SH | Equipped Vessel has **silent_running** and +0/+1. |
| Stalker Sub | Vessel — Submarine | {2T} | 2/2 | PERISCOPE | SH | **Silent Running**. Crush-Dive: gain 1 Sonar. |
| Bottom-Crawler Probe | Vessel — Submarine | {2S} | 1/4 | DEEP | SH | **bottom_crawler**, **silent_running**. |
| Acoustic Decoy | Mine | {1S} | — | PERISCOPE | SH | When triggered, the triggering Vessel becomes detected and takes 2. |
| Sonar Jammer | Action | {1S} | — | — | SH | Opponent's detection attempts cost +1 Sonar EOT. |
| Failed Ping | Action | {2S} | — | — | SH | Counter target detection attempt; opponent loses 2 Sonar. |
| U-Class Stalker | Vessel — Submarine | {2T,1S} | 2/3 | MID | SH | **Silent Running**. |
| Cold-Cathode Periscope | Weapon | {1S} | — | — | SH | Equipped Vessel has **silent_running**. {1S}: that Vessel gains +1/+0 EOT. |
| Iron Discipline | Doctrine | {3S} | — | — | SH | Your Vessels at DEEP cannot be detected. |
| Type-XXI Phantom | Vessel — Submarine | {4T,2S} | 5/4 | DEEP | SH | **Silent Running**, **homing**. |
| Sonar Decoy Crew | Crew | {1T,1S} | — | — | SH | Equipped Vessel: when an opposing detection attempt against it fails, opponent loses 1 SC. |
| Hydrophone Operator | Crew | {1S} | — | — | SH | Equipped Vessel: at your upkeep, look at top card of opponent's library. |
| Dive Master | Crew | {2S} | — | — | SH | Equipped Vessel's dives cost 0. |
| Whisper Below | Action | {2S} | — | — | SH | Target Vessel becomes undetected and dives 1 band. |
| Silent Service Doctrine | Doctrine | {2S} | — | — | SH | Whenever a Vessel you control becomes undetected, gain 1 SC. |
| Dead-Stop Maneuver | Action | {1S} | — | — | SH | Target Vessel you control becomes undetected and gains **silent_running** EOT. |
| Snorkel Stalker | Vessel — Submarine | {2T} | 3/2 | PERISCOPE | SH | **Silent Running**. Whenever this attacks while undetected, +2 power EOT. |
| Threat Board Analyst | Crew | {1S} | — | — | SH | Equipped Vessel gets +1/+0 for each opposing undetected Vessel (**Shadow-Count**). |
| Wolf at the Door | Vessel — Submarine | {3T,1S} | 3/4 | DEEP | SH | **Silent Running**. While undetected, has **homing**. |
| Black Sea Veteran | Vessel — Submarine | {3T,2S} | 3/3 | DEEP | SH | **Silent Running**. Crush-Dive: detect target Vessel an opponent controls (free). |
| Quiet Reload | Action | {2S} | — | — | SH | Target Vessel you control becomes undetected; gain 2 TC. |
| Acoustic Camouflage | Doctrine | {2T,2S} | — | — | SH | Your Vessels enter the battlefield with **silent_running**. |
| Operational Brief | Action | {1S} | — | — | SH | Draw 2; if you control an undetected Vessel, draw 3. |
| Periscope Sweep | Action | {1S} | — | — | SH | Detect target Vessel; if it has cost 3 or less, also tap it. |
| Submersion Veteran | Vessel — Submarine | {2T,1S} | 2/4 | MID | SH | **Silent Running**. Crush-Dive: this gets +1/+0 EOT. |
| Black Sea Doctrine | Doctrine | {3T,3S} | — | — | SH | At your end step, deal 1 to opposing Flagship for each undetected Vessel you control. |

### Carrier — 30 cards

| name | type | cost | P/H | depth | arch | rules text |
|------|------|------|-----|-------|------|------------|
| Hangar Tech | Crew | {1T} | — | — | CR | Equipped Carrier produces 1 extra Drone token per trigger. |
| Pilot Cadet | Vessel — Drone | {1T} | 1/1 | SURFACE | CR | Vanilla token-style body. |
| Recon Drone | Vessel — Drone | {1T} | 1/1 | SURFACE | CR | When sunk, draw 1. |
| Escort Frigate | Vessel — Destroyer | {2T} | 2/2 | SURFACE | CR | **reach**. |
| Patrol Bomber | Vessel — Drone | {2T} | 2/1 | SURFACE | CR | **homing**. |
| Escort Carrier | Vessel — Carrier | {3T} | 1/5 | PERISCOPE | CR | At your end step, create a 1/1 Drone token at SURFACE. |
| Drone Catapult | Weapon | {2T} | — | — | CR | Equipped Carrier creates 1 additional Drone per trigger. |
| Air-Sea Coordinator | Crew | {1T,1S} | — | — | CR | Equipped Vessel: at your end step, all your Drones get +1/+0 EOT. |
| Fleet Carrier "Hiryu" | Vessel — Carrier | {4T,1S} | 2/6 | PERISCOPE | CR | At your end step, create two 1/1 Drone tokens at SURFACE. |
| Drone Swarm | Action | {2T} | — | — | CR | Create three 1/1 Drone tokens at SURFACE. |
| Carrier Air Wing Doctrine | Doctrine | {3T} | — | — | CR | Your Drones get +1/+0 and have **homing**. |
| Kamikaze Run | Action | {1T} | — | — | CR | Sacrifice a Drone: deal 3 damage to target Vessel ignoring depth modifier. |
| Catapult Officer | Crew | {1T} | — | — | CR | Equipped Carrier produces +1 Drone per trigger. |
| Skipjack Drone | Vessel — Drone | {1T} | 2/1 | SURFACE | CR | When this is sunk, you may pay {1T} to create a 1/1 Drone token. |
| Dive Bomber Squadron | Action | {3T,1S} | — | — | CR | Each Drone you control deals 1 damage to target Vessel. |
| Saber Strike Drone | Vessel — Drone | {2T,1S} | 2/2 | PERISCOPE | CR | **homing**. |
| Crash-Boat Pilot | Vessel — Drone | {2T} | 2/2 | SURFACE | CR | When this attacks the Flagship, sacrifice it: deal 4 damage. |
| Air Group Doctrine | Doctrine | {2T,1S} | — | — | CR | Whenever you create a Drone token, gain 1 TC. |
| Repair Crew | Crew | {1T,1S} | — | — | CR | Equipped Vessel: at your upkeep, remove 1 damage from it. |
| Hangar Bay Doctrine | Doctrine | {3T,1S} | — | — | CR | Your Carriers create 1 extra Drone per trigger. |
| Refit Run | Action | {2T} | — | — | CR | Remove all damage from target Carrier; create a 1/1 Drone. |
| Drone Pen Mate | Crew | {1T} | — | — | CR | Equipped Carrier: when it deploys a Drone, that Drone gets +1/+0 EOT. |
| Veteran Squadron Lead | Crew | {2T,1S} | — | — | CR | Equipped Vessel: your Drones get +1/+1. |
| Strike Group Bonsai | Action | {2T,1S} | — | — | CR | Two target Drones you control attack as one (combine power for one strike, both tap). |
| Light Carrier "Shoho" | Vessel — Carrier | {3T} | 1/4 | PERISCOPE | CR | When this attacks, create a 1/1 Drone at SURFACE. |
| Heavy Cruiser Escort | Vessel — Destroyer | {3T,1S} | 4/4 | SURFACE | CR | **reach**. |
| Anti-Sub Drone | Vessel — Drone | {1T,1S} | 1/1 | PERISCOPE | CR | **homing**, **reach**. |
| Carrier Battle Group | Doctrine | {4T,2S} | — | — | CR | Your Carriers have +0/+3; create 1 additional Drone per trigger. |
| Fleet Admiral Yamamoto | Vessel — Carrier, Legendary | {6T,2S} | 3/8 | PERISCOPE | CR | At your end step, create three 1/1 Drone tokens at SURFACE. Drones you control have **homing**. |
| Last-Stand Drone Wave | Action | {3T} | — | — | CR | Create five 1/1 Drone tokens at SURFACE; if you have <8 hull, they get +1/+0 EOT. |

### Deep-Strike — 30 cards

| name | type | cost | P/H | depth | arch | rules text |
|------|------|------|-----|-------|------|------------|
| Bathyscaphe Mite | Vessel — Submarine | {1S} | 0/2 | DEEP | DS | **bottom_crawler**, **defender**. |
| Pressure Probe | Vessel — Drone | {1T} | 1/1 | DEEP | DS | Crush-Dive: gain 1 SC. |
| Salvage Diver | Vessel — Submarine | {2S} | 1/3 | DEEP | DS | **bottom_crawler**. {2S}: dive 1 band. |
| Bathyscaphe Pilot | Crew | {1T,1S} | — | — | DS | Equipped Vessel's dives cost 0. |
| Pressure Hull Veteran | Vessel — Submarine | {3T,1S} | 3/4 | MID | DS | **Crush-Dive**: draw 1. |
| Deep-Lurker | Vessel — Submarine | {2T,1S} | 2/3 | MID | DS | **bottom_crawler**. Crush-Dive: gain +1/+0 EOT. |
| Battery Reroute | Doctrine | {1S} | — | — | DS | {2T}: gain 1 SC. {2S}: gain 1 TC. *Each once per turn.* |
| Crush-Depth Doctrine | Doctrine | {2T,1S} | — | — | DS | Whenever a Vessel you control changes depth 2+ bands in a turn, deal 1 to opposing Flagship. |
| Black Demon X-7 | Vessel — Submarine, Legendary | {4T,4S} | 6/4 | SURFACE | DS | **Crush-Dive**: deal 4 damage to target Vessel. **homing**. |
| Triton-Class | Vessel — Submarine, Legendary | {6T,2S} | 8/8 | SURFACE | DS | **homing**. Whenever this dives, gain 2 TC. |
| Scuba Saboteur | Vessel — Submarine | {2T,1S} | 2/2 | DEEP | DS | **bottom_crawler**. When this is sunk, you may put a Mine card from your hand on the battlefield free at any depth. |
| Thermocline Cloak | Crew | {2S} | — | — | DS | Equipped Vessel: detection cost +2 while at MID/DEEP/CRUSH. |
| Dive Tube | Weapon | {1S} | — | — | DS | Equipped Vessel: {1S}: dive 1 band. |
| Crush-Depth Charges | Action | {2T,2S} | — | — | DS | Deal 4 damage to target Vessel ignoring depth modifier. |
| Pressure Wave | Action | {3T,1S} | — | — | DS | Each Vessel you control dives 1 band; each opposing Vessel takes 1 damage. |
| Sound-Channel Pilot | Crew | {2T,2S} | — | — | DS | Equipped Vessel has **homing** and **reach**. |
| Coelacanth Class | Vessel — Submarine | {3T,2S} | 4/4 | DEEP | DS | **bottom_crawler**, **homing**. |
| Crush Capacitor | Weapon | {2T,1S} | — | — | DS | Equipped Vessel: when it changes depth, deal 1 to opposing Flagship. |
| Sonar Hoard Doctrine | Doctrine | {2S} | — | — | DS | At your end step, if you have 6+ SC, draw 1. |
| Contingency Plan | Action | {X(T/S)} | — | — | DS | Gain X charges in either pool (at most until cap). |
| Bathysphere Veteran | Vessel — Submarine | {3T,1S} | 3/5 | DEEP | DS | **bottom_crawler**. Crush-Dive: this gains +0/+2 EOT. |
| Deep Pulse Bomb | Action | {2T,2S} | — | — | DS | Deal 2 damage to each Vessel and to the opposing Flagship; ignore depth modifier. |
| Final Surge | Action | {X(T/S)} | — | — | DS | Target Vessel you control gains +X/+0 EOT and **homing**. |
| Frogman Squad | Vessel — Submarine | {2S} | 2/2 | DEEP | DS | **bottom_crawler**. {1S}: tap target Vessel. |
| Cold-Water Engineer | Crew | {2T,1S} | — | — | DS | Equipped Vessel: each Crush-Dive trigger fires twice. |
| Battery Drain | Action | {1T,1S} | — | — | DS | Opponent loses up to 3 SC. |
| Deep Vector Doctrine | Doctrine | {3S} | — | — | DS | The first dive each turn for each Vessel you control is free. |
| Implosion Strike | Action | {4T,2S} | — | — | DS | Sacrifice a Vessel at DEEP: deal damage equal to its hull to target Vessel or Flagship. |
| Shadow-Vector | Vessel — Submarine | {4T,1S} | 4/4 | DEEP | DS | **Crush-Dive**: deal 2 to opposing Flagship. **bottom_crawler**. |
| Abyssal Doctrine | Doctrine | {4T,3S} | — | — | DS | Your Vessels at DEEP/CRUSH get **homing** and **silent_running**. |

### Neutral — 30 cards

| name | type | cost | P/H | depth | arch | rules text |
|------|------|------|-----|-------|------|------------|
| Diesel-Electric Sub | Vessel — Submarine | {2T} | 2/2 | SURFACE | N | Vanilla generic body. |
| Coastal Patrol Boat | Vessel — Submarine | {1T} | 1/2 | SURFACE | N | Vanilla. |
| Steam Pinnace | Vessel — Submarine | {1T} | 2/1 | SURFACE | N | Vanilla. |
| Reserve Engineer | Crew | {1T} | — | — | N | Equipped Vessel gets +1/+1. |
| Rear-Tube Loader | Crew | {1T} | — | — | N | Equipped Vessel gets +0/+2. |
| Periscope Watch | Crew | {1S} | — | — | N | Equipped Vessel: at your upkeep, gain 1 SC. |
| Compass Officer | Crew | {1T} | — | — | N | Equipped Vessel: dives cost 0 the first time each turn. |
| Sonar Buoy | Mine | {1T} | — | SURFACE | N | When triggered, deal 2 damage. |
| Magnetic Mine | Mine | {1T,1S} | — | PERISCOPE | N | When triggered, deal 3 damage. |
| Acoustic Trip | Mine | {2T,1S} | — | MID | N | When triggered, deal 4 damage. |
| Pressure Mine | Mine | {2T,2S} | — | DEEP | N | When triggered, deal 5 damage and detect the triggering Vessel. |
| Decoy Buoy | Action | {1T} | — | — | N | Create a 0/2 Decoy Vessel token at SURFACE; it can intercept once. |
| Dive Order | Action | {1S} | — | — | N | Up to 2 Vessels you control dive 1 band (free). |
| Surface Order | Action | {0} | — | — | N | Up to 2 Vessels you control surface 1 band. |
| Resupply Run | Action | {1T} | — | — | N | Gain 1 TC and 1 SC. |
| Chart Plot | Action | {1S} | — | — | N | Draw 1; gain 1 SC. |
| Damage Control | Action | {1T} | — | — | N | Remove up to 3 damage from target Vessel you control. |
| Brace for Impact | Action | {1T,1S} | — | — | N | Prevent the next 4 damage to target Vessel you control EOT. |
| Sonar Sweep | Action | {2S} | — | — | N | Detect each opposing Vessel at SURFACE/PERISCOPE. |
| Torpedo Spread | Action | {2T} | — | — | N | Deal 2 damage to up to 2 target Vessels. |
| Deep Charge | Action | {2T,1S} | — | — | N | Deal 4 damage to target Vessel at MID, DEEP, or CRUSH. |
| Helm Officer | Crew | {1T} | — | — | N | Equipped Vessel can fire from one band shallower than its actual depth. |
| Stoker Mate | Crew | {1T} | — | — | N | Equipped Vessel gets +1/+0. |
| Sonar Tech | Crew | {1S} | — | — | N | Equipped Vessel has **silent_running**. |
| Hull Plate | Weapon | {1T} | — | — | N | Equipped Vessel gets +0/+2. |
| Spare Torpedo | Weapon | {1T} | — | — | N | {1T}: deal 1 damage to target Vessel. *3 charges.* |
| Captain's Bell | Doctrine | {2T,1S} | — | — | N | Whenever you deploy a Vessel, gain 1 TC. |
| Bridge Logbook | Doctrine | {1S} | — | — | N | At your upkeep, scry 1. |
| Light Cruiser | Vessel — Destroyer | {3T} | 3/3 | SURFACE | N | **reach**. |
| Coastguard Cutter | Vessel — Destroyer | {2T} | 2/3 | SURFACE | N | **reach**. |

**150 cards total**: 30 WP + 30 SH + 30 CR + 30 DS + 30 N.

---

## 5. Per-set art style preamble

See `src/cards/depths/submarine_fleet/style.py` for the canonical Python module consumed by the art harness.

**STYLE_HEADLINE**: WWII Kriegsmarine reconnaissance plates crossed with deep-sea documentary cinematography. Dim, technical, oppressively wet — every frame feels lit by failing sodium lamp inside a steel pressure hull or the cold blue-green spill of an active sonar dome. Deep ultramarine and abyssal black, oxidised brass and rust-orange, sodium-yellow interior glow, sonar cyan/teal sweep lines, salt-stained off-white. Painterly oil-on-canvas or photographic grain over crisp digital surfaces. Sailors weathered, not glamorous. Strong vertical-pressure framing.

---

## 6. Pipeline coordination

**Stage 4 splits** (one parallel agent per file):
- `src/cards/depths/submarine_fleet/wolfpack.py` → `WOLFPACK_CARDS`
- `src/cards/depths/submarine_fleet/silent_hunter.py` → `SILENT_HUNTER_CARDS`
- `src/cards/depths/submarine_fleet/carrier.py` → `CARRIER_CARDS`
- `src/cards/depths/submarine_fleet/deep_strike.py` → `DEEP_STRIKE_CARDS`
- `src/cards/depths/submarine_fleet/neutral.py` → `NEUTRAL_CARDS`

**Shared factories**: `src/cards/depths/submarine_fleet/_factories.py` — `make_vessel`, `make_crew`, `make_weapon`, `make_mine`, `make_action`, `make_doctrine`. All five archetype files import these.

**Aggregating `__init__.py`** merges all five into `SUBS_CARDS` and auto-wires image URLs.

**Stage 6 deck builders** in `decks.py`:
- `make_subs_wolfpack_deck()` → label `SUBS_wolfpack`
- `make_subs_silent_hunter_deck()` → label `SUBS_silent_hunter`
- `make_subs_carrier_deck()` → label `SUBS_carrier`
- `make_subs_deep_strike_deck()` → label `SUBS_deep_strike`

Deck labels MUST start with `SUBS_` (load-bearing for balance loop).

---

## 7. Out of scope

1. No DFC / transform.
2. No real-time / hidden-information mechanics.
3. No bidding modal choices.
4. No multi-turn delayed abilities.
5. No copy/clone effects.

---

## Archetype changelog

### Cycle 1 — Carrier deck rebuild (audit-driven, 2026-05-06)

Pre-cycle Carrier winrate: **0.0% (15 losses / 15 games)**. Audit routed
to `archetype_redesign` because card-tweaking can't lift a deck losing
every game. Diagnosis showed three independent engine gaps were
silently breaking the loop:

1. `make_end_step_trigger` filters on `payload['phase'] == 'end_step'`
   but the depths turn manager emits `phase == 'surface'` (and `'dive'`
   for upkeep). **Every Carrier's drone-spawn trigger was a no-op** —
   Escort Carrier / Hiryu / Yamamoto produced exactly zero Drones across
   all 15 games (`triggers_fired: 0` for every Carrier in the per-card
   stats).
2. The Medium AI's `MEDIUM_MIN_ATTACK_DAMAGE = 2` threshold means a 1/1
   Drone refuses to swing at the Flagship (1 damage < threshold). Even
   if (1) had been working, the spawned Drones would have stood inert.
3. `cast_effect_fn` set on Action `CardDefinition`s is never invoked by
   the engine — Drone Swarm / Kamikaze Run / Dive Bomber Squadron all
   resolved to no-ops on cast.

Redesign category: **Light + a touch of Moderate.** No new mechanics,
no rewriting strategic identity. Specific changes:

* **`carrier.py`** — added `make_depths_end_phase_trigger` and
  `make_depths_dive_phase_trigger` helpers that watch for
  `phase == 'surface'` / `phase == 'dive'` (the depths turn manager's
  actual phase names). Re-pointed all Carriers' end-step triggers and
  Repair Crew's upkeep trigger at these.
* **`carrier.py`** — bumped the `DRONE_TOKEN` template and Pilot
  Cadet / Recon Drone from 1/1 to **2/1** so they clear the AI's
  attack threshold.
* **`carrier.py`** — every Carrier now also fires an **ETB drone-spawn
  trigger** (so even the turn it lands, the Carrier produces value)
  and grants its own static **+0/+1 anthem** to your Drones (2/1 → 2/2,
  surviving most aggro trades). This bakes the Carrier Air Wing
  Doctrine into the Vessel itself, since the AI doesn't deploy
  Doctrines.
* **Light Carrier "Shoho"** — bumped from 1/4 to **2/4** (so it can
  attack), added an ETB drone-spawn alongside its existing on-attack
  spawn, plus the same static anthem.
* **`decks.py`** — rebuilt `CARRIER_DECK_SPEC`: dropped Doctrines
  (Carrier Air Wing Doctrine, Hangar Bay Doctrine — never deploy) and
  the Action cards whose `cast_effect_fn` doesn't run (Drone Swarm,
  Kamikaze Run, Dive Bomber Squadron). Replaced with more cheap Drone
  bodies (Patrol Bomber, Skipjack Drone), Crew anchors that exist as
  on-board permanents (Veteran Squadron Lead +1/+1 Drones, Drone Pen
  Mate, Air-Sea Coordinator), and one Crash-Boat Pilot for a sacrifice
  payoff that uses an attack-trigger (ATTACK_DECLARED — fires
  reliably). Deck size unchanged at 30.

Cards in `CARRIER_CARDS` registry are unchanged — the original 30
remain importable so `coverage.py` and tests still see the full set.
Doctrines + Action cards just aren't in the deck anymore.

Post-fix smoke tournament (8 games per pairing, 24 games per archetype):

| Archetype        | Wins | Games | Winrate    |
|------------------|------|-------|------------|
| SUBS_carrier     | 14   | 24    | **58.3%**  |
| SUBS_silent_hunter | 11 | 24    | **45.8%**  |
| SUBS_deep_strike | 11   | 24    | **45.8%**  |
| SUBS_wolfpack    | 12   | 24    | **50.0%**  |

All four archetypes now sit in the 40–60% target band — Carrier
recovered from 0% baseline, and the previously dominant Wolfpack
naturally settled at 50% as Carrier's defensive trades cooled the
race-aggro plan. Far above the 5% success criterion the audit
required.

The underlying engine gaps (broken phase-name helpers, dead
`cast_effect_fn`, AI Doctrine deployment, OBJECT_CREATED handler
ignoring `depth_band` payload key, depths_combat checking
`characteristics.toughness` instead of `get_toughness`) are real
problems for cycles 2+ to address at the engine level. The cycle 1
fix routes around them entirely from the card-side.
