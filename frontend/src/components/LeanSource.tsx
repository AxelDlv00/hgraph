import type { LeanDecl } from '../types';
import { leanHi } from '../latex';
import { Docstring } from './Docstring';
import { leanSourceUrl } from '../sourceUrl';

export function LeanSource({ decl, repo, root }: { decl: LeanDecl; repo?: string | null; root?: string }) {
  const statement = decl.statement || decl.code;
  const sourceUrl = leanSourceUrl(decl.file, repo, root);
  return <>
    {sourceUrl && <a className="lean-source-link" href={sourceUrl} target="_blank" rel="noopener noreferrer">View Lean source on GitHub</a>}
    {decl.docstring && <Docstring text={decl.docstring} />}
    {statement && <pre className="lean-code" dangerouslySetInnerHTML={{ __html: leanHi(statement) }} />}
    {(decl.context || (decl.statement && decl.code !== decl.statement)) && <details>
      <summary>Source and context</summary>
      {decl.context && <pre className="lean-code" dangerouslySetInnerHTML={{ __html: leanHi(decl.context) }} />}
      {decl.code && <pre className="lean-code" dangerouslySetInnerHTML={{ __html: leanHi(decl.code) }} />}
    </details>}
  </>;
}
