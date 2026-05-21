/**
 * Pipeline-the-Game v0.1 LOCAL FALLBACK card pool — HD-CRIT-002 §06.
 *
 * Note: v0.2 (current) draws cards from the **server** via /api/pipeline/*.
 * This file is retained as a local fallback for storybook / offline mode
 * and as a reference for the card shape. The authoritative pool lives in
 * `src/engine/pipeline_deck.py` server-side.
 *
 * Stage colours: TRANSFORM → plasma, PREVENT → halt, RESOLVE → ink,
 * REACT → acid. Cost is a generic resource (not engine mana).
 */
export const LOCAL_FALLBACK = true;

export type PipelineStage = 'TRANSFORM' | 'PREVENT' | 'RESOLVE' | 'REACT';
export type PipelineEngine = 'MTG' | 'HS' | 'PKM' | 'YGO' | 'MNR' | 'FIN' | 'DPT' | 'SCP';
export type ArtGlyph = 'tri' | 'bar' | 'square' | 'circle' | 'grid';

export interface InterceptorCardDef {
  id: string;
  engine: PipelineEngine;
  stage: PipelineStage;
  name: string;
  cost: number;
  text: string;
  art: ArtGlyph;
}

export const PIPELINE_CARD_POOL: InterceptorCardDef[] = [
  // ── TRANSFORM (plasma) ─────────────────────────────────────────────────
  { id: 't-mtg-furnace',  engine: 'MTG', stage: 'TRANSFORM', name: 'Furnace of Rath',  cost: 3, text: 'Double damage from red sources.',           art: 'tri' },
  { id: 't-mtg-quicken',  engine: 'MTG', stage: 'TRANSFORM', name: 'Quicken',          cost: 1, text: 'The next spell is an instant.',              art: 'tri' },
  { id: 't-scp-mnestic',  engine: 'SCP', stage: 'TRANSFORM', name: 'Mnestic Recall',   cost: 4, text: 'Rewrite the event source.',                  art: 'tri' },
  { id: 't-hs-prep',      engine: 'HS',  stage: 'TRANSFORM', name: 'Preparation',      cost: 1, text: 'Next spell costs (3) less.',                 art: 'tri' },
  { id: 't-pkm-magnet',   engine: 'PKM', stage: 'TRANSFORM', name: 'Energy Magnet',    cost: 2, text: 'Redirect attached energy.',                  art: 'tri' },
  { id: 't-fin-arbitrage', engine: 'FIN', stage: 'TRANSFORM', name: 'Arbitrage',       cost: 2, text: 'Re-price the event by 1 tick.',              art: 'tri' },

  // ── PREVENT (halt) ────────────────────────────────────────────────────
  { id: 'p-mtg-shielding', engine: 'MTG', stage: 'PREVENT', name: 'Shielding Plate',  cost: 1, text: 'Prevent the next 2 damage.',                 art: 'bar' },
  { id: 'p-mtg-counter',   engine: 'MTG', stage: 'PREVENT', name: 'Counterspell',     cost: 2, text: 'Counter target spell.',                       art: 'bar' },
  { id: 'p-hs-iceblock',   engine: 'HS',  stage: 'PREVENT', name: 'Ice Block',        cost: 3, text: 'Prevent lethal once this turn.',              art: 'bar' },
  { id: 'p-ygo-jammer',    engine: 'YGO', stage: 'PREVENT', name: 'Magic Jammer',     cost: 2, text: 'Discard 1, negate a spell.',                  art: 'bar' },
  { id: 'p-pkm-protect',   engine: 'PKM', stage: 'PREVENT', name: 'Protection Cube',  cost: 1, text: 'Block 30 damage to a Pokémon.',               art: 'bar' },
  { id: 'p-dpt-silent',    engine: 'DPT', stage: 'PREVENT', name: 'Silent Running',   cost: 2, text: 'Hide from sonar this round.',                 art: 'bar' },
  { id: 'p-scp-veil',      engine: 'SCP', stage: 'PREVENT', name: 'Veil Protocol',    cost: 3, text: 'Cancel an anomalous trigger.',                art: 'bar' },

  // ── RESOLVE (ink) — the mandatory column ──────────────────────────────
  { id: 'r-mtg-bolt',      engine: 'MTG', stage: 'RESOLVE', name: 'Lightning Bolt',   cost: 1, text: 'Deal 3 damage to any target.',                art: 'square' },
  { id: 'r-mtg-wrath',     engine: 'MTG', stage: 'RESOLVE', name: 'Wrath of God',     cost: 4, text: 'Destroy all creatures.',                      art: 'square' },
  { id: 'r-hs-fireball',   engine: 'HS',  stage: 'RESOLVE', name: 'Fireball',         cost: 4, text: 'Deal 6 damage.',                              art: 'square' },
  { id: 'r-pkm-poisoned',  engine: 'PKM', stage: 'RESOLVE', name: 'Status: Poisoned', cost: 2, text: 'Apply 10 damage on resolve.',                 art: 'square' },
  { id: 'r-ygo-raigeki',   engine: 'YGO', stage: 'RESOLVE', name: 'Raigeki',          cost: 3, text: 'Destroy all opponent monsters.',              art: 'square' },
  { id: 'r-mnr-pulse',     engine: 'MNR', stage: 'RESOLVE', name: 'Redstone Pulse',   cost: 1, text: 'Trigger an adjacent interceptor.',            art: 'square' },
  { id: 'r-fin-short',     engine: 'FIN', stage: 'RESOLVE', name: 'Short Squeeze',    cost: 3, text: '+1 trick if you held the long.',              art: 'square' },
  { id: 'r-dpt-torpedo',   engine: 'DPT', stage: 'RESOLVE', name: 'Torpedo Salvo',    cost: 3, text: 'Deal 4 to the active sub.',                   art: 'square' },
  { id: 'r-scp-breach',    engine: 'SCP', stage: 'RESOLVE', name: 'Containment Breach', cost: 5, text: 'Resolve anomaly damage twice.',             art: 'square' },

  // ── REACT (acid) ──────────────────────────────────────────────────────
  { id: 'k-mtg-soul',      engine: 'MTG', stage: 'REACT',   name: 'Soul Warden',      cost: 1, text: 'When damage resolves, gain 1 life per source.', art: 'circle' },
  { id: 'k-hs-acolyte',    engine: 'HS',  stage: 'REACT',   name: 'Acolyte of Pain',  cost: 2, text: 'When dealt damage, draw a card.',             art: 'circle' },
  { id: 'k-mnr-redstone',  engine: 'MNR', stage: 'REACT',   name: 'Redstone Latch',   cost: 1, text: 'Trigger an adjacent interceptor.',            art: 'grid' },
  { id: 'k-pkm-grit',      engine: 'PKM', stage: 'REACT',   name: 'Survivor',         cost: 2, text: 'Survive a KO with 10 HP once.',               art: 'circle' },
  { id: 'k-ygo-mirror',    engine: 'YGO', stage: 'REACT',   name: 'Mirror Force',     cost: 3, text: 'Destroy all attacking monsters.',             art: 'circle' },
  { id: 'k-scp-amnestic',  engine: 'SCP', stage: 'REACT',   name: 'Amnestic Dose',    cost: 2, text: 'Forget the event happened.',                  art: 'circle' },
  { id: 'k-fin-margin',    engine: 'FIN', stage: 'REACT',   name: 'Margin Call',      cost: 4, text: 'On resolve, opponent pays cost in tricks.',   art: 'grid' },
  { id: 'k-dpt-sonar',     engine: 'DPT', stage: 'REACT',   name: 'Sonar Pulse',      cost: 1, text: 'Reveal one opponent card.',                   art: 'grid' },
];

export function drawStartingHand(seed: number): InterceptorCardDef[] {
  // Deterministic-ish: rotate the pool by seed*7 and take 8.
  const rotated = [...PIPELINE_CARD_POOL.slice(seed * 7 % PIPELINE_CARD_POOL.length),
                   ...PIPELINE_CARD_POOL.slice(0, seed * 7 % PIPELINE_CARD_POOL.length)];
  return rotated.slice(0, 8);
}
