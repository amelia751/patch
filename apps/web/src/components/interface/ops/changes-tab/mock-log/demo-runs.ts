/**
 * Throwaway demo runs for the Changes → Runs tab.
 *
 * Two captured remediations, rewritten onto a repository that does not exist.
 * They never hit the control plane: not started from Releases, not polled, not
 * continued. Deleting `changes-tab/mock-log/` and the handful of `isDemoRun`
 * call sites removes this without touching live runs.
 */

import type { ProjectChange } from "../data";
import { toRun, type RunDetail } from "../live-runs";
import type { MockRun } from "../run-scripts";
import type { RunFixture } from "./timeline";
import gemini from "./fixtures/gemini-run.json";
import imagen from "./fixtures/imagen-run.json";

export const DEMO_REPO = "patchapi-demo/storygen";

const DEMO_PREFIX = "00000000-0000-4000-8000-0000000d3m";

const IMAGEN_CARD = {
  id: "imagen4-retirement-2026-08-17",
  title: "Imagen 4 retirement",
  repo: DEMO_REPO,
  identifiers: [
    "imagen-4.0-generate-001",
    "imagen-4.0-ultra-generate-001",
    "imagen-4.0-fast-generate-001",
  ],
  replacement: "gemini-3.1-flash-image",
  fileHits: 2,
  fileCount: 2,
  files: [
    { path: "app/page.tsx", hits: 1, kind: "runtime" },
    { path: "lib/gemini.ts", hits: 1, kind: "runtime" },
  ],
} as ProjectChange;

const GEMINI_CARD = {
  id: "gemini20-flash-shutdown-2026-06-01",
  title: "Gemini 2.0 Flash shutdown",
  repo: DEMO_REPO,
  identifiers: [
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-001",
  ],
  replacement: "gemini-3.5-flash",
  fileHits: 4,
  fileCount: 4,
  files: [
    { path: "generate.py", hits: 8, kind: "runtime" },
    { path: "expected-findings.yaml", hits: 3, kind: "documentation" },
    { path: "app/page.tsx", hits: 1, kind: "runtime" },
    { path: "lib/gemini.ts", hits: 1, kind: "runtime" },
  ],
} as ProjectChange;

const FIXTURES: { run: MockRun; fixture: RunFixture }[] = [
  {
    run: toRun(imagen as unknown as RunDetail, 0, IMAGEN_CARD),
    fixture: imagen as unknown as RunFixture,
  },
  {
    run: toRun(gemini as unknown as RunDetail, 1, GEMINI_CARD),
    fixture: gemini as unknown as RunFixture,
  },
];

export const DEMO_RUNS: MockRun[] = FIXTURES.map((item) => item.run);

export function isDemoRun(run: { id: string }): boolean {
  return run.id.startsWith(DEMO_PREFIX);
}

export function fixtureFor(run: { id: string }): RunFixture | null {
  return FIXTURES.find((item) => item.run.id === run.id)?.fixture ?? null;
}
