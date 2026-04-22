/**
 * AnimationsToggle
 *
 * Tiny labeled checkbox bound to the global `animationsEnabled` preference
 * in the game store. Drop this into any sidebar so the player can skip the
 * legendary fanfare + damage floats if they prefer a quieter experience.
 */

import { useGameStore } from '../../../stores/gameStore';

interface AnimationsToggleProps {
  className?: string;
  labelClassName?: string;
}

export function AnimationsToggle({ className = '', labelClassName = '' }: AnimationsToggleProps) {
  const enabled = useGameStore((s) => s.ui.animationsEnabled);
  const setEnabled = useGameStore((s) => s.setAnimationsEnabled);

  return (
    <label className={`flex items-center gap-2 cursor-pointer select-none ${className}`}>
      <input
        type="checkbox"
        checked={enabled}
        onChange={(e) => setEnabled(e.target.checked)}
        className="w-3 h-3 accent-yellow-400"
      />
      <span className={`text-[11px] text-gray-400 ${labelClassName}`}>
        Show animations
      </span>
    </label>
  );
}

export default AnimationsToggle;
