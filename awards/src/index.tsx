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
import { renderToHtml, renderUnavailable } from "./render/html";
import { ProgramPage } from "./render/program";
import { canonicalAln, defaultWindow } from "./routing";
import { TooMuchData, buildFilters, findPrograms, search } from "./sources/usaspending";
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

/**
 * One program, computed and rendered at the edge.
 *
 * Everything a reader or a crawler needs is in this response. There is no client-side fetch
 * for primary content, because a number nobody can read without running JavaScript is a
 * number that will not be cited.
 */
app.get("/programs/:aln", async (c) => {
  const raw = c.req.param("aln");
  const aln = canonicalAln(raw);
  if (!aln) return c.notFound();
  // Never two URLs for one program. 93243, cfda/93.243 and title slugs all land here and
  // are redirected permanently rather than rendering their own copy of the page.
  if (aln !== raw) return c.redirect(`/programs/${aln}`, 301);

  return withPageCache(c.req.raw, c.executionCtx, c.env, async () => {
    const vintage = await readVintage(c.env);
    const [sinceFy, untilFy] = defaultWindow();
    const lookbackYears = 5;
    const filters = buildFilters(
      aln,
      `${sinceFy - lookbackYears - 1}-10-01`,
      `${untilFy + 1}-09-30`,
    );

    let awards: Awaited<ReturnType<typeof search>>;
    try {
      awards = await search(c.env, vintage, filters);
    } catch (error) {
      const detail =
        error instanceof TooMuchData
          ? error.message
          : "USAspending did not answer. The figures for this program are temporarily unavailable.";
      return { html: renderUnavailable(c.env.SITE_ORIGIN, aln, detail), status: 503 };
    }
    if (awards.truncated) {
      return {
        html: renderUnavailable(
          c.env.SITE_ORIGIN,
          aln,
          "This program has more awards than can be fetched in one edge request. A partial " +
            "pull would bias every statistic upward, because the upstream sorts by award " +
            "amount descending and the smallest awards are the ones that fall off the end. " +
            "No figures are shown rather than wrong ones.",
        ),
        status: 503,
      };
    }

    const profile = buildProfile(awards.awards, { program: aln, sinceFy, untilFy, lookbackYears });
    // The title and agency are cosmetic, so a failure to look them up must not cost the page.
    let title: string | null = null;
    try {
      const found = await findPrograms(c.env, vintage, aln, 1);
      title = found.programs[0]?.title ?? null;
    } catch {
      title = null;
    }
    const agency = awards.awards.find((a) => a.awardingAgency)?.awardingAgency ?? null;

    return {
      html: renderToHtml(
        <ProgramPage
          origin={c.env.SITE_ORIGIN}
          profile={profile}
          title={title}
          agency={agency}
          retrieved={awards.fetchedAt}
          vintage={vintage}
        />,
      ),
    };
  });
});

/** `/programs/93.243/oh` and the other variants that must not become second URLs. */
app.get("/cfda/:aln", (c) => {
  const aln = canonicalAln(c.req.param("aln"));
  return aln ? c.redirect(`/programs/${aln}`, 301) : c.notFound();
});
app.get("/programs/cfda/:aln", (c) => {
  const aln = canonicalAln(c.req.param("aln"));
  return aln ? c.redirect(`/programs/${aln}`, 301) : c.notFound();
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
