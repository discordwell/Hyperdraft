/**
 * YGOTurnBanner
 *
 * Displays "It's Your Move!" or "Opponent's Move" with auto-dismiss.
 * Dark + Gold themed.
 */

import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { turnBanner } from '../../utils/ygoAnimations';

interface YGOTurnBannerProps {
  isMyTurn: boolean;
  visible: boolean;
  onDismiss: () => void;
}

export default function YGOTurnBanner({ isMyTurn, visible, onDismiss }: YGOTurnBannerProps) {
  useEffect(() => {
    if (!visible) return;
    const timer = setTimeout(onDismiss, 1500);
    return () => clearTimeout(timer);
  }, [visible, onDismiss]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          key="ygo-turn-banner"
          variants={turnBanner}
          initial="initial"
          animate="animate"
          exit="exit"
          className="fixed top-8 left-1/2 -translate-x-1/2 z-50 px-10 py-4 rounded-xl
                     bg-ygo-dark/90 backdrop-blur-sm border border-ygo-gold-dim/50
                     shadow-lg shadow-black/50"
          style={{
            borderBottomWidth: '3px',
            borderBottomColor: isMyTurn ? '#d4a843' : '#4b5563',
          }}
        >
          <p
            className={`text-lg font-bold text-center whitespace-nowrap tracking-wide ${
              isMyTurn ? 'text-ygo-gold-bright' : 'text-gray-400'
            }`}
          >
            {isMyTurn ? "It's Your Move!" : "Opponent's Move"}
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
