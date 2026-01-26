/**
 * Icon Components
 *
 * Clean, consistent SVG icons for game actions and UI elements.
 */

import clsx from 'clsx';

interface IconProps {
  className?: string;
  size?: 'xs' | 'sm' | 'md' | 'lg';
}

const sizeClasses = {
  xs: 'w-3 h-3',
  sm: 'w-4 h-4',
  md: 'w-5 h-5',
  lg: 'w-6 h-6',
};

// Cast/Spell icon - magic sparkles
export function CastIcon({ className, size = 'md' }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={clsx(sizeClasses[size], className)}
    >
      <path d="M12 3v1m0 16v1m-8-9H3m18 0h-1M5.6 5.6l.7.7m12.4 12.4l.7.7m0-13.8l-.7.7M6.3 18.7l-.7.7" />
      <circle cx="12" cy="12" r="4" />
    </svg>
  );
}

// Play Land icon - mountain/land shape
export function PlayLandIcon({ className, size = 'md' }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={clsx(sizeClasses[size], className)}
    >
      <path d="M2 20h20" />
      <path d="M5 20L8.5 9l3.5 5 4-7 6 13" />
    </svg>
  );
}

// Attack/Sword icon
export function AttackIcon({ className, size = 'md' }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={clsx(sizeClasses[size], className)}
    >
      <path d="M14.5 17.5L3 6V3h3l11.5 11.5" />
      <path d="M13 19l6-6" />
      <path d="M16 16l4 4" />
      <path d="M19 21l2-2" />
    </svg>
  );
}

// Block/Shield icon
export function BlockIcon({ className, size = 'md' }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={clsx(sizeClasses[size], className)}
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

// Creature icon - crossed swords
export function CreatureIcon({ className, size = 'md' }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={clsx(sizeClasses[size], className)}
    >
      <path d="M14.5 17.5L3 6V3h3l11.5 11.5" />
      <path d="M13 19l6-6M16 16l4 4M19 21l2-2" />
      <path d="M9.5 6.5L21 18v3h-3L6.5 9.5" />
      <path d="M5 19l6-6M5 21l-2-2" />
    </svg>
  );
}

// Other permanents icon - crystal/artifact
export function ArtifactIcon({ className, size = 'md' }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={clsx(sizeClasses[size], className)}
    >
      <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2" />
      <line x1="12" y1="22" x2="12" y2="8.5" />
      <line x1="22" y1="8.5" x2="12" y2="8.5" />
      <line x1="2" y1="8.5" x2="12" y2="8.5" />
    </svg>
  );
}

// User/Player icon
export function PlayerIcon({ className, size = 'md' }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={clsx(sizeClasses[size], className)}
    >
      <circle cx="12" cy="8" r="4" />
      <path d="M20 21a8 8 0 1 0-16 0" />
    </svg>
  );
}

// Gamepad/Controller icon
export function GamepadIcon({ className, size = 'md' }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={clsx(sizeClasses[size], className)}
    >
      <rect x="2" y="6" width="20" height="12" rx="2" />
      <path d="M6 12h4M8 10v4" />
      <circle cx="17" cy="10" r="1" fill="currentColor" />
      <circle cx="15" cy="12" r="1" fill="currentColor" />
    </svg>
  );
}

// Target icon
export function TargetIcon({ className, size = 'md' }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={clsx(sizeClasses[size], className)}
    >
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" />
    </svg>
  );
}

export default {
  CastIcon,
  PlayLandIcon,
  AttackIcon,
  BlockIcon,
  CreatureIcon,
  ArtifactIcon,
  PlayerIcon,
  GamepadIcon,
  TargetIcon,
};
