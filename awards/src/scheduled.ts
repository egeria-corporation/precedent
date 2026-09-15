/**
 * The Thursday job: probe the upstreams, bump the vintage, warm the cache, write sitemaps.
 *
 * Thursday because FAC production refreshes weekly and typically on Wednesdays, so this
 * probes the day after rather than racing it.
 *
 * **Everything here is sequential and paced.** These are two free public APIs, and a warmer
 * that fanned out across 56 states would be a load problem for somebody else's
 * infrastructure - the exact thing the cache layer exists to prevent. A cold state page
 * costs around 90 seconds of sequential FAC calls, so the warmer does a handful per run and
 * lets the vintage do the rest: pages nobody requests do not need warming, and pages
 * somebody requests warm themselves.
 */

import { readVintage, writeVintage } from "./cache";
import { type SitemapUrl, chunkKey, indexKey, renderIndex, renderUrlset } from "./seo/sitemap";
import { buildUrls, chunk } from "./seo/sitemap";
import { STATES } from "./states";
import type { Env } from "./types";

/** Between warm requests. Politeness, not performance. */
const PACE_MS = 2000;

/** Per run. The rest warm on demand; a page nobody asks for does not need to be fast. */
const MAX_WARM = 8;

/** Assistance Listings worth keeping warm, and worth listing in the sitemap from day one. */
const SEED_PROGRAMS = [
  "93.243",
  "93.959",
  "93.788",
  "93.045",
  "16.842",
  "84.425",
  "10.558",
  "14.218",
];

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * What the upstreams say their newest data is.
 *
 * FAC exposes `fac_accepted_date`, so one ordered row is the whole probe. USAspending has no
 * equivalent, so its half of the vintage is the current ISO week: award records for closed
 * fiscal years do not change, and the ones that do are restated on no schedule anybody
 * publishes. A weekly bucket is honest about that rather than pretending to a precision the
 * source does not offer.
 */
export async function probeVintage(env: Env): Promise<string> {
  let facStamp = "unknown";
  if (env.FAC_API_KEY) {
    try {
      const response = await fetch(
        "https://api.fac.gov/general?select=fac_accepted_date&order=fac_accepted_date.desc&limit=1",
        { headers: { "X-Api-Key": env.FAC_API_KEY, accept: "application/json" } },
      );
      if (response.ok) {
        const rows = (await response.json()) as { fac_accepted_date?: string }[];
        facStamp = rows[0]?.fac_accepted_date?.slice(0, 10) ?? "unknown";
      }
    } catch {
      // A failed probe keeps the old vintage, which is correct: the alternative is
      // invalidating the whole site because one request timed out.
      facStamp = "unknown";
    }
  }
  const now = new Date();
  const week = isoWeek(now);
  return `fac${facStamp}-usa${now.getUTCFullYear()}w${String(week).padStart(2, "0")}`;
}

/** ISO 8601 week number, so the USAspending half of the vintage moves once a week. */
export function isoWeek(date: Date): number {
  const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  // Thursday decides the week's year, which is what makes this ISO rather than approximate.
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil(((d.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7);
}

/** Fetch a page so its render lands in the Cache API, one at a time, with a pause between. */
async function warm(origin: string, paths: string[]): Promise<number> {
  let warmed = 0;
  for (const path of paths.slice(0, MAX_WARM)) {
    try {
      const response = await fetch(`${origin}${path}`, {
        headers: { "user-agent": "awards.opengrants.io cache warmer" },
      });
      if (response.ok) warmed += 1;
    } catch {
      // One failed warm is not worth ending the run over.
    }
    await sleep(PACE_MS);
  }
  return warmed;
}

/**
 * Write the sitemap index and its chunks to R2.
 *
 * Only URLs that have data. The full cross product of states by programs would be 128,800
 * mostly-empty pages, and an empty page that ranks is worse than no page.
 */
export async function writeSitemaps(env: Env, vintage: string): Promise<number> {
  const lastmod = new Date().toISOString().slice(0, 10);
  const urls: SitemapUrl[] = buildUrls({
    origin: env.SITE_ORIGIN,
    lastmod,
    programs: SEED_PROGRAMS,
    states: Object.keys(STATES),
    // Left empty until the warmer has established which combinations actually produce
    // intermediaries. Emitting them speculatively is the spam failure mode.
    statePrograms: [],
    intermediaries: [],
  });
  const chunks = chunk(urls);
  for (let i = 0; i < chunks.length; i++) {
    await env.ASSETS.put(chunkKey(env.ASSET_PREFIX, i), renderUrlset(chunks[i] as SitemapUrl[]), {
      httpMetadata: { contentType: "application/xml" },
    });
  }
  await env.ASSETS.put(
    indexKey(env.ASSET_PREFIX),
    renderIndex(env.SITE_ORIGIN, chunks.length, lastmod),
    { httpMetadata: { contentType: "application/xml" } },
  );
  return urls.length;
}

export async function scheduled(env: Env): Promise<void> {
  const previous = await readVintage(env);
  const next = await probeVintage(env);

  if (next !== previous) {
    // One short string in KV, and every cache key on both layers changes with it. No purge
    // call, no deploy, and no window where half the site is old and half is new.
    await writeVintage(env, next);
  }

  const count = await writeSitemaps(env, next);
  const warmed = await warm(env.SITE_ORIGIN, [
    "/",
    ...SEED_PROGRAMS.slice(0, 4).map((p) => `/programs/${p}`),
    "/passthrough/oh",
    "/passthrough/ca",
    "/passthrough/tx",
  ]);

  console.log(
    JSON.stringify({
      job: "weekly",
      vintageBefore: previous,
      vintageAfter: next,
      vintageChanged: next !== previous,
      sitemapUrls: count,
      pagesWarmed: warmed,
    }),
  );
}
