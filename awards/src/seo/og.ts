/**
 * The social card image, generated at the edge from the headline statistics.
 *
 * SVG rather than a rasterizer: the card is type on a flat ground, an SVG of it is under two
 * kilobytes with no dependency and no cold-start cost, and it carries the actual number
 * rather than a stock graphic. A static image would say the same thing on every page, which
 * for a site whose whole value is one number per page is close to saying nothing.
 *
 * Every text value is escaped: these strings come from upstream data, and an unescaped
 * ampersand in a recipient name produces an SVG that will not parse.
 */

export const OG_WIDTH = 1200;
export const OG_HEIGHT = 630;

export function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

/** Cut to fit the card rather than overflowing it, at a width this type size allows. */
function fit(text: string, chars: number): string {
  const clean = text.trim();
  return clean.length <= chars ? clean : `${clean.slice(0, chars - 1).trimEnd()}…`;
}

export interface OgCard {
  eyebrow: string;
  title: string;
  /** The one number worth putting on a card, and what it means. */
  figure?: string;
  figureLabel?: string;
  footnote: string;
}

export function ogImage(card: OgCard): string {
  const title = fit(card.title, 76);
  const line2 = card.title.length > 76 ? fit(card.title.slice(76), 76) : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${OG_WIDTH}" height="${OG_HEIGHT}" viewBox="0 0 ${OG_WIDTH} ${OG_HEIGHT}" role="img">
  <rect width="${OG_WIDTH}" height="${OG_HEIGHT}" fill="#14161a"/>
  <rect x="0" y="0" width="${OG_WIDTH}" height="10" fill="#1a4d8f"/>
  <text x="72" y="118" fill="#7fb0ea" font-family="Helvetica,Arial,sans-serif" font-size="28" letter-spacing="2">${escapeXml(card.eyebrow.toUpperCase())}</text>
  <text x="72" y="216" fill="#e8eaed" font-family="Helvetica,Arial,sans-serif" font-size="54" font-weight="600">${escapeXml(title)}</text>
  ${line2 ? `<text x="72" y="282" fill="#e8eaed" font-family="Helvetica,Arial,sans-serif" font-size="54" font-weight="600">${escapeXml(line2)}</text>` : ""}
  ${
    card.figure
      ? `<text x="72" y="452" fill="#ffffff" font-family="Helvetica,Arial,sans-serif" font-size="128" font-weight="700">${escapeXml(card.figure)}</text>
  <text x="72" y="500" fill="#9aa4b2" font-family="Helvetica,Arial,sans-serif" font-size="30">${escapeXml(fit(card.figureLabel ?? "", 60))}</text>`
      : ""
  }
  <text x="72" y="574" fill="#9aa4b2" font-family="Helvetica,Arial,sans-serif" font-size="24">${escapeXml(fit(card.footnote, 96))}</text>
</svg>
`;
}
