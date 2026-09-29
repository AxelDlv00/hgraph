/** Resolve project-relative Lean files within the configured GitHub repository. */
export function leanSourceUrl(file: string | null, repo?: string | null, root = ''): string | null {
  if (!file || !repo || !/^[\w.-]+\/[\w.-]+$/.test(repo) || file.startsWith('/') || file.includes('\\')) return null;
  const parts: string[] = [];
  for (const part of `${root}/${file}`.split('/')) {
    if (!part || part === '.') continue;
    if (part === '..') {
      if (!parts.length) return null;
      parts.pop();
    } else parts.push(part);
  }
  return `https://github.com/${repo}/blob/main/${parts.map(encodeURIComponent).join('/')}`;
}
