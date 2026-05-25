/**
 * GameBoard Component
 *
 * Main game board layout combining all game zones.
 * Manages drag and drop interactions between hand and battlefield.
 */

import { useMemo, useCallback, useEffect } from 'react';
import { TargetablePlayer } from './TargetablePlayer';
import { PhaseIndicator } from './PhaseIndicator';
import { Battlefield } from './Battlefield';
import { HandView } from './HandView';
import { StackView } from './StackView';
import { TriggerQueuePanel } from './TriggerQueuePanel';
import MTGCardDetailPanel from './MTGCardDetailPanel';
import { MultiTargetModal } from '../actions/MultiTargetModal';
import { LegendaryEntranceOverlay } from './shared/LegendaryEntranceOverlay';
import { BattlefieldEventLayer } from './shared/DamageFloater';
import { useBattlefieldEvents } from '../../hooks/useBattlefieldEvents';
import { useDragDropStore, type DragItem } from '../../hooks/useDragDrop';
import { useCardZoneStore } from '../../stores/cardZoneStore';
import { useCardPreviewStore } from '../../hooks/useCardPreview';
import type { GameState, CardData, LegalActionData, PendingChoice } from '../../types';

// MTG card-zone primitive constants (mirror HandView / Battlefield / etc.).
// When multi-target mode starts, the second-target candidates are primed
// into cardZoneStore so they glow arcane violet just like first-target
// candidates. Click any glowing card to fire the second-target select.
const MTG_ENGINE_ID = 'mtg';
const MTG_ACCENT = '#a78bfa';
const MTG_CARD_ZONE = (id: string) => `mtg-card-${id}`;
const MTG_PLAYER_ZONE = (id: string) => `mtg-player-${id}`;

interface GameBoardProps {
  gameState: GameState;
  playerId: string;
  selectedCardId?: string | null;
  validTargets?: string[];
  selectedAttackers?: string[];
  selectedBlockers?: Map<string, string>;
  onCardClick?: (card: CardData, zone: 'hand' | 'battlefield') => void;
  onPlayLand?: (cardId: string) => void;
  onCastSpell?: (cardId: string, targets?: string[]) => void;
  onCastMultiTargetSpell?: (cardId: string, targets: string[][]) => void;
  // Phase 5b: when an overlay-mode pending choice is active for the
  // local player, GameBoard surfaces the legal options as click-to-target
  // highlights and submits the choice on click.
  overlayPendingChoice?: PendingChoice | null;
  onSubmitOverlayChoice?: (selectedIds: string[]) => void;
}

