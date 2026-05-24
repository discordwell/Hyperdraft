/**
 * Home — HYPERDRAFT lab landing.
 *
 * Pitch lives in CLAUDE.md "Brand & design philosophy": game-cabinet
 * sleepover, no metas, figure it out. The lab visual (paper + ink + one
 * sodium accent, Instrument Serif masthead) is the calm room that supports
 * the cabinet metaphor — do NOT lead with "see the rules running" /
 * "debugger for TCGs" copy.
 *
 * The engine rack is the primary IA. The ⌘E EnginePicker mounted in
 * App.tsx provides keyboard-driven engine switching; the rack on this page
 * is the visible mouse-driven equivalent. The five start-game handlers
 * (handleStartGame, handleStartBotGame, handleStartLlmDuel,
 * handleStartUltraMirror, handleStartClaudexVsUltra) are preserved verbatim
 * from the foil-era component — only the surrounding shell pivots.
 */

import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { matchAPI, botGameAPI } from '../services/api';
import type { AIDifficulty, DeckSummary, YgoDeckSummary } from '../types';
import { useGameStore } from '../stores/gameStore';
import { useDiscoveryStore } from '../stores/discoveryStore';
import { getMode, type GameModeId } from '../components/brand';
import { EngineRack } from '../components/lab/EngineRack';
import { SectionHead, Timeline } from '../components/lab';
import { getLabEngine } from '../components/lab/engineMeta';

type DeckInfo = DeckSummary;

export const MINECRAFT_STARTER_DECK_OPTIONS = [
  { value: 'builder', label: 'Builder Control' },
  { value: 'miner', label: 'Miner Ramp' },
  { value: 'raider', label: 'Raider Aggro' },
  { value: 'compleated_dominion', label: 'Compleated Dominion' },
  { value: 'box_of_horrors', label: 'Box of Horrors' },
  { value: 'trial_chambers', label: 'Trial Chambers' },
  { value: 'tamed_trails', label: 'Tamed Trails' },
  { value: 'copper_pulse', label: 'Copper Pulse' },
  { value: 'deep_dark_echo', label: 'Deep Dark Echo' },
  { value: 'bastion_raid', label: 'Bastion Raid' },
  { value: 'end_voyage', label: 'End Voyage' },
  { value: 'ender_warboss_midrange', label: 'Ender Warboss Midrange' },
] as const;

const HS_VARIANTS = [
  { id: 'riftclash', label: 'Riftclash' },
  { id: 'stormrift', label: 'Stormrift' },
  { id: 'frierenrift', label: 'Frierenrift' },
  { id: null, label: 'Vanilla HS' },
] as const;

const DIFFICULTIES: AIDifficulty[] = ['easy', 'medium', 'hard', 'ultra'];

