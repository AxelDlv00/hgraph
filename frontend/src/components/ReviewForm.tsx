import { useState } from 'react';
import type { Entry, ReviewData } from '../types';

/**
 * The review write path, offered as two explicit choices rather than one that
 * silently depends on where the page is served from:
 *
 * - **Save locally** POSTs into the graph — only possible under `hgraph serve`,
 *   where a backend is listening. On a static export (window.__HGRAPH_DATA__ is
 *   present, e.g. a github.io page) there is nothing to POST to, so it explains
 *   that instead of failing.
 * - **Send to GitHub** opens a prefilled "new issue" — the reviewer's own
 *   browser navigates to github.com, so it works anywhere, including a static
 *   page. It needs `repo` set (site.repo in hgraph/config.yaml, or `repo:` on a
 *   manifest entry); without it, it says so.
 *
 * At least one of the two is always usable, and each says why when it isn't.
 */
export function ReviewForm({
  root,
  entry,
  repo,
  onSubmitted,
}: {
  root: string;
  entry: Entry;
  repo: string | null;
  onSubmitted: (item: ReviewData) => void;
}) {
  const [maths, setMaths] = useState('');
  const [mathsComment, setMathsComment] = useState('');
  const [lean, setLean] = useState('');
  const [leanComment, setLeanComment] = useState('');
  const [author, setAuthor] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: 'err' | 'note'; text: string } | null>(null);

  // a static export ships its data inline; `hgraph serve` leaves that undefined
  // and the page fetches live — which is exactly when a POST can land.
  const isLive = !window.__HGRAPH_DATA__;
  const label = entry.title || entry.label || entry.id;

  /** the shared gate: both actions need a verdict. Returns the trimmed
   *  comments, or null (having set the error) when nothing was picked. */
  function collect(): { mc: string | null; lc: string | null } | null {
    if (!maths && !lean) {
      setMsg({ kind: 'err', text: 'Pick a Maths and/or Lean verdict first.' });
      return null;
    }
    return {
      mc: mathsComment.trim().slice(0, 500) || null,
      lc: leanComment.trim().slice(0, 500) || null,
    };
  }

  function resetFields() {
    setMaths(''); setMathsComment(''); setLean(''); setLeanComment(''); setAuthor('');
  }

  function saveLocally() {
    const c = collect();
    if (!c) return;
    if (!isLive) {
      setMsg({
        kind: 'note',
        text: "This is a static page, so there's no graph to save into — run `hgraph serve` to " +
          'review locally, or use “Send to GitHub”.',
      });
      return;
    }
    setBusy(true);
    setMsg(null);
    fetch(`${root}/api/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target: entry.id,
        maths_verdict: maths || null,
        maths_comment: c.mc,
        lean_verdict: lean || null,
        lean_comment: c.lc,
        author: author.trim() || null,
      }),
    })
      .then((r) => r.json())
      .then((d) => {
        setBusy(false);
        if (!d.ok) return setMsg({ kind: 'err', text: d.error || 'Save failed.' });
        onSubmitted(d.item);
        resetFields();
        setMsg({ kind: 'note', text: 'Saved into the graph.' });
      })
      .catch(() => {
        setBusy(false);
        setMsg({ kind: 'err', text: 'Could not reach the server.' });
      });
  }

  function sendToGitHub() {
    const c = collect();
    if (!c) return;
    if (!repo) {
      setMsg({
        kind: 'note',
        text: 'No repository is configured for this project. Add `site.repo: owner/name` to ' +
          'its hgraph/config.yaml (or `repo:` on its manifest entry) to enable GitHub reviews.',
      });
      return;
    }
    const title = `Review: ${label} [${maths || '–'}/${lean || '–'}]`;
    const body =
      `### Review — ${label}\n\n` +
      `- **Node:** \`${entry.id}\`${entry.label ? ` (${entry.label})` : ''}\n` +
      `- **Maths verdict:** ${maths || '—'}\n` +
      `- **Lean verdict:** ${lean || '—'}\n` +
      `- **Reviewer:** ${author.trim() || '_anonymous_'}\n\n` +
      `**Maths comment**\n\n${c.mc || '_none_'}\n\n` +
      `**Lean comment**\n\n${c.lc || '_none_'}\n\n` +
      `---\n_Filed from the hgraph dashboard._\n`;
    const url =
      `https://github.com/${repo}/issues/new` +
      `?title=${encodeURIComponent(title)}` +
      `&body=${encodeURIComponent(body)}` +
      `&labels=review`;
    const win = window.open(url, '_blank', 'noopener');
    setMsg(
      win
        ? { kind: 'note', text: 'Opened a prefilled issue in a new tab — submit it there to file the review.' }
        : { kind: 'err', text: 'Your browser blocked the popup — allow popups, then try again.' },
    );
  }

  return (
    <div className="rv-form">
      <label className="rv-row">
        Maths
        <select value={maths} onChange={(e) => setMaths(e.target.value)}>
          <option value="">—</option>
          <option value="good">Good</option>
          <option value="bad">Bad</option>
        </select>
      </label>
      <textarea
        placeholder="maths comment (optional, 500 chars)"
        maxLength={500}
        value={mathsComment}
        onChange={(e) => setMathsComment(e.target.value)}
      />
      <label className="rv-row">
        Lean
        <select value={lean} onChange={(e) => setLean(e.target.value)}>
          <option value="">—</option>
          <option value="good">Good</option>
          <option value="bad">Bad</option>
        </select>
      </label>
      <textarea
        placeholder="lean comment (optional, 500 chars)"
        maxLength={500}
        value={leanComment}
        onChange={(e) => setLeanComment(e.target.value)}
      />
      <input placeholder="your name (optional)" value={author} onChange={(e) => setAuthor(e.target.value)} />

      {msg && <p className={msg.kind === 'err' ? 'rv-err' : 'rv-note'}>{msg.text}</p>}

      <div className="rv-actions">
        <button
          className={`gm-btn${isLive ? ' rv-primary' : ''}`}
          disabled={busy}
          onClick={saveLocally}
          title={isLive ? 'Write this review straight into the graph' : 'Only works under `hgraph serve`'}
        >
          {busy ? 'Saving…' : 'Save locally'}
        </button>
        <button
          className={`gm-btn${!isLive && repo ? ' rv-primary' : ''}`}
          onClick={sendToGitHub}
          title={repo ? `Open a prefilled issue on ${repo}` : 'Needs a configured repo'}
        >
          Send to GitHub
        </button>
      </div>
    </div>
  );
}
