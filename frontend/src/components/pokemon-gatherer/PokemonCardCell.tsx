/**
 * PokemonCardCell
 *
 * Compact card thumbnail for the Pokemon gatherer grid. Uses image_url
 * when available; otherwise falls back to a text card with HP, type
 * badge, and one-line snippet.
 */

import type { PokemonCardData } from '../../types/pokemonGatherer';
import { POKEMON_TYPE_INFO } from '../../types/pokemonGatherer';

interface Props {
  card: PokemonCardData;
  onClick: () => void;
}

const SUPERTYPE_BG: Record<string, string> = {
  Pokemon: 'from-amber-900/40 to-amber-800/20 border-amber-700/40',
  Trainer: 'from-sky-900/40 to-sky-800/20 border-sky-700/40',
  Energy: 'from-emerald-900/40 to-emerald-800/20 border-emerald-700/40',
};

export function PokemonCardCell({ card, onClick }: Props) {
  if (card.image_url) {
    return (
      <button
        onClick={onClick}
        className="group relative aspect-[245/342] overflow-hidden rounded-lg bg-black/30 border border-gray-700 hover:border-game-accent transition-all hover:scale-[1.03]"
        title={card.name}
      >
        <img
          src={card.image_url}
          alt={card.name}
          loading="lazy"
          className="w-full h-full object-cover"
        />
        {card.is_ex && (
          <span className="absolute top-1 right-1 text-[10px] font-bold bg-yellow-500 text-black px-1.5 py-0.5 rounded uppercase tracking-wide">
            EX
          </span>
        )}
      </button>
    );
  }

  const typeInfo =
    card.pokemon_type ? POKEMON_TYPE_INFO[card.pokemon_type] : null;
  const supertypeBg = SUPERTYPE_BG[card.supertype] ?? 'from-gray-900/40 to-gray-800/20 border-gray-700/40';

  return (
    <button
      onClick={onClick}
      className={`group relative aspect-[245/342] overflow-hidden rounded-lg bg-gradient-to-b ${supertypeBg} border hover:border-game-accent transition-all hover:scale-[1.03] p-3 text-left flex flex-col`}
      title={card.name}
    >
      <div className="flex items-start justify-between gap-1">
        <span className="font-bold text-white text-sm leading-tight line-clamp-2 flex-1">
          {card.name}
        </span>
        {card.hp != null && (
          <span className="text-[11px] font-bold text-white tabular-nums whitespace-nowrap">
            HP {card.hp}
          </span>
        )}
      </div>

      {card.evolution_stage && (
        <div className="text-[10px] text-gray-300 mt-0.5">
          {card.evolution_stage}
          {card.evolves_from && (
            <span className="text-gray-400"> · from {card.evolves_from}</span>
          )}
        </div>
      )}

      {typeInfo && (
        <div className="flex items-center gap-1 mt-1.5">
          <span
            className="w-3 h-3 rounded-full border border-black/30"
            style={{ background: typeInfo.color }}
          />
          <span className="text-[10px] text-gray-200">{typeInfo.label}</span>
          {card.is_ex && (
            <span className="text-[9px] font-bold bg-yellow-500 text-black px-1 rounded uppercase ml-auto">
              EX
            </span>
          )}
        </div>
      )}

      {card.supertype === 'Trainer' && (
        <div className="text-[10px] text-sky-200 mt-1.5">
          Trainer{card.trainer_subtype ? ` · ${card.trainer_subtype}` : ''}
        </div>
      )}

      {card.supertype === 'Energy' && (
        <div className="text-[10px] text-emerald-200 mt-1.5">Energy</div>
      )}

      <div className="mt-auto pt-2 text-[10px] text-gray-300 line-clamp-3 leading-snug">
        {card.attacks[0]
          ? `${card.attacks[0].name}${card.attacks[0].damage ? ` · ${card.attacks[0].damage}` : ''}`
          : card.text || ''}
      </div>

      {card.guild && (
        <div className="absolute bottom-1 right-1 text-[9px] uppercase tracking-wider px-1 py-0.5 rounded bg-fuchsia-700/80 text-white">
          {card.guild}
        </div>
      )}
    </button>
  );
}

export default PokemonCardCell;
