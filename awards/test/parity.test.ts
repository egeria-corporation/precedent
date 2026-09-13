/**
 * The TypeScript port must produce the same numbers as the Python library.
 *
 * This is the acceptance criterion for the statistics on this site, and it is checked
 * against a fixture captured from the reference implementation itself: 7,681 real award
 * records, the same input, every published figure compared. A site that disagrees with the
 * tool it is a companion to is worse than one that does not exist, because both look
 * authoritative and only one of them can be right.
 *
 * Regenerate with the capture block in the M-H2 commit message if USAspending restates.
 */

import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { normalizeName, resolve, stripLevelSuffix } from "../src/analysis/identity";
import {
  type Award,
  buildProfile,
  inclusiveQuantile,
  median,
  sizeStats,
} from "../src/analysis/profile";

/**
 * Gzipped because it is 3.1 MB of real award records and a repository should not carry that
 * uncompressed to prove one thing. It stays whole rather than trimmed: the point is parity
 * at real scale, including the order floating-point addition happens in.
 */
/** What the Python reference produced for this input, as captured. */
interface ExpectedProfile {
  windowAwardCount: number;
  lookbackAwardCount: number;
  recipientCount: number;
  newEntrantCount: number;
  newEntrantRate: number;
  repeatWinnerCount: number;
  concentrationTop10Share: number;
  multiListingShare: number;
  statesCovered: number;
  sizes: {
    count: number;
    total: number;
    mean: number;
    median: number;
    minimum: number;
    maximum: number;
    percentiles: Record<string, number>;
    buckets: { name: string; count: number }[];
  };
  identityResolution: Record<string, number>;
  excluded: { missingDate: number; nonpositiveAmount: number };
  topStatesByCount: [string, number][];
}

interface ParityFixture {
  program: string;
  sinceFy: number;
  untilFy: number;
  awards: Award[];
  expected: ExpectedProfile;
}

const fixture = JSON.parse(
  // Package-relative, which is where vitest runs. Resolving through import.meta.url would
  // need node:url's URL, and this tsconfig loads the Workers URL, which is a different type.
  gunzipSync(readFileSync("test/fixtures/parity-93243.json.gz")).toString("utf8"),
) as ParityFixture;

const awards = fixture.awards;
const expected = fixture.expected;

const profile = buildProfile(awards, {
  program: fixture.program,
  sinceFy: fixture.sinceFy,
  untilFy: fixture.untilFy,
});

/** Money and counts must match exactly; only floating-point ratios get a tolerance. */
const CENT = 0.01;

describe("parity with the Python reference, on 7,681 real awards", () => {
  it("counts the same window and lookback", () => {
    expect(profile.windowAwardCount).toBe(expected.windowAwardCount);
    expect(profile.lookbackAwardCount).toBe(expected.lookbackAwardCount);
  });

  it("resolves the same number of distinct recipients", () => {
    // The single most consequential number here: it is the denominator of both headline
    // rates, and it depends on every rule in identity.ts agreeing with its original.
    expect(profile.recipientCount).toBe(expected.recipientCount);
  });

  it("finds the same new entrants and repeat winners", () => {
    expect(profile.newEntrantCount).toBe(expected.newEntrantCount);
    expect(profile.repeatWinnerCount).toBe(expected.repeatWinnerCount);
    expect(profile.newEntrantRate).toBeCloseTo(expected.newEntrantRate, 10);
  });

  it("computes the same award-size statistics to the cent", () => {
    const s = profile.sizes;
    const e = expected.sizes;
    expect(s.count).toBe(e.count);
    expect(s.total).toBeCloseTo(e.total, 2);
    expect(s.minimum as number).toBeCloseTo(e.minimum, 2);
    expect(s.maximum as number).toBeCloseTo(e.maximum, 2);
    expect(s.mean as number).toBeCloseTo(e.mean, 2);
    expect(s.median as number).toBeCloseTo(e.median, 2);
  });

  it("computes the same inclusive percentiles", () => {
    // The reference pins method="inclusive"; the library default is exclusive and gives
    // $185,956 for p25 against inclusive's $186,013 on this very data.
    for (const p of ["p10", "p25", "p50", "p75", "p90"]) {
      expect(profile.sizes.percentiles[p] as number).toBeCloseTo(
        expected.sizes.percentiles[p] as number,
        2,
      );
    }
  });

  it("places awards in the same buckets", () => {
    const got = profile.sizes.buckets.map((b) => [b.name, b.count]);
    const want = expected.sizes.buckets.map((b) => [b.name, b.count]);
    expect(got).toEqual(want);
  });

  it("reports the same concentration, multi-listing share and geography", () => {
    expect(profile.concentrationTop10Share as number).toBeCloseTo(
      expected.concentrationTop10Share,
      10,
    );
    expect(profile.multiListingShare).toBeCloseTo(expected.multiListingShare, 10);
    expect(profile.statesCovered).toBe(expected.statesCovered);
    expect(profile.topStatesByCount).toEqual(expected.topStatesByCount);
  });

  it("resolves identity at the same tiers, in the same proportions", () => {
    expect(profile.identityResolution).toEqual(expected.identityResolution);
  });

  it("excludes the same awards for the same reasons", () => {
    expect(profile.excluded.missingDate).toBe(expected.excluded.missingDate);
    expect(profile.excluded.nonpositiveAmount).toBe(expected.excluded.nonpositiveAmount);
  });
});

