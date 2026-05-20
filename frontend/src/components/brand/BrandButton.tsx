/**
 * BrandButton — primary (foil) and secondary (outlined) actions.
 *
 * The primary variant is a foil-stamped pill: aged-gold gradient face with
 * a darker rim and a subtle inner highlight. Hover pushes the gradient
 * brighter; active sinks slightly. Secondary is a hairline-outline pill
 * with a cream label that brightens on hover.
 */

import { ButtonHTMLAttributes, ReactNode, forwardRef } from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

export interface BrandButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  leading?: ReactNode;
  trailing?: ReactNode;
  /** Visual loading state — disables click and shows spinner glyph. */
  loading?: boolean;
}

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'h-9 px-3.5 text-[13px]',
  md: 'h-11 px-5 text-sm',
  lg: 'h-13 px-7 text-[15px]',
};

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    'bg-gradient-to-b from-brand-foil-bright via-brand-foil to-brand-foil-deep ' +
    'text-brand-ink shadow-brand-foil ' +
    'hover:shadow-brand-foil-strong hover:from-[#f6db95] hover:via-[#d8b25b] ' +
    'active:translate-y-[1px]',
  secondary:
    'bg-brand-shelf/60 text-brand-cream border border-brand-hairline ' +
    'hover:border-brand-foil/50 hover:bg-brand-shelf hover:text-brand-foil-bright ' +
    'active:translate-y-[1px]',
  ghost:
    'bg-transparent text-brand-chalk border border-transparent ' +
    'hover:text-brand-cream hover:bg-brand-shelf/60',
  danger:
    'bg-brand-ember/10 text-brand-ember border border-brand-ember/40 ' +
    'hover:bg-brand-ember/20 hover:border-brand-ember',
};

export const BrandButton = forwardRef<HTMLButtonElement, BrandButtonProps>(
  ({ variant = 'primary', size = 'md', leading, trailing, loading, className, children, disabled, ...rest }, ref) => {
    const isDisabled = disabled || loading;
    return (
      <button
        ref={ref}
        disabled={isDisabled}
        className={
          'relative inline-flex items-center justify-center gap-2 font-medium ' +
          'tracking-wide rounded-none border-none transition-all ' +
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-foil/70 ' +
          'disabled:opacity-50 disabled:cursor-not-allowed ' +
          'before:absolute before:inset-x-0 before:top-0 before:h-[1px] ' +
          'before:bg-gradient-to-r before:from-transparent before:via-white/20 before:to-transparent ' +
          'before:opacity-50 before:pointer-events-none ' +
          SIZE_CLASSES[size] + ' ' +
          VARIANT_CLASSES[variant] + ' ' +
          (className ?? '')
        }
        {...rest}
      >
        {loading && (
          <span
            className="inline-block w-4 h-4 border-2 border-current border-r-transparent rounded-full animate-spin"
            aria-hidden
          />
        )}
        {!loading && leading}
        <span>{children}</span>
        {!loading && trailing}
      </button>
    );
  },
);

BrandButton.displayName = 'BrandButton';

export default BrandButton;
