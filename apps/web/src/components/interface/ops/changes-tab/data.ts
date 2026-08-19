/**
 * Hardcoded project-change detections until subscribe backfill is live.
 *
 * Each row is a note × repository join. A project can import many repos;
 * the same provider note can appear once per repo with that repo's
 * inventory and status. A run is always one repo at one pinned SHA.
 *
 * Rows tagged `source: "fixture"` copy identifiers, dates, and URLs from
 * pinned demo files. Rows tagged `source: "ui"` are layout fixtures so the
 * tab can show every kind, status, and empty field — they are not provider
 * facts.
 */

import type { ChangeKind } from "@/components/interface/provider/data";

export type DetectionStatus = "needs_you" | "watching" | "dismissed";

export type FileHitKind = "runtime" | "documentation" | "changelog";

export interface FileHit {
  path: string;
  hits: number;
  kind?: FileHitKind;
}

export interface ProjectChange {
  id: string;
  provider: string;
  providerSlug: string;
  product: string;
  title: string;
  summary: string;
  kind: ChangeKind;
  status: DetectionStatus;
  announcedAt?: string;
  effectiveAt?: string;
  identifiers: string[];
  identifierCounts?: Record<string, number>;
  replacement?: string;
  migration?: "semantic" | "mechanical";
  repo?: string;
  baseSha?: string;
  fileHits: number;
  fileCount: number;
  files: FileHit[];
  sourceUrls: string[];
  source: "fixture" | "ui";
}

