/**
 * HandView Component
 *
 * Displays the player's hand of cards in a fan layout.
 * Cards can be dragged to play lands or cast spells on targets.
 */

import { useMemo, useCallback } from 'react';
import clsx from 'clsx';
import { Card } from '../cards/Card';
import { CastIcon, PlayLandIcon } from '../ui/Icons';
import { useHandCard } from '../../hooks/useHandCard';
import { useCardZoneStore, type CardIntent } from '../../stores/cardZoneStore';
import type { CardData, LegalActionData } from '../../types';
import { useCardInspector, type InspectableCardType } from '../../hooks/useCardInspector';

// MTG engine constants for the shared card-zone primitive. The hand-card
// validZones include the battlefield + (eventually) per-permanent and
// per-player zone ids for cast-time targets. This PR migrates the
// hand-to-battlefield flow; cast-time targeting + multi-target + combat
// stay on the existing pending_choice / overlay path until PR 3.1.
const MTG_ENGINE_ID = 'mtg';
const MTG_ACCENT = '#a78bfa'; // arcane violet
const MTG_BATTLEFIELD_ME = 'mtg-battlefield-me';

// Pick the intent verb from the MTG card's types. Lands/permanents land
// on the battlefield ("play"); instants and sorceries are one-shot
// effects ("activate"). Engines with cast-time target requirements still
// route through pending_choice after the initial hop.
function mtgIntent(card: CardData): CardIntent {
  const types = card.types || [];
  if (types.includes('LAND')) return 'play';
  if (types.includes('INSTANT') || types.includes('SORCERY')) return 'activate';
  return 'play';
}

// Map MTG type tags onto the inspector's engine accent palette.
function pickInspectorType(card: CardData): InspectableCardType {
  const types = card.types || [];
  if (types.includes('CREATURE')) return 'creature';
  if (types.includes('LAND')) return 'land';
  // Instants, sorceries, enchantments, artifacts, planeswalkers all share
  // the "spell" accent (blue) — matches the existing CAST badge.
  return 'spell';
}

// Build the inspector subtitle for an MTG card: type line — e.g. "Creature · Human Soldier".
function buildSubtitle(card: CardData): string | undefined {
  const types = (card.types || []).map(
    (t) => t.charAt(0) + t.slice(1).toLowerCase(),
  );
  const left = types.join(' ');
  const right = (card.subtypes || []).join(' ');
  if (left && right) return `${left} — ${right}`;
  return left || right || undefined;
}

// Stats line for creatures / planeswalkers; undefined otherwise.
function buildStats(card: CardData): string | undefined {
  const types = card.types || [];
  if (types.includes('CREATURE') && card.power != null && card.toughness != null) {
    return `${card.power}/${card.toughness}`;
  }
  return undefined;
}

interface HandViewProps {
  cards: CardData[];
  selectedCardId?: string | null;
  castableCards?: string[];
  playableLands?: string[];
  legalActions?: LegalActionData[];
  onCardClick?: (card: CardData) => void;
  onGetValidDropZones?: (card: CardData) => string[];
  disabled?: boolean;
}

// ---------------------------------------------------------------------------
// HandCard — inline card with useDraggable (replaces DraggableCard wrapper)
// Badges (LAND / TARGET / CAST) are MTG-specific and preserved here.
// ---------------------------------------------------------------------------
interface HandCardProps {
  card: CardData;
  action: LegalActionData | undefined;
  isSelected: boolean;
  isPlayable: boolean;
  disabled: boolean;
  onClick?: () => void;
  validDropZones: string[];
}

