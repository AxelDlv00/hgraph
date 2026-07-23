import type { Chapter, StmtBlock } from '../types';
import { plainTex } from '../latex';

export function Outline({
  chapter,
  selectedId,
  onSelect,
}: {
  chapter: Chapter | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (!chapter) {
    return (
      <aside className="doc-outline" id="blueprint-outline" aria-label="Chapter outline">
        <div className="olh">Outline</div>
        <div className="oempty">The chapter outline appears while reading the blueprint.</div>
      </aside>
    );
  }
  const stmts = chapter.blocks.filter((b): b is StmtBlock => b.t === 'stmt');
  return (
    <aside className="doc-outline" id="blueprint-outline" aria-label="Chapter outline">
      <div className="olh">
        In this chapter <span className="olc">{stmts.length}</span>
      </div>
      {stmts.length ? (
        <div className="olist">
          {stmts.map((b) => {
            const en = b.enrich;
            const st = en ? en.lean_status : 'empty';
            const title = b.title && b.title !== b.label ? plainTex(b.title) : (b.label || '').replace(/^[a-z]+:/, '');
            return (
              <a
                key={b.id}
                className={`omini k-${b.content_type}${selectedId === b.id ? ' cur' : ''}`}
                onClick={() => b.id && onSelect(b.id)}
                title={plainTex(b.title || b.label)}
              >
                <div className="omini-h">
                  <span className={`tag k-${b.content_type}`}>
                    {b.abbr}&nbsp;{b.num}
                  </span>
                  <span className="omini-b">
                    {en && <span className={`b b-${st}`}>{st.replace('_', ' ')}</span>}
                  </span>
                </div>
                <div className="otitle2">{title}</div>
              </a>
            );
          })}
        </div>
      ) : (
        <div className="oempty">No statements in this chapter.</div>
      )}
    </aside>
  );
}