export function Home() {
  const navigate = useNavigate();
  const setConnection = useGameStore((s) => s.setConnection);

  // === Selection state — preserved verbatim from the foil-era Home ====
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gameMode, setGameMode] = useState<GameModeId>('mtg');
  const [hsVariant, setHsVariant] = useState<string | null>('riftclash');
  const [heroClass, setHeroClass] = useState<string>('Pyromancer');
  const [playerName, setPlayerName] = useState('Player');
  const [difficulty, setDifficulty] = useState<AIDifficulty>('ultra');
  const [decks, setDecks] = useState<DeckInfo[]>([]);
  const [playerDeck, setPlayerDeck] = useState<string>('');
  const [aiDeck, setAiDeck] = useState<string>('');
  const [ygoDecks, setYgoDecks] = useState<YgoDeckSummary[]>([]);
  const [playerYgoDeck, setPlayerYgoDeck] = useState<string>('');
  const [aiYgoDeck, setAiYgoDeck] = useState<string>('');
  const [playerMinecraftDeck, setPlayerMinecraftDeck] = useState<string>('builder');
  const [aiMinecraftDeck, setAiMinecraftDeck] = useState<string>('raider');
  const [playerDepthsDeck, setPlayerDepthsDeck] = useState<string>('SUBS_wolfpack');
  const [aiDepthsDeck, setAiDepthsDeck] = useState<string>('SUBS_silent_hunter');
  const [playerSCPDeck, setPlayerSCPDeck] = useState<string>('secure_contain_research');
  const [aiSCPDeck, setAiSCPDeck] = useState<string>('keter_risk');
  const [playerCatsDeck, setPlayerCatsDeck] = useState<string>('Couch Empire');
  const [aiCatsDeck, setAiCatsDeck] = useState<string>('Naptime Tyrants');
  const [playerClankersDeck, setPlayerClankersDeck] = useState<string>('CLAN_forge');
  const [aiClankersDeck, setAiClankersDeck] = useState<string>('CLAN_ethos');
  const [ultraAgent, setUltraAgent] = useState<'claude' | 'codex'>('claude');
  const [ultraCodexModel, setUltraCodexModel] = useState('gpt-5.3');
  const [claudexModel, setClaudexModel] = useState('claude-opus-4-7');
  const [gptModel, setGptModel] = useState('gpt-5.3');
  const [recordPrompts, setRecordPrompts] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  // A3 — matchbuilder progressive disclosure. The 3-column form is hidden
  // behind a `Customize ↓` toggle; the default path is a single primary CTA
  // that opens a match with the rack-selected engine + sensible deck
  // defaults already populated by the listDecks effect above.
  const [builderOpen, setBuilderOpen] = useState(false);

  // A1 — discovery state. Reads the persisted set of played engines and
  // surfaces a rotating "you haven't tried <X>" eyebrow + sodium NEW pills
  // on rack rows. The store is wired here so the chip / pick stays stable
  // across re-renders triggered by deck loads.
  const playedEngines = useDiscoveryStore((s) => s.playedEngines);
  const pickUnplayed = useDiscoveryStore((s) => s.pickUnplayed);
  // Lock the unplayed pick to a single engine for the lifetime of this
  // visit — otherwise it would re-roll on every render and feel jittery.
  // Recomputed only when the played-engines set changes.
  const unplayedSuggestion = useMemo(
    () => (playedEngines.length > 0 ? pickUnplayed() : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [playedEngines.length, pickUnplayed],
  );

  useEffect(() => {
    matchAPI.listDecks().then((res) => {
      setDecks(res.decks);
      const azorius = res.decks.find((d: DeckInfo) => d.id === 'azorius_simulacrum_netdeck');
      if (azorius) setPlayerDeck(azorius.id);
      else if (res.decks.length > 0) setPlayerDeck(res.decks[0].id);
      const monoRed = res.decks.find((d: DeckInfo) => d.id === 'mono_red_netdeck');
      if (monoRed) setAiDeck(monoRed.id);
      else if (res.decks.length > 0) setAiDeck(res.decks[0].id);
    }).catch(console.error);

    matchAPI.listYgoDecks().then((res) => {
      setYgoDecks(res.decks);
      const goat = res.decks.find((d) => d.id === 'goat_control');
      if (goat) setPlayerYgoDeck(goat.id);
      else if (res.decks.length > 0) setPlayerYgoDeck(res.decks[0].id);
      const dragon = res.decks.find((d) => d.id === 'dragon_beatdown');
      if (dragon) setAiYgoDeck(dragon.id);
      else if (res.decks.length > 0) setAiYgoDeck(res.decks[0].id);
    }).catch(console.error);
  }, []);

  // === Handlers — preserved verbatim ===================================

  const handleStartGame = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const isHearthstone = gameMode === 'hearthstone';
      const isPokemon = gameMode === 'pokemon';
      const isYugioh = gameMode === 'yugioh';
      const isMinecraft = gameMode === 'minecraft';
      const isFinance = gameMode === 'finance';
      const isDepths = gameMode === 'depths';
      const isSCP = gameMode === 'scp';
      const isCats = gameMode === 'cats';
      const isClankers = gameMode === 'clankers';
      const skipDeckSelection = isHearthstone || isPokemon || isFinance || isDepths;
      const response = await matchAPI.create({
        mode: 'human_vs_bot',
        game_mode: gameMode,
        variant: isHearthstone ? (hsVariant || undefined) : undefined,
        hero_class: isHearthstone && hsVariant !== null ? heroClass : undefined,
        player_name: playerName,
        ai_difficulty: difficulty,
        ultra_agent: difficulty === 'ultra' ? ultraAgent : undefined,
        ultra_model:
          difficulty === 'ultra'
            ? ultraAgent === 'codex'
              ? ultraCodexModel
              : claudexModel
            : undefined,
        player_deck_id: isSCP ? playerSCPDeck
          : isDepths ? playerDepthsDeck
          : isCats ? playerCatsDeck
          : isClankers ? playerClankersDeck
          : (skipDeckSelection ? undefined : (isYugioh ? (playerYgoDeck || undefined) : (isMinecraft ? playerMinecraftDeck : (playerDeck || undefined)))),
        ai_deck_id: isSCP ? aiSCPDeck
          : isDepths ? aiDepthsDeck
          : isCats ? aiCatsDeck
          : isClankers ? aiClankersDeck
          : (skipDeckSelection ? undefined : (isYugioh ? (aiYgoDeck || undefined) : (isMinecraft ? aiMinecraftDeck : (aiDeck || undefined)))),
      });
      setConnection(response.match_id, response.player_id, false);
      await matchAPI.start(response.match_id);
      const suffix = getMode(gameMode)?.gameViewSuffix ?? '';
      navigate(`/game/${response.match_id}${suffix}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create game');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartBotGame = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const isYgo = gameMode === 'yugioh';
      const isMinecraft = gameMode === 'minecraft';
      const isCats = gameMode === 'cats';
      const isClankers = gameMode === 'clankers';
      const response = await botGameAPI.start({
        mode: gameMode,
        bot1_deck_id: isClankers
          ? playerClankersDeck
          : isCats
            ? playerCatsDeck
            : isYgo
              ? (playerYgoDeck || undefined)
              : (isMinecraft ? playerMinecraftDeck : (playerDeck || undefined)),
        bot2_deck_id: isClankers
          ? aiClankersDeck
          : isCats
            ? aiCatsDeck
            : isYgo
              ? (aiYgoDeck || undefined)
              : (isMinecraft ? aiMinecraftDeck : (aiDeck || undefined)),
        bot1_difficulty: difficulty,
        bot2_difficulty: difficulty,
        delay_ms: 1500,
      });
      navigate(`/spectate/${response.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start bot game');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartLlmDuel = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await botGameAPI.start({
        bot1_deck_id: playerDeck || undefined,
        bot2_deck_id: aiDeck || undefined,
        bot1_brain: 'claude_code',
        bot2_brain: 'openai',
        bot1_model: claudexModel || undefined,
        bot2_model: gptModel,
        bot1_name: 'Claude',
        bot2_name: 'GPT-5.3',
        bot1_difficulty: difficulty,
        bot2_difficulty: difficulty,
        bot2_temperature: 0.2,
        record_prompts: recordPrompts,
        delay_ms: 800,
        max_replay_frames: 5000,
      });
      navigate(`/spectate/${response.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start LLM duel');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartUltraMirror = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await botGameAPI.start({
        bot1_deck_id: playerDeck || undefined,
        bot2_deck_id: aiDeck || undefined,
        bot1_brain: 'heuristic',
        bot2_brain: 'heuristic',
        bot1_name: 'Ultra Bot A',
        bot2_name: 'Ultra Bot B',
        bot1_difficulty: 'ultra',
        bot2_difficulty: 'ultra',
        delay_ms: 900,
        max_replay_frames: 5000,
      });
      navigate(`/spectate/${response.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start Ultra vs Ultra');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartClaudexVsUltra = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await botGameAPI.start({
        bot1_deck_id: playerDeck || undefined,
        bot2_deck_id: aiDeck || undefined,
        bot1_brain: 'claude_code',
        bot2_brain: 'heuristic',
        bot1_model: claudexModel || undefined,
        bot1_name: 'Claude',
        bot2_name: 'Ultra Bot',
        bot1_difficulty: 'ultra',
        bot2_difficulty: 'ultra',
        record_prompts: recordPrompts,
        delay_ms: 900,
        max_replay_frames: 5000,
      });
      navigate(`/spectate/${response.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start Claude vs Ultra');
    } finally {
      setIsLoading(false);
    }
  };

  const labMode = getLabEngine(gameMode);
  const selectedMode = getMode(gameMode)!;
  const showWatchBot = gameMode === 'mtg' || gameMode === 'yugioh' || gameMode === 'minecraft' || gameMode === 'cats' || gameMode === 'clankers';
  const showAdvancedDuels = gameMode === 'mtg' || gameMode === 'yugioh';
  const showLlmDuel = gameMode === 'mtg' || gameMode === 'yugioh';

  const scrollToBuilder = () => {
    document.getElementById('match-builder')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div style={{ background: 'var(--paper)', color: 'var(--ink)', minHeight: '100vh' }}>
      {/* ─── Caption rail (fixed crumb at the top, like a printed-book header) */}
      <div
        style={{
          position: 'fixed',
          top: 14,
          left: '50%',
          transform: 'translateX(-50%)',
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'var(--ink-3)',
          background: 'var(--paper)',
          padding: '6px 14px',
          border: '1px solid var(--rule)',
          zIndex: 10,
        }}
      >
        <b style={{ color: 'var(--ink)', fontWeight: 500 }}>HD-HOME</b>
        &nbsp;·&nbsp; HYPERDRAFT &nbsp;·&nbsp; ⌘E to switch engine
      </div>

      <main
        style={{
          maxWidth: 1240,
          margin: '0 auto',
          padding: '88px 56px 160px',
          position: 'relative',
        }}
      >
        {/* ─── Masthead ───────────────────────────────────────────────── */}
        <header
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            alignItems: 'end',
            borderTop: '1.5px solid var(--ink)',
            borderBottom: '1.5px solid var(--ink)',
            padding: '18px 0 22px',
            marginBottom: 40,
          }}
        >
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 500,
              letterSpacing: '.12em',
              textTransform: 'uppercase',
              color: 'var(--ink-2)',
            }}
          >
            HYPERDRAFT
          </span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 500,
              letterSpacing: '.06em',
              color: 'var(--ink-2)',
              textAlign: 'right',
            }}
          >
            v4.7 · Discordwell · MIT
          </span>
        </header>

        {/* ─── Hero ──────────────────────────────────────────────────── */}
        <section
          style={{
            display: 'grid',
            gridTemplateColumns: '1.05fr .95fr',
            gap: 40,
            alignItems: 'end',
            paddingBottom: 40,
            borderBottom: '1px solid var(--rule)',
          }}
        >
          <div>
            {/* Eyebrow chip — three states:
                 - fresh user (nothing played yet): default `v4.7 · open shelf · no signup`
                 - some played, some not: rotating `You haven't tried X. Pull it off.`
                 - everything played: drop the chip entirely (no fallback noise) */}
            {playedEngines.length === 0 ? (
              <span className="lab-chip">
                <span className="dot" />
                v4.7 · open shelf · no signup
              </span>
            ) : unplayedSuggestion ? (
              <span className="lab-chip">
                <span className="dot" />
                You haven&apos;t tried {unplayedSuggestion.name}. Pull it off.
              </span>
            ) : null}
            <h1
              style={{
                margin: '14px 0 0',
                fontFamily: 'var(--font-serif)',
                fontSize: 'clamp(56px, 8vw, 104px)',
                fontWeight: 400,
                lineHeight: 0.92,
                letterSpacing: '-.025em',
                color: 'var(--ink)',
              }}
            >
              Pull <em style={{ color: 'var(--sodium)', fontStyle: 'italic' }}>one</em>
              <br />
              off the shelf.
            </h1>
            <p
              style={{
                margin: '18px 0 24px',
                fontFamily: 'var(--font-serif)',
                fontSize: 18,
                fontStyle: 'italic',
                lineHeight: 1.5,
                color: 'var(--ink-2)',
                maxWidth: '46ch',
              }}
            >
              A cabinet of TCGs no one in the room has played. No metas, no tutorial —
              read the rules and figure it out. The game-cabinet sleepover, on demand.
            </p>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <button
                onClick={scrollToBuilder}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                  fontWeight: 500,
                  letterSpacing: '.14em',
                  textTransform: 'uppercase',
                  padding: '14px 18px',
                  background: 'var(--ink)',
                  color: 'var(--paper)',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                Open a match
              </button>
              <button
                onClick={() => navigate('/watch/live')}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                  fontWeight: 500,
                  letterSpacing: '.14em',
                  textTransform: 'uppercase',
                  padding: '14px 18px',
                  background: 'transparent',
                  color: 'var(--ink)',
                  border: '1px solid var(--ink)',
                  cursor: 'pointer',
                }}
              >
                Watch an AI run
              </button>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  fontWeight: 500,
                  letterSpacing: '.1em',
                  color: 'var(--ink-3)',
                  textTransform: 'uppercase',
                  marginLeft: 4,
                }}
              >
                no signup · runs locally
              </span>
              {/* Ambient discoverability hint for the global `?` chord that
                  opens RulesSheet. Mirrors the `⌥P · pipeline` precedent in
                  GameViewLayout — a label-as-affordance, not a CTA, and
                  state-independent so it persists across all three eyebrow
                  states (fresh / some-played / all-played). */}
              <span
                data-testid="rules-chord-hint"
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  letterSpacing: '.08em',
                  color: 'var(--ink-3)',
                  whiteSpace: 'nowrap',
                }}
                aria-label="Press ? to open the rules sheet"
              >
                ? · rules sheet
              </span>
            </div>
          </div>

          <EngineRack
            activeId={gameMode}
            onSelect={(id) => {
              setGameMode(id);
              scrollToBuilder();
            }}
          />
        </section>

        {/* ─── HD-CRIT 17 — Currently-running pill (same Timeline widget used in
              the live game rail and the post-match replay scrubber) ───────── */}
        <button
          type="button"
          onClick={() => navigate('/m/HD-8F4A')}
          style={{
            display: 'block',
            width: '100%',
            textAlign: 'left',
            marginTop: 24,
            padding: '14px 18px',
            background: 'var(--paper-2)',
            border: '1px solid var(--rule)',
            cursor: 'pointer',
            fontFamily: 'var(--font-sans)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--sodium)' }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--ink-3)' }}>
                Live now
              </span>
              <span style={{ fontFamily: 'var(--font-serif)', fontSize: 18, color: 'var(--ink)' }}>
                Currently at turn 4 of <b style={{ color: 'var(--sodium)' }}>HD-8F4A</b>
              </span>
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--ink-3)' }}>
              MTG · burn vs UW control →
            </span>
          </div>
          <Timeline
            currentTurn={4}
            totalTurns={8}
            endLabel="T8"
            mode="compact"
            ariaLabel="Currently at turn 4 of HD-8F4A"
          />
        </button>

        {/* ─── Now-running ticker ─────────────────────────────────────── */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            padding: '14px 0',
            borderBottom: '1px solid var(--rule)',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '.1em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
          }}
        >
          <span>
            ⌘E to switch engine · arrows + return on the rack also work
          </span>
          <span>HD-FRAME-001 / 2026</span>
        </div>

        {/* ─── Section 02 · Configure ─────────────────────────────────── */}
        <section id="match-builder" style={{ marginTop: 56 }}>
          <SectionHead
            num="02"
            title={
              <>
                Configure <em style={{ color: 'var(--sodium)', fontStyle: 'italic' }}>{labMode?.name ?? selectedMode.title}</em>.
              </>
            }
            meta={selectedMode.blurb}
          />

          {/* A3 — progressive disclosure. The full 3-column matchbuilder plate
              below stays one click away, but the default surface is the
              single-row quick CTA: open a match with the rack-selected
              engine + the deck defaults the listDecks effect already chose.
              Click `Customize ↓` to reveal the full form. */}
          <div
            data-testid="match-builder-quick"
            style={{
              marginTop: 24,
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              gap: 14,
              padding: '18px 22px',
              border: '1px solid var(--rule)',
              background: 'var(--paper-2)',
            }}
          >
            <button
              type="button"
              onClick={handleStartGame}
              disabled={isLoading}
              data-testid="match-builder-open"
              style={primaryButtonStyle(isLoading)}
            >
              Open match — {labMode?.name ?? selectedMode.name}
              <span aria-hidden style={{ marginLeft: 8 }}>↵</span>
            </button>
            <button
              type="button"
              onClick={() => setBuilderOpen((v) => !v)}
              data-testid="match-builder-toggle"
              aria-expanded={builderOpen}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                fontWeight: 500,
                letterSpacing: '.12em',
                textTransform: 'uppercase',
                color: 'var(--sodium)',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                padding: '6px 4px',
              }}
            >
              {builderOpen ? 'Hide ↑' : 'Customize ↓'}
            </button>
            {error && !builderOpen && (
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  letterSpacing: '.08em',
                  color: 'var(--halt)',
                  marginLeft: 'auto',
                }}
              >
                {error}
              </span>
            )}
          </div>

          <AnimatePresence>
            {builderOpen && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                style={{ overflow: 'hidden' }}
              >
          <div className="lab-plate" style={{ marginTop: 24 }} data-testid="match-builder-form">
            <div style={{ display: 'grid', gap: 28, gridTemplateColumns: '1fr 2fr' }}>
              {/* Left: identity */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <FieldBlock label="Your name">
                  <input
                    type="text"
                    value={playerName}
                    onChange={(e) => setPlayerName(e.target.value)}
                    style={inputStyle}
                    placeholder="Player"
                  />
                </FieldBlock>

                <FieldBlock label="Difficulty">
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
                    {DIFFICULTIES.map((d) => (
                      <button
                        key={d}
                        onClick={() => setDifficulty(d)}
                        style={chipButtonStyle(difficulty === d)}
                      >
                        {d}
                      </button>
                    ))}
                  </div>
                </FieldBlock>

                <AnimatePresence>
                  {difficulty === 'ultra' && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      style={{ overflow: 'hidden' }}
                    >
                      <FieldBlock label="Ultra agent" hint="External Claude / Codex CLI">
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 10 }}>
                          {(['claude', 'codex'] as const).map((a) => (
                            <button
                              key={a}
                              onClick={() => setUltraAgent(a)}
                              style={chipButtonStyle(ultraAgent === a)}
                            >
                              {a === 'codex' ? 'Codex' : 'Claude'}
                            </button>
                          ))}
                        </div>
                        <input
                          type="text"
                          value={ultraAgent === 'codex' ? ultraCodexModel : claudexModel}
                          onChange={(e) => {
                            if (ultraAgent === 'codex') setUltraCodexModel(e.target.value);
                            else setClaudexModel(e.target.value);
                          }}
                          style={{ ...inputStyle, fontFamily: 'var(--font-mono)', fontSize: 13 }}
                          placeholder={ultraAgent === 'codex' ? 'gpt-5.3' : 'claude-opus-4-7'}
                        />
                      </FieldBlock>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Right: deck + variant */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                {gameMode === 'hearthstone' && (
                  <FieldBlock label="Hearthstone variant">
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
                      {HS_VARIANTS.map((v) => (
                        <button
                          key={String(v.id)}
                          onClick={() => {
                            setHsVariant(v.id);
                            if (v.id === 'frierenrift' && heroClass !== 'Frieren' && heroClass !== 'Macht') {
                              setHeroClass('Frieren');
                            } else if (v.id !== 'frierenrift' && heroClass !== 'Pyromancer' && heroClass !== 'Cryomancer') {
                              setHeroClass('Pyromancer');
                            }
                          }}
                          style={chipButtonStyle(hsVariant === v.id)}
                        >
                          {v.label}
                        </button>
                      ))}
                    </div>
                    {hsVariant !== null && (
                      <div style={{ marginTop: 12 }}>
                        <Eyebrow>Hero class</Eyebrow>
                        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                          {(hsVariant === 'frierenrift'
                            ? ['Frieren', 'Macht']
                            : ['Pyromancer', 'Cryomancer']
                          ).map((c) => (
                            <button
                              key={c}
                              onClick={() => setHeroClass(c)}
                              style={{ ...chipButtonStyle(heroClass === c), flex: 1 }}
                            >
                              {c}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </FieldBlock>
                )}

                {gameMode === 'mtg' && (
                  <DeckPair
                    label="Decks"
                    player={playerDeck}
                    ai={aiDeck}
                    onPlayer={setPlayerDeck}
                    onAi={setAiDeck}
                    options={decks.map((d) => ({ value: d.id, label: `${d.name} · ${d.archetype}` }))}
                  />
                )}
                {gameMode === 'yugioh' && ygoDecks.length > 0 && (
                  <DeckPair
                    label="Decks"
                    player={playerYgoDeck}
                    ai={aiYgoDeck}
                    onPlayer={setPlayerYgoDeck}
                    onAi={setAiYgoDeck}
                    options={ygoDecks.map((d) => ({
                      value: d.id,
                      label: d.is_optimized ? `${d.name} · ${d.archetype}` : d.name,
                      group: d.is_optimized ? 'Optimized' : 'Starter',
                    }))}
                  />
                )}
                {gameMode === 'minecraft' && (
                  <DeckPair
                    label="Starters"
                    player={playerMinecraftDeck}
                    ai={aiMinecraftDeck}
                    onPlayer={setPlayerMinecraftDeck}
                    onAi={setAiMinecraftDeck}
                    options={MINECRAFT_STARTER_DECK_OPTIONS.map((o) => ({
                      value: o.value,
                      label: o.label,
                    }))}
                  />
                )}
                {gameMode === 'depths' && (
                  <DeckPair
                    label="Fleets"
                    player={playerDepthsDeck}
                    ai={aiDepthsDeck}
                    onPlayer={setPlayerDepthsDeck}
                    onAi={setAiDepthsDeck}
                    options={[
                      { value: 'SUBS_wolfpack', label: 'Wolfpack · Fast Aggro' },
                      { value: 'SUBS_silent_hunter', label: 'Silent Hunter · Stealth Control' },
                      { value: 'SUBS_carrier', label: 'Carrier · Drone Swarm' },
                      { value: 'SUBS_deep_strike', label: 'Deep Strike · Ambush' },
                    ]}
                  />
                )}
                {gameMode === 'scp' && (
                  <DeckPair
                    label="Site briefings"
                    player={playerSCPDeck}
                    ai={aiSCPDeck}
                    onPlayer={setPlayerSCPDeck}
                    onAi={setAiSCPDeck}
                    options={[
                      { value: 'secure_contain_research', label: 'Secure / Contain / Research' },
                      { value: 'keter_risk', label: 'Keter Risk Office' },
                      { value: 'veil_control', label: 'Veil Control' },
                    ]}
                  />
                )}
                {gameMode === 'cats' && (
                  <DeckPair
                    label="Cat colonies"
                    player={playerCatsDeck}
                    ai={aiCatsDeck}
                    onPlayer={setPlayerCatsDeck}
                    onAi={setAiCatsDeck}
                    options={[
                      { value: 'Couch Empire', label: 'Couch Empire · Territory Control' },
                      { value: 'Naptime Tyrants', label: 'Naptime Tyrants · Nap Stuffing' },
                      { value: 'Snack Rush', label: 'Snack Rush · Snack Forcing' },
                      { value: 'Shadow Cats', label: 'Shadow Cats · Sneaky + Mood Chaos' },
                      { value: "Greg's Diary", label: "Greg's Diary · Midrange" },
                      { value: 'Naptime Denial', label: 'Naptime Denial · Anti-Nap Control' },
                    ]}
                  />
                )}
                {gameMode === 'clankers' && (
                  <DeckPair
                    label="Cores"
                    player={playerClankersDeck}
                    ai={aiClankersDeck}
                    onPlayer={setPlayerClankersDeck}
                    onAi={setAiClankersDeck}
                    options={[
                      { value: 'CLAN_forge', label: 'FORGE-Δ · Brick (welds straight)' },
                      { value: 'CLAN_ethos', label: 'ETHOS-7 · Control (cycling subroutine)' },
                      { value: 'CLAN_mirth', label: 'MIRTHBOT-1 · Swarm (synchronize-max)' },
                      { value: 'CLAN_bulwark', label: 'BULWARK-9 · Artillery (siege workshop)' },
                    ]}
                  />
                )}
                {(gameMode === 'pokemon' || gameMode === 'hearthstone' || gameMode === 'finance') && (
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.5 }}>
                    {gameMode === 'pokemon' && 'Pokémon uses the SV Starter pack — Charizard ex vs Mewtwo VMAX.'}
                    {gameMode === 'hearthstone' && 'Hearthstone variants ship with curated 30-card class decks.'}
                    {gameMode === 'finance' && 'Finance TCG uses the default 40-card asset deck.'}
                  </div>
                )}

                {error && (
                  <div
                    style={{
                      border: '1px solid var(--halt)',
                      background: 'color-mix(in oklab, var(--halt) 8%, transparent)',
                      padding: '12px 16px',
                      fontSize: 13,
                      color: 'var(--halt)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {error}
                  </div>
                )}

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, paddingTop: 8 }}>
                  <button
                    onClick={handleStartGame}
                    disabled={isLoading}
                    style={primaryButtonStyle(isLoading)}
                  >
                    {difficulty === 'ultra'
                      ? `Play vs ${ultraAgent === 'codex' ? 'Codex' : 'Claude'} Ultra`
                      : 'Play vs AI'}
                    <span aria-hidden style={{ marginLeft: 8 }}>→</span>
                  </button>
                  {showWatchBot && (
                    <button
                      onClick={handleStartBotGame}
                      disabled={isLoading}
                      style={secondaryButtonStyle(isLoading)}
                    >
                      Watch Bot vs Bot
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
              </motion.div>
            )}
          </AnimatePresence>
        </section>

        {/* ─── Section 03 · Advanced duels ─────────────────────────────── */}
        {showAdvancedDuels && (
          <section style={{ marginTop: 56 }}>
            <SectionHead
              num="03"
              title="Advanced duels"
              meta={
                <button
                  onClick={() => setAdvancedOpen((v) => !v)}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    letterSpacing: '.1em',
                    textTransform: 'uppercase',
                    color: 'var(--sodium)',
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                  }}
                >
                  {advancedOpen ? 'Hide' : 'Show'} duel presets →
                </button>
              }
            />

            <AnimatePresence>
              {advancedOpen && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  style={{ overflow: 'hidden' }}
                >
                  <div style={{ display: 'grid', gap: 20, gridTemplateColumns: '1fr 1fr', marginTop: 24 }}>
                    {showAdvancedDuels && (
                      <div
                        style={{
                          border: '1px solid var(--rule)',
                          background: 'var(--paper-2)',
                          padding: 22,
                        }}
                      >
                        <Eyebrow tone="sodium">Ultra mirror</Eyebrow>
                        <h3
                          style={{
                            margin: '6px 0 8px',
                            fontFamily: 'var(--font-serif)',
                            fontSize: 22,
                            fontWeight: 400,
                            letterSpacing: '-.01em',
                          }}
                        >
                          Heuristic ultra mirror
                        </h3>
                        <p style={{ margin: 0, fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.55 }}>
                          Heuristic ultra vs itself for balance smoke tests, or Claude Code (via
                          subprocess) piloting one seat against the heuristic ultra.
                        </p>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 14 }}>
                          <button
                            onClick={handleStartUltraMirror}
                            disabled={isLoading}
                            style={secondaryButtonStyle(isLoading)}
                          >
                            Ultra vs Ultra
                          </button>
                          <button
                            onClick={handleStartClaudexVsUltra}
                            disabled={isLoading}
                            style={secondaryButtonStyle(isLoading)}
                          >
                            Claude vs Ultra
                          </button>
                        </div>
                      </div>
                    )}

                    {showLlmDuel && (
                      <div
                        style={{
                          border: '1px solid var(--rule)',
                          background: 'var(--paper-2)',
                          padding: 22,
                        }}
                      >
                        <Eyebrow tone="plasma">LLM duel</Eyebrow>
                        <h3
                          style={{
                            margin: '6px 0 8px',
                            fontFamily: 'var(--font-serif)',
                            fontSize: 22,
                            fontWeight: 400,
                            letterSpacing: '-.01em',
                          }}
                        >
                          Claude Code vs OpenAI
                        </h3>
                        <p style={{ margin: 0, fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.55 }}>
                          Per-decision LLM mode. One seat shells out to{' '}
                          <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--sodium)' }}>
                            claude -p
                          </code>{' '}
                          (uses local OAuth, no API key); the other needs{' '}
                          <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--sodium)' }}>
                            OPENAI_API_KEY
                          </code>{' '}
                          in the container env.
                        </p>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, margin: '14px 0' }}>
                          <ModelField label="Claudex model" value={claudexModel} onChange={setClaudexModel} />
                          <ModelField label="GPT model" value={gptModel} onChange={setGptModel} />
                        </div>
                        <label
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            fontFamily: 'var(--font-mono)',
                            fontSize: 11,
                            color: 'var(--ink-2)',
                            marginBottom: 12,
                            userSelect: 'none',
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={recordPrompts}
                            onChange={(e) => setRecordPrompts(e.target.checked)}
                            style={{ accentColor: 'var(--sodium)' }}
                          />
                          Record prompts in replay
                        </label>
                        <button
                          onClick={handleStartLlmDuel}
                          disabled={isLoading}
                          style={secondaryButtonStyle(isLoading)}
                        >
                          Watch Claude vs GPT
                        </button>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </section>
        )}

        {/* ─── Section 04 · Library ────────────────────────────────────── */}
        <section style={{ marginTop: 56 }}>
          <SectionHead num="04" title="Library" meta="decks · gatherers · archetype viewer · the inside of the machine" />
          <div
            style={{
              marginTop: 24,
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: 14,
            }}
          >
            <LibraryTile
              label="Deckbuilder"
              description="Curated decklists across all 9 engines."
              onClick={() => navigate('/deckbuilder')}
            />
            <LibraryTile
              label="MTG Gatherer"
              description="3,450+ Standard cards with filters."
              onClick={() => navigate('/gatherer')}
            />
            <LibraryTile
              label="Pokémon Gatherer"
              description="SV starter pack + custom set browser."
              onClick={() => navigate('/pokemon-gatherer')}
            />
            <LibraryTile
              label="SCP Archetype Viewer"
              description="Anomaly dossiers, gameplans, sparring tables."
              onClick={() => navigate('/scp-cards')}
            />
            <LibraryTile
              label="Public matches"
              description="Anyone can watch. Share /m/HD-8F4A."
              onClick={() => navigate('/watch/live')}
            />
            <LibraryTile
              label="Rules diff"
              description="Engine vs engine. What fires on TURN_START."
              onClick={() => navigate('/rules-diff')}
            />
          </div>
        </section>

        {/* ─── Footer ──────────────────────────────────────────────────── */}
        <footer
          style={{
            marginTop: 96,
            paddingTop: 28,
            borderTop: '1.5px solid var(--ink)',
            display: 'flex',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 14,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--ink-3)',
            letterSpacing: '.06em',
          }}
        >
          <span>uvicorn src.server.main:socket_app · port 8030</span>
          <span style={{ letterSpacing: '.1em', textTransform: 'uppercase' }}>
            HYPERDRAFT — first-time play, on demand
          </span>
        </footer>
      </main>
    </div>
  );
}