function HandCard({
  card,
  action,
  isSelected,
  isPlayable,
  disabled,
  onClick,
  validDropZones,
}: HandCardProps) {
  // Track other-card-dragging via the shared card-zone store so the
  // hand fade-out effect still works after migration. dragItemPayload
  // is no longer needed; useHandCard owns the drag protocol.
  const dragCardId = useCardZoneStore((s) => s.dragCardId);
  const isDragging = dragCardId !== null;

  const handCard = useHandCard({
    cardId: card.id,
    cardName: card.name,
    engineId: MTG_ENGINE_ID,
    accent: MTG_ACCENT,
    // Untargeted spells & lands resolve on the battlefield. Targeted
    // spells (Lightning Bolt et al.) still drop on the battlefield to
    // cast; the pending_choice overlay then drives target selection.
    // validDropZones from props is honored when the parent passes a
    // refined list; default is the battlefield.
    validZones: disabled || !isPlayable ? [] : (validDropZones.length > 0 ? validDropZones : [MTG_BATTLEFIELD_ME]),
    intent: mtgIntent(card),
    disabled: disabled || !isPlayable,
  });
  const isBeingDragged = handCard.isDragging;
  const dragProps = {
    draggable: handCard.draggable,
    onDragStart: handCard.onDragStart,
    onDragEnd: handCard.onDragEnd,
  };

  const isLand = action?.type === 'PLAY_LAND';
  const isTargetedSpell = action?.type === 'CAST_SPELL' && action.requires_targets;
  const isOtherCardDragging = isDragging && dragCardId !== card.id;

  // Compose: clicking opens the inspector (parent's onClick path)
  // AND primes the card in the shared store so the battlefield zone
  // lights with the MTG accent.
  const handleClick = () => {
    handCard.onClick();
    onClick?.();
  };

  return (
    <div
      {...dragProps}
      className={clsx(
        'transition-all duration-200',
        {
          'opacity-50 scale-95 shadow-2xl': isBeingDragged,
          'opacity-30': isOtherCardDragging,
          'cursor-grab active:cursor-grabbing': !disabled && isPlayable,
        },
      )}
      style={
        handCard.isPrimed
          ? { transform: 'translateY(-8px)', filter: `drop-shadow(0 0 10px ${MTG_ACCENT})`, transition: 'transform 120ms ease, filter 120ms ease' }
          : undefined
      }
    >
      <Card
        card={card}
        size="medium"
        isSelected={isSelected}
        isHighlighted={isPlayable && !disabled && !isBeingDragged}
        onClick={handleClick}
        showDetails
      />

      {/* MTG-specific drag-intent badge */}
      {!disabled && isPlayable && !isBeingDragged && !isOtherCardDragging && (
        <div className="absolute -top-2 -right-2 z-20">
          <div
            className={clsx(
              'px-2 py-0.5 rounded-full text-[10px] font-bold shadow-lg border',
              isLand
                ? 'bg-emerald-500 text-white border-emerald-400'
                : isTargetedSpell
                  ? 'bg-red-500 text-white border-red-400'
                  : 'bg-blue-500 text-white border-blue-400',
            )}
          >
            {/* Human-requested label: LAND / TARGET / CAST */}
            {isLand ? 'LAND' : isTargetedSpell ? 'TARGET' : 'CAST'}
          </div>
        </div>
      )}
    </div>
  );
}

