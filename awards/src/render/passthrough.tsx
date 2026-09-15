/**
 * The pass-through pages: the reason this site exists.
 *
 * Nothing else on the internet answers "which organizations pass federal money down to
 * nonprofits in this state". USAspending shows the award to the state agency; the
 * organizations it re-grants to appear only in single audits, where each subrecipient's own
 * auditor had to name who passed the money.
 *
 * Two rules shape every page here:
 *
 * - **The coverage warning renders above any table it qualifies.** Not a footer, not a
 *   tooltip, not something collapsed. Every count below it is a floor, and a reader who
 *   takes a floor for a total is wrong by however many organizations spend under the single
 *   audit threshold - which is most of them.
 * - **The raw name variants are printed.** Showing the clustering is what makes it
 *   auditable, and auditability is the trust argument for the whole site.
 */

import type { FC } from "hono/jsx";
import type { PassthroughCoverage } from "../analysis/coverage";
import type { Intermediary, PassthroughResult } from "../analysis/passthrough";
import { intermediarySlug } from "../analysis/passthrough";
import { breadcrumbs } from "./jsonld";
import { Page, count, money } from "./layout";

/** The threshold note, above the table it qualifies. Rendered from coverage.ts so it
 *  cannot drift between pages. */
export const Coverage: FC<{ coverage: PassthroughCoverage }> = ({ coverage: c }) => (
  <div class="note">
    <p>
      <strong>Read this before quoting any count below.</strong> {c.thresholdNote}
    </p>
    {c.notes.map((note) => (
      <p>{note}</p>
    ))}
  </div>
);

