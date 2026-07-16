import type { Chapter, StmtBlock } from '../types';
import { chapterTree, type TreeSection } from '../chapterTree';
import { Math as Tex } from './Tex';
import { STATUS, statusColor, type Status } from '../palette';

function Squares({ stmts, onGoto, flat }: { stmts: StmtBlock[]; onGoto: (id: string) => void; flat?: boolean }) {
  return (
    <div className={`mmcells ov-statements${flat ? ' ov-flat' : ''}`}>
      {stmts.map((b) => (
        <i
          key={b.id}
          className="mm"
          style={{ background: statusColor(b.enrich?.lean_status) }}
          onClick={(e) => {
            e.preventDefault();
            if (b.id) onGoto(b.id);
          }}
        />
      ))}
    </div>
  );
}

function SecLabel({ num, title }: { num: string; title: string }) {
  return num ? (
    <div className="co-sec">
      <span className="n">{num}</span>
      <Tex as="span" text={title} />
    </div>
  ) : (
    <span className="co-sec" style={{ color: 'var(--muted)' }}>
      Introduction
    </span>
  );
}

function SectionRow({ s, onGoto }: { s: TreeSection; onGoto: (id: string) => void }) {
  const secStmts = s.stmts.concat(s.subs.flatMap((u) => u.stmts));
  if (!s.subs.length) {
    return (
      <div className="ov-section-h">
        <SecLabel num={s.num} title={s.title} />
        <Squares stmts={secStmts} onGoto={onGoto} />
      </div>
    );
  }
  return (
    <details className="ov-section">
      <summary>
        <SecLabel num={s.num} title={s.title} />
        <Squares stmts={secStmts} onGoto={onGoto} flat />
      </summary>
      <div className="ov-subsections">
        {s.stmts.length > 0 && (
          <div className="ov-subsection">
            <span className="co-sec" style={{ color: 'var(--muted)' }}>
              Direct
            </span>
            <Squares stmts={s.stmts} onGoto={onGoto} />
          </div>
        )}
        {s.subs.map((u) => (
          <div className="ov-subsection" key={u.num}>
            <SecLabel num={u.num} title={u.title} />
            <Squares stmts={u.stmts} onGoto={onGoto} />
          </div>
        ))}
      </div>
    </details>
  );
}

/** The "Overview" landing page for a multi-chapter blueprint — a title page
 * (`\maketitle`) + a status-color legend + every chapter, progressively
 * disclosed down to section/subsection, ported from the original's
 * `renderOverview()`. This is the default view on load (not chapter 1's
 * full prose — that's one click away in the TOC); the squares never turn
 * into a percentage, they just re-partition one level finer each time you
 * expand a row. */
export function Overview({
  docTitle,
  docAuthor,
  chapters,
  onGoto,
}: {
  docTitle?: string;
  docAuthor?: string;
  chapters: Chapter[];
  onGoto: (id: string) => void;
}) {
  const rows = chapters
    .map((ch, i) => {
      const secs = chapterTree(ch);
      if (!secs.length) return null;
      const chStmts = secs.flatMap((s) => s.stmts.concat(s.subs.flatMap((u) => u.stmts)));
      if (!chStmts.length) return null;
      return { ch, i, secs, chStmts };
    })
    .filter((r): r is NonNullable<typeof r> => r !== null);

  return (
    <div className="doc">
      <div className="maketitle">
        <h1>
          <Tex as="span" text={docTitle || 'Blueprint'} />
        </h1>
        {docAuthor && (
          <div className="mkauthor">
            <Tex as="span" text={docAuthor} />
          </div>
        )}
      </div>
      <div className="ovleg-wrap">
        <div className="ovleg">
          {(['mathlib_ok', 'lean_ok', 'sorry', 'empty'] as Status[]).map((k) => (
            <span key={k}>
              <i className="sw" style={{ background: STATUS[k].fg }} />
              {STATUS[k].label}
            </span>
          ))}
        </div>
      </div>
      {rows.map(({ ch, i, secs, chStmts }) => (
        <details className="ov-chapter" key={i}>
          <summary>
            <div className="ov-chh">
              <span className="hn">{ch.num}</span>
              <Tex as="span" text={ch.title} />
            </div>
            <Squares stmts={chStmts} onGoto={onGoto} flat />
          </summary>
          <div className="ov-sections">
            {secs.map((s, si) => (
              <SectionRow key={si} s={s} onGoto={onGoto} />
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}
