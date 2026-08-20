import type { ProviderCategory, ProviderProfile } from "@/components/interface/provider/data";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type ConnectionKind = "catalog" | "changes";

export type ProviderConnection = {
  id: string;
  kind: ConnectionKind;
  adapter: string;
  source_url: string;
  canonical_url: string;
  status: "pending" | "connected" | "error" | "disconnected";
  parsed: Record<string, string>;
  last_error: string | null;
  fetched_at: string | null;
};

export type ProviderRecord = ProviderProfile & {
  status: "draft" | "live" | "retired";
  owner: { user_id: string | null; organization_id: string | null } | null;
  connections: {
    catalog: ProviderConnection | null;
    changes: ProviderConnection | null;
  };
};

export type RegisterProviderInput = {
  name: string;
  slug: string;
  website: string;
  contact_email: string;
  contact_url?: string;
  category: ProviderCategory;
  description: string;
  hq?: string;
  since?: string;
  console_url?: string;
  docs_url?: string;
  status_url?: string;
  attested: true;
};

async function readBody(response: Response): Promise<Record<string, unknown> | null> {
  return (await response.json().catch(() => null)) as Record<string, unknown> | null;
}

function detail(body: Record<string, unknown> | null, fallback: string): string {
  if (body && typeof body.detail === "string" && body.detail) return body.detail;
  return fallback;
}

export function profileFromApi(row: Record<string, unknown>): ProviderRecord {
  const connections = (row.connections && typeof row.connections === "object"
    ? row.connections
    : {}) as Record<string, ProviderConnection | null>;
  const category = String(row.category || "cloud") as ProviderCategory;
  return {
    id: String(row.id || ""),
    name: String(row.name || ""),
    slug: String(row.slug || ""),
    website: String(row.website || ""),
    contactEmail: String(row.contact_email || ""),
    contactUrl: String(row.contact_url || "") || undefined,
    category,
    description: String(row.description || ""),
    verified: Boolean(row.verified),
    registeredAt: String(row.registered_at || new Date().toISOString()),
    watchingOrgs: typeof row.watching_orgs === "number" ? row.watching_orgs : 0,
    logoUrl: String(row.logo_url || "") || undefined,
    hq: String(row.hq || "") || undefined,
    since: String(row.since || "") || undefined,
    consoleUrl: String(row.console_url || "") || undefined,
    docsUrl: String(row.docs_url || "") || undefined,
    statusUrl: String(row.status_url || "") || undefined,
    featuredProducts: Array.isArray(row.featured_products)
      ? row.featured_products.map((item) => String(item))
      : [],
    status: (row.status as ProviderRecord["status"]) || "draft",
    owner: (row.owner as ProviderRecord["owner"]) ?? null,
    connections: {
      catalog: connections.catalog ?? null,
      changes: connections.changes ?? null,
    },
  };
}

export async function fetchProviders(): Promise<ProviderRecord[]> {
  const response = await fetch(`${API_URL}/api/providers`, { credentials: "include" });
  const body = await readBody(response);
  if (!response.ok) throw new Error(detail(body, `Providers unavailable (${response.status})`));
  const rows = Array.isArray(body?.providers) ? body.providers : [];
  return rows.map((row) => profileFromApi(row as Record<string, unknown>));
}

export async function fetchProvider(slug: string): Promise<ProviderRecord> {
  const response = await fetch(`${API_URL}/api/providers/${encodeURIComponent(slug)}`, {
    credentials: "include",
  });
  const body = await readBody(response);
  if (!response.ok) throw new Error(detail(body, `Provider unavailable (${response.status})`));
  return profileFromApi(body || {});
}

export async function registerProvider(input: RegisterProviderInput): Promise<ProviderRecord> {
  const response = await fetch(`${API_URL}/api/providers`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  const body = await readBody(response);
  if (!response.ok) throw new Error(detail(body, `Could not register (${response.status})`));
  return profileFromApi(body || {});
}

export async function connectProvider(
  slug: string,
  kind: ConnectionKind,
  url: string,
): Promise<ProviderConnection> {
  const response = await fetch(`${API_URL}/api/providers/${encodeURIComponent(slug)}/connections`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, url }),
  });
  const body = await readBody(response);
  if (!response.ok) throw new Error(detail(body, `Could not connect (${response.status})`));
  return body as unknown as ProviderConnection;
}

export async function disconnectProvider(slug: string, kind: ConnectionKind): Promise<void> {
  const response = await fetch(
    `${API_URL}/api/providers/${encodeURIComponent(slug)}/connections/${kind}`,
    { method: "DELETE", credentials: "include" },
  );
  const body = await readBody(response);
  if (!response.ok) throw new Error(detail(body, `Could not disconnect (${response.status})`));
}

export async function fetchProjectProviders(projectId: string): Promise<
  Array<ProviderRecord & { subscribed: boolean; subscribed_at: string | null }>
> {
  const response = await fetch(`${API_URL}/api/projects/${projectId}/providers`, {
    credentials: "include",
  });
  const body = await readBody(response);
  if (!response.ok) throw new Error(detail(body, `Subscriptions unavailable (${response.status})`));
  const rows = Array.isArray(body?.providers) ? body.providers : [];
  return rows.map((row) => {
    const record = profileFromApi(row as Record<string, unknown>);
    const raw = row as Record<string, unknown>;
    return {
      ...record,
      subscribed: Boolean(raw.subscribed),
      subscribed_at: typeof raw.subscribed_at === "string" ? raw.subscribed_at : null,
    };
  });
}

export async function subscribeProjectProvider(projectId: string, slug: string): Promise<void> {
  const response = await fetch(
    `${API_URL}/api/projects/${projectId}/providers/${encodeURIComponent(slug)}`,
    { method: "PUT", credentials: "include" },
  );
  const body = await readBody(response);
  if (!response.ok) throw new Error(detail(body, `Could not subscribe (${response.status})`));
}

export async function unsubscribeProjectProvider(projectId: string, slug: string): Promise<void> {
  const response = await fetch(
    `${API_URL}/api/projects/${projectId}/providers/${encodeURIComponent(slug)}`,
    { method: "DELETE", credentials: "include" },
  );
  const body = await readBody(response);
  if (!response.ok) throw new Error(detail(body, `Could not unsubscribe (${response.status})`));
}

export const providersApiUrl = API_URL;
