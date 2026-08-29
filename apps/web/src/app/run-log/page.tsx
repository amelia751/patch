"use client";

/**
 * A preview of the run log, on its own route.
 *
 * Throwaway: this page and `components/interface/ux-ui/run-log/` are the whole
 * feature. Deleting both removes it without touching anything on the live path.
 * It imports no run loader, no polling, no project context — the two runs it
 * draws are captured JSON on a repository that does not exist, so it cannot
 * reach, start or interfere with a real run, and it is not wired into Releases
 * or Changes. Reloading the page restarts the replay.
 */

import { RunLog } from "@/components/interface/ux-ui/run-log/run-log";
import type { RunFixture } from "@/components/interface/ux-ui/run-log/timeline";
import gemini from "@/components/interface/ux-ui/run-log/fixtures/gemini-run.json";
import imagen from "@/components/interface/ux-ui/run-log/fixtures/imagen-run.json";

export default function RunLogPreviewPage() {
  return (
    <div className="h-full overflow-y-auto bg-[var(--bg-secondary)]">
      <div className="mx-auto flex max-w-3xl flex-col gap-5 px-5 py-6">
        <header>
          <h1 className="text-base font-semibold text-[var(--text-primary)]">Run log</h1>
          <p className="mt-1 text-[12px] leading-relaxed text-[var(--text-tertiary)]">
            Two captured runs, replayed on their own timings against a fake repository.
            Nothing here reaches the control plane.
          </p>
        </header>

        <RunLog fixture={imagen as unknown as RunFixture} title="Imagen 4 retirement" />
        <RunLog fixture={gemini as unknown as RunFixture} title="Gemini 2.0 Flash shutdown" />
      </div>
    </div>
  );
}
