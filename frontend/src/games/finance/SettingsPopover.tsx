/**
 * SettingsPopover — gear-icon dropdown with Finance TCG client settings.
 *
 * Two controls:
 *   - Response timer slider (5/10/15/30s/Off=manual). Persists to
 *     localStorage["financeResponseTimer"].
 *   - Sound toggle. Persists to localStorage["financeSoundsEnabled"].
 *
 * Both keys are read by useFinanceSounds and ResponseWindow at runtime.
 */

import { useEffect, useRef, useState } from "react";

const TIMER_OPTIONS = [5, 10, 15, 30, 0] as const; // 0 = no auto-pass
type TimerValue = (typeof TIMER_OPTIONS)[number];

const TIMER_LABELS: Record<TimerValue, string> = {
  5: "5s",
  10: "10s",
  15: "15s",
  30: "30s",
  0: "Manual",
};

const STORAGE_TIMER = "financeResponseTimer";
const STORAGE_SOUNDS = "financeSoundsEnabled";

function readTimer(): TimerValue {
  if (typeof window === "undefined") return 10;
  const raw = window.localStorage.getItem(STORAGE_TIMER);
  const parsed = raw === null ? 10 : Number(raw);
  return (TIMER_OPTIONS as readonly number[]).includes(parsed)
    ? (parsed as TimerValue)
    : 10;
}

function readSounds(): boolean {
  if (typeof window === "undefined") return true;
  return window.localStorage.getItem(STORAGE_SOUNDS) !== "false";
}

export function SettingsPopover() {
  const [open, setOpen] = useState(false);
  const [timer, setTimer] = useState<TimerValue>(() => readTimer());
  const [sounds, setSounds] = useState<boolean>(() => readSounds());
  const ref = useRef<HTMLDivElement | null>(null);

  // Click-outside dismissal.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const setTimerValue = (val: TimerValue) => {
    setTimer(val);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_TIMER, String(val));
    }
  };

  const setSoundsValue = (val: boolean) => {
    setSounds(val);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_SOUNDS, val ? "true" : "false");
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Settings"
        className="font-mono uppercase text-xs px-2 py-1 border border-gray-700 text-gray-400 hover:bg-gray-800 transition-colors"
        style={{ minWidth: "2rem" }}
      >
        ⚙
      </button>
      {open && (
        <div
          className="absolute right-0 mt-2 z-50 p-4 border"
          style={{
            background: "#03080f",
            borderColor: "#1a2a1a",
            minWidth: "240px",
            boxShadow: "0 4px 24px rgba(0, 255, 136, 0.1)",
          }}
        >
          <div
            className="font-mono uppercase text-xs mb-3 pb-2 border-b"
            style={{ color: "#00FF88", borderColor: "#1a2a1a" }}
          >
            Trading Settings
          </div>

          {/* Timer */}
          <div className="mb-4">
            <div
              className="font-mono uppercase text-[10px] mb-2"
              style={{ color: "#888" }}
            >
              Response Timer
            </div>
            <div className="flex flex-wrap gap-1">
              {TIMER_OPTIONS.map((opt) => {
                const isActive = timer === opt;
                return (
                  <button
                    key={opt}
                    onClick={() => setTimerValue(opt)}
                    className="font-mono text-xs px-2 py-1 border transition-colors"
                    style={{
                      borderColor: isActive ? "#00FF88" : "#1a2a1a",
                      color: isActive ? "#00FF88" : "#888",
                      background: isActive
                        ? "rgba(0, 255, 136, 0.08)"
                        : "transparent",
                    }}
                  >
                    {TIMER_LABELS[opt]}
                  </button>
                );
              })}
            </div>
            <div
              className="font-mono text-[9px] mt-1"
              style={{ color: "#555" }}
            >
              Auto-pass on opponent's spell after this many seconds.
            </div>
          </div>

          {/* Sound toggle */}
          <div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={sounds}
                onChange={(e) => setSoundsValue(e.target.checked)}
                className="w-3 h-3"
              />
              <span
                className="font-mono uppercase text-[10px]"
                style={{ color: "#888" }}
              >
                Trading Floor Sounds
              </span>
            </label>
            <div
              className="font-mono text-[9px] mt-1 ml-5"
              style={{ color: "#555" }}
            >
              Order placed / filled / cancelled cues.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Helper hooks for other components that need to read these settings.
export function useResponseTimer(): TimerValue {
  const [value, setValue] = useState<TimerValue>(() => readTimer());

  useEffect(() => {
    const onStorage = () => setValue(readTimer());
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return value;
}
