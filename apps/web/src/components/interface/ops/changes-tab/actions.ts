/**
 * What a human can do from a change row.
 *
 * There is no "Approve fix" at this stage: no patch exists yet, and PatchAPI
 * never merges. The primary commitment is to start a remediation run that
 * stops at an evidence-backed pull request.
 */

import type { DetectionStatus, ProjectChange } from "./data";

export type ChangeActionId = "start" | "review" | "prepare" | "dismiss" | "reopen";

export type RunProgress = "idle" | "running" | "pr_opened";

export interface ChangeAction {
  id: ChangeActionId;
  label: string;
  tone: "primary" | "outline" | "ghost";
  /** Shown on the collapsed row so the inbox is not read-only. */
  onRow?: boolean;
}

export function actionsFor(
  change: ProjectChange,
  progress: RunProgress,
  status: DetectionStatus,
): ChangeAction[] {
  if (progress === "running") {
    return [{ id: "start", label: "Run started", tone: "outline", onRow: true }];
  }
  if (progress === "pr_opened") {
    return [{ id: "start", label: "View pull request", tone: "outline", onRow: true }];
  }

  switch (status) {
    case "affected":
      return [
        { id: "start", label: "Start remediation", tone: "primary", onRow: true },
        { id: "dismiss", label: "Dismiss", tone: "ghost" },
      ];
    case "human_required":
      return [
        { id: "review", label: "Review and continue", tone: "primary", onRow: true },
        { id: "dismiss", label: "Dismiss", tone: "ghost" },
      ];
    case "docs_only":
      return [
        { id: "dismiss", label: "Keep as report-only", tone: "outline", onRow: true },
        { id: "start", label: "Start anyway", tone: "ghost" },
      ];
    case "scheduled":
      return [{ id: "prepare", label: "Prepare early", tone: "outline", onRow: true }];
    case "ignored":
      return [{ id: "reopen", label: "Reopen", tone: "outline" }];
    case "watching":
      return [];
  }
}

export function actionDialog(change: ProjectChange, action: ChangeActionId): {
  title: string;
  body: string;
  confirm: string;
  destructive?: boolean;
} {
  const repo = change.repo ?? "this project's imported repositories";
  const replacement = change.replacement
    ? ` Replacement named in the note: ${change.replacement}.`
    : " No replacement is named, so the run must fail closed rather than guess.";

  switch (action) {
    case "start":
      return {
        title: `Start remediation for ${change.title}?`,
        body:
          (change.migration === "semantic"
            ? "This is a semantic migration, not a model-id rewrite. "
            : change.status === "docs_only"
              ? "These hits are documentation only. Starting a run is unusual. "
              : "") +
          `PatchAPI will analyze ${repo}, generate a patch in isolation, verify it, and open a pull request. It will not merge.`,
        confirm: change.status === "docs_only" ? "Start anyway" : "Start remediation",
      };
    case "review":
      return {
        title: `Continue ${change.title}?`,
        body:
          "Policy will not auto-patch this change. A human has to confirm the replacement and any option mapping." +
          replacement +
          ` The run still stops at a pull request against ${repo}.`,
        confirm: "Continue",
      };
    case "prepare":
      return {
        title: `Prepare ${change.title} early?`,
        body: `The note is not in effect yet. An early run still only opens a pull request against ${repo}. It does not merge or deploy.`,
        confirm: "Prepare early",
      };
    case "dismiss":
      return {
        title: `Dismiss ${change.title}?`,
        body: "This project will stop treating the note as something to remediate. You can reopen it from Ignored. Historical inventory is untouched.",
        confirm: "Dismiss",
        destructive: true,
      };
    case "reopen":
      return {
        title: `Reopen ${change.title}?`,
        body: "The note returns to the inbox so you can start a remediation run later.",
        confirm: "Reopen",
      };
  }
}