export function GameBoard({
  gameState,
  playerId,
  selectedCardId,
  validTargets = [],
  selectedAttackers = [],
  selectedBlockers = new Map(),
  onCardClick,
  onPlayLand,
  onCastSpell,
  onCastMultiTargetSpell,
  overlayPendingChoice = null,
  onSubmitOverlayChoice,
}: GameBoardProps) {
  const multiTargetMode = useDragDropStore((s) => s.multiTargetMode);
  const multiTargetSpell = useDragDropStore((s) => s.multiTargetSpell);
  const multiTargetCardId = useDragDropStore((s) => s.multiTargetCardId);
  const firstTarget = useDragDropStore((s) => s.firstTarget);
  const secondTargetOptions = useDragDropStore((s) => s.secondTargetOptions);
  const startMultiTargetMode = useDragDropStore((s) => s.startMultiTargetMode);
  const cancelMultiTarget = useDragDropStore((s) => s.cancelMultiTarget);

  // Wire damage/heal/death floaters
  useBattlefieldEvents(gameState, 'mtg');

  // Clear card preview state on unmount (e.g. nav away from game)
  const clearPreview = useCardPreviewStore((s) => s.clearAll);
  useEffect(() => {
    return () => clearPreview();
  }, [clearPreview]);

  // Derive player info
  const player = gameState.players[playerId];
  const opponentId = useMemo(
    () => Object.keys(gameState.players).find((id) => id !== playerId) || '',
    [gameState.players, playerId]
  );
  const opponent = gameState.players[opponentId];

  // Split battlefield by controller
  const myBattlefield = useMemo(
    () => gameState.battlefield.filter((c) => c.controller === playerId),
    [gameState.battlefield, playerId]
  );
  const opponentBattlefield = useMemo(
    () => gameState.battlefield.filter((c) => c.controller === opponentId),
    [gameState.battlefield, opponentId]
  );

  // Get castable cards
  const castableCards = useMemo(
    () =>
      gameState.legal_actions
        .filter((a) => a.type === 'CAST_SPELL' && a.card_id)
        .map((a) => a.card_id!),
    [gameState.legal_actions]
  );

  const playableLands = useMemo(
    () =>
      gameState.legal_actions
        .filter((a) => a.type === 'PLAY_LAND' && a.card_id)
        .map((a) => a.card_id!),
    [gameState.legal_actions]
  );

  // Get attackers from combat state
  const combatAttackers = useMemo(
    () => gameState.combat?.attackers.map((a) => a.attacker_id) || [],
    [gameState.combat]
  );

  // Can act?
  const canAct = gameState.priority_player === playerId;

  // Phase 5b overlay-mode targeting: extract legal option IDs and a
  // quick membership lookup for the click-intercept path. Empty when no
  // overlay-mode choice is active.
  const overlayOptionIds = useMemo<string[]>(() => {
    if (!overlayPendingChoice) return [];
    return overlayPendingChoice.options
      .map((opt) => (typeof opt === 'string' ? opt : opt?.id))
      .filter((id): id is string => Boolean(id));
  }, [overlayPendingChoice]);

  const overlayTargetSet = useMemo(() => new Set(overlayOptionIds), [overlayOptionIds]);

  // Card click handler — intercepts when overlay-mode targeting is
  // active and the clicked card is a legal target, otherwise falls
  // through to the supplied ``onCardClick``.
  const handleCardClickInternal = useCallback(
    (card: CardData, zone: 'hand' | 'battlefield') => {
      if (overlayPendingChoice && onSubmitOverlayChoice && overlayTargetSet.has(card.id)) {
        onSubmitOverlayChoice([card.id]);
        return;
      }
      onCardClick?.(card, zone);
    },
    [overlayPendingChoice, onSubmitOverlayChoice, overlayTargetSet, onCardClick]
  );

  // Player click handler — same intercept pattern. When the click isn't
  // a legal target, we no-op (TargetablePlayer has no default click
  // behaviour outside drop-target wiring).
  const handlePlayerClickInternal = useCallback(
    (clickedPlayerId: string) => {
      if (
        overlayPendingChoice &&
        onSubmitOverlayChoice &&
        overlayTargetSet.has(clickedPlayerId)
      ) {
        onSubmitOverlayChoice([clickedPlayerId]);
      }
    },
    [overlayPendingChoice, onSubmitOverlayChoice, overlayTargetSet]
  );

  // Merge overlay target IDs with the existing ``validTargets`` prop so
  // both highlight paths drive a single glow ring in Battlefield.
  const effectiveValidTargets = useMemo(() => {
    if (overlayOptionIds.length === 0) return validTargets;
    return Array.from(new Set([...validTargets, ...overlayOptionIds]));
  }, [validTargets, overlayOptionIds]);

  // Get the legal action for a card
  const getCardAction = useCallback((cardId: string): LegalActionData | undefined => {
    return gameState.legal_actions.find(
      (a) => (a.type === 'CAST_SPELL' || a.type === 'PLAY_LAND') && a.card_id === cardId
    );
  }, [gameState.legal_actions]);

  // Determine valid drop zones for a card being dragged. Returns
  // engine-prefixed zone IDs (mtg-*) so cardZoneStore.validZoneIds
  // matches the zoneId each MTG drop target registers under. Fixed
  // PR 3 latent bug where 'battlefield-self' (legacy) didn't match
  // 'mtg-battlefield-me' (new).
  const getValidDropZones = useCallback((card: CardData): string[] => {
    const zones: string[] = [];
    const action = getCardAction(card.id);

    if (!action) return zones;

    // Lands can be dropped on your battlefield
    if (action.type === 'PLAY_LAND') {
      zones.push('mtg-battlefield-me');
      return zones;
    }

    // Spells that require targets - each valid target is a drop zone
    if (action.type === 'CAST_SPELL') {
      if (action.requires_targets) {
        // Add all permanents as potential targets (server will validate)
        gameState.battlefield.forEach((perm) => {
          zones.push(`mtg-card-${perm.id}`);
        });
        // Add players as targets (player-portrait drop zones are PR 3.2)
        zones.push(`mtg-player-${playerId}`);
        zones.push(`mtg-player-${opponentId}`);
      } else {
        // Non-targeted spells can be dropped on your battlefield to cast
        zones.push('mtg-battlefield-me');
      }
    }

    return zones;
  }, [getCardAction, gameState.battlefield, playerId, opponentId]);

  // Handle dropping a land on the battlefield
  const handleBattlefieldDrop = useCallback((item: DragItem) => {
    if (!item.action || !item.card) return;

    if (item.action.type === 'PLAY_LAND') {
      onPlayLand?.(item.card.id);
    } else if (item.action.type === 'CAST_SPELL' && !item.action.requires_targets) {
      // Non-targeted spell
      onCastSpell?.(item.card.id);
    }
  }, [onPlayLand, onCastSpell]);

  // Check if a spell needs multiple targets based on card text
  const detectMultiTarget = useCallback((cardText: string): { needsSecond: boolean; secondTargetType: 'opponent_permanent' | 'any_permanent' | 'any_creature' | 'player' } => {
    const text = cardText.toLowerCase();

    // Auras that exile on ETB (like Sheltered by Ghosts)
    if ((text.includes('exile') && text.includes('enchanted')) ||
        (text.includes('when') && text.includes('enters') && text.includes('exile'))) {
      return { needsSecond: true, secondTargetType: 'opponent_permanent' };
    }

    // "Choose another target" patterns
    if (text.includes('choose another')) {
      return { needsSecond: true, secondTargetType: 'any_permanent' };
    }

    // Fight effects
    if (text.includes('target creature you control fights')) {
      return { needsSecond: true, secondTargetType: 'any_creature' };
    }

    return { needsSecond: false, secondTargetType: 'any_permanent' };
  }, []);

  // Handle dropping/clicking a spell on a target card. There are three
  // distinct phases here:
  //   1. First drop of a multi-target spell    → start multi-target mode
  //      and prime cardZoneStore so the second-target candidates glow.
  //   2. Click/drop on a glowing second-target → fire the cast with both.
  //   3. Single-target drop                    → cast immediately.
  const handleCardDrop = useCallback((item: DragItem, targetCard: CardData) => {
    // Phase 2 — we're already in multi-target mode; this click/drop is
    // the second target. Read state from the store directly to avoid
    // stale closure values.
    const dd = useDragDropStore.getState();
    if (dd.multiTargetMode && dd.multiTargetCardId && dd.firstTarget) {
      onCastMultiTargetSpell?.(dd.multiTargetCardId, [[dd.firstTarget], [targetCard.id]]);
      // Clear both stores so no second-target glow lingers and the
      // legacy modal closes.
      useCardZoneStore.getState().clearAll();
      cancelMultiTarget();
      return;
    }

    if (!item.action || !item.card) return;

    if (item.action.type === 'CAST_SPELL' && item.action.requires_targets) {
      const { needsSecond, secondTargetType } = detectMultiTarget(item.card.text);

      if (needsSecond) {
        // Determine valid second targets based on type
        let secondTargets: string[] = [];

        switch (secondTargetType) {
          case 'opponent_permanent':
            secondTargets = gameState.battlefield
              .filter((p) => p.controller === opponentId && p.id !== targetCard.id)
              .map((p) => p.id);
            break;
          case 'any_permanent':
            secondTargets = gameState.battlefield
              .filter((p) => p.id !== targetCard.id)
              .map((p) => p.id);
            break;
          case 'any_creature':
            secondTargets = gameState.battlefield
              .filter((p) => p.types.includes('CREATURE') && p.id !== targetCard.id)
              .map((p) => p.id);
            break;
          case 'player':
            secondTargets = [playerId, opponentId];
            break;
        }

        if (secondTargets.length > 0) {
          startMultiTargetMode(item.action, item.card.id, targetCard.id, secondTargets);
          // Phase 1 — prime cardZoneStore with the second-target options
          // so they light up arcane violet (matches the rest of MTG
          // vocabulary). The existing MultiTargetModal still renders as
          // the secondary hint.
          const validZones = secondTargetType === 'player'
            ? secondTargets.map(MTG_PLAYER_ZONE)
            : secondTargets.map(MTG_CARD_ZONE);
          useCardZoneStore
            .getState()
            .primeCard(item.card.id, MTG_ENGINE_ID, validZones, MTG_ACCENT, 'play');
          return;
        }
      }

      // Single target spell - cast immediately
      onCastSpell?.(item.card.id, [targetCard.id]);
    }
  }, [gameState.battlefield, playerId, opponentId, onCastSpell, onCastMultiTargetSpell, startMultiTargetMode, cancelMultiTarget, detectMultiTarget]);

  // Handle dropping/clicking a spell on a player portrait. Same three
  // phases as handleCardDrop. Most multi-target spells second-target a
  // permanent, not a player, so this path is rarely the cast-finisher,
  // but Wear // Tear and friends use it.
  const handlePlayerDrop = useCallback((item: DragItem, targetPlayerId: string) => {
    // Phase 2 — already in multi-target mode; this click is the second
    // target (player).
    const dd = useDragDropStore.getState();
    if (dd.multiTargetMode && dd.multiTargetCardId && dd.firstTarget) {
      onCastMultiTargetSpell?.(dd.multiTargetCardId, [[dd.firstTarget], [targetPlayerId]]);
      useCardZoneStore.getState().clearAll();
      cancelMultiTarget();
      return;
    }

    if (!item.action || !item.card) return;

    if (item.action.type === 'CAST_SPELL' && item.action.requires_targets) {
      const { needsSecond, secondTargetType } = detectMultiTarget(item.card.text);

      if (needsSecond && secondTargetType === 'player') {
        const otherPlayer = targetPlayerId === playerId ? opponentId : playerId;
        startMultiTargetMode(item.action, item.card.id, targetPlayerId, [otherPlayer]);
        useCardZoneStore
          .getState()
          .primeCard(item.card.id, MTG_ENGINE_ID, [MTG_PLAYER_ZONE(otherPlayer)], MTG_ACCENT, 'play');
        return;
      }

      // Single target spell targeting player - cast immediately
      onCastSpell?.(item.card.id, [targetPlayerId]);
    }
  }, [playerId, opponentId, onCastSpell, onCastMultiTargetSpell, startMultiTargetMode, cancelMultiTarget, detectMultiTarget]);

  // Handle selecting the second target in multi-target mode. Called by
  // the legacy <MultiTargetModal> when the user clicks a candidate in
  // the modal. The new card-zone click-prime path (clicking a glowing
  // permanent on the board) routes through handleCardDrop / handlePlayerDrop
  // → both paths converge on onCastMultiTargetSpell.
  const handleSecondTargetSelect = useCallback((targetId: string) => {
    if (!multiTargetCardId || !firstTarget) return;
    onCastMultiTargetSpell?.(multiTargetCardId, [[firstTarget], [targetId]]);
    useCardZoneStore.getState().clearAll();
  }, [multiTargetCardId, firstTarget, onCastMultiTargetSpell]);

  // Handle canceling multi-target selection. Clear cardZoneStore too so
  // the second-target glow disappears.
  const handleMultiTargetCancel = useCallback(() => {
    cancelMultiTarget();
    useCardZoneStore.getState().clearAll();
  }, [cancelMultiTarget]);

  // Get cards for multi-target modal
  const multiTargetCards = useMemo(() => {
    return gameState.battlefield.filter((p) => secondTargetOptions.includes(p.id));
  }, [gameState.battlefield, secondTargetOptions]);

  // Get the first target card for display in modal
  const firstTargetCard = useMemo(() => {
    if (!firstTarget) return undefined;
    return gameState.battlefield.find((p) => p.id === firstTarget);
  }, [gameState.battlefield, firstTarget]);

  return (
    <div className="flex flex-col h-full gap-3 p-4 bg-game-bg">
      {/* Overlays (fixed-position, do not affect layout or re-render children) */}
      <LegendaryEntranceOverlay battlefieldCards={gameState.battlefield} />
      <BattlefieldEventLayer />

      {/* Card preview panel (hover / right-click to pin) */}
      <MTGCardDetailPanel />

      {/* Top Row: Opponent Info */}
      <div className="flex items-start gap-4">
        <div className="flex-1">
          {opponent && (
            <TargetablePlayer
              player={opponent}
              playerId={opponentId}
              isActivePlayer={gameState.active_player === opponentId}
              hasPriority={gameState.priority_player === opponentId}
              isOpponent
              onDrop={handlePlayerDrop}
              isTargetable={overlayTargetSet.has(opponentId)}
              onTargetClick={handlePlayerClickInternal}
            />
          )}
        </div>
        <PhaseIndicator
          turnNumber={gameState.turn_number}
          phase={gameState.phase}
          step={gameState.step}
          activePlayerName={
            gameState.active_player === playerId
              ? player?.name
              : opponent?.name
          }
        />
      </div>

      {/* Opponent's Battlefield */}
      <Battlefield
        permanents={opponentBattlefield}
        isOpponent
        selectedCardId={selectedCardId}
        validTargets={effectiveValidTargets}
        combatAttackers={combatAttackers}
        onCardClick={(card) => handleCardClickInternal(card, 'battlefield')}
        onCardDrop={handleCardDrop}
      />

      {/* Middle Row: Stack + queued triggers */}
      <div className="flex justify-center gap-2">
        <div className="w-80 flex flex-col gap-2">
          <StackView items={gameState.stack} playerId={playerId} />
          <TriggerQueuePanel
            pendingTriggers={gameState.pending_triggers ?? []}
            playerId={playerId}
          />
        </div>
      </div>

      {/* My Battlefield */}
      <Battlefield
        permanents={myBattlefield}
        selectedCardId={selectedCardId}
        validTargets={effectiveValidTargets}
        selectedAttackers={selectedAttackers}
        selectedBlockers={selectedBlockers}
        combatAttackers={combatAttackers}
        onCardClick={(card) => handleCardClickInternal(card, 'battlefield')}
        onCardDrop={handleCardDrop}
        onBattlefieldDrop={handleBattlefieldDrop}
      />

      {/* Bottom Row: My Info + Hand */}
      <div className="flex items-end gap-4">
        <div className="flex-shrink-0">
          {player && (
            <TargetablePlayer
              player={player}
              playerId={playerId}
              isActivePlayer={gameState.active_player === playerId}
              hasPriority={canAct}
              onDrop={handlePlayerDrop}
              isTargetable={overlayTargetSet.has(playerId)}
              onTargetClick={handlePlayerClickInternal}
            />
          )}
        </div>
        <div className="flex-1">
          <HandView
            cards={gameState.hand}
            selectedCardId={selectedCardId}
            castableCards={castableCards}
            playableLands={playableLands}
            legalActions={gameState.legal_actions}
            onCardClick={(card) => handleCardClickInternal(card, 'hand')}
            onGetValidDropZones={getValidDropZones}
            disabled={!canAct && !overlayPendingChoice}
          />
        </div>
      </div>

      {/* Game Over Overlay */}
      {gameState.is_game_over && (
        <div className="absolute inset-0 bg-black/80 flex items-center justify-center z-50">
          <div className="text-center">
            <h2 className="text-4xl font-bold text-white mb-4">
              {gameState.winner === playerId ? 'Victory!' : 'Defeat'}
            </h2>
            <p className="text-gray-300 text-lg">
              {gameState.winner === playerId
                ? 'You have won the game!'
                : 'Your opponent has won the game.'}
            </p>
          </div>
        </div>
      )}

      {/* Multi-Target Modal */}
      {multiTargetMode && (
        <MultiTargetModal
          availableTargets={multiTargetCards}
          firstTargetCard={firstTargetCard}
          targetPrompt={multiTargetSpell?.description || 'Select a permanent to target'}
          onSelect={handleSecondTargetSelect}
          onCancel={handleMultiTargetCancel}
        />
      )}
    </div>
  );
}

export default GameBoard;
