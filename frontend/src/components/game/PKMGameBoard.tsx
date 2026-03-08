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
import { useDraggable } from '../../hooks/useDraggable';
import { useDropTarget } from '../../hooks/useDropTarget';
import { useDragDropStore, type DragItem } from '../../hooks/useDragDrop';
import type { CardData, PlayerData, PendingChoice } from '../../types';

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

  let intent: 'attach' | 'evolve' | 'play' = 'play';
  let zones: string[] = [];
  let enabled = false;

  if (!isMyTurn || actionPending) {
    // disabled
  } else if (isEnergy && canAttachEnergy(card)) {
    intent = 'attach';
    zones = fieldPokemonIds;
    enabled = true;
  } else if (isEvolution) {
    intent = 'evolve';
    zones = fieldPokemonIds;
    enabled = true;
  } else if (isBasic && canPlayCard(card)) {
    intent = 'play';
    zones = ['pkm-bench-self'];
    enabled = true;
  } else if (isTrainer && !isPokemon && canPlayCard(card)) {
    intent = 'play';
    zones = ['pkm-play-area'];
    enabled = true;
  }

  const { dragProps, isBeingDragged } = useDraggable({
    item: { type: 'hand-card', card, gameMode: 'pkm', intent, sourceZone: 'hand' },
    validDropZones: zones,
    disabled: !enabled,
  });

  return (
    <PKMCard
      card={card}
      isSelected={isSelected}
      onClick={onClick}
      onHover={onHover}
      dragProps={dragProps}
      isBeingDragged={isBeingDragged}
    />
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
}: PKMDropTargetCardProps) {
  const handleDrop = useCallback((item: DragItem) => {
    if (item.intent === 'attach') {
      onDropAttach(item.card.id, card.id);
    } else if (item.intent === 'evolve') {
      onDropEvolve(item.card.id, card.id);
    }
  }, [card.id, onDropAttach, onDropEvolve]);

  const { dropProps, isValidTarget: isDropValid, isHovered } = useDropTarget({
    zoneId: card.id,
    onDrop: handleDrop,
    disabled: isOpponent,
  });

  return (
    <PKMCard
      card={card}
      compact={compact}
      isActive={isActive}
      isSelected={isSelected}
      isValidTarget={isValidTargetProp}
      isOpponent={isOpponent}
      isBeingAttacked={isBeingAttacked}
      onClick={onClick}
      onHover={onHover}
      dropProps={dropProps}
      isDropTarget={isDropValid}
      isDropHovered={isHovered}
    />
  );
}

interface PKMGameBoardProps {
  gameState: any;
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
  const [hoveredCard, setHoveredCard] = useState<CardData | null>(null);
  const [isBeingAttacked, setIsBeingAttacked] = useState(false);
  const [actionPending, setActionPending] = useState(false);

  // Drag-and-drop: cancel click mode when a drag begins
  const isDragging = useDragDropStore((s) => s.isDragging);
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

  // Handle clicking a card in hand
  const handleHandCardClick = useCallback((card: CardData) => {
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

  // Handle retreat button
  const handleRetreatClick = useCallback(() => {
    if (myBench.length === 0) return;
    if (myBench.length === 1) {
      onRetreat(myBench[0].id);
    } else {
      setMode('select_retreat_target');
    }
  }, [myBench, onRetreat]);

  // Handle ability use
  const handleAbilityClick = useCallback((pokemonId: string) => {
    onUseAbility(pokemonId);
  }, [onUseAbility]);

  // Handle card hover
  const handleCardHover = useCallback((card: CardData | null) => {
    setHoveredCard(card);
  }, []);

  // Drop handler: bench area (basic Pokemon)
  const handleBenchDrop = useCallback((item: DragItem) => {
    if (item.intent === 'play' && item.card?.id) {
      onPlayCard(item.card.id);
    }
  }, [onPlayCard]);

  // Drop handler: play area (trainer cards)
  const handlePlayAreaDrop = useCallback((item: DragItem) => {
    if (item.intent === 'play' && item.card?.id) {
      onPlayCard(item.card.id);
    }
  }, [onPlayCard]);

  // Bench zone drop target
  const { dropProps: benchDropProps, isValidTarget: benchIsValidTarget, isHovered: benchIsHovered } = useDropTarget({
    zoneId: 'pkm-bench-self',
    onDrop: handleBenchDrop,
  });

  // Play area drop target (for trainers)
  const { dropProps: playAreaDropProps, isValidTarget: playAreaIsValidTarget, isHovered: playAreaIsHovered } = useDropTarget({
    zoneId: 'pkm-play-area',
    onDrop: handlePlayAreaDrop,
  });

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

  return (
    <div
      className="h-full flex flex-col bg-gradient-to-b from-emerald-950 via-green-900 to-emerald-950 select-none relative"
      onClick={mode !== 'none' ? handleCancel : undefined}
    >
      {/* Turn Banner */}
      <PKMTurnBanner
        isMyTurn={isMyTurn}
        visible={showTurnBanner}
        onDismiss={() => setShowTurnBanner(false)}
      />

      {/* Card Detail Panel */}
      <PKMCardDetailPanel card={hoveredCard} />

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
        className={`flex items-center justify-center gap-4 px-4 py-2 border-y border-green-800 bg-green-900/50 transition-all duration-150 ${
          playAreaIsValidTarget && !playAreaIsHovered ? 'ring-2 ring-amber-400/60' : ''
        }${playAreaIsHovered ? ' ring-2 ring-amber-300 bg-amber-900/10' : ''}`}
      >
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

      {/* Player bench */}
      <div
        {...benchDropProps}
        className={`flex items-center justify-center gap-2 px-4 py-1 min-h-[48px] transition-all duration-150 ${
          benchIsValidTarget && !benchIsHovered ? 'outline outline-2 outline-amber-400/60 outline-offset-2 rounded-lg' : ''
        }${benchIsHovered ? ' outline outline-2 outline-amber-300 outline-offset-2 rounded-lg bg-amber-900/10' : ''}`}
        onClick={(e) => e.stopPropagation()}
      >
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
