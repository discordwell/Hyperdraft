/**
 * useAltP — global keybind to toggle the Pipeline View on the board.
 *
 * Mirrors useCmdE.ts: a document-level keydown listener that fires for
 * Alt+P (Option+P on macOS) and Alt+P everywhere else, with the same
 * typing-target guard so the chord doesn't fire while the player is
 * typing in a text input, textarea, select, or contenteditable surface.
 *
 * HD-CRIT-018 deliverable: this is the toggle that swaps the cards for
 * their event stream — TRANSFORM / PREVENT / RESOLVE / REACT.
 */

import { useEffect } from 'react';

type Handler = () => void;

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
  if (el.isContentEditable) return true;
  return false;
}

export function useAltP(handler: Handler) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.altKey) return;
      // `e.key` is "π" on macOS Option+P, so check `e.code` first
      // (always 'KeyP') and fall back to a case-insensitive key match.
      const matchesCode = e.code === 'KeyP';
      const matchesKey = e.key.toLowerCase() === 'p';
      if (!matchesCode && !matchesKey) return;
      if (isTypingTarget(e.target)) return;
      e.preventDefault();
      handler();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [handler]);
}
