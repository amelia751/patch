import "server-only";

import type {
  ChangeListResponse,
  ChangeRecord,
  FleetResponse,
  ReadinessResponse,
  RepositoryImpactResponse,
  RunDetailResponse,
  RunListResponse,
} from "./types";

/**
 * The dashboard's read path into the control plane.
 *
 * Requests are made server-side so the browser never needs a route to the API,
 * and so the API's address is not a public value.
 *
 * The important design decision here is that failures are values, not
 * exceptions. A page must be able to tell these apart:
 *
 *   - `ok`          the store answered
 *   - `unwired`     the API is up but a dependency it needs is not configured
 *   - `unreachable` the API itself did not answer
 *   - `not-found`   the thing asked for does not exist
 *
 * Collapsing any of those into an empty array would render "we cannot see the
 * workflow" as "the workflow is empty", which is the one mistake an operations
 * dashboard must never make.
 */

const DEFAULT_BASE_URL = "http://127.0.0.1:8080";

export function apiBaseUrl(): string {
  return (process.env.PATCHAPI_API_URL ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
}

export type ApiResult<T> =
  | { status: "ok"; data: T }
  | { status: "unwired"; dependency: string; reason: string }
  | { status: "unreachable"; reason: string }
  | { status: "not-found" };

interface DependencyUnavailableDetail {
  error?: string;
  dependency?: string;
  reason?: string;
}

async function request<T>(path: string): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      headers: { accept: "application/json" },
      // Run state changes while a page is open; a cached read would show a
      // finished run as still building.
      cache: "no-store",
    });
  } catch (error) {
    return {
      status: "unreachable",
      reason: error instanceof Error ? error.message : "the control plane did not answer",
    };
  }

  if (response.status === 404) {
    return { status: "not-found" };
  }

  if (response.status === 503) {
    const detail = await readDetail(response);
    return {
      status: "unwired",
      dependency: detail?.dependency ?? "unknown dependency",
      reason: detail?.reason ?? "a dependency the control plane needs is not configured",
    };
  }

  if (!response.ok) {
    return { status: "unreachable", reason: `the control plane returned ${response.status}` };
  }

  return { status: "ok", data: (await response.json()) as T };
}

async function readDetail(response: Response): Promise<DependencyUnavailableDetail | null> {
  try {
    const body = (await response.json()) as { detail?: DependencyUnavailableDetail };
    return body.detail ?? null;
  } catch {
    return null;
  }
}

export function listChanges(limit = 50): Promise<ApiResult<ChangeListResponse>> {
  return request(`/v1/changes?limit=${limit}`);
}

export function readChange(changeId: string): Promise<ApiResult<ChangeRecord>> {
  return request(`/v1/changes/${encodeURIComponent(changeId)}`);
}

export function listRepositoryImpact(
  changeId?: string,
): Promise<ApiResult<RepositoryImpactResponse>> {
  const query = changeId ? `?change_id=${encodeURIComponent(changeId)}` : "";
  return request(`/v1/repositories${query}`);
}

export function listRuns(options: { changeId?: string; repository?: string } = {}) {
  const params = new URLSearchParams();
  if (options.changeId) params.set("change_id", options.changeId);
  if (options.repository) params.set("repository", options.repository);
  const query = params.toString();
  return request<RunListResponse>(`/v1/runs${query ? `?${query}` : ""}`);
}

export function readRunDetail(runId: string): Promise<ApiResult<RunDetailResponse>> {
  return request(`/v1/runs/${encodeURIComponent(runId)}/detail`);
}

export function readFleet(): Promise<ApiResult<FleetResponse>> {
  return request("/v1/fleet");
}

export function readReadiness(): Promise<ApiResult<ReadinessResponse>> {
  // `/readyz` answers 503 when a probe is unsatisfied, and that body is the
  // report itself rather than an error — so it is read directly instead of
  // through `request`, which would classify it as an unwired dependency.
  return readReadinessDirect();
}

async function readReadinessDirect(): Promise<ApiResult<ReadinessResponse>> {
  try {
    const response = await fetch(`${apiBaseUrl()}/readyz`, {
      headers: { accept: "application/json" },
      cache: "no-store",
    });
    return { status: "ok", data: (await response.json()) as ReadinessResponse };
  } catch (error) {
    return {
      status: "unreachable",
      reason: error instanceof Error ? error.message : "the control plane did not answer",
    };
  }
}
