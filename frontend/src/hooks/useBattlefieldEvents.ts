/**
 * useBattlefieldEvents
 *
 * Diffs game-state card health each tick and fires fireBattlefieldEvent()
 * for damage taken, healing, and card disappearance (death).
 *
 * Covers all four game modes:
 *   MTG   — card.damage (damage_marked); death on disappearance with prior damage > 0
 *   HS    — card.toughness - card.damage = current HP; heal when that rises
 *   PKM   — card.damage_counters (each counter = 10 dmg); death on disappearance
 *   YGO   — no per-monster HP in state; death-only on disappearance
 *
 * Coordinates are looked up via data-card-id DOM attributes set on each
 * battlefield card's root element. If the element isn't found, the floater
 * is silently skipped.
 */

import { useEffect, useRef } from 'react';
import { fireBattlefieldEvent } from '../components/game/shared/DamageFloater';
import { useGameStore } from '../stores/gameStore';
import type { CardData, GameState } from '../types';

// ---------------------------------------------------------------------------
// Per-mode health extractors
// ---------------------------------------------------------------------------

/** Returns { current, max } HP for HS minions. */
function hsHp(card: CardData): { current: number; max: number } {
  const max = card.toughness ?? 0;
  const current = max - (card.damage ?? 0);
  return { current, max };
}

/** Returns current HP for PKM Pokémon (damage_counters × 10 subtracted from hp). */
function pkmHp(card: CardData): { current: number; max: number } {
  const max = card.hp ?? 0;
  const counters = card.damage_counters ?? 0;
  const current = Math.max(0, max - counters * 10);
  return { current, max };
}

/** Returns damage_marked for MTG creatures (increasing = damage taken). */
function mtgDamage(card: CardData): number {
  return card.damage ?? 0;
}

// ---------------------------------------------------------------------------
// Snapshot helpers
// ---------------------------------------------------------------------------

interface CardSnapshot {
  id: string;
  /** Generic numeric value for "how much damage is this card carrying".
   *  Increases  → damage event
   *  Decreases  → heal event (or just disappearance = death)
   *  Card gone  → death event (if it had damage or is a creature/pokemon)
   */
  damageStat: number;
  /** Whether the card was alive/present (always true in the snapshot map) */
  hp: number; // current HP (0 means dead / about to die)
  maxHp: number;
  mode: 'hs' | 'pkm' | 'mtg' | 'ygo';
}

function snapshotFromCard(card: CardData, mode: 'hs' | 'pkm' | 'mtg' | 'ygo'): CardSnapshot {
  if (mode === 'hs') {
    const { current, max } = hsHp(card);
    return { id: card.id, damageStat: card.damage ?? 0, hp: current, maxHp: max, mode };
  }
  if (mode === 'pkm') {
    const { current, max } = pkmHp(card);
    return { id: card.id, damageStat: card.damage_counters ?? 0, hp: current, maxHp: max, mode };
  }
  if (mode === 'mtg') {
    const damage = mtgDamage(card);
    const hp = Math.max(0, (card.toughness ?? 0) - damage);
    return { id: card.id, damageStat: damage, hp, maxHp: card.toughness ?? 0, mode };
  }
  // YGO — no per-card HP; only death tracking
  return { id: card.id, damageStat: 0, hp: 1, maxHp: 1, mode };
}

// ---------------------------------------------------------------------------
// DOM coordinate lookup
// ---------------------------------------------------------------------------

function getCardCenter(cardId: string): { x: number; y: number } | null {
  try {
    const el = document.querySelector(`[data-card-id="${CSS.escape(cardId)}"]`);
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    return {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
    };
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Battlefield card extractors per mode
// ---------------------------------------------------------------------------

function getBattlefieldCards(
  gameState: GameState,
  mode: 'hs' | 'pkm' | 'mtg' | 'ygo',
): CardData[] {
  // All four modes expose `gameState.battlefield` with cards that are
  // currently on the battlefield. PKM and YGO may use slotted zones but
  // BattlefieldEventLayer queries by data-card-id so we just need the IDs.
  //
  // PKM also surfaces cards via myActivePokemon / myBench props, but those
  // are derived from gameState.battlefield in the hook consumers; we can
  // read directly from gameState.battlefield here.
  //
  // YGO monster zones are in gameState.battlefield as well.
  return (gameState.battlefield ?? []).filter((c) => {
    if (mode === 'ygo') {
      // Only track monsters (spells/traps have no HP)
      return c.types?.includes('YGO_MONSTER') ?? false;
    }
    if (mode === 'pkm') {
      // Only track Pokemon on the field
      return c.types?.includes('POKEMON') ?? false;
    }
    if (mode === 'hs') {
      // Minions only (heroes are not in battlefield array)
      return true;
    }
    // MTG: creatures
    return c.types?.includes('CREATURE') ?? false;
  });
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useBattlefieldEvents(
  gameState: GameState | null | undefined,
  mode: 'hs' | 'pkm' | 'mtg' | 'ygo',
): void {
  const animationsEnabled = useGameStore((s) => s.ui.animationsEnabled);
  const prevSnapshotRef = useRef<Map<string, CardSnapshot>>(new Map());

  useEffect(() => {
    if (!animationsEnabled || !gameState) return;

    const cards = getBattlefieldCards(gameState, mode);

    // Build current snapshot map
    const currentMap = new Map<string, CardSnapshot>();
    for (const card of cards) {
      currentMap.set(card.id, snapshotFromCard(card, mode));
    }

    const prevMap = prevSnapshotRef.current;

    // Compare prev → current
    for (const [id, curr] of currentMap) {
      const prev = prevMap.get(id);
      if (!prev) continue; // Card is new (just entered); skip first tick

      // Skip YGO damage/heal checks (no HP data)
      if (mode !== 'ygo') {
        const damageDelta = curr.damageStat - prev.damageStat;

        if (damageDelta > 0) {
          // Damage taken — damageStat increased
          const coords = getCardCenter(id);
          if (coords) {
            // For PKM, each counter = 10 HP; show actual HP lost
            const amount = mode === 'pkm' ? damageDelta * 10 : damageDelta;
            fireBattlefieldEvent({ kind: 'damage', amount, x: coords.x, y: coords.y });
          }
        } else if (damageDelta < 0 && mode !== 'mtg') {
          // Heal — damageStat decreased (MTG doesn't heal damage mid-game in this way)
          const coords = getCardCenter(id);
          if (coords) {
            const amount = mode === 'pkm' ? Math.abs(damageDelta) * 10 : Math.abs(damageDelta);
            fireBattlefieldEvent({ kind: 'heal', amount, x: coords.x, y: coords.y });
          }
        }
      }
    }

    // Death detection: cards present in prev but gone in current
    for (const [id, prev] of prevMap) {
      if (!currentMap.has(id)) {
        // Card left the battlefield; fire death only if it had taken damage
        // (or for YGO/PKM always fire — they die via combat)
        const shouldFireDeath =
          mode === 'ygo' ||
          mode === 'pkm' ||
          prev.damageStat > 0 ||
          prev.hp <= 0;

        if (shouldFireDeath) {
          const coords = getCardCenter(id);
          if (coords) {
            fireBattlefieldEvent({ kind: 'death', x: coords.x, y: coords.y });
          }
        }
      }
    }

    prevSnapshotRef.current = currentMap;
  }, [gameState, animationsEnabled, mode]);
}
