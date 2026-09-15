/**
 * The sitemap index and its chunks, written to R2 by the scheduled Worker.
 *
 * An index from day one even though one chunk holds everything this site has: retrofitting
 * an index later means changing the URL search engines already know, and the cost of having
 * one now is a few lines.
 *
 * **No URL for a combination with no data.** The full cross product of 56 states by 2,300
 * Assistance Listings is 128,800 URLs, almost all of which would be empty pages. An empty
 * page that ranks is worse than no page, and generating them to grow a URL count is the
 * single most effective way to make this site look like spam.
 */

export const CHUNK_SIZE = 50_000;

/** Below this an intermediary is one filing, which is an anecdote rather than a finding. */
export const MIN_INTERMEDIARY_EVIDENCE = 2;

export interface SitemapUrl {
  loc: string;
  lastmod: string;
  /** Left off entirely rather than guessed at: a fabricated priority is noise. */
  changefreq?: "daily" | "weekly" | "monthly";
}

function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

export function renderUrlset(urls: SitemapUrl[]): string {
  const body = urls
    .map(
      (u) =>
        `  <url><loc>${escapeXml(u.loc)}</loc><lastmod>${u.lastmod}</lastmod>${
          u.changefreq ? `<changefreq>${u.changefreq}</changefreq>` : ""
        }</url>`,
    )
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${body}
</urlset>
`;
}

export function renderIndex(origin: string, chunkCount: number, lastmod: string): string {
  const entries = Array.from({ length: Math.max(chunkCount, 1) }, (_, i) => {
    const loc = `${origin}/sitemaps/sitemap-${String(i + 1).padStart(5, "0")}.xml`;
    return `  <sitemap><loc>${escapeXml(loc)}</loc><lastmod>${lastmod}</lastmod></sitemap>`;
  }).join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${entries}
</sitemapindex>
`;
}

export function chunk<T>(items: T[], size = CHUNK_SIZE): T[][] {
  if (!items.length) return [[]];
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

/** Where a chunk lives in R2, under this site's own prefix in the shared bucket. */
export function chunkKey(prefix: string, index: number): string {
  return `${prefix}/sitemaps/sitemap-${String(index + 1).padStart(5, "0")}.xml`;
}

export function indexKey(prefix: string): string {
  return `${prefix}/sitemaps/sitemap.xml`;
}

export interface SitemapInputs {
  origin: string;
  lastmod: string;
  /** Assistance Listings known to have awards. Never the full catalogue. */
  programs: string[];
  states: string[];
  /** Only combinations that actually produced intermediaries. */
  statePrograms: [string, string][];
  /** Slugs of intermediaries meeting the evidence threshold. */
  intermediaries: string[];
}

export function buildUrls(input: SitemapInputs): SitemapUrl[] {
  const { origin, lastmod } = input;
  const urls: SitemapUrl[] = [
    { loc: `${origin}/`, lastmod, changefreq: "weekly" },
    { loc: `${origin}/programs`, lastmod, changefreq: "weekly" },
    { loc: `${origin}/passthrough`, lastmod, changefreq: "weekly" },
    { loc: `${origin}/methodology`, lastmod, changefreq: "monthly" },
    { loc: `${origin}/coverage`, lastmod, changefreq: "monthly" },
    { loc: `${origin}/about`, lastmod, changefreq: "monthly" },
  ];
  for (const program of input.programs) {
    urls.push({ loc: `${origin}/programs/${program}`, lastmod, changefreq: "weekly" });
  }
  for (const state of input.states) {
    urls.push({
      loc: `${origin}/passthrough/${state.toLowerCase()}`,
      lastmod,
      changefreq: "weekly",
    });
  }
  for (const [state, program] of input.statePrograms) {
    urls.push({
      loc: `${origin}/passthrough/${state.toLowerCase()}/${program}`,
      lastmod,
      changefreq: "weekly",
    });
  }
  for (const slug of input.intermediaries) {
    urls.push({ loc: `${origin}/intermediaries/${slug}`, lastmod, changefreq: "weekly" });
  }
  return urls;
}
