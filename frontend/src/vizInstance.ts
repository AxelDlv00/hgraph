// Graphviz layout, lazily loaded AND off the main thread. The WASM build is
// ~1.2MB, so it's only fetched once a layout is actually needed, never on
// initial page load — and it's fetched inside a Web Worker (vizWorker.ts), so
// laying out a big chapter never freezes the modal; pan/zoom keep running
// while `dot` works. Bundled (not CDN), matching this whole rewrite's "no
// CDN, pip install and go" goal — the original loaded d3-graphviz from a CDN
// for this same job. Falls back to running Viz on the main thread if Workers
// are unavailable.
//
// Layouts are pure (same DOT -> same SVG), so results are cached by DOT
// string at module level: a given expand/detail state only ever pays once per
// session, and the cache survives the graph modal closing and reopening.

let worker: Worker | null = null;
let workerFailed = false;
let seq = 0;
const pending = new Map<number, { resolve: (svg: string) => void; reject: (e: Error) => void }>();

const cache = new Map<string, string>();
const CACHE_MAX = 200;

function remember(dot: string, svg: string): string {
  if (cache.size >= CACHE_MAX) {
    const oldest = cache.keys().next().value;
    if (oldest !== undefined) cache.delete(oldest);
  }
  cache.set(dot, svg);
  return svg;
}

/** Synchronous cache probe — lets the caller skip a loading state entirely
 * when the layout for this DOT already exists. */
export function cachedLayout(dot: string): string | undefined {
  return cache.get(dot);
}

function getWorker(): Worker | null {
  if (workerFailed) return null;
  if (!worker) {
    try {
      worker = new Worker(new URL('./vizWorker.ts', import.meta.url), { type: 'module' });
      worker.onmessage = (ev: MessageEvent<{ id: number; svg?: string; error?: string }>) => {
        const p = pending.get(ev.data.id);
        if (!p) return;
        pending.delete(ev.data.id);
        if (ev.data.svg != null) p.resolve(ev.data.svg);
        else p.reject(new Error(ev.data.error || 'graph layout failed'));
      };
      worker.onerror = () => {
        // the worker itself died (script failed to load, WASM refused, …):
        // fail everything in flight and let layoutDot retry on the main thread
        workerFailed = true;
        const err = new Error('graph layout worker failed');
        pending.forEach((p) => p.reject(err));
        pending.clear();
        worker?.terminate();
        worker = null;
      };
    } catch {
      workerFailed = true;
      worker = null;
    }
  }
  return worker;
}

async function layoutOnMainThread(dot: string): Promise<string> {
  const { instance } = await import('@viz-js/viz');
  const viz = await instance();
  return remember(dot, viz.renderString(dot, { format: 'svg' }));
}

/** Lay `dot` out to positioned SVG (cached; in a worker when possible). */
export function layoutDot(dot: string): Promise<string> {
  const hit = cache.get(dot);
  if (hit !== undefined) return Promise.resolve(hit);
  const w = getWorker();
  if (!w) return layoutOnMainThread(dot);
  return new Promise<string>((resolve, reject) => {
    const id = ++seq;
    pending.set(id, { resolve: (svg) => resolve(remember(dot, svg)), reject });
    w.postMessage({ id, dot });
  }).catch((e) => {
    if (workerFailed) return layoutOnMainThread(dot); // died mid-flight — one main-thread retry
    throw e;
  });
}

// --- idle prefetch ----------------------------------------------------------
// Exactly one chapter is ever expanded at a time, so the set of layouts a
// session can need is small: one per chapter (at the current detail level),
// plus the collapsed overview. Warm them while the user looks at the current
// graph — strictly one at a time, each next job scheduled in idle time after
// the previous finishes, so a real click's layout only ever queues behind at
// most one prefetch in the (single-threaded) worker.
let prefetchToken = 0;

export function prefetchLayouts(dots: string[]): void {
  const token = ++prefetchToken; // a newer prefetch set supersedes this one
  const queue = dots.filter((d) => !cache.has(d));
  const idle = (cb: () => void) =>
    typeof requestIdleCallback === 'function'
      ? requestIdleCallback(() => cb(), { timeout: 4000 })
      : setTimeout(cb, 300);
  const next = () => {
    if (token !== prefetchToken) return;
    const dot = queue.shift();
    if (!dot) return;
    layoutDot(dot)
      .catch(() => {}) // prefetch is best-effort; a real request will surface errors
      .finally(() => idle(next));
  };
  idle(next);
}
