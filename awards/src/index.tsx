/**
 * awards.opengrants.io - federal award history and pass-through funder pages.
 *
 * Request path: Cache API (rendered HTML, keyed on schema version and data vintage)
 *   -> KV (upstream responses, same keying)
 *     -> USAspending and the Federal Audit Clearinghouse.
 *
 * R2 holds sitemap chunks only and is never in the path of a page render.
 *
 * Everything renders at the edge. Nothing is pre-rendered at build time: there are
 * thousands of Assistance Listings and fifty-six states and territories, and a build step
 * that enumerated them would be both slow and stale.
 */

import { Hono } from "hono";
import { SCHEMA_VERSION, buildProfile } from "./analysis/profile";
import { readVintage, withPageCache } from "./cache";
import { DISCLOSURE } from "./content";
import { canonicalAln, defaultWindow } from "./routing";
import { TooMuchData, buildFilters, search } from "./sources/usaspending";
import type { Env } from "./types";

const app = new Hono<{ Bindings: Env }>();

app.get("/health", (c) =>
  c.json({
    ok: true,
    schemaVersion: SCHEMA_VERSION,
    service: "awards.opengrants.io",
  }),
);

/**
 * The same computation the pages render, as JSON.
 *
 * Cheap, because the renderer already holds the object. CORS is open because a number
 * derived from public records is not something to make anyone ask for.
 */
app.get("/api/programs/:aln{.+\\.json}", async (c) => {
  const raw = c.req.param("aln").replace(/\.json$/, "");
  const aln = canonicalAln(raw);
  if (!aln) {
    return c.json({ error: `'${raw}' is not an Assistance Listing number, e.g. 93.243` }, 400);
  }

  const vintage = await readVintage(c.env);
  const [sinceFy, untilFy] = defaultWindow();
  const lookbackYears = 5;

  try {
    // The fetch runs a year past the window: action_date filters on transaction activity,
    // not on the Base Obligation Date that decides an award's cohort year, so an award
    // obligated inside the window and modified after it is only returned by the wider pull.
    const filters = buildFilters(
      aln,
      `${sinceFy - lookbackYears - 1}-10-01`,
      `${untilFy + 1}-09-30`,
    );
    const { awards, fetchedAt, truncated } = await search(c.env, vintage, filters);
    if (truncated) {
      // A truncated pull is not a smaller answer, it is a wrong one. The upstream is sorted
      // by Award Amount descending, so the records that fall off the end are the *smallest*
      // awards: every percentile shifts upward and the median can be several times too
      // high while the page looks entirely normal. Refusing is the only honest option.
      return c.json(
        {
          error:
            "This program has more awards than can be fetched within one edge request, and " +
            "a partial pull would bias every statistic upward because the upstream sorts by " +
            "award amount descending. No numbers are returned rather than wrong ones.",
          program: aln,
          vintage,
        },
        503,
      );
    }
    const profile = buildProfile(awards, { program: aln, sinceFy, untilFy, lookbackYears });
    return c.json(
      {
        ...profile,
        provenance: { sources: ["usaspending"], retrieved: fetchedAt, vintage, truncated },
        disclosure: DISCLOSURE,
      },
      200,
      {
        "access-control-allow-origin": "*",
        "cache-control": "public, max-age=3600, stale-while-revalidate=86400",
      },
    );
  } catch (error) {
    if (error instanceof TooMuchData) {
      return c.json({ error: error.message, program: aln }, 413);
    }
    throw error;
  }
});

app.get("/", async (c) =>
  withPageCache(c.req.raw, c.executionCtx, c.env, async () => ({
    html: `<!doctype html><meta charset="utf-8"><title>awards.opengrants.io</title>
<h1>awards.opengrants.io</h1>
<p>Federal award history and pass-through funder analysis. Pages are being built.</p>
<p>Working now: <a href="/api/programs/93.243.json">/api/programs/93.243.json</a></p>`,
  })),
);

export default app;