export function HandView({
  cards,
  selectedCardId,
  castableCards = [],
  playableLands = [],
  legalActions = [],
  onCardClick,
  onGetValidDropZones,
  disabled = false,
}: HandViewProps) {
  // Migrated away from useDragDropStore; the shared cardZoneStore now
  // tracks drag state across all engines. The local dragItem analogue
  // is the active card (drag or prime) which we look up by ID.
  const activeCardId = useCardZoneStore((s) => s.dragCardId ?? s.primedCardId);
  const validDropZoneSet = useCardZoneStore((s) => s.validZoneIds);
  const isDragging = useCardZoneStore((s) => s.dragCardId !== null);
  const activeCard = useMemo(
    () => cards.find((c) => c.id === activeCardId) ?? null,
    [activeCardId, cards],
  );
  const validDropZones = useMemo(() => Array.from(validDropZoneSet), [validDropZoneSet]);
  const inspector = useCardInspector();

  // Open the shared inspector modal for a hand card. The Play action
  // re-routes the click into the existing `onCardClick` handler, which
  // dispatches CAST_SPELL / PLAY_LAND through the engine pipeline
  // (targeting flows continue to work via overlay / pending_choice).
  const openInspector = useCallback(
    (card: CardData) => {
      const action = legalActions.find(
        (a) =>
          (a.type === 'CAST_SPELL' || a.type === 'PLAY_LAND') &&
          a.card_id === card.id,
      );
      const canCast = castableCards.includes(card.id);
      const canPlayLand = playableLands.includes(card.id);
      const isPlayable = canCast || canPlayLand;
      const isLand = action?.type === 'PLAY_LAND';
      const isTargeted = action?.type === 'CAST_SPELL' && action.requires_targets;
      // Default "insufficient mana" gating mirrors HandView's existing
      // disabled state: a spell shows up but isn't in `castableCards`
      // when mana is short.
      const disabledReason = disabled
        ? 'Your opponent has priority'
        : !isPlayable
          ? action?.type === 'CAST_SPELL'
            ? 'Insufficient mana'
            : 'Not playable right now'
          : undefined;
      inspector.open(
        {
          id: card.id,
          name: card.name,
          text: card.text,
          cost: card.mana_cost ?? undefined,
          subtitle: buildSubtitle(card),
          stats: buildStats(card),
          engine: pickInspectorType(card),
        },
        [
          {
            label: isLand ? 'Play Land' : isTargeted ? 'Cast (pick target)' : 'Cast',
            variant: 'primary',
            disabled: disabled || !isPlayable,
            disabledReason,
            // Route through the parent's onCardClick — GameView's
            // `handleCardClick` dispatches castSpell/playLand from there.
            // For targeted spells the engine then drives the target
            // overlay; closing the modal here is correct because the
            // overlay handles its own targeting UI on the battlefield.
            onClick: () => {
              onCardClick?.(card);
            },
          },
        ],
      );
    },
    [
      inspector,
      legalActions,
      castableCards,
      playableLands,
      disabled,
      onCardClick,
    ],
  );

  // Get context about the currently dragged card. Now sourced from the
  // shared store via `activeCard` (matches the existing visual + label).
  const dragContext = useMemo(() => {
    if (!isDragging || !activeCard) return null;

    const action = legalActions.find(
      (a) =>
        (a.type === 'CAST_SPELL' || a.type === 'PLAY_LAND') &&
        a.card_id === activeCard.id,
    );
    const isLand = action?.type === 'PLAY_LAND';
    const isTargetedSpell = action?.type === 'CAST_SPELL' && action.requires_targets;

    return {
      cardName: activeCard.name,
      isLand,
      isTargetedSpell,
      targetCount: validDropZones.length,
    };
  }, [isDragging, activeCard, legalActions, validDropZones]);

  // Calculate card positions for fan effect
  const cardPositions = useMemo(() => {
    const count = cards.length;
    if (count === 0) return [];

    const maxRotation = Math.min(count * 4, 30);
    const rotationStep = count > 1 ? maxRotation / (count - 1) : 0;
    const startRotation = -maxRotation / 2;
    const overlapPercent = count <= 4 ? 0 : Math.min((count - 4) * 8, 50);

    return cards.map((_, index) => ({
      rotation: startRotation + index * rotationStep,
      translateY: Math.abs(index - (count - 1) / 2) * 4,
      zIndex: index,
      marginLeft: index === 0 ? 0 : -overlapPercent,
    }));
  }, [cards]);

  // Get the legal action for a card
  const getCardAction = useCallback((cardId: string): LegalActionData | undefined => {
    return legalActions.find(
      (a) => (a.type === 'CAST_SPELL' || a.type === 'PLAY_LAND') && a.card_id === cardId
    );
  }, [legalActions]);

  return (
    <div className="relative">
      {/* Hand container */}
      <div className={clsx(
        'bg-gradient-to-t from-slate-900/95 to-slate-800/90 backdrop-blur-sm rounded-t-2xl border border-slate-600/50 border-b-0 px-6 py-4 shadow-2xl',
        'transition-all duration-200',
        {
          'border-cyan-500/50': isDragging,
        }
      )}>
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-slate-400 text-xs uppercase tracking-widest font-semibold">Your Hand</span>
            <span className="bg-slate-700 text-slate-300 text-xs px-2 py-0.5 rounded-full font-medium">
              {cards.length} {cards.length === 1 ? 'card' : 'cards'}
            </span>
          </div>
          {cards.length > 0 && (
            <div className="text-xs">
              {isDragging && dragContext ? (
                <span className={clsx(
                  'px-3 py-1 rounded-full font-medium',
                  dragContext.isLand
                    ? 'bg-emerald-600/80 text-emerald-100'
                    : dragContext.isTargetedSpell
                      ? 'bg-red-600/80 text-red-100'
                      : 'bg-blue-600/80 text-blue-100'
                )}>
                  {dragContext.isLand
                    ? 'Drop on your battlefield to play'
                    : dragContext.isTargetedSpell
                      ? `Drop on a target (${dragContext.targetCount} valid)`
                      : 'Drop on battlefield to cast'}
                </span>
              ) : (
                <span className="text-slate-500">
                  Drag cards to play lands or cast spells
                </span>
              )}
            </div>
          )}
        </div>

        {/* Cards */}
        {cards.length === 0 ? (
          <div className="text-slate-500 text-sm italic text-center py-8 border border-dashed border-slate-600 rounded-lg">
            No cards in hand
          </div>
        ) : (
          <div className="flex justify-center items-end min-h-[230px] pb-2">
            {cards.map((card, index) => {
              const isSelected = selectedCardId === card.id;
              const canCast = castableCards.includes(card.id);
              const canPlayLand = playableLands.includes(card.id);
              const isPlayable = canCast || canPlayLand;
              const position = cardPositions[index] || { rotation: 0, translateY: 0, zIndex: index, marginLeft: 0 };
              const action = getCardAction(card.id);
              const cardValidDropZones = isPlayable && !disabled && onGetValidDropZones
                ? onGetValidDropZones(card)
                : [];

              return (
                <div
                  key={card.id}
                  role="button"
                  tabIndex={!disabled || isPlayable ? 0 : -1}
                  aria-label={card.name}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      if (!disabled || isPlayable) openInspector(card);
                    }
                  }}
                  className={clsx(
                    'relative transition-all duration-200 ease-out',
                    {
                      'cursor-pointer': !disabled || isPlayable,
                      'cursor-not-allowed': disabled && !isPlayable,
                    }
                  )}
                  style={{
                    transform: `rotate(${position.rotation}deg) translateY(${isSelected ? -30 : position.translateY}px)`,
                    transformOrigin: 'bottom center',
                    zIndex: isSelected ? 100 : position.zIndex,
                    marginLeft: index === 0 ? 0 : `${position.marginLeft}px`,
                  }}
                >
                  <div
                    className={clsx(
                      'transition-transform duration-200',
                      {
                        'hover:-translate-y-6 hover:scale-105': !disabled && !isSelected,
                        'scale-110': isSelected,
                        'opacity-40 grayscale': disabled && !isPlayable,
                      }
                    )}
                  >
                    <HandCard
                      card={card}
                      action={action}
                      isSelected={isSelected}
                      isPlayable={isPlayable}
                      disabled={disabled}
                      onClick={disabled && !isPlayable ? undefined : () => openInspector(card)}
                      validDropZones={cardValidDropZones}
                    />
                  </div>

                  {/* Playable badge */}
                  {isPlayable && !disabled && (
                    <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 z-10">
                      <span
                        className={clsx(
                          'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide shadow-lg',
                          'border-2',
                          canCast
                            ? 'bg-gradient-to-r from-blue-600 to-blue-500 text-white border-blue-400'
                            : 'bg-gradient-to-r from-emerald-600 to-emerald-500 text-white border-emerald-400'
                        )}
                      >
                        {canCast ? (
                          <>
                            <CastIcon size="sm" />
                            Cast
                          </>
                        ) : (
                          <>
                            <PlayLandIcon size="sm" />
                            Play
                          </>
                        )}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export default HandView;
