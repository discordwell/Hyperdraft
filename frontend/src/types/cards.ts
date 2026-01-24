/**
 * Card Definition Types
 */

export type CardType =
  | 'CREATURE'
  | 'INSTANT'
  | 'SORCERY'
  | 'ENCHANTMENT'
  | 'ARTIFACT'
  | 'LAND'
  | 'PLANESWALKER';

export type Color =
  | 'WHITE'
  | 'BLUE'
  | 'BLACK'
  | 'RED'
  | 'GREEN'
  | 'COLORLESS';

export interface CardDefinitionData {
  name: string;
  mana_cost: string | null;
  types: CardType[];
  subtypes: string[];
  power: number | null;
  toughness: number | null;
  text: string;
  colors: Color[];
}

export interface CardListResponse {
  cards: CardDefinitionData[];
  total: number;
}

// Mana cost parsing helpers
export function parseManaSymbols(manaCost: string | null): string[] {
  if (!manaCost) return [];

  const symbols: string[] = [];
  const regex = /\{([^}]+)\}/g;
  let match;

  while ((match = regex.exec(manaCost)) !== null) {
    symbols.push(match[1]);
  }

  return symbols;
}

export function getColorFromSymbol(symbol: string): Color | null {
  const colorMap: Record<string, Color> = {
    'W': 'WHITE',
    'U': 'BLUE',
    'B': 'BLACK',
    'R': 'RED',
    'G': 'GREEN',
    'C': 'COLORLESS',
  };
  return colorMap[symbol] || null;
}

export function getTotalManaValue(manaCost: string | null): number {
  if (!manaCost) return 0;

  const symbols = parseManaSymbols(manaCost);
  let total = 0;

  for (const symbol of symbols) {
    const num = parseInt(symbol, 10);
    if (!isNaN(num)) {
      total += num;
    } else {
      total += 1; // Colored mana costs 1
    }
  }

  return total;
}
