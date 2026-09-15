/**
 * Pass-through clustering, the two evidence streams, and the coverage that rides along.
 *
 * The bias under test throughout: a wrongly merged entity asserts a fact that is not true,
 * a split entity merely undercounts, and this site would rather undercount.
 */

import { describe, expect, it } from "vitest";
import { THRESHOLD_NOTE, buildCoverage } from "../src/analysis/coverage";
import {
  buildIntermediaries,
  buildPassthrough,
  buildSuppliers,
  clusterKey,
  intermediarySlug,
} from "../src/analysis/passthrough";
import {
  type Audit,
  type PassThrough,
  type SefaAward,
  UEI_PLACEHOLDER,
  awardKey,
  passedMoneyDown,
  receivedThroughSomeone,
  toAudit,
  toSefaAward,
} from "../src/sources/fac";

function audit(id: string, over: Partial<Audit> = {}): Audit {
  return {
    reportId: id,
    auditYear: "2023",
    auditeeName: "Small Nonprofit",
    auditeeEin: "111",
    auditeeUei: null,
    auditeeCity: "Columbus",
    auditeeState: "OH",
    entityType: "nonprofit",
    totalAmountExpended: 900_000,
    facAcceptedDate: null,
    ...over,
  };
}

function sefa(id: string, over: Partial<SefaAward> = {}): SefaAward {
  return {
    reportId: id,
    awardReference: "AWARD-1",
    federalAgencyPrefix: "93",
    federalAwardExtension: "045",
    federalProgramName: "Aging",
    amountExpended: 100_000,
    isDirect: false,
    isPassthroughAward: false,
    passthroughAmount: null,
    clusterName: "AGING CLUSTER",
    auditYear: "2023",
    ...over,
  };
}

function named(id: string, ref: string, name: string): PassThrough {
  return { reportId: id, awardReference: ref, name, identifier: null, auditYear: "2023" };
}

describe("the flags FAC sends as strings where its dictionary promises booleans", () => {
  it("reads Y and N rather than treating both as truthy", () => {
    // Both are truthy in JavaScript. Reading one straight marks every row direct and
    // inverts the entire feature.
    expect(toSefaAward({ report_id: "r", is_direct: "N" }).isDirect).toBe(false);
    expect(toSefaAward({ report_id: "r", is_direct: "Y" }).isDirect).toBe(true);
  });

  it("keeps the two directions apart", () => {
    const received = toSefaAward({ report_id: "r", is_direct: "N" });
    expect(receivedThroughSomeone(received)).toBe(true);
    expect(passedMoneyDown(received)).toBe(false);

    const passed = toSefaAward({
      report_id: "r",
      is_direct: "Y",
      is_passthrough_award: "Y",
      passthrough_amount: 5000,
    });
    expect(passedMoneyDown(passed)).toBe(true);
    expect(receivedThroughSomeone(passed)).toBe(false);
  });

  it("does not call a zero-dollar passthrough flag passing money down", () => {
    const flagged = toSefaAward({
      report_id: "r",
      is_passthrough_award: "Y",
      passthrough_amount: 0,
    });
    expect(passedMoneyDown(flagged)).toBe(false);
  });

  it("drops the migration placeholder rather than joining strangers on it", () => {
    // auditee_uei holds the literal GSA_MIGRATION on legacy records. Kept as a value it
    // joins tens of thousands of unrelated organizations to one another.
    expect(toAudit({ report_id: "r", auditee_uei: UEI_PLACEHOLDER }).auditeeUei).toBeNull();
    expect(toAudit({ report_id: "r", auditee_uei: "KNY3ET8DBBB8" }).auditeeUei).toBe(
      "KNY3ET8DBBB8",
    );
  });
});

describe("the join key", () => {
  it("cannot collide however a report id or award reference is spelled", () => {
    // A separator character could occur inside either value, and a collision silently joins
    // two different SEFA lines to one pass-through entity.
    expect(awardKey("A B", null)).not.toBe(awardKey("A", "B"));
    expect(awardKey("r1", "AWARD-1")).toBe(awardKey("r1", "AWARD-1"));
  });
});

