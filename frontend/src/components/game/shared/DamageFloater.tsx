/**
 * DamageFloater + DeathPuff
 *
 * Background polish: overlays a short-lived floating damage number or skull
 * particle at a given screen position. Driven by a lightweight event queue
 * so callers just fire, no per-card subscription required.
 *
 * Usage:
 *   import { BattlefieldEventLayer, fireBattlefieldEvent } from '.../DamageFloater';
 *   <BattlefieldEventLayer />
 *   fireBattlefieldEvent({ kind: 'damage', amount: 3, x, y });
 *
 * All effects respect the global `animationsEnabled` preference.
 */

import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useGameStore } from '../../../stores/gameStore';

export type BattlefieldEvent =
  | { kind: 'damage'; amount: number; x: number; y: number }
  | { kind: 'heal'; amount: number; x: number; y: number }
  | { kind: 'death'; x: number; y: number };

type QueuedEvent = BattlefieldEvent & { id: number };

let nextId = 1;
const listeners = new Set<(e: QueuedEvent) => void>();

export function fireBattlefieldEvent(event: BattlefieldEvent): void {
  const queued: QueuedEvent = { ...event, id: nextId++ };
  for (const fn of listeners) fn(queued);
}

export function BattlefieldEventLayer() {
  const animationsEnabled = useGameStore((s) => s.ui.animationsEnabled);
  const [events, setEvents] = useState<QueuedEvent[]>([]);

  useEffect(() => {
    const handler = (e: QueuedEvent) => {
      setEvents((prev) => [...prev, e]);
      setTimeout(() => {
        setEvents((prev) => prev.filter((x) => x.id !== e.id));
      }, 1100);
    };
    listeners.add(handler);
    return () => {
      listeners.delete(handler);
    };
  }, []);

  if (!animationsEnabled) return null;

  return (
    <div className="pointer-events-none fixed inset-0 z-30">
      <AnimatePresence>
        {events.map((e) => {
          if (e.kind === 'death') {
            return (
              <motion.div
                key={e.id}
                className="absolute text-3xl"
                style={{ left: e.x, top: e.y }}
                initial={{ opacity: 1, scale: 0.6 }}
                animate={{ opacity: 0, scale: 1.6, y: -40 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 1.0, ease: 'easeOut' }}
              >
                <span role="img" aria-label="death">💀</span>
              </motion.div>
            );
          }
          const isHeal = e.kind === 'heal';
          return (
            <motion.div
              key={e.id}
              className={`absolute text-2xl font-black select-none drop-shadow-[0_2px_6px_rgba(0,0,0,0.8)] ${
                isHeal ? 'text-emerald-300' : 'text-red-400'
              }`}
              style={{ left: e.x, top: e.y }}
              initial={{ opacity: 0, scale: 0.4, y: 0 }}
              animate={{ opacity: 1, scale: 1.2, y: -60 }}
              exit={{ opacity: 0, y: -90 }}
              transition={{ duration: 1.0, ease: 'easeOut' }}
            >
              {isHeal ? `+${e.amount}` : `-${e.amount}`}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

export default BattlefieldEventLayer;
