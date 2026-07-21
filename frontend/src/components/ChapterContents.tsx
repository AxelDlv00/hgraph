import type { MouseEvent } from 'react';
import type { RefEntry, StmtBlock } from '../types';
import type { TreeSection } from '../chapterTree';
import { statusColor } from '../palette';
import { plainTex } from '../latex';
import { Math as Tex } from './Tex';

function follow(e: MouseEvent, action: () => void) {
  e.preventDefault();
  e.stopPropagation();
  action();
}

export function StatementSquares({
  stmts,
  onGoto,
  flat,
}: {
  stmts: StmtBlock[];
  onGoto: (id: string) => void;
  flat?: boolean;
}) {
  return (
    <div className={`mmcells ov-statements${flat ? ' ov-flat' : ''}`}>
      {stmts.map((b, i) => (
        <button
          type="button"
          key={b.id || `${b.num}-${i}`}
          className="mm"
          data-id={b.id}
          style={{ background: statusColor(b.enrich?.lean_status) }}
          onClick={(e) => b.id && follow(e, () => onGoto(b.id!))}
          aria-label={`Open ${b.abbr} ${b.num}${b.title ? `: ${plainTex(b.title)}` : ''}`}
        />
      ))}
    </div>
  );
}

function SectionLabel({
  num,
  title,
  refs,
  onGoto,
}: {
  num: string;
  title: string;
  refs?: Record<string, RefEntry>;
  onGoto?: (num: string) => void;
}) {
  if (!num) {
    return (
      <span className="co-sec co-intro">
        Introduction
      </span>
    );
  }
  const contents = (
    <>
      <span className="n">{num}</span>
      <Tex as="span" text={title} refs={refs} />
    </>
  );
  return onGoto ? (
    <button
      type="button"
      className="co-sec co-link"
      onClick={(e) => follow(e, () => onGoto(num))}
      title={`Jump to section ${num}: ${plainTex(title)}`}
    >
      {contents}
    </button>
  ) : (
    <div className="co-sec">{contents}</div>
  );
}

function SectionRow({
  section,
  refs,
  onGotoStatement,
  onGotoSection,
}: {
  section: TreeSection;
  refs?: Record<string, RefEntry>;
  onGotoStatement: (id: string) => void;
  onGotoSection?: (num: string) => void;
}) {
  const sectionStatements = section.stmts.concat(section.subs.flatMap((u) => u.stmts));
  if (!section.subs.length) {
    return (
      <div className="ov-section-h">
        <SectionLabel num={section.num} title={section.title} refs={refs} onGoto={onGotoSection} />
        <StatementSquares stmts={sectionStatements} onGoto={onGotoStatement} />
      </div>
    );
  }
  return (
    <details className="ov-section">
      <summary>
        <SectionLabel num={section.num} title={section.title} refs={refs} onGoto={onGotoSection} />
        <StatementSquares stmts={sectionStatements} onGoto={onGotoStatement} flat />
      </summary>
      <div className="ov-subsections">
        {section.stmts.length > 0 && (
          <div className="ov-subsection">
            <span className="co-sec co-intro">Direct</span>
            <StatementSquares stmts={section.stmts} onGoto={onGotoStatement} />
          </div>
        )}
        {section.subs.map((subsection) => (
          <div className="ov-subsection" key={subsection.num}>
            <SectionLabel
              num={subsection.num}
              title={subsection.title}
              refs={refs}
              onGoto={onGotoSection}
            />
            <StatementSquares stmts={subsection.stmts} onGoto={onGotoStatement} />
          </div>
        ))}
      </div>
    </details>
  );
}

/** The single section/subsection tree used by the overview and chapter TOC. */
export function ChapterContentsTree({
  sections,
  refs,
  onGotoStatement,
  onGotoSection,
}: {
  sections: TreeSection[];
  refs?: Record<string, RefEntry>;
  onGotoStatement: (id: string) => void;
  onGotoSection?: (num: string) => void;
}) {
  return (
    <div className="ov-sections">
      {sections.map((section, i) => (
        <SectionRow
          key={section.num || i}
          section={section}
          refs={refs}
          onGotoStatement={onGotoStatement}
          onGotoSection={onGotoSection}
        />
      ))}
    </div>
  );
}
