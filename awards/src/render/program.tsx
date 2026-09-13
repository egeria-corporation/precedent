/**
 * The program page.
 *
 * The new-entrant rate comes first, above the median, in its own block. That ordering is a
 * requirement and it is the right one: the median tells a reader whether their organization
 * is in the right weight class, but the new-entrant rate tells them whether the door is
 * open at all, and a program with a healthy median and a new-entrant rate near zero is a
 * closed shop with good optics.
 *
 * The distribution renders as inline SVG *and* as a table. Never the chart alone: a crawler
 * cannot read a chart, and neither can somebody copying numbers into a proposal.
 */

import type { FC } from "hono/jsx";
import type { Profile } from "../analysis/profile";
import { breadcrumbs, derivedDataset, governmentService } from "./jsonld";
import { Page, count, money, rate } from "./layout";

const BUCKET_LABELS: Record<string, string> = {
  under_100k: "Under $100k",
  "100k_250k": "$100k - $250k",
  "250k_500k": "$250k - $500k",
  "500k_1m": "$500k - $1M",
  "1m_5m": "$1M - $5M",
  "5m_plus": "$5M and over",
};

export interface ProgramPageProps {
  origin: string;
  profile: Profile;
  title: string | null;
  agency: string | null;
  retrieved: string | null;
  vintage: string;
}

/**
 * The headline sentence.
 *
 * Stated as a sentence rather than left as a bare percentage, because "39.7%" invites a
 * reader to supply their own meaning and "288 of 725 recipients had won nothing under this
 * program in the five years before" does not.
 */
const Headline: FC<{ p: Profile }> = ({ p }) => {
  if (!p.recipientCount) {
    return (
      <div class="headline">
        <p>
          No recipients resolved in FY{p.sinceFy}-FY{p.untilFy}, so a new-entrant rate cannot be
          computed for this window. That is usually a program that made no assistance awards in
          these years rather than a program nobody new could enter.
        </p>
      </div>
    );
  }
  const bound = p.newEntrantRateIsUpperBound ? " at most" : "";
  return (
    <div class="headline">
      <span class="rate">{rate(p.newEntrantRate)}</span>
      {p.newEntrantRateIsUpperBound ? <span class="k"> (upper bound)</span> : null}
      <p>
        <strong>New-entrant rate.</strong> {count(p.newEntrantCount)} of {count(p.recipientCount)}{" "}
        recipients in FY{p.sinceFy}-FY{p.untilFy} had{bound} won no award under this program in the
        FY{p.lookbackSinceFy}-FY{p.sinceFy - 1} lookback.
      </p>
    </div>
  );
};