describe("clustering", () => {
  it("resolves an initialism only through the committed table", () => {
    expect(clusterKey("ODA", "OH")).toBe("OHIO DEPARTMENT OF AGING");
    // The same three letters name a different agency in another state.
    expect(clusterKey("ODA", "TX")).toBe("ODA");
  });

  it("lands every table spelling on one canonical key", () => {
    const keys = new Set(
      ["Ohio Department of Aging", "OHIO DEPT OF AGING", "ohio department on aging"].map((n) =>
        clusterKey(n, "OH"),
      ),
    );
    expect([...keys]).toEqual(["OHIO DEPARTMENT OF AGING"]);
  });

  it("clusters everything else by exact normalized match only", () => {
    expect(clusterKey("Acme Council, Inc.", "OH")).toBe(clusterKey("ACME COUNCIL INC", "OH"));
    expect(clusterKey("Acme Council", "OH")).not.toBe(clusterKey("Acme Councils", "OH"));
  });

  it("never crosses a state", () => {
    const audits = [audit("r1", { auditeeEin: "1" }), audit("r2", { auditeeEin: "2" })];
    const awards = [sefa("r1"), sefa("r2")];
    const rows = [
      named("r1", "AWARD-1", "DEPARTMENT OF AGING"),
      named("r2", "AWARD-1", "DEPARTMENT OF AGING"),
    ];
    const oh = buildIntermediaries(audits, awards, rows, "OH");
    expect(oh.intermediaries).toHaveLength(1);
    const tx = buildIntermediaries(audits, awards, rows, "TX");
    expect(tx.intermediaries.every((e) => e.state === "TX")).toBe(true);
  });
});

describe("counting", () => {
  it("counts one organization audited twice as one subrecipient", () => {
    // Otherwise an organization audited five years running looks like five grantees, and
    // the intermediary looks five times as reachable as it is.
    const audits = [
      audit("r1", { auditeeEin: "99", auditYear: "2022" }),
      audit("r2", { auditeeEin: "99", auditYear: "2023" }),
    ];
    const rows = [
      named("r1", "AWARD-1", "OHIO DEPARTMENT OF AGING"),
      named("r2", "AWARD-1", "OHIO DEPARTMENT OF AGING"),
    ];
    const { intermediaries } = buildIntermediaries(audits, [sefa("r1"), sefa("r2")], rows, "OH");
    expect(intermediaries[0]?.subrecipientCount).toBe(1);
    expect(intermediaries[0]?.observationCount).toBe(2);
  });

  it("ranks by subrecipient count before dollars", () => {
    // Deliberate: dollars name the biggest intermediary, subrecipient count names the one
    // that actually makes subawards to organizations like the reader's.
    const audits = [1, 2, 3].map((i) => audit(`r${i}`, { auditeeEin: String(i) }));
    const awards = [
      sefa("r1", { amountExpended: 10_000_000 }),
      sefa("r2", { amountExpended: 1 }),
      sefa("r3", { amountExpended: 1 }),
    ];
    const rows = [
      named("r1", "AWARD-1", "ONE BIG GRANT COUNCIL"),
      named("r2", "AWARD-1", "MANY SMALL GRANTS COUNCIL"),
      named("r3", "AWARD-1", "MANY SMALL GRANTS COUNCIL"),
    ];
    const { intermediaries } = buildIntermediaries(audits, awards, rows, "OH");
    expect(intermediaries[0]?.canonicalName).toBe("MANY SMALL GRANTS COUNCIL");
    expect(intermediaries[0]?.amountExpendedTotal).toBeLessThan(
      intermediaries[1]?.amountExpendedTotal as number,
    );
  });

  it("counts an indirect line naming nobody rather than dropping it", () => {
    const audits = [audit("r1", { auditeeEin: "1" }), audit("r2", { auditeeEin: "2" })];
    const rows = [named("r1", "AWARD-1", "OHIO DEPARTMENT OF AGING")];
    const { intermediaries, unattributed } = buildIntermediaries(
      audits,
      [sefa("r1"), sefa("r2")],
      rows,
      "OH",
    );
    expect(unattributed).toBe(1);
    expect(intermediaries.reduce((s, e) => s + e.subrecipientCount, 0)).toBe(1);
  });
});

