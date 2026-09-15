/**
 * The pages that explain the site rather than compute anything.
 *
 * `/methodology` defines every statistic with its arithmetic, because a page that shows its
 * work gets cited and a page that asserts bare numbers does not. `/coverage` states what the
 * data does not reach, in one place, linked from every footer. Neither is marketing copy.
 */

import type { FC } from "hono/jsx";
import {
  THRESHOLD_EFFECTIVE,
  THRESHOLD_NEW,
  THRESHOLD_NOTE,
  THRESHOLD_OLD,
} from "../analysis/coverage";
import { BUCKETS, COVERAGE_START, DEFAULT_LOOKBACK_YEARS } from "../analysis/profile";
import { LIVE_SIBLINGS } from "../seo/siblings";
import { COVERAGE_START_YEAR } from "../sources/fac";
import { Page, REPO, money } from "./layout";

export const Home: FC<{ origin: string }> = ({ origin }) => (
  <Page
    title="Federal award history and pass-through funders"
    description="Who has won a federal grant program before, and who actually passes federal money down to smaller organizations. Computed from public federal data, with the method published."
    canonical={`${origin}/`}
  >
    <h1>Two questions about federal money</h1>
    <p class="lede">Both are answerable from public data, and neither is usually answered.</p>

    <h2>Who has actually won this program before?</h2>
    <p>
      Not the eligibility language in the notice of funding opportunity, which describes who may
      apply. The organizations that did win, how large their awards were, and - the number that
      changes a decision - how many of them had never won under that program in the five years
      before.
    </p>
    <p>
      A program with a healthy median award and a new-entrant rate near zero is a closed shop with
      good optics. That is worth knowing before writing a proposal, and it takes one page to see.
      Try <a href="/programs/93.243">93.243, substance abuse and mental health projects</a>, or{" "}
      <a href="/programs">browse by program</a>.
    </p>

    <h2>Who would actually fund an organization like mine?</h2>
    <p>
      Most federal money does not reach a small organization directly. It goes to a state agency, a
      university or a large nonprofit, which re-grants it. USAspending records the first award and
      nothing after it, so the intermediary is invisible there.
    </p>
    <p>
      Single audits record it, because an organization spending federal money above the threshold
      has to file a schedule naming who passed the money to it. This site reads those schedules. Try{" "}
      <a href="/passthrough/oh">who passes federal money to organizations in Ohio</a>, or{" "}
      <a href="/passthrough">pick a state</a>.
    </p>

    <h2>What this site will not do</h2>
    <ul>
      <li>
        Tell you whether you are eligible for anything. It reports what happened, not what will
        happen.
      </li>
      <li>
        Present a pass-through count as complete. Those counts are floors, always, and every page
        carrying one says so above the table rather than in a footer. See{" "}
        <a href="/coverage">coverage</a>.
      </li>
      <li>
        Hide its arithmetic. Every statistic is defined on the{" "}
        <a href="/methodology">methodology page</a>, and the code that computes it is{" "}
        <a href={REPO}>open source</a>.
      </li>
    </ul>

    <p class="provenance">
      The same computations run locally with no account and no key:{" "}
      <code>uvx federal-precedent history 93.243</code>.
    </p>
  </Page>
);

