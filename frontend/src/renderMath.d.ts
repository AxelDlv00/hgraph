// katex/contrib/auto-render ships no bundled types.
declare module 'katex/contrib/auto-render' {
  interface AutoRenderOptions {
    delimiters?: { left: string; right: string; display: boolean }[];
    macros?: Record<string, string>;
    throwOnError?: boolean;
  }
  export default function renderMathInElement(el: HTMLElement, options?: AutoRenderOptions): void;
}
