/**
 * Two cache layers, doing two different jobs, both keyed on the data vintage.
 *
 * **Layer one, KV, upstream responses.** This is not a performance nicety. Every page on
 * this site is computed from two free public APIs, and a crawler walking a few thousand
 * program pages against a cold cache is a load problem for somebody else's infrastructure.
 * This layer is what makes the site polite.
 *
 * **Layer two, the Cache API, rendered HTML.** A cold program page costs a lot of upstream
 * calls, so the rendered result is worth keeping.
 *
 * **Vintage keying rather than expiry.** Both layers put the vintage in the key, so a new
 * upstream refresh invalidates the whole site at once by changing one short string in KV -
 * no purge call, no deploy, and no window where half the pages are old and half are new.
 *
 * **Stale while revalidate.** A four-day-old median is better than a spinner. A stale hit
 * is served immediately and refreshed behind the response with `ctx.waitUntil`.
 */

import { SCHEMA_VERSION } from "./analysis/profile";
import type { CachedResponse, Env, Source } from "./types";

/** Seconds. USAspending and FAC restate slowly; an open opportunity does not. */
const TTL_SECONDS: Record<Source, number> = {
  usaspending: 7 * 24 * 60 * 60,
  fac: 7 * 24 * 60 * 60,
  opengrants: 24 * 60 * 60,
};

const VINTAGE_KEY = "meta:vintage";

/**
 * Used when KV holds no vintage yet - a fresh deployment, or the scheduled probe has not
 * run. Deliberately a constant rather than a timestamp: a clock-derived fallback would
 * change on every request and give every request its own cache key, which is the same as
 * having no cache at all, on the exact path where that hurts most.
 */
export const UNKNOWN_VINTAGE = "v0";

export async function readVintage(env: Env): Promise<string> {
  return (await env.CACHE.get(VINTAGE_KEY)) ?? UNKNOWN_VINTAGE;
}

export async function writeVintage(env: Env, vintage: string): Promise<void> {
  await env.CACHE.put(VINTAGE_KEY, vintage);
}

/** Hex sha256. Keys have to be stable across isolates, so this is the digest, not a hash code. */
async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * One request reduced to a stable string.
 *
 * Object key order is not guaranteed to survive a round trip through a caller, and two
 * requests that differ only in key order are the same request. Sorting makes the digest
 * depend on the request rather than on how it happened to be spelled.
 */
export function canonicalRequest(
  method: string,
  url: string,
  payload?: Record<string, unknown> | unknown[] | null,
): string {
  return `${method.toUpperCase()} ${url} ${stableStringify(payload ?? null)}`;
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${stableStringify(v)}`).join(",")}}`;
}

export async function upstreamKey(
  source: Source,
  canonical: string,
  vintage: string,
): Promise<string> {
  return `u:${SCHEMA_VERSION}:${source}:${await sha256(canonical)}:${vintage}`;
}

/**
 * A cached upstream response, or the result of fetching and caching one.
 *
 * `fetchedAt` is stored with the body rather than inferred from KV metadata, because every
 * rendered page states when its numbers were retrieved and that claim has to survive the
 * round trip.
 */
export async function cachedFetch<T>(
  env: Env,
  source: Source,
  canonical: string,
  vintage: string,
  fetcher: () => Promise<T>,
): Promise<CachedResponse<T>> {
  const key = await upstreamKey(source, canonical, vintage);
  const hit = await env.CACHE.get<CachedResponse<T>>(key, "json");
  if (hit) return hit;

  const body = await fetcher();
  const entry: CachedResponse<T> = { body, fetchedAt: new Date().toISOString() };
  await env.CACHE.put(key, JSON.stringify(entry), { expirationTtl: TTL_SECONDS[source] });
  return entry;
}

/**
 * The Cache API key for a rendered page.
 *
 * The schema version is in here beside the vintage on purpose. The vintage moves when the
 * *data* changes; the schema version moves when the *arithmetic* changes. Without the
 * second, editing a calculation would leave every already-cached page serving the old
 * number under the new code, which is the worst failure this site can have because nothing
 * about the page looks wrong.
 */
export function pageKey(origin: string, path: string, search: string, vintage: string): string {
  const query = search && search !== "?" ? `${search}&` : "?";
  return `${origin}${path}${query}v=${SCHEMA_VERSION}-${vintage}`;
}

export interface RenderedPage {
  html: string;
  status?: number;
  /** Seconds a shared cache may serve this without revalidating. */
  maxAge?: number;
}

/**
 * Render through the Cache API: a hit returns at once, a miss renders and stores.
 *
 * `stale-while-revalidate` is generous because the alternative to a slightly old median is
 * a reader waiting twenty seconds on a cold program page while two public APIs are called
 * in sequence.
 */
export async function withPageCache(
  request: Request,
  // Structural rather than `ExecutionContext`: the only capability needed is waitUntil, and
  // Hono's context and the Workers runtime type it differently enough to fight over.
  ctx: { waitUntil(promise: Promise<unknown>): void },
  env: Env,
  render: () => Promise<RenderedPage>,
): Promise<Response> {
  const url = new URL(request.url);
  const vintage = await readVintage(env);
  const key = new Request(pageKey(env.SITE_ORIGIN, url.pathname, url.search, vintage), {
    method: "GET",
  });
  const cache = caches.default;

  const hit = await cache.match(key);
  if (hit) return hit;

  const page = await render();
  const response = new Response(page.html, {
    status: page.status ?? 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": `public, max-age=${page.maxAge ?? 3600}, stale-while-revalidate=86400`,
      "x-precedent-vintage": vintage,
    },
  });
  // Only success is worth keeping. A 404 cached under a vintage key would outlive the
  // reason it was a 404 - a program that appears in the next upstream refresh, say.
  if ((page.status ?? 200) === 200) {
    ctx.waitUntil(cache.put(key, response.clone()));
  }
  return response;
}
