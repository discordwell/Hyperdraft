/**
 * HSGameBoard - Main Hearthstone-style game board layout.
 *
 * Layout (top to bottom):
 * - Opponent hero portrait + stats
 * - Opponent hand (face-down card backs)
 * - Opponent battlefield (minions)
 * - Center divider (turn indicator, mana)
 * - Player battlefield (minions)
 * - Player hand (face-up cards)
 * - Player hero portrait + hero power + end turn
 */

import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { HSHeroPortrait } from './HSHeroPortrait';
import { HSMinionCard } from './HSMinionCard';
import { HSHandCard } from './HSHandCard';
import HSCardDetailPanel from './HSCardDetailPanel';
import type { GameState, CardData } from '../../types';
import { useDropTarget } from '../../hooks/useDropTarget';
import { useDragDropStore, type DragItem } from '../../hooks/useDragDrop';
import { useCardPreviewStore } from '../../hooks/useCardPreview';
import { useCardInspector, type InspectorAction } from '../../hooks/useCardInspector';
import { LegendaryEntranceOverlay } from './shared/LegendaryEntranceOverlay';
import { BattlefieldEventLayer } from './shared/DamageFloater';
import { useBattlefieldEvents } from '../../hooks/useBattlefieldEvents';

// Parse "{N}" mana cost into a number for the inspector cost chip.
function hsManaLabel(manaCost: string | null | undefined): string | undefined {
  if (!manaCost) return undefined;
  const match = manaCost.match(/\{(\d+)\}/);
  return match ? match[1] : manaCost;
}

// Stat line for HS hand cards: minions show power/toughness, weapons show
// attack/durability, spells / hero powers show nothing.
function hsStatsLabel(card: CardData): string | undefined {
  const isMinion = card.types.includes('MINION') || card.types.includes('CREATURE');
  const isWeapon = card.types.includes('WEAPON');
  if (isMinion && card.power != null && card.toughness != null) {
    return `${card.power}/${card.toughness}`;
  }
  if (isWeapon && card.power != null && card.toughness != null) {
    return `${card.power} atk · ${card.toughness} dur`;
  }
  return undefined;
}

// Subtitle: "Minion · Beast", "Weapon", "Spell", etc.
function hsSubtitle(card: CardData): string | undefined {
  const isMinion = card.types.includes('MINION') || card.types.includes('CREATURE');
  const isWeapon = card.types.includes('WEAPON');
  let label = 'Spell';
  if (isMinion) label = 'Minion';
  else if (isWeapon) label = 'Weapon';
  const subs = (card.subtypes || []).filter(Boolean);
  return subs.length > 0 ? `${label} · ${subs.join(' ')}` : label;
}

interface HSGameBoardProps {
  gameState: GameState;
  playerId: string;
  isMyTurn: boolean;
  canPlayCard: (card: CardData) => boolean;
  canAttuneCard: (card: CardData) => boolean;
  canAttack: (card: CardData) => boolean;
  canUseHeroPower: boolean;
  getAttackableTargets: (attackerId: string) => string[];
  onPlayCard: (cardId: string) => void;
  onAttuneCard: (cardId: string) => void;
  onAttack: (attackerId: string, targetId: string) => void;
  onHeroPower: () => void;
  onEndTurn: () => void;
}

type InteractionMode = 'none' | 'select_attacker' | 'select_target';

