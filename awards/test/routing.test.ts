import { describe, expect, it } from "vitest";
import { canonicalAln, defaultWindow } from "../src/routing";

describe("canonical Assistance Listing form", () => {
  it("accepts the canonical form unchanged", () => {
    expect(canonicalAln("93.243")).toBe("93.243");
  });

  it("normalizes the variants that must never be a second URL", () => {
    // Never serve two URLs for one program: each of these redirects permanently to the
    // canonical one rather than rendering its own copy of the page.
    expect(canonicalAln("93243")).toBe("93.243");
    expect(canonicalAln("93.243-substance-abuse-and-mental-health")).toBe("93.243");
    expect(canonicalAln("93243-substance-abuse")).toBe("93.243");
    expect(canonicalAln(" 93.243 ")).toBe("93.243");
  });

  it("keeps the alphabetic suffix some listings carry", () => {
    expect(canonicalAln("84.425C")).toBe("84.425C");
    expect(canonicalAln("84425C")).toBe("84.425C");
  });

  it("refuses anything that is not a listing number rather than guessing", () => {
    for (const bad of ["", "abc", "9.243", "93.24", "93.2431", "../etc/passwd", "93"]) {
      expect(canonicalAln(bad)).toBeNull();
    }
  });
});

describe("the default window", () => {
  it("is the last five complete fiscal years", () => {
    // The current fiscal year is partial, and a partial year dragged into a cohort
    // statistic reads as a collapse in awards that has not happened.
    expect(defaultWindow(new Date("2026-01-15T00:00:00Z"))).toEqual([2021, 2025]);
    expect(defaultWindow(new Date("2026-09-30T00:00:00Z"))).toEqual([2021, 2025]);
  });

  it("rolls forward the day the federal fiscal year does", () => {
    expect(defaultWindow(new Date("2026-10-01T00:00:00Z"))).toEqual([2022, 2026]);
  });
});
