/**
 * What must be in the HTML of the initial response.
 *
 * These are acceptance criteria from the build prompt, not preferences, so they are checked
 * here rather than by looking at the page once. A number that only appears after JavaScript
 * runs is a number that will not be cited, and a page that loses its disclosure or its
 * canonical link in a refactor is a page that should fail the build.
 */

import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { type Award, buildProfile } from "../src/analysis/profile";
import { renderToHtml, renderUnavailable } from "../src/render/html";
import { ProgramPage } from "../src/render/program";

const fixture = JSON.parse(
  gunzipSync(readFileSync("test/fixtures/parity-93243.json.gz")).toString("utf8"),
) as { program: string; sinceFy: number; untilFy: number; awards: Award[] };

const ORIGIN = "https://awards.opengrants.io";
const profile = buildProfile(fixture.awards, {
  program: fixture.program,
  sinceFy: fixture.sinceFy,
  untilFy: fixture.untilFy,
});

const html = renderToHtml(
  ProgramPage({
    origin: ORIGIN,
    profile,
    title: "Substance Abuse and Mental Health Services Projects",
    agency: "Department of Health and Human Services",
    retrieved: "2026-09-13T12:00:00.000Z",
    vintage: "fac2026-08-26-usa2026-08-29",
  }),
);

describe("the program page, in the initial response", () => {
  it("is a complete document", () => {
    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain('<html lang="en">');
  });

  it("leads with the new-entrant rate, above the median", () => {
    // The ordering is a requirement: the median says whether you are the right size, the
    // new-entrant rate says whether the door is open at all.
    const rateAt = html.indexOf("New-entrant rate");
    const medianAt = html.indexOf("median award");
    expect(rateAt).toBeGreaterThan(-1);
    expect(medianAt).toBeGreaterThan(-1);
    expect(rateAt).toBeLessThan(medianAt);
  });

  it("states the headline as a sentence, not a bare percentage", () => {
    expect(html).toContain(`of ${profile.recipientCount.toLocaleString("en-US")} recipients`);
    expect(html).toContain("had won no award under this program");
  });

  it("carries the median and the award counts as text a crawler can read", () => {
    const median = `$${Math.round(profile.sizes.median as number).toLocaleString("en-US")}`;
    expect(html).toContain(median);
    expect(html).toContain(profile.windowAwardCount.toLocaleString("en-US"));
  });

  it("renders the distribution as a chart and as a table, never the chart alone", () => {
    expect(html).toContain("<svg");
    expect((html.match(/<rect/g) ?? []).length).toBe(profile.sizes.buckets.length);
    // Every bucket count also appears in a table row, which is what survives copy and paste.
    expect(html).toContain("Share of dollars");
  });

  it("runs no client-side JavaScript at all", () => {
    const scripts = html.match(/<script[^>]*>/g) ?? [];
    expect(scripts.every((s) => s.includes("application/ld+json"))).toBe(true);
  });

  it("names its own canonical URL", () => {
    expect(html).toContain(`<link rel="canonical" href="${ORIGIN}/programs/93.243"`);
  });

  it("carries the structured data that makes it machine-quotable", () => {
    expect(html).toContain("GovernmentService");
    expect(html).toContain("BreadcrumbList");
    expect(html).toContain('"@type":"Dataset"');
    expect(html).toContain("api.usaspending.gov");
    // temporalCoverage is what tells a model which years these numbers describe.
    expect(html).toContain(
      `"temporalCoverage":"${profile.sinceFy - 1}-10-01/${profile.untilFy}-09-30"`,
    );
  });

  it("states its source and vintage in visible body text, not only in markup", () => {
    expect(html).toContain("Computed");
    expect(html).toContain("2026-09-13");
    expect(html).toContain("fac2026-08-26-usa2026-08-29");
  });

  it("carries the disclosure verbatim in the footer", () => {
    expect(html).toContain(
      "This is informational only, derived from public data on the dates shown. It is not an " +
        "eligibility determination, and not legal, tax, or accounting advice. Verify against " +
        "the official source before relying on it.",
    );
  });

  it("links to the repository and the methodology from every page", () => {
    expect(html).toContain("github.com/egeria-corporation/precedent");
    expect(html).toContain('href="/methodology"');
  });
});

describe("when the figures cannot be computed", () => {
  const page = renderUnavailable(ORIGIN, "93.243", "USAspending did not answer.");

  it("says what is missing and why, rather than rendering an empty statistic", () => {
    expect(page).toContain("No figures are shown for this program right now");
    expect(page).toContain("USAspending did not answer.");
    // No zeroes standing in for numbers nobody computed.
    expect(page).not.toContain("New-entrant rate");
    expect(page).not.toContain("$0");
  });

  it("still carries the disclosure and the canonical link", () => {
    expect(page).toContain("eligibility determination");
    expect(page).toContain(`<link rel="canonical" href="${ORIGIN}/programs/93.243"`);
  });
});
