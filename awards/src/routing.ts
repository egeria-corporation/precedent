/**
 * URL and window helpers, out of the entry module.
 *
 * Every named export of a Worker's entry module is treated as a handler by the runtime,
 * so a helper exported from there fails at startup rather than at build time. These also
 * need to be importable by tests, which the entry module is a poor place to be.
 */

/** The last five complete federal fiscal years. The current one is partial, and a partial
 *  year dragged into a cohort statistic reads as a collapse in awards that has not happened. */
export function defaultWindow(today = new Date()): [number, number] {
  const fy = today.getUTCMonth() >= 9 ? today.getUTCFullYear() + 1 : today.getUTCFullYear();
  const until = fy - 1;
  return [until - 4, until];
}

/** Canonical form is `93.243`. Anything that is recognisably a listing number normalizes
 *  to it, and everything else is refused rather than guessed at. */
export function canonicalAln(raw: string): string | null {
  const text = decodeURIComponent(raw).trim();
  const dotted = /^(\d{2})\.(\d{3}[A-Za-z]?)$/.exec(text);
  if (dotted) return `${dotted[1]}.${dotted[2]}`;
  const bare = /^(\d{2})(\d{3}[A-Za-z]?)$/.exec(text);
  if (bare) return `${bare[1]}.${bare[2]}`;
  // A title-slug variant such as 93.243-substance-abuse-...
  const slug = /^(\d{2})[.-]?(\d{3}[A-Za-z]?)-/.exec(text);
  if (slug) return `${slug[1]}.${slug[2]}`;
  return null;
}
