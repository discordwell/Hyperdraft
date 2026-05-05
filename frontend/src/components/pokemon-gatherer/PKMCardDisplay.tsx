/**
 * PKMCardDisplay
 *
 * Pure presentational component that renders a PokemonCardData. Used
 * by the Pokemon Gatherer's detail modal. Has no in-game state
 * dependencies (damage counters, attached energy, status conditions
 * etc. live on the gameplay-side PKMCardDetailPanel).
 */

import type { PokemonCardData } from '../../types/pokemonGatherer';
import { POKEMON_TYPE_INFO } from '../../types/pokemonGatherer';

const TYPE_BADGE_MAP: Record<string, string> = {
  G: 'bg-green-600 text-white',
  R: 'bg-red-600 text-white',
  W: 'bg-blue-600 text-white',
  L: 'bg-yellow-500 text-black',
  P: 'bg-purple-600 text-white',
  F: 'bg-orange-600 text-white',
  D: 'bg-gray-800 text-white',
  M: 'bg-gray-500 text-white',
  C: 'bg-gray-400 text-black',
};

function EnergyDot({ type }: { type: string }) {
  const info = POKEMON_TYPE_INFO[type] || POKEMON_TYPE_INFO.C;
  return (
    <span
      className="inline-block w-4 h-4 rounded-full border border-black/30 flex-shrink-0"
      style={{ background: info.color }}
      title={info.label}
    />
  );
}

function AttackCost({ cost }: { cost: { type: string; count: number }[] }) {
  if (!cost.length) {
    return <span className="text-gray-500 text-xs italic">No cost</span>;
  }
  const dots: React.ReactNode[] = [];
  cost.forEach((entry, i) => {
    for (let j = 0; j < entry.count; j++) {
      dots.push(<EnergyDot key={`${i}-${j}`} type={entry.type} />);
    }
  });
  return <span className="flex items-center gap-0.5">{dots}</span>;
}

function TypeBadge({ type }: { type: string }) {
  const info = POKEMON_TYPE_INFO[type];
  if (!info) return null;
  const cls = TYPE_BADGE_MAP[type] ?? 'bg-gray-600 text-white';
  return (
    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded ${cls}`}>
      {info.label}
    </span>
  );
}

function SupertypeBadge({
  supertype,
  trainerSubtype,
}: {
  supertype: string;
  trainerSubtype: string | null;
}) {
  const label =
    supertype === 'Trainer' && trainerSubtype
      ? `${supertype} · ${trainerSubtype}`
      : supertype;
  const bg =
    supertype === 'Pokemon'
      ? 'bg-amber-700/80 text-white'
      : supertype === 'Trainer'
        ? 'bg-sky-700/80 text-white'
        : 'bg-emerald-700/80 text-white';
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded ${bg}`}>
      {label}
    </span>
  );
}

interface Props {
  card: PokemonCardData;
}

export function PKMCardDisplay({ card }: Props) {
  return (
    <div className="space-y-3 text-sm text-gray-100">
      {card.image_url && (
        <img
          src={card.image_url}
          alt={card.name}
          className="w-full max-h-[320px] object-contain rounded-lg bg-black/40"
        />
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xl font-bold text-white flex-1 min-w-0 truncate">
          {card.name}
        </span>
        {card.is_ex && (
          <span className="text-[10px] font-bold bg-yellow-500 text-black px-1.5 py-0.5 rounded uppercase tracking-wide">
            EX
          </span>
        )}
        {card.pokemon_type && card.supertype === 'Pokemon' && (
          <TypeBadge type={card.pokemon_type} />
        )}
        {card.energy_type && card.supertype === 'Energy' && (
          <TypeBadge type={card.energy_type} />
        )}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <SupertypeBadge supertype={card.supertype} trainerSubtype={card.trainer_subtype} />
        {card.evolution_stage && (
          <span className="text-xs text-gray-400">{card.evolution_stage}</span>
        )}
        {card.evolves_from && (
          <span className="text-xs text-gray-400">
            from <span className="text-gray-200">{card.evolves_from}</span>
          </span>
        )}
        {card.guild && (
          <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-fuchsia-700/80 text-white">
            {card.guild}
          </span>
        )}
        {card.rarity && (
          <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-gray-600/70 text-white">
            {card.rarity}
          </span>
        )}
      </div>

      {card.hp != null && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400">HP</span>
          <span className="text-2xl font-bold text-white tabular-nums">
            {card.hp}
          </span>
        </div>
      )}

      {card.ability && (
        <div className="bg-red-900/30 border border-red-800/40 rounded-lg p-2.5">
          <div className="flex items-center gap-1.5 mb-1">
            <span className="text-[10px] font-bold bg-red-700 text-white px-1.5 py-0.5 rounded uppercase">
              {card.ability.ability_type ?? 'Ability'}
            </span>
            <span className="font-semibold text-red-200">
              {card.ability.name}
            </span>
          </div>
          {card.ability.text && (
            <p className="text-gray-300 text-xs leading-relaxed">
              {card.ability.text}
            </p>
          )}
        </div>
      )}

      {card.attacks.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-gray-500 text-[10px] uppercase tracking-wider font-semibold">
            Attacks
          </div>
          {card.attacks.map((atk, i) => (
            <div key={i} className="bg-gray-800/60 rounded-lg p-2 space-y-1">
              <div className="flex items-center gap-2">
                <AttackCost cost={atk.cost} />
                <span className="font-semibold text-white flex-1 truncate">
                  {atk.name}
                </span>
                {atk.damage != null && atk.damage > 0 && (
                  <span className="text-yellow-400 font-bold text-base">
                    {atk.damage}
                  </span>
                )}
              </div>
              {atk.text && (
                <p className="text-gray-300 text-xs leading-relaxed">
                  {atk.text}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {card.supertype === 'Pokemon' &&
        (card.weakness_type || card.resistance_type || card.retreat_cost != null) && (
          <div className="flex items-center gap-4 text-xs flex-wrap">
            {card.weakness_type && (
              <div className="flex items-center gap-1.5">
                <span className="text-gray-500">Weakness</span>
                <EnergyDot type={card.weakness_type} />
                <span className="text-gray-300">{card.weakness_modifier ?? 'x2'}</span>
              </div>
            )}
            {card.resistance_type && (
              <div className="flex items-center gap-1.5">
                <span className="text-gray-500">Resistance</span>
                <EnergyDot type={card.resistance_type} />
                <span className="text-gray-300">
                  {card.resistance_modifier ?? -30}
                </span>
              </div>
            )}
            {card.retreat_cost != null && (
              <div className="flex items-center gap-1.5">
                <span className="text-gray-500">Retreat</span>
                {card.retreat_cost === 0 ? (
                  <span className="text-green-400 font-semibold">Free</span>
                ) : (
                  <span className="flex gap-0.5">
                    {Array.from({ length: card.retreat_cost }).map((_, i) => (
                      <EnergyDot key={i} type="C" />
                    ))}
                  </span>
                )}
              </div>
            )}
          </div>
        )}

      {card.text && (card.supertype !== 'Pokemon' || card.attacks.length === 0) && (
        <p className="text-gray-300 text-xs leading-relaxed italic">{card.text}</p>
      )}

      {card.rule_box && (
        <div className="text-[11px] text-gray-400 italic border-t border-gray-700 pt-2">
          {card.rule_box}
        </div>
      )}

      {card.is_ex && card.prize_count != null && card.prize_count > 1 && (
        <div className="text-yellow-500 text-xs">
          Worth {card.prize_count} prize cards when KO'd
        </div>
      )}
    </div>
  );
}

export default PKMCardDisplay;
