// A small set of flat, monochrome academic icons for a card's illustration
// panel. Hand-drawn (not from an icon library) — simple geometric shapes,
// currentColor throughout so the panel's accent color tints them.
import type { ReactElement } from 'react';

const common = {
  width: 56,
  height: 56,
  viewBox: '0 0 56 56',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2.2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

function Hierarchy() {
  return (
    <svg {...common}>
      <circle cx="28" cy="12" r="4.5" />
      <circle cx="12" cy="42" r="4.5" />
      <circle cx="28" cy="42" r="4.5" />
      <circle cx="44" cy="42" r="4.5" />
      <path d="M28 16.5V26M28 26 12 37.5M28 26v11.5M28 26 44 37.5" />
    </svg>
  );
}

function Calculator() {
  return (
    <svg {...common}>
      <rect x="14" y="8" width="28" height="40" rx="4" />
      <path d="M19 16h18M19 26h4M27 26h4M35 26h4M19 34h4M27 34h4M35 34h4M19 42h4M27 42h4M35 42h4" />
    </svg>
  );
}

function Sigma() {
  return (
    <svg {...common}>
      <path d="M16 12h22l-11 16 11 16H16" />
    </svg>
  );
}

function Manifold() {
  return (
    <svg {...common}>
      <ellipse cx="28" cy="28" rx="19" ry="10" />
      <path d="M9 28c0 8 8 15 19 15s19-7 19-15" strokeDasharray="2.6 3.4" />
    </svg>
  );
}

function BookIcon() {
  return (
    <svg {...common}>
      <path d="M28 14c-4-3-11-4-16-3v29c5-1 12 0 16 3 4-3 11-4 16-3V11c-5-1-12 0-16 3Z" />
      <path d="M28 14v29" />
    </svg>
  );
}

const ICONS: Record<string, () => ReactElement> = {
  hierarchy: Hierarchy,
  calculator: Calculator,
  sigma: Sigma,
  manifold: Manifold,
  book: BookIcon,
};

/** A card's illustration. `name` is the manifest's `icon:`; an unset or
 * unknown one falls back to `hierarchy` rather than rendering nothing — a card
 * with no `icon:` and no `image:` would otherwise show an empty gradient box,
 * which reads as a broken image rather than as a deliberate blank. */
export function Icon({ name }: { name?: string }) {
  const C = (name && ICONS[name]) || ICONS.hierarchy;
  return <C />;
}
