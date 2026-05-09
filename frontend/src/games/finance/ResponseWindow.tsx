/**
 * ResponseWindow — overlay shown when the engine is awaiting a
 * response from this player. Displays:
 *   - Top-of-stack card name and controller
 *   - Countdown timer bar (auto-passes when expired)
 *   - List of playable Orders from hand (with target = top card)
 *   - PASS button
 *
 * Visible iff `gameState.finance_pending_response.prompted_player_id`
 * matches the current player's id.
 */

import { useEffect, useRef, useState } from "react";
import type { CardData, GameState } from "../../types/game";
import { useResponseTimer } from "./SettingsPopover";

interface Props {
  gameState: GameState | null;
  playerId: string | null;
  myHand: CardData[];
  myLiquidity: number;
  onPlayResponse: (cardId: string, targetStackCardId: string) => void;
  onPassResponse: () => void;
}

function _parseCost(card: CardData): number {
  const raw = card.mana_cost;
  if (!raw) return 0;
  const matches = raw.match(/\{(\d+)\}/g) || [];
  let total = 0;
  for (const m of matches) {
    const n = Number(m.replace(/[{}]/g, ""));
    if (Number.isFinite(n)) total += n;
  }
  return total;
}

function _isOrder(card: CardData): boolean {
  return (card.types || []).some((t) => t === "FIN_ORDER");
}

export function FinanceResponseWindow({
  gameState,
  playerId,
  myHand,
  myLiquidity,
  onPlayResponse,
  onPassResponse,
}: Props) {
  const pending = gameState?.finance_pending_response;
  const stack = gameState?.finance_stack || [];
  const isMyResponse = !!pending && pending.prompted_player_id === playerId;
  const timerSec = useResponseTimer();

  // Countdown state. Reset whenever a new response window opens.
  const [secondsLeft, setSecondsLeft] = useState<number>(timerSec || 0);
  const lastCardId = useRef<string | null>(null);
  const submitted = useRef<boolean>(false);

  useEffect(() => {
    if (!isMyResponse || !pending) {
      lastCardId.current = null;
      submitted.current = false;
      setSecondsLeft(timerSec || 0);
      return;
    }
    if (lastCardId.current !== pending.top_card_id) {
      lastCardId.current = pending.top_card_id;
      submitted.current = false;
      setSecondsLeft(timerSec || 0);
    }
  }, [isMyResponse, pending, timerSec]);

  useEffect(() => {
    if (!isMyResponse || !pending) return;
    if (timerSec === 0) return; // Manual mode — no auto-pass.
    if (submitted.current) return;
    if (secondsLeft <= 0) {
      submitted.current = true;
      onPassResponse();
      return;
    }
    const t = window.setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => window.clearTimeout(t);
  }, [isMyResponse, pending, secondsLeft, timerSec, onPassResponse]);

  if (!isMyResponse || !pending) return null;

  const playableOrders = myHand.filter((card) => {
    if (!_isOrder(card)) return false;
    if (_parseCost(card) > myLiquidity) return false;
    return true;
  });

  const timerPct = timerSec > 0 ? Math.max(0, (secondsLeft / timerSec) * 100) : 0;

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center"
      style={{ background: "rgba(3, 8, 15, 0.85)" }}
    >
      <div
        className="border p-6"
        style={{
          background: "#03080f",
          borderColor: "#FFD700",
          minWidth: "420px",
          maxWidth: "560px",
          boxShadow: "0 0 32px rgba(255, 215, 0, 0.35)",
        }}
      >
        {/* Header */}
        <div
          className="font-mono uppercase text-xs mb-3 pb-2 border-b"
          style={{ color: "#FFD700", borderColor: "#1a2a1a" }}
        >
          ▲ Response Window — Top of Stack
        </div>

        {/* Stack snapshot */}
        <div className="mb-4">
          <div className="font-mono text-[10px] mb-1" style={{ color: "#888" }}>
            Stack ({stack.length} item{stack.length !== 1 ? "s" : ""}, top first)
          </div>
          <div className="space-y-1">
            {[...stack].reverse().map((item, idx) => {
              const isTop = idx === 0;
              return (
                <div
                  key={item.card_id}
                  className="font-mono text-xs px-2 py-1 border flex items-center justify-between"
                  style={{
                    borderColor: isTop ? "#FFD700" : "#1a2a1a",
                    color: isTop ? "#FFD700" : "#888",
                    background: isTop ? "rgba(255, 215, 0, 0.05)" : "transparent",
                  }}
                >
                  <span>
                    {item.is_response ? "↳ " : ""}
                    {item.name || item.card_id}
                    {item.countered ? " (COUNTERED)" : ""}
                  </span>
                  <span className="text-[10px]" style={{ color: "#555" }}>
                    {item.controller === playerId ? "YOU" : "OPP"}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Timer bar */}
        {timerSec > 0 && (
          <div className="mb-4">
            <div className="flex items-center justify-between mb-1">
              <span
                className="font-mono uppercase text-[10px]"
                style={{ color: "#888" }}
              >
                Auto-pass in
              </span>
              <span
                className="font-mono text-xs"
                style={{ color: "#FFD700" }}
              >
                {secondsLeft}s
              </span>
            </div>
            <div
              className="h-1 w-full"
              style={{ background: "#1a2a1a" }}
            >
              <div
                className="h-1 transition-all"
                style={{
                  width: `${timerPct}%`,
                  background: "#FFD700",
                }}
              />
            </div>
          </div>
        )}

        {/* Order picker */}
        <div className="mb-4">
          <div
            className="font-mono uppercase text-[10px] mb-2"
            style={{ color: "#888" }}
          >
            Playable Orders ({playableOrders.length})
          </div>
          {playableOrders.length === 0 ? (
            <div
              className="font-mono text-xs italic"
              style={{ color: "#555" }}
            >
              No Orders affordable in your hand.
            </div>
          ) : (
            <div className="space-y-1">
              {playableOrders.map((card) => (
                <button
                  key={card.id}
                  onClick={() => {
                    if (submitted.current) return;
                    submitted.current = true;
                    onPlayResponse(card.id, pending.top_card_id);
                  }}
                  className="font-mono text-xs px-3 py-2 border w-full text-left transition-colors"
                  style={{
                    borderColor: "#00FF88",
                    color: "#00FF88",
                    background: "rgba(0, 255, 136, 0.05)",
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span>{card.name}</span>
                    <span style={{ color: "#888" }}>
                      {card.mana_cost || "{0}"}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Pass button */}
        <button
          onClick={() => {
            if (submitted.current) return;
            submitted.current = true;
            onPassResponse();
          }}
          className="font-mono uppercase text-xs px-4 py-2 border w-full transition-colors hover:bg-gray-800"
          style={{ borderColor: "#888", color: "#888" }}
        >
          Pass — Let It Resolve
        </button>
      </div>
    </div>
  );
}
