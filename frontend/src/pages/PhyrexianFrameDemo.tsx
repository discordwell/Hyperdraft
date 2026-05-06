/**
 * PhyrexianFrameDemo
 *
 * Storybook-style showcase for the Phyrexia Bedrock Edition card frame. Displays
 * one example of every variant in both compact and full sizes so the design
 * can be reviewed before generating real card art.
 */

import { useMemo, useState } from 'react';
import { PhyrexianCardFrame, resolveVariant } from '../components/game/PhyrexianCardFrame';
import type { CardData } from '../types';

// =============================================================================
// Sample cards
// =============================================================================

function makeSample(partial: Partial<CardData> & { name: string }): CardData {
  const { name, ...rest } = partial;
  return {
    id: name,
    name,
    domain: 'MC',
    mana_cost: null,
    types: [],
    subtypes: [],
    power: null,
    toughness: null,
    text: '',
    tapped: false,
    counters: {},
    damage: 0,
    controller: null,
    owner: null,
    keywords: [],
    ...rest,
  } as CardData;
}

const SAMPLES: CardData[] = [
  makeSample({
    name: 'Wolf Pack',
    types: ['MC_MOB'],
    subtypes: ['Animal'],
    power: 3,
    toughness: 2,
    text: 'Pack: gains +1 ATK for each other Worker you control.',
    mc_cost: { wood: 1, iron: 1 },
    mc_keywords: [],
  }),
  makeSample({
    name: 'Phyrexian Crusader',
    types: ['MC_MOB'],
    subtypes: ['Hostile', 'Compleated'],
    power: 3,
    toughness: 3,
    text: 'Compleated. Aerial + Infect.',
    mc_cost: { wood: 1, iron: 2 },
    mc_keywords: ['aerial', 'infect'],
  }),
  makeSample({
    name: 'Sheoldred, the Whispering One',
    types: ['MC_MOB'],
    subtypes: ['Hostile', 'Boss', 'Praetor', 'Compleated'],
    power: 5,
    toughness: 8,
    text: 'When played, drain 5 (deal 5 to opponent, heal 5).',
    mc_cost: { wood: 1, iron: 2, redstone: 2 },
    mc_keywords: [],
  }),
  makeSample({
    name: 'Ender Dragon',
    types: ['MC_MOB'],
    subtypes: ['Hostile', 'Boss', 'End'],
    power: 9,
    toughness: 9,
    text: 'Aerial — ignores Blocks.',
    mc_cost: { redstone: 2, diamond: 4 },
    mc_keywords: ['aerial'],
  }),
  makeSample({
    name: 'Realmbreaker Spire',
    types: ['MC_STRUCTURE'],
    subtypes: ['Structure', 'Spire'],
    power: null,
    toughness: 8,
    text: 'Start of turn: gain 1 of every material.',
    mc_cost: { stone: 3, diamond: 2 },
    mc_keywords: [],
  }),
  makeSample({
    name: 'Cobblestone Wall',
    types: ['MC_BLOCK'],
    subtypes: ['Block', 'Wall'],
    power: null,
    toughness: 6,
    text: 'Wall — soaks damage in its column.',
    mc_cost: { stone: 2 },
    mc_keywords: [],
  }),
  makeSample({
    name: 'Phyrexian Sword',
    types: ['MC_TOOL'],
    subtypes: ['Weapon', 'Gear'],
    power: null,
    toughness: null,
    text: 'Avatar attack deals 5. Infect.',
    mc_cost: { iron: 1, redstone: 1 },
    mc_keywords: ['infect'],
  }),
  makeSample({
    name: "Herobrine, World's Eye",
    types: ['MC_MOB'],
    subtypes: ['Hostile', 'Boss'],
    power: 7,
    toughness: 7,
    text:
      'Aerial. When played, destroy any 1 mob. "This is _my_ world."',
    mc_cost: { iron: 2, redstone: 1, diamond: 3 },
    mc_keywords: ['aerial'],
  }),
  makeSample({
    name: 'Glistening Oil',
    types: ['MC_ACTION'],
    subtypes: ['Action'],
    power: null,
    toughness: null,
    text: 'Compleate target enemy mob with HP ≤ 2 — it joins your side.',
    mc_cost: { redstone: 1 },
    mc_keywords: [],
  }),
  makeSample({
    name: 'Phyrexian Rebirth',
    types: ['MC_ACTION'],
    subtypes: ['Action'],
    power: null,
    toughness: null,
    text: 'Destroy every mob in the battle row, then create a 4/4 Phyrexian Horror.',
    mc_cost: { stone: 1, iron: 2, redstone: 2 },
    mc_keywords: [],
  }),
];

// =============================================================================
// Page
// =============================================================================

