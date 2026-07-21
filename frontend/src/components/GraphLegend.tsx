import { useState } from 'react';
import { GRAPH } from '../palette';
import { ChevronDown } from 'lucide-react';

/**
 * The graph modal's floating legend — ported from the original's
 * `#gmLegendPanel`. Every swatch reads its colour from `palette.ts`, the same
 * module `graphDot.ts` renders the SVG from, so the legend cannot drift out of
 * step with the graph it describes. The original also had a solid/dashed edge
 * distinction (statement vs proof dependency); both hard-edge types collapsed
 * into one (`uses`) in this schema, so every edge here is the same dashed
 * style — no edge legend needed.
 */
export function GraphLegend({ mode }: { mode: 'groups' | 'full' }) {
  const [collapsed, setCollapsed] = useState(true);
  return (
    <div className={`gm-float gm-legend${collapsed ? ' collapsed' : ''}`}>
      <button
        type="button"
        className="lgttl"
        onClick={() => setCollapsed((c) => !c)}
        aria-expanded={!collapsed}
      >
        <span>Legend</span>
        <ChevronDown className="lgcar" size={15} strokeWidth={2} aria-hidden="true" />
        <span className="lgsub">shape, border &amp; fill</span>
      </button>

      <div className="lgsec">Chapters</div>
      <div className="lg">
        <i className="lgf" style={{ background: GRAPH.clusterFill, border: `2px solid ${GRAPH.clusterBorder}` }} />
        {mode === 'groups' ? 'collapsed — click to open the full graph' : 'one cluster per chapter'}
      </div>

      <div className="lgsec">Shape</div>
      <div className="lg">
        <i className="lgshape rect" />
        definition / example / remark
      </div>
      <div className="lg">
        <i className="lgshape ell" />
        theorem / lemma / proposition / corollary
      </div>

      <div className="lgsec">Statement (border)</div>
      {(
        [
          ['blocked', 'blocked'],
          ['ready', 'ready to formalize'],
          ['formalized', 'formalized'],
        ] as const
      ).map(([k, label]) => (
        <div className="lg" key={k}>
          <i className="lgb" style={{ borderColor: GRAPH.border[k] }} />
          {label}
        </div>
      ))}

      <div className="lgsec">Proof (fill)</div>
      {(
        [
          ['notready', 'not ready'],
          ['ready', 'ready to formalize'],
          ['incomplete', 'Lean code incomplete'],
          ['local', 'locally formalized'],
          ['done', '+ dependencies complete'],
        ] as const
      ).map(([k, label]) => (
        <div className="lg" key={k}>
          <i className="lgf" style={{ background: GRAPH.fill[k] }} />
          {label}
        </div>
      ))}

      <div className="lgsec">Edges</div>
      <div className="lg">
        <span className="lge dash" />
        depends on (uses)
      </div>
    </div>
  );
}
