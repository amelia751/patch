export type ProviderCategory =
  | "ai"
  | "cloud"
  | "payments"
  | "communications"
  | "data"
  | "identity";

export type ServiceStatus = "live" | "preview" | "deprecated";

export type ServiceGroup =
  | "ai"
  | "storage"
  | "compute"
  | "database"
  | "networking"
  | "security"
  | "api";

export type ChangeKind =
  | "deprecation"
  | "replacement"
  | "new_identifier"
  | "breaking_change";

export type ChangeStatus = "draft" | "published" | "superseded";

export interface ProviderProfile {
  id: string;
  name: string;
  slug: string;
  website: string;
  contactEmail: string;
  category: ProviderCategory;
  description: string;
  verified: boolean;
  registeredAt: string;
  watchingOrgs: number;
  logoUrl?: string;
  hq?: string;
  since?: string;
  consoleUrl?: string;
  docsUrl?: string;
  statusUrl?: string;
  featuredProducts?: string[];
}

export interface PublishedService {
  id: string;
  name: string;
  slug: string;
  summary: string;
  status: ServiceStatus;
  product: string;
  group: ServiceGroup;
  identifiers: string[];
  docsUrl: string;
  watchers: number;
  lastPublishedAt: string;
}

export interface PublishedChange {
  id: string;
  serviceId: string;
  title: string;
  kind: ChangeKind;
  status: ChangeStatus;
  effectiveAt: string;
  retiredIdentifiers: string[];
  recommendedReplacement: string | null;
  sourceUrl: string;
  publishedAt: string;
}

export const CATEGORY_LABELS: Record<ProviderCategory, string> = {
  ai: "AI models",
  cloud: "Cloud platform",
  payments: "Payments",
  communications: "Communications",
  data: "Data",
  identity: "Identity",
};

export const SERVICE_STATUS_LABELS: Record<ServiceStatus, string> = {
  live: "Live",
  preview: "Preview",
  deprecated: "Deprecated",
};

export const SERVICE_GROUP_LABELS: Record<ServiceGroup, string> = {
  ai: "AI & Machine Learning",
  compute: "Compute",
  database: "Databases",
  storage: "Storage",
  networking: "Networking",
  security: "Security",
  api: "APIs",
};

export function asServiceGroup(value: string): ServiceGroup {
  return value in SERVICE_GROUP_LABELS ? (value as ServiceGroup) : "api";
}

export const CHANGE_KIND_LABELS: Record<ChangeKind, string> = {
  deprecation: "Deprecation",
  replacement: "Replacement",
  new_identifier: "New identifier",
  breaking_change: "Breaking change",
};

export const GOOGLE_CLOUD_PROVIDER: ProviderProfile = {
  id: "prov_google",
  name: "Google Cloud",
  slug: "google",
  website: "https://cloud.google.com",
  contactEmail: "api-changes@google.com",
  category: "cloud",
  description:
    "First-party Google Cloud APIs — Vertex AI, Gemini, Cloud Storage, GKE, and the rest of the surface enterprises call. Change events arrive as structured manifests. PatchAPI treats every claim as untrusted input.",
  verified: true,
  registeredAt: "2025-11-04T00:00:00Z",
  watchingOrgs: 1847,
  logoUrl: "/google-cloud.svg",
  hq: "Mountain View, California",
  since: "2008",
  consoleUrl: "https://console.cloud.google.com",
  docsUrl: "https://cloud.google.com/docs",
  statusUrl: "https://status.cloud.google.com",
  featuredProducts: [
    "Vertex AI",
    "Gemini API",
    "Imagen",
    "Cloud Storage",
    "GKE",
    "Cloud Run",
    "BigQuery",
    "Cloud SQL",
  ],
};

export const GOOGLE_CLOUD_SERVICES: PublishedService[] = [
  {
    id: "svc_gemini",
    name: "Gemini API",
    slug: "gemini-api",
    summary:
      "Generate content across text, image, and multimodal models. Identifiers and thinking levels are first-class.",
    status: "live",
    product: "Gemini API",
    group: "ai",
    identifiers: [
      "gemini-3.5-flash",
      "gemini-3.1-flash-image",
      "gemini-3-pro-image",
    ],
    docsUrl: "https://ai.google.dev/gemini-api/docs",
    watchers: 1240,
    lastPublishedAt: "2026-08-12T00:00:00Z",
  },
  {
    id: "svc_imagen",
    name: "Imagen",
    slug: "imagen",
    summary:
      "Image generation. Imagen 4 identifiers retire on August 17, 2026 with no announced grace period.",
    status: "deprecated",
    product: "Imagen",
    group: "ai",
    identifiers: [
      "imagen-4.0-generate-001",
      "imagen-4.0-ultra-generate-001",
      "imagen-4.0-fast-generate-001",
    ],
    docsUrl: "https://ai.google.dev/gemini-api/docs/imagen",
    watchers: 986,
    lastPublishedAt: "2026-07-17T00:00:00Z",
  },
  {
    id: "svc_vertex",
    name: "Vertex AI Prediction",
    slug: "vertex-ai-prediction",
    summary:
      "Managed prediction endpoints for Gemini and partner models on Vertex AI.",
    status: "live",
    product: "Vertex AI",
    group: "ai",
    identifiers: [
      "publishers/google/models/gemini-3.5-flash",
      "publishers/google/models/gemini-3-pro-image",
    ],
    docsUrl: "https://cloud.google.com/vertex-ai/docs",
    watchers: 612,
    lastPublishedAt: "2026-08-01T00:00:00Z",
  },
  {
    id: "svc_storage",
    name: "Cloud Storage JSON API",
    slug: "cloud-storage-json",
    summary: "Object storage JSON surface used by generated-image pipelines.",
    status: "live",
    product: "Cloud Storage",
    group: "storage",
    identifiers: ["storage.googleapis.com/storage/v1"],
    docsUrl: "https://cloud.google.com/storage/docs/json_api",
    watchers: 431,
    lastPublishedAt: "2026-03-18T00:00:00Z",
  },
];

