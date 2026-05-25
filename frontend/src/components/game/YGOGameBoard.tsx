/**
 * YGOGameBoard Component
 *
 * Yu-Gi-Oh! duel field with Dark + Gold theming, animations,
 * fan hand layout, card detail panel, turn banner, attack UX,
 * and drag-and-drop for summoning, setting, activating, and attacking.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { YGOCard } from './YGOCard';
import { YGOActionBar } from './YGOActionBar';
import YGOCardDetailPanel from './YGOCardDetailPanel';
import YGOTurnBanner from './YGOTurnBanner';
import YGOBanishedModal from './YGOBanishedModal';
import YGOExtraDeckModal from './YGOExtraDeckModal';
import { useDraggable } from '../../hooks/useDraggable';
import { useDropTarget } from '../../hooks/useDropTarget';
import { useHandCard } from '../../hooks/useHandCard';
import { useCardZone } from '../../hooks/useCardZone';
import { type CardIntent } from '../../stores/cardZoneStore';
import { useDropChoiceStore } from '../../stores/dropChoiceStore';
import ZoneHighlight from '../cards/ZoneHighlight';
import { cardSummon, handStagger, modalBackdrop, modalContent, gameOverOverlay } from '../../utils/ygoAnimations';
import type { DragItem } from '../../hooks/useDragDrop';

// YGO engine constants for the shared card-zone primitive. Monster zones
// and spell/trap zones each have 5 slots per side; field spell is a single
// shared slot. Attack-drag (own face-up ATK monster on opponent's monster)
// stays on the legacy useDraggable in this PR — that's PR 4.1 scope.
const YGO_ENGINE_ID = 'yugioh';
const YGO_ACCENT = '#c4b5fd'; // duelist violet — distinguishes from MTG arcane
const YGO_MZONE = (i: number) => `ygo-mzone-${i}`;
const YGO_STZONE = (i: number) => `ygo-stzone-${i}`;
const YGO_FIELD_SPELL = 'ygo-field-spell';

function ygoIntent(isMonster: boolean, isSpell: boolean, isTrap: boolean): CardIntent {
  if (isMonster) return 'summon';
  if (isSpell) return 'activate';
  if (isTrap) return 'set';
  return 'play';
}
import { useCardPreviewStore, useCardPreviewBindings } from '../../hooks/useCardPreview';
import { useCardInspector } from '../../hooks/useCardInspector';
import CardPreviewWrapper from './shared/CardPreviewWrapper';
import { LegendaryEntranceOverlay } from './shared/LegendaryEntranceOverlay';
import { BattlefieldEventLayer } from './shared/DamageFloater';
import { useBattlefieldEvents } from '../../hooks/useBattlefieldEvents';
import type { CardData, PlayerData, GameState } from '../../types';

const PHASE_LABELS: Record<string, string> = {
  DRAW: 'Draw',
  STANDBY: 'Standby',
  MAIN1: 'Main 1',
  BATTLE_START: 'Battle',
  BATTLE_STEP: 'Battle',
  DAMAGE_STEP: 'Damage',
  DAMAGE_CALC: 'Damage',
  BATTLE_END: 'Battle End',
  MAIN2: 'Main 2',
  END: 'End',
};

const PHASE_DISPLAY = ['DRAW', 'STANDBY', 'MAIN1', 'BATTLE_STEP', 'MAIN2', 'END'];

function isInBattlePhase(phase: string): boolean {
  return ['BATTLE_START', 'BATTLE_STEP', 'DAMAGE_STEP', 'DAMAGE_CALC', 'BATTLE_END'].includes(phase);
}

// ======================================================================
// Wrapper: Draggable hand card
// ======================================================================

interface YGODraggableHandCardProps {
  card: CardData;
  index: number;
  total: number;
  isMyTurn: boolean;
  selectedHandCard: string | null;
  myMonsterZones: (CardData | null)[];
  mySpellTrapZones: (CardData | null)[];
  onClick: () => void;
  onHoverStart: () => void;
  onHoverEnd: () => void;
}

function YGODraggableHandCard({
  card,
  index,
  total,
  isMyTurn,
  selectedHandCard,
  myMonsterZones,
  mySpellTrapZones,
  onClick,
  onHoverStart,
  onHoverEnd,
}: YGODraggableHandCardProps) {
  const isMonster = card.types?.includes('YGO_MONSTER') ?? false;
  const isSpell = card.types?.includes('YGO_SPELL') ?? false;
  const isTrap = card.types?.includes('YGO_TRAP') ?? false;
  const isFieldSpell = isSpell && card.ygo_spell_type === 'Field';

  const intent: CardIntent = ygoIntent(isMonster, isSpell, isTrap);

  // Valid zones depend on card type. Monsters land in empty m-zones,
  // spells/traps land in empty st-zones, field spells go to the field
  // spell slot (or any free st-zone). Engine validates server-side.
  const validZones = useMemo(() => {
    const zones: string[] = [];
    if (isMonster) {
      myMonsterZones.forEach((slot, i) => {
        if (!slot) zones.push(YGO_MZONE(i));
      });
    } else if (isFieldSpell) {
      zones.push(YGO_FIELD_SPELL);
      mySpellTrapZones.forEach((slot, i) => {
        if (!slot) zones.push(YGO_STZONE(i));
      });
    } else if (isSpell || isTrap) {
      mySpellTrapZones.forEach((slot, i) => {
        if (!slot) zones.push(YGO_STZONE(i));
      });
    }
    return zones;
  }, [isMonster, isSpell, isTrap, isFieldSpell, myMonsterZones, mySpellTrapZones]);

  const handCard = useHandCard({
    cardId: card.id,
    cardName: card.name,
    engineId: YGO_ENGINE_ID,
    accent: YGO_ACCENT,
    validZones: !isMyTurn ? [] : validZones,
    intent,
    disabled: !isMyTurn,
  });
  const isBeingDragged = handCard.isDragging;
  const dragProps = {
    draggable: handCard.draggable,
    onDragStart: handCard.onDragStart,
    onDragEnd: handCard.onDragEnd,
  };

  // Preview bindings: right-click / long-press to pin the hand card preview.
  const previewProps = useCardPreviewBindings(card, { disabled: isBeingDragged });

  // Fan layout
  const fan = useMemo(() => {
    if (total <= 1) return { rotate: 0, y: 0 };
    const center = (total - 1) / 2;
    const offset = index - center;
    const maxRotate = Math.min(total * 2, 15);
    const rotate = (offset / center) * maxRotate;
    const y = Math.abs(offset) * Math.min(total, 6);
    return { rotate, y };
  }, [index, total]);

  return (
    <motion.div
      key={card.id}
      initial={{ opacity: 0, y: 40 }}
      animate={{ opacity: 1, rotate: fan.rotate, y: fan.y }}
      exit={{ opacity: 0, y: 40 }}
      transition={{ type: 'spring', stiffness: 200, damping: 25 }}
      style={{
        marginLeft: index === 0 ? 0 : -8,
        zIndex: selectedHandCard === card.id ? 30 : index,
      }}
      whileHover={{ y: -20, scale: 1.1, zIndex: 20, rotate: 0 }}
    >
      <span
        {...previewProps}
        className="inline-block"
        style={
          handCard.isPrimed
            ? { transform: 'translateY(-8px)', filter: `drop-shadow(0 0 10px ${YGO_ACCENT})`, transition: 'transform 120ms ease, filter 120ms ease' }
            : undefined
        }
      >
        <YGOCard
          card={card}
          size="sm"
          onClick={() => { handCard.onClick(); onClick(); }}
          selected={selectedHandCard === card.id}
          animate={false}
          onHoverStart={onHoverStart}
          onHoverEnd={onHoverEnd}
          dragProps={dragProps}
          isBeingDragged={isBeingDragged}
        />
      </span>
    </motion.div>
  );
}

// ======================================================================
// Wrapper: Monster zone slot (drop target + optional drag source for attacks)
// ======================================================================

interface YGOMonsterZoneSlotProps {
  index: number;
  card: CardData | null;
  isMine: boolean;
  isMyTurn: boolean;
  inBattlePhase: boolean;
  attackMode: string | null;
  selectedFieldCard: string | null;
  oppMonsterZones: (CardData | null)[];
  onFieldCardClick: (card: CardData, isMine: boolean) => void;
  onHoverStart: (card: CardData) => void;
  onHoverEnd: () => void;
  onMonsterDrop: (item: DragItem, slotIndex: number) => void;
  onAttackDrop: (attackerId: string, targetId: string) => void;
}

function YGOMonsterZoneSlot({
  index,
  card,
  isMine,
  isMyTurn,
  inBattlePhase,
  attackMode,
  selectedFieldCard,
  oppMonsterZones,
  onFieldCardClick,
  onHoverStart,
  onHoverEnd,
  onMonsterDrop,
  onAttackDrop,
}: YGOMonsterZoneSlotProps) {
  // Drop target: my empty monster zone accepts monster hand cards.
  // Migrated to shared card-zone primitive. The onPlay callback
  // synthesizes a DragItem-shaped value so the upstream onMonsterDrop
  // handler (which expects DragItem) keeps working without modification.
  const ownZone = useCardZone({
    zoneId: YGO_MZONE(index),
    engineId: YGO_ENGINE_ID,
    onPlay: (cardId) => {
      if (!isMine || !isMyTurn) return;
      const item: DragItem = {
        type: 'hand-card',
        card: { id: cardId } as CardData,
      } as DragItem;
      onMonsterDrop(item, index);
    },
  });
  // onDragEnter aliased to onDragOver: legacy DropPropsType requires it,
  // but the shared primitive uses onDragOver for both enter + over.
  const dropProps = !isMine || !isMyTurn
    ? undefined
    : {
        onClick: ownZone.onClick,
        onDragOver: ownZone.onDragOver,
        onDragEnter: ownZone.onDragOver,
        onDragLeave: ownZone.onDragLeave,
        onDrop: ownZone.onDrop,
      };
  const isValidTarget = ownZone.isValid;
  const isHovered = ownZone.isHovered;

  // Drop target for opponent monsters: accept attack drags
  const oppDropZoneId = card ? card.id : `ygo-opp-mzone-empty-${index}`;
  const { dropProps: attackDropProps, isValidTarget: isAttackTarget, isHovered: isAttackHovered } = useDropTarget({
    zoneId: oppDropZoneId,
    onDrop: (item: DragItem) => {
      if (card && item.card?.id) {
        onAttackDrop(item.card.id, card.id);
      }
    },
    disabled: isMine || !card,
  });

  // Drag source: own face-up ATK monsters during battle phase
  const canAttackDrag = isMine && isMyTurn && inBattlePhase && card && !card.face_down &&
    card.ygo_position !== 'face_up_def' && card.ygo_position !== 'face_down_def';

  const attackValidZones = useMemo(() => {
    if (!canAttackDrag) return [];
    const zones: string[] = [];
    oppMonsterZones.forEach(c => {
      if (c) zones.push(c.id);
    });
    zones.push('ygo-direct-attack');
    zones.push('ygo-direct-attack-bar');
    return zones;
  }, [canAttackDrag, oppMonsterZones]);

  const { dragProps: attackDragProps, isBeingDragged: isAttackDragged } = useDraggable({
    item: {
      type: 'field-card',
      card: card || { id: '', name: '', mana_cost: null, types: [], subtypes: [], power: null, toughness: null, text: '', tapped: false, counters: {}, damage: 0, controller: null, owner: null },
      gameMode: 'ygo',
      intent: 'attack',
      sourceZone: 'monster-zone',
    },
    validDropZones: attackValidZones,
    disabled: !canAttackDrag,
  });

  // Merge drop props: for opponent zones, use attack drop; for own zones, use summon drop
  const activeDropProps = !isMine && card ? attackDropProps : (isMine ? dropProps : undefined);
  const activeIsTarget = !isMine && card ? isAttackTarget : (isMine ? isValidTarget : false);
  const activeIsHovered = !isMine && card ? isAttackHovered : (isMine ? isHovered : false);

  return (
    <div
      className={`
        relative
        w-[76px] h-[106px] border border-dashed rounded-lg flex items-center justify-center
        border-ygo-gold-dim/30
        ${!card ? 'bg-ygo-dark/40' : ''}
        ${attackMode && !isMine && card ? 'border-red-500/50 bg-red-950/20' : ''}
        ${activeIsHovered && !card ? 'border-ygo-gold bg-ygo-gold/10' : ''}
        ${activeIsTarget && !card ? 'border-ygo-gold/50 bg-ygo-gold/5' : ''}
        transition-colors duration-200
      `}
      style={{ boxShadow: 'inset 0 2px 8px rgba(0,0,0,0.3)' }}
      {...(!card && isMine && dropProps ? dropProps : {})}
    >
      {!card && isMine && (
        <ZoneHighlight
          isValid={ownZone.isValid}
          isHovered={ownZone.isHovered}
          hasActiveCard={ownZone.hasActiveCard}
          activeAccent={ownZone.activeAccent}
        />
      )}
      <AnimatePresence mode="popLayout">
        {card && (
          <motion.div
            key={card.id}
            variants={cardSummon}
            initial="initial"
            animate="animate"
            exit="exit"
          >
            <CardPreviewWrapper
              card={card}
              disabled={isAttackDragged || !!card.face_down}
            >
              <YGOCard
                card={card}
                size="sm"
                onClick={() => onFieldCardClick(card, isMine)}
                selected={isMine && selectedFieldCard === card.id}
                isTarget={attackMode !== null && !isMine}
                isDefensePosition={card.ygo_position === 'face_up_def' || card.ygo_position === 'face_down_def'}
                onHoverStart={() => !card.face_down && onHoverStart(card)}
                onHoverEnd={onHoverEnd}
                dragProps={canAttackDrag ? attackDragProps : undefined}
                isBeingDragged={isAttackDragged}
                dropProps={activeDropProps}
                isDropTarget={activeIsTarget}
                isDropHovered={activeIsHovered}
              />
            </CardPreviewWrapper>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ======================================================================
// Wrapper: Spell/Trap zone slot (drop target)
// ======================================================================

interface YGOSpellTrapZoneSlotProps {
  index: number;
  card: CardData | null;
  isMine: boolean;
  isMyTurn: boolean;
  attackMode: string | null;
  selectedFieldCard: string | null;
  onFieldCardClick: (card: CardData, isMine: boolean) => void;
  onHoverStart: (card: CardData) => void;
  onHoverEnd: () => void;
  onSpellTrapDrop: (item: DragItem, slotIndex: number) => void;
}

function YGOSpellTrapZoneSlot({
  index,
  card,
  isMine,
  isMyTurn,
  attackMode,
  selectedFieldCard,
  onFieldCardClick,
  onHoverStart,
  onHoverEnd,
  onSpellTrapDrop,
}: YGOSpellTrapZoneSlotProps) {
  const zone = useCardZone({
    zoneId: YGO_STZONE(index),
    engineId: YGO_ENGINE_ID,
    onPlay: (cardId) => {
      if (!isMine || !isMyTurn) return;
      const item: DragItem = {
        type: 'hand-card',
        card: { id: cardId } as CardData,
      } as DragItem;
      onSpellTrapDrop(item, index);
    },
  });
  const dropProps = !isMine || !isMyTurn
    ? undefined
    : {
        onClick: zone.onClick,
        onDragOver: zone.onDragOver,
        onDragLeave: zone.onDragLeave,
        onDrop: zone.onDrop,
      };
  const isValidTarget = zone.isValid;
  const isHovered = zone.isHovered;

  return (
    <div
      className={`
        relative
        w-[76px] h-[106px] border border-dashed rounded-lg flex items-center justify-center
        border-teal-800/30
        ${!card ? 'bg-ygo-dark/40' : ''}
        ${attackMode && !isMine && card ? 'border-red-500/50 bg-red-950/20' : ''}
        ${isHovered && !card ? 'border-ygo-gold bg-ygo-gold/10' : ''}
        ${isValidTarget && !card ? 'border-ygo-gold/50 bg-ygo-gold/5' : ''}
        transition-colors duration-200
      `}
      style={{ boxShadow: 'inset 0 2px 8px rgba(0,0,0,0.3)' }}
      {...(!card && isMine && dropProps ? dropProps : {})}
    >
      {!card && isMine && (
        <ZoneHighlight
          isValid={zone.isValid}
          isHovered={zone.isHovered}
          hasActiveCard={zone.hasActiveCard}
          activeAccent={zone.activeAccent}
        />
      )}
      <AnimatePresence mode="popLayout">
        {card && (
          <motion.div
            key={card.id}
            variants={cardSummon}
            initial="initial"
            animate="animate"
            exit="exit"
          >
            <CardPreviewWrapper card={card} disabled={!!card.face_down}>
              <YGOCard
                card={card}
                size="sm"
                onClick={() => onFieldCardClick(card, isMine)}
                selected={isMine && selectedFieldCard === card.id}
                isTarget={attackMode !== null && !isMine}
                isDefensePosition={card.ygo_position === 'face_up_def' || card.ygo_position === 'face_down_def'}
                onHoverStart={() => !card.face_down && onHoverStart(card)}
                onHoverEnd={onHoverEnd}
              />
            </CardPreviewWrapper>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ======================================================================
// Wrapper: Field Spell zone (drop target)
// ======================================================================

interface YGOFieldSpellZoneProps {
  card: CardData | null;
  isMine: boolean;
  isMyTurn: boolean;
  onActivateCard: (cardId: string) => void;
  onHoverStart: (card: CardData) => void;
  onHoverEnd: () => void;
}

function YGOFieldSpellZone({
  card,
  isMine,
  isMyTurn,
  onActivateCard,
  onHoverStart,
  onHoverEnd,
}: YGOFieldSpellZoneProps) {
  const zone = useCardZone({
    zoneId: YGO_FIELD_SPELL,
    engineId: YGO_ENGINE_ID,
    onPlay: (cardId) => {
      if (!isMine || !isMyTurn) return;
      onActivateCard(cardId);
    },
  });
  const dropProps = !isMine || !isMyTurn
    ? undefined
    : {
        onClick: zone.onClick,
        onDragOver: zone.onDragOver,
        onDragLeave: zone.onDragLeave,
        onDrop: zone.onDrop,
      };
  const isValidTarget = zone.isValid;
  const isHovered = zone.isHovered;

  if (card) {
    return (
      <YGOCard card={card} size="sm" onClick={isMine ? () => {} : undefined} animate={false}
        onHoverStart={() => !card.face_down && onHoverStart(card)}
        onHoverEnd={onHoverEnd}
      />
    );
  }

  return (
    <div
      className={`
        relative
        w-16 h-[88px] border border-dashed rounded-lg opacity-30
        ${isHovered ? 'border-ygo-gold opacity-100 bg-ygo-gold/10' : ''}
        ${isValidTarget ? 'border-green-800/60 opacity-60 bg-green-900/10' : 'border-green-800/20'}
        transition-all duration-200
      `}
      {...(isMine && dropProps ? dropProps : {})}
    >
      {isMine && (
        <ZoneHighlight
          isValid={zone.isValid}
          isHovered={zone.isHovered}
          hasActiveCard={zone.hasActiveCard}
          activeAccent={zone.activeAccent}
        />
      )}
    </div>
  );
}

// ======================================================================
// Wrapper: Direct attack drop zone
// ======================================================================

interface YGODirectAttackZoneProps {
  attackMode: string | null;
  inBattlePhase: boolean;
  onDirectAttackClick: () => void;
  onDirectAttackDrop: (attackerId: string) => void;
}

function YGODirectAttackZone({
  attackMode,
  inBattlePhase,
  onDirectAttackClick,
  onDirectAttackDrop,
}: YGODirectAttackZoneProps) {
  const { dropProps, isValidTarget, isHovered } = useDropTarget({
    zoneId: 'ygo-direct-attack',
    onDrop: (item: DragItem) => {
      if (item.card?.id) {
        onDirectAttackDrop(item.card.id);
      }
    },
    disabled: !inBattlePhase,
  });

  return (
    <div {...dropProps}>
      {(attackMode || isValidTarget) && (
        <button
          onClick={onDirectAttackClick}
          className={`px-3 py-1 text-white text-xs font-bold rounded transition-colors ${
            isHovered
              ? 'bg-red-500 shadow-lg shadow-red-500/40'
              : isValidTarget
                ? 'bg-red-700 hover:bg-red-600 animate-pulse ring-1 ring-red-400/50'
                : 'bg-red-700 hover:bg-red-600 animate-pulse'
          }`}
        >
          Direct Attack
        </button>
      )}
    </div>
  );
}

// ======================================================================
// Wrapper: Opponent info bar with direct attack drop zone
// ======================================================================

interface YGOOpponentInfoBarProps {
  opponentPlayer: PlayerData | null;
  oppLPDelta: number | null;
  oppGraveyard: CardData[];
  oppBanished: CardData[];
  oppExtraDeckSize: number;
  inBattlePhase: boolean;
  onDirectAttackDrop: (attackerId: string) => void;
  onShowGraveyard: () => void;
  onShowBanished: () => void;
}

function YGOOpponentInfoBar({
  opponentPlayer,
  oppLPDelta,
  oppGraveyard,
  oppBanished,
  oppExtraDeckSize,
  inBattlePhase,
  onDirectAttackDrop,
  onShowGraveyard,
  onShowBanished,
}: YGOOpponentInfoBarProps) {
  const { dropProps, isValidTarget, isHovered } = useDropTarget({
    zoneId: 'ygo-direct-attack-bar',
    onDrop: (item: DragItem) => {
      if (item.card?.id) {
        onDirectAttackDrop(item.card.id);
      }
    },
    disabled: !inBattlePhase,
  });

  return (
    <div
      className={`
        flex items-center justify-between px-4 py-2 bg-ygo-dark/80 backdrop-blur-sm border-b border-ygo-gold-dim/20
        ${isHovered ? 'bg-red-950/50 border-red-500/50' : ''}
        ${isValidTarget && !isHovered ? 'border-red-500/20' : ''}
        transition-colors duration-200
      `}
      {...dropProps}
    >
      <div className="flex items-center gap-3">
        <span className="text-sm text-ygo-gold-dim font-medium">{opponentPlayer?.name || 'Opponent'}</span>
        <LPDisplay lp={opponentPlayer?.lp ?? 8000} delta={oppLPDelta} isPlayer={false} />
      </div>
      <div className="flex items-center gap-3 text-xs text-gray-500">
        <span>Hand: {opponentPlayer?.hand_size ?? 0}</span>
        <span>Deck: {opponentPlayer?.library_size ?? 0}</span>
        <button onClick={onShowGraveyard} className="text-gray-400 hover:text-ygo-gold transition-colors">
          GY: {oppGraveyard.length}
        </button>
        {(oppBanished?.length || 0) > 0 && (
          <button onClick={onShowBanished} className="text-gray-500 hover:text-gray-300 transition-colors">
            Ban: {oppBanished.length}
          </button>
        )}
        {(oppExtraDeckSize || 0) > 0 && (
          <span className="text-purple-400">ED: {oppExtraDeckSize}</span>
        )}
      </div>
    </div>
  );
}

// ======================================================================
// LP display (static sub-component)
// ======================================================================

function LPDisplay({ lp, delta, isPlayer }: { lp: number; delta: number | null; isPlayer: boolean }) {
  return (
    <div className="relative">
      <span className={`text-lg font-bold ${isPlayer ? 'text-ygo-gold-bright' : 'text-ygo-gold'} ${delta !== null ? 'animate-ygo-lp-flash' : ''}`}>
        LP {lp}
      </span>
      <AnimatePresence>
        {delta !== null && (
          <motion.span
            initial={{ opacity: 1, y: 0 }}
            animate={{ opacity: 0, y: -20 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.2 }}
            className={`absolute -top-4 left-1/2 -translate-x-1/2 text-sm font-bold whitespace-nowrap ${
              delta < 0 ? 'text-red-400' : 'text-green-400'
            }`}
          >
            {delta > 0 ? '+' : ''}{delta}
          </motion.span>
        )}
      </AnimatePresence>
    </div>
  );
}

// ======================================================================
// Main component
// ======================================================================

interface YGOGameBoardProps {
  gameState: GameState;
  playerId: string;
  isMyTurn: boolean;
  myPlayer: PlayerData | null;
  opponentPlayer: PlayerData | null;
  myMonsterZones: (CardData | null)[];
  oppMonsterZones: (CardData | null)[];
  mySpellTrapZones: (CardData | null)[];
  oppSpellTrapZones: (CardData | null)[];
  myFieldSpell: CardData | null;
  oppFieldSpell: CardData | null;
  hand: CardData[];
  myGraveyard: CardData[];
  oppGraveyard: CardData[];
  myBanished?: CardData[];
  oppBanished?: CardData[];
  myExtraDeckSize?: number;
  oppExtraDeckSize?: number;
  ygoPhase: string;
  onNormalSummon: (cardId: string) => void;
  onSetMonster: (cardId: string) => void;
  onFlipSummon: (cardId: string) => void;
  onChangePosition: (cardId: string) => void;
  onActivateCard: (cardId: string, targetId?: string) => void;
  onSetSpellTrap: (cardId: string) => void;
  onDeclareAttack: (attackerId: string, targetId: string) => void;
  onDirectAttack: (attackerId: string) => void;
  onEndPhase: () => void;
  onEndTurn: () => void;
}

export function YGOGameBoard({
  gameState,
  playerId,
  isMyTurn,
  myPlayer,
  opponentPlayer,
  myMonsterZones,
  oppMonsterZones,
  mySpellTrapZones,
  oppSpellTrapZones,
  myFieldSpell,
  oppFieldSpell,
  hand,
  myGraveyard,
  oppGraveyard,
  myBanished = [],
  oppBanished = [],
  myExtraDeckSize = 0,
  oppExtraDeckSize = 0,
  ygoPhase,
  onNormalSummon,
  onSetMonster,
  onFlipSummon,
  onChangePosition,
  onActivateCard,
  onSetSpellTrap,
  onDeclareAttack,
  onDirectAttack,
  onEndPhase,
  onEndTurn,
}: YGOGameBoardProps) {
  const [selectedHandCard, setSelectedHandCard] = useState<string | null>(null);
  const [selectedFieldCard, setSelectedFieldCard] = useState<string | null>(null);
  const [attackMode, setAttackMode] = useState<string | null>(null);
  const [showGraveyard, setShowGraveyard] = useState<'mine' | 'opp' | null>(null);
  const [showBanished, setShowBanished] = useState<'mine' | 'opp' | null>(null);
  const [showExtraDeck, setShowExtraDeck] = useState(false);
  // Card preview (hover + pin) routes through a shared store so the detail
  // panel and other modes stay consistent. `setHoveredCard` wraps the store
  // action so existing zero-arg callers (framer-motion's `onHoverStart` /
  // `onHoverEnd` signatures) still type-check — bare calls clear the hover.
  const previewSetHover = useCardPreviewStore((s) => s.setHover);
  const clearCardPreview = useCardPreviewStore((s) => s.clearAll);
  const setHoveredCard = useCallback(
    (card?: CardData | null) => previewSetHover(card ?? null),
    [previewSetHover],
  );
  useEffect(() => {
    return () => clearCardPreview();
  }, [clearCardPreview]);
  const [showTurnBanner, setShowTurnBanner] = useState(false);
  const [graveyardFilter, setGraveyardFilter] = useState<'all' | 'monster' | 'spell' | 'trap'>('all');

  // Drop choice popup — migrated to shared dropChoiceStore (PR 1). The
  // <DropChoicePopup /> is mounted once at App root and listens for
  // open() calls from any engine. YGO uses it for Normal Summon vs Set
  // (monster zones) and Activate vs Set (spell zones). The bespoke
  // YGODropChoicePopup component was deleted in PR 4.1.
  const openDropChoice = useDropChoiceStore((s) => s.open);

  // LP tracking for flash effects
  const prevMyLP = useRef(myPlayer?.lp ?? 8000);
  const prevOppLP = useRef(opponentPlayer?.lp ?? 8000);
  const [myLPDelta, setMyLPDelta] = useState<number | null>(null);
  const [oppLPDelta, setOppLPDelta] = useState<number | null>(null);

  const inBattlePhase = isInBattlePhase(ygoPhase);

  // Wire death floaters (YGO has no per-card HP in state, so only death events fire)
  useBattlefieldEvents(gameState, 'ygo');

  // Shared "click to inspect, then act" modal — additive to drag+drop / hover.
  const inspector = useCardInspector();

  // Clear selection / attack-mode state. Hoisted above the click handlers so
  // the inspector's action callbacks can call it without a TDZ error.
  const clearSelections = useCallback(() => {
    setSelectedHandCard(null);
    setSelectedFieldCard(null);
    setAttackMode(null);
  }, []);

  // Turn banner trigger
  const prevTurn = useRef(gameState.turn_number);
  useEffect(() => {
    if (gameState.turn_number !== prevTurn.current) {
      prevTurn.current = gameState.turn_number;
      setShowTurnBanner(true);
    }
  }, [gameState.turn_number]);

  // LP change detection
  useEffect(() => {
    const myLP = myPlayer?.lp ?? 8000;
    const oppLP = opponentPlayer?.lp ?? 8000;
    const timers: ReturnType<typeof setTimeout>[] = [];

    if (myLP !== prevMyLP.current) {
      const delta = myLP - prevMyLP.current;
      setMyLPDelta(delta);
      prevMyLP.current = myLP;
      timers.push(setTimeout(() => setMyLPDelta(null), 1500));
    }
    if (oppLP !== prevOppLP.current) {
      const delta = oppLP - prevOppLP.current;
      setOppLPDelta(delta);
      prevOppLP.current = oppLP;
      timers.push(setTimeout(() => setOppLPDelta(null), 1500));
    }

    return () => timers.forEach(clearTimeout);
  }, [myPlayer?.lp, opponentPlayer?.lp]);

  const handleHandCardClick = useCallback((card: CardData) => {
    // Mirror the prior selection behavior so the action-bar buttons /
    // drag affordances stay in sync, then open the shared inspector with
    // a context-appropriate action list. The inspector is additive: when
    // it's dismissed, the action-bar buttons remain available for users
    // who prefer that flow.
    if (!isMyTurn) return;
    const wasSelected = selectedHandCard === card.id;
    setSelectedHandCard(wasSelected ? null : card.id);
    setSelectedFieldCard(null);
    setAttackMode(null);

    const isMonsterCard = card.types?.includes('YGO_MONSTER') ?? false;
    const isSpellCard = card.types?.includes('YGO_SPELL') ?? false;
    const isTrapCard = card.types?.includes('YGO_TRAP') ?? false;

    // Build inspector card descriptor.
    let cost: string | undefined;
    let stats: string | undefined;
    let subtitle: string | undefined;
    let engineKind: 'monster' | 'spell_trap' = isMonsterCard ? 'monster' : 'spell_trap';
    if (isMonsterCard) {
      if (typeof card.level === 'number') cost = `Lv ${card.level}`;
      else if (typeof card.rank === 'number') cost = `Rank ${card.rank}`;
      else if (typeof card.link_rating === 'number') cost = `Link ${card.link_rating}`;
      const atk = card.atk ?? card.power;
      const def = card.def_val ?? card.toughness;
      const atkStr = atk != null ? `ATK ${atk}` : '';
      const defStr = def != null ? `DEF ${def}` : '';
      stats = [atkStr, defStr].filter(Boolean).join(' / ') || undefined;
      const typeBits = [card.attribute, card.ygo_monster_type].filter(Boolean).join(' · ');
      subtitle = typeBits || 'Monster';
    } else if (isSpellCard) {
      engineKind = 'spell_trap';
      subtitle = card.ygo_spell_type ? `${card.ygo_spell_type} Spell` : 'Spell';
    } else if (isTrapCard) {
      engineKind = 'spell_trap';
      subtitle = card.ygo_trap_type ? `${card.ygo_trap_type} Trap` : 'Trap';
    }

    // Build action list. Each action wraps the existing engine handler
    // and clears the selection so the action-bar state stays consistent.
    // Tribute / chain-target follow-ups are still driven by the engine —
    // those flows close the modal naturally because the action returns
    // void (the engine then opens its own picker / chain window).
    const actions = [] as Parameters<typeof inspector.open>[1];

    if (isMonsterCard) {
      actions!.push({
        label: 'Normal Summon',
        variant: 'primary',
        onClick: () => {
          onNormalSummon(card.id);
          clearSelections();
        },
      });
      actions!.push({
        label: 'Set',
        variant: 'secondary',
        onClick: () => {
          onSetMonster(card.id);
          clearSelections();
        },
      });
    } else if (isSpellCard) {
      actions!.push({
        label: 'Activate',
        variant: 'primary',
        onClick: () => {
          onActivateCard(card.id);
          clearSelections();
        },
      });
      actions!.push({
        label: 'Set',
        variant: 'secondary',
        onClick: () => {
          onSetSpellTrap(card.id);
          clearSelections();
        },
      });
    } else if (isTrapCard) {
      actions!.push({
        label: 'Set',
        variant: 'primary',
        onClick: () => {
          onSetSpellTrap(card.id);
          clearSelections();
        },
      });
    }

    inspector.open(
      {
        id: card.id,
        name: card.name,
        text: card.text,
        cost,
        stats,
        subtitle,
        engine: engineKind,
      },
      actions,
    );
  }, [
    isMyTurn,
    selectedHandCard,
    inspector,
    onNormalSummon,
    onSetMonster,
    onActivateCard,
    onSetSpellTrap,
    clearSelections,
  ]);

  const handleFieldCardClick = useCallback((card: CardData, isMine: boolean) => {
    if (attackMode && !isMine && card.id) {
      onDeclareAttack(attackMode, card.id);
      setAttackMode(null);
      return;
    }
    if (!isMine || !isMyTurn) return;
    setSelectedFieldCard(prev => prev === card.id ? null : card.id);
    setSelectedHandCard(null);
    setAttackMode(null);
  }, [isMyTurn, attackMode, onDeclareAttack]);

  const handleDirectAttackClick = useCallback(() => {
    if (attackMode) {
      onDirectAttack(attackMode);
      setAttackMode(null);
    }
  }, [attackMode, onDirectAttack]);

  // --- Drag-and-drop handlers ---

  const handleMonsterZoneDrop = useCallback((item: DragItem, _slotIndex: number) => {
    const cardId = item.card?.id;
    if (!cardId) return;
    const cardName = item.card?.name || 'Monster';
    // Normal Summon vs Set — shared DropChoicePopup (mounted at App root).
    openDropChoice(
      { id: cardId, name: cardName, subtitle: 'Monster' },
      [
        {
          label: 'Normal Summon',
          variant: 'primary',
          onClick: () => { onNormalSummon(cardId); clearSelections(); },
        },
        {
          label: 'Set',
          variant: 'secondary',
          onClick: () => { onSetMonster(cardId); clearSelections(); },
        },
      ],
    );
  }, [onNormalSummon, onSetMonster, clearSelections, openDropChoice]);

  const handleSpellTrapZoneDrop = useCallback((item: DragItem, _slotIndex: number) => {
    const cardId = item.card?.id;
    if (!cardId) return;
    const cardName = item.card?.name || 'Card';
    const isTrapCard = item.card?.types?.includes('YGO_TRAP');

    if (isTrapCard) {
      // Traps can only be set face-down — no choice needed.
      onSetSpellTrap(cardId);
      clearSelections();
      return;
    }
    // Spell: Activate vs Set via shared DropChoicePopup.
    openDropChoice(
      { id: cardId, name: cardName, subtitle: 'Spell' },
      [
        {
          label: 'Activate',
          variant: 'primary',
          onClick: () => { onActivateCard(cardId); clearSelections(); },
        },
        {
          label: 'Set',
          variant: 'secondary',
          onClick: () => { onSetSpellTrap(cardId); clearSelections(); },
        },
      ],
    );
  }, [onActivateCard, onSetSpellTrap, clearSelections, openDropChoice]);

  const handleAttackDrop = useCallback((attackerId: string, targetId: string) => {
    onDeclareAttack(attackerId, targetId);
  }, [onDeclareAttack]);

  const handleDirectAttackDrop = useCallback((attackerId: string) => {
    onDirectAttack(attackerId);
  }, [onDirectAttack]);

  // Computed hand card state
  const selectedHandCardData = hand.find(c => c.id === selectedHandCard);
  const isMonster = selectedHandCardData?.types?.includes('YGO_MONSTER') ?? false;
  const isSpell = selectedHandCardData?.types?.includes('YGO_SPELL') ?? false;
  const isTrap = selectedHandCardData?.types?.includes('YGO_TRAP') ?? false;

  // Computed field card state
  const selectedFieldCardData = (() => {
    if (!selectedFieldCard) return null;
    for (const card of myMonsterZones) {
      if (card?.id === selectedFieldCard) return card;
    }
    for (const card of mySpellTrapZones) {
      if (card?.id === selectedFieldCard) return card;
    }
    return null;
  })();

  const isFieldMonster = selectedFieldCardData?.types?.includes('YGO_MONSTER') ?? false;
  const isFaceDown = selectedFieldCardData?.face_down ?? false;
  const isDefPos = selectedFieldCardData?.ygo_position === 'face_up_def' || selectedFieldCardData?.ygo_position === 'face_down_def';

  // Graveyard filtering
  const filterGY = (cards: CardData[]) => {
    if (graveyardFilter === 'all') return cards;
    if (graveyardFilter === 'monster') return cards.filter(c => c.types?.includes('YGO_MONSTER'));
    if (graveyardFilter === 'spell') return cards.filter(c => c.types?.includes('YGO_SPELL'));
    return cards.filter(c => c.types?.includes('YGO_TRAP'));
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden"
      style={{
        background: 'linear-gradient(to bottom, #0a0e1a 0%, #0f1425 50%, #0a0e1a 100%)',
      }}
    >
      {/* Turn Banner */}
      <YGOTurnBanner
        isMyTurn={isMyTurn}
        visible={showTurnBanner}
        onDismiss={() => setShowTurnBanner(false)}
      />

      {/* Card Detail Panel (reads from shared preview store) */}
      <YGOCardDetailPanel />

      {/* Overlays (fixed-position) */}
      <LegendaryEntranceOverlay
        battlefieldCards={[
          ...myMonsterZones.filter((c): c is CardData => c !== null),
          ...oppMonsterZones.filter((c): c is CardData => c !== null),
        ]}
      />
      <BattlefieldEventLayer />

      {/* Opponent info bar (also a direct attack drop zone) */}
      <YGOOpponentInfoBar
        opponentPlayer={opponentPlayer}
        oppLPDelta={oppLPDelta}
        oppGraveyard={oppGraveyard}
        oppBanished={oppBanished}
        oppExtraDeckSize={oppExtraDeckSize}
        inBattlePhase={inBattlePhase}
        onDirectAttackDrop={handleDirectAttackDrop}
        onShowGraveyard={() => setShowGraveyard('opp')}
        onShowBanished={() => setShowBanished('opp')}
      />

      {/* Main Field */}
      <div className="flex-1 flex flex-col justify-center items-center gap-1 py-1 relative min-h-0">
        {/* Subtle center radial glow */}
        <div className="absolute inset-0 pointer-events-none"
          style={{ background: 'radial-gradient(ellipse at 50% 50%, rgba(212,168,67,0.03) 0%, transparent 60%)' }}
        />

        {/* Opponent back row (spell/trap) */}
        <div className="flex items-center gap-3">
          {oppFieldSpell ? (
            <YGOCard card={oppFieldSpell} size="sm" animate={false}
              onHoverStart={() => !oppFieldSpell.face_down && setHoveredCard(oppFieldSpell)}
              onHoverEnd={() => setHoveredCard(null)}
            />
          ) : (
            <div className="w-16 h-[88px] border border-dashed border-green-800/20 rounded-lg opacity-30" />
          )}
          <div className="flex gap-2 justify-center">
            {Array.from({ length: 5 }).map((_, i) => (
              <YGOSpellTrapZoneSlot
                key={i}
                index={i}
                card={oppSpellTrapZones[i] || null}
                isMine={false}
                isMyTurn={isMyTurn}
                attackMode={attackMode}
                selectedFieldCard={selectedFieldCard}
                onFieldCardClick={handleFieldCardClick}
                onHoverStart={setHoveredCard}
                onHoverEnd={() => setHoveredCard(null)}
                onSpellTrapDrop={handleSpellTrapZoneDrop}
              />
            ))}
          </div>
        </div>

        {/* Opponent monster row */}
        <div className="flex items-center gap-3">
          <div className="w-16" />
          <div className="flex gap-2 justify-center">
            {Array.from({ length: 5 }).map((_, i) => (
              <YGOMonsterZoneSlot
                key={i}
                index={i}
                card={oppMonsterZones[i] || null}
                isMine={false}
                isMyTurn={isMyTurn}
                inBattlePhase={inBattlePhase}
                attackMode={attackMode}
                selectedFieldCard={selectedFieldCard}
                oppMonsterZones={oppMonsterZones}
                onFieldCardClick={handleFieldCardClick}
                onHoverStart={setHoveredCard}
                onHoverEnd={() => setHoveredCard(null)}
                onMonsterDrop={handleMonsterZoneDrop}
                onAttackDrop={handleAttackDrop}
              />
            ))}
          </div>
        </div>

        {/* Gold center divider + Phase indicator */}
        <div className="flex items-center gap-4 py-1 w-full max-w-2xl px-4">
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-ygo-gold-dim/40 to-transparent" />
          <div className="flex gap-1">
            {PHASE_DISPLAY.map(phase => {
              const isActive = ygoPhase === phase || (phase === 'BATTLE_STEP' && inBattlePhase);
              return (
                <div
                  key={phase}
                  className={`px-2.5 py-1 rounded text-xs font-bold uppercase tracking-wider transition-all duration-200 ${
                    isActive
                      ? 'bg-ygo-gold text-ygo-dark shadow-md shadow-ygo-gold/30'
                      : 'bg-ygo-dark/80 text-gray-600 border border-ygo-gold-dim/15'
                  }`}
                >
                  {PHASE_LABELS[phase] || phase}
                </div>
              );
            })}
          </div>
          <YGODirectAttackZone
            attackMode={attackMode}
            inBattlePhase={inBattlePhase}
            onDirectAttackClick={handleDirectAttackClick}
            onDirectAttackDrop={handleDirectAttackDrop}
          />
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-ygo-gold-dim/40 to-transparent" />
        </div>

        {/* My monster row */}
        <div className="flex items-center gap-3">
          <div className="w-16" />
          <div className="flex gap-2 justify-center">
            {Array.from({ length: 5 }).map((_, i) => (
              <YGOMonsterZoneSlot
                key={i}
                index={i}
                card={myMonsterZones[i] || null}
                isMine={true}
                isMyTurn={isMyTurn}
                inBattlePhase={inBattlePhase}
                attackMode={attackMode}
                selectedFieldCard={selectedFieldCard}
                oppMonsterZones={oppMonsterZones}
                onFieldCardClick={handleFieldCardClick}
                onHoverStart={setHoveredCard}
                onHoverEnd={() => setHoveredCard(null)}
                onMonsterDrop={handleMonsterZoneDrop}
                onAttackDrop={handleAttackDrop}
              />
            ))}
          </div>
        </div>

        {/* My back row (spell/trap) */}
        <div className="flex items-center gap-3">
          <YGOFieldSpellZone
            card={myFieldSpell}
            isMine={true}
            isMyTurn={isMyTurn}
            onActivateCard={onActivateCard}
            onHoverStart={setHoveredCard}
            onHoverEnd={() => setHoveredCard(null)}
          />
          <div className="flex gap-2 justify-center">
            {Array.from({ length: 5 }).map((_, i) => (
              <YGOSpellTrapZoneSlot
                key={i}
                index={i}
                card={mySpellTrapZones[i] || null}
                isMine={true}
                isMyTurn={isMyTurn}
                attackMode={attackMode}
                selectedFieldCard={selectedFieldCard}
                onFieldCardClick={handleFieldCardClick}
                onHoverStart={setHoveredCard}
                onHoverEnd={() => setHoveredCard(null)}
                onSpellTrapDrop={handleSpellTrapZoneDrop}
              />
            ))}
          </div>
        </div>
      </div>

      {/* My info bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-ygo-dark/80 backdrop-blur-sm border-t border-ygo-gold-dim/20">
        <div className="flex items-center gap-3">
          <span className="text-sm text-ygo-gold font-medium">{myPlayer?.name || 'You'}</span>
          <LPDisplay lp={myPlayer?.lp ?? 8000} delta={myLPDelta} isPlayer={true} />
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>Deck: {myPlayer?.library_size ?? 0}</span>
          <button onClick={() => setShowGraveyard('mine')} className="text-gray-400 hover:text-ygo-gold transition-colors">
            GY: {myGraveyard.length}
          </button>
          {myBanished.length > 0 && (
            <button onClick={() => setShowBanished('mine')} className="text-gray-500 hover:text-gray-300 transition-colors">
              Ban: {myBanished.length}
            </button>
          )}
          {myExtraDeckSize > 0 && (
            <button onClick={() => setShowExtraDeck(true)} className="text-purple-400 hover:text-purple-300 transition-colors">
              ED: {myExtraDeckSize}
            </button>
          )}
          <span className={`px-2 py-0.5 rounded text-[10px] font-bold transition-colors ${
            isMyTurn ? 'bg-ygo-gold/90 text-ygo-dark' : 'bg-gray-800 text-gray-500'
          }`}>
            {isMyTurn ? 'YOUR TURN' : 'WAITING'}
          </span>
        </div>
      </div>

      {/* Hand with fan layout */}
      <div className="bg-ygo-dark/60 backdrop-blur-sm border-t border-ygo-gold-dim/15 px-4 py-3">
        <motion.div
          variants={handStagger}
          initial={false}
          animate="animate"
          className="flex justify-center items-end"
          style={{ minHeight: '100px' }}
        >
          <AnimatePresence mode="popLayout">
            {hand.map((card, index) => (
              <YGODraggableHandCard
                key={card.id}
                card={card}
                index={index}
                total={hand.length}
                isMyTurn={isMyTurn}
                selectedHandCard={selectedHandCard}
                myMonsterZones={myMonsterZones}
                mySpellTrapZones={mySpellTrapZones}
                onClick={() => handleHandCardClick(card)}
                onHoverStart={() => setHoveredCard(card)}
                onHoverEnd={() => setHoveredCard(null)}
              />
            ))}
          </AnimatePresence>
          {hand.length === 0 && (
            <div className="text-gray-600 text-sm py-8">No cards in hand</div>
          )}
        </motion.div>
      </div>

      {/* Action bar */}
      <YGOActionBar
        isMyTurn={isMyTurn}
        selectedHandCard={selectedHandCard}
        isMonster={isMonster}
        isSpell={isSpell}
        isTrap={isTrap}
        selectedFieldCard={selectedFieldCard}
        isFieldMonster={isFieldMonster}
        isFaceDown={isFaceDown}
        isDefPos={isDefPos ?? false}
        attackMode={attackMode}
        onNormalSummon={() => { onNormalSummon(selectedHandCard!); clearSelections(); }}
        onSetMonster={() => { onSetMonster(selectedHandCard!); clearSelections(); }}
        onFlipSummon={() => { onFlipSummon(selectedFieldCard!); clearSelections(); }}
        onChangePosition={() => { onChangePosition(selectedFieldCard!); clearSelections(); }}
        onActivateCard={() => { onActivateCard(selectedHandCard!); clearSelections(); }}
        onSetSpellTrap={() => { onSetSpellTrap(selectedHandCard!); clearSelections(); }}
        onAttack={() => { setAttackMode(selectedFieldCard); setSelectedFieldCard(null); }}
        onCancelAttack={() => setAttackMode(null)}
        onEndPhase={() => { onEndPhase(); clearSelections(); }}
        onEndTurn={() => { onEndTurn(); clearSelections(); }}
      />

      {/* Drop Choice Popup — replaced by shared <DropChoicePopup />
          (PR 4.1) which is mounted once at App root and driven from
          dropChoiceStore via openDropChoice() above. */}

      {/* Game over overlay */}
      <AnimatePresence>
        {gameState.is_game_over && (
          <motion.div
            variants={{ initial: { opacity: 0 }, animate: { opacity: 1 } }}
            initial="initial"
            animate="animate"
            className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50"
          >
            <motion.div
              variants={gameOverOverlay}
              initial="initial"
              animate="animate"
              className="bg-ygo-dark border-2 border-ygo-gold rounded-2xl p-10 text-center shadow-2xl shadow-ygo-gold/20"
            >
              <h2 className={`text-4xl font-bold mb-3 tracking-wide ${
                gameState.winner === playerId
                  ? 'text-ygo-gold-bright drop-shadow-[0_0_15px_rgba(212,168,67,0.6)]'
                  : 'text-gray-400'
              }`}>
                {gameState.winner === playerId ? 'VICTORY!' : 'DEFEAT'}
              </h2>
              <p className="text-gray-400 mb-6 text-sm">
                {gameState.winner === playerId
                  ? 'You won the duel!'
                  : 'You lost the duel.'}
              </p>
              <button
                onClick={() => window.location.href = '/'}
                className="px-8 py-2.5 bg-ygo-gold hover:bg-ygo-gold-bright text-ygo-dark font-bold rounded-lg transition-colors"
              >
                Return to Menu
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Graveyard modal */}
      <AnimatePresence>
        {showGraveyard && (
          <motion.div
            variants={modalBackdrop}
            initial="initial" animate="animate" exit="exit"
            className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-40"
            onClick={() => setShowGraveyard(null)}
          >
            <motion.div
              variants={modalContent}
              initial="initial" animate="animate" exit="exit"
              className="bg-ygo-dark/95 border border-ygo-gold-dim/30 rounded-xl p-6 max-w-lg max-h-[80vh] overflow-y-auto shadow-2xl"
              onClick={e => e.stopPropagation()}
            >
              <h3 className="text-lg font-bold text-ygo-gold mb-3">
                {showGraveyard === 'mine' ? 'Your Graveyard' : "Opponent's Graveyard"}
              </h3>

              {/* Filter tabs */}
              <div className="flex gap-1.5 mb-4">
                {(['all', 'monster', 'spell', 'trap'] as const).map(f => (
                  <button
                    key={f}
                    onClick={() => setGraveyardFilter(f)}
                    className={`px-2 py-0.5 text-[10px] font-bold rounded uppercase transition-colors ${
                      graveyardFilter === f
                        ? f === 'monster' ? 'bg-ygo-gold/80 text-ygo-dark'
                        : f === 'spell' ? 'bg-teal-700 text-white'
                        : f === 'trap' ? 'bg-pink-700 text-white'
                        : 'bg-gray-600 text-white'
                        : 'bg-gray-800 text-gray-500 hover:text-gray-300'
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>

              <div className="flex flex-wrap gap-2">
                {filterGY(showGraveyard === 'mine' ? myGraveyard : oppGraveyard).map((card, i) => (
                  <YGOCard key={`${card.id}-${i}`} card={card} size="md" animate={false}
                    onHoverStart={() => setHoveredCard(card)}
                    onHoverEnd={() => setHoveredCard(null)}
                  />
                ))}
                {filterGY(showGraveyard === 'mine' ? myGraveyard : oppGraveyard).length === 0 && (
                  <p className="text-gray-600 text-sm">No cards</p>
                )}
              </div>

              <button
                onClick={() => setShowGraveyard(null)}
                className="mt-4 px-4 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded transition-colors"
              >
                Close
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Banished modal */}
      <YGOBanishedModal
        isOpen={showBanished !== null}
        onClose={() => setShowBanished(null)}
        myBanished={myBanished}
        oppBanished={oppBanished}
        tab={showBanished || 'mine'}
        onTabChange={(t) => setShowBanished(t)}
      />

      {/* Extra deck modal */}
      <YGOExtraDeckModal
        isOpen={showExtraDeck}
        onClose={() => setShowExtraDeck(false)}
        cards={[]}
      />
    </div>
  );
}
