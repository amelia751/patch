/**
 * What a human can do from a release row.
 *
 * Releases have three statuses. Human-required is a run pause, not a
 * release state. Scheduled and docs-only are row facts, not statuses.
 */

import { isDocsOnly, isNotYetEffective, type DetectionStatus, type ProjectChange } from "./data";

export type ChangeActionId = "start" | "review" | "prepare" | "dismiss" | "reopen";

export type RunProgress = "idle" | "running" | "pr_opened";

export interface ChangeAction {
  id: ChangeActionId;
  label: string;
  tone: "primary" | "outline" | "ghost";
  onRow?: boolean;
}

export function actionsFor(
  change: ProjectChange,
  progress: RunProgress,
  status: DetectionStatus,
): ChangeAction[] {
  if (progress === "running") {
    return [{ id: "start", label: "Watch run", tone: "outline", onRow: true }];
  }
  if (progress === "pr_opened") {
    return [{ id: "start", label: "Open run", tone: "outline", onRow: true }];
  }

  switch (status) {
    case "needs_you":
      return [
        { id: "start", label: "Start remediation", tone: "primary", onRow: true },
        { id: "dismiss", label: "Dismiss", tone: "ghost" },
      ];
    case "watching":
      if (isNotYetEffective(change)) {
        return [
          { id: "prepare", label: "Prepare early", tone: "outline", onRow: true },
          { id: "dismiss", label: "Dismiss", tone: "ghost" },
        ];
      }
      if (isDocsOnly(change)) {
        return [
          { id: "dismiss", label: "Dismiss", tone: "ghost" },
          { id: "start", label: "Start anyway", tone: "ghost" },
        ];
      }
      return [{ id: "dismiss", label: "Dismiss", tone: "ghost" }];
    case "dismissed":
      return [{ id: "reopen", label: "Reopen", tone: "outline" }];
  }
}

export function actionDialog(change: ProjectChange, action: ChangeActionId): {
  title: string;
  body: string;
  confirm: string;
  destructive?: boolean;
} {
  const repo = change.repo ?? "this project's imported repositories";

  switch (action) {
    case "start":
      return {
        title: `Start remediation for ${change.title}?`,
        body:
          (change.migration === "semantic"
            ? "This is a semantic migration, not a model-id rewrite. "
            : isDocsOnly(change)
              ? "These hits are documentation only. Starting a run is unusual. "
              : "") +
          `PatchAPI will analyze ${repo}, generate a patch in isolation, verify it, and open a pull request. It will not merge.`,
        confirm: isDocsOnly(change) ? "Start anyway" : "Start remediation",
      };
    case "review":
      return {
        title: `Continue ${change.title}?`,
        body: `A human has to confirm the replacement. The run still stops at a pull request against ${repo}.`,
        confirm: "Continue",
      };
    case "prepare":
      return {
        title: `Prepare ${change.title} early?`,
        body: `The note is not in effect yet. This drafts impact only. It does not open a pull request.`,
        confirm: "Prepare early",
      };
    case "dismiss":
      return {
        title: `Dismiss ${change.title}?`,
        body: "This project will stop treating the note as something to remediate. You can reopen it from Dismissed.",
        confirm: "Dismiss",
        destructive: true,
      };
    case "reopen":
      return {
        title: `Reopen ${change.title}?`,
        body: "The note returns to Releases so you can start a remediation run later.",
        confirm: "Reopen",
      };
  }
}