describe("the supply side", () => {
  it("counts only lines that passed real dollars down, and keeps its real identifiers", () => {
    const audits = [audit("r1", { auditeeName: "Ohio Department of Aging", auditeeEin: "310000" })];
    const awards = [
      sefa("r1", { awardReference: "A1", isPassthroughAward: true, passthroughAmount: 500_000 }),
      sefa("r1", { awardReference: "A2", isPassthroughAward: true, passthroughAmount: 0 }),
      sefa("r1", { awardReference: "A3", isPassthroughAward: false }),
    ];
    const suppliers = buildSuppliers(audits, awards);
    expect(suppliers).toHaveLength(1);
    expect(suppliers[0]?.passthroughAmountTotal).toBe(500_000);
    expect(suppliers[0]?.ein).toBe("310000");
  });

  it("records that an identifier came from a name match, never as an identity match", () => {
    const demandAudit = audit("r1", { auditeeEin: "1" });
    const supplyAudit = audit("r2", {
      auditeeName: "Buckeye Hills Regional Council",
      auditeeEin: "310807186",
    });
    const result = buildPassthrough({
      state: "OH",
      program: "93.045",
      audits: [demandAudit, supplyAudit],
      indirectAwards: [sefa("r1")],
      passthroughRows: [named("r1", "AWARD-1", "Buckeye Hills Regional Council")],
      supplyAwards: [
        sefa("r2", { awardReference: "A1", isPassthroughAward: true, passthroughAmount: 1000 }),
      ],
      retrieved: "2026-09-15T00:00:00.000Z",
    });
    const matched = result.intermediaries[0];
    expect(matched?.ein).toBe("310807186");
    expect(matched?.identifierSource).toBe("supply_side_match");
  });

  it("claims no identifier when the supply side names a different organization", () => {
    // Ohio's suppliers include "STATE OF OHIO", which does not normalize to "OHIO
    // DEPARTMENT OF AGING". Borrowing its EIN would be inventing an identity.
    const result = buildPassthrough({
      state: "OH",
      program: null,
      audits: [
        audit("r1", { auditeeEin: "1" }),
        audit("r2", { auditeeName: "State of Ohio", auditeeEin: "311334820" }),
      ],
      indirectAwards: [sefa("r1")],
      passthroughRows: [named("r1", "AWARD-1", "Ohio Department of Aging")],
      supplyAwards: [
        sefa("r2", { awardReference: "A1", isPassthroughAward: true, passthroughAmount: 1000 }),
      ],
      retrieved: null,
    });
    expect(result.intermediaries[0]?.ein).toBeNull();
    expect(result.intermediaries[0]?.identifierSource).toBe("none");
  });
});

describe("coverage rides on every result", () => {
  it("carries the threshold note verbatim, and says absent rather than zero", () => {
    const c = buildCoverage({
      state: "OH",
      auditsScanned: 10,
      auditYears: [2022, 2023],
      unattributedIndirectLines: 0,
      retrieved: "2026-09-15T00:00:00.000Z",
    });
    expect(c.thresholdNote).toBe(THRESHOLD_NOTE);
    expect(c.thresholdNote).toContain("absent from this data entirely, not counted as zero");
    expect(c.countsAreFloors).toBe(true);
    expect(c.facRetrieved).toBe("2026-09-15");
  });

  it("is present on a result with no data at all", () => {
    const result = buildPassthrough({
      state: "oh",
      program: null,
      audits: [],
      indirectAwards: [],
      passthroughRows: [],
      supplyAwards: [],
      retrieved: null,
    });
    expect(result.coverage.thresholdNote).toBe(THRESHOLD_NOTE);
    expect(result.state).toBe("OH");
  });

  it("discloses a window clamped to the coverage floor", () => {
    const c = buildCoverage({
      state: "OH",
      auditsScanned: 1,
      auditYears: [2016],
      unattributedIndirectLines: 0,
      retrieved: null,
      requestedSinceYear: 2009,
    });
    expect(c.notes.some((n) => n.includes("clamped to 2016"))).toBe(true);
  });

  it("explains unattributed lines rather than leaving a bare number", () => {
    const c = buildCoverage({
      state: "OH",
      auditsScanned: 5,
      auditYears: [2023],
      unattributedIndirectLines: 7,
      retrieved: null,
    });
    expect(c.notes.some((n) => n.includes("without naming one"))).toBe(true);
  });
});

describe("intermediary slugs", () => {
  it("carry the state, which is how the entity is found again", () => {
    expect(intermediarySlug("OH", "OHIO DEPARTMENT OF AGING")).toBe("oh-ohio-department-of-aging");
  });

  it("are url-safe whatever the auditor typed", () => {
    const slug = intermediarySlug("OH", "ACME & SONS, L.L.C. #2");
    expect(slug).toMatch(/^[a-z0-9-]+$/);
    expect(slug.startsWith("oh-")).toBe(true);
  });
});
