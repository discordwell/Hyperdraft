/**
 * GameBoard Component
 *
 * Main game board layout combining all game zones.
 * Manages drag and drop interactions between hand and battlefield.
 */

import { useMemo, useCallback, useEffect, useState } from 'react';
import { TargetablePlayer } from './TargetablePlayer';
import { PhaseIndicator } from './PhaseIndicator';
import { Battlefield } from './Battlefield';
import { HandView } from './HandView';
import { StackView } from './StackView';
import { TriggerQueuePanel } from './TriggerQueuePanel';
import MTGCardDetailPanel from './MTGCardDetailPanel';
// MultiTargetModal removed in PR A1 — second-target selection flows
// through cardZoneStore + the overlay pill in ChoiceModal.
import { LegendaryEntranceOverlay } from './shared/LegendaryEntranceOverlay';
import { BattlefieldEventLayer } from './shared/DamageFloater';
import { useBattlefieldEvents } from '../../hooks/useBattlefieldEvents';
// DragItem type retired in PR A2 — handlers receive plain string card ids
// and look up actions via gameState.legal_actions.
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
  // Arc A — multi-target second-pick now lives in cardZoneStore instead
  // of dragDropStore. GameBoard tracks just the cast context (card +
  // first target + dispatch kind) so the auto-confirm useEffect can fire
  // onCastMultiTargetSpell when the second target lands. The heuristic
  // detectMultiTarget stays for now; Arc B removes it once the engine
  // emits target metadata directly.
  const [multiTargetContext, setMultiTargetContext] = useState<{
    cardId: string;
    firstTarget: string;
    // Whether the second target is expected to be a player (vs. a permanent).
    // Used to strip the right engine-prefix from the zone id when dispatching.
    secondIsPlayer: boolean;
  } | null>(null);
  const activeChoiceId = useCardZoneStore((s) => s.activeChoiceId);
  const pendingTargets = useCardZoneStore((s) => s.pendingTargets);

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

  // PR 3.4 — combat visual prime. During DECLARE_ATTACKERS, surface the
  // opponent portrait as the default attack-into target by priming
  // cardZoneStore with `'attack'` intent. The opponent zone glows arcane
  // violet (via TargetablePlayer's <ZoneHighlight>) so combat reads in
  // the same vocabulary as casting/playing. The actual attacker
  // selection is still owned by gameStore.selectedAttackers /
  // toggleAttacker — this is a visual-cue layer only.
  const isDeclaringAttackers =
    gameState.phase === 'COMBAT' &&
    gameState.step === 'DECLARE_ATTACKERS' &&
    gameState.active_player === playerId;
  useEffect(() => {
    if (!isDeclaringAttackers || !opponentId || selectedAttackers.length === 0) {
      // Clean up any combat-prime when we leave the step.
      const intent = useCardZoneStore.getState().activeIntent;
      if (intent === 'attack') useCardZoneStore.getState().clearAll();
      return;
    }
    // Sentinel prime: any selected attacker id will do as the "active
    // card" — the engine accent + valid-zone-glow is what we care about.
    useCardZoneStore
      .getState()
      .primeCard(
        selectedAttackers[0],
        MTG_ENGINE_ID,
        [MTG_PLAYER_ZONE(opponentId)],
        MTG_ACCENT,
        'attack',
      );
    return () => {
      const intent = useCardZoneStore.getState().activeIntent;
      if (intent === 'attack') useCardZoneStore.getState().clearAll();
    };
  }, [isDeclaringAttackers, opponentId, selectedAttackers]);

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

  // Handle dropping a hand card on the battlefield. Receives just the
  // source card id; looks up the action from gameState.legal_actions
  // (the legal_actions list is the engine's source of truth — DragItem's
  // synthesized action was a workaround that's no longer needed).
  const handleBattlefieldDrop = useCallback((sourceCardId: string) => {
    const action = getCardAction(sourceCardId);
    if (!action) return;
    if (action.type === 'PLAY_LAND') {
      onPlayLand?.(sourceCardId);
    } else if (action.type === 'CAST_SPELL' && !action.requires_targets) {
      onCastSpell?.(sourceCardId);
    }
  }, [getCardAction, onPlayLand, onCastSpell]);

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

  // Handle dropping/clicking a spell on a target card. Two phases now:
  //   1. First drop of a multi-target spell → prime cardZoneStore with
  //      the second-target options + store cast context locally. The
  //      auto-confirm effect below dispatches onCastMultiTargetSpell
  //      when the user picks the second target via lit zone.
  //   2. Single-target drop → cast immediately.
  //
  // (The legacy "Phase 2" branch — handling the second-target click
  // here in handleCardDrop — is gone. The second click now flows
  // through useCardZone → togglePendingTarget → the effect.)
  const handleCardDrop = useCallback((sourceCardId: string, targetCard: CardData) => {
    const action = getCardAction(sourceCardId);
    if (!action) return;
    // Look up the full card for the detectMultiTarget heuristic
    // (reads card text). After Arc B the engine drives target groups
    // and this lookup goes away too.
    const sourceCard = gameState.hand.find((c) => c.id === sourceCardId);
    if (!sourceCard) return;

    if (action.type === 'CAST_SPELL' && action.requires_targets) {
      const { needsSecond, secondTargetType } = detectMultiTarget(sourceCard.text);

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
          const secondIsPlayer = secondTargetType === 'player';
          const validZones = secondIsPlayer
            ? secondTargets.map(MTG_PLAYER_ZONE)
            : secondTargets.map(MTG_CARD_ZONE);
          setMultiTargetContext({
            cardId: sourceCardId,
            firstTarget: targetCard.id,
            secondIsPlayer,
          });
          // Synthesize a choice for the second target. choiceId is
          // prefixed `mtg-multi-` so it never collides with a real
          // server-side pending_choice id. Arc B replaces this
          // synthesis with a real engine-emitted PendingChoice.
          useCardZoneStore.getState().primeFromChoice({
            choiceId: `mtg-multi-${sourceCardId}`,
            sourceId: sourceCardId,
            prompt: 'Pick second target',
            engineId: MTG_ENGINE_ID,
            accent: MTG_ACCENT,
            optionIds: validZones,
            metadata: {
              label: 'Second target',
              predicate_description: '',
              min: 1,
              max: 1,
            },
          });
          return;
        }
      }

      // Single target spell - cast immediately
      onCastSpell?.(sourceCardId, [targetCard.id]);
    }
  }, [gameState.battlefield, gameState.hand, playerId, opponentId, onCastSpell, detectMultiTarget, getCardAction]);

  // Handle dropping/clicking a spell on a player portrait. Same two
  // phases as handleCardDrop, second-target via cardZoneStore.
  const handlePlayerDrop = useCallback((sourceCardId: string, targetPlayerId: string) => {
    const action = getCardAction(sourceCardId);
    if (!action) return;
    const sourceCard = gameState.hand.find((c) => c.id === sourceCardId);
    if (!sourceCard) return;

    if (action.type === 'CAST_SPELL' && action.requires_targets) {
      const { needsSecond, secondTargetType } = detectMultiTarget(sourceCard.text);

      if (needsSecond && secondTargetType === 'player') {
        const otherPlayer = targetPlayerId === playerId ? opponentId : playerId;
        setMultiTargetContext({
          cardId: sourceCardId,
          firstTarget: targetPlayerId,
          secondIsPlayer: true,
        });
        useCardZoneStore.getState().primeFromChoice({
          choiceId: `mtg-multi-${sourceCardId}`,
          sourceId: sourceCardId,
          prompt: 'Pick second target',
          engineId: MTG_ENGINE_ID,
          accent: MTG_ACCENT,
          optionIds: [MTG_PLAYER_ZONE(otherPlayer)],
          metadata: {
            label: 'Second target',
            predicate_description: 'player',
            min: 1,
            max: 1,
          },
        });
        return;
      }

      // Single target spell targeting player - cast immediately
      onCastSpell?.(sourceCardId, [targetPlayerId]);
    }
  }, [playerId, opponentId, onCastSpell, detectMultiTarget, getCardAction, gameState.hand]);

  // Auto-confirm effect — when the user picks the second target via
  // cardZoneStore (lit zone click), the choice's pendingTargets fills.
  // For MTG multi-target this means we have everything we need to fire
  // onCastMultiTargetSpell. Also clears the local context when the
  // choice is cancelled (activeChoiceId goes null) without completing.
  useEffect(() => {
    if (!multiTargetContext) return;
    if (!activeChoiceId) {
      // Choice was cleared (Cancel pill or other), abandon cast.
      setMultiTargetContext(null);
      return;
    }
    if (pendingTargets.length >= 1) {
      // Got the second target — recover the raw id from the zone prefix.
      // Same prefix the primeFromChoice call used above.
      const prefix = multiTargetContext.secondIsPlayer ? 'mtg-player-' : 'mtg-card-';
      const rawSecondTarget = pendingTargets[0].startsWith(prefix)
        ? pendingTargets[0].slice(prefix.length)
        : pendingTargets[0];
      onCastMultiTargetSpell?.(
        multiTargetContext.cardId,
        [[multiTargetContext.firstTarget], [rawSecondTarget]],
      );
      useCardZoneStore.getState().clearChoice();
      setMultiTargetContext(null);
    }
  }, [activeChoiceId, pendingTargets, multiTargetContext, onCastMultiTargetSpell]);

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

      {/* Multi-Target Modal removed in PR A1. Second-target selection now
          goes through cardZoneStore: the spell drops on the first target,
          cardZoneStore is primed with second-target candidates, lit zones
          show on the board, and the overlay pill in ChoiceModal handles
          progress + Confirm + Cancel. Auto-confirm at max fires the cast. */}
    </div>
  );
}

export default GameBoard;
