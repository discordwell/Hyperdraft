"""
Hyperdraft Core Types

Everything is an Event. Everything else is an Interceptor.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional
from uuid import uuid4


# =============================================================================
# IDs
# =============================================================================

def new_id() -> str:
    return str(uuid4())[:8]


# =============================================================================
# Event Types
# =============================================================================

class EventType(Enum):
    # Object lifecycle
    OBJECT_CREATED = auto()
    OBJECT_DESTROYED = auto()
    ZONE_CHANGE = auto()
    ENTER_BATTLEFIELD = auto()  # Legacy marker event used by some test helpers

    # State changes
    TAP = auto()
    UNTAP = auto()
    GAIN_CONTROL = auto()  # Change a permanent's controller (often until end of turn)
    CONTROL_CHANGE = auto()  # Alias for GAIN_CONTROL used by some card scripts
    COUNTER_ADDED = auto()
    COUNTER_REMOVED = auto()
    PT_MODIFICATION = auto()  # Temporary P/T changes (until end of turn, etc.)
    PT_MODIFIER = auto()      # Alias for PT_MODIFICATION (power_mod/toughness_mod payload)
    PT_CHANGE = auto()        # Alias for temporary P/T changes (power/toughness deltas)
    PT_MODIFY = auto()        # Alias for temporary P/T changes (power/toughness deltas)
    TEMPORARY_PT_CHANGE = auto()  # Alias for temporary P/T changes (power/toughness deltas)

    # Combat
    COMBAT_DECLARED = auto()  # Alias used by some card scripts (beginning of combat)
    ATTACK_DECLARED = auto()
    BLOCK_DECLARED = auto()
    DAMAGE = auto()

    # Resources
    MANA_PRODUCED = auto()
    MANA_SPENT = auto()
    LIFE_CHANGE = auto()

    # Card actions
    DRAW = auto()
    DISCARD = auto()
    CAST = auto()
    SPELL_CAST = auto()  # Alias for card files using this name
    ACTIVATE = auto()

    # Turn structure
    PHASE_START = auto()
    PHASE_END = auto()
    PHASE_CHANGE = auto()  # Legacy alias used by some card scripts
    TURN_START = auto()
    TURN_END = auto()
    PRIORITY_PASS = auto()

    # Meta
    GAME_START = auto()
    GAME_END = auto()
    PLAYER_LOSES = auto()
    PLAYER_WINS = auto()

    # Query events (for continuous effects)
    QUERY_POWER = auto()
    QUERY_TOUGHNESS = auto()
    QUERY_TYPES = auto()
    QUERY_SUBTYPES = auto()
    QUERY_SUPERTYPES = auto()
    QUERY_COLORS = auto()
    QUERY_ABILITIES = auto()
    QUERY_COST = auto()
    QUERY_ACTIVATION_COST = auto()  # Synthetic query for activated-ability cost reduction

    # Targeting
    TARGET_REQUIRED = auto()  # Card requires a target to be chosen
    TARGET_CHANGED = auto()   # Legacy marker (target changed by an effect)
    # TARGET_CHOSEN fires once per (spell/ability, target) pair when a spell or
    # ability finalises its target selection (i.e. just after the stack item is
    # built and its chosen_targets are committed). Payload:
    #   spell_id   - id of the spell/ability source object (or stack item card_id)
    #   target_id  - id of the chosen target (object id or player id)
    #   controller - controller of the spell/ability (the caster)
    # Used by Ward to react to opponent-targeting; intentionally fires for both
    # SPELL and ACTIVATED/TRIGGERED ABILITY stack items so a v1 of Ward can be
    # implemented without the engine having to model abilities-on-the-stack.
    TARGET_CHOSEN = auto()

    # Library manipulation
    SCRY = auto()              # Look at top N cards, put any on bottom
    SURVEIL = auto()           # Look at top N cards, put any in graveyard
    MILL = auto()              # Put top N cards into graveyard
    EXPLORE = auto()           # Reveal top card, +1/+1 or keep on top
    DISCOVER = auto()          # Exile until CMC <= N; player chooses cast-free or hand
    SEARCH_LIBRARY = auto()    # Search library for card
    LIBRARY_SEARCH = auto()    # Alias for SEARCH_LIBRARY
    LOOK_AT_TOP = auto()       # Look at top N cards
    LOOK_AT_HAND = auto()      # Look at (or force-reveal) a player's hand — information event
    REVEAL_TOP = auto()        # Reveal top card(s)
    REVEAL_UNTIL_LAND = auto() # Reveal until land found
    EXILE_FROM_TOP = auto()    # Exile top card(s) of library
    EXILE_TOP = auto()         # Legacy alias for EXILE_FROM_TOP used by some card scripts
    IMPULSE_DRAW = auto()      # Exile top, may play until end of turn

    # Token creation
    CREATE_TOKEN = auto()      # Create a token

    # Sacrifice
    SACRIFICE = auto()         # Sacrifice a permanent
    SACRIFICE_REQUIRED = auto()        # Player must sacrifice
    SACRIFICE_ALL = auto()             # Sacrifice all of type
    OPTIONAL_SACRIFICE_FOR_EFFECT = auto()  # May sacrifice for effect

    # Temporary effects
    PUMP = auto()              # +X/+Y until end of turn
    TEMPORARY_EFFECT = auto()  # Generic temporary effect
    GRANT_KEYWORD = auto()     # Grant keyword until end of turn
    KEYWORD_GRANT = auto()     # Alias for GRANT_KEYWORD (keyword until end of turn)

    # Conditional effects
    CONDITIONAL_COUNTERS = auto()      # Add counters if condition met
    CONDITIONAL_DISCARD = auto()       # Discard if condition met
    OPTIONAL_COST_FOR_EFFECT = auto()  # Pay optional cost for effect
    OPTIONAL_DISCARD_FOR_EFFECT = auto()  # Discard for effect

    # Misc
    EXILE = auto()             # Exile a card/permanent
    FLICKER = auto()           # Exile and return at the beginning of the next end step
    UNLOCK_DOOR = auto()       # Duskmourn: unlock a Door/Room (mechanic stub)
    MANIFEST_DREAD = auto()    # Duskmourn manifest dread mechanic
    MANA_ADDED = auto()        # Mana was added to pool
    ADD_MANA = auto()          # Alias for mana production
    TAP_FOR_EFFECT = auto()    # Tap as part of an effect
    CONDITIONAL_EFFECT = auto() # Effect with condition

    # Additional card-used events
    DESTROY = auto()                       # Destroy a permanent
    REGENERATE = auto()                    # Regeneration shield replaced a destroy (tap + clear damage + leave combat)
    COUNTER = auto()                       # Counter a spell/ability
    COUNTER_SPELL = auto()                 # Alias for COUNTER (counter a spell)
    COUNTER_SPELL_UNLESS_PAY = auto()      # Alias (counter unless pay)
    SPELL_COUNTERED = auto()               # Marker event (spell was countered)
    MAKE_UNCOUNTERABLE = auto()            # Set can_be_countered=False on a target stack item
    COPY_SPELL = auto()                    # Copy a spell on the stack
    COPY_STACK_ITEM = auto()               # Copy any stack item (spell or activated/triggered ability)
    RETURN_TO_HAND = auto()                # Return permanent to hand
    RETURN_FROM_GRAVEYARD = auto()         # Return card from graveyard
    RETURN_TO_HAND_FROM_GRAVEYARD = auto() # Bounce from graveyard to hand
    BOUNCE = auto()                        # Alias: return permanent to its owner's hand
    TAP_TARGET = auto()                    # Tap target permanent
    UNTAP_TARGET = auto()                  # Untap target permanent
    UNTAP_ALL = auto()                     # Untap all of type
    REVEAL_HAND = auto()                   # Reveal player's hand
    LIFE_GAIN = auto()                     # Alias - use LIFE_CHANGE with amount > 0
    LIFE_LOSS = auto()                     # Alias - use LIFE_CHANGE with amount < 0
    EXTRA_TURN = auto()                    # Take an extra turn
    EXTRA_COMBAT = auto()                  # Extra combat phase
    PHASE_OUT = auto()                     # Phase out a permanent
    PHASE_IN = auto()                      # Phase in a permanent
    FREEZE = auto()                        # Freeze a permanent (doesn't untap)
    TRANSFORM = auto()                     # Transform a DFC
    GRANT_ABILITY = auto()                 # Grant an ability temporarily
    GRANT_RESTRICTION = auto()             # Grant a restriction temporarily (mechanic stub)
    GRANT_CAST_FROM_GRAVEYARD = auto()     # Temporarily allow casting spells from your graveyard
    GRANT_PLAY_LANDS_FROM_GRAVEYARD = auto()  # Temporarily allow playing lands from your graveyard
    GRANT_EXILE_INSTEAD_OF_GRAVEYARD = auto() # Temporarily replace "to graveyard" with exile
    GRANT_UNBLOCKABLE = auto()             # Grant can't be blocked
    GRANT_PT_MODIFIER = auto()             # Grant P/T modifier
    TEMPORARY_BOOST = auto()               # Temporary stat boost (alias for PUMP)
    REMOVE_ABILITIES = auto()              # Remove all abilities from permanent
    CONTINUOUS_EFFECT = auto()             # Register continuous effect
    DELAYED_TRIGGER = auto()               # Create delayed trigger
    DELAYED_SACRIFICE = auto()             # Sacrifice at end of turn
    MODAL_CHOICE = auto()                  # Player makes modal choice
    MAY_PAY_LIFE = auto()                  # May pay life for effect
    MAY_PAY_DRAW = auto()                  # May pay to draw
    MAY_SACRIFICE = auto()                 # May sacrifice for effect
    OPTIONAL_COST = auto()                 # Pay optional additional cost
    DISCARD_CHOICE = auto()                # Choose cards to discard
    LOOK_TOP_CARDS = auto()                # Look at top N cards of library
    EXILE_TOP_CARD = auto()                # Exile top card of library
    EXILE_TOP_PLAY = auto()                # Exile top, may play
    IMPULSE_TO_GRAVEYARD = auto()          # Put impulse-drawn cards to graveyard
    PUT_TIME_COUNTER = auto()              # Put time counters on permanent
    DECLARE_ATTACKERS = auto()             # Declare attackers step
    AUTO_EQUIP = auto()                    # Auto-equip to creature
    ATTACH = auto()                        # MTG: attach Equipment/Aura to a permanent
    UNATTACH = auto()                      # MTG: detach an Equipment/Aura
    FIGHT = auto()                         # Two creatures deal damage to each other
    CANT_BLOCK = auto()                    # Creature can't block (restriction)
    TURN_FACE_UP = auto()                  # Turn a face-down creature face up

    # Hearthstone mechanics
    HERO_POWER_ACTIVATE = auto()           # Activate hero power
    WEAPON_EQUIP = auto()                  # Equip weapon to hero
    WEAPON_ATTACK = auto()                 # Hero attacks with weapon
    WEAPON_DURABILITY_LOSS = auto()        # Weapon loses durability
    DIVINE_SHIELD_BREAK = auto()           # Divine shield is broken
    FREEZE_TARGET = auto()                 # Freeze a minion or hero
    SILENCE_TARGET = auto()                # Silence a minion (remove all effects)
    SECRET_TRIGGER = auto()                # Secret card triggers
    FATIGUE_DAMAGE = auto()                # Damage from drawing empty deck
    ARMOR_GAIN = auto()                    # Hero gains armor
    ADD_TO_HAND = auto()                   # Add a card definition to hand as new object

    # Pokemon TCG mechanics
    PKM_ATTACH_ENERGY = auto()        # Attach energy card to Pokemon
    PKM_EVOLVE = auto()               # Evolve a Pokemon
    PKM_RETREAT = auto()              # Retreat active Pokemon
    PKM_ATTACK_DECLARE = auto()       # Declare an attack
    PKM_ATTACK_DAMAGE = auto()        # Calculate and apply attack damage
    PKM_APPLY_WEAKNESS = auto()       # Weakness modifier step
    PKM_APPLY_RESISTANCE = auto()     # Resistance modifier step
    PKM_PLACE_DAMAGE_COUNTERS = auto() # Place counters (bypasses W/R)
    PKM_HEAL = auto()                 # Remove damage counters
    PKM_KNOCKOUT = auto()             # Pokemon knocked out
    PKM_TAKE_PRIZE = auto()           # Take prize card(s)
    PKM_PROMOTE_ACTIVE = auto()       # Promote benched Pokemon to active
    PKM_PLAY_BASIC = auto()           # Play basic Pokemon to bench
    PKM_PLAY_ITEM = auto()            # Play Item trainer
    PKM_PLAY_SUPPORTER = auto()       # Play Supporter trainer
    PKM_PLAY_STADIUM = auto()         # Play Stadium trainer
    PKM_ATTACH_TOOL = auto()          # Attach Pokemon Tool
    PKM_USE_ABILITY = auto()          # Use a Pokemon Ability
    PKM_APPLY_STATUS = auto()         # Apply status condition
    PKM_REMOVE_STATUS = auto()        # Remove status condition
    PKM_CHECKUP = auto()              # Between-turns checkup
    PKM_CHECKUP_POISON = auto()       # Poison tick
    PKM_CHECKUP_BURN = auto()         # Burn tick + coin flip
    PKM_CHECKUP_SLEEP = auto()        # Sleep coin flip
    PKM_CHECKUP_PARALYSIS = auto()    # Paralysis recovery
    PKM_COIN_FLIP = auto()            # Coin flip result
    PKM_DISCARD_ENERGY = auto()       # Discard energy from Pokemon
    PKM_SWITCH = auto()               # Switch effect (not retreat)
    PKM_MULLIGAN = auto()             # Opening hand mulligan
    PKM_SETUP = auto()                # Game setup phase
    PKM_LOST_ZONE = auto()            # Card moved to the (shared) Lost Zone
    PKM_REVEAL_HAND = auto()          # Opponent forced to reveal their hand
    PKM_REVEAL = auto()               # Public reveal of card(s) from a hidden zone
    PKM_FORCE_SWITCH = auto()         # Opponent forced to switch Active (Boss's Orders)
    PKM_MOVE_ENERGY = auto()          # Energy moved between Pokemon (own or opp)
    PKM_PRIZE_TAX = auto()            # Marker: future prize draws reduced
    PKM_COST_REDUCTION = auto()       # Attack cost reduced (Tool / Stadium effect)
    PKM_DETACH_TOOL = auto()          # Tool detached (KO or replaced by another Tool)

    # OTJ Plot mechanic
    PLOT_PAID = auto()                # Plot cost was paid; card goes to exile
    PLOT_CAST = auto()                # Plotted card cast from exile (free)
    PLOT_BECOMES_PLOTTED = auto()     # Trigger event for "when this becomes plotted"

    # OTJ Saddle mechanic
    SADDLE_PAID = auto()              # Saddle cost was paid (creatures tapped)
    SADDLE_BECOMES_SADDLED = auto()   # Mount becomes saddled until end of turn
    SADDLE_ATTACK_TRIGGER = auto()    # Marker for "attacks while saddled" effects

    # Edge of Eternities — Warp mechanic
    WARP_CAST = auto()                # A card is being cast for its warp cost (alternate cost)
    WARP_EXILE_SCHEDULED = auto()     # End-step exile has been scheduled for a warp-cast permanent
    WARP_EXILE = auto()               # End-step exile actually fires for a warp-cast permanent
    # Marvel's Spider-Man (SPM) mechanics. See src/engine/spm_mechanics.py for helpers.
    # Web-slinging: alternate cast cost from hand. Pay the web-slinging mana cost
    # AND return a tapped creature you control to its owner's hand instead of
    # paying the spell's regular mana cost. Sorcery speed unless the spell has flash.
    WEBSLING_REGISTER = auto()        # Marker: a card with web-slinging entered a public zone (book-keeping)
    WEBSLING_RETURN_CREATURE = auto() # Resolve "return tapped creature you control to its owner's hand" portion of the cost
    WEBSLING_CAST = auto()            # Marker: spell was cast for its web-slinging cost (payload: spell_id, returned_card_id, returned_mv, controller)
    # Mayhem: alternate cast cost from graveyard if the card was discarded this turn.
    # Sorcery-speed timing applies. Discard tracking happens via state.turn_data['discarded_card_ids'].
    MAYHEM_DISCARD_TRACK = auto()     # Marker: a card with mayhem was discarded; appended to turn_data['discarded_card_ids']
    MAYHEM_REGISTER = auto()          # Marker: a card with mayhem entered a public zone (book-keeping)
    MAYHEM_CAST = auto()              # Marker: spell was cast for its mayhem cost (payload: spell_id, controller)

    # Yu-Gi-Oh! mechanics
    YGO_NORMAL_SUMMON = auto()        # Normal Summon a monster
    YGO_TRIBUTE_SUMMON = auto()       # Tribute Summon (level 5+)
    YGO_SET_MONSTER = auto()          # Set a monster face-down
    YGO_FLIP_SUMMON = auto()          # Flip Summon a set monster
    YGO_SPECIAL_SUMMON = auto()       # Special Summon (any method)
    YGO_ACTIVATE_SPELL = auto()       # Activate a Spell card
    YGO_SET_SPELL_TRAP = auto()       # Set a Spell/Trap face-down
    YGO_ACTIVATE_TRAP = auto()        # Activate a Trap card
    YGO_CHAIN_LINK = auto()           # Add a link to the Chain
    YGO_CHAIN_RESOLVE = auto()        # Resolve the Chain (LIFO)
    YGO_BATTLE_DECLARE = auto()       # Declare an attack
    YGO_BATTLE_DAMAGE = auto()        # Battle damage dealt
    YGO_FLIP = auto()                 # Monster flipped face-up
    YGO_POSITION_CHANGE = auto()      # Monster position changed
    YGO_DESTROY = auto()              # Effect family: destroy target_ids (handler moves to GY)
                                      # payload: {'target_ids': [str], 'source_id': str, 'reason': str (optional)}
                                      # Also accepted (single-target legacy): {'card_id': str}
    YGO_DESTROYED = auto()            # Notification: a card was just destroyed
                                      # payload: {'card_id': str, 'card_name': str, 'owner': str,
                                      #           'controller': str, 'from_zone': str, 'reason': str,
                                      #           'source_id': str}
    YGO_SEND_TO_GY = auto()           # Effect family: send card_id from any zone to GY
                                      # payload: {'card_id': str, 'from_zone': str (optional),
                                      #           'reason': str (e.g. 'tribute', 'discard', 'cost')}
    YGO_SENT_TO_GY = auto()           # Notification: a card was just sent to GY (non-destroy path)
                                      # payload: {'card_id': str, 'card_name': str, 'owner': str,
                                      #           'controller': str, 'from_zone': str, 'reason': str}
    YGO_BANISH = auto()               # Card banished
    YGO_EQUIP = auto()                # Equip card to monster
    YGO_DRAW = auto()                 # Draw Phase draw OR effect-induced draw / search-to-hand
                                      # payload: {'player', 'card_id'?, 'count'?, 'source'?}
                                      # source values: None|'draw'|'search'|'recovery'|'add_to_hand'
    YGO_SEARCH_DECK = auto()          # Tutor: search deck/GY/banish for a card matching predicate
                                      # payload: {'player', 'card_id', 'filter_desc'?, 'destination': 'hand'|'field'}
                                      # Always emit a YGO_DRAW follow-up so generic draw-reactive triggers fire.
    YGO_LP_CHANGE = auto()            # Life Points change (request).
                                      # payload: {
                                      #   'player': pid, 'amount': int (positive=gain, negative=burn),
                                      #   'source': str (card name for log),
                                      #   '_engine_apply': bool (True = pipeline mutates LP; False/missing
                                      #     = caller already mutated, this event is informational only)
                                      # }
    YGO_LP_CHANGED = auto()           # Follow-up: LP delta has been applied.
                                      # payload: {'player': pid, 'amount': int, 'new_lp': int, 'source': str}
    YGO_GAME_OVER = auto()            # LP-zero (or other) loss condition triggered.
                                      # payload: {'player': pid (loser), 'reason': str}
    YGO_ACTIVATE_MONSTER_EFFECT = auto()  # Activate a monster's Ignition/Quick Effect
                                          # payload: {'monster_id', 'effect_index', 'player', 'targets'}

    # Minecraft TCG mechanics
    MC_PLAY_CARD = auto()             # Play/craft a Minecraft card
    MC_ASSIGN_WORKER = auto()         # Exhaust a mob/worker to mine a biome
    MC_AVATAR_ACTION = auto()         # Use the once-per-turn avatar action
    MC_EXPLORE_BIOME = auto()         # Upgrade/replace a biome slot
    MC_MATERIAL_GAIN = auto()         # Materials were added to a player stockpile
    MC_MATERIAL_SPEND = auto()        # Materials were spent from a player stockpile
    MC_GRID_PLACE = auto()            # Structure/block/tool entered Minecraft board state
    MC_RESPAWN = auto()               # Avatar died and respawned at a Bed
    MC_DAY_NIGHT_FLIP = auto()        # Day/night cycle changed
    MC_DECLARE_ATTACKERS = auto()     # Minecraft combat attackers declared
    MC_DECLARE_BLOCKERS = auto()      # Minecraft combat blockers declared
    MC_COMBAT_DAMAGE = auto()         # Minecraft combat damage marker
    MC_END_TURN = auto()              # Minecraft turn-end action marker

    # ------------------------------------------------------------------
    # Depths (submarine fleet) mechanics. See src/engine/depths.py.
    # All Depths events follow MTG-style {payload, source, controller}
    # contracts. The depth ladder uses the DepthBand enum from
    # src/engine/depths.py with numeric values (SURFACE=0, PERISCOPE=1,
    # MID=2, DEEP=3, CRUSH=4) so depth-difference math works.
    # ------------------------------------------------------------------
    # DEPTHS_DIVE: a Vessel descends one or more depth bands.
    #   Payload: {'object_id': str, 'from_band': DepthBand,
    #             'to_band': DepthBand, 'controller': str}
    #   Source: the Vessel id. The depths.py system interceptors check
    #   for opposing Mines at the destination band and emit
    #   DEPTHS_MINE_TRIGGER damage in response.
    DEPTHS_DIVE = auto()
    # DEPTHS_SURFACE_VESSEL: a Vessel ascends one or more depth bands.
    #   Payload: {'object_id': str, 'from_band': DepthBand,
    #             'to_band': DepthBand, 'controller': str}
    #   Source: the Vessel id. Mines at the destination band also trigger.
    #   Note: named DEPTHS_SURFACE_VESSEL (not DEPTHS_SURFACE) to avoid
    #   colliding with the SURFACE turn phase.
    DEPTHS_SURFACE_VESSEL = auto()
    # DEPTHS_DETECT: a Vessel becomes "pinged" — its detected flag flips
    # to True and it becomes a legal interceptor target.
    #   Payload: {'object_id': str, 'detector': str (player_id),
    #             'sonar_spent': int, 'duration': str}
    #   duration is one of 'end_of_turn' | 'until_leaves' | 'forever'.
    DEPTHS_DETECT = auto()
    # DEPTHS_DETECTION_FAIL: a detection attempt fizzled (insufficient
    # Sonar Charges or the target was protected by silent_running etc.).
    #   Payload: {'object_id': str, 'detector': str, 'reason': str,
    #             'sonar_required': int, 'sonar_available': int}
    DEPTHS_DETECTION_FAIL = auto()
    # DEPTHS_PING_DECAY: a previously-detected Vessel reverts to
    # undetected at end-of-turn cleanup. Marker emitted by the Sonar
    # Decay step in the Surface (end) phase.
    #   Payload: {'object_id': str, 'controller': str}
    DEPTHS_PING_DECAY = auto()
    # DEPTHS_LAY_MINE: a player places a Mine at a chosen depth band.
    #   Payload: {'object_id': str (mine), 'controller': str,
    #             'depth_band': DepthBand}
    #   Source: the Mine card object id. Movement onto the battlefield
    #   already happens through ZONE_CHANGE; this is a marker so triggers
    #   and UI can react.
    DEPTHS_LAY_MINE = auto()
    # DEPTHS_MINE_TRIGGER: a Mine fires because an opposing Vessel
    # entered or attacked from the Mine's depth band.
    #   Payload: {'mine_id': str, 'target_id': str (vessel),
    #             'amount': int, 'depth_band': DepthBand,
    #             'controller': str (mine controller)}
    #   The depths system interceptor follows this with a DAMAGE event
    #   targeting the vessel and a SACRIFICE/destroy of the mine itself
    #   (mines are one-shot).
    DEPTHS_MINE_TRIGGER = auto()
    # DEPTHS_RESUPPLY: fired during the Beginning (Dive) phase to grant
    # +1 Torpedo Charge and +1 Sonar Charge (each capped at the per-turn
    # ceiling of min(turn_number, 10)).
    #   Payload: {'player': str, 'tc_gained': int, 'sc_gained': int,
    #             'cap': int}
    DEPTHS_RESUPPLY = auto()
    # DEPTHS_OXYGEN_TICK: a submerged Vessel's oxygen counter decrements
    # one step (during the Surface end-step Sonar Decay sub-step). When
    # oxygen reaches 0 the Vessel typically forces a surface or sinks;
    # the card-level effect_fn decides.
    #   Payload: {'object_id': str, 'controller': str,
    #             'old_oxygen': int, 'new_oxygen': int}
    DEPTHS_OXYGEN_TICK = auto()
    # DEPTHS_BECOME_UNDETECTED: a previously-detected Vessel reverts to
    # undetected via a card effect (Dead-Stop Maneuver, Quiet Reload, etc.).
    # The depths system interceptor REACTs by setting ``state.detected`` to
    # False and clearing any persistence marker.
    #   Payload: {'object_id': str, 'source': str}
    DEPTHS_BECOME_UNDETECTED = auto()
    # DAMAGE_REMOVE: a card effect removes damage from a Vessel (e.g.
    # Damage Control). The depths system interceptor REACTs by
    # decrementing ``state.damage`` (clamped at 0). For Flagship targets
    # the change is mirrored onto ``player.life`` so SBA/UI stay in sync.
    #   Payload: {'object_id': str, 'amount': int}
    DAMAGE_REMOVE = auto()

    # Library search subsystem (player-choice-driven tutors)
    LIBSEARCH_BEGIN = auto()          # Open the search choice (creates PendingChoice)
    LIBSEARCH_REVEAL = auto()         # Reveal a chosen card (marker event for triggers)
    LIBSEARCH_COMPLETE = auto()       # Finalize: move card to destination (post-choice)
    LIBSEARCH_SHUFFLE = auto()        # Shuffle library after a search (often part of complete)

    # MTG Saga mechanic
    SAGA_LORE_ADDED = auto()          # A lore counter is being added to a Saga
    SAGA_CHAPTER = auto()             # A Saga chapter ability is triggering
    # OTJ Crime mechanic
    CRIME_COMMITTED = auto()          # A player committed a crime (targeted opp/opp's permanent/opp's GY card)
    # Bloomburrow (BLB) set mechanics. See src/engine/blb_mechanics.py for helpers.
    OFFSPRING_TRIGGERED = auto()      # Marker: offspring resolved -> 1/1 token copy was created
    FORAGE_PAID = auto()              # Marker: forage cost was paid (3 GY exiled OR Food sacrificed)
    EXPEND_4_REACHED = auto()         # Player crossed 4 total mana spent this turn
    EXPEND_8_REACHED = auto()         # Player crossed 8 total mana spent this turn
    VALIANT_TARGETED = auto()         # Permanent became target of an ally spell/ability
    # Avatar TLA Bending mechanics — marker events fired when a bending action
    # occurs. These let other cards observe bending (e.g. Aang's transform).
    # Effect events (MANA_ADDED, COUNTER_ADDED, ZONE_CHANGE) still do the work.
    BENDING_FIREBEND = auto()         # Firebending X resolved: payload = {'amount': X, 'controller', 'source'}
    BENDING_WATERBEND = auto()        # Waterbend cost paid: payload = {'amount': X, 'controller', 'source'}
    BENDING_EARTHBEND = auto()        # Earthbend X resolved: payload = {'amount': X, 'controller', 'source', 'land_id'}
    BENDING_AIRBEND = auto()          # Airbend resolved: payload = {'amount': X, 'controller', 'source', 'target_id'}
    # Edge of Eternities — Lander mechanic
    LANDER_CREATED = auto()           # A Lander token was created
    LANDER_SACRIFICED = auto()        # A Lander token was sacrificed (sets turn_data flag)
    LANDER_SEARCH_LAND = auto()       # Resolve the search-for-basic-land step of Lander activation
    # Edge of Eternities — Station mechanic
    STATION_ACTIVATE = auto()           # Player taps another creature to charge a Station
    STATION_CHARGE = auto()             # Charge counters being added to a Station
    STATION_THRESHOLD_REACHED = auto()  # Station reached a charge threshold
    STATION_ACTIVATED = auto()          # Marker: Station ability resolved (post-charge, post-threshold)
    # Edge of Eternities — Void mechanic
    VOID_ACTIVATED = auto()           # Marker: Void condition became true this turn for a player
    VOID_TRIGGERED = auto()           # Marker: a Void-gated triggered ability fired this turn

    # Generic coin flip primitive (FIN, custom sets, legacy cards). The
    # turn_state tracker emits/observes these. Payload typically includes
    # 'result': bool (True=heads), 'player': str (optional caller).
    COIN_FLIP = auto()
    # ------------------------------------------------------------------
    # Face-down mechanic (Manifest, Manifest Dread, Cloak, Disguise, Morph).
    # Implementation lives in src/engine/face_down.py and the helpers in
    # src/cards/interceptor_helpers.py (FACE-DOWN HELPERS section).
    # NOTE: TURN_FACE_UP is declared earlier in this enum (line ~185) and is
    # the canonical event used to flip a face-down permanent face up.
    # ------------------------------------------------------------------
    FACE_DOWN_ENTER = auto()          # Marker: a permanent has entered the battlefield face-down
    FACE_DOWN_TURNED_UP = auto()      # Marker: a permanent was turned face-up (post-flip)
    FACE_DOWN_QUERY_MASK = auto()     # Internal marker (reserved for future overrides)
    # ------------------------------------------------------------------
    # Final Fantasy (FIN) — Tiered cost mechanic.
    # Implementation lives in src/engine/tiered.py and the helper in
    # src/cards/interceptor_helpers.py (TIERED COST section).
    # Payload: {'player': str, 'card_id': str, 'tiers': list[dict]}, where
    # each tier dict is {'name': str, 'extra_cost': str, 'effect_label': str}.
    # ------------------------------------------------------------------
    TIERED_CHOICE = auto()            # Player must choose a tier as the spell is cast

    # ------------------------------------------------------------------
    # Outlaws of Thunder Junction (OTJ) — Spree cost-per-mode mechanic.
    # Implementation lives in src/engine/spree.py and the helper in
    # src/cards/interceptor_helpers.py (SPREE section).
    # Payload: {'card_id': str, 'controller': str, 'modes': list[dict],
    #           'selected': list[int] | None}, where each mode dict is
    # {'name': str, 'extra_cost': str, 'description': str}.
    # ------------------------------------------------------------------
    SPREE_MODE_CHOSEN = auto()        # Spree mode prompt opened / mode(s) chosen

    # ------------------------------------------------------------------
    # Shadowmoor / Lorwyn — Conspire mechanic (CR 702.78). Implementation
    # lives in src/engine/conspire.py and the helper re-export in
    # src/cards/interceptor_helpers.py (CONSPIRE GRANT section). This is
    # purely a telemetry/UI marker; the COPY_STACK_ITEM event does the
    # actual work. Payload:
    #   {'spell_id': str, 'stack_item_id': str, 'controller': str,
    #    'tapped': list[str] (creature ids tapped to pay conspire),
    #    'source_id': str (the grant source — e.g. Raiding Schemes id)}
    # ------------------------------------------------------------------
    CONSPIRE_TRIGGERED = auto()       # Marker: caster paid the conspire cost; copy is being queued

    # ------------------------------------------------------------------
    # Generic replacement-effect telemetry. Fired by ``make_replacement_effect``
    # whenever a TRANSFORM-priority replacement rewrites an event. Useful for
    # logs / tests / future debug UIs. Payload:
    #   source       - id of the permanent providing the replacement
    #   replacer_id  - id of the interceptor that fired
    #   original     - dict snapshot of the pre-replacement payload
    #   replacement  - list of post-replacement events (typically length 1)
    # ------------------------------------------------------------------
    REPLACEMENT_FIRED = auto()

    # Vehicle / artifact-becomes-creature: install a TRANSFORM interceptor on
    # QUERY_TYPES that adds CREATURE to the type-set for the target. Used by
    # Crew, Aetherdrift Exhaust-vehicle animations, and any "X becomes a
    # creature" effect that needs to grant the CREATURE type WITHOUT going
    # through the full becomes_creature P/T/abilities sweep.
    # Payload: {'object_id': str, 'duration': 'end_of_turn'|'until_leaves'|'forever'}
    GRANT_CREATURE_TYPE = auto()

    # Granted activated abilities (Equipment / Aura "Equipped creature has '<cost>: <effect>'").
    # Payload: {'target_id': str, 'source_id': str, 'cost': str, 'effect_fn': Callable, 'description': str}.
    # Resolution registers the ability on the target creature, tagged with
    # _granted_by=source_id so cleanup on UNATTACH can remove it.
    GRANT_ACTIVATED_ABILITY = auto()

    # ------------------------------------------------------------------
    # Cast-from-zone permission system (W7).
    # See src/engine/cast_permission.py and the make_castable_from_zone
    # helper in src/cards/interceptor_helpers.py. The priority handler
    # (_handle_cast_spell) consults QUERY_CAST_LEGALITY before refusing a
    # cast from a non-HAND zone. CAST_FROM_ZONE_GRANT is a marker emitted
    # when a permission interceptor is installed (useful for triggers /
    # debugging; not required by the lookup itself).
    # ------------------------------------------------------------------
    CAST_FROM_ZONE_GRANT = auto()     # Marker: permission to cast from a zone was granted
    QUERY_CAST_LEGALITY = auto()      # Synthetic query: is this card castable from its current zone?

    # ------------------------------------------------------------------
    # Cycling (W8). CR 702.32. Implementation: src/engine/cycling.py.
    #
    # CYCLE: marker event fired when a player resolves a cycling ability.
    #   Payload: {'player': str, 'card_id': str, 'card_name': str,
    #             'variant': 'plain'|'landcycling'|'typecycling',
    #             'mana_cost': str (the cost text, e.g. '{2}')}.
    #   Used by external "Whenever a player cycles a card, ..." triggers and
    #   for telemetry. Emitted from the cycling ability's resolve_fn before
    #   any draw / search effects so triggers can read pre-effect state.
    #
    # CYCLING_TRIGGERED: rider trigger marker fired immediately after the
    #   on-card "When you cycle this, ..." rider effect_fn runs. Used for
    #   tests/logs (rider events themselves are returned as new events from
    #   the resolve_fn and are processed normally).
    # ------------------------------------------------------------------
    CYCLE = auto()
    CYCLING_TRIGGERED = auto()

    # ------------------------------------------------------------------
    # Planeswalker loyalty framework. See src/engine/planeswalker.py
    # and the helpers in src/cards/interceptor_helpers.py
    # (Planeswalker loyalty section).
    # ------------------------------------------------------------------
    # Marker emitted on every successful loyalty ability activation. Payload:
    #   source        - planeswalker object id
    #   controller    - activating player id
    #   ability_id    - logical id of the loyalty ability (e.g. "+1", "-3")
    #   cost          - signed loyalty cost (positive add, negative remove)
    LOYALTY_ABILITY_ACTIVATED = auto()
    # Marker emitted by the planeswalker damage TRANSFORM hook when damage is
    # redirected to remove loyalty counters from a planeswalker. Payload:
    #   target        - planeswalker object id
    #   amount        - amount of damage redirected to loyalty
    #   source        - id of the damaging permanent (or None)
    PLANESWALKER_DAMAGED = auto()

    # ------------------------------------------------------------------
    # W15: Planeswalker deepening — combat redirect, legend rule, emblems.
    # See src/engine/planeswalker.py / src/engine/emblem.py.
    # ------------------------------------------------------------------
    # Emitted when an emblem is created. Payload:
    #   emblem_id     - id of the new emblem
    #   controller    - player who owns/controls the emblem
    #   source_card   - source PW name (informational)
    EMBLEM_CREATED = auto()
    # Marker emitted when the legend rule destroys a duplicate legendary
    # permanent. Payload:
    #   object_id     - permanent put into graveyard
    #   kept_id       - permanent the player chose to keep
    #   name          - shared legendary name
    LEGEND_RULE_TRIGGERED = auto()

    # ------------------------------------------------------------------
    # Exhaust mechanic — reset hook (Aetherdrift / TLA).
    # Some cards (e.g. Elvish Refueler) say "you may activate exhaust
    # abilities as though they hadn't been activated." Emitting
    # EXHAUST_RESET clears the once_per_game_used flag for one or more
    # ActivatedAbility descriptors, allowing them to be activated again.
    # Payload (one of):
    #   target_id     - object id whose Exhaust abilities should reset (all)
    #   ability_index - optional, reset only that index on target_id
    #   controller    - player id whose Exhaust abilities should reset
    #                   (used for "your exhaust abilities" wording)
    # The pipeline doesn't need a dedicated handler; the activated module
    # exposes ``reset_exhaust(state, ...)`` for direct invocation, and
    # cards typically emit this event so observers (logs / UI) can react.
    # ------------------------------------------------------------------
    EXHAUST_RESET = auto()

    # ------------------------------------------------------------------
    # Triggered abilities on the stack (CR 603.2 / 603.3).
    # Marker emitted whenever a triggered-ability interceptor is queued onto
    # state.pending_triggers. Useful for telemetry, logs, and tests. Payload:
    #   source_id          - object that owns the trigger
    #   source_card_name   - name of the source object (informational)
    #   controller         - player who controls the trigger
    #   description        - human-readable description (e.g. "ETB: gain 3 life")
    # ------------------------------------------------------------------
    TRIGGERED_ABILITY_PUT_ON_STACK = auto()

    # ------------------------------------------------------------------
    # Finance TCG events — see src/engine/finance.py.
    # ------------------------------------------------------------------
    FIN_PLAY_CARD = auto()       # Finance card played from hand
    FIN_CARD_CAST = auto()       # Spell pushed onto FinanceStack (frontend: order-placed sound)
    FIN_CARD_RESOLVED = auto()   # Spell resolved off the top of the stack (sound: order-filled)
    FIN_CARD_COUNTERED = auto()  # Spell countered before resolution (sound: order-cancelled)
    FIN_MARKET_EVENT = auto()    # Dark Pool card triggered (phase-deferred Order fires)
    FIN_LEVERAGE_TICK = auto()   # Leverage counter cost accrued at Market Close
    FIN_CAPITAL_CALL = auto()    # Capital Reserve damage from a non-combat source
    FIN_BANKRUPTCY = auto()      # Player's Capital Reserve reached 0


    # ------------------------------------------------------------------
    # Cats — trick-taking + pile-building card game. See src/engine/cats.py.
    # Each round: Stretch -> Pounce -> Counter-pounce -> Resolve -> Claim ->
    # Curl up. Two players play one card per round; the trick winner claims
    # the trick into one of their three scoring piles (or attention).
    # ------------------------------------------------------------------
    CATS_ROUND_START = auto()           # Stretch phase opened. Payload: {'round_number': int}
    CATS_ROUND_END = auto()             # Curl-up phase closed. Payload: {'round_number': int}
    CATS_CARD_PLAYED = auto()           # Pounce or Counter-pounce. Payload: {'player': str, 'card_id': str, 'role': 'pounce'|'counter'}
    CATS_TRICK_RULE_QUERY = auto()      # Synthetic query: what rule resolves this trick? Mood interceptors REPLACE.
    CATS_TRICK_RESOLVE = auto()         # Trick winner determined. Payload: {'winner': str, 'cards': list[str]}
    CATS_CLAIM_PILE = auto()            # Winner is sending cards to a pile. Payload: {'player': str, 'pile': str, 'card_ids': list[str]}
    CATS_PILE_CAPPED = auto()           # A scoring pile hit its cap. Payload: {'player': str, 'pile': str, 'overflow': list[str]}
    CATS_PILE_ACTIVATE = auto()         # Player activates a pile-card ability. Payload: {'player': str, 'card_id': str, 'pile': str}
    CATS_KNOCK_OVER = auto()            # A pile card was knocked over (tapped) as an activation cost.
    CATS_QUERY_PILE_SCORE = auto()      # Synthetic query: rewrite a pile's contribution to final score.
    CATS_GAME_OVER = auto()             # Marker: round 9 ended + both hands empty -> finalize scores.
    CATS_REVEAL = auto()                # A card's hidden info (e.g. Sneaky sneaky_value) is revealed. Payload: {'player': str, 'card_id': str, 'sneaky_value': int}

    # ------------------------------------------------------------------
    # Clankers — newly-sentient AIs building battle robots from multi-card
    # assemblies (chassis + weapons + add-ons). Always-7-cards-in-hand floor.
    # See src/engine/clankers.py.
    # ------------------------------------------------------------------
    CLANKERS_TURN_START = auto()            # Boot phase opened. Payload: {'player': str, 'turn_number': int}
    CLANKERS_TURN_END = auto()              # Cleanup phase closed. Payload: {'player': str, 'turn_number': int}
    CLANKERS_ATTACH_PART = auto()           # Attach action. Payload: {'part_id': str, 'target_chassis_id': str, 'controller': str}
    CLANKERS_DETACH_PART = auto()           # Detach action. Payload: {'part_id': str, 'former_host_id': str}
    CLANKERS_PART_ATTACHED = auto()         # Marker: part successfully attached. Payload: {'part_id', 'target_chassis_id'}
    CLANKERS_PART_DETACHED = auto()         # Marker: part successfully detached.
    CLANKERS_HAND_REFILL_QUERY = auto()     # Synthetic query: should this player refill to 7? Payload: {'player_id', 'current_hand_size', 'target_hand_size': 7, 'may': True}
    CLANKERS_QUERY_POWER = auto()           # Synthetic query: effective power of a chassis assembly. Payload: {'chassis_id', 'base_value', 'result'}
    CLANKERS_QUERY_INTEGRITY = auto()       # Synthetic query: effective integrity of a chassis assembly. Same shape.
    CLANKERS_COMPUTE_SPEND = auto()         # Compute spent. Payload: {'player_id', 'amount', 'source_card_id'}
    CLANKERS_COMPUTE_GAIN = auto()          # Compute gained (Boot refresh, card effects).
    CLANKERS_SCRAP_GAIN = auto()            # Scrap pool increased.
    CLANKERS_SCRAP_SPEND = auto()           # Scrap pool decreased.
    CLANKERS_CHASSIS_DESTROYED = auto()     # Marker: a chassis was destroyed. Payload includes attached part list (death cascade).
    CLANKERS_WEAPON_DESTROYED = auto()      # Marker: a weapon was destroyed (combat damage to chassis, cascade, or direct effect).
    CLANKERS_ADD_ON_DESTROYED = auto()      # Marker: an add-on was destroyed.
    CLANKERS_DEATH_CASCADE = auto()         # Marker: a chassis death triggered its attached parts going to scrap. Payload: {'chassis_id', 'cascaded_part_ids': list[str]}
    CLANKERS_ATTACK_DECLARE = auto()        # Attacker declared in Combat phase. Payload: {'attacker_id', 'attacker_controller'}
    CLANKERS_BLOCK_DECLARE = auto()         # Blocker assigned. Payload: {'attacker_id', 'blocker_id', 'blocker_controller'}
    CLANKERS_COMBAT_DAMAGE = auto()         # Combat damage event. Payload: {'attacker_id', 'defender_id', 'amount', 'damage_credited_to'}
    CLANKERS_WORKSHOP_DAMAGE = auto()       # Damage routed to Core's workshop_integrity (unblocked attacker, Transient effect, etc.).
    CLANKERS_WORKSHOP_BREACHED = auto()     # Workshop Integrity hit 0. Game-end trigger. Payload: {'player_id'} = loser.
    CLANKERS_CONTAINMENT_FAILURE_TICK = auto()  # Deathclock fired. Payload: {'turn': int, 'damage': int}
    CLANKERS_CORE_PASSIVE = auto()          # Marker: a Core Processor passive triggered (for observability/logging).
    CLANKERS_REFILL_TAKEN = auto()          # Marker: a player actually took their Allocate-phase refill (after may-decision).
    CLANKERS_REFILL_DECLINED = auto()       # Marker: a player declined the refill.
    CLANKERS_ACTIVATE = auto()              # Marker: an activated ability fired. Payload: {'player_id', 'source_id', 'ability_index', 'targets', 'compute_paid', 'exhausted_self'}

    # SCP (Foundation vs Insurgency) — see src/engine/scp.py.
    SCP_INSTALL = auto()         # A card was installed. Payload: {'player','object_id','kind'}
    SCP_ADVANCE = auto()         # An anomaly gained an advancement token. Payload: {'player','object_id','advancement'}
    SCP_CONTAIN = auto()         # An anomaly locked into containment. Payload: {'player','object_id','value','containment_points'}
    SCP_INFILTRATE = auto()      # The Insurgency began a run. Payload: {'player','target'}
    SCP_LAYER_ENCOUNTER = auto() # A layer was encountered during a run. Payload: {'player','layer_id','rezzed','broken'}
    SCP_ACCESS = auto()          # The Insurgency accessed a target. Payload: {'player','target'}
    SCP_FREE = auto()            # An anomaly was freed/stolen. Payload: {'player','object_id','value','liberation_points'}
    SCP_BREACH = auto()          # Total Breach increased. Payload: {'amount','total_breach'}
    SCP_DAMAGE = auto()          # Damage dealt to the Insurgency. Payload: {'player','amount'}
    SCP_EXPOSE = auto()          # The Insurgency was exposed (tagged). Payload: {'player'}
    SCP_WIN = auto()             # A faction met a win condition. Payload: {'winner','loser','reason'}
    SCP_ACTIVATE = auto()        # An installed asset/tool ability was activated. Payload: {'player','object_id'}
    SCP_SABOTAGE = auto()        # Central access resolved (HQ/Research/Archives). Payload: {'player','central','effect'}


class EventStatus(Enum):
    PENDING = auto()      # On the stack, can be responded to
    RESOLVING = auto()    # Currently resolving
    RESOLVED = auto()     # Done
    PREVENTED = auto()    # Cancelled


@dataclass
class Event:
    type: EventType
    payload: dict = field(default_factory=dict)
    source: Optional[str] = None      # Object ID that caused this
    controller: Optional[str] = None  # Player ID who controls source
    status: EventStatus = EventStatus.RESOLVING
    id: str = field(default_factory=new_id)
    timestamp: int = 0

    def copy(self) -> 'Event':
        return Event(
            type=self.type,
            payload=dict(self.payload),
            source=self.source,
            controller=self.controller,
            status=self.status,
            id=new_id(),
            timestamp=self.timestamp
        )


# =============================================================================
# Interceptor Types
# =============================================================================

class InterceptorPriority(Enum):
    TRANSFORM = 1   # Runs first - can change the event
    PREVENT = 2     # Can stop the event
    REACT = 3       # Runs after - creates new events
    QUERY = 4       # Modifies state reads


class InterceptorAction(Enum):
    PASS = auto()       # Do nothing
    TRANSFORM = auto()  # Modify the event
    PREVENT = auto()    # Cancel the event
    REACT = auto()      # Queue new events
    REPLACE = auto()    # Replace event with others


@dataclass
class InterceptorResult:
    action: InterceptorAction
    transformed_event: Optional[Event] = None
    new_events: list[Event] = field(default_factory=list)


# Type alias for interceptor handler functions
InterceptorHandler = Callable[['Event', 'GameState'], InterceptorResult]
EventFilter = Callable[['Event', 'GameState'], bool]


@dataclass
class Interceptor:
    id: str
    source: str                     # Object ID that created this
    controller: str                 # Player ID
    priority: InterceptorPriority
    filter: EventFilter             # What events to intercept
    handler: InterceptorHandler     # What to do
    timestamp: int = 0              # For ordering

    # Lifecycle
    duration: Optional[str] = None  # 'forever', 'end_of_turn', 'until_leaves'
    uses_remaining: Optional[int] = None

    # CR 603.2: Marks this interceptor as a triggered ability. When True, the
    # pipeline's REACT phase will not invoke effect_fn inline; it will instead
    # queue a ``TriggeredStackItem`` onto ``state.pending_triggers`` so the
    # trigger can be put on the stack at the next priority window. Replacement
    # effects (TRANSFORM-priority) and other react-phase observers (telemetry,
    # markers) leave this False.
    is_triggered_ability: bool = False
    # Cached ``effect_fn`` and human-readable description for trigger handlers.
    # Set by the helpers in src/cards/interceptor_helpers.py and consumed by
    # the pipeline when building a ``TriggeredStackItem``. The handler itself
    # remains the legacy-shape ``(event, state) -> InterceptorResult`` so non-
    # auto-resolve fallback paths still work, but when ``is_triggered_ability``
    # is True the pipeline reads ``effect_fn`` directly instead of running
    # ``handler``.
    effect_fn: Optional[Callable[['Event', 'GameState'], list['Event']]] = None
    description: str = ""


# =============================================================================
# Card Types
# =============================================================================

class CardType(Enum):
    # MTG card types
    CREATURE = auto()
    INSTANT = auto()
    SORCERY = auto()
    ENCHANTMENT = auto()
    ARTIFACT = auto()
    LAND = auto()
    PLANESWALKER = auto()

    # Hearthstone card types
    MINION = auto()      # Hearthstone creature
    SPELL = auto()       # Hearthstone instant
    WEAPON = auto()      # Hero equipment
    HERO = auto()        # Player avatar
    HERO_POWER = auto()  # Repeatable ability
    SECRET = auto()      # Opponent-turn trigger

    # Pokemon TCG card types
    POKEMON = auto()        # Pokemon card (Basic, Stage 1, Stage 2)
    TRAINER = auto()        # Trainer card (parent type)
    ITEM = auto()           # Trainer - Item
    SUPPORTER = auto()      # Trainer - Supporter
    STADIUM = auto()        # Trainer - Stadium
    POKEMON_TOOL = auto()   # Trainer - Pokemon Tool
    ENERGY = auto()         # Energy card

    # Yu-Gi-Oh! card types
    YGO_MONSTER = auto()    # Monster card
    YGO_SPELL = auto()      # Spell card
    YGO_TRAP = auto()       # Trap card

    # Minecraft TCG card types
    MC_MOB = auto()          # Creature-row unit
    MC_STRUCTURE = auto()    # Grid structure
    MC_BLOCK = auto()        # Grid defensive/utility block
    MC_TOOL = auto()         # Avatar gear
    MC_ACTION = auto()       # One-shot action card

    # Depths (submarine fleet) card types — see src/engine/depths.py.
    DEPTHS_VESSEL = auto()   # Submarine / Destroyer / Carrier / Drone / Flagship
    DEPTHS_CREW = auto()     # Equipment-style attachment (boost host Vessel)
    DEPTHS_WEAPON = auto()   # Attached ordnance with limited charges
    DEPTHS_MINE = auto()     # Battlefield permanent at a chosen depth band

    # Finance TCG card types — see src/engine/finance.py.
    FIN_TRADER = auto()      # Creature analog — has Aggression/Defense, can attack
    FIN_ORDER = auto()       # Instant analog — Market Order (immediate) or Dark Pool Order (deferred)
    FIN_STRATEGY = auto()    # Sorcery analog — sorcery-speed, higher impact
    FIN_ASSET = auto()       # Permanent with passive income or activated ability; non-combatant
    FIN_DERIVATIVE = auto()  # Enchantment-on-a-Trader; stages to Derivatives Desk before attaching
    FIN_STRUCTURE = auto()   # Building; max 3 per player on Trading Floor; tap-to-activate


    # Cats card types — see src/engine/cats.py.
    CATS_CAT = auto()         # Core unit. Numeric Value (1-10) + one Category (Sleek/Fluffy/Scrappy/Sneaky).
    CATS_MOOD = auto()        # Trick-rule replacement card. Value 0; distorts the comparison rule.
    CATS_SNACK = auto()       # Wildcard; forces the trick into the winner's Snack pile.
    CATS_TRINKET = auto()     # Persistent pile attachment. Grants a passive score/utility mod.
    CATS_COMMANDER = auto()   # Pre-game-only. Lives in COMMAND zone; permanent passive.

    # Clankers card types — see src/engine/clankers.py.
    CLANKERS_CHASSIS = auto()    # Robot base. Has power/integrity/weapon_slots/add_on_slots.
    CLANKERS_WEAPON = auto()     # Attachable offensive part; adds power_bonus to host chassis. Optional activated abilities.
    CLANKERS_ADD_ON = auto()     # Attachable utility/defensive part; adds power_bonus/integrity_bonus and/or static effects.
    CLANKERS_TRANSIENT = auto()  # One-shot AI subroutine. Resolves and goes to scrap heap.
    CLANKERS_STRUCTURE = auto()  # Workshop fixture providing passive global effects. Max 3 per player.
    CLANKERS_CORE = auto()       # The AI itself. Commander-equivalent. Lives in COMMAND zone. Carries workshop_integrity (HP).

    # SCP: SECURE / CONTAIN / SUBVERT (asymmetric Foundation-vs-Insurgency rebuild) — see src/engine/scp.py.
    SCP_ANOMALY = auto()      # Foundation "agenda": installed face-down, advanced over turns to contain for points.
    SCP_LAYER = auto()        # Foundation "ICE": a containment layer guarding a site; rezzed on encounter.
    SCP_ASSET = auto()        # Foundation installed econ/utility (persistent).
    SCP_OPERATION = auto()    # Foundation one-shot operation.
    SCP_OPERATIVE = auto()    # Insurgency breaker/body (cracks a layer type).
    SCP_TOOL = auto()         # Insurgency installed hardware/resource (persistent).
    SCP_EVENT = auto()        # Insurgency one-shot event (often a run).
    SCP_IDENTITY = auto()     # Faction identity: base stats + a passive, installed at setup.


class Color(Enum):
    WHITE = 'W'
    BLUE = 'U'
    BLACK = 'B'
    RED = 'R'
    GREEN = 'G'
    COLORLESS = 'C'


class PokemonType(Enum):
    GRASS = "G"
    FIRE = "R"
    WATER = "W"
    LIGHTNING = "L"
    PSYCHIC = "P"
    FIGHTING = "F"
    DARKNESS = "D"
    METAL = "M"
    DRAGON = "N"       # No basic energy exists
    COLORLESS = "C"    # Any energy satisfies


class ZoneType(Enum):
    LIBRARY = auto()
    HAND = auto()
    BATTLEFIELD = auto()
    GRAVEYARD = auto()
    STACK = auto()
    EXILE = auto()
    COMMAND = auto()

    # Pokemon TCG zones
    ACTIVE_SPOT = auto()    # 1 Pokemon per player
    BENCH = auto()          # Up to 5 Pokemon per player
    PRIZE_CARDS = auto()    # 6 face-down cards per player
    LOST_ZONE = auto()      # Permanent removal (public, no recovery)
    STADIUM_ZONE = auto()   # Shared, 0-1 Stadium card

    # Yu-Gi-Oh! zones
    MONSTER_ZONE = auto()       # 5 Monster Zones per player
    SPELL_TRAP_ZONE = auto()    # 5 Spell/Trap Zones per player
    FIELD_SPELL_ZONE = auto()   # 1 Field Spell Zone per player
    PENDULUM_ZONE = auto()      # 2 Pendulum Zones per player (leftmost/rightmost S/T)
    EXTRA_DECK = auto()         # Extra Deck (Fusion/Synchro/Xyz/Link/Pendulum)
    BANISHED = auto()           # Banished (removed from play)

    # Cats — see src/engine/cats.py.
    CATS_PILE_TERRITORY = auto()    # Per-player scoring pile #1. Cap 8 cards. 1pt/card +bonuses.
    CATS_PILE_NAP = auto()          # Per-player scoring pile #2. Cap 6 cards. 2pt/card, capped at 12.
    CATS_PILE_SNACK = auto()        # Per-player scoring pile #3. Cap 5 cards. 3pt/card if <5 else 1pt.
    CATS_PILE_ATTENTION = auto()    # Per-player tiebreaker pile. Unlimited. Holds overflow + "demands attention" placements.

    # Clankers — see src/engine/clankers.py.
    CLANKERS_ASSEMBLY_FLOOR = auto()   # Central battlefield analogue. Chassis, solo parts, Structures live here. Shared across players (each obj has its own controller).
    CLANKERS_SCRAP_HEAP = auto()       # Per-player graveyard analogue for destroyed parts and discarded cards.


# =============================================================================
# Game Objects
# =============================================================================

@dataclass
class Characteristics:
    """Base characteristics of a card/object."""
    types: set[CardType] = field(default_factory=set)
    subtypes: set[str] = field(default_factory=set)
    supertypes: set[str] = field(default_factory=set)
    colors: set[Color] = field(default_factory=set)
    mana_cost: Optional[str] = None
    power: Optional[int] = None
    toughness: Optional[int] = None
    abilities: list[dict] = field(default_factory=list)  # Keyword abilities and other static abilities

    @property
    def keywords(self) -> set[str]:
        """Get set of keyword abilities for easy checking."""
        return {
            a.get('keyword', '').lower()
            for a in self.abilities
            if isinstance(a, dict) and a.get('keyword')
        }


@dataclass
class ObjectState:
    """Mutable state of an object."""
    tapped: bool = False
    flipped: bool = False
    face_down: bool = False
    # Combat status flags (used by a handful of card scripts that target
    # "attacking or blocking" creatures).
    attacking: bool = False
    blocking: bool = False
    damage: int = 0
    counters: dict[str, int] = field(default_factory=dict)
    attached_to: Optional[str] = None
    attachments: list[str] = field(default_factory=list)
    is_token: bool = False           # True if this is a token (not a card)
    foil: bool = False               # Cosmetic "holo foil" — rolled at deck-load
    damage_marked: int = 0           # Damage marked this turn (before cleanup)
    crewed_until_eot: bool = False   # True if Vehicle was crewed this turn
    # Set EOT by abilities like Timid Shieldbearer's "can attack this turn as
    # though it didn't have defender"; read by CombatManager._can_attack.
    can_attack_despite_defender: bool = False
    # OTJ Saddle mechanic state
    saddled_until_eot: bool = False  # True if Mount was saddled this turn
    saddled_by_this_turn: list = field(default_factory=list)  # Creature IDs that saddled this Mount this turn
    saddled_count_this_turn: int = 0  # Times saddled this turn (for "first time" triggers)
    # OTJ Plot mechanic state
    plotted_turn: Optional[int] = None  # Turn number this card was plotted (None = not plotted)
    plot_cast_used: bool = False     # True after a plotted card has been cast (prevents re-cast)
    # Track discard timing for mechanics like Mayhem.
    last_discarded_turn: Optional[int] = None
    last_discarded_by: Optional[str] = None
    # Source of the most recent damage applied to this object. Used by the
    # SBA-driven lethal-damage check so OBJECT_DESTROYED can credit the
    # damager (otherwise the harness's kill-tracking sees no source).
    last_damage_source: Optional[str] = None

    # Phase 4: registered activated abilities (list of ActivatedAbility descriptors).
    activated_abilities: list = field(default_factory=list)

    # Phase 5: MKM Suspect mechanic — creature is suspected (menace + can't block).
    suspected: bool = False

    # Phase 5: WOE Bargain mechanic — set on the spell card object before resolve
    # if the player paid the optional bargain cost (sacrificed an artifact /
    # enchantment / token). Resolve callbacks check this for the bonus effect.
    was_bargained: bool = False

    # WOE Adventure mechanic — set when a card is exiled as part of paying an
    # Adventure activation cost ("Exile this card"). The owner may then cast
    # the original card from exile as its main (creature/enchantment) half.
    # Cleared when the card moves to the stack as the main spell so it can't
    # be cast a second time from exile.
    adventure_exile: bool = False

    # DSK Survival / generic per-source exile tracking. When a card exiles
    # other cards as part of its effect (e.g. Veteran Survivor's "exile up
    # to one target card from a graveyard"), each exiled card's id is
    # appended here on the SOURCE object. Static abilities can then read
    # ``len(source.state.exiled_with_source)`` to compute things like
    # "as long as there are three or more cards exiled with this creature".
    exiled_with_source: list = field(default_factory=list)

    # Hearthstone-specific (optional, unused in MTG)
    divine_shield: bool = False       # Prevents first damage
    frozen: bool = False              # Can't attack next turn
    stealth: bool = False             # Can't be targeted
    windfury: bool = False            # Can attack twice per turn
    attacks_this_turn: int = 0        # Track attacks for Windfury
    summoning_sickness: bool = False  # Set True on battlefield entry (pipeline.py:628)
    weapon_durability: int = 0        # For weapon cards
    weapon_attack: int = 0            # For weapon cards

    # Yu-Gi-Oh!-specific (optional, unused in MTG/HS/PKM)
    ygo_position: Optional[str] = None       # 'face_up_atk', 'face_up_def', 'face_down_def'
    overlay_units: list = field(default_factory=list)  # Xyz material object IDs
    equipped_to: Optional[str] = None        # Monster ID this equip is attached to
    turns_set: int = 0                       # Turns this card has been set face-down
    flip_summoned: bool = False              # Was Flip Summoned this turn
    position_changed: bool = False           # Position changed this turn
    attacks_declared_this_turn: int = 0      # Attacks declared this turn

    # Pokemon-specific (optional, unused in MTG/HS)
    damage_counters: int = 0             # Each = 10 HP damage
    status_conditions: set = field(default_factory=set)  # {"poisoned","burned","asleep","confused","paralyzed"}
    attached_energy: list = field(default_factory=list)   # List of energy object IDs
    attached_tool: Optional[str] = None   # Tool object ID
    evolution_stage_num: int = 0          # 0=Basic, 1=Stage1, 2=Stage2
    evolved_from_id: Optional[str] = None # Previous stage object ID
    turns_in_play: int = 0               # For evolution timing
    evolved_this_turn: bool = False       # Cannot evolve again

    # Minecraft-specific (optional, unused in other modes)
    mc_exhausted: bool = False            # Mined/attacked/used this turn
    mc_grid_x: Optional[int] = None       # 3x3 base-grid x coordinate
    mc_grid_y: Optional[int] = None       # 3x3 base-grid y coordinate
    mc_gear_slot: Optional[str] = None    # weapon / armor / tool
    mc_last_attack_column: Optional[int] = None      # Last column this mob attacked
    mc_last_attack_target: Optional[str] = None      # Last attack target id (mob/structure/avatar)
    mc_last_blocked_attacker: Optional[str] = None   # When blocking, the attacker id
    death_triggered: bool = False                    # Once-only deathrattle/on_death guard


    # Depths-specific (optional, unused in other modes). depth_band stores
    # an Enum from src/engine/depths.py (DepthBand). It's stored as a plain
    # attribute so the GameState dataclass doesn't have to import the enum;
    # the depths module sets/reads it directly. detected is True iff the
    # vessel has been pinged and is a legal interceptor target. oxygen is
    # an integer counter consumed by activated abilities (Silent Hunter
    # archetype).
    depth_band: Optional[Any] = None      # DepthBand enum (None = not a vessel)
    detected: bool = False                # Pinged this turn (or longer per duration)
    detected_until: Optional[str] = None  # 'end_of_turn' | 'until_leaves' | 'forever' | None
    oxygen: int = 0                       # Per-Vessel oxygen counter


@dataclass
class GameObject:
    """A card, token, or other game object."""
    id: str
    name: str
    owner: str                          # Player ID
    controller: str                     # Player ID
    zone: ZoneType
    characteristics: Characteristics
    state: ObjectState = field(default_factory=ObjectState)

    # Interceptors this object has registered
    interceptor_ids: list[str] = field(default_factory=list)

    # Card definition reference (for tokens, this is None)
    card_def: Optional['CardDefinition'] = None

    # Timestamps
    entered_zone_at: int = 0
    created_at: int = 0
    _state_ref: Optional['GameState'] = field(default=None, repr=False, compare=False)

    # ---------------------------------------------------------------------
    # Compatibility accessors
    # ---------------------------------------------------------------------
    # Some older card/test code assigns `obj.attached_to` directly. The actual
    # attachment state lives on `obj.state.attached_to`.
    @property
    def attached_to(self) -> Optional[str]:
        return self.state.attached_to

    @attached_to.setter
    def attached_to(self, value: Optional[str]) -> None:
        self.state.attached_to = value

    # Some older card code uses `obj.is_token` directly.
    @property
    def is_token(self) -> bool:
        return bool(self.state.is_token)

    @is_token.setter
    def is_token(self, value: bool) -> None:
        self.state.is_token = bool(value)

    # Legacy tests sometimes read/write `obj.life` directly on heroes/minions.
    @property
    def life(self) -> int:
        if CardType.HERO in self.characteristics.types and self._state_ref:
            player = self._state_ref.players.get(self.owner)
            if player:
                return int(player.life)
        base_toughness = self.characteristics.toughness
        if base_toughness is None:
            return 0
        return int(base_toughness - self.state.damage)

    @life.setter
    def life(self, value: int) -> None:
        value = int(value)
        if CardType.HERO in self.characteristics.types and self._state_ref:
            player = self._state_ref.players.get(self.owner)
            if player:
                player.life = value
                max_life = getattr(player, 'max_life', None)
                if max_life is not None:
                    self.state.damage = max(0, int(max_life) - value)
                return

        if self.characteristics.toughness is None:
            self.characteristics.toughness = max(0, value)
            self.state.damage = 0
            return
        self.state.damage = max(0, self.characteristics.toughness - value)

    # Legacy compatibility alias.
    @property
    def damage_taken(self) -> int:
        return int(self.state.damage)

    @damage_taken.setter
    def damage_taken(self, value: int) -> None:
        self.state.damage = max(0, int(value))


# =============================================================================
# Zone
# =============================================================================

@dataclass
class Zone:
    type: ZoneType
    owner: Optional[str]  # Player ID, or None for shared zones
    objects: list[str] = field(default_factory=list)  # Object IDs, ordered

    @property
    def is_ordered(self) -> bool:
        return self.type in {ZoneType.LIBRARY, ZoneType.GRAVEYARD, ZoneType.STACK}

    @property
    def is_hidden(self) -> bool:
        return self.type in {ZoneType.LIBRARY, ZoneType.HAND}


# =============================================================================
# Player
# =============================================================================

@dataclass
class Player:
    id: str
    name: str
    life: int = 20
    mana_pool: dict[Color, int] = field(default_factory=dict)
    has_lost: bool = False
    has_won: bool = False

    # Hearthstone-specific (optional, unused in MTG)
    mana_crystals: int = 0                    # Max mana crystals (0-10)
    mana_crystals_available: int = 0          # Available to spend this turn
    armor: int = 0                            # Damage reduction
    hero_id: Optional[str] = None             # Hero object ID
    hero_power_id: Optional[str] = None       # Hero power object ID
    hero_power_used: bool = False             # Used this turn
    fatigue_damage: int = 0                   # Next fatigue damage amount
    weapon_attack: int = 0                    # Current weapon attack
    weapon_durability: int = 0                # Current weapon durability
    max_life: int = 30                        # Max hero HP (healing cap)
    overloaded_mana: int = 0                  # Mana locked next turn (Shaman Overload)
    cards_played_this_turn: int = 0           # Cards played this turn (Rogue Combo)
    cost_modifiers: list = field(default_factory=list)  # [{card_type, amount, duration, uses_remaining, floor}]

    # Yu-Gi-Oh!-specific (optional, unused in MTG/HS/PKM)
    lp: int = 8000                            # Life Points
    normal_summon_used: bool = False           # Normal Summon used this turn

    # Pokemon-specific (optional, unused in MTG/HS)
    prizes_remaining: int = 0                 # Prizes left to take
    energy_attached_this_turn: bool = False   # Once per turn limit
    supporter_played_this_turn: bool = False  # Once per turn limit
    stadium_played_this_turn: bool = False    # Once per turn limit
    retreated_this_turn: bool = False         # Once per turn limit
    prize_tax: int = 0                        # Reduce next prize-take by this much (clamped >=0)

    # Minecraft-specific (optional, unused in other modes)
    mc_materials: dict[str, int] = field(default_factory=dict)
    mc_avatar_gear: dict[str, Optional[str]] = field(
        default_factory=lambda: {"weapon": None, "armor": None, "tool": None}
    )
    mc_avatar_action_used: bool = False
    mc_avatar_exhausted: bool = False
    mc_oil_counters: int = 0   # Phyrexia infect tracker; 5 counters = loss

    # Depths-specific (optional, unused in other modes). Two parallel
    # charge pools — Torpedo (offense) and Sonar (sensors). Both grow by
    # +1 per turn up to the per-turn cap of min(turn_number, 10).
    # Persist across turns up to that cap.
    tc: int = 0                            # Torpedo Charges
    sc: int = 0                            # Sonar Charges
    flagship_id: Optional[str] = None      # The Flagship Vessel object id

    @property
    def cost_reductions(self) -> list:
        """Legacy alias for older tests/card code."""
        return self.cost_modifiers

    @cost_reductions.setter
    def cost_reductions(self, value: list) -> None:
        self.cost_modifiers = list(value or [])


# =============================================================================
# Card Face (for split/adventure cards)
# =============================================================================

@dataclass
class CardFace:
    """
    Represents one face of a multi-face card (adventure, split, MDFC).

    For adventure cards: the adventure spell portion
    For split cards: left or right half
    For MDFCs: front or back face
    """
    name: str
    mana_cost: str
    types: set['CardType'] = field(default_factory=set)
    text: str = ""
    power: Optional[int] = None
    toughness: Optional[int] = None
    resolve: Optional[Callable[['Event', 'GameState'], list['Event']]] = None

    # Phase 5b: cast-time target picker for this face. Mirrors
    # ``CardDefinition.target_requirements``. When the engine routes a cast
    # through this face (e.g. Adventure half from exile), the cast handler
    # reads target_requirements from the face instead of the parent
    # CardDefinition. Type: ``list[TargetRequirement]`` from
    # ``src/engine/targeting.py`` — imported lazily inside the cast handler
    # to avoid a circular import.
    target_requirements: Optional[list] = None


# =============================================================================
# Card Definition (template for creating objects)
# =============================================================================

@dataclass
class CardDefinition:
    """Template for a card - used to create GameObjects."""
    name: str
    mana_cost: Optional[str]
    characteristics: Characteristics
    # Card space identifier. For printed Magic cards this should be "MTG".
    # For custom cards, use a set code like "TMH", "TLAC", etc.
    domain: str = "MTG"
    text: str = ""
    rarity: Optional[str] = None  # 'common', 'uncommon', 'rare', 'mythic'

    # Spells whose own text reads "this spell can't be countered" set this to
    # False. The cast path (SpellBuilder.cast_spell) copies it onto the
    # StackItem.can_be_countered flag that StackManager.counter() honors.
    # Default True preserves behavior for every existing card.
    can_be_countered: bool = True

    # Keyword-ability metadata (list of dicts like {'keyword': 'taunt'}). Retained
    # for the Hearthstone keyword catalog and legacy text-based assertions in
    # tests/test_jujutsu_kaisen.py. Not a declarative DSL — behaviour comes
    # exclusively from setup_interceptors / ability_bundles.
    abilities: list = field(default_factory=list)

    # Function to set up interceptors when this card enters play
    setup_interceptors: Optional[Callable[['GameObject', 'GameState'], list[Interceptor]]] = None

    # Phase: optional setup that runs on entry to the GRAVEYARD zone, used
    # for cards whose abilities activate from the graveyard (e.g. Goldmeadow
    # Nomad's "{W}, Exile this card from your graveyard: Create a token...").
    # Same signature as setup_interceptors.
    setup_in_graveyard: Optional[Callable[['GameObject', 'GameState'], list[Interceptor]]] = None

    # Optional setup that runs on entry to (and creation in) the HAND zone,
    # for hand-activated abilities like Cycling ("{cost}, Discard this card:
    # Draw a card.") and Evoke. Same signature as setup_interceptors.
    setup_in_hand: Optional[Callable[['GameObject', 'GameState'], list[Interceptor]]] = None

    # Function for spell/ability resolution
    resolve: Optional[Callable[['Event', 'GameState'], list[Event]]] = None

    # Phase 5b: cast-time target picker via PendingChoice.
    # When this is set, ``priority._handle_cast_spell_sync`` will emit one
    # PendingChoice per requirement BEFORE paying mana if ``action.targets``
    # is empty. Drag-to-target casts that pre-supply ``action.targets`` skip
    # this path entirely (no behavioural change). AI casts that pre-supply
    # via ``_select_targets_for_spell`` also skip it. This is purely the
    # engine-driven prompt fallback that other engines have via
    # ``create_choice_and_resolve``.
    #
    # Type: ``list[Union[TargetRequirement, TargetRequirementBuilder]]`` from
    # ``src/engine/targeting.py`` — imported lazily inside the cast handler
    # to avoid a circular import.
    #
    # Phase 5b cross-target: a list entry may be a ``TargetRequirementBuilder``
    # — ``Callable[[GameState, controller_id, list[list[str]]], TargetRequirement]``
    # — that builds the requirement from prior picks. Use this when a
    # later requirement's filter depends on what was already chosen:
    # "another target creature" (exclude prior picks), "different controllers"
    # (exclude prior pick's controller), "same mana value" (pin MV from
    # prior pick). See ``targeting.resolve_target_requirement_spec``.
    target_requirements: Optional[list] = None

    # Hearthstone-specific fields
    battlecry: Optional[Callable[['GameObject', 'GameState'], list[Event]]] = None
    deathrattle: Optional[Callable[['GameObject', 'GameState'], list[Event]]] = None
    spell_effect: Optional[Callable[['GameObject', 'GameState', list[list[str]]], list[Event]]] = None
    requires_target: bool = False

    # Pokemon-specific fields
    evolution_stage: Optional[str] = None    # "Basic", "Stage 1", "Stage 2"
    evolves_from: Optional[str] = None       # Name of pre-evolution
    hp: Optional[int] = None                 # Pokemon HP
    pokemon_type: Optional[str] = None       # PokemonType value
    weakness_type: Optional[str] = None      # Type weak to
    weakness_modifier: str = "x2"            # "x2" for modern
    resistance_type: Optional[str] = None    # Type resistant to
    resistance_modifier: int = -30           # -30 for modern
    retreat_cost: int = 0                    # Energy to discard to retreat
    attacks: list = field(default_factory=list)  # [{name, cost, damage, text, effect_fn}]
    ability: Optional[dict] = None           # {name, text, ability_type, effect_fn}
    prize_count: int = 1                     # Prizes given on KO (2 for ex)
    is_ex: bool = False                      # Pokemon ex flag
    rule_box: Optional[str] = None           # Rule box text for ex etc.

    # Yu-Gi-Oh!-specific fields
    level: Optional[int] = None              # Monster level (1-12)
    rank: Optional[int] = None               # Xyz rank
    link_rating: Optional[int] = None        # Link rating
    link_arrows: list = field(default_factory=list)  # Link arrow directions
    atk: Optional[int] = None                # ATK stat
    def_val: Optional[int] = None            # DEF stat (def is reserved keyword)
    attribute: Optional[str] = None          # YGOAttribute value
    ygo_monster_type: Optional[str] = None   # YGOMonsterType value
    ygo_spell_type: Optional[str] = None     # YGOSpellType value
    ygo_trap_type: Optional[str] = None      # YGOTrapType value
    spell_speed: Optional[int] = None        # SpellSpeed value (1, 2, or 3)
    pendulum_scale: Optional[int] = None     # Pendulum Scale value
    pendulum_effect_fn: Optional[Callable] = None  # Pendulum Zone effect
    materials: Optional[str] = None          # Fusion/Synchro/Xyz materials text
    is_tuner: bool = False                   # Synchro tuner flag
    flip_effect: Optional[Callable] = None   # FLIP: effect function

    # Card art URL (e.g. pokemontcg.io images)
    image_url: Optional[str] = None

    # Multi-face card support
    adventure: Optional[CardFace] = None      # Adventure spell portion
    split_left: Optional[CardFace] = None     # Left half of split card
    split_right: Optional[CardFace] = None    # Right half of split card
    back_face: Optional[CardFace] = None      # Back face of MDFC

    # Event-trace fire markers — substrings used by event-trace tools to
    # detect "this card fired". Defaults to a frozenset containing the card
    # name (and, for Pokemon, the names of all attacks). Card factories
    # auto-populate this at construction time, so the trace stays in sync
    # with the card pool as new cards ship. Override at the call site only
    # when an effect_fn emits events sourced by a string that isn't already
    # captured by name / attack-name (rare — see callers of make_pokemon
    # for examples). Must be a frozenset (mutable defaults aren't allowed
    # in dataclasses).
    fire_markers: frozenset = field(default_factory=frozenset)


# =============================================================================
# Game State (forward declaration - full impl in game_state.py)
# =============================================================================

# =============================================================================
# Player Choice System
# =============================================================================

@dataclass
class DivideAllocation:
    """
    Damage / counter / life allocation metadata for spells that distribute
    a quantity among multiple targets (Disintegrate X, Bituminous Blast,
    divide-damage spells). Surfaced on TargetGroupMetadata so the
    frontend can render its divide UI directly from the engine's spec.

    Engine-agnostic — any TCG with "deal X divided among targets" uses
    the same shape.
    """
    total: int  # Total points to distribute across targets in this group
    min_per_target: int = 0  # Minimum each chosen target must receive
    allow_zero: bool = True  # True = some targets in the group may receive 0


@dataclass
class TargetGroupMetadata:
    """
    Structured metadata about ONE target group in a PendingChoice. The
    engine populates this when it emits a target-type pending choice so
    the frontend can render proper UI ("Pick 3 of 6 — six different
    creatures") without parsing card text.

    Engine-agnostic: every game with targeting eventually needs
    min/max/predicate/unique/divide/group-progress. Any future user-gen
    game inherits the targeting UX by populating this struct.
    """
    label: str  # "Exile target", "Pick attacker", etc. — group-level label.
    predicate_description: str  # "creature with power 3 or less", "opponent's monster".
    min: int  # Minimum picks required (may equal max for "exactly N").
    max: int  # Maximum picks allowed (1 for single-target; 6 for Hex; large for "up to N").
    unique: bool = False  # "Different" / "distinct" constraint within the group.
    divide: Optional[DivideAllocation] = None  # Distribute-quantity spells.
    group_index: int = 0  # Zero-based; for multi-group spells.
    total_groups: int = 1  # Frontend renders "Step 2 of 3" when > 1.


@dataclass
class PendingChoice:
    """
    Tracks when the game needs player input.

    Used for modal spells, targeted ETB abilities, scry/surveil decisions, etc.
    When pending_choice is set on GameState, the game pauses and waits for
    the player to submit their choice through the API.
    """
    choice_type: str  # "modal", "target", "scry", "surveil", "order", "discard", etc.
    player: str  # player_id who must make the choice
    prompt: str  # Human-readable prompt ("Choose a mode", "Choose a target", etc.)
    options: list[Any]  # Available choices (card IDs, mode indices, etc.)
    source_id: str  # Card/ability ID that needs the choice
    min_choices: int = 1  # Minimum number of choices required
    max_choices: int = 1  # Maximum number of choices allowed
    callback_data: dict = field(default_factory=dict)  # Data needed to continue after choice
    id: str = field(default_factory=new_id)  # Unique identifier for this choice
    # Arc B — engine-supplied structured target hint for the client.
    # Populated when choice_type == "target"; None otherwise. Frontend
    # falls back to min_choices/max_choices/prompt when absent.
    target_metadata: Optional[TargetGroupMetadata] = None

    def validate_selection(self, selected: list[Any]) -> tuple[bool, str]:
        """
        Validate that a selection is legal for this choice.

        Returns (is_valid, error_message).
        """
        # Special handling for divide_allocation - selections are {target_id, amount} dicts
        if self.choice_type == "divide_allocation":
            ok, msg = self._validate_divide_allocation(selected)
            if not ok:
                return ok, msg
            validator = self.callback_data.get("validator")
            if callable(validator):
                return validator(self, selected)
            return True, ""

        if len(selected) < self.min_choices:
            return False, f"Must choose at least {self.min_choices} option(s)"
        if len(selected) > self.max_choices:
            return False, f"Cannot choose more than {self.max_choices} option(s)"

        # Check all selected options are valid
        # Handle both raw values and option dicts
        valid_ids = set()
        for opt in self.options:
            if isinstance(opt, dict):
                valid_ids.add(opt.get('id'))
                valid_ids.add(opt.get('index'))
            else:
                valid_ids.add(opt)

        for choice in selected:
            choice_id = choice.get('id') if isinstance(choice, dict) else choice
            if choice_id not in valid_ids and choice not in self.options:
                return False, f"Invalid choice: {choice}"

        validator = self.callback_data.get("validator")
        if callable(validator):
            return validator(self, selected)

        return True, ""

    def _validate_divide_allocation(self, selected: list[Any]) -> tuple[bool, str]:
        """Validate a divide_allocation selection."""
        total_amount = self.callback_data.get('total_amount', 0)

        # Build valid target IDs from options
        valid_ids = set()
        for opt in self.options:
            if isinstance(opt, dict):
                valid_ids.add(opt.get('id'))
            else:
                valid_ids.add(opt)

        # Handle dict-based allocations
        allocations = {}
        for item in selected:
            if isinstance(item, dict):
                target_id = item.get('target_id') or item.get('id')
                amount = item.get('amount', 0)
                if target_id:
                    allocations[target_id] = amount
            elif isinstance(item, tuple) and len(item) == 2:
                allocations[item[0]] = item[1]

        # Validate each target is valid
        for target_id in allocations:
            if target_id not in valid_ids:
                return False, f"Invalid target: {target_id}"

        # Validate amounts
        for target_id, amount in allocations.items():
            if amount < 1:
                return False, f"Each target must receive at least 1"

        # Validate total
        total = sum(allocations.values())
        if total != total_amount:
            return False, f"Must allocate exactly {total_amount}, got {total}"

        return True, ""


@dataclass
class GameOptions:
    """Per-game runtime configuration knobs.

    Lives on ``GameState.options`` to keep tunables out of the GameState dict.
    Most values default to the most permissive / test-friendly setting; the
    server flips them at game start when a different default is appropriate
    for production play.
    """
    # CR 603.2: Triggered abilities go on the stack and players receive
    # priority before they resolve. When True (test-friendly default),
    # trigger queueing is bypassed and the trigger's effect resolves
    # immediately when drained — preserves pre-existing test semantics where
    # ETB triggers fire inline. Set False on the live server to enable real
    # response windows.
    auto_resolve_triggers: bool = True


@dataclass
class GameState:
    """Complete game state."""
    players: dict[str, Player] = field(default_factory=dict)
    objects: dict[str, GameObject] = field(default_factory=dict)
    zones: dict[str, Zone] = field(default_factory=dict)
    interceptors: dict[str, Interceptor] = field(default_factory=dict)
    options: 'GameOptions' = field(default_factory=lambda: GameOptions())
    # CR 603.2 trigger queue. Triggers accumulate here when they fire but
    # haven't been put on the stack yet (i.e. between the triggering event
    # and the next priority window). Drained by ``process_pending_triggers``
    # in src/engine/stack.py — ordered by APNAP and pushed onto the stack
    # as TriggeredStackItem entries.
    pending_triggers: list = field(default_factory=list)

    # Turn tracking
    active_player: Optional[str] = None
    priority_player: Optional[str] = None
    turn_number: int = 0
    timestamp: int = 0  # Global timestamp counter
    # Timestamp captured at the start of the current turn (turn.py run_turn).
    # A creature is summoning sick iff entered_zone_at >= turn_start_timestamp
    # (it entered at/after this turn began). 0 = no turn has run yet (combat
    # falls back to the legacy entered==timestamp probe so direct-combat test
    # harnesses that never invoke the turn loop keep working).
    turn_start_timestamp: int = 0

    # Land play tracking (for "one land per turn" rule)
    lands_played_this_turn: int = 0
    lands_allowed_this_turn: int = 1  # Can be increased by effects like Exploration

    # Game mode configuration
    game_mode: str = "mtg"           # "mtg", "hearthstone", "pokemon", "yugioh", or "minecraft"
    starting_life: int = 20          # Default life total for newly added MTG-style players
    opening_hand_size: int = 7       # Default MTG opening hand size
    draw_step_cards: int = 1         # Cards drawn by the active player during a normal draw step
    max_mulligans: int = 7           # Safety cap for MTG-style mulligan loops
    base_lands_allowed_per_turn: int = 1
    max_hand_size: int = 7           # 7 for MTG, 10 for Hearthstone (no limit for Pokemon)
    first_player_draws: bool = False # MTG default skips the first player's first draw
    empty_library_draw_loses: bool = True
    clear_damage_on_cleanup: bool = True

    # Pending events (the "stack")
    pending_events: list[Event] = field(default_factory=list)

    # Event history
    event_log: list[Event] = field(default_factory=list)

    # Per-turn scratchpad for interceptors that need to remember "did X happen this turn"
    # (e.g. "did this player gain life this turn", "did this player attack this turn")
    # Cleared by turn manager at turn boundaries.
    turn_data: dict[str, object] = field(default_factory=dict)

    # Optional RNG seed for deterministic coin flips and other randomized
    # primitives (used by tests). When set, ``flip_coin`` constructs a
    # ``random.Random(state.rng_seed)`` lazily and stores it on
    # ``state._rng`` so subsequent flips draw from the same stream.
    rng_seed: Optional[int] = None

    # Minecraft TCG mode state.
    minecraft_day_phase: str = "day"
    minecraft_round_turns: int = 0
    minecraft_biomes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    minecraft_grid: dict[str, list[list[Optional[str]]]] = field(default_factory=dict)
    minecraft_combat: dict[str, Any] = field(default_factory=dict)


    # SCP (Foundation vs Insurgency rebuild): one record per player holding
    # faction, resources (credits/AP), win counters (containment/liberation),
    # the shared Total Breach (kept on the Foundation's record), and board
    # structures (remote cells + central-access layer stacks). See scp.py.
    scp_state: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Depths (submarine fleet) mode state. depths_combat tracks the
    # active engagement (analogous to minecraft_combat) — populated by
    # DepthsCombatManager. Keys/format are owned by the combat module;
    # depths.py only reads/initialises it.
    depths_combat: dict[str, Any] = field(default_factory=dict)

    # Player choice system - when set, game is paused waiting for input.
    # `pending_choice` is the SCALAR top-of-stack: at most one choice is
    # "active" at any time, and the player resolves it before the next
    # one surfaces. Arc C adds an optional `pending_choice_stack` for
    # nested cases — when a card's effect needs to ask Question A, then
    # mid-resolution needs to ask Question B, B is pushed onto the stack
    # and the engine resolves B first; when B clears, A becomes the new
    # top. Existing callers that just write to `pending_choice` are
    # unaffected (single-level use case). Cards that need nesting call
    # `push_pending_choice` / `pop_pending_choice`.
    pending_choice: Optional['PendingChoice'] = None
    pending_choice_stack: list['PendingChoice'] = field(default_factory=list)

    # Arc D3 — subgame slot (Shahrazad-style nested matches).
    #
    # When non-None, the frontend renders the nested GameState as a
    # contained game-view inside the parent's board. The subgame runs
    # to completion using a full Game instance; its result is read
    # by the parent's resolution logic. Engine-side subgame execution
    # is its own feature work (not implemented in this commit) — the
    # field is here so the contract is stable: PendingChoice can
    # reference a subgame_id; the GameState carries the nested state.
    #
    # Storing as Any to avoid the circular dataclass forward-ref since
    # GameState contains GameState. Serializer wraps it as GameStateData.
    subgame: Optional[Any] = None

    # W15: emblems (CR 113.1c) live forever in the command zone with their
    # interceptors registered on ``self.interceptors``. The Emblem dataclass
    # is defined in src/engine/emblem.py. Stored as ``Any`` here to avoid a
    # forward import cycle through types.py.
    emblems: list = field(default_factory=list)

    # ---------------------------------------------------------------------
    # Temporary permissions / replacement effects (turn-based)
    # ---------------------------------------------------------------------
    # Values are inclusive turn numbers (<= means active). None means "forever".
    cast_from_graveyard_until: dict[str, Optional[int]] = field(default_factory=dict)
    play_lands_from_graveyard_until: dict[str, Optional[int]] = field(default_factory=dict)
    exile_instead_of_graveyard_until: dict[str, Optional[int]] = field(default_factory=dict)

    # ---------------------------------------------------------------------
    # Ability mirror registry (Marvin, Murderous Mimic etc.)
    # ---------------------------------------------------------------------
    # Keyed by source object id (the "mimic" object). Each entry pairs that
    # object with a predicate that computes the live list of source creatures
    # whose activated abilities should be mirrored onto the source object.
    # Cleared on departure via the standard interceptor cleanup path: the
    # registration helper attaches a sentinel interceptor whose lifecycle
    # mirrors "while_on_battlefield", and the helper that returns its
    # interceptor also has the mirror prune itself when the source leaves.
    ability_mirrors: dict[str, Any] = field(default_factory=dict)

    def next_timestamp(self) -> int:
        self.timestamp += 1
        return self.timestamp

    def has_pending_choice(self) -> bool:
        """Check if the game is waiting for a player choice."""
        return self.pending_choice is not None

    def get_pending_choice_for_player(self, player_id: str) -> Optional['PendingChoice']:
        """Get the pending choice if it's for this player, else None."""
        if self.pending_choice and self.pending_choice.player == player_id:
            return self.pending_choice
        return None

    # ------------------------------------------------------------------
    # Arc C — nested pending_choice stack
    # ------------------------------------------------------------------
    # Most card effects only need a single PendingChoice at a time
    # (sequential chain). The stack is reserved for the case where one
    # effect's resolution interrupts another that hasn't finished yet
    # (e.g. a replacement effect inside a target's resolve handler that
    # needs its own choice). Card authors who hit this case use these
    # helpers; the engine's pipeline-level code uses plain
    # `state.pending_choice = X` and is unaffected.

    def push_pending_choice(self, choice: 'PendingChoice') -> None:
        """Push a nested choice on top of the current one.

        If there's an active `pending_choice`, it moves to the stack and
        `choice` becomes the new active. The player resolves `choice`
        first; on resolution, `pop_pending_choice` restores the prior
        choice as active.
        """
        if self.pending_choice is not None:
            self.pending_choice_stack.append(self.pending_choice)
        self.pending_choice = choice

    def pop_pending_choice(self) -> Optional['PendingChoice']:
        """Pop the current choice; restore the next from the stack.

        Returns the choice that was popped (may be None if nothing was
        active). After this call, `pending_choice` is either the next
        item from the stack (if any) or None.
        """
        popped = self.pending_choice
        if self.pending_choice_stack:
            self.pending_choice = self.pending_choice_stack.pop()
        else:
            self.pending_choice = None
        return popped

    def pending_choice_depth(self) -> int:
        """Total number of pending choices in flight (active + stacked).

        Frontend renders "Resolving 2 of 3" in the overlay pill when > 1
        so the player knows there's queued work after this choice.
        """
        return (1 if self.pending_choice is not None else 0) + len(self.pending_choice_stack)