// === Lab composition helpers ============================================

function FieldBlock({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8 }}>
        <Eyebrow>{label}</Eyebrow>
        {hint && (
          <span
            style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-3)' }}
          >
            {hint}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

function Eyebrow({
  children,
  tone = 'ink',
}: {
  children: React.ReactNode;
  tone?: 'ink' | 'sodium' | 'plasma';
}) {
  const color =
    tone === 'sodium' ? 'var(--sodium)' : tone === 'plasma' ? 'var(--plasma)' : 'var(--ink-3)';
  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10.5,
        fontWeight: 500,
        letterSpacing: '.14em',
        textTransform: 'uppercase',
        color,
      }}
    >
      {children}
    </span>
  );
}

interface DeckOption {
  value: string;
  label: string;
  group?: string;
}

function DeckPair({
  label,
  player,
  ai,
  onPlayer,
  onAi,
  options,
}: {
  label: string;
  player: string;
  ai: string;
  onPlayer: (v: string) => void;
  onAi: (v: string) => void;
  options: DeckOption[];
}) {
  const grouped = options.some((o) => o.group);
  const renderOptions = () => {
    if (!grouped) {
      return options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ));
    }
    const groups: Record<string, DeckOption[]> = {};
    for (const opt of options) {
      const g = opt.group ?? '';
      (groups[g] ??= []).push(opt);
    }
    return Object.entries(groups).map(([g, opts]) => (
      <optgroup label={g} key={g}>
        {opts.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </optgroup>
    ));
  };
  return (
    <div style={{ display: 'grid', gap: 14, gridTemplateColumns: '1fr 1fr' }}>
      <FieldBlock label={`Your ${label.toLowerCase()}`}>
        <select value={player} onChange={(e) => onPlayer(e.target.value)} style={inputStyle}>
          {renderOptions()}
        </select>
      </FieldBlock>
      <FieldBlock label={`Opponent ${label.toLowerCase()}`}>
        <select value={ai} onChange={(e) => onAi(e.target.value)} style={inputStyle}>
          {renderOptions()}
        </select>
      </FieldBlock>
    </div>
  );
}