export function PhyrexianFrameDemo() {
  const [size, setSize] = useState<'full' | 'compact'>('full');

  const grouped = useMemo(() => {
    const order = ['mob', 'compleated', 'praetor', 'boss', 'structure', 'block', 'tool', 'action'];
    const seen = new Map<string, CardData[]>();
    for (const c of SAMPLES) {
      const v = resolveVariant(c);
      seen.set(v, [...(seen.get(v) || []), c]);
    }
    return order
      .map((v) => ({ variant: v, cards: seen.get(v) || [] }))
      .filter((g) => g.cards.length > 0);
  }, []);

  return (
    <div className="min-h-screen bg-[#0a0608] text-stone-100">
      {/* Hero band */}
      <header
        className="relative overflow-hidden border-b border-red-900/60"
        style={{
          background:
            'radial-gradient(circle at 20% 0%, rgba(180,40,50,0.18) 0%, transparent 38%),' +
            'radial-gradient(circle at 80% 100%, rgba(80,180,40,0.10) 0%, transparent 42%),' +
            'linear-gradient(180deg, #110608 0%, #06030a 100%)',
        }}
      >
        <div className="max-w-6xl mx-auto px-6 py-10 relative">
          <p className="phx-mono text-xs tracking-[0.4em] text-red-300/80 uppercase mb-2">
            Phyrexia Bedrock Edition · frame design v1
          </p>
          <h1
            className="text-4xl md:text-5xl mb-2"
            style={{
              fontFamily: "'UnifrakturCook', 'Cinzel', serif",
              background: 'linear-gradient(180deg, #f4d068 0%, #c8742c 60%, #5a1010 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.8))',
            }}
          >
            Phyrexian Foundry — Card Chrome
          </h1>
          <p className="text-stone-400 max-w-2xl phx-rules text-base leading-snug">
            Industrial-occult voxel frames forged from oil-slicked steel. Seam glow shifts by card class:
            crimson runes for mortal mobs, sickly-green ichor for the Compleated, gold for the Praetors who
            command them, stone-blue for Overworld architecture, bronze for arms, scorched parchment for
            actions. The chrome is meant to make any portrait of generated art feel pulled out of the
            same desecrated forge.
          </p>
          <div className="mt-6 inline-flex p-1 border border-red-900/60 bg-black/40 rounded-sm">
            {(['full', 'compact'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSize(s)}
                className={`px-4 py-1.5 phx-mono text-sm tracking-[0.2em] uppercase transition ${
                  size === s
                    ? 'bg-red-900/70 text-amber-200 shadow-inner'
                    : 'text-stone-400 hover:text-stone-100'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* Variant gallery */}
      <main className="max-w-6xl mx-auto px-6 py-10 space-y-12">
        {grouped.map(({ variant, cards }) => (
          <section key={variant}>
            <div className="flex items-baseline justify-between mb-4 border-b border-red-900/40 pb-2">
              <h2
                className="text-2xl uppercase phx-name"
                style={{ color: VARIANT_HEADING_COLOR[variant] || '#d83242', letterSpacing: '0.18em' }}
              >
                {variant}
              </h2>
              <p className="phx-rules text-stone-400 italic text-sm max-w-md text-right">
                {VARIANT_BLURB[variant]}
              </p>
            </div>
            <div className="flex flex-wrap items-end gap-8">
              {cards.map((c) => (
                <div key={c.id} className="flex flex-col items-center gap-2">
                  <PhyrexianCardFrame card={c} size={size} />
                  <span className="phx-mono text-xs uppercase tracking-[0.18em] text-stone-500">
                    {c.name}
                  </span>
                </div>
              ))}
            </div>
          </section>
        ))}

        <footer className="border-t border-red-900/40 pt-8 mt-12 phx-rules text-stone-500 text-sm">
          <p>
            Each variant maps to <code className="phx-mono text-amber-300">resolveVariant(card)</code> in
            <code className="phx-mono text-amber-300"> PhyrexianCardFrame.tsx</code>.
            Once art generation finishes, the auto-wired <code className="phx-mono text-amber-300">image_url</code>
            replaces the voxel placeholder; the frame chrome stays identical.
          </p>
        </footer>
      </main>
    </div>
  );
}

const VARIANT_HEADING_COLOR: Record<string, string> = {
  mob: '#d83242',
  compleated: '#76c83c',
  praetor: '#f0c860',
  boss: '#e64a3a',
  structure: '#92a8c0',
  block: '#bcbcc0',
  tool: '#c79560',
  action: '#e84252',
};

const VARIANT_BLURB: Record<string, string> = {
  mob: 'Mortal Overworld creatures — obsidian plate, crimson rune-seams, riveted corners.',
  compleated: 'Flesh-machine fusions. Oil-slick overlay, sickly-green seams, ichor leaking from the top edge.',
  praetor: 'Phyrexian overlords. Heavier voxel step, cracked-gold halo crown above the name plate.',
  boss: 'Multi-block legendary entities. Wider stepped frame, fire-tinted obsidian, aggressive accent.',
  structure: 'Architectural permanents. Stone-blue plate, cooler hue, the tower-cornice motif up top.',
  block: 'Grid defenders. Heavy uniform stone, plain rivets, grim utility.',
  tool: 'Avatar gear. Bronze-and-leather plate, weapon-rack proportions, no stat box.',
  action: 'One-shot rituals. Torn-edge clip, scorched parchment radiating crimson embers.',
};

export default PhyrexianFrameDemo;
