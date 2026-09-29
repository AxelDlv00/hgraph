import { createContext, useContext } from 'react';

// Expositions can link to Lean without using annotation coverage as proof progress.
export const ProgressContext = createContext(true);
export const useProgress = () => useContext(ProgressContext);

export function sourceLinkLabel(status?: string | null): string {
  return ({ mathlib_ok: 'mathlib reference', lean_ok: 'Lean linked',
    sorry: 'link needs review', empty: 'no resolved link' } as Record<string, string>)[status || 'empty'] || 'no resolved link';
}
