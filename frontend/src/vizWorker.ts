// Runs Graphviz (compiled to WASM, @viz-js/viz) off the main thread — see
// vizInstance.ts. Layout of a big chapter takes long enough to freeze the UI
// if run on the main thread; in here it just makes the "Laying out…" overlay
// linger while pan/zoom stay live.
import { instance } from '@viz-js/viz';

const vizPromise = instance();

self.onmessage = async (ev: MessageEvent<{ id: number; dot: string }>) => {
  const { id, dot } = ev.data;
  try {
    const viz = await vizPromise;
    const svg = viz.renderString(dot, { format: 'svg' });
    postMessage({ id, svg });
  } catch (e) {
    postMessage({ id, error: String(e) });
  }
};
