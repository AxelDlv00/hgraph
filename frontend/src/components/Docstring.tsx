import { memo, useEffect, useRef } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { typesetMath } from '../typeset';

export const Docstring = memo(function Docstring({ text }: { text: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) typesetMath(ref.current);
  });

  return <details className="lean-docstring" open>
    <summary>Documentation</summary>
    <div className="lean-docstring-body" ref={ref}>
      <Markdown remarkPlugins={[remarkGfm]} skipHtml>{text}</Markdown>
    </div>
  </details>;
});
