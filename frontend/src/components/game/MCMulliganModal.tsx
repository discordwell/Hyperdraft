import type { CardData } from '../../types/game';

interface MulliganPrompt {
  mulligan_count: number;
  hand_size_after_keep: number;
  cost_for_next: number;
}

interface Props {
  prompt: MulliganPrompt;
  hand: CardData[];
  onKeep: () => void;
  onMulligan: () => void;
}

export function MCMulliganModal({ prompt, hand, onKeep, onMulligan }: Props) {
  const { mulligan_count, hand_size_after_keep, cost_for_next } = prompt;
  const isFirstDraw = mulligan_count === 0;
  const nextCostLabel = cost_for_next === 0 ? 'free' : `−${cost_for_next} card${cost_for_next === 1 ? '' : 's'}`;
  const keepLabel = hand_size_after_keep === 6
    ? 'Keep this hand (6 cards)'
    : `Keep this hand (${hand_size_after_keep} cards — pay ${6 - hand_size_after_keep} to bottom of library)`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 px-4">
      <div className="w-full max-w-3xl border-2 border-emerald-600 bg-slate-950 p-6 shadow-2xl">
        <div className="mb-1 text-xs uppercase tracking-[0.2em] text-emerald-400">
          {isFirstDraw ? 'Opening hand' : `Mulligan #${mulligan_count}`}
        </div>
        <h2 className="mb-3 font-bold text-2xl text-stone-100">
          Keep your hand or mulligan?
        </h2>
        <p className="mb-4 text-sm text-stone-400">
          {isFirstDraw
            ? 'Your first mulligan is free. Each subsequent mulligan costs one card off the top of your kept hand (placed on the bottom of your library).'
            : `Mulliganing again costs your next decision ${nextCostLabel}. Keeping now puts ${
                6 - hand_size_after_keep
              } card${6 - hand_size_after_keep === 1 ? '' : 's'} on the bottom of your library.`}
        </p>

        <div className="mb-5 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-6">
          {hand.length === 0 ? (
            <div className="col-span-full rounded border border-slate-800 bg-slate-900 p-4 text-center text-sm text-slate-500">
              Hand is empty.
            </div>
          ) : (
            hand.map((card) => (
              <div
                key={card.id}
                className="border border-slate-700 bg-slate-900 p-2 text-xs text-stone-200"
                title={card.text || card.name}
              >
                <div className="truncate font-bold text-emerald-300">{card.name}</div>
                <div className="mt-0.5 text-[10px] uppercase tracking-wide text-stone-500">
                  {(card.types || []).join(', ')}
                </div>
                {card.power != null && card.toughness != null && (
                  <div className="mt-1 text-[11px] text-stone-300">
                    {card.power}/{card.toughness}
                  </div>
                )}
                {card.text && (
                  <div className="mt-1 line-clamp-3 text-[10px] text-stone-400">
                    {card.text}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        <div className="flex flex-wrap justify-end gap-2">
          <button
            onClick={onMulligan}
            className="border border-amber-600 bg-amber-900/30 px-4 py-2 text-sm font-bold text-amber-200 transition hover:bg-amber-900/60"
          >
            Mulligan ({nextCostLabel})
          </button>
          <button
            onClick={onKeep}
            className="border border-emerald-600 bg-emerald-700 px-4 py-2 text-sm font-bold text-white transition hover:bg-emerald-600"
          >
            {keepLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export default MCMulliganModal;
