/**
 * PKMPrizeCards - 6-slot prize card display.
 *
 * Shows face-down prize cards with animation when a prize is taken.
 */

import { motion, AnimatePresence } from 'framer-motion';
import { springSnappy } from '../../utils/pkmAnimations';

interface PKMPrizeCardsProps {
  total: number;      // Always 6
  remaining: number;  // Prizes left
  isOpponent?: boolean;
  compact?: boolean;
}

export function PKMPrizeCards({ total = 6, remaining, isOpponent = false, compact = false }: PKMPrizeCardsProps) {
  const size = compact ? 'w-4 h-5' : 'w-5 h-7';
  const gap = compact ? 'gap-0.5' : 'gap-1';

  return (
    <div className={`flex items-center ${gap}`}>
      <span className={`text-yellow-400 font-bold mr-1 ${compact ? 'text-[9px]' : 'text-xs'}`}>
        Prizes
      </span>
      <AnimatePresence mode="popLayout">
        {Array.from({ length: total }).map((_, i) => {
          const isPresent = i < remaining;
          return (
            <motion.div
              key={`prize-${i}`}
              layout
              initial={false}
              animate={{
                scale: isPresent ? 1 : 0.6,
                opacity: isPresent ? 1 : 0.3,
              }}
              transition={springSnappy}
              className={`${size} rounded-sm ${
                isPresent
                  ? isOpponent
                    ? 'bg-red-700 border border-red-500'
                    : 'bg-yellow-500 border border-yellow-300'
                  : 'bg-gray-700 border border-gray-600'
              }`}
            />
          );
        })}
      </AnimatePresence>
    </div>
  );
}
