/**
 * Home — premium card-game landing + match builder.
 *
 * Phase A2 of the brand redesign. The 877-line mega-form was replaced by:
 *   1. Hero: wordmark + tagline + NowPlayingPill
 *   2. 8-mode tile grid (GameModeTile cycles via brand.modes.ts)
 *   3. Match Builder — progressively reveals deck / variant / difficulty /
 *      ultra-agent based on the selected mode
 *   4. Advanced duels (LLM duel, Ultra mirror) tucked into a disclosed panel
 *   5. Library shortcuts (Deckbuilder, Card gatherers, SCP viewer)
 *
 * All five original handlers (handleStartGame, handleStartBotGame,
 * handleStartLlmDuel, handleStartUltraMirror, handleStartClaudexVsUltra)
 * are preserved verbatim — only their call sites changed shape.
 */

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { matchAPI, botGameAPI } from '../services/api';
import type { AIDifficulty, DeckSummary, YgoDeckSummary } from '../types';
import { useGameStore } from '../stores/gameStore';
import {
  AppShell,
  Section,
  BrandButton,
  GameModeTile,
  Monogram,
  NowPlayingPill,
  GAME_MODES,
  getMode,
  type GameModeId,
} from '../components/brand';

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
  { id: 'riftclash', label: 'Riftclash', accent: 'bg-amber-600' },
  { id: 'stormrift', label: 'Stormrift', accent: 'bg-purple-600' },
  { id: 'frierenrift', label: 'Frierenrift', accent: 'bg-cyan-700' },
  { id: null, label: 'Vanilla HS', accent: 'bg-brand-foil' },
] as const;

const DIFFICULTIES: AIDifficulty[] = ['easy', 'medium', 'hard', 'ultra'];

