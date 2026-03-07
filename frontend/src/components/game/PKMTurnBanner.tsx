import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { turnBanner } from '../../utils/pkmAnimations';

interface PKMTurnBannerProps {
  isMyTurn: boolean;
  visible: boolean;
  onDismiss: () => void;
}

export default function PKMTurnBanner({ isMyTurn, visible, onDismiss }: PKMTurnBannerProps) {
  useEffect(() => {
    if (!visible) return;
    const timer = setTimeout(onDismiss, 1500);
    return () => clearTimeout(timer);
  }, [visible, onDismiss]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          key="turn-banner"
          variants={turnBanner}
          initial="initial"
          animate="animate"
          exit="exit"
          className="fixed top-8 left-1/2 -translate-x-1/2 z-50 px-8 py-4 rounded-xl
                     bg-gray-900/90 backdrop-blur-sm border border-gray-700
                     shadow-lg shadow-black/40"
          style={{
            borderBottomWidth: '3px',
            borderBottomColor: isMyTurn ? '#EAB308' : '#6B7280',
          }}
        >
          <p
            className={`text-lg font-bold text-center whitespace-nowrap ${
              isMyTurn ? 'text-yellow-400' : 'text-gray-400'
            }`}
          >
            {isMyTurn ? 'Your Turn!' : "Opponent's Turn"}
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
