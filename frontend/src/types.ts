// The data contracts written by `hgraph site` (static, embedded as
// window.__HGRAPH_DATA__ / <root>/data.json) or served by `hgraph serve`
// (live, fetched from /api/site / <root>/data.json) — either way the same
// shape, so components don't care which mode they're running in.

export interface CardLink {
  label: string;
  href: string;
}

export interface ProjectStats {
  statements: number;
  done: number;
  partial: number;
  todo: number;
  pct: number;
}

export interface ProjectCardData {
  name: string;
  /** the frontend hash-routes to #/<root> — there is no separate dashboard file */
  root: string;
  category: string | null;
  /** shown in serif under the illustration panel, e.g. an author/source name */
  author?: string;
  /** shown in sans under the author line, e.g. the book/project title (falls back to `name`) */
  bookTitle?: string;
  /** pill tag text; a "\n" splits it onto two lines */
  tag?: string;
  /** extra labeled links rendered after the pill (e.g. "Formalization", "Docs") */
  links?: CardLink[];
  /** flat icon key for the illustration panel — see Icon.tsx for the set */
  icon?: string;
  /** picture for the illustration panel (data URI or URL); replaces the icon + gradient */
  image?: string;
  /** alt text for `image` (falls back to the card title) */
  imageAlt?: string;
  /** vertical crop anchor for `image` — a CSS length/percentage; 0% shows the
   *  top of the picture, 100% the bottom. Defaults to "0%". Only meaningful
   *  when `imageFit` is "cover" (with "contain" nothing is cropped away). */
  imageOffset?: string;
  /** how `image` fills the card panel. "cover" (default) fills it and crops the
   *  overflow — right for a photo. "contain" fits the whole picture inside,
   *  gradient showing around it — right for a book cover, which is portrait
   *  while the panel is landscape, so cropping would show only a band of it. */
  imageFit?: 'cover' | 'contain';
  blurb?: string;
  stats: ProjectStats;
}

export interface Section {
  category: string | null;
  /** optional line under the category heading — the manifest's `categories:` */
  subtitle?: string | null;
  projects: ProjectCardData[];
}

export interface SiteData {
  title: string;
  subtitle?: string;
  brand?: string;
  overviewHtml?: string;
  footer?: string;
  sections: Section[];
}

// ---- per-project (ProjectView) ------------------------------------------ //

export interface LeanDecl {
  name: string;
  status: 'lean_ok' | 'mathlib_ok' | 'sorry' | 'empty' | null;
  file: string | null;
  code: string;
}

export interface Dep {
  id: string;
  title: string | null;
  label: string | null;
  type: string;
}

export interface Note {
  author: string | null;
  created: string | null;
  updated: string | null;
}

export interface CommentData extends Note {
  title: string | null;
  text: string;
}

export interface ReviewData extends Note {
  maths_verdict: 'good' | 'bad' | null;
  maths_comment: string | null;
  lean_verdict: 'good' | 'bad' | null;
  lean_comment: string | null;
}

export interface Entry {
  id: string;
  label: string | null;
  title: string | null;
  chapter: string | null;
  kind: string; // content_type
  body: string;
  lean_status: 'lean_ok' | 'mathlib_ok' | 'sorry' | 'empty';
  mathlib_name: string[] | null;
  status: string | null;
  tags: string[] | null;
  lean: LeanDecl[];
  deps: Dep[];
  reviewed: boolean;
  maths_verdict: 'good' | 'bad' | null;
  lean_verdict: 'good' | 'bad' | null;
  reviews: ReviewData[];
  comments: CommentData[];
  /** semantic cluster id (community-detection stub or authored) — the dependency graph's group axis */
  group: string | number | null;
  /** how foundational this node is: coarse (most-depended-on) / medium / fine — the graph's detail-level filter */
  level: 'coarse' | 'medium' | 'fine' | null;
}

// ---- document mode (chapters/prose/cross-refs) --------------------------- //

export interface Enrich {
  lean_status: Entry['lean_status'];
  mathlib_name: string[] | null;
  reviewed: boolean;
  maths_verdict: 'good' | 'bad' | null;
  lean_verdict: 'good' | 'bad' | null;
  lean: LeanDecl[];
  deps: Dep[];
  reviews: ReviewData[];
  comments: CommentData[];
  status: string | null;
  tags: string[] | null;
  ref: string | null;
  group: string | number | null;
}

export interface HeadBlock {
  t: 'head';
  level: number;
  title: string;
  num?: string;
}
export interface ProseBlock {
  t: 'prose';
  tex: string;
}
export interface ProofBlock {
  t: 'proof';
  tex: string;
}
export interface StmtBlock {
  t: 'stmt';
  label: string;
  labels: string[];
  title: string;
  content_type: string;
  lean: string[];
  uses: string[];
  leanok: boolean;
  mathlibok: boolean;
  body: string;
  num: string;
  abbr: string;
  id?: string;
  enrich?: Enrich;
}
export type Block = HeadBlock | ProseBlock | ProofBlock | StmtBlock;

export interface Chapter {
  title: string;
  num?: string;
  blocks: Block[];
}

export interface RefEntry {
  num: string;
  id: string | null;
  abbr: string;
}

export interface BibEntry {
  key: string;
  type: string;
  title: string | null;
  author: string | null;
  year: string | null;
  journal: string | null;
  booktitle: string | null;
  publisher: string | null;
  volume: string | null;
  number: string | null;
  pages: string | null;
  url: string | null;
}

export interface ProjectData {
  title: string;
  mode?: 'doc' | 'list';
  entries: Entry[];
  chapters?: Chapter[];
  refs?: Record<string, RefEntry>;
  loc?: Record<string, number>;
  bib: BibEntry[];
  docTitle?: string;
  docAuthor?: string;
  macros: Record<string, string>;
  repo: string | null;
  gvsvg?: Record<string, string>;
}

declare global {
  interface Window {
    __HGRAPH_DATA__?: SiteData;
  }
}
