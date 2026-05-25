/**
 * PKMGameBoard - Pokemon TCG game board layout.
 *
 * Layout (top to bottom):
 * - Opponent prizes + deck count
 * - Opponent bench (up to 5)
 * - Opponent active spot (1 Pokemon)
 * - Stadium card (shared)
 * - Player active spot (1 Pokemon)
 * - Player bench (up to 5)
 * - Player prizes + deck count
 * - Player hand
 * - Action bar
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { PKMCard } from './PKMCard';
import PKMCardDetailPanel from './PKMCardDetailPanel';
import PKMTurnBanner from './PKMTurnBanner';
import { PKMPrizeCards } from './PKMPrizeCards';
import { PKMActionBar } from './PKMActionBar';
import { PKMSetupOverlay } from './PKMSetupOverlay';
import { PKMChoiceModal } from './PKMChoiceModal';
import { PKMDiscardModal } from './PKMDiscardModal';
import { typeToGlowColor } from '../../utils/pkmAnimations';
import { handCard, benchSlide, cardEnter } from '../../utils/pkmAnimations';
import { useHandCard } from '../../hooks/useHandCard';
import { useCardZone } from '../../hooks/useCardZone';
import { useCardZoneStore, type CardIntent } from '../../stores/cardZoneStore';
import ZoneHighlight from '../cards/ZoneHighlight';
import { useCardPreviewStore, useCardPreviewBindings } from '../../hooks/useCardPreview';
import { useCardInspector } from '../../hooks/useCardInspector';

// Engine-namespaced constants for the shared card-zone primitive.
// Hand-card validZones + drop-zone IDs must match exactly — engine prefix
// ('pkm-') keeps PKM zones from colliding with MTG/HS/etc. in the global store.
const PKM_ENGINE_ID = 'pokemon';
const PKM_ACCENT = '#fca5a5'; // soft red — matches the engine palette
const PKM_BENCH_ME = 'pkm-bench-me';
const PKM_PLAY_AREA_ME = 'pkm-play-area';
const PKM_POKEMON_ZONE = (id: string) => `pkm-pokemon-${id}`;
import { LegendaryEntranceOverlay } from './shared/LegendaryEntranceOverlay';
import { BattlefieldEventLayer } from './shared/DamageFloater';
import { useBattlefieldEvents } from '../../hooks/useBattlefieldEvents';
import type { CardData, GameState, PlayerData, PendingChoice } from '../../types';

// ---------------------------------------------------------------------------
// Wrapper: draggable hand card
// ---------------------------------------------------------------------------
interface PKMDraggableHandCardProps {
  card: CardData;
  isSelected: boolean;
  isMyTurn: boolean;
  actionPending: boolean;
  canPlayCard: (card: CardData) => boolean;
  canAttachEnergy: (card: CardData) => boolean;
  /** IDs of own Pokemon on the field (active + bench) */
  fieldPokemonIds: string[];
  onClick: () => void;
  onHover: (card: CardData | null) => void;
}

