/**
 * schema.org structured data.
 *
 * This is what makes a page machine-quotable. A model or a crawler that reads only the
 * markup should still come away with the program, who runs it, what period the statistics
 * cover, when they were computed, and what they were computed from - and `isBasedOn`
 * pointing at the USAspending API is the part that says these numbers are derived rather
 * than asserted.
 */

import type { Profile } from "../analysis/profile";

const CREATOR = {
  "@type": "Organization",
  name: "Egeria Corporation",
  url: "https://github.com/egeria-corporation",
};

export function breadcrumbs(origin: string, trail: [string, string][]): unknown {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: trail.map(([name, path], i) => ({
      "@type": "ListItem",
      position: i + 1,
      name,
      item: `${origin}${path}`,
    })),
  };
}

export function governmentService(
  origin: string,
  profile: Profile,
  title: string | null,
  agency: string | null,
): unknown {
  return {
    "@context": "https://schema.org",
    "@type": "GovernmentService",
    name: title ?? `Assistance Listing ${profile.program}`,
    identifier: profile.program,
    url: `${origin}/programs/${profile.program}`,
    ...(agency ? { serviceOperator: { "@type": "GovernmentOrganization", name: agency } } : {}),
    serviceType: "Federal financial assistance",
    areaServed: { "@type": "Country", name: "United States" },
  };
}

export function derivedDataset(
  origin: string,
  profile: Profile,
  retrieved: string | null,
): unknown {
  return {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name: `Award history statistics for Assistance Listing ${profile.program}`,
    description: [
      "Derived award-size distribution, new-entrant rate and recipient concentration for",
      `Assistance Listing ${profile.program}, federal fiscal years ${profile.sinceFy}`,
      `through ${profile.untilFy}.`,
    ].join(" "),
    url: `${origin}/programs/${profile.program}`,
    // Schema.org's ISO 8601 interval form. The fiscal year runs to September 30.
    temporalCoverage: `${profile.sinceFy - 1}-10-01/${profile.untilFy}-09-30`,
    ...(retrieved ? { dateModified: retrieved.slice(0, 10) } : {}),
    creator: CREATOR,
    license: "https://www.apache.org/licenses/LICENSE-2.0",
    isBasedOn: {
      "@type": "Dataset",
      name: "USAspending award data",
      url: "https://api.usaspending.gov/",
    },
    variableMeasured: [
      { "@type": "PropertyValue", name: "Awards in window", value: profile.windowAwardCount },
      { "@type": "PropertyValue", name: "Distinct recipients", value: profile.recipientCount },
      ...(profile.newEntrantRate !== null
        ? [
            {
              "@type": "PropertyValue",
              name: "New-entrant rate",
              value: Number((profile.newEntrantRate * 100).toFixed(1)),
              unitText: "percent",
            },
          ]
        : []),
      ...(profile.sizes.median !== null
        ? [
            {
              "@type": "PropertyValue",
              name: "Median award size",
              value: Math.round(profile.sizes.median),
              unitCode: "USD",
            },
          ]
        : []),
    ],
  };
}
