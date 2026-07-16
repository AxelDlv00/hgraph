import type { ProjectCardData } from '../types';
import type { Theme } from '../theme';
import { Icon } from './Icon';

export function ProjectCard({ p, theme }: { p: ProjectCardData; theme: Theme }) {
  const tagLines = (p.tag || '').split('\n').filter(Boolean);
  const title = p.bookTitle || p.name;
  return (
    <a className="card" href={`#/${p.root}`}>
      <div
        className="card-illo"
        style={{ background: `linear-gradient(135deg, ${theme.gradientFrom}, ${theme.gradientTo})`, color: theme.accent }}
      >
        {p.image ? (
          <img
            src={p.image}
            alt={p.imageAlt ?? title}
            loading="lazy"
            className={p.imageFit === 'contain' ? 'fit-contain' : undefined}
            // offset only bites when the picture is being cropped
            style={p.imageOffset && p.imageFit !== 'contain' ? { objectPosition: `center ${p.imageOffset}` } : undefined}
          />
        ) : (
          <Icon name={p.icon} />
        )}
        {p.stats.statements > 0 && (
          <span className="card-pct" style={{ color: theme.accent, background: '#ffffffcc' }}>
            {p.stats.pct}%
          </span>
        )}
      </div>

      {p.author && <div className="card-author">{p.author}</div>}
      <div className="card-title">{title}</div>

      {p.blurb && <p className="card-blurb">{p.blurb}</p>}

      <div className="card-row">
        {tagLines.length > 0 && (
          <span className="card-pill" style={{ background: theme.pillBg, color: theme.pillText }}>
            {tagLines.map((l, i) => (
              <span key={i}>{l}</span>
            ))}
          </span>
        )}
        <span className="card-links">
          {(p.links || []).map((l, i) => (
            // not a real <a>: the whole card is one, and nesting anchors is
            // invalid HTML — open the manifest's href without following the card
            <span
              key={i}
              role="link"
              style={{ color: theme.accent, textDecoration: 'underline', cursor: 'pointer' }}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                window.open(l.href, '_blank', 'noopener');
              }}
            >
              {l.label}
            </span>
          ))}
        </span>
        <span className="card-arrow" style={{ color: theme.accent }}>
          &rarr;
        </span>
      </div>
    </a>
  );
}
