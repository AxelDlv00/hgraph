// One accent "theme" per category, assigned in order of first appearance and
// cycled if there are more categories than themes — so a two-category
// workspace gets exactly the purple/teal pairing from the design reference,
// and a bigger one still gets a distinct, tasteful color per section.
export interface Theme {
  accent: string;
  accentDark: string;
  gradientFrom: string;
  gradientTo: string;
  pillBg: string;
  pillText: string;
}

// Each gradient runs between two *distinct* light hues (a ~25-40° shift), not
// two near-identical tints — that cross-hue sweep is what reads as a gradient
// rather than a flat wash. `gradientFrom` sits on the accent's own hue (and
// doubles as the pill background, so pills stay on-hue); `gradientTo` drifts to
// a neighbouring hue. Keep both light and low-saturation so a card's cover or
// icon still sits cleanly on top.
export const THEMES: Theme[] = [
  { accent: '#4938D1', accentDark: '#372aa8', gradientFrom: '#ECEAFB', gradientTo: '#E5EFFB', pillBg: '#ECEAFB', pillText: '#4938D1' },
  { accent: '#058476', accentDark: '#046b60', gradientFrom: '#E1F4EE', gradientTo: '#E9F5E3', pillBg: '#E1F4EE', pillText: '#058476' },
  { accent: '#B4530B', accentDark: '#93430a', gradientFrom: '#FBEDE0', gradientTo: '#FCF4DC', pillBg: '#FBEDE0', pillText: '#B4530B' },
  { accent: '#BE185D', accentDark: '#9c1350', gradientFrom: '#FBE8F0', gradientTo: '#F1E8FB', pillBg: '#FBE8F0', pillText: '#BE185D' },
  { accent: '#1D4ED8', accentDark: '#1839a8', gradientFrom: '#E6EDFB', gradientTo: '#E0F4F7', pillBg: '#E6EDFB', pillText: '#1D4ED8' },
];

export function themeFor(index: number): Theme {
  return THEMES[index % THEMES.length];
}