const Variants: FC<{ entity: Intermediary }> = ({ entity }) => {
  if (entity.nameVariants.length < 2) return null;
  return (
    <details>
      <summary>
        {entity.nameVariants.length} spellings on the schedules, clustered into this entity
      </summary>
      <div class="wrap">
        <table>
          <thead>
            <tr>
              <th>As the auditor typed it</th>
              <th class="num">Lines</th>
              <th>Example report</th>
            </tr>
          </thead>
          <tbody>
            {entity.nameVariants.map((v) => (
              <tr>
                <td>{v.raw}</td>
                <td class="num">{count(v.count)}</td>
                <td>
                  <code>{v.exampleReportId}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
};

export interface StatePageProps {
  origin: string;
  result: PassthroughResult;
  stateName: string;
  vintage: string;
}

export const PassthroughStatePage: FC<StatePageProps> = ({
  origin,
  result: r,
  stateName,
  vintage,
}) => {
  const c = r.coverage;
  const path = r.program
    ? `/passthrough/${r.state.toLowerCase()}/${r.program}`
    : `/passthrough/${r.state.toLowerCase()}`;
  const scope = r.program ? ` under Assistance Listing ${r.program}` : "";
  const years = c.auditYears.length
    ? `audit years ${c.auditYears[0]} through ${c.auditYears[c.auditYears.length - 1]}`
    : "no audit years in range";

  return (
    <Page
      title={`Who passes federal money to organizations in ${stateName}${scope}`}
      description={
        `${count(r.intermediaries.length)} pass-through entities named by organizations in ` +
        `${stateName}${scope}, ranked by how many distinct organizations name them. From ` +
        `${count(c.auditsScanned)} single audits, ${years}.`
      }
      canonical={`${origin}${path}`}
      jsonLd={[
        breadcrumbs(origin, [
          ["Pass-through", "/passthrough"],
          [stateName, `/passthrough/${r.state.toLowerCase()}`],
          ...(r.program ? [[r.program, path] as [string, string]] : []),
        ]),
      ]}
    >
      <h1>
        Who passes federal money to organizations in {stateName}
        {scope}
      </h1>
      <p class="lede">
        USAspending records the award the government made. It does not record what happened next.
        These are the entities that organizations in {stateName} named as the source of money they
        received through somebody, in their own single audits.
      </p>

      <Coverage coverage={c} />

      <p>
        {count(c.auditsScanned)} single audits scanned, {years}.
      </p>

      {r.intermediaries.length ? (
        <>
          <h2>Entities passing money down, by how many organizations name them</h2>
          <p class="provenance">
            Ranked by distinct organizations rather than by dollars. Dollars tell you which
            intermediary is biggest; the count tells you which one actually makes subawards to
            organizations like yours, and that is the question being asked.
          </p>
          <div class="wrap">
            <table>
              <thead>
                <tr>
                  <th>Pass-through entity</th>
                  <th class="num">Organizations</th>
                  <th class="num">Audits</th>
                  <th class="num">Expended</th>
                  <th>Identifier</th>
                </tr>
              </thead>
              <tbody>
                {r.intermediaries.map((e) => (
                  <tr>
                    <td>
                      <a href={`/intermediaries/${intermediarySlug(e.state, e.clusterKey)}`}>
                        {e.canonicalName}
                      </a>
                      {e.fromAliasTable ? (
                        <span class="k"> (name from the alias table)</span>
                      ) : null}
                    </td>
                    <td class="num">{count(e.subrecipientCount)}</td>
                    <td class="num">{count(e.observationCount)}</td>
                    <td class="num">{money(e.amountExpendedTotal)}</td>
                    <td>
                      {e.ein ? (
                        <>
                          EIN {e.ein}{" "}
                          <span class="k">({e.identifierSource.replace(/_/g, " ")})</span>
                        </>
                      ) : (
                        <span class="k">name only</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p class="note">
          No organization in {stateName} reported receiving money through a named pass-through
          entity under this filter. That is not the same as nobody doing it: organizations below the
          single audit threshold file nothing at all.
        </p>
      )}

      {r.suppliers.length ? (
        <>
          <h2>Organizations here that report passing money down</h2>
          <p class="provenance">
            Their own audits, so these carry a real Employer Identification Number and a real city.
            This is the stream that lends identifiers to the names above.
          </p>
          <div class="wrap">
            <table>
              <thead>
                <tr>
                  <th>Organization</th>
                  <th>EIN</th>
                  <th>City</th>
                  <th class="num">Passed down</th>
                </tr>
              </thead>
              <tbody>
                {r.suppliers.slice(0, 25).map((s) => (
                  <tr>
                    <td>{s.name}</td>
                    <td>{s.ein ?? "-"}</td>
                    <td>{s.city ?? "-"}</td>
                    <td class="num">{money(s.passthroughAmountTotal)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      <h2>How this was produced</h2>
      <p class="provenance">
        Computed from the <a href="https://www.fac.gov/api/">Federal Audit Clearinghouse API</a>
        {c.facRetrieved ? `, retrieved ${c.facRetrieved}` : ""}. {c.facDataVintageNote}. Coverage
        begins with audit year {c.facEarliestAuditYear}. Names were clustered by a committed alias
        table and by exact normalized match within {r.state}; nothing is clustered across states,
        and an initialism is only ever resolved through the table. Every definition is on the{" "}
        <a href="/methodology">methodology page</a>. Data vintage <code>{vintage}</code>.
      </p>
    </Page>
  );
};

export interface IntermediaryPageProps {
  origin: string;
  entity: Intermediary;
  stateName: string;
  coverage: PassthroughCoverage;
  vintage: string;
}

export const IntermediaryPage: FC<IntermediaryPageProps> = ({
  origin,
  entity: e,
  stateName,
  coverage: c,
  vintage,
}) => {
  const slug = intermediarySlug(e.state, e.clusterKey);
  return (
    <Page
      title={`${e.canonicalName} - federal money passed to organizations in ${stateName}`}
      description={
        `${e.canonicalName} is named by ${count(e.subrecipientCount)} organizations in ` +
        `${stateName} as the entity that passed federal money to them, across ` +
        `${count(e.observationCount)} single audits.`
      }
      canonical={`${origin}/intermediaries/${slug}`}
      jsonLd={[
        {
          "@context": "https://schema.org",
          "@type": "Organization",
          name: e.canonicalName,
          url: `${origin}/intermediaries/${slug}`,
          // taxID where known is the highest-leverage markup on the site: it is what makes
          // this page resolvable to a specific organization rather than to a name.
          ...(e.ein ? { taxID: e.ein } : {}),
          address: {
            "@type": "PostalAddress",
            addressRegion: e.state,
            addressCountry: "US",
            ...(e.city ? { addressLocality: e.city } : {}),
          },
          ...(e.nameVariants.length > 1 ? { alternateName: e.nameVariants.map((v) => v.raw) } : {}),
        },
        breadcrumbs(origin, [
          ["Pass-through", "/passthrough"],
          [stateName, `/passthrough/${e.state.toLowerCase()}`],
          [e.canonicalName, `/intermediaries/${slug}`],
        ]),
      ]}
    >
      <h1>{e.canonicalName}</h1>
      <p class="lede">
        Named by organizations in {stateName} as the entity that passed federal money to them.
        {e.ein ? (
          <>
            {" "}
            Employer Identification Number {e.ein}, matched{" "}
            {e.identifierSource === "supply_side_match"
              ? "from this entity's own single audit"
              : "from the committed alias table"}
            .
          </>
        ) : (
          <>
            {" "}
            No Employer Identification Number is known for this entity: the single audits that name
            it record a name and nothing else, and a name match is not an identity match.
          </>
        )}
      </p>

      <Coverage coverage={c} />

      <ul class="stats">
        <div>
          <span class="n">{count(e.subrecipientCount)}</span>
          <span class="k">organizations funded</span>
        </div>
        <div>
          <span class="n">{count(e.observationCount)}</span>
          <span class="k">single audits naming it</span>
        </div>
        <div>
          <span class="n">{money(e.amountExpendedTotal)}</span>
          <span class="k">expended by those organizations</span>
        </div>
      </ul>

      {e.programs.length ? (
        <>
          <h2>Programs</h2>
          <p>
            {e.programs.map(([listing, n], i) => (
              <>
                {i ? ", " : ""}
                <a href={`/programs/${listing}`}>{listing}</a> ({count(n)})
              </>
            ))}
          </p>
        </>
      ) : null}

      <h2>Organizations that named this entity</h2>
      <div class="wrap">
        <table>
          <thead>
            <tr>
              <th>Organization</th>
              <th>City</th>
              <th>EIN</th>
              <th class="num">Expended</th>
            </tr>
          </thead>
          <tbody>
            {e.subrecipients.slice(0, 25).map((s) => (
              <tr>
                <td>{s.name ?? "(unnamed)"}</td>
                <td>{s.city ?? "-"}</td>
                <td>{s.ein ?? "-"}</td>
                <td class="num">{money(s.amountExpended)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {e.subrecipients.length > 25 ? (
        <p class="provenance">
          Showing 25 of {count(e.subrecipients.length)}. The complete list is in the JSON.
        </p>
      ) : null}

      <h2>How the name was clustered</h2>
      <p class="provenance">
        <code>passthrough_name</code> is free text an auditee's auditor typed. Clustering it is
        required and will never be perfect, so it is shown rather than hidden.
      </p>
      <Variants entity={e} />
      <p class="provenance">
        Computed from the <a href="https://www.fac.gov/api/">Federal Audit Clearinghouse API</a>
        {c.facRetrieved ? `, retrieved ${c.facRetrieved}` : ""}. Data vintage <code>{vintage}</code>
        .
      </p>
    </Page>
  );
};
