import type { LeanDecl } from '../types';
import { leanHi } from '../latex';
import { Docstring } from './Docstring';

export function LeanSource({ decl }: { decl: LeanDecl }) {
  const statement = decl.statement || decl.code;
  return <>
    {decl.docstring && <Docstring text={decl.docstring} />}
    {statement && <pre className="lean-code" dangerouslySetInnerHTML={{ __html: leanHi(statement) }} />}
    {(decl.context || (decl.statement && decl.code !== decl.statement)) && <details>
      <summary>Source and context</summary>
      {decl.context && <pre className="lean-code" dangerouslySetInnerHTML={{ __html: leanHi(decl.context) }} />}
      {decl.code && <pre className="lean-code" dangerouslySetInnerHTML={{ __html: leanHi(decl.code) }} />}
    </details>}
  </>;
}