export const Methodology: FC<{ origin: string }> = ({ origin }) => (
  <Page
    title="Methodology: how every number on this site is computed"
    description="Definitions and worked arithmetic for the new-entrant rate, award size percentiles, distribution buckets, identity resolution and pass-through clustering."
    canonical={`${origin}/methodology`}
  >
    <h1>Methodology</h1>
    <p class="lede">
      Every statistic, defined. Where two defensible choices produce two different numbers, the
      choice made here is named and the reason given, because only one of them can be reproduced.
    </p>

    <h2>The window</h2>
    <p>
      A federal fiscal year runs from October 1 of the prior calendar year to September 30. The
      default window is the last five <em>complete</em> fiscal years; the current one is excluded
      because it is partial, and a partial year dragged into a cohort statistic reads as a collapse
      in awards that has not happened.
    </p>
    <p>
      An award belongs to the fiscal year of its <strong>first obligating action</strong>, taken
      from <code>Base Obligation Date</code>, not to the year we happened to fetch it in. The pull
      itself runs a year past the window, because USAspending filters on transaction activity rather
      than on that first obligation, so an award obligated inside the window and modified after it
      is only returned by the wider pull. The extra year widens what is fetched and never what is
      counted.
    </p>

    <h2>The new-entrant rate</h2>
    <p>
      The share of the window's distinct recipients that had won nothing under the same Assistance
      Listing in the {DEFAULT_LOOKBACK_YEARS} fiscal years immediately before it. Stated on every
      page as a sentence rather than a bare percentage, because "39.7%" invites a reader to supply
      their own meaning.
    </p>
    <p>
      It is reported as an <strong>upper bound</strong> when the lookback reaches before{" "}
      <code>{COVERAGE_START}</code>, which is as far back as this search covers, or when the
      lookback is empty because the program did not exist yet. In both cases some recipients counted
      as new may have won earlier.
    </p>

    <h2>Award size</h2>
    <p>
      Computed over awards, not recipients. The amount is <code>Award Amount</code>, which is the
      total obligated over the life of an award rather than a yearly figure.
    </p>
    <p>
      An award whose amount is null, zero or negative is excluded from the universe entirely - not
      just from the size statistics. That figure is a lifetime obligation, so at or below zero the
      award was approved and then unwound, the organization ended up with nothing, and counting it
      as a recipient would say a program let somebody new in when it gave them no money.
    </p>
    <p>
      Percentiles use the <strong>inclusive</strong> method. The exclusive method is the more common
      default and gives different answers on small samples, which is exactly a niche program's
      situation; on one real program the two differ by $57 at the 25th percentile. The 50th
      percentile and the median agree to within a cent, by construction.
    </p>
    <p>Distribution buckets are fixed rather than data-derived, so two programs can be compared:</p>
    <ul>
      {BUCKETS.map(([name, lo, hi]) => (
        <li>
          <code>{name}</code>: {money(lo)} to {Number.isFinite(hi) ? money(hi) : "no upper limit"},
          half-open, so a boundary amount lands in exactly one bucket
        </li>
      ))}
    </ul>

    <h2>Deciding when two records are the same organization</h2>
    <p>
      Both headline rates count <em>distinct organizations</em>, so splitting one grantee in two
      makes a program look more open than it is and merging two makes it look closed. Identity is
      resolved in descending order of how much the identifier is worth:
    </p>
    <ol>
      <li>
        <strong>Unique Entity Identifier.</strong> Assigned and unique.
      </li>
      <li>
        <strong>USAspending's recipient id, with its level suffix stripped.</strong> The same
        organization appears as <code>-C</code>, <code>-R</code> and <code>-P</code>; keeping the
        suffix splits it into three.
      </li>
      <li>
        <strong>Normalized name.</strong> A last resort. Every page reports how often it was needed,
        because a program resolved mostly by name has weaker counts than one resolved by identifier.
      </li>
    </ol>

    <h2>Pass-through clustering</h2>
    <p>
      <code>passthrough_name</code> on a single audit schedule is free text an auditor typed.
      Clustering it is required and will never be perfect, so it is deliberately timid: a committed
      alias table that a person maintains, then exact normalized match within one state, and nothing
      else. Clusters never cross a state, and an initialism is only ever resolved through the table,
      because the same three letters name a different agency elsewhere.
    </p>
    <p>
      A wrongly merged entity asserts a fact that is not true. A split entity merely undercounts.
      This site would rather undercount, and every intermediary page prints the raw spellings that
      were merged so the decision can be checked.
    </p>
    <p>
      Where an intermediary carries an Employer Identification Number, the page says how it was
      obtained. A name agreeing with a name is a name match, and it is never presented as an
      identity match.
    </p>

    <h2>Two directions, never confused</h2>
    <p>
      On a single audit schedule, <code>is_direct = false</code> means the filer <em>received</em>{" "}
      money through somebody, who is named on a separate row.{" "}
      <code>is_passthrough_award = true</code> with a positive amount means the filer{" "}
      <em>passed money down</em> to its own subrecipients. They are opposite ends of the same pipe
      and this site computes them as separate streams, merging them only for display.
    </p>

    <p class="provenance">
      The same statistics, computed by the same rules, run locally:{" "}
      <a href={REPO}>the precedent repository</a>.
    </p>
  </Page>
);

