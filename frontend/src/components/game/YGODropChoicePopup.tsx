/**
 * YGODropChoicePopup
 *
 * Small popup appearing after dropping a card on a YGO zone,
 * asking the player to choose between Summon/Set or Activate/Set.
 */

import { motion, AnimatePresence } from 'framer-motion';

interface YGODropChoicePopupProps {
  visible: boolean;
  cardName: string;
  choices: { label: string; action: () => void }[];
  onCancel: () => void;
  position?: { x: number; y: number };
}

export function YGODropChoicePopup({
  visible,
  cardName,
  choices,
  onCancel,
  position,
}: YGODropChoicePopupProps) {
  return (
    <AnimatePresence>
      {visible && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={onCancel}
          />
          {/* Popup */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ duration: 0.15 }}
            className="fixed z-50 bg-ygo-dark border-2 border-ygo-gold rounded-lg shadow-2xl shadow-ygo-gold/20 p-3 min-w-[160px]"
            style={
              position
                ? { left: position.x, top: position.y, transform: 'translate(-50%, -50%)' }
                : { left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }
            }
          >
            <div className="text-[10px] text-ygo-gold-dim uppercase tracking-wider mb-2 text-center truncate max-w-[180px]">
              {cardName}
            </div>
            <div className="flex flex-col gap-1.5">
              {choices.map((choice, i) => (
                <button
                  key={i}
                  onClick={(e) => {
                    e.stopPropagation();
                    choice.action();
                  }}
                  className="px-4 py-2 bg-ygo-gold/90 hover:bg-ygo-gold-bright text-ygo-dark font-bold text-sm rounded transition-colors"
                >
                  {choice.label}
                </button>
              ))}
              <button
                onClick={onCancel}
                className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs rounded transition-colors"
              >
                Cancel
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
