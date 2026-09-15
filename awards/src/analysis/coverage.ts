/**
 * What a pass-through answer does not cover, attached to every pass-through answer.
 *
 * Single audits are filed only by organizations that expend at or above the federal single
 * audit threshold. Everyone below it files nothing, so they are **absent from this data, not
 * counted as zero**. A subrecipient count from this source is therefore a floor, and a
 * reader who does not know that will read a floor as a total.
 *
 * The threshold note is written once here and rendered from here, so it cannot drift between
 * pages, and it renders **above** any table it qualifies rather than in a footer. That is a
 * correctness requirement, and it is also what makes the difference between an accountant
 * trusting this site and dismantling it.
 */

import { COVERAGE_START_YEAR } from "../sources/fac";

export const THRESHOLD_OLD = 750_000;
export const THRESHOLD_NEW = 1_000_000;
export const THRESHOLD_EFFECTIVE = "fiscal years beginning on or after 2024-10-01";

export const THRESHOLD_NOTE =
  "Single audits are only filed by organizations that expend at or above the federal " +
  "single audit threshold in a fiscal year. That threshold was $750,000 and rose to " +
  "$1,000,000 for fiscal years beginning on or after 2024-10-01. Organizations below the " +
  "threshold file nothing, so they are absent from this data entirely, not counted as " +
  "zero. This list is therefore skewed toward larger recipients and larger intermediaries, " +
  "and every subrecipient count is a floor rather than a total.";

export const FAC_VINTAGE_NOTE = "FAC production refreshes weekly, typically Wednesdays";

export interface PassthroughCoverage {
  thresholdNote: string;
  thresholdOld: number;
  thresholdNew: number;
  thresholdEffective: string;
  auditsScanned: number;
  auditYears: number[];
  state: string;
  countsAreFloors: true;
  unattributedIndirectLines: number;
  facEarliestAuditYear: number;
  facRetrieved: string | null;
  facDataVintageNote: string;
  notes: string[];
}

export function buildCoverage(input: {
  state: string;
  auditsScanned: number;
  auditYears: number[];
  unattributedIndirectLines: number;
  retrieved: string | null;
  requestedSinceYear?: number;
}): PassthroughCoverage {
  const notes: string[] = [];
  if (input.requestedSinceYear !== undefined && input.requestedSinceYear < COVERAGE_START_YEAR) {
    notes.push(
      [
        `Audit years before ${COVERAGE_START_YEAR} were requested but this source does not`,
        "serve them; earlier single audits are in the legacy Census extracts. The window was",
        `clamped to ${COVERAGE_START_YEAR}.`,
      ].join(" "),
    );
  }
  if (input.unattributedIndirectLines) {
    notes.push(
      [
        `${input.unattributedIndirectLines.toLocaleString()} award line(s) report money`,
        "received through a pass-through entity without naming one. They are counted here",
        "and excluded from every cluster, because attributing them to anybody would be a guess.",
      ].join(" "),
    );
  }
  if (!input.auditsScanned) {
    notes.push(
      "No single audits were found for this state and window, which usually means the filter " +
        "is wrong rather than that no organization received federal money.",
    );
  }
  return {
    thresholdNote: THRESHOLD_NOTE,
    thresholdOld: THRESHOLD_OLD,
    thresholdNew: THRESHOLD_NEW,
    thresholdEffective: THRESHOLD_EFFECTIVE,
    auditsScanned: input.auditsScanned,
    auditYears: [...input.auditYears].sort((a, b) => a - b),
    state: input.state,
    countsAreFloors: true,
    unattributedIndirectLines: input.unattributedIndirectLines,
    facEarliestAuditYear: COVERAGE_START_YEAR,
    facRetrieved: input.retrieved ? input.retrieved.slice(0, 10) : null,
    facDataVintageNote: FAC_VINTAGE_NOTE,
    notes,
  };
}