function PKMDraggableHandCard({
  card,
  isSelected,
  isMyTurn,
  actionPending,
  canPlayCard,
  canAttachEnergy,
  fieldPokemonIds,
  onClick,
  onHover,
}: PKMDraggableHandCardProps) {
  const types = card.types || [];
  const isEnergy = types.includes('ENERGY');
  const isPokemon = types.includes('POKEMON');
  const isEvolution = isPokemon && (card.evolution_stage === 'Stage 1' || card.evolution_stage === 'Stage 2');
  const isBasic = isPokemon && !isEvolution;
  const isTrainer = types.includes('ITEM') || types.includes('SUPPORTER') || types.includes('STADIUM') || types.includes('POKEMON_TOOL');

  let intent: CardIntent = 'play';
  let zones: string[] = [];
  let enabled = false;

  if (!isMyTurn || actionPending) {
    // disabled
  } else if (isEnergy && canAttachEnergy(card)) {
    intent = 'attach';
    // Energy attaches to ANY field pokemon — active or bench.
    zones = fieldPokemonIds.map(PKM_POKEMON_ZONE);
    enabled = true;
  } else if (isEvolution) {
    intent = 'evolve';
    // Evolutions can only land on a pokemon that matches the pre-evolution.
    // Engine validates server-side; we expose all field pokemon as targets
    // and let the engine reject invalid attempts (matches legacy behaviour).
    zones = fieldPokemonIds.map(PKM_POKEMON_ZONE);
    enabled = true;
  } else if (isBasic && canPlayCard(card)) {
    intent = 'play';
    zones = [PKM_BENCH_ME];
    enabled = true;
  } else if (isTrainer && !isPokemon && canPlayCard(card)) {
    intent = 'activate'; // trainer = one-shot effect, not a permanent
    zones = [PKM_PLAY_AREA_ME];
    enabled = true;
  }

  const handCard = useHandCard({
    cardId: card.id,
    cardName: card.name,
    engineId: PKM_ENGINE_ID,
    accent: PKM_ACCENT,
    validZones: zones,
    intent,
    disabled: !enabled,
  });
  const isBeingDragged = handCard.isDragging;
  const dragProps = {
    draggable: handCard.draggable,
    onDragStart: handCard.onDragStart,
    onDragEnd: handCard.onDragEnd,
  };

  // Preview bindings add right-click/long-press pinning on top of the
  // existing onHover handler (which sets the shared preview store).
  const previewProps = useCardPreviewBindings(card, { disabled: isBeingDragged });

  // Click primes the card in the shared store (so valid zones light up)
  // AND fires the parent onClick (which opens the inspector via
  // PKMGameBoard's interaction-mode machinery). Two stores, same trigger.
  const handleClick = () => {
    handCard.onClick();
    onClick();
  };

  // Primed visual: subtle lift + accent drop-shadow so the user sees which
  // card is "live" while choosing a target. Mirrors the Cats/Clankers/HS
  // pattern.
  const primedStyle = handCard.isPrimed
    ? { transform: 'translateY(-6px)', filter: `drop-shadow(0 0 8px ${PKM_ACCENT})`, transition: 'transform 120ms ease, filter 120ms ease' }
    : undefined;

  return (
    <span {...previewProps} className="inline-block" style={primedStyle}>
      <PKMCard
        card={card}
        isSelected={isSelected}
        onClick={handleClick}
        onHover={onHover}
        dragProps={dragProps}
        isBeingDragged={isBeingDragged}
      />
    </span>
  );
}

// ---------------------------------------------------------------------------
// Wrapper: drop-target field Pokemon (active + bench)
// ---------------------------------------------------------------------------
interface PKMDropTargetCardProps {
  card: CardData;
  compact?: boolean;
  isActive?: boolean;
  isSelected?: boolean;
  isValidTarget?: boolean;
  isOpponent?: boolean;
  isBeingAttacked?: boolean;
  onClick?: () => void;
  onHover?: (card: CardData | null) => void;
  onDropAttach: (energyCardId: string, pokemonId: string) => void;
  onDropEvolve: (evolutionCardId: string, pokemonId: string) => void;
  /** Retreat — bench Pokemon receives the swap. Engine reads the active
   *  Pokemon from primedCardId; this callback only needs the bench id. */
  onDropRetreat: (benchPokemonId: string) => void;
}

function PKMDropTargetCard({
  card,
  compact,
  isActive,
  isSelected,
  isValidTarget: isValidTargetProp,
  isOpponent,
  isBeingAttacked,
  onClick,
  onHover,
  onDropAttach,
  onDropEvolve,
  onDropRetreat,
}: PKMDropTargetCardProps) {
  // Migrated to the shared card-zone primitive. The active intent ('attach'
  // for energy / 'evolve' for stage-1+) is set by the hand-card at drag /
  // click-prime time; here we just route to the right engine action.
  // Opponent's Pokemon don't register as zones (no drop).
  const zone = useCardZone({
    zoneId: PKM_POKEMON_ZONE(card.id),
    engineId: PKM_ENGINE_ID,
    onPlay: (cardId) => {
      if (isOpponent) return;
      const intent = useCardZoneStore.getState().activeIntent;
      if (intent === 'attach') onDropAttach(cardId, card.id);
      else if (intent === 'evolve') onDropEvolve(cardId, card.id);
      else if (intent === 'retreat') onDropRetreat(card.id);
    },
  });
  const dropProps = isOpponent
    ? undefined
    : {
        onDragOver: zone.onDragOver,
        onDragEnter: zone.onDragOver, // shared store uses dragOver for both
        onDragLeave: zone.onDragLeave,
        onDrop: zone.onDrop,
      };

  // Preview bindings add right-click/long-press pinning. Disabled when this
  // zone is actively a valid drop target so the drag UI takes precedence.
  const previewProps = useCardPreviewBindings(card, { disabled: zone.isValid });

  // Compose the parent onClick (interaction-mode machinery: select retreat
  // target, etc.) with the zone click — clicking a lit zone plays the
  // primed card from hand.
  const handleClick = () => {
    if (!isOpponent && zone.isValid) zone.onClick();
    if (onClick) onClick();
  };

  return (
    <span {...previewProps} className="inline-block relative">
      {!isOpponent && (
        <ZoneHighlight
          isValid={zone.isValid}
          isHovered={zone.isHovered}
          hasActiveCard={zone.hasActiveCard}
          activeAccent={zone.activeAccent}
        />
      )}
      <PKMCard
        card={card}
        compact={compact}
        isActive={isActive}
        isSelected={isSelected}
        isValidTarget={isValidTargetProp}
        isOpponent={isOpponent}
        isBeingAttacked={isBeingAttacked}
        onClick={handleClick}
        onHover={onHover}
        dropProps={dropProps}
        isDropTarget={zone.isValid}
        isDropHovered={zone.isHovered}
      />
    </span>
  );
}

