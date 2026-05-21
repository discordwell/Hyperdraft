/**
 * useQuestionMark — global keybind to toggle the RulesSheet slide-over.
 *
 * Listens for a plain `?` keystroke at the document level so it works from
 * any focused element. Ignores typing inside text inputs, textareas, and
 * content-editable surfaces — those need `?` for normal punctuation. Same
 * pattern as `useCmdE`.
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

export function useQuestionMark(handler: Handler) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Accept both `?` (US keyboard) and explicit Shift+/ — `e.key` on most
      // layouts is just `?`. Guard against repeats so holding the key
      // doesn't oscillate the panel.
      if (e.key !== '?') return;
      if (e.repeat) return;
      if (isTypingTarget(e.target)) return;
      e.preventDefault();
      handler();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [handler]);
}
