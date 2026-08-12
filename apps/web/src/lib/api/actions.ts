"use server";

import { apiBaseUrl } from "./client";

/**
 * The manual "check this provider now" trigger (roadmap §10.5).
 *
 * A server action rather than a browser fetch, so the control plane's address
 * stays server-side and the dashboard needs no public API route.
 *
 * The result is reported exactly as the control plane gave it. When the event
 * transport is not configured the API answers 503, and that is surfaced as a
 * failure — a trigger that reported success for work nobody enqueued would be
 * worse than no button at all.
 */

export interface ProviderCheckOutcome {
  ok: boolean;
  message: string;
  runId?: string | null;
  created?: boolean;
}

export async function requestProviderCheck(
  providerId: string,
  requestedBy: string,
): Promise<ProviderCheckOutcome> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/v1/provider-checks`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({ provider_id: providerId, requested_by: requestedBy }),
      cache: "no-store",
    });
  } catch (error) {
    return {
      ok: false,
      message:
        error instanceof Error ? error.message : "the control plane did not answer",
    };
  }

  const body = await response.json().catch(() => null);

  if (response.status === 503) {
    const detail = body?.detail ?? {};
    return {
      ok: false,
      message: `Not enqueued — ${detail.dependency ?? "a dependency"} is unavailable: ${
        detail.reason ?? "not configured"
      }`,
    };
  }

  if (!response.ok) {
    return { ok: false, message: `Not enqueued — the control plane returned ${response.status}` };
  }

  return {
    ok: true,
    created: body?.created,
    runId: body?.run_id ?? null,
    message: body?.created
      ? `Check enqueued for ${providerId}`
      : `Already enqueued for ${providerId} — replay ignored`,
  };
}
