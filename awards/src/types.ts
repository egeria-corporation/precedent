/**
 * Bindings and the shapes shared across modules.
 *
 * `CACHE` carries two unrelated things behind one namespace, separated by key prefix:
 * `u:` for upstream responses and `meta:` for the vintage pointer. They are together
 * because the vintage has to be readable on the same hot path that reads the responses it
 * keys, and a second namespace would be a second round trip for one short string.
 */

export interface Env {
  CACHE: KVNamespace;
  ASSETS: R2Bucket;
  SITE_ORIGIN: string;
  ASSET_PREFIX: string;
  /** Set with `wrangler secret put`. Absent in local dev, and pass-through pages say so. */
  FAC_API_KEY?: string;
  /** Optional enrichment. Every failure is silent; see sources/opengrants.ts. */
  OPENGRANTS_API_KEY?: string;
}

/** Which upstream a cached response came from. Decides its time to live. */
export type Source = "usaspending" | "fac" | "opengrants";

/** A cached upstream response and when it was actually fetched. */
export interface CachedResponse<T = unknown> {
  body: T;
  fetchedAt: string;
}
