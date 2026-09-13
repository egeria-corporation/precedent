/**
 * One small stylesheet, inlined into every page.
 *
 * Inlined rather than linked because it is under 3 KB and a separate request would be a
 * second round trip for something every page needs before it can be read. There is no
 * client-side JavaScript on this site at all: everything here is content that exists in the
 * initial response, which is both the search requirement and the honest way to serve a page
 * whose whole value is a number somebody is going to quote.
 */

export const STYLES = `
:root {
  --ink: #16181d;
  --muted: #5b6472;
  --rule: #e3e6ea;
  --bg: #ffffff;
  --accent: #1a4d8f;
  --flag-bg: #fbf6e9;
  --flag-edge: #d9c38a;
  --measure: 42rem;
}
@media (prefers-color-scheme: dark) {
  :root {
    --ink: #e8eaed; --muted: #9aa4b2; --rule: #2a2f37; --bg: #14161a;
    --accent: #7fb0ea; --flag-bg: #221f16; --flag-edge: #5a4d2c;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
main { max-width: 62rem; margin: 0 auto; padding: 1.5rem 1.25rem 4rem; }
header.site, footer.site { border-bottom: 1px solid var(--rule); }
footer.site { border-bottom: 0; border-top: 1px solid var(--rule); margin-top: 3rem; }
header.site nav, footer.site div { max-width: 62rem; margin: 0 auto; padding: .85rem 1.25rem; }
header.site a { margin-right: 1.1rem; }
a { color: var(--accent); }
h1 { font-size: 1.6rem; line-height: 1.25; margin: .4rem 0 .2rem; }
h2 { font-size: 1.15rem; margin: 2rem 0 .6rem; }
h3 { font-size: 1rem; margin: 1.4rem 0 .4rem; }
p, li { max-width: var(--measure); }
.lede { color: var(--muted); margin-top: 0; }
.headline {
  border: 1px solid var(--flag-edge); background: var(--flag-bg);
  border-radius: 6px; padding: 1rem 1.1rem; margin: 1.4rem 0;
}
.headline .rate { font-size: 2.4rem; font-weight: 650; line-height: 1; letter-spacing: -.02em; }
.headline p { margin: .5rem 0 0; }
.stats { display: flex; flex-wrap: wrap; gap: 1.75rem; margin: 1.2rem 0; padding: 0; list-style: none; }
.stats div { min-width: 8rem; }
.stats .n { display: block; font-size: 1.3rem; font-weight: 600; }
.stats .k { color: var(--muted); font-size: .85rem; }
table { border-collapse: collapse; width: 100%; margin: .6rem 0 1rem; font-size: .95rem; }
th, td { text-align: left; padding: .4rem .6rem .4rem 0; border-bottom: 1px solid var(--rule); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.wrap { overflow-x: auto; }
.note, .caveats { border-left: 3px solid var(--flag-edge); padding: .1rem 0 .1rem .9rem; margin: 1rem 0; }
.caveats li { margin: .35rem 0; }
.provenance { color: var(--muted); font-size: .9rem; }
.disclosure { color: var(--muted); font-size: .85rem; max-width: var(--measure); }
svg.dist { max-width: 100%; height: auto; display: block; margin: .6rem 0; }
svg.dist rect { fill: var(--accent); }
svg.dist text { fill: var(--muted); font-size: 11px; }
`.trim();
