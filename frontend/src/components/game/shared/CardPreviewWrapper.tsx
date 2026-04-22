/**
 * CardPreviewWrapper
 *
 * Conditional wrapper that attaches card preview bindings (hover + right-click
 * pin + long-press pin) to its children. Hooks must be called unconditionally,
 * so this is a component (not a helper function) — render it only when a
 * non-null card exists.
 *
 * Use this when a parent can't call `useCardPreviewBindings` directly because
 * the card may be null (e.g. zone slots in Yu-Gi-Oh!, Pokemon bench, etc.).
 */

import type { ReactNode } from 'react';
import { useCardPreviewBindings } from '../../../hooks/useCardPreview';
import type { CardData } from '../../../types';

interface CardPreviewWrapperProps {
  card: CardData;
  disabled?: boolean;
  className?: string;
  children: ReactNode;
}

export default function CardPreviewWrapper({
  card,
  disabled,
  className,
  children,
}: CardPreviewWrapperProps) {
  const previewProps = useCardPreviewBindings(card, { disabled });
  return (
    <span {...previewProps} className={className ?? 'inline-block'}>
      {children}
    </span>
  );
}