/** Wrapper that makes an opponent minion a drop target for attacks */
function OpponentMinionDropWrapper({
  card,
  onDrop,
  isClickTarget,
  storeDragging,
  storeValidZones,
  variant,
  onClick,
}: {
  card: CardData;
  onDrop: (targetId: string, item: DragItem) => void;
  isClickTarget: boolean;
  storeDragging: boolean;
  storeValidZones: string[];
  variant?: string | null;
  onClick: () => void;
}) {
  const handleDrop = useCallback(
    (item: DragItem) => onDrop(card.id, item),
    [card.id, onDrop],
  );

  const { dropProps, isValidTarget: isDropTarget, isHovered } = useDropTarget({
    zoneId: card.id,
    onDrop: handleDrop,
  });

  // Dim cards that are not valid drop targets while dragging
  const isDimmed = storeDragging && !storeValidZones.includes(card.id);

  return (
    <div
      {...dropProps}
      className={`relative transition-opacity duration-150 ${isDimmed ? 'opacity-60' : ''} ${isHovered ? 'scale-110 z-10' : ''} ${isClickTarget ? 'cursor-crosshair' : ''}`}
    >
      <HSMinionCard
        card={card}
        canAttack={false}
        isSelected={false}
        isValidTarget={isClickTarget || isDropTarget}
        variant={variant}
        onClick={onClick}
      />
    </div>
  );
}

