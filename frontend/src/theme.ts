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

export const THEMES: Theme[] = [
  { accent: '#4938D1', accentDark: '#372aa8', gradientFrom: '#EDEBFB', gradientTo: '#E9F0FB', pillBg: '#EDEBFB', pillText: '#4938D1' },
  { accent: '#058476', accentDark: '#046b60', gradientFrom: '#E6F5F1', gradientTo: '#EAF7EE', pillBg: '#E6F5F1', pillText: '#058476' },
  { accent: '#B4530B', accentDark: '#93430a', gradientFrom: '#FBF0E6', gradientTo: '#FDF4E9', pillBg: '#FBF0E6', pillText: '#B4530B' },
  { accent: '#BE185D', accentDark: '#9c1350', gradientFrom: '#FBEAF2', gradientTo: '#FBEDF5', pillBg: '#FBEAF2', pillText: '#BE185D' },
  { accent: '#1D4ED8', accentDark: '#1839a8', gradientFrom: '#E9EEFB', gradientTo: '#EAF2FB', pillBg: '#E9EEFB', pillText: '#1D4ED8' },
];

export function themeFor(index: number): Theme {
  return THEMES[index % THEMES.length];
}