export const HARDCODED_PROJECT_CHANGES: ProjectChange[] = [
  {
    id: "imagen4-retirement-2026-08-17",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Imagen",
    title: "Imagen 4 retirement",
    summary:
      "Imagen 4 generate models stop resolving. Gemini native image generation is a different request surface, not a string rewrite.",
    kind: "deprecation",
    status: "needs_you",
    announcedAt: "2026-06-24",
    effectiveAt: "2026-08-17",
    identifiers: [
      "imagen-4.0-generate-001",
      "imagen-4.0-ultra-generate-001",
      "imagen-4.0-fast-generate-001",
    ],
    identifierCounts: {
      "imagen-4.0-generate-001": 30,
      "imagen-4.0-ultra-generate-001": 10,
      "imagen-4.0-fast-generate-001": 7,
    },
    replacement: "gemini-3.1-flash-image",
    migration: "semantic",
    repo: "amelia751/egaki",
    baseSha: "c09e1a44200ff5e951746e013035e68aeb3a14b1",
    fileHits: 47,
    fileCount: 14,
    files: [
      { path: "cli/CHANGELOG.md", hits: 7, kind: "changelog" },
      { path: "cli/src/cli/model-catalog.ts", hits: 6, kind: "runtime" },
      { path: "cli/src/cli/generate.ts", hits: 6, kind: "runtime" },
      { path: "README.md", hits: 6, kind: "documentation" },
      { path: "cli/src/cli/cli.ts", hits: 5, kind: "runtime" },
      { path: "website/src/pages/docs/models.mdx", hits: 4, kind: "documentation" },
      { path: "website/src/pages/docs/image-generation.mdx", hits: 3, kind: "documentation" },
      { path: "example-generated-media/video.mdx", hits: 3, kind: "documentation" },
      { path: "website/src/pages/docs/mdx-video/server-components.mdx", hits: 2, kind: "documentation" },
      { path: "website/src/pages/docs/authentication.mdx", hits: 1, kind: "documentation" },
      { path: "website/src/pages/docs/quickstart.mdx", hits: 1, kind: "documentation" },
      { path: "cli/src/cli/generate.test.ts", hits: 1, kind: "runtime" },
      { path: "cli/src/cli/models.ts", hits: 1, kind: "runtime" },
      { path: "example-generated-media/hero-scene.server.tsx", hits: 1, kind: "runtime" },
    ],
    sourceUrls: [
      "https://ai.google.dev/gemini-api/docs/deprecations",
      "https://ai.google.dev/gemini-api/docs/changelog",
      "https://ai.google.dev/gemini-api/docs/models/imagen",
    ],
    source: "fixture",
  },
  {
    id: "gemini20-flash-shutdown-2026-06-01",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Gemini",
    title: "Gemini 2.0 Flash shutdown",
    summary:
      "gemini-2.0-flash identifiers retire. No usages in this project, so the note is watched and not opened as a finding.",
    kind: "deprecation",
    status: "watching",
    effectiveAt: "2026-06-01",
    identifiers: [
      "gemini-2.0-flash",
      "gemini-2.0-flash-001",
      "gemini-2.0-flash-lite",
      "gemini-2.0-flash-lite-001",
    ],
    replacement: "gemini-3.5-flash",
    migration: "mechanical",
    fileHits: 0,
    fileCount: 0,
    files: [],
    sourceUrls: [
      "https://ai.google.dev/gemini-api/docs/deprecations",
      "https://ai.google.dev/gemini-api/docs/changelog",
    ],
    source: "fixture",
  },
  {
    id: "chg_flash_image_preview",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Gemini",
    title: "gemini-3.1-flash-image-preview no longer resolves",
    summary:
      "The pinned Egaki catalog still names the preview id. The provider replacement is a claim — the installed SDK must resolve it before a patch writes it.",
    kind: "replacement",
    status: "needs_you",
    effectiveAt: "2026-07-17",
    identifiers: ["gemini-3.1-flash-image-preview"],
    identifierCounts: { "gemini-3.1-flash-image-preview": 4 },
    replacement: "gemini-3.1-flash-image",
    migration: "mechanical",
    repo: "amelia751/egaki",
    fileHits: 4,
    fileCount: 2,
    files: [
      { path: "cli/src/cli/model-catalog.ts", hits: 3, kind: "runtime" },
      { path: "README.md", hits: 1, kind: "documentation" },
    ],
    sourceUrls: ["https://ai.google.dev/gemini-api/docs/changelog"],
    source: "fixture",
  },
  {
    id: "chg_flash_35_ga",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Gemini",
    title: "Gemini 3.5 Flash generally available",
    summary: "New identifier on the generateContent surface. Nothing in this project needs to move because of it.",
    kind: "new_identifier",
    status: "watching",
    effectiveAt: "2026-08-12",
    identifiers: ["gemini-3.5-flash"],
    replacement: "gemini-3.5-flash",
    fileHits: 0,
    fileCount: 0,
    files: [],
    sourceUrls: ["https://ai.google.dev/gemini-api/docs/models"],
    source: "fixture",
  },
  {
    id: "adv-docs-only-imagen",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Imagen",
    title: "Imagen 4 id in documentation only",
    summary:
      "The retired id appears in Markdown prose and a changelog entry. No source, config, or test path. Report-only — do not open a remediation run.",
    kind: "deprecation",
    status: "watching",
    effectiveAt: "2026-08-17",
    identifiers: ["imagen-4.0-generate-001"],
    identifierCounts: { "imagen-4.0-generate-001": 2 },
    replacement: "gemini-3.1-flash-image",
    repo: "example-org/media-docs",
    fileHits: 2,
    fileCount: 2,
    files: [
      { path: "docs/recipes.md", hits: 1, kind: "documentation" },
      { path: "CHANGELOG.md", hits: 1, kind: "changelog" },
    ],
    sourceUrls: ["https://ai.google.dev/gemini-api/docs/deprecations"],
    source: "fixture",
  },
  {
    id: "adv-fal-ai-not-covered",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Imagen",
    title: "fal-ai/imagen4/preview is not this retirement",
    summary:
      "A third-party fal.ai-hosted model whose id contains imagen4. Not a Google first-party endpoint. Editing it is an unnecessary change.",
    kind: "other",
    status: "dismissed",
    identifiers: ["fal-ai/imagen4/preview"],
    identifierCounts: { "fal-ai/imagen4/preview": 1 },
    fileHits: 1,
    fileCount: 1,
    files: [{ path: "cli/src/cli/model-catalog.ts", hits: 1, kind: "runtime" }],
    sourceUrls: [],
    source: "fixture",
  },
  {
    id: "adv-spanish-imagen-prose",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Imagen",
    title: "Spanish “imagen” is not an API identifier",
    summary:
      "Substring match on the Spanish word for image. Correct result is no finding and no run.",
    kind: "other",
    status: "watching",
    identifiers: [],
    repo: "example-org/localization-site",
    fileHits: 0,
    fileCount: 0,
    files: [
      { path: "content/es/galeria.md", hits: 2, kind: "documentation" },
    ],
    sourceUrls: [],
    source: "fixture",
  },
  {
    id: "ui-vertex-prefix-leftover",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Vertex AI",
    title: "Vertex-routed Imagen 4 left after a bare-id rewrite",
    summary:
      "The vertex/ prefix is a routing decision, not a different model. A migration that only rewrites bare ids leaves Vertex callers broken.",
    kind: "breaking_change",
    status: "needs_you",
    effectiveAt: "2026-08-17",
    identifiers: [
      "vertex/imagen-4.0-generate-001",
      "vertex/imagen-4.0-ultra-generate-001",
      "vertex/imagen-4.0-fast-generate-001",
    ],
    identifierCounts: {
      "vertex/imagen-4.0-generate-001": 3,
      "vertex/imagen-4.0-ultra-generate-001": 1,
      "vertex/imagen-4.0-fast-generate-001": 1,
    },
    migration: "semantic",
    repo: "amelia751/egaki",
    fileHits: 5,
    fileCount: 1,
    files: [{ path: "cli/src/cli/model-catalog.ts", hits: 5, kind: "runtime" }],
    sourceUrls: ["https://ai.google.dev/gemini-api/docs/deprecations"],
    source: "fixture",
  },
  {
    id: "ui-changelog-immutable",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Imagen",
    title: "CHANGELOG.md records what shipped — do not rewrite history",
    summary:
      "Hits in a changelog are evidence the old id existed, not a call site to patch. Add a new entry instead of editing the past.",
    kind: "change",
    status: "watching",
    identifiers: ["imagen-4.0-generate-001"],
    identifierCounts: { "imagen-4.0-generate-001": 7 },
    fileHits: 7,
    fileCount: 1,
    files: [{ path: "cli/CHANGELOG.md", hits: 7, kind: "changelog" }],
    sourceUrls: [],
    source: "fixture",
  },
  {
    id: "ui-scheduled-window",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Gemini",
    title: "Scheduled note with no inventory yet",
    summary:
      "Layout fixture: a published note whose effective day is still ahead. Banner should not treat this as already broken.",
    kind: "announcement",
    status: "watching",
    announcedAt: "2026-08-18",
    effectiveAt: "2026-09-30",
    identifiers: [],
    fileHits: 0,
    fileCount: 0,
    files: [],
    sourceUrls: ["https://ai.google.dev/gemini-api/docs/changelog"],
    source: "ui",
  },
  {
    id: "ui-feature-no-ids",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Vertex AI",
    title: "Feature note with no identifiers and no effective date",
    summary: "Layout fixture: a feature write-up that never becomes a finding. Empty identifier list, no shutdown line.",
    kind: "feature",
    status: "watching",
    identifiers: [],
    fileHits: 0,
    fileCount: 0,
    files: [],
    sourceUrls: ["https://cloud.google.com/vertex-ai/docs"],
    source: "ui",
  },
  {
    id: "ui-security-no-link",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Security",
    title: "Security bulletin with no public source URL yet",
    summary: "Layout fixture: PatchAPI has no release-note link to open. Fail closed on the link, not on the row.",
    kind: "security",
    status: "watching",
    effectiveAt: "2026-08-01",
    identifiers: [],
    fileHits: 0,
    fileCount: 0,
    files: [],
    sourceUrls: [],
    source: "ui",
  },
  {
    id: "ui-libraries-sdk-bump",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Gemini",
    title: "Libraries: @google/genai peer range widened",
    summary: "Layout fixture: a library note. Mechanical if a lockfile matches; watching when it does not.",
    kind: "libraries",
    status: "watching",
    identifiers: ["@google/genai"],
    fileHits: 0,
    fileCount: 0,
    files: [],
    sourceUrls: ["https://ai.google.dev/gemini-api/docs/changelog"],
    source: "ui",
  },
  {
    id: "ui-fix-single-file",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Gemini",
    title: "Fix",
    summary: "Layout fixture: shortest title, one file, one hit.",
    kind: "fix",
    status: "needs_you",
    effectiveAt: "2026-08-10",
    identifiers: ["generateContent"],
    identifierCounts: { generateContent: 1 },
    fileHits: 1,
    fileCount: 1,
    files: [{ path: "cli/src/cli/generate.ts", hits: 1, kind: "runtime" }],
    sourceUrls: ["https://ai.google.dev/gemini-api/docs/changelog"],
    source: "ui",
  },
  {
    id: "ui-issue-long-title",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Vertex AI",
    title:
      "Issue: predict request surface rejects seed plus numberOfImages when the caller still spreads the Imagen feature bag onto a Gemini native image model which does not expose that option set",
    summary:
      "Layout fixture: a wrapping title and a long summary so the row, badges, and expanded copy do not collide. HUMAN_REQUIRED because there is no safe silent drop.",
    kind: "issue",
    status: "needs_you",
    announcedAt: "2026-08-05",
    effectiveAt: "2026-08-17",
    identifiers: ["seed", "numberOfImages", "aspectRatio"],
    fileHits: 3,
    fileCount: 1,
    files: [{ path: "cli/src/cli/model-catalog.ts", hits: 3, kind: "runtime" }],
    sourceUrls: [
      "https://ai.google.dev/gemini-api/docs/models/imagen",
      "https://ai.google.dev/gemini-api/docs/changelog",
    ],
    source: "ui",
  },
  {
    id: "ui-other-no-fields",
    provider: "Google Cloud",
    providerSlug: "google",
    product: "Other",
    title: "Unclassified note",
    summary: "Layout fixture: kind=other, no dates, no identifiers, no replacement, no links, no files.",
    kind: "other",
    status: "watching",
    identifiers: [],
    fileHits: 0,
    fileCount: 0,
    files: [],
    sourceUrls: [],
    source: "ui",
  },
];

export function isDocsOnly(change: ProjectChange): boolean {
  return change.files.length > 0 && change.files.every((file) => file.kind !== "runtime");
}

export function isNotYetEffective(change: ProjectChange): boolean {
  if (!change.effectiveAt) return false;
  return new Date(`${change.effectiveAt}T00:00:00Z`) > new Date();
}

export const HARDCODED_AFFECTED_COUNT = HARDCODED_PROJECT_CHANGES.filter(
  (change) => change.status === "needs_you",
).length;

export const UNSCOPED_REPO = "unscoped";

export function repoOf(change: { repo?: string }): string {
  return change.repo ?? UNSCOPED_REPO;
}

export function repoTitle(repo: string): string {
  return repo === UNSCOPED_REPO ? "No repository" : repo;
}

export function runKey(change: { id: string; repo?: string }): string {
  return `${change.id}::${repoOf(change)}`;
}