export function HSGameBoard({
  gameState,
  playerId,
  isMyTurn,
  canPlayCard,
  canAttuneCard,
  canAttack,
  canUseHeroPower,
  getAttackableTargets,
  onPlayCard,
  onAttuneCard,
  onAttack,
  onHeroPower,
  onEndTurn,
}: HSGameBoardProps) {
  const [mode, setMode] = useState<InteractionMode>('none');
  const [selectedAttackerId, setSelectedAttackerId] = useState<string | null>(null);
  const [validTargets, setValidTargets] = useState<string[]>([]);

  // Wire damage/heal/death floaters
  useBattlefieldEvents(gameState, 'hs');

  // Drag-drop state
  const storeDragging = useDragDropStore((s) => s.isDragging);
  const storeValidZones = useDragDropStore((s) => s.validDropZones);

  // Shared card-inspector modal — opening a hand card surfaces the
  // Play / Attune actions through this primitive instead of firing the
  // play action on the first click.
  const inspector = useCardInspector();

  // Clear card preview state on unmount
  const clearPreview = useCardPreviewStore((s) => s.clearAll);
  useEffect(() => {
    return () => clearPreview();
  }, [clearPreview]);

  // Cancel click-based attack mode when a drag starts
  useEffect(() => {
    if (storeDragging && mode === 'select_target') {
      setMode('none');
      setSelectedAttackerId(null);
      setValidTargets([]);
    }
  }, [storeDragging, mode]);

  const opponentId = useMemo(() =>
    Object.keys(gameState.players).find(id => id !== playerId) || null,
    [gameState.players, playerId]
  );

  const myPlayer = gameState.players[playerId];
  const opponentPlayer = opponentId ? gameState.players[opponentId] : null;
  const isFrierenrift = gameState.variant === 'frierenrift';
  const variantResources = myPlayer?.variant_resources || {};

  const myMinions = useMemo(() =>
    gameState.battlefield.filter(c => c.controller === playerId),
    [gameState.battlefield, playerId]
  );

  const opponentMinions = useMemo(() =>
    gameState.battlefield.filter(c => c.controller !== playerId),
    [gameState.battlefield, playerId]
  );

  // Handle clicking own minion
  const handleMyMinionClick = useCallback((card: CardData) => {
    if (!isMyTurn) return;

    if (mode === 'select_attacker' || mode === 'none') {
      // Select this minion as attacker
      if (canAttack(card)) {
        const targets = getAttackableTargets(card.id);
        if (targets.length > 0) {
          setMode('select_target');
          setSelectedAttackerId(card.id);
          setValidTargets(targets);
        }
      }
    }
  }, [isMyTurn, mode, canAttack, getAttackableTargets]);

  // Handle clicking enemy minion or hero (attack target)
  const handleTargetClick = useCallback((targetId: string) => {
    if (mode === 'select_target' && selectedAttackerId && validTargets.includes(targetId)) {
      onAttack(selectedAttackerId, targetId);
      setMode('none');
      setSelectedAttackerId(null);
      setValidTargets([]);
    }
  }, [mode, selectedAttackerId, validTargets, onAttack]);

  // Cancel attack selection
  const handleCancel = useCallback(() => {
    setMode('none');
    setSelectedAttackerId(null);
    setValidTargets([]);
  }, []);

  // Escape key cancels attack selection — ref keeps the effect stable
  const handleCancelRef = useRef(handleCancel);
  handleCancelRef.current = handleCancel;
  useEffect(() => {
    if (mode !== 'select_target') return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        handleCancelRef.current();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [mode]);

  // Handle card play from hand — fires the play action directly. The
  // inspector wraps this; drag-and-drop also funnels through here via
  // the battlefield drop handler.
  const handleHandCardClick = useCallback((card: CardData) => {
    if (!isMyTurn || !canPlayCard(card)) return;
    // Cancel any attack selection
    handleCancel();
    onPlayCard(card.id);
  }, [isMyTurn, canPlayCard, handleCancel, onPlayCard]);

  const handleAttuneClick = useCallback((card: CardData) => {
    if (!isMyTurn || !canAttuneCard(card)) return;
    handleCancel();
    onAttuneCard(card.id);
  }, [isMyTurn, canAttuneCard, handleCancel, onAttuneCard]);

  // Inspector-aware click: opens the shared modal with a Play action
  // (and an Attune action in Frierenrift variant). Drag-and-drop still
  // works as the primary play affordance — this is an additive click
  // path that surfaces the rules text before committing.
  const handleHandCardInspect = useCallback(
    (card: CardData) => {
      const playable = isMyTurn && canPlayCard(card);
      const attunable = isFrierenrift && isMyTurn && canAttuneCard(card);
      const playReason = !isMyTurn
        ? 'Not your turn'
        : !playable
          ? 'Insufficient mana or no valid target'
          : undefined;
      // Drop variant-specific affinity tag from displayed text — the
      // inspector already shows the cost chip separately.
      const displayText = (card.text || '').replace(/\[AF:\d+\/\d+\/\d+\]\s*/i, '');
      const actions: InspectorAction[] = [
        {
          label: 'Play',
          variant: 'primary',
          disabled: !playable,
          disabledReason: playReason,
          onClick: () => {
            handleHandCardClick(card);
          },
        },
      ];
      if (isFrierenrift) {
        actions.push({
          label: 'Attune',
          variant: 'secondary',
          disabled: !attunable,
          disabledReason: !attunable ? 'Cannot attune this card' : undefined,
          onClick: () => {
            handleAttuneClick(card);
          },
        });
      }
      inspector.open(
        {
          id: card.id,
          name: card.name,
          text: displayText,
          cost: hsManaLabel(card.mana_cost),
          subtitle: hsSubtitle(card),
          stats: hsStatsLabel(card),
          engine: 'minion',
        },
        actions,
      );
    },
    [
      inspector,
      isMyTurn,
      canPlayCard,
      canAttuneCard,
      isFrierenrift,
      handleHandCardClick,
      handleAttuneClick,
    ],
  );

  // Drop target: player battlefield (for playing hand cards)
  const handleBattlefieldDrop = useCallback((item: DragItem) => {
    if (item.type === 'hand-card' && item.intent === 'play') {
      onPlayCard(item.card.id);
    }
  }, [onPlayCard]);

  const { dropProps: battlefieldDropProps, isValidTarget: isBattlefieldDropTarget } = useDropTarget({
    zoneId: 'hs-battlefield-self',
    onDrop: handleBattlefieldDrop,
    disabled: !isMyTurn,
  });

  // Drop handler for opponent minions (attack targets)
  const handleOpponentMinionDrop = useCallback((targetId: string, item: DragItem) => {
    if (item.type === 'field-card' && item.intent === 'attack') {
      onAttack(item.card.id, targetId);
    } else if (item.type === 'hand-card' && item.intent === 'play') {
      // Targeted spell on minion
      onPlayCard(item.card.id);
    }
  }, [onAttack, onPlayCard]);

  // Drop handler for opponent hero
  const handleOpponentHeroDrop = useCallback((item: DragItem) => {
    if (item.type === 'field-card' && item.intent === 'attack' && opponentId) {
      const oppPlayer = gameState.players[opponentId];
      if (oppPlayer?.hero_id) {
        onAttack(item.card.id, oppPlayer.hero_id);
      }
    }
  }, [opponentId, gameState.players, onAttack]);

  if (!myPlayer || !opponentPlayer) return null;

  return (
    <div className="h-full flex flex-col bg-gradient-to-b from-gray-900 via-gray-800 to-gray-900 select-none" onClick={mode === 'select_target' ? handleCancel : undefined}>
      {/* Card preview panel (hover / right-click to pin) */}
      <HSCardDetailPanel variant={gameState.variant} />

      {/* Overlays (fixed-position, do not affect layout) */}
      <LegendaryEntranceOverlay battlefieldCards={gameState.battlefield} />
      <BattlefieldEventLayer />

      {/* Opponent section */}
      <div className="px-4 py-2">
        <HSHeroPortrait
          player={opponentPlayer}
          isOpponent={true}
          isMyTurn={isMyTurn}
          canUseHeroPower={false}
          isValidTarget={mode === 'select_target' && opponentPlayer.hero_id != null && validTargets.includes(opponentPlayer.hero_id!)}
          onHeroClick={() => opponentPlayer.hero_id && handleTargetClick(opponentPlayer.hero_id)}
          heroDropZoneId={opponentPlayer.hero_id || undefined}
          onHeroDrop={handleOpponentHeroDrop}
        />
      </div>

      {/* Opponent hand (face-down) */}
      <div className="flex justify-center gap-1 px-4 py-1">
        {Array.from({ length: opponentPlayer.hand_size }).map((_, i) => (
          <div key={i} className="w-8 h-11 rounded bg-gradient-to-b from-blue-800 to-blue-900 border border-blue-600" />
        ))}
      </div>

      {/* Opponent battlefield */}
      <div className="flex-1 flex items-center justify-center gap-2 px-4 py-2 min-h-[120px]">
        {opponentMinions.length === 0 ? (
          <div className="text-gray-600 text-sm">No minions</div>
        ) : (
          opponentMinions.map(card => (
            <OpponentMinionDropWrapper
              key={card.id}
              card={card}
              onDrop={handleOpponentMinionDrop}
              isClickTarget={mode === 'select_target' && validTargets.includes(card.id)}
              storeDragging={storeDragging}
              storeValidZones={storeValidZones}
              variant={gameState.variant}
              onClick={() => handleTargetClick(card.id)}
            />
          ))
        )}
      </div>

      {/* Center divider */}
      <div className="flex items-center justify-center gap-4 px-4 py-2 border-y border-gray-700 bg-gray-800/50">
        {/* Turn indicator */}
        <div className={`text-sm font-bold ${isMyTurn ? 'text-green-400' : 'text-gray-500'}`}>
          {isMyTurn ? 'Your Turn' : "Opponent's Turn"}
        </div>

        {/* Mana display */}
        <div className="flex items-center gap-1">
          {Array.from({ length: myPlayer.mana_crystals || 0 }).map((_, i) => (
            <div
              key={i}
              className={`w-4 h-4 rounded-full border ${
                i < (myPlayer.mana_crystals_available || 0)
                  ? 'bg-blue-500 border-blue-300'
                  : 'bg-gray-700 border-gray-600'
              }`}
            />
          ))}
          <span className="text-blue-300 text-sm font-bold ml-1">
            {myPlayer.mana_crystals_available}/{myPlayer.mana_crystals}
          </span>
        </div>

        {isFrierenrift && (
          <div className="flex items-center gap-2">
            <div className="text-[11px] font-semibold text-cyan-300">
              Azure {variantResources.azure || 0}
            </div>
            <div className="text-[11px] font-semibold text-orange-300">
              Ember {variantResources.ember || 0}
            </div>
            <div className="text-[11px] font-semibold text-emerald-300">
              Verdant {variantResources.verdant || 0}
            </div>
            <div className="text-[11px] font-semibold text-yellow-300">
              Attune {variantResources.attunes_left || 0}
            </div>
          </div>
        )}

        {/* Turn number */}
        <div className="text-gray-500 text-xs">
          Turn {gameState.turn_number}
        </div>

        {/* End Turn button */}
        <button
          onClick={(e) => { e.stopPropagation(); onEndTurn(); }}
          disabled={!isMyTurn}
          className={`
            px-4 py-1.5 rounded-lg font-bold text-sm transition-all
            ${isMyTurn
              ? 'bg-yellow-600 text-white hover:bg-yellow-500 shadow-lg'
              : 'bg-gray-700 text-gray-500 cursor-not-allowed'
            }
          `}
        >
          End Turn
        </button>
      </div>

      {/* Player battlefield */}
      <div
        className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 min-h-[120px] transition-all duration-200 ${isBattlefieldDropTarget ? 'bg-green-900/20 ring-2 ring-green-500/40 ring-inset rounded-lg' : ''}`}
        {...battlefieldDropProps}
      >
        {myMinions.length === 0 ? (
          <div className="text-gray-600 text-sm">{isBattlefieldDropTarget ? 'Drop to play' : 'No minions'}</div>
        ) : (
          myMinions.map(card => {
            const cardCanAttack = isMyTurn && canAttack(card);
            const targets = cardCanAttack ? getAttackableTargets(card.id) : [];
            return (
              <HSMinionCard
                key={card.id}
                card={card}
                canAttack={cardCanAttack}
                isSelected={selectedAttackerId === card.id}
                isValidTarget={false}
                variant={gameState.variant}
                attackableTargets={targets}
                onClick={() => handleMyMinionClick(card)}
              />
            );
          })
        )}
      </div>

      {/* Player hand */}
      <div className="flex justify-center gap-2 px-4 py-2 overflow-x-auto">
        {gameState.hand.map(card => (
          <HSHandCard
            key={card.id}
            card={card}
            isPlayable={isMyTurn && canPlayCard(card)}
            variant={gameState.variant}
            showAttune={isFrierenrift}
            canAttune={isMyTurn && canAttuneCard(card)}
            onAttune={() => handleAttuneClick(card)}
            onClick={() => handleHandCardInspect(card)}
          />
        ))}
        {gameState.hand.length === 0 && (
          <div className="text-gray-600 text-sm py-4">No cards in hand</div>
        )}
      </div>

      {/* Player hero section */}
      <div className="px-4 py-2 border-t border-gray-700">
        <HSHeroPortrait
          player={myPlayer}
          isOpponent={false}
          isMyTurn={isMyTurn}
          canUseHeroPower={canUseHeroPower}
          isValidTarget={false}
          onHeroPowerClick={onHeroPower}
        />
      </div>

      {/* Attack mode indicator */}
      {mode === 'select_target' && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-red-900/90 text-red-200 px-4 py-2 rounded-lg text-sm font-bold shadow-lg z-50">
          Select a target to attack — press <kbd className="bg-red-800 px-1 rounded text-xs font-mono">Esc</kbd> or click empty space to cancel
        </div>
      )}

      {/* Game Over overlay */}
      {gameState.is_game_over && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-gray-800 border border-gray-600 rounded-xl p-8 text-center">
            <h2 className="text-3xl font-bold mb-4 text-white">
              {gameState.winner === playerId ? 'Victory!' : 'Defeat'}
            </h2>
            <p className="text-gray-400 mb-4">
              {gameState.winner === playerId
                ? 'You have defeated your opponent!'
                : 'Your hero has been destroyed.'}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
