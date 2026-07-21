import type { Chapter, RefEntry } from '../types';
import { chapterTree } from '../chapterTree';
import { Math as Tex } from './Tex';
import { STATUS, type Status } from '../palette';
import { ChapterContentsTree, StatementSquares } from './ChapterContents';

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
  refs,
  onGoto,
  onGotoChapter,
  onGotoSection,
}: {
  docTitle?: string;
  docAuthor?: string;
  chapters: Chapter[];
  refs?: Record<string, RefEntry>;
  onGoto: (id: string) => void;
  onGotoChapter: (chapterIndex: number) => void;
  onGotoSection: (chapterIndex: number, num: string) => void;
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
            <button
              type="button"
              className="ov-chh ov-link"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onGotoChapter(i);
              }}
              title={`Open chapter ${ch.num}: ${ch.title}`}
            >
              <span className="hn">{ch.num}</span>
              <Tex as="span" text={ch.title} refs={refs} />
            </button>
            <StatementSquares stmts={chStmts} onGoto={onGoto} flat />
          </summary>
          <ChapterContentsTree
            sections={secs}
            refs={refs}
            onGotoStatement={onGoto}
            onGotoSection={(num) => onGotoSection(i, num)}
          />
        </details>
      ))}
    </div>
  );
}