/** The distribution, as a chart and as a table. Both, always. */
const Distribution: FC<{ p: Profile }> = ({ p }) => {
  const buckets = p.sizes.buckets;
  if (!p.sizes.count || !buckets.length) return null;
  const max = Math.max(...buckets.map((b) => b.count), 1);
  const barW = 78;
  const gap = 14;
  const chartH = 130;
  const width = buckets.length * (barW + gap);

  return (
    <>
      <h2>Award size distribution</h2>
      <p class="provenance">Each award's total obligation over its life, not a yearly figure.</p>
      <div class="wrap">
        <svg
          class="dist"
          viewBox={`0 0 ${width} ${chartH + 34}`}
          width={width}
          height={chartH + 34}
          role="img"
          aria-label={`Award size distribution across ${buckets.length} size bands`}
        >
          {buckets.map((b, i) => {
            const h = Math.round((b.count / max) * chartH);
            const x = i * (barW + gap);
            return (
              <>
                <rect x={x} y={chartH - h} width={barW} height={h} rx="2" />
                <text x={x} y={chartH - h - 5}>
                  {b.count}
                </text>
                <text x={x} y={chartH + 16}>
                  {BUCKET_LABELS[b.name] ?? b.name}
                </text>
                <text x={x} y={chartH + 29}>
                  {(b.shareOfAwards * 100).toFixed(1)}%
                </text>
              </>
            );
          })}
        </svg>
      </div>
      <div class="wrap">
        <table>
          <thead>
            <tr>
              <th>Award size</th>
              <th class="num">Awards</th>
              <th class="num">Share of awards</th>
              <th class="num">Share of dollars</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((b) => (
              <tr>
                <td>{BUCKET_LABELS[b.name] ?? b.name}</td>
                <td class="num">{count(b.count)}</td>
                <td class="num">{(b.shareOfAwards * 100).toFixed(1)}%</td>
                <td class="num">{(b.shareOfDollars * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
};

export const ProgramPage: FC<ProgramPageProps> = ({
  origin,
  profile: p,
  title,
  agency,
  retrieved,
  vintage,
}) => {
  const canonical = `${origin}/programs/${p.program}`;
  const name = title ?? `Assistance Listing ${p.program}`;
  const s = p.sizes;
  const description =
    p.recipientCount && p.newEntrantRate !== null
      ? `${count(p.windowAwardCount)} awards to ${count(p.recipientCount)} recipients under ` +
        `Assistance Listing ${p.program}, FY${p.sinceFy}-FY${p.untilFy}. New-entrant rate ` +
        `${rate(p.newEntrantRate)}, median award ${money(s.median)}.`
      : `Award history for Assistance Listing ${p.program}, FY${p.sinceFy}-FY${p.untilFy}.`;

  return (
    <Page
      title={`${p.program} ${name} - award history and new-entrant rate`}
      description={description}
      canonical={canonical}
      jsonLd={[
        governmentService(origin, p, title, agency),
        derivedDataset(origin, p, retrieved),
        breadcrumbs(origin, [
          ["Programs", "/programs"],
          [p.program, `/programs/${p.program}`],
        ]),
      ]}
    >
      <h1>
        {p.program} {name}
      </h1>
      <p class="lede">
        {agency ? `${agency}. ` : ""}Assistance awards with a base obligation date in FY
        {p.sinceFy}-FY{p.untilFy}.
      </p>

      <Headline p={p} />

      <ul class="stats">
        <div>
          <span class="n">{count(p.windowAwardCount)}</span>
          <span class="k">awards in window</span>
        </div>
        <div>
          <span class="n">{count(p.recipientCount)}</span>
          <span class="k">distinct recipients</span>
        </div>
        <div>
          <span class="n">{money(s.total)}</span>
          <span class="k">obligated</span>
        </div>
        <div>
          <span class="n">{money(s.median)}</span>
          <span class="k">median award</span>
        </div>
        <div>
          <span class="n">{rate(p.repeatWinnerRate)}</span>
          <span class="k">won more than once</span>
        </div>
        {p.concentrationTop10Share !== null ? (
          <div>
            <span class="n">{rate(p.concentrationTop10Share)}</span>
            <span class="k">held by the top 10</span>
          </div>
        ) : null}
      </ul>

      {s.count ? (
        <>
          <h2>Award size</h2>
          <div class="wrap">
            <table>
              <tbody>
                <tr>
                  <td>Median</td>
                  <td class="num">{money(s.median)}</td>
                  <td>Mean</td>
                  <td class="num">
                    {money(s.mean)}
                    {s.meanIsSkewed ? " (skewed by large awards)" : ""}
                  </td>
                </tr>
                <tr>
                  <td>10th percentile</td>
                  <td class="num">{money(s.percentiles.p10)}</td>
                  <td>25th percentile</td>
                  <td class="num">{money(s.percentiles.p25)}</td>
                </tr>
                <tr>
                  <td>75th percentile</td>
                  <td class="num">{money(s.percentiles.p75)}</td>
                  <td>90th percentile</td>
                  <td class="num">{money(s.percentiles.p90)}</td>
                </tr>
                <tr>
                  <td>Smallest</td>
                  <td class="num">{money(s.minimum)}</td>
                  <td>Largest</td>
                  <td class="num">{money(s.maximum)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p class="note">
          No award in this window carried a positive obligated amount, so no size statistics can be
          computed. An award whose total obligation is zero or less was unwound rather than paid.
        </p>
      )}

      <Distribution p={p} />

      {p.topRecipientsByDollars.length ? (
        <>
          <h2>Largest recipients by dollars</h2>
          <div class="wrap">
            <table>
              <thead>
                <tr>
                  <th>Recipient</th>
                  <th class="num">Awards</th>
                  <th class="num">Total obligated</th>
                </tr>
              </thead>
              <tbody>
                {p.topRecipientsByDollars.map((r) => (
                  <tr>
                    <td>{r.displayName || "(unnamed)"}</td>
                    <td class="num">{count(r.awardCount)}</td>
                    <td class="num">{money(r.totalDollars)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {p.topStatesByCount.length ? (
        <>
          <h2>Geography</h2>
          <p>
            {count(p.statesCovered)} states or territories by place of performance.{" "}
            {p.topStatesByCount.map(([st, n], i) => (
              <>
                {i ? ", " : ""}
                <a href={`/programs/${p.program}/${st.toLowerCase()}`}>{st}</a> {count(n)}
              </>
            ))}
          </p>
        </>
      ) : null}

      {p.caveats.length ? (
        <div class="caveats">
          <h2>Read this before quoting any of the above</h2>
          <ul>
            {p.caveats.map((caveat) => (
              <li>{caveat}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <h2>How these numbers were produced</h2>
      <p class="provenance">
        Computed{" "}
        {retrieved
          ? `from data retrieved ${retrieved.slice(0, 10)}`
          : "from data whose retrieval date is not recorded"}{" "}
        from the <a href="https://api.usaspending.gov/">USAspending API</a>, over assistance awards
        whose base obligation date falls in FY{p.sinceFy}-FY{p.untilFy}. Recipients were matched by{" "}
        {Object.entries(p.identityResolution)
          .sort(([a], [b]) => (a < b ? -1 : 1))
          .map(([tier, share], i) => `${i ? ", " : ""}${tier} ${(share * 100).toFixed(0)}%`)
          .join("")}
        . Every definition is on the <a href="/methodology">methodology page</a>. Data vintage{" "}
        <code>{vintage}</code>.
      </p>
      <p class="provenance">
        The same computation as JSON:{" "}
        <a href={`/api/programs/${p.program}.json`}>/api/programs/{p.program}.json</a>
      </p>
    </Page>
  );
};
