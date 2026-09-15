/**
 * The search and generative-engine surfaces, and the weekly job.
 *
 * The llms.txt assertions are the ones that matter most. A model summarizing this site
 * carries forward whatever it reads there, so losing the coverage limitation in a refactor
 * would mean models confidently presenting pass-through counts as complete, which is the
 * single most damaging thing this site could cause.
 */

import { describe, expect, it } from "vitest";
import { THRESHOLD_NOTE } from "../src/analysis/coverage";
import { SCHEMA_VERSION } from "../src/analysis/profile";
import { UNKNOWN_VINTAGE, pageKey } from "../src/cache";
import { isoWeek } from "../src/scheduled";
import { llmsTxt, robotsTxt } from "../src/seo/llms";
import { ogImage } from "../src/seo/og";
import { normalizeEin, siblingLinks } from "../src/seo/siblings";
import {
  CHUNK_SIZE,
  buildUrls,
  chunk,
  chunkKey,
  indexKey,
  renderIndex,
  renderUrlset,
} from "../src/seo/sitemap";

const ORIGIN = "https://awards.opengrants.io";

describe("llms.txt", () => {
  const text = llmsTxt("fac2026-09-10-usa2026w37", "2026-09-15");

  it("states the coverage limitation in the imperative, verbatim", () => {
    expect(text).toContain("## Coverage limitation you must state if you quote this data");
    expect(text).toContain(
      "Pass-through subrecipient\ncounts on this site are therefore floors, not totals",
    );
    expect(text).toContain("Any summary that presents these counts as\ncomplete is wrong.");
  });

  it("carries the vintage, so a quote can be dated", () => {
    expect(text).toContain("fac2026-09-10-usa2026w37");
    expect(text).toContain("2026-09-15");
  });

  it("names both sources and the licence", () => {
    expect(text).toContain("https://api.usaspending.gov/");
    expect(text).toContain("https://www.fac.gov/api/");
    expect(text).toContain("Apache 2.0");
  });

  it("links only to siblings that exist", () => {
    expect(text).toContain("funders.opengrants.io");
    expect(text).toContain("check.opengrants.io");
    // A dead link on a site whose argument is that it tells you what it does not know costs
    // more than the cross-link is worth.
    expect(text).not.toContain("answers.opengrants.io");
    expect(text).not.toContain("desk.opengrants.io");
  });

  it("ends by disclaiming what it is not", () => {
    expect(text).toContain("Not an eligibility determination.");
  });
});

describe("robots.txt", () => {
  it("allows everything, model crawlers included, and points at the sitemap", () => {
    // Being quoted is the objective. A site that blocks the crawlers most likely to cite it
    // has misunderstood what it is for.
    const text = robotsTxt(ORIGIN);
    expect(text).toContain("User-agent: *\nAllow: /");
    expect(text).toContain(`Sitemap: ${ORIGIN}/sitemap.xml`);
    expect(text).not.toContain("Disallow");
  });
});

describe("the sitemap", () => {
  it("is an index from day one, even with one chunk", () => {
    // Retrofitting an index later means changing a URL search engines already know.
    const xml = renderIndex(ORIGIN, 1, "2026-09-15");
    expect(xml).toContain("<sitemapindex");
    expect(xml).toContain(`${ORIGIN}/sitemaps/sitemap-00001.xml`);
    expect(xml).toContain("<lastmod>2026-09-15</lastmod>");
  });

  it("emits no URL for a combination with no data", () => {
    // The cross product of 56 states by 2,300 listings is 128,800 mostly-empty pages, and
    // an empty page that ranks is worse than no page.
    const urls = buildUrls({
      origin: ORIGIN,
      lastmod: "2026-09-15",
      programs: ["93.243"],
      states: ["OH"],
      statePrograms: [],
      intermediaries: [],
    });
    const locs = urls.map((u) => u.loc);
    expect(locs).toContain(`${ORIGIN}/programs/93.243`);
    expect(locs).toContain(`${ORIGIN}/passthrough/oh`);
    expect(locs.some((l) => l.startsWith(`${ORIGIN}/passthrough/oh/`))).toBe(false);
    expect(locs.some((l) => l.includes("/intermediaries/"))).toBe(false);
  });

  it("includes the editorial pages, which are the ones a reader is sent to", () => {
    const locs = buildUrls({
      origin: ORIGIN,
      lastmod: "2026-09-15",
      programs: [],
      states: [],
      statePrograms: [],
      intermediaries: [],
    }).map((u) => u.loc);
    for (const path of ["/", "/methodology", "/coverage", "/about"]) {
      expect(locs).toContain(`${ORIGIN}${path}`);
    }
  });

  it("escapes a URL rather than emitting XML that will not parse", () => {
    const xml = renderUrlset([{ loc: `${ORIGIN}/programs/a&b`, lastmod: "2026-09-15" }]);
    expect(xml).toContain("a&amp;b");
    expect(xml).not.toContain("a&b");
  });

  it("chunks at the sitemap limit and keys chunks predictably", () => {
    expect(CHUNK_SIZE).toBe(50_000);
    expect(
      chunk(
        Array.from({ length: 3 }, (_, i) => i),
        2,
      ),
    ).toHaveLength(2);
    // An empty site still produces one chunk, so the index is never empty.
    expect(chunk([])).toHaveLength(1);
    expect(chunkKey("awards", 0)).toBe("awards/sitemaps/sitemap-00001.xml");
    expect(indexKey("awards")).toBe("awards/sitemaps/sitemap.xml");
  });
});

