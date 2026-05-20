/**
 * useCmdE — global keybind to toggle the lab Engine Picker.
 *
 * Listens for ⌘E on macOS / Ctrl+E elsewhere. Captures at the document level
 * so it works from any focused element. Ignores typing inside text inputs
 * and content-editable surfaces — those use the chord for their own actions
 * (e.g. find-in-editor).
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

export function useCmdE(handler: Handler) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod || e.key.toLowerCase() !== 'e') return;
      if (isTypingTarget(e.target)) return;
      e.preventDefault();
      handler();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [handler]);
}
