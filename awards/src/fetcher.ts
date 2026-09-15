/**
 * Every outbound request this Worker makes, with a name on it and a retry behind it.
 *
 * Two things that a bare `fetch` does not do, and both matter here.
 *
 * **A User-Agent.** These are free public APIs. An operator whose service this site strains
 * should be able to see who is doing it and reach us, and an anonymous request is both rude
 * and the kind of traffic an origin is most willing to drop. The Python client this site is
 * a companion to has always sent one.
 *
 * **Retries on the transient failures.** A single unretried fetch is fragile in a way that
 * shows up as a blank page rather than as an error anyone notices. 525 is in the retry set
 * deliberately: it is Cloudflare's own SSL-handshake-failed, raised when the edge cannot
 * negotiate TLS with an origin, and it is frequently per-colo and transient rather than a
 * property of the origin.
 *
 * Retries are capped and backed off. A site that hammers a public API on failure is the
 * load problem the whole cache layer exists to prevent.
 */

export const USER_AGENT = "awards.opengrants.io (+https://github.com/egeria-corporation/precedent)";

/** 525 is Cloudflare's SSL handshake failure; 520-527 are its other origin-reach errors. */
const RETRY_STATUS = new Set([
  408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527,
]);

const ATTEMPTS = 3;
const BASE_DELAY_MS = 400;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export class UpstreamFailure extends Error {
  constructor(
    readonly source: string,
    readonly status: number | null,
    message: string,
  ) {
    super(message);
    this.name = "UpstreamFailure";
  }
}

export interface PoliteRequest {
  source: string;
  url: string;
  method?: "GET" | "POST";
  body?: unknown;
  headers?: Record<string, string>;
}

/** Fetch with our name attached, retrying the statuses that are worth retrying. */
export async function politeFetch(request: PoliteRequest): Promise<Response> {
  const { source, url, method = "GET", body, headers = {} } = request;
  let lastStatus: number | null = null;
  let lastDetail = "no attempt was made";

  for (let attempt = 0; attempt < ATTEMPTS; attempt++) {
    try {
      const response = await fetch(url, {
        method,
        headers: {
          "user-agent": USER_AGENT,
          accept: "application/json",
          ...(body ? { "content-type": "application/json" } : {}),
          ...headers,
        },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if (response.ok) return response;
      lastStatus = response.status;
      lastDetail = `HTTP ${response.status}`;
      if (!RETRY_STATUS.has(response.status)) break;
    } catch (error) {
      // A thrown fetch is a transport failure, which is exactly what a retry is for.
      lastStatus = null;
      lastDetail = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
    }
    if (attempt < ATTEMPTS - 1) await sleep(BASE_DELAY_MS * 2 ** attempt);
  }

  throw new UpstreamFailure(
    source,
    lastStatus,
    `${source} did not answer after ${ATTEMPTS} attempts: ${lastDetail}`,
  );
}
