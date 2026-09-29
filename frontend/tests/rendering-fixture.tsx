import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Math } from '../src/components/Tex';
import { LeanSource } from '../src/components/LeanSource';

export function Fixture() {
  const [count, setCount] = useState(0);
  return <>
    <button onClick={() => setCount(count + 1)}>Update {count}</button>
    <Math as="div" id="math" text={String.raw`\begin{split}R_i(0,x)&\leq C(r)\\A_i(t,x)&\leq C(r)\end{split}
      \begin{gathered}0<\Delta\leq1,\quad\varepsilon=\Delta/8,\\\sigma=\varepsilon^2/2048.\end{gathered}
      \begin{equation}\label{eq:budget}4\sqrt\delta+3q/r\leq\varepsilon/2.\tag{2.20}\end{equation}`}/>
    <LeanSource repo="frenzymath/Poincare-Conjecture" root="PoincareConjecture" decl={{
      name: 'PoincareMT.ancientKappaStructuralConsequences', status: 'lean_ok',
      file: 'PoincareLib/Geometry.lean', code: 'theorem t : True := by trivial',
    }} />
  </>;
}
createRoot(document.getElementById('root')!).render(<Fixture />);
