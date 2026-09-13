/**
 * Turning a component into a complete document, and the page shown when figures cannot be.
 */

import { Page } from "./layout";

/**
 * A rendered component as an HTML document.
 *
 * Hono's JSX renders to a string synchronously; the doctype is prepended here because a
 * component cannot emit one. Without it browsers fall into quirks mode, where the stylesheet
 * behaves differently for no visible reason.
 */
/** What a Hono function component returns: an element, a promise of one, or null. */
type Rendered = { toString(): string } | Promise<unknown> | null;

export function renderToHtml(element: Rendered): string {
  return `<!doctype html>${String(element)}`;
}

/**
 * The page for a program whose figures could not be computed.
 *
 * A page must never render an empty statistic, and it must never render a wrong one. This
 * says which numbers are missing and why, in a sentence, and returns 503 so a crawler
 * treats it as temporary rather than indexing an empty program page as the truth.
 */
export function renderUnavailable(origin: string, program: string, reason: string): string {
  return renderToHtml(
    <Page
      title={`${program} - figures temporarily unavailable`}
      description={`Award history for Assistance Listing ${program} could not be computed right now.`}
      canonical={`${origin}/programs/${program}`}
    >
      <h1>Assistance Listing {program}</h1>
      <div class="note">
        <p>
          <strong>No figures are shown for this program right now.</strong> {reason}
        </p>
        <p>
          This is a temporary condition rather than a statement about the program. The{" "}
          <a href="/methodology">methodology page</a> explains what is computed and from what, and
          the <code>precedent</code> command line tool computes the same profile without the limits
          an edge request has.
        </p>
      </div>
    </Page>,
  );
}
