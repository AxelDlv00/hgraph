// The async KaTeX chunk — only ever loaded through typeset.ts's dynamic
// import. Importing the CSS here rather than in the entry keeps the KaTeX
// stylesheet (and the font fetches it triggers) out of the critical path too.
import 'katex/dist/katex.min.css';
export { default } from 'katex/contrib/auto-render';
