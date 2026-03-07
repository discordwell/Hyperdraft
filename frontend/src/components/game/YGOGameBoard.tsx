/**
 * YGOGameBoard Component
 *
 * Yu-Gi-Oh! duel field with Dark + Gold theming, animations,
 * fan hand layout, card detail panel, turn banner, and attack UX.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { YGOCard } from './YGOCard';
import { YGOActionBar } from './YGOActionBar';
import YGOCardDetailPanel from './YGOCardDetailPanel';
import YGOTurnBanner from './YGOTurnBanner';
import YGOBanishedModal from './YGOBanishedModal';
import YGOExtraDeckModal from './YGOExtraDeckModal';
import { cardSummon, handStagger, modalBackdrop, modalContent, gameOverOverlay } from '../../utils/ygoAnimations';
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
  const [hoveredCard, setHoveredCard] = useState<CardData | null>(null);
  const [showTurnBanner, setShowTurnBanner] = useState(false);
  const [graveyardFilter, setGraveyardFilter] = useState<'all' | 'monster' | 'spell' | 'trap'>('all');

  // LP tracking for flash effects
  const prevMyLP = useRef(myPlayer?.lp ?? 8000);
  const prevOppLP = useRef(opponentPlayer?.lp ?? 8000);
  const [myLPDelta, setMyLPDelta] = useState<number | null>(null);
  const [oppLPDelta, setOppLPDelta] = useState<number | null>(null);

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
    if (!isMyTurn) return;
    setSelectedHandCard(prev => prev === card.id ? null : card.id);
    setSelectedFieldCard(null);
    setAttackMode(null);
  }, [isMyTurn]);

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

  const clearSelections = useCallback(() => {
    setSelectedHandCard(null);
    setSelectedFieldCard(null);
    setAttackMode(null);
  }, []);

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

  // Hand fan layout
  const handFanStyle = (index: number, total: number) => {
    if (total <= 1) return { rotate: 0, y: 0 };
    const center = (total - 1) / 2;
    const offset = index - center;
    const maxRotate = Math.min(total * 2, 15);
    const rotate = (offset / center) * maxRotate;
    const y = Math.abs(offset) * Math.min(total, 6);
    return { rotate, y };
  };

  // Zone slot render
  const renderZoneRow = (zones: (CardData | null)[], isMine: boolean, isMonsterZone: boolean) => (
    <div className="flex gap-2 justify-center">
      {Array.from({ length: 5 }).map((_, i) => {
        const card = zones[i] || null;
        return (
          <div
            key={i}
            className={`
              w-[76px] h-[106px] border border-dashed rounded-lg flex items-center justify-center
              ${isMonsterZone ? 'border-ygo-gold-dim/30' : 'border-teal-800/30'}
              ${!card ? 'bg-ygo-dark/40' : ''}
              ${attackMode && !isMine && card ? 'border-red-500/50 bg-red-950/20' : ''}
              transition-colors duration-200
            `}
            style={{ boxShadow: 'inset 0 2px 8px rgba(0,0,0,0.3)' }}
          >
            <AnimatePresence mode="popLayout">
              {card && (
                <motion.div
                  key={card.id}
                  variants={cardSummon}
                  initial="initial"
                  animate="animate"
                  exit="exit"
                >
                  <YGOCard
                    card={card}
                    size="sm"
                    onClick={() => handleFieldCardClick(card, isMine)}
                    selected={isMine && selectedFieldCard === card.id}
                    isTarget={attackMode !== null && !isMine}
                    isDefensePosition={card.ygo_position === 'face_up_def' || card.ygo_position === 'face_down_def'}
                    onHoverStart={() => !card.face_down && setHoveredCard(card)}
                    onHoverEnd={() => setHoveredCard(null)}
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );

  // LP display component
  const LPDisplay = ({ lp, delta, isPlayer }: { lp: number; delta: number | null; isPlayer: boolean }) => (
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

      {/* Card Detail Panel */}
      <YGOCardDetailPanel card={hoveredCard} />

      {/* Opponent info bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-ygo-dark/80 backdrop-blur-sm border-b border-ygo-gold-dim/20">
        <div className="flex items-center gap-3">
          <span className="text-sm text-ygo-gold-dim font-medium">{opponentPlayer?.name || 'Opponent'}</span>
          <LPDisplay lp={opponentPlayer?.lp ?? 8000} delta={oppLPDelta} isPlayer={false} />
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>Hand: {opponentPlayer?.hand_size ?? 0}</span>
          <span>Deck: {opponentPlayer?.library_size ?? 0}</span>
          <button onClick={() => setShowGraveyard('opp')} className="text-gray-400 hover:text-ygo-gold transition-colors">
            GY: {oppGraveyard.length}
          </button>
          {(oppBanished?.length || 0) > 0 && (
            <button onClick={() => setShowBanished('opp')} className="text-gray-500 hover:text-gray-300 transition-colors">
              Ban: {oppBanished.length}
            </button>
          )}
          {(oppExtraDeckSize || 0) > 0 && (
            <span className="text-purple-400">ED: {oppExtraDeckSize}</span>
          )}
        </div>
      </div>

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
          {renderZoneRow(oppSpellTrapZones, false, false)}
        </div>

        {/* Opponent monster row */}
        <div className="flex items-center gap-3">
          <div className="w-16" />
          {renderZoneRow(oppMonsterZones, false, true)}
        </div>

        {/* Gold center divider + Phase indicator */}
        <div className="flex items-center gap-4 py-1 w-full max-w-2xl px-4">
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-ygo-gold-dim/40 to-transparent" />
          <div className="flex gap-1">
            {PHASE_DISPLAY.map(phase => {
              const isActive = ygoPhase === phase || (phase === 'BATTLE_STEP' && isInBattlePhase(ygoPhase));
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
          {attackMode && (
            <button
              onClick={handleDirectAttackClick}
              className="px-3 py-1 bg-red-700 hover:bg-red-600 text-white text-xs font-bold rounded animate-pulse transition-colors"
            >
              Direct Attack
            </button>
          )}
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-ygo-gold-dim/40 to-transparent" />
        </div>

        {/* My monster row */}
        <div className="flex items-center gap-3">
          <div className="w-16" />
          {renderZoneRow(myMonsterZones, true, true)}
        </div>

        {/* My back row (spell/trap) */}
        <div className="flex items-center gap-3">
          {myFieldSpell ? (
            <YGOCard card={myFieldSpell} size="sm" onClick={() => {}} animate={false}
              onHoverStart={() => !myFieldSpell.face_down && setHoveredCard(myFieldSpell)}
              onHoverEnd={() => setHoveredCard(null)}
            />
          ) : (
            <div className="w-16 h-[88px] border border-dashed border-green-800/20 rounded-lg opacity-30" />
          )}
          {renderZoneRow(mySpellTrapZones, true, false)}
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
            {hand.map((card, index) => {
              const fan = handFanStyle(index, hand.length);
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
                  <YGOCard
                    card={card}
                    size="sm"
                    onClick={() => handleHandCardClick(card)}
                    selected={selectedHandCard === card.id}
                    animate={false}
                    onHoverStart={() => setHoveredCard(card)}
                    onHoverEnd={() => setHoveredCard(null)}
                  />
                </motion.div>
              );
            })}
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