export const CoveragePage: FC<{ origin: string }> = ({ origin }) => (
  <Page
    title="Coverage: what this data does not reach"
    description="The single audit threshold, the multi-listing distortion, and the two dates before which these sources do not usefully reach."
    canonical={`${origin}/coverage`}
  >
    <h1>What this data does not reach</h1>
    <p class="lede">
      Every limitation below changes how a number on this site should be read. None of them is
      hidden in a footnote elsewhere.
    </p>

    <h2>The single audit threshold</h2>
    <div class="note">
      <p>{THRESHOLD_NOTE}</p>
    </div>
    <p>
      The threshold was {money(THRESHOLD_OLD)} and rose to {money(THRESHOLD_NEW)} for{" "}
      {THRESHOLD_EFFECTIVE}. This is the most consequential limitation on the site: a pass-through
      entity that funds two hundred small organizations and four large ones will appear here with
      four.
    </p>

    <h2>Awards reported under more than one Assistance Listing</h2>
    <p>
      A single award can be reported under several listings, and its amount is not apportioned
      between them. Where enough of a program's awards do this, the size percentiles include money
      from other programs and the page says so. Treat them as an upper bound.
    </p>

    <h2>Two floors in the sources</h2>
    <ul>
      <li>
        <strong>Single audits: audit year {COVERAGE_START_YEAR}.</strong> Earlier ones are in the
        legacy Census extracts, which this API does not serve.
      </li>
      <li>
        <strong>USAspending: {COVERAGE_START}.</strong> A lookback window reaching before it is
        truncated, so new-entrant rates computed across that boundary are upper bounds and are
        labelled as such on the page.
      </li>
    </ul>

    <h2>Restatement</h2>
    <p>
      Federal spending data is restated. Every page prints the date its numbers were retrieved, and
      a figure quoted without that date cannot be reproduced later. That is why the vintage appears
      in visible text rather than only in metadata.
    </p>

    <h2>What is not here at all</h2>
    <ul>
      <li>Awards below the reporting thresholds of the source systems.</li>
      <li>
        Subawards that no single audit records, which is most subawards by count and few by dollar.
      </li>
      <li>Any prediction. This site reports what happened; it does not estimate what will.</li>
    </ul>
  </Page>
);

export const About: FC<{ origin: string }> = ({ origin }) => (
  <Page
    title="About awards.opengrants.io"
    description="Who builds this, what it is for, and where the code lives."
    canonical={`${origin}/about`}
  >
    <h1>About</h1>
    <p>
      This site is the hosted companion to <code>precedent</code>, an open source command line tool
      that computes the same statistics locally. Both are built by Egeria Corporation and sponsored
      by OpenGrants, and both are Apache 2.0.
    </p>
    <p>
      Everything here is derived from public federal data. Nothing on this site is behind an
      account, a key or a paywall, and the derived JSON is available at{" "}
      <code>/api/programs/&lt;listing&gt;.json</code> with CORS open, because a number derived from
      public records is not something to make anyone ask for.
    </p>

    <h2>The code</h2>
    <p>
      <a href={REPO}>github.com/egeria-corporation/precedent</a>. The statistics the site renders
      and the statistics the tool prints are checked against each other on every push, against
      several thousand real award records, because a site that disagrees with its own tool is worse
      than one that does not exist: both look authoritative and only one can be right.
    </p>

    <h2>Related</h2>
    <ul>
      {LIVE_SIBLINGS.map((s) => (
        <li>
          <a href={s.host}>{s.host.replace("https://", "")}</a> - {s.label}
        </li>
      ))}
    </ul>

    <h2>Corrections</h2>
    <p>
      Errors here are worth reporting and will be fixed in public:{" "}
      <a href={`${REPO}/issues`}>open an issue</a>. If a pass-through entity is clustered wrongly,
      the intermediary page prints the raw spellings that were merged, which is usually enough to
      say exactly what went wrong.
    </p>
  </Page>
);