export function Home() {
  const navigate = useNavigate();
  const setConnection = useGameStore((s) => s.setConnection);

  // === Selection state (mirrors original) =============================
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gameMode, setGameMode] = useState<GameModeId>('hearthstone');
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
  const [ultraAgent, setUltraAgent] = useState<'claude' | 'codex'>('claude');
  const [ultraCodexModel, setUltraCodexModel] = useState('gpt-5.3');
  const [claudexModel, setClaudexModel] = useState('claude-opus-4-7');
  const [gptModel, setGptModel] = useState('gpt-5.3');
  const [recordPrompts, setRecordPrompts] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);

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

  // === Handlers (preserved from original) =============================

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
          : (skipDeckSelection ? undefined : (isYugioh ? (playerYgoDeck || undefined) : (isMinecraft ? playerMinecraftDeck : (playerDeck || undefined)))),
        ai_deck_id: isSCP ? aiSCPDeck
          : isDepths ? aiDepthsDeck
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
      const response = await botGameAPI.start({
        mode: gameMode,
        bot1_deck_id: isYgo ? (playerYgoDeck || undefined) : (isMinecraft ? playerMinecraftDeck : (playerDeck || undefined)),
        bot2_deck_id: isYgo ? (aiYgoDeck || undefined) : (isMinecraft ? aiMinecraftDeck : (aiDeck || undefined)),
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
        bot1_brain: 'anthropic',
        bot2_brain: 'openai',
        bot1_model: claudexModel,
        bot2_model: gptModel,
        bot1_name: 'Claudex',
        bot2_name: 'GPT-5.3',
        bot1_difficulty: difficulty,
        bot2_difficulty: difficulty,
        bot1_temperature: 0.2,
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
        bot1_brain: 'anthropic',
        bot2_brain: 'heuristic',
        bot1_model: claudexModel,
        bot1_name: 'Claudex',
        bot2_name: 'Ultra Bot',
        bot1_difficulty: 'ultra',
        bot2_difficulty: 'ultra',
        bot1_temperature: 0.2,
        record_prompts: recordPrompts,
        delay_ms: 900,
        max_replay_frames: 5000,
      });
      navigate(`/spectate/${response.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start Claudex vs Ultra');
    } finally {
      setIsLoading(false);
    }
  };

  const selectedMode = getMode(gameMode)!;
  /** Bot-vs-bot spectate (the "Watch Bot vs Bot" button) — supported in mtg/ygo/mc. */
  const showWatchBot = gameMode === 'mtg' || gameMode === 'yugioh' || gameMode === 'minecraft';
  /** Advanced duels (Ultra mirror, Claudex-vs-Ultra, LLM duel) — mtg + ygo only. */
  const showAdvancedDuels = gameMode === 'mtg' || gameMode === 'yugioh';
  const showLlmDuel = gameMode === 'mtg' || gameMode === 'yugioh';

  return (
    <AppShell headerRight={<NowPlayingPill />}>
      {/* === Hero ============================================================ */}
      <section className="relative pt-20 pb-16 lg:pt-28 lg:pb-20 brand-frame">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.22, 0.8, 0.3, 1] }}
          className="max-w-4xl"
        >
          <p className="brand-eyebrow mb-5">A multi-engine card laboratory</p>
          <h1 className="brand-wordmark text-[clamp(3.5rem,9vw,7.5rem)] leading-[0.9] brand-foil-text mb-6">
            hyperdraft
          </h1>
          <p className="text-lg lg:text-xl text-brand-parchment max-w-xl leading-relaxed">
            Eight rules engines, one frame. Play <span className="text-brand-foil">Magic</span>,{' '}
            <span className="text-brand-ember">Hearthstone</span>, <span className="text-brand-sheen">Pokémon</span>,{' '}
            Yu-Gi-Oh!, and four bespoke formats against an opponent that{' '}
            <em className="text-brand-cream not-italic font-medium">actually plans</em>.
          </p>
          <div className="mt-8 flex items-center gap-4">
            <BrandButton
              size="lg"
              onClick={() => {
                document.getElementById('match-builder')?.scrollIntoView({ behavior: 'smooth' });
              }}
            >
              Start a match
            </BrandButton>
            <BrandButton variant="secondary" size="lg" onClick={() => navigate('/watch/live')}>
              Watch live
            </BrandButton>
          </div>
        </motion.div>
      </section>

      {/* === Engine grid ===================================================== */}
      <Section
        eyebrow="01 · Choose your engine"
        title="Eight rules engines, one frame"
        trailing={
          <span className="text-xs text-brand-dust brand-mono tracking-tight">
            {GAME_MODES.length} live · 0 in draft
          </span>
        }
      >
        <div className="grid gap-4 lg:gap-5 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          {GAME_MODES.map((mode, idx) => (
            <GameModeTile
              key={mode.id}
              mode={mode}
              selected={mode.id === gameMode}
              onClick={() => setGameMode(mode.id)}
              delaySeconds={0.05 * idx}
            />
          ))}
        </div>
      </Section>

      {/* === Match Builder =================================================== */}
      <Section
        eyebrow="02 · Start a match"
        title={
          <span className="flex items-center gap-3">
            <span>{selectedMode.title}</span>
            <Monogram mode={selectedMode} size={24} variant="mode" />
          </span>
        }
        trailing={selectedMode.blurb}
      >
        <div id="match-builder" className="grid gap-6 lg:grid-cols-3">
          {/* ── Left: identity ───────────────────────────────────────────── */}
          <div className="space-y-6 lg:col-span-1">
            <FieldBlock label="Your name">
              <input
                type="text"
                value={playerName}
                onChange={(e) => setPlayerName(e.target.value)}
                className="w-full bg-brand-obsidian border border-brand-hairline px-3 py-2.5 text-brand-cream placeholder-brand-dust focus:outline-none focus:border-brand-foil/60 transition-colors"
                placeholder="Player"
              />
            </FieldBlock>

            <FieldBlock label="Difficulty">
              <div className="grid grid-cols-4 gap-1.5">
                {DIFFICULTIES.map((d) => (
                  <button
                    key={d}
                    onClick={() => setDifficulty(d)}
                    className={
                      'px-2 py-2 text-[11px] uppercase tracking-[0.14em] transition-all ' +
                      (difficulty === d
                        ? d === 'ultra'
                          ? 'bg-brand-violet/20 text-brand-violet border border-brand-violet/60'
                          : 'bg-brand-foil/20 text-brand-foil border border-brand-foil/60'
                        : 'bg-brand-obsidian text-brand-chalk border border-brand-hairline hover:border-brand-foil/40 hover:text-brand-cream')
                    }
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
                  className="overflow-hidden"
                >
                  <FieldBlock label="Ultra agent" hint="External Claude / Codex CLI">
                    <div className="grid grid-cols-2 gap-1.5 mb-2.5">
                      {(['claude', 'codex'] as const).map((a) => (
                        <button
                          key={a}
                          onClick={() => setUltraAgent(a)}
                          className={
                            'px-3 py-2 text-sm transition-all ' +
                            (ultraAgent === a
                              ? 'bg-brand-foil/15 text-brand-foil border border-brand-foil/60'
                              : 'bg-brand-obsidian text-brand-chalk border border-brand-hairline hover:border-brand-foil/40')
                          }
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
                      className="w-full bg-brand-obsidian border border-brand-hairline px-3 py-2 text-sm brand-mono text-brand-cream focus:outline-none focus:border-brand-foil/60"
                      placeholder={ultraAgent === 'codex' ? 'gpt-5.3' : 'claude-opus-4-7'}
                    />
                  </FieldBlock>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* ── Middle + right: deck / variant selection ─────────────────── */}
          <div className="lg:col-span-2 space-y-6">
            {/* HS variant + hero */}
            {gameMode === 'hearthstone' && (
              <FieldBlock label="Hearthstone variant">
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-1.5">
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
                      className={
                        'px-3 py-2 text-sm transition-all ' +
                        (hsVariant === v.id
                          ? 'bg-brand-foil/15 text-brand-foil border border-brand-foil/60'
                          : 'bg-brand-obsidian text-brand-chalk border border-brand-hairline hover:border-brand-foil/40')
                      }
                    >
                      {v.label}
                    </button>
                  ))}
                </div>
                {hsVariant !== null && (
                  <div className="mt-3">
                    <p className="brand-eyebrow mb-2">Hero class</p>
                    <div className="flex gap-2">
                      {(hsVariant === 'frierenrift'
                        ? ['Frieren', 'Macht']
                        : ['Pyromancer', 'Cryomancer']
                      ).map((c) => (
                        <button
                          key={c}
                          onClick={() => setHeroClass(c)}
                          className={
                            'flex-1 px-3 py-2 text-sm transition-all ' +
                            (heroClass === c
                              ? 'bg-brand-foil/15 text-brand-foil border border-brand-foil/60'
                              : 'bg-brand-obsidian text-brand-chalk border border-brand-hairline hover:border-brand-foil/40')
                          }
                        >
                          {c}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </FieldBlock>
            )}

            {/* Deck selection per mode */}
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
            {/* Pokemon / Hearthstone / Finance use built-in decks (no picker) */}
            {(gameMode === 'pokemon' || gameMode === 'hearthstone' || gameMode === 'finance') && (
              <div className="text-sm text-brand-chalk px-1">
                {gameMode === 'pokemon' && 'Pokémon uses the SV Starter pack — Charizard ex vs Mewtwo VMAX.'}
                {gameMode === 'hearthstone' && 'Hearthstone variants ship with curated 30-card class decks.'}
                {gameMode === 'finance' && 'Finance TCG uses the default 40-card asset deck.'}
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="border border-brand-ember/50 bg-brand-ember/10 px-4 py-3 text-sm text-brand-ember">
                {error}
              </div>
            )}

            {/* Primary action row */}
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <BrandButton
                size="lg"
                onClick={handleStartGame}
                loading={isLoading}
                trailing={<span aria-hidden>→</span>}
              >
                {difficulty === 'ultra'
                  ? `Play vs ${ultraAgent === 'codex' ? 'Codex' : 'Claude'} Ultra`
                  : 'Play vs AI'}
              </BrandButton>
              {showWatchBot && (
                <BrandButton variant="secondary" size="lg" onClick={handleStartBotGame} loading={isLoading}>
                  Watch Bot vs Bot
                </BrandButton>
              )}
            </div>
          </div>
        </div>
      </Section>

      {/* === Advanced (collapsible) ========================================== */}
      {showAdvancedDuels && (
        <Section
          eyebrow="03 · Advanced"
          title="Bot duels & LLM head-to-heads"
          trailing={
            <button
              onClick={() => setAdvancedOpen((v) => !v)}
              className="text-xs text-brand-foil hover:text-brand-foil-bright tracking-wide"
            >
              {advancedOpen ? 'Hide' : 'Show'} duel presets →
            </button>
          }
        >
          <AnimatePresence>
            {advancedOpen && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="grid gap-4 lg:grid-cols-2">
                  {showAdvancedDuels && (
                    <div className="brand-tile brand-frame p-6">
                      <p className="brand-eyebrow text-brand-foil mb-2">Ultra mirror</p>
                      <h3 className="text-xl font-display font-semibold mb-2">Two heuristic ultras</h3>
                      <p className="text-sm text-brand-chalk mb-5">
                        Both seats run the heuristic engine at ultra difficulty. Useful for
                        balance smoke tests and meta sampling.
                      </p>
                      <div className="grid grid-cols-2 gap-2">
                        <BrandButton variant="secondary" onClick={handleStartUltraMirror} loading={isLoading}>
                          Ultra vs Ultra
                        </BrandButton>
                        <BrandButton variant="secondary" onClick={handleStartClaudexVsUltra} loading={isLoading}>
                          Claudex vs Ultra
                        </BrandButton>
                      </div>
                    </div>
                  )}

                  {showLlmDuel && (
                    <div className="brand-tile brand-frame p-6">
                      <p className="brand-eyebrow text-brand-sheen mb-2">LLM duel</p>
                      <h3 className="text-xl font-display font-semibold mb-2">Anthropic vs OpenAI</h3>
                      <p className="text-sm text-brand-chalk mb-5">
                        Per-decision API mode. Requires <code className="brand-mono text-brand-foil">ANTHROPIC_API_KEY</code> +{' '}
                        <code className="brand-mono text-brand-foil">OPENAI_API_KEY</code> in the container env.
                      </p>
                      <div className="grid grid-cols-2 gap-2 mb-3">
                        <ModelField label="Claudex model" value={claudexModel} onChange={setClaudexModel} />
                        <ModelField label="GPT model" value={gptModel} onChange={setGptModel} />
                      </div>
                      <label className="flex items-center gap-2 text-xs text-brand-chalk mb-3 select-none">
                        <input
                          type="checkbox"
                          checked={recordPrompts}
                          onChange={(e) => setRecordPrompts(e.target.checked)}
                          className="accent-brand-foil"
                        />
                        Record prompts in replay
                      </label>
                      <BrandButton variant="secondary" onClick={handleStartLlmDuel} loading={isLoading}>
                        Watch Claudex vs GPT
                      </BrandButton>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </Section>
      )}

      {/* === Library shortcuts =============================================== */}
      <Section eyebrow="04 · Library" title="Decks, gatherers, and replays">
        <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
          <LibraryTile
            label="Deckbuilder"
            description="Browse curated decklists across all 8 engines."
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
            label="SCP Cards"
            description="Anomaly dossiers and containment briefs."
            onClick={() => navigate('/scp-cards')}
          />
        </div>
      </Section>

      {/* === Footer ========================================================== */}
      <footer className="border-t border-brand-hairline/60 mt-16 py-10">
        <div className="flex flex-wrap items-baseline justify-between gap-4 text-xs text-brand-dust">
          <span className="brand-mono tracking-tight">
            uvicorn src.server.main:socket_app · port 8030
          </span>
          <span className="tracking-wide">
            Hyperdraft — an experimental card-engine laboratory
          </span>
        </div>
      </footer>
    </AppShell>
  );
}

// === Small composition helpers (file-local) ============================

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
      <div className="flex items-baseline justify-between mb-2">
        <p className="brand-eyebrow">{label}</p>
        {hint && <span className="text-[10px] text-brand-dust">{hint}</span>}
      </div>
      {children}
    </div>
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
    <div className="grid gap-4 sm:grid-cols-2">
      <FieldBlock label={`Your ${label.toLowerCase()}`}>
        <select
          value={player}
          onChange={(e) => onPlayer(e.target.value)}
          className="w-full bg-brand-obsidian border border-brand-hairline px-3 py-2.5 text-brand-cream focus:outline-none focus:border-brand-foil/60"
        >
          {renderOptions()}
        </select>
      </FieldBlock>
      <FieldBlock label={`Opponent ${label.toLowerCase()}`}>
        <select
          value={ai}
          onChange={(e) => onAi(e.target.value)}
          className="w-full bg-brand-obsidian border border-brand-hairline px-3 py-2.5 text-brand-cream focus:outline-none focus:border-brand-foil/60"
        >
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
      <p className="brand-eyebrow mb-1">{label}</p>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-brand-obsidian border border-brand-hairline px-2.5 py-2 text-sm brand-mono text-brand-cream focus:outline-none focus:border-brand-foil/60"
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
      className="brand-tile brand-frame p-5 text-left group transition-shadow hover:shadow-[0_22px_50px_-20px_rgba(0,0,0,0.7)]"
    >
      <div className="flex items-baseline justify-between mb-2">
        <span className="text-base font-display font-semibold text-brand-cream">{label}</span>
        <span className="text-brand-foil opacity-0 group-hover:opacity-100 transition-opacity">→</span>
      </div>
      <p className="text-xs text-brand-chalk leading-relaxed">{description}</p>
    </button>
  );
}

export default Home;
