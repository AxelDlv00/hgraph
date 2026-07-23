import { useState } from 'react';
import type { SiteData } from '../types';
import { themeFor } from '../theme';
import { ProjectCard } from './ProjectCard';
import { ContentPage } from './ContentPage';

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
  const contentTabs = data.tabs ?? [];
  // The tab rail: always Projects, then the overview (if any), then whatever
  // extra content tabs (People, Roadmap, …) the manifest's `tabs:` configured.
  // "Projects" is the default landing view — same rationale as ProjectView's
  // own `view` state defaulting to 'overview' there: whichever tab answers
  // "what is this, concretely" belongs up front. The rest are one click away.
  const railTabs: { id: string; label: string }[] = [
    { id: 'projects', label: 'Projects' },
    ...(hasOverview ? [{ id: 'overview', label: 'Overview' }] : []),
    ...contentTabs.map((c) => ({ id: c.id, label: c.label })),
  ];
  const [tab, setTab] = useState('projects');
  const activeContentTab = contentTabs.find((c) => c.id === tab);

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

        {railTabs.length > 1 && (
          <nav className="landing-tabs">
            {railTabs.map((rt) => (
              <a
                key={rt.id}
                className={`landing-tab${tab === rt.id ? ' on' : ''}`}
                onClick={() => setTab(rt.id)}
              >
                {rt.label}
              </a>
            ))}
          </nav>
        )}

        {tab === 'projects' &&
          data.sections.map((section, i) => {
            // a configured section/project theme wins; otherwise cycle the palette
            const theme = section.theme ?? themeFor(i);
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
                    <ProjectCard key={p.root} p={p} theme={p.theme ?? theme} />
                  ))}
                </div>
              </section>
            );
          })}

        {tab === 'overview' && hasOverview && <ContentPage html={data.overviewHtml!} />}
        {activeContentTab && <ContentPage html={activeContentTab.html} />}

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