interface PKMGameBoardProps {
  gameState: GameState;
  playerId: string;
  isMyTurn: boolean;
  myPlayer: PlayerData | null;
  opponentPlayer: PlayerData | null;
  myActivePokemon: CardData | null;
  opponentActivePokemon: CardData | null;
  myBench: CardData[];
  opponentBench: CardData[];
  stadiumCard: CardData | null;
  hand: CardData[];
  myGraveyard: CardData[];
  opponentGraveyard: CardData[];
  canPlayCard: (card: CardData) => boolean;
  canAttachEnergy: (card: CardData) => boolean;
  onPlayCard: (cardId: string) => void;
  onAttachEnergy: (energyCardId: string, targetPokemonId: string) => void;
  onAttack: (attackIndex: number) => void;
  onRetreat: (benchPokemonId: string) => void;
  onEvolve: (evolutionCardId: string, targetPokemonId: string) => void;
  onUseAbility: (pokemonId: string) => void;
  onEndTurn: () => void;
  onSubmitChoice?: (choiceId: string, selected: string[]) => void;
  showDiscardModal?: boolean;
  onToggleDiscardModal?: (show: boolean) => void;
}

type InteractionMode =
  | 'none'
  | 'select_energy_target'    // Picking a Pokemon to attach energy to
  | 'select_attack'           // Picking which attack to use
  | 'select_retreat_target'   // Picking bench Pokemon to swap in
  | 'select_evolution_target' // Picking which Pokemon to evolve
  ;