describe("the arithmetic the parity fixture cannot pin on its own", () => {
  it("p50 equals the median to within a cent, on odd and even counts", () => {
    for (const amounts of [
      [1, 2, 3],
      [1, 2, 3, 4],
      [10, 3, 7, 1, 99],
    ]) {
      const s = sizeStats(amounts);
      expect(Math.abs((s.percentiles.p50 as number) - (s.median as number))).toBeLessThan(CENT);
    }
  });

  it("reproduces CPython's inclusive quantiles on a known sequence", () => {
    // statistics.quantiles(range(1,11), n=100, method="inclusive")[89] is 9.1 exactly.
    const ordered = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    expect(inclusiveQuantile(ordered, 90)).toBeCloseTo(9.1, 10);
    expect(inclusiveQuantile(ordered, 50)).toBeCloseTo(5.5, 10);
    expect(median(ordered)).toBeCloseTo(5.5, 10);
  });

  it("buckets are half-open, so a boundary lands once", () => {
    const s = sizeStats([100_000]);
    expect(s.buckets.filter((b) => b.count).map((b) => b.name)).toEqual(["100k_250k"]);
  });

  it("strips the level suffix that would split one organization into three", () => {
    expect(stripLevelSuffix("ABC-C")).toBe("ABC");
    expect(stripLevelSuffix("ABC-R")).toBe("ABC");
    expect(stripLevelSuffix("ABC-P")).toBe("ABC");
    expect(stripLevelSuffix("ABC")).toBe("ABC");
  });

  it("normalizes names the way the reference does", () => {
    expect(normalizeName("The Foo Services, Inc.")).toBe("FOO SERVICES");
    expect(normalizeName("Smith & Sons LLC")).toBe("SMITH AND SONS");
    expect(normalizeName("ST Department of Health")).toBe("STATE DEPARTMENT OF HEALTH");
    expect(normalizeName("Acme Dept of Health")).toBe("ACME DEPARTMENT OF HEALTH");
  });

  it("prefers a Unique Entity Identifier over anything else", () => {
    expect(
      resolve({ recipientUei: "ABCDEFGHIJKL", recipientId: "x-C", recipientName: "Acme" }),
    ).toEqual({ tier: "uei", value: "ABCDEFGHIJKL" });
    expect(resolve({ recipientUei: null, recipientId: "x-C", recipientName: "Acme" })).toEqual({
      tier: "recipient_id",
      value: "x",
    });
    expect(resolve({ recipientUei: null, recipientId: null, recipientName: "Acme Inc" })).toEqual({
      tier: "name",
      value: "ACME",
    });
  });
});
