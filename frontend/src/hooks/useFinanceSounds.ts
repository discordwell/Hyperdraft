/**
 * useFinanceSounds — plays Interactive Brokers-style audio cues in
 * response to FINA game events.
 *
 * Stack cues come from gameState.game_log entries (emitted by engine
 * via FIN_CARD_CAST / FIN_CARD_RESOLVED / FIN_CARD_COUNTERED, surfaced
 * by the server's _add_log layer):
 *   - "fin_card_cast"      → /sounds/order-placed.mp3       (ToS Chimes)
 *   - "fin_card_resolved"  → /sounds/order-filled.mp3       (IB voice)
 *   - "fin_card_countered" → /sounds/order-cancelled.mp3    (IB voice)
 *
 * Game-level cues come from gameState transitions:
 *   - First time gameState becomes non-null → /sounds/game-started.mp3
 *     (IB "Trading connection reestablished")
 *   - is_game_over flips true and winner !== playerId → /sounds/game-lost.mp3
 *     (IB "Trading connection lost")
 *
 * On/off is read from localStorage["financeSoundsEnabled"] (default
 * "true"). Missing audio files cause silent fallback.
 */

import { useEffect, useRef } from "react";
import type { GameState } from "../types/game";

const STACK_SOUND_PATHS = {
  fin_card_cast: "/sounds/order-placed.mp3",
  fin_card_resolved: "/sounds/order-filled.mp3",
  fin_card_countered: "/sounds/order-cancelled.mp3",
} as const;

const GAME_SOUND_PATHS = {
  game_started: "/sounds/game-started.mp3",
  game_lost: "/sounds/game-lost.mp3",
} as const;

type StackSoundEvent = keyof typeof STACK_SOUND_PATHS;
type GameSoundEvent = keyof typeof GAME_SOUND_PATHS;

function isStackSoundEvent(value: string): value is StackSoundEvent {
  return value in STACK_SOUND_PATHS;
}

function soundsEnabled(): boolean {
  return (
    typeof window !== "undefined" &&
    window.localStorage?.getItem("financeSoundsEnabled") !== "false"
  );
}

export function useFinanceSounds(
  gameState: GameState | null,
  playerId: string | null = null
) {
  const stackRefs = useRef<Record<StackSoundEvent, HTMLAudioElement> | null>(
    null
  );
  const gameRefs = useRef<Record<GameSoundEvent, HTMLAudioElement> | null>(
    null
  );
  const lastSeenIndex = useRef<number>(-1);
  const startedRef = useRef<boolean>(false);
  const lostFiredRef = useRef<boolean>(false);

  // Lazy-init audio elements once.
  useEffect(() => {
    if (stackRefs.current === null) {
      stackRefs.current = {
        fin_card_cast: new Audio(STACK_SOUND_PATHS.fin_card_cast),
        fin_card_resolved: new Audio(STACK_SOUND_PATHS.fin_card_resolved),
        fin_card_countered: new Audio(STACK_SOUND_PATHS.fin_card_countered),
      };
      Object.values(stackRefs.current).forEach((a) => {
        a.preload = "auto";
        a.volume = 0.5;
      });
    }
    if (gameRefs.current === null) {
      gameRefs.current = {
        game_started: new Audio(GAME_SOUND_PATHS.game_started),
        game_lost: new Audio(GAME_SOUND_PATHS.game_lost),
      };
      Object.values(gameRefs.current).forEach((a) => {
        a.preload = "auto";
        a.volume = 0.6;
      });
    }
  }, []);

  function play(audio: HTMLAudioElement | undefined) {
    if (!audio || !soundsEnabled()) return;
    try {
      audio.currentTime = 0;
      const p = audio.play();
      if (p && typeof p.catch === "function") {
        p.catch(() => {
          // Silently swallow autoplay-policy / missing-file errors.
        });
      }
    } catch {
      // No-op
    }
  }

  // Stack cues from game_log.
  useEffect(() => {
    if (!gameState?.game_log || !stackRefs.current) return;
    const log = gameState.game_log;
    if (lastSeenIndex.current === -1) {
      lastSeenIndex.current = log.length;
      return;
    }
    if (log.length <= lastSeenIndex.current) return;

    for (let i = lastSeenIndex.current; i < log.length; i++) {
      const entry = log[i];
      const eventType = (entry.event_type || "").toLowerCase();
      if (!isStackSoundEvent(eventType)) continue;
      play(stackRefs.current[eventType]);
    }
    lastSeenIndex.current = log.length;
  }, [gameState?.game_log]);

  // Game start cue — fires once when gameState first appears.
  useEffect(() => {
    if (!gameState || startedRef.current || !gameRefs.current) return;
    startedRef.current = true;
    play(gameRefs.current.game_started);
  }, [gameState]);

  // Game lost cue — fires when this player loses.
  useEffect(() => {
    if (!gameState || lostFiredRef.current || !gameRefs.current) return;
    if (!gameState.is_game_over) return;
    if (!playerId) return;
    if (gameState.winner === playerId) return; // we won
    lostFiredRef.current = true;
    play(gameRefs.current.game_lost);
  }, [gameState?.is_game_over, gameState?.winner, playerId]);
}