export function PKMGameBoard({
  gameState,
  playerId,
  isMyTurn,
  myPlayer,
  opponentPlayer,
  myActivePokemon,
  opponentActivePokemon,
  myBench,
  opponentBench,
  stadiumCard,
  hand,
  myGraveyard,
  opponentGraveyard,
  canPlayCard,
  canAttachEnergy,
  onPlayCard,
  onAttachEnergy,
  onAttack,
  onRetreat,
  onEvolve,
  onUseAbility,
  onEndTurn,
  onSubmitChoice,
  showDiscardModal = false,
  onToggleDiscardModal,
}: PKMGameBoardProps) {
  const [mode, setMode] = useState<InteractionMode>('none');
  const [selectedHandCardId, setSelectedHandCardId] = useState<string | null>(null);
  const [isBeingAttacked, setIsBeingAttacked] = useState(false);
  const [actionPending, setActionPending] = useState(false);

  // Wire damage/heal/death floaters
  useBattlefieldEvents(gameState, 'pkm');

  // Shared "click to inspect, then Play" modal — additive to drag+drop / hover.
  const inspector = useCardInspector();

  // Card preview store (hover + pin)
  const setPreviewHover = useCardPreviewStore((s) => s.setHover);
  const clearPreview = useCardPreviewStore((s) => s.clearAll);
  useEffect(() => {
    return () => clearPreview();
  }, [clearPreview]);

  // Drag-and-drop: cancel click mode when a drag begins. The shared
  // cardZoneStore tracks the active drag — same signal as the legacy
  // dragDropStore, just via the new primitive.
  const isDragging = useCardZoneStore((s) => s.dragCardId !== null);
  useEffect(() => {
    if (isDragging && mode !== 'none') {
      setMode('none');
      setSelectedHandCardId(null);
    }
  }, [isDragging]); // eslint-disable-line react-hooks/exhaustive-deps

  // Compute field Pokemon IDs for drag valid zones
  const fieldPokemonIds = [
    ...(myActivePokemon ? [myActivePokemon.id] : []),
    ...myBench.map((b) => b.id),
  ];

  // Turn banner state
  const [showTurnBanner, setShowTurnBanner] = useState(false);
  const prevTurnRef = useRef(isMyTurn);

  useEffect(() => {
    if (prevTurnRef.current !== isMyTurn) {
      setShowTurnBanner(true);
      prevTurnRef.current = isMyTurn;
    }
  }, [isMyTurn]);

  // Cancel current interaction
  const handleCancel = useCallback(() => {
    setMode('none');
    setSelectedHandCardId(null);
  }, []);

  // Escape key cancels current mode
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && mode !== 'none') handleCancel();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [mode, handleCancel]);

  // Reset actionPending when game state changes (action resolved)
  useEffect(() => { setActionPending(false); }, [gameState]);

  // Underlying play resolver — fires the appropriate engine action for a hand
  // card. Used by both the legacy direct-click path (kept for tests / drag
  // fallback callers) and by the new inspector's primary action.
  const resolveHandCardPlay = useCallback((card: CardData) => {
    if (!isMyTurn || actionPending) return;

    const types = card.types || [];

    // Energy card - select for attachment
    if (types.includes('ENERGY') && canAttachEnergy(card)) {
      setMode('select_energy_target');
      setSelectedHandCardId(card.id);
      return;
    }

    // Evolution card - select target
    if (types.includes('POKEMON') && (card.evolution_stage === 'Stage 1' || card.evolution_stage === 'Stage 2')) {
      setMode('select_evolution_target');
      setSelectedHandCardId(card.id);
      return;
    }

    // Basic Pokemon or Trainer - play directly
    if (canPlayCard(card)) {
      setActionPending(true);
      onPlayCard(card.id);
      handleCancel();
    }
  }, [isMyTurn, actionPending, canPlayCard, canAttachEnergy, onPlayCard, handleCancel]);

  // Handle clicking a card in hand — opens the shared inspector modal. The
  // modal's primary action calls back into `resolveHandCardPlay`, preserving
  // the existing play/attach/evolve flow (including target-picker mode).
  const handleHandCardClick = useCallback((card: CardData) => {
    const types = card.types || [];
    const isEnergy = types.includes('ENERGY');
    const isPokemon = types.includes('POKEMON');
    const isEvolution = isPokemon && (card.evolution_stage === 'Stage 1' || card.evolution_stage === 'Stage 2');
    const isTrainer = !isPokemon && !isEnergy &&
      (types.includes('ITEM') || types.includes('SUPPORTER') || types.includes('STADIUM') || types.includes('POKEMON_TOOL'));

    // Inspector card descriptor — engine-agnostic shape consumed by <CardInspector />.
    let subtitle: string | undefined;
    let stats: string | undefined;
    let actionLabel = 'Play';
    let inspectorEngine: 'pokemon' | 'energy' | 'trainer' = 'pokemon';
    if (isEnergy) {
      subtitle = 'Energy';
      inspectorEngine = 'energy';
      actionLabel = 'Attach Energy';
    } else if (isEvolution) {
      subtitle = `${card.evolution_stage}${card.pokemon_type ? ` · ${card.pokemon_type}` : ''}`;
      stats = card.hp ? `HP ${card.hp}` : undefined;
      actionLabel = 'Evolve';
    } else if (isPokemon) {
      subtitle = `Basic${card.pokemon_type ? ` · ${card.pokemon_type}` : ''}`;
      stats = card.hp ? `HP ${card.hp}` : undefined;
    } else if (isTrainer) {
      const trainerKind =
        types.includes('SUPPORTER') ? 'Supporter' :
        types.includes('ITEM') ? 'Item' :
        types.includes('STADIUM') ? 'Stadium' :
        types.includes('POKEMON_TOOL') ? 'Pokémon Tool' :
        'Trainer';
      subtitle = trainerKind;
      inspectorEngine = 'trainer';
    }

    // Disability check mirrors `resolveHandCardPlay`'s preconditions exactly.
    let disabled = false;
    let disabledReason: string | undefined;
    if (!isMyTurn) {
      disabled = true;
      disabledReason = "Not your turn";
    } else if (actionPending) {
      disabled = true;
      disabledReason = 'Resolving previous action…';
    } else if (isEnergy && !canAttachEnergy(card)) {
      disabled = true;
      disabledReason = 'No energy attach available';
    } else if (!isEnergy && !isEvolution && !canPlayCard(card)) {
      disabled = true;
      disabledReason = 'Cannot play this card right now';
    }

    inspector.open(
      {
        id: card.id,
        name: card.name,
        text: card.text || (card.ability_text ? `Ability: ${card.ability_text}` : undefined),
        subtitle,
        stats,
        engine: inspectorEngine,
      },
      [
        {
          label: actionLabel,
          variant: 'primary',
          disabled,
          disabledReason,
          onClick: () => {
            resolveHandCardPlay(card);
            // For Energy / Evolution we set a target-picker mode; let the
            // modal close so the user can click a field Pokemon. For Basic
            // Pokemon / Trainer the engine action fires directly. In both
            // cases default-close (void) is the right behavior.
          },
        },
      ],
    );
  }, [isMyTurn, actionPending, canPlayCard, canAttachEnergy, inspector, resolveHandCardPlay]);

  // Handle clicking a Pokemon on field (for energy attachment, evolution, ability)
  const handleFieldPokemonClick = useCallback((pokemonId: string, isOwn: boolean) => {
    if (!isMyTurn || !isOwn) return;

    if (mode === 'select_energy_target' && selectedHandCardId) {
      onAttachEnergy(selectedHandCardId, pokemonId);
      handleCancel();
      return;
    }

    if (mode === 'select_evolution_target' && selectedHandCardId) {
      onEvolve(selectedHandCardId, pokemonId);
      handleCancel();
      return;
    }

    if (mode === 'select_retreat_target') {
      onRetreat(pokemonId);
      handleCancel();
      return;
    }
  }, [isMyTurn, mode, selectedHandCardId, onAttachEnergy, onEvolve, onRetreat, handleCancel]);

  // Handle attack - trigger shake animation on opponent
  const handleAttackClick = useCallback((attackIndex: number) => {
    setIsBeingAttacked(true);
    setTimeout(() => setIsBeingAttacked(false), 600);
    onAttack(attackIndex);
    handleCancel();
  }, [onAttack, handleCancel]);

  // Handle retreat button — single bench Pokemon auto-resolves; multiple
  // bench primes the active Pokemon in the shared card-zone store with
  // intent='retreat' and the bench zones lit. Bench Pokemon's useCardZone
  // routes the 'retreat' intent to onRetreat(thisBenchId) on click.
  const handleRetreatClick = useCallback(() => {
    if (!myActivePokemon) return;
    if (myBench.length === 0) return;
    if (myBench.length === 1) {
      onRetreat(myBench[0].id);
      return;
    }
    const benchZoneIds = myBench.map((b) => PKM_POKEMON_ZONE(b.id));
    useCardZoneStore
      .getState()
      .primeCard(myActivePokemon.id, PKM_ENGINE_ID, benchZoneIds, PKM_ACCENT, 'retreat');
  }, [myActivePokemon, myBench, onRetreat]);

  // Cancel a primed retreat (Esc, click-off, or any other dismissal).
  // Bound to the existing handleCancel path so the old mode-state-machine
  // cancel UX still works during the transition.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        const intent = useCardZoneStore.getState().activeIntent;
        if (intent === 'retreat') useCardZoneStore.getState().clearAll();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Handle ability use
  const handleAbilityClick = useCallback((pokemonId: string) => {
    onUseAbility(pokemonId);
  }, [onUseAbility]);

  // Handle card hover — routes to the shared preview store so the panel (and
  // any other preview consumers) stay in sync across modes.
  const handleCardHover = useCallback((card: CardData | null) => {
    setPreviewHover(card);
  }, [setPreviewHover]);

  // Bench drop zone — basic Pokemon land here. Migrated to shared
  // card-zone primitive; the hand-card's validZones include PKM_BENCH_ME
  // exactly when isBasic + canPlayCard. The activeIntent here is 'play'.
  const benchZone = useCardZone({
    zoneId: PKM_BENCH_ME,
    engineId: PKM_ENGINE_ID,
    onPlay: (cardId) => onPlayCard(cardId),
  });
  const benchIsValidTarget = benchZone.isValid;
  const benchIsHovered = benchZone.isHovered;
  const benchDropProps = {
    onClick: benchZone.onClick,
    onDragOver: benchZone.onDragOver,
    onDragLeave: benchZone.onDragLeave,
    onDrop: benchZone.onDrop,
  };

  // Play area drop zone — trainer cards (Items / Supporters / Stadium /
  // Pokemon Tools) land here. activeIntent for trainers is 'activate'.
  const playAreaZone = useCardZone({
    zoneId: PKM_PLAY_AREA_ME,
    engineId: PKM_ENGINE_ID,
    onPlay: (cardId) => onPlayCard(cardId),
  });
  const playAreaIsValidTarget = playAreaZone.isValid;
  const playAreaIsHovered = playAreaZone.isHovered;
  const playAreaDropProps = {
    onClick: playAreaZone.onClick,
    onDragOver: playAreaZone.onDragOver,
    onDragLeave: playAreaZone.onDragLeave,
    onDrop: playAreaZone.onDrop,
  };

  if (!myPlayer || !opponentPlayer) return null;

  const myPrizes = myPlayer.prizes_remaining ?? 0;
  const oppPrizes = opponentPlayer.prizes_remaining ?? 0;

  // Check for pending choices (setup phase or trainer targeting)
  const pendingChoice = gameState.pending_choice as PendingChoice | null;
  const isSetupChoice = pendingChoice && (
    pendingChoice.choice_type === 'pkm_select_active' ||
    pendingChoice.choice_type === 'pkm_select_bench'
  );
  const isTargetChoice = pendingChoice && !isSetupChoice && pendingChoice.player === playerId;

  // Active Pokemon glow style
  const activeGlowStyle = myActivePokemon?.pokemon_type ? {
    '--pkm-glow-color': typeToGlowColor(myActivePokemon.pokemon_type),
  } as React.CSSProperties : {};

  // Hand fan calculations
  const handCount = hand.length;
  const maxRotation = Math.min(handCount * 2, 15);

  // All pokemon on the field (for LegendaryEntranceOverlay detection).
  const fieldPokemon: CardData[] = [
    ...(myActivePokemon ? [myActivePokemon] : []),
    ...(opponentActivePokemon ? [opponentActivePokemon] : []),
    ...myBench,
    ...opponentBench,
  ];

  return (
    <div
      className="h-full flex flex-col bg-gradient-to-b from-emerald-950 via-green-900 to-emerald-950 select-none relative"
      onClick={mode !== 'none' ? handleCancel : undefined}
    >
      {/* Overlays (fixed-position) */}
      <LegendaryEntranceOverlay battlefieldCards={fieldPokemon} />
      <BattlefieldEventLayer />

      {/* Turn Banner */}
      <PKMTurnBanner
        isMyTurn={isMyTurn}
        visible={showTurnBanner}
        onDismiss={() => setShowTurnBanner(false)}
      />

      {/* Card Detail Panel */}
      <PKMCardDetailPanel />

      {/* Opponent info bar */}
      <div className="flex items-center justify-between px-4 py-1.5 bg-black/30">
        <div className="flex items-center gap-3">
          <span className="text-gray-300 text-sm font-bold">{opponentPlayer.name}</span>
          <span className="text-gray-500 text-xs">Deck: {opponentPlayer.library_size}</span>
          <span className="text-gray-500 text-xs">Hand: {opponentPlayer.hand_size}</span>
        </div>
        <PKMPrizeCards total={6} remaining={oppPrizes} isOpponent compact />
      </div>

      {/* Opponent hand (face-down) */}
      <div className="flex justify-center gap-1 px-4 py-1">
        {Array.from({ length: opponentPlayer.hand_size }).map((_, i) => (
          <div key={i} className="w-7 h-10 rounded bg-gradient-to-b from-red-800 to-red-900 border border-red-600" />
        ))}
      </div>

      {/* Opponent bench */}
      <div className="flex items-center justify-center gap-2 px-4 py-1 min-h-[48px]">
        <AnimatePresence mode="popLayout">
          {opponentBench.length === 0 ? (
            <div className="text-green-800 text-xs">Empty bench</div>
          ) : (
            opponentBench.map(card => (
              <motion.div key={card.id} variants={benchSlide} initial="initial" animate="animate" exit="exit">
                <PKMCard card={card} compact isOpponent onHover={handleCardHover} />
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>

      {/* Opponent active spot */}
      <div className="flex items-center justify-center py-2 min-h-[160px]">
        <AnimatePresence mode="wait">
          {opponentActivePokemon ? (
            <motion.div key={opponentActivePokemon.id} variants={cardEnter} initial="initial" animate="animate" exit="exit">
              <PKMCard
                card={opponentActivePokemon}
                isActive
                isOpponent
                isBeingAttacked={isBeingAttacked}
                onHover={handleCardHover}
              />
            </motion.div>
          ) : (
            <div className="w-32 h-44 rounded-lg border-2 border-dashed border-green-700 flex items-center justify-center">
              <span className="text-green-700 text-xs">No Active</span>
            </div>
          )}
        </AnimatePresence>
      </div>

      {/* Stadium + center divider (also trainer drop target) */}
      <div
        {...playAreaDropProps}
        className={`relative flex items-center justify-center gap-4 px-4 py-2 border-y border-green-800 bg-green-900/50 transition-all duration-150 ${
          playAreaIsValidTarget && !playAreaIsHovered ? 'ring-2 ring-amber-400/60' : ''
        }${playAreaIsHovered ? ' ring-2 ring-amber-300 bg-amber-900/10' : ''}`}
      >
        <ZoneHighlight
          isValid={playAreaZone.isValid}
          isHovered={playAreaZone.isHovered}
          hasActiveCard={playAreaZone.hasActiveCard}
          activeAccent={playAreaZone.activeAccent}
        />
        {stadiumCard ? (
          <div
            className="flex items-center gap-2 cursor-pointer"
            onMouseEnter={() => handleCardHover(stadiumCard)}
            onMouseLeave={() => handleCardHover(null)}
          >
            <span className="text-[10px] text-gray-400 uppercase">Stadium</span>
            <div className="bg-gray-700 rounded px-2 py-1 text-white text-[10px] font-bold">
              {stadiumCard.name}
            </div>
          </div>
        ) : (
          <div className="text-green-700 text-[10px]">No Stadium</div>
        )}

        <div className={`text-sm font-bold ${isMyTurn ? 'text-yellow-400' : 'text-gray-500'}`}>
          {isMyTurn ? 'Your Turn' : "Opponent's Turn"}
        </div>

        <div className="text-gray-500 text-xs">Turn {gameState.turn_number}</div>
      </div>

      {/* Player active spot */}
      <div className="flex items-center justify-center py-2 min-h-[160px]">
        <AnimatePresence mode="wait">
          {myActivePokemon ? (
            <motion.div
              key={myActivePokemon.id}
              variants={cardEnter}
              initial="initial"
              animate="animate"
              exit="exit"
              className="flex items-center gap-4"
              onClick={(e) => e.stopPropagation()}
              style={activeGlowStyle}
            >
              <div className={isMyTurn ? 'animate-pkm-glow rounded-lg' : ''}>
                <PKMDropTargetCard
                  card={myActivePokemon}
                  isActive
                  isSelected={mode === 'select_energy_target' || mode === 'select_evolution_target'}
                  isValidTarget={mode === 'select_energy_target' || mode === 'select_evolution_target'}
                  onClick={() => handleFieldPokemonClick(myActivePokemon.id, true)}
                  onHover={handleCardHover}
                  onDropAttach={onAttachEnergy}
                  onDropEvolve={onEvolve}
                  onDropRetreat={onRetreat}
                />
              </div>
            </motion.div>
          ) : (
            <div className="w-32 h-44 rounded-lg border-2 border-dashed border-green-700 flex items-center justify-center">
              <span className="text-green-700 text-xs">No Active</span>
            </div>
          )}
        </AnimatePresence>
      </div>

      {/* Player bench — shared-primitive drop zone (PKM_BENCH_ME) */}
      <div
        {...benchDropProps}
        className={`relative flex items-center justify-center gap-2 px-4 py-1 min-h-[48px] transition-all duration-150 ${
          benchIsValidTarget && !benchIsHovered ? 'outline outline-2 outline-amber-400/60 outline-offset-2 rounded-lg' : ''
        }${benchIsHovered ? ' outline outline-2 outline-amber-300 outline-offset-2 rounded-lg bg-amber-900/10' : ''}`}
        onClick={(e) => {
          e.stopPropagation();
          benchDropProps.onClick();
        }}
      >
        <ZoneHighlight
          isValid={benchZone.isValid}
          isHovered={benchZone.isHovered}
          hasActiveCard={benchZone.hasActiveCard}
          activeAccent={benchZone.activeAccent}
        />
        <AnimatePresence mode="popLayout">
          {myBench.length === 0 ? (
            <div className="text-green-800 text-xs">
              {benchIsValidTarget ? 'Drop here to play' : 'Empty bench'}
            </div>
          ) : (
            myBench.map(card => (
              <motion.div key={card.id} variants={benchSlide} initial="initial" animate="animate" exit="exit">
                <PKMDropTargetCard
                  card={card}
                  compact
                  isValidTarget={mode === 'select_energy_target' || mode === 'select_evolution_target' || mode === 'select_retreat_target'}
                  onClick={() => handleFieldPokemonClick(card.id, true)}
                  onHover={handleCardHover}
                  onDropAttach={onAttachEnergy}
                  onDropEvolve={onEvolve}
                  onDropRetreat={onRetreat}
                />
              </motion.div>
            ))
          )}
        </AnimatePresence>
        {/* Bench slots */}
        {myBench.length < 5 && Array.from({ length: 5 - myBench.length }).map((_, i) => (
          <div key={`empty-${i}`} className={`w-20 h-28 rounded border border-dashed border-green-800 ${benchIsValidTarget ? 'opacity-60 border-amber-500' : 'opacity-30'}`} />
        ))}
      </div>

      {/* Player info bar */}
      <div className={`flex items-center justify-between px-4 py-1.5 bg-black/30 ${isMyTurn ? 'border-l-2 border-yellow-500' : ''}`}>
        <div className="flex items-center gap-3">
          <span className="text-white text-sm font-bold">{myPlayer.name}</span>
          <span className="text-gray-400 text-xs">Deck: {myPlayer.library_size}</span>
        </div>
        <PKMPrizeCards total={6} remaining={myPrizes} />
      </div>

      {/* Player hand with fan layout */}
      <div className="flex justify-center px-4 py-2 overflow-x-auto" onClick={(e) => e.stopPropagation()}>
        <AnimatePresence mode="popLayout">
          {hand.map((card, i) => {
            // Fan rotation and offset
            const centerIndex = (handCount - 1) / 2;
            const offset = i - centerIndex;
            const rotation = handCount > 1 ? (offset / centerIndex) * maxRotation : 0;
            const yOffset = Math.abs(offset) * 4;

            return (
              <motion.div
                key={card.id}
                variants={handCard}
                initial="initial"
                animate="animate"
                exit="exit"
                whileHover={{ y: -16, scale: 1.08, zIndex: 20, rotate: 0 }}
                style={{
                  transform: `rotate(${rotation}deg) translateY(${yOffset}px)`,
                  marginLeft: i > 0 ? '-6px' : '0',
                  zIndex: i,
                }}
                className="transition-transform"
              >
                <PKMDraggableHandCard
                  card={card}
                  isSelected={selectedHandCardId === card.id}
                  isMyTurn={isMyTurn}
                  actionPending={actionPending}
                  canPlayCard={canPlayCard}
                  canAttachEnergy={canAttachEnergy}
                  fieldPokemonIds={fieldPokemonIds}
                  onClick={() => handleHandCardClick(card)}
                  onHover={handleCardHover}
                />
              </motion.div>
            );
          })}
        </AnimatePresence>
        {hand.length === 0 && (
          <div className="text-green-800 text-sm py-4">No cards in hand</div>
        )}
      </div>

      {/* Action bar */}
      <PKMActionBar
        isMyTurn={isMyTurn}
        activePokemon={myActivePokemon}
        benchCount={myBench.length}
        mode={mode}
        onAttack={handleAttackClick}
        onRetreat={handleRetreatClick}
        onAbility={handleAbilityClick}
        onEndTurn={onEndTurn}
        onCancel={handleCancel}
      />

      {/* Setup phase overlay */}
      {isSetupChoice && pendingChoice && onSubmitChoice && (
        <PKMSetupOverlay
          choice={pendingChoice}
          hand={hand}
          onSubmit={onSubmitChoice}
        />
      )}

      {/* Trainer targeting / choice modal */}
      {isTargetChoice && pendingChoice && onSubmitChoice && (
        <PKMChoiceModal
          choice={pendingChoice}
          cards={[
            ...(myActivePokemon ? [myActivePokemon] : []),
            ...myBench,
            ...(opponentActivePokemon ? [opponentActivePokemon] : []),
            ...opponentBench,
            ...hand,
          ]}
          onSubmit={onSubmitChoice}
          onCardHover={handleCardHover}
        />
      )}

      {/* Discard pile modal */}
      <PKMDiscardModal
        isOpen={showDiscardModal}
        onClose={() => onToggleDiscardModal?.(false)}
        myGraveyard={myGraveyard}
        opponentGraveyard={opponentGraveyard}
        myName={myPlayer.name}
        opponentName={opponentPlayer.name}
        onCardHover={handleCardHover}
      />

      {/* Game Over overlay */}
      {gameState.is_game_over && (
        <motion.div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          <motion.div
            className="bg-gray-800 border border-gray-600 rounded-xl p-8 text-center"
            initial={{ scale: 0.7, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', stiffness: 300, damping: 25 }}
          >
            <h2 className="text-3xl font-bold mb-4 text-white">
              {gameState.winner === playerId ? 'Victory!' : gameState.winner ? 'Defeat' : 'Game Over'}
            </h2>
            <p className="text-gray-400 mb-4">
              {gameState.winner === playerId
                ? 'You collected all your prize cards!'
                : gameState.winner ? 'Your opponent wins!' : 'The game has ended.'}
            </p>
          </motion.div>
        </motion.div>
      )}
    </div>
  );
}
