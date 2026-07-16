import { useEffect, useRef, useState } from 'react';
import type { SiteData } from '../types';
import { themeFor } from '../theme';
import { typesetMath } from '../typeset';
import { ProjectCard } from './ProjectCard';

/** The overview fragment, with its math typeset.
 *
 * The fragment is authored with `$…$` for KaTeX — an .html one written by hand
 * (Poincare-Conjecture's `scripts/gen_overview.py` says so in as many words) or
 * an .md one converted by `hgraph.site._md_to_html`, which leaves math alone on
 * purpose. Nothing ever ran KaTeX over it, so a landing page whose overview had
 * any math showed it as raw LaTeX. */
function Overview({ html }: { html: string }) {
  const ref = useRef<HTMLElement | null>(null);
  // no deps — same React-19 innerHTML-reset caveat as Tex.tsx; typesetMath's
  // guard makes the per-commit call O(1) when the fragment was left alone
  useEffect(() => {
    if (ref.current) typesetMath(ref.current);
  });
  return <section className="overview" ref={ref as never} dangerouslySetInnerHTML={{ __html: html }} />;
}

/** The workspace totals shown in the header — the same quantities a project's
 * own header shows, summed over every project on the page. */
function totals(data: SiteData) {
  const projects = data.sections.flatMap((s) => s.projects);
  const statements = projects.reduce((n, p) => n + p.stats.statements, 0);
  const done = projects.reduce((n, p) => n + p.stats.done, 0);
  return { projects: projects.length, statements, done, pct: statements ? Math.round((100 * done) / statements) : 0 };
}

export function Landing({ data }: { data: SiteData }) {
  const t = totals(data);
  const hasOverview = !!data.overviewHtml;
  // "Projects" is the default landing view — same rationale as ProjectView's
  // own `view` state defaulting to 'overview' there: whichever tab answers
  // "what is this, concretely" belongs up front. Here that's the projects,
  // not the prose. The overview is one click away, not inline after them.
  const [tab, setTab] = useState<'projects' | 'overview'>('projects');

  return (
    <>
      <header className="site-header">
        <div className="site-htop">
          <span className="site-brand">{data.brand || data.title}</span>
          {data.brand && <span className="sub">{data.title}</span>}
          <div className="project-stats">
            <span className="pstat">
              <b>{t.projects}</b> {t.projects === 1 ? 'project' : 'projects'}
            </span>
            {t.statements > 0 && (
              <>
                <span className="pstat">
                  <b>{t.statements}</b> statements
                </span>
                <span className="pstat">
                  <b>{t.pct}%</b> formalized
                  <span className="pbar">
                    <i style={{ width: `${t.pct}%` }} />
                  </span>
                </span>
              </>
            )}
          </div>
        </div>
      </header>

      <div className="page">
        <div className="hero">
          <h1>{data.title}</h1>
          {data.subtitle && <p className="subtitle">{data.subtitle}</p>}
        </div>

        {hasOverview && (
          <nav className="landing-tabs">
            <a
              className={`landing-tab${tab === 'projects' ? ' on' : ''}`}
              onClick={() => setTab('projects')}
            >
              Projects
            </a>
            <a
              className={`landing-tab${tab === 'overview' ? ' on' : ''}`}
              onClick={() => setTab('overview')}
            >
              Overview
            </a>
          </nav>
        )}

        {tab === 'projects' &&
          data.sections.map((section, i) => {
            const theme = themeFor(i);
            return (
              <section className="section" key={section.category ?? `_${i}`}>
                {section.category && (
                  <>
                    <h2 className="section-title" style={{ color: '#131B2B' }}>
                      {section.category}
                    </h2>
                    <span className="section-underline" style={{ background: theme.accent }} />
                    {section.subtitle && <p className="subtitle">{section.subtitle}</p>}
                  </>
                )}
                <div className="card-grid">
                  {section.projects.map((p) => (
                    <ProjectCard key={p.root} p={p} theme={theme} />
                  ))}
                </div>
              </section>
            );
          })}

        {tab === 'overview' && hasOverview && <Overview html={data.overviewHtml!} />}

        <footer
          className="footer"
          dangerouslySetInnerHTML={{
            __html:
              data.footer ||
              'Built with <a href="https://github.com/AxelDlv00/hgraph">hgraph</a> — a plain-files semantic graph for autoformalization.',
          }}
        />
      </div>
    </>
  );
}