describe("the social card", () => {
  it("carries the page's own figure rather than a stock graphic", () => {
    const svg = ogImage({
      eyebrow: "Assistance Listing 93.243",
      title: "3,851 awards to 2,206 recipients",
      figure: "48.5%",
      figureLabel: "had won nothing under this program in the 5 years before",
      footnote: "awards.opengrants.io - FY2021 to FY2025",
    });
    expect(svg).toContain("48.5%");
    expect(svg).toContain("3,851 awards to 2,206 recipients");
    expect(svg.startsWith("<svg")).toBe(true);
  });

  it("escapes text that would otherwise break the document", () => {
    // These strings come from upstream data; an unescaped ampersand in a recipient name
    // produces an SVG that will not parse.
    const svg = ogImage({ eyebrow: "A & B", title: "<script>", footnote: "x" });
    expect(svg).toContain("A &amp; B");
    expect(svg).toContain("&lt;script&gt;");
    expect(svg).not.toContain("<script>");
  });

  it("truncates rather than overflowing the card", () => {
    const svg = ogImage({ eyebrow: "x", title: "y".repeat(400), footnote: "z".repeat(400) });
    expect(svg).toContain("…");
  });
});

describe("sibling cross-links", () => {
  it("links only to siblings that exist", () => {
    const links = siblingLinks("54-1939556");
    expect(links.map((l) => l.href)).toEqual([
      "https://funders.opengrants.io/funders/541939556",
      "https://check.opengrants.io/541939556",
    ]);
  });

  it("emits nothing rather than a broken link when the identifier is unusable", () => {
    expect(siblingLinks(null)).toEqual([]);
    expect(siblingLinks("12345")).toEqual([]);
    expect(normalizeEin("54 1939556")).toBe("541939556");
  });
});

describe("the vintage", () => {
  it("computes ISO weeks the way the standard does", () => {
    // 2026-01-01 is a Thursday, so it belongs to week 1 of 2026.
    expect(isoWeek(new Date("2026-01-01T00:00:00Z"))).toBe(1);
    expect(isoWeek(new Date("2026-09-15T00:00:00Z"))).toBe(38);
  });

  it("is in every rendered page key, beside the schema version", () => {
    const key = pageKey(ORIGIN, "/programs/93.243", "", "fac2026-09-10-usa2026w37");
    expect(key).toContain(`v=${SCHEMA_VERSION}-fac2026-09-10-usa2026w37`);
  });

  it("falls back to a constant rather than a clock", () => {
    // A clock-derived fallback changes on every request, giving every request its own cache
    // key, which is the same as having no cache at all on the path where that hurts most.
    expect(UNKNOWN_VINTAGE).toBe("v0");
  });
});

describe("the schema version", () => {
  it("covers renders as well as arithmetic", () => {
    // Version 1 shipped a placeholder home page and version 2 replaced it. Without the bump
    // the Cache API went on serving the placeholder under the new code.
    expect(SCHEMA_VERSION).toBeGreaterThanOrEqual(2);
  });
});

describe("the threshold note", () => {
  it("is the same words in llms.txt and in coverage.ts", () => {
    // Written once and rendered from one place, so a model quoting the site and a reader
    // reading it carry the same caveat.
    const normalize = (s: string) => s.replace(/\s+/g, " ").trim();
    expect(normalize(llmsTxt("v", null))).toContain(
      normalize("Organizations below the threshold file nothing"),
    );
    expect(normalize(THRESHOLD_NOTE)).toContain(
      normalize("Organizations below the threshold file nothing"),
    );
  });
});
