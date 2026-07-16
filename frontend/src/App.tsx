import { useEffect, useState } from 'react';
import type { SiteData } from './types';
import { Landing } from './components/Landing';
import { ProjectView } from './components/ProjectView';

/** "#/examples/gauss" -> {root: "examples/gauss"}; "" or "#/" -> {root: null}.
 * A second "#" deep-links into a statement or chapter within that project —
 * "#/examples/gauss#thm:bishop-gromov" or "#/examples/gauss#ch-2" — the same
 * locator syntax the original dashboard's own page-level hash understood, so
 * external links (e.g. a proof-structure diagram) keep working.
 *
 * A trailing slash is stripped: the root is pasted straight into
 * `${root}/data.json` (ProjectView), so "#/gauss/" would fetch "gauss//data.json".
 * A static file server shrugs that off, but `hgraph serve` matches its mount
 * prefixes exactly and 404s — and the URLs `hgraph serve` itself prints carry
 * that trailing slash. Canonicalise here, once, rather than at each use. */
function parseHash(hash: string): { root: string | null; locator: string | null } {
  const raw = hash.replace(/^#\/?/, '');
  const i = raw.indexOf('#');
  const rootPart = (i === -1 ? raw : raw.slice(0, i)).replace(/\/+$/, '');
  const locatorPart = i === -1 ? '' : raw.slice(i + 1);
  let locator: string | null = null;
  try {
    locator = locatorPart ? decodeURIComponent(locatorPart) : null;
  } catch {
    locator = locatorPart || null;
  }
  return { root: rootPart || null, locator };
}

function useHashRoute(): { root: string | null; locator: string | null } {
  const [route, setRoute] = useState(() => parseHash(location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}

export default function App() {
  const { root: projectRoot, locator } = useHashRoute();
  const [data, setData] = useState<SiteData | null>(window.__HGRAPH_DATA__ ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (data || projectRoot) return; // ProjectView fetches its own data
    fetch('/api/site')
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [data, projectRoot]);

  // key by root: switching projects must reset every bit of view state
  // (current chapter, filters, selection) — carrying chapter index 7 into a
  // 3-chapter project would render chapters[7] and crash
  if (projectRoot) return <ProjectView key={projectRoot} root={projectRoot} initialLocator={locator} />;
  if (error) return <div className="page-error">Couldn't load the workspace: {error}</div>;
  if (!data) return <div className="page-loading">Loading…</div>;
  return <Landing data={data} />;
}