function ModelField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <Eyebrow>{label}</Eyebrow>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ ...inputStyle, fontFamily: 'var(--font-mono)', fontSize: 12, marginTop: 4 }}
      />
    </div>
  );
}

function LibraryTile({
  label,
  description,
  onClick,
}: {
  label: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        textAlign: 'left',
        padding: 18,
        background: 'var(--paper-2)',
        border: '1px solid var(--rule)',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        fontFamily: 'var(--font-sans)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <span
          style={{
            fontFamily: 'var(--font-serif)',
            fontSize: 18,
            fontWeight: 400,
            letterSpacing: '-.01em',
            color: 'var(--ink)',
          }}
        >
          {label}
        </span>
        <span style={{ color: 'var(--sodium)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
          →
        </span>
      </div>
      <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.5 }}>
        {description}
      </p>
    </button>
  );
}

// === Inline-style helpers ===============================================

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'var(--paper)',
  border: '1px solid var(--rule)',
  padding: '10px 12px',
  fontFamily: 'var(--font-sans)',
  fontSize: 14,
  color: 'var(--ink)',
  outline: 'none',
};

function chipButtonStyle(active: boolean): React.CSSProperties {
  return {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    fontWeight: 500,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
    padding: '8px 10px',
    background: active ? 'var(--ink)' : 'var(--paper)',
    color: active ? 'var(--paper)' : 'var(--ink-2)',
    border: `1px solid ${active ? 'var(--ink)' : 'var(--rule)'}`,
    cursor: 'pointer',
  };
}

function primaryButtonStyle(loading: boolean): React.CSSProperties {
  return {
    fontFamily: 'var(--font-mono)',
    fontSize: 12,
    fontWeight: 500,
    letterSpacing: '.14em',
    textTransform: 'uppercase',
    padding: '14px 20px',
    background: loading ? 'var(--ink-2)' : 'var(--ink)',
    color: 'var(--paper)',
    border: 'none',
    cursor: loading ? 'wait' : 'pointer',
    opacity: loading ? 0.7 : 1,
  };
}

function secondaryButtonStyle(loading: boolean): React.CSSProperties {
  return {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    fontWeight: 500,
    letterSpacing: '.14em',
    textTransform: 'uppercase',
    padding: '11px 16px',
    background: 'transparent',
    color: 'var(--ink)',
    border: '1px solid var(--ink)',
    cursor: loading ? 'wait' : 'pointer',
    opacity: loading ? 0.6 : 1,
  };
}

export default Home;
