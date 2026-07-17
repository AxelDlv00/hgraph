import { useState } from 'react';
import type { ReviewData, CommentData } from '../types';
import { ReviewForm, type ReviewTarget } from './ReviewForm';

/** A node's reviews + comments, and the form to add one — the same unit
 * wherever a statement is shown. It lives in the `StatementCard` side panel
 * (the dependency graph) and in the blueprint's own statement boxes, so a
 * reader can review what they are reading without first finding the node in
 * the graph.
 *
 * Collapsed by default: the summary doubles as the trigger, and reads
 * "N reviews · M comments" so it sits in the blueprint's meta row alongside
 * "uses N · used by N" without inventing a second visual language. */
export function Reviews({
  root,
  target,
  reviews: initial,
  comments,
  repo,
  className = 'stmt-reviews',
}: {
  root: string;
  target: ReviewTarget;
  reviews: ReviewData[];
  comments: CommentData[];
  repo: string | null;
  className?: string;
}) {
  const [reviews, setReviews] = useState(initial);
  return (
    <details className={className}>
      <summary>
        {reviews.length} review{reviews.length === 1 ? '' : 's'} · {comments.length} comment
        {comments.length === 1 ? '' : 's'}
      </summary>
      {reviews.map((r, i) => (
        <div key={i} className="ritem">
          <span>{r.author || 'anon'}</span>
          <span className="k">{(r.created || '').slice(0, 10)}</span>
          <div className="rmeta">
            {r.maths_verdict && (
              <span className="p">
                maths: <b>{r.maths_verdict}</b>
              </span>
            )}
            {r.lean_verdict && (
              <span className="p">
                lean: <b>{r.lean_verdict}</b>
              </span>
            )}
          </div>
          {(r.maths_comment || r.lean_comment) && (
            <div className="rmeta">{[r.maths_comment, r.lean_comment].filter(Boolean).join(' — ')}</div>
          )}
        </div>
      ))}
      {comments.map((c, i) => (
        <div key={i} className="ritem">
          <span>{c.author || 'anon'}</span>
          <span className="k">{(c.created || '').slice(0, 10)}</span>
          {c.title && (
            <div className="rmeta">
              <b>{c.title}</b>
            </div>
          )}
          <div className="rmeta">{c.text}</div>
        </div>
      ))}
      <ReviewForm
        root={root}
        entry={target}
        repo={repo}
        onSubmitted={(item: ReviewData) => setReviews((rs) => [...rs, item])}
      />
    </details>
  );
}