export const GOOGLE_CLOUD_CHANGES: PublishedChange[] = [
  {
    id: "chg_imagen4_retire",
    serviceId: "svc_imagen",
    title: "Imagen 4 identifiers retire — three-to-two replacement",
    kind: "deprecation",
    status: "published",
    effectiveAt: "2026-08-17T00:00:00Z",
    retiredIdentifiers: [
      "imagen-4.0-generate-001",
      "imagen-4.0-ultra-generate-001",
      "imagen-4.0-fast-generate-001",
    ],
    recommendedReplacement: "gemini-3.1-flash-image",
    sourceUrl: "https://ai.google.dev/gemini-api/docs/deprecations",
    publishedAt: "2026-07-17T00:00:00Z",
  },
  {
    id: "chg_flash_image_preview",
    serviceId: "svc_gemini",
    title: "gemini-3.1-flash-image-preview no longer resolves",
    kind: "deprecation",
    status: "published",
    effectiveAt: "2026-07-17T00:00:00Z",
    retiredIdentifiers: ["gemini-3.1-flash-image-preview"],
    recommendedReplacement: "gemini-3.1-flash-image",
    sourceUrl: "https://ai.google.dev/gemini-api/docs/changelog",
    publishedAt: "2026-07-17T00:00:00Z",
  },
  {
    id: "chg_flash_35_ga",
    serviceId: "svc_gemini",
    title: "Gemini 3.5 Flash generally available",
    kind: "new_identifier",
    status: "published",
    effectiveAt: "2026-08-12T00:00:00Z",
    retiredIdentifiers: [],
    recommendedReplacement: "gemini-3.5-flash",
    sourceUrl: "https://ai.google.dev/gemini-api/docs/models",
    publishedAt: "2026-08-12T00:00:00Z",
  },
];

export function slugify(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "P";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

export function formatShortDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function daysUntil(iso: string): number {
  const target = new Date(iso);
  const now = new Date();
  const start = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  const end = Date.UTC(target.getFullYear(), target.getMonth(), target.getDate());
  return Math.round((end - start) / 86_400_000);
}

export function formatWatchers(n: number): string {
  return n.toLocaleString();
}

export function catalogChangeFromApi(raw: {
  id: string;
  serviceId: string;
  title: string;
  kind: string;
  status: string;
  effectiveAt: string;
  retiredIdentifiers: string[];
  recommendedReplacement: string | null;
  sourceUrl: string;
  publishedAt: string;
}): PublishedChange | null {
  if (!raw.effectiveAt || raw.effectiveAt.length < 10) return null;
  const kind: ChangeKind =
    raw.kind === "replacement"
      ? "replacement"
      : raw.kind === "new_identifier"
        ? "new_identifier"
        : raw.kind === "breaking_change"
          ? "breaking_change"
          : "deprecation";
  const status: ChangeStatus =
    raw.status === "superseded" ? "superseded" : raw.status === "draft" ? "draft" : "published";
  return {
    id: raw.id,
    serviceId: raw.serviceId,
    title: raw.title,
    kind,
    status,
    effectiveAt: raw.effectiveAt,
    retiredIdentifiers: Array.isArray(raw.retiredIdentifiers) ? raw.retiredIdentifiers : [],
    recommendedReplacement: raw.recommendedReplacement || null,
    sourceUrl: raw.sourceUrl,
    publishedAt: raw.publishedAt || raw.effectiveAt,
  };
}

export function catalogServiceFromApi(raw: {
  id: string;
  name: string;
  slug: string;
  product: string;
  group: string;
  summary: string;
  status: string;
  identifiers: string[];
  docsUrl: string;
  watchers?: number;
  lastPublishedAt: string;
}): PublishedService {
  const status: ServiceStatus =
    raw.status === "deprecated" ? "deprecated" : raw.status === "preview" ? "preview" : "live";
  return {
    id: raw.id,
    name: raw.name,
    slug: raw.slug,
    summary: raw.summary,
    status,
    product: raw.product,
    group: asServiceGroup(raw.group),
    identifiers: raw.identifiers,
    docsUrl: raw.docsUrl,
    watchers: raw.watchers ?? 0,
    lastPublishedAt: raw.lastPublishedAt,
  };
}

export function inferServiceMeta(name: string): { product: string; group: ServiceGroup } {
  const lower = name.toLowerCase();
  if (lower.includes("imagen")) return { product: "Imagen", group: "ai" };
  if (lower.includes("gemini")) return { product: "Gemini API", group: "ai" };
  if (lower.includes("vertex")) return { product: "Vertex AI", group: "ai" };
  if (lower.includes("storage") || lower.includes("gcs")) return { product: "Cloud Storage", group: "storage" };
  return { product: name.trim() || "API", group: "api" };
}
