/**
 * Mana Cost Display Component
 *
 * Renders mana cost symbols as styled circular pips.
 * Supports different sizes for grid cards vs detail views.
 */

interface ManaSymbolStyle {
  bg: string;
  text: string;
}

/**
 * Get Tailwind classes for a mana symbol.
 */
export function getManaSymbolStyle(symbol: string): ManaSymbolStyle {
  const inner = symbol.replace(/[{}]/g, '').toUpperCase();

  const styles: Record<string, ManaSymbolStyle> = {
    W: { bg: 'bg-amber-100', text: 'text-amber-900' },
    U: { bg: 'bg-blue-500', text: 'text-white' },
    B: { bg: 'bg-gray-800', text: 'text-white' },
    R: { bg: 'bg-red-500', text: 'text-white' },
    G: { bg: 'bg-green-600', text: 'text-white' },
    C: { bg: 'bg-gray-400', text: 'text-gray-900' },
  };

  // Hybrid mana (e.g., W/U)
  if (inner.includes('/')) {
    return { bg: 'bg-gradient-to-br from-amber-200 to-blue-400', text: 'text-gray-900' };
  }

  // Generic mana (numbers)
  if (/^\d+$/.test(inner)) {
    return { bg: 'bg-gray-300', text: 'text-gray-800' };
  }

  // X mana
  if (inner === 'X') {
    return { bg: 'bg-gray-400', text: 'text-gray-900' };
  }

  return styles[inner] || { bg: 'bg-gray-400', text: 'text-gray-900' };
}

/**
 * Parse mana cost string into array of symbols.
 */
export function parseManaSymbols(manaCost: string | null): string[] {
  if (!manaCost) return [];
  return manaCost.match(/\{[^}]+\}/g) || [];
}

type ManaCostSize = 'sm' | 'md' | 'lg';

const SIZE_CLASSES: Record<ManaCostSize, { container: string; symbol: string; text: string }> = {
  sm: {
    container: 'gap-0.5',
    symbol: 'w-5 h-5',
    text: 'text-[10px]',
  },
  md: {
    container: 'gap-1',
    symbol: 'w-6 h-6',
    text: 'text-xs',
  },
  lg: {
    container: 'gap-1',
    symbol: 'w-7 h-7',
    text: 'text-sm',
  },
};

interface ManaCostDisplayProps {
  manaCost: string | null;
  size?: ManaCostSize;
  maxSymbols?: number;
}

export function ManaCostDisplay({ manaCost, size = 'sm', maxSymbols = 8 }: ManaCostDisplayProps) {
  if (!manaCost) return null;

  const symbols = parseManaSymbols(manaCost);
  const sizeClasses = SIZE_CLASSES[size];
  const displaySymbols = symbols.slice(0, maxSymbols);
  const overflow = symbols.length - maxSymbols;

  return (
    <div className={`flex ${sizeClasses.container}`}>
      {displaySymbols.map((symbol, i) => {
        const style = getManaSymbolStyle(symbol);
        const inner = symbol.replace(/[{}]/g, '');
        return (
          <span
            key={i}
            className={`${sizeClasses.symbol} rounded-full flex items-center justify-center ${sizeClasses.text} font-bold ${style.bg} ${style.text} shadow-sm`}
            title={symbol}
          >
            {inner}
          </span>
        );
      })}
      {overflow > 0 && (
        <span className={`${sizeClasses.text} text-gray-500`}>+{overflow}</span>
      )}
    </div>
  );
}

export default ManaCostDisplay;
