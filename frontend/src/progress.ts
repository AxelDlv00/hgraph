import { createContext, useContext } from 'react';

// Expositions can link to Lean without using annotation coverage as proof progress.
export const ProgressContext = createContext(true);
export const useProgress = () => useContext(ProgressContext);

export function sourceLinkLabel(status?: string | null): string {
  return ({ mathlib_ok: 'mathlib ok', lean_ok: 'lean ok',
    sorry: 'sorry', empty: 'not formalized' } as Record<string, string>)[status || 'empty'] || 'not formalized';
}
