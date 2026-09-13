/**
 * The page shell: head, navigation, footer, and the things every page must carry.
 *
 * Three of those are requirements rather than furniture, and they live here so no page can
 * be built without them: a canonical link on every page including the canonical one, the
 * disclosure verbatim in the footer, and a link to the repository and the methodology.
 */

import type { FC, PropsWithChildren } from "hono/jsx";
import { DISCLOSURE } from "../content";
import { STYLES } from "../styles";

export const REPO = "https://github.com/egeria-corporation/precedent";

export interface PageMeta {
  title: string;
  description: string;
  canonical: string;
  /** JSON-LD objects for the head. Entity pages always carry at least a BreadcrumbList. */
  jsonLd?: unknown[];
}

/** Dollars with thousands separators and no cents. */
export function money(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

/** Rates to one decimal place. */
export function rate(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

export function count(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString("en-US");
}

export const Page: FC<PropsWithChildren<PageMeta>> = ({
  title,
  description,
  canonical,
  jsonLd,
  children,
}) => (
  <html lang="en">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>{title}</title>
      <meta name="description" content={description} />
      {/* On every page, including the canonical one: a page that does not name its own
          canonical URL leaves a crawler to decide, and it will decide differently than we do. */}
      <link rel="canonical" href={canonical} />
      <meta property="og:title" content={title} />
      <meta property="og:description" content={description} />
      <meta property="og:url" content={canonical} />
      <meta property="og:type" content="website" />
      <meta name="twitter:card" content="summary" />
      {(jsonLd ?? []).map((block) => (
        // Serialized here from our own objects; serializeJsonLd escapes the one sequence
        // that could close the script element early. No user input reaches this.
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: serializeJsonLd(block) }}
        />
      ))}
      {/* A constant stylesheet from this repository: no interpolation, no user input. */}
      <style dangerouslySetInnerHTML={{ __html: STYLES }} />
    </head>
    <body>
      <header class="site">
        <nav>
          <a href="/">awards.opengrants.io</a>
          <a href="/programs">Programs</a>
          <a href="/passthrough">Pass-through</a>
          <a href="/methodology">Methodology</a>
          <a href="/coverage">Coverage</a>
        </nav>
      </header>
      <main>{children}</main>
      <footer class="site">
        <div>
          <p class="disclosure">{DISCLOSURE}</p>
          <p class="disclosure">
            Open source: <a href={REPO}>the precedent repository</a>. How every number here is
            defined: <a href="/methodology">methodology</a>. What this data does not cover:{" "}
            <a href="/coverage">coverage</a>.
          </p>
        </div>
      </footer>
    </body>
  </html>
);

/**
 * JSON-LD as a string safe to place inside a script element.
 *
 * `</script` inside a JSON string would end the element early and drop the rest of the page
 * into the document as markup. Escaping the slash keeps the JSON valid and the element
 * intact; the parser reads `<\/script` as `</script`.
 */
export function serializeJsonLd(value: unknown): string {
  return JSON.stringify(value).replace(/<\/(script)/gi, "<\\/$1");
}
