import Link from "next/link";
import {
  ArrowLeft,
  Ban,
  CheckCircle2,
  CircleDashed,
  ExternalLink,
  FileDiff,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import { Page, Section } from "@/components/patch/page";
import { ApiFailure } from "@/components/patch/api-state";
import { Field, RunStateBadge, StatusPill } from "@/components/patch/status";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { readRunDetail } from "@/lib/api/client";
import type {
  ArtifactRecord,
  PatchAttemptRecord,
  PolicyDecisionRecord,
  PullRequestRecord,
  RunDetailResponse,
  TransitionRecord,
  UsageRecord,
  VerificationRecord,
} from "@/lib/api/types";
import {
  formatBytes,
  formatDuration,
  formatTime,
  formatTimestamp,
  pluralize,
  shortSha,
} from "@/lib/format";
import {
  TONE_CLASSES,
  TONE_DOT_CLASSES,
  attemptTone,
  humanizeState,
  policyTone,
  riskTone,
  runStateTone,
  verdictTone,
} from "@/lib/run-state";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  const result = await readRunDetail(runId);

  if (result.status !== "ok") {
    return (
      <Page title="Run" description={runId}>
        <ApiFailure result={result} what="run" backHref="/runs" />
      </Page>
    );
  }

  return <RunDetail response={result.data} />;
}

function RunDetail({ response }: { response: RunDetailResponse }) {
  const { detail, terminal, allowed_next: allowedNext } = response;
  const { summary, change } = detail;

  return (
    <Page
      title={summary.repository}
      description={`${change.title} · ${change.change_id}`}
      actions={
        <Link
          href="/runs"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" />
          All runs
        </Link>
      }
    >
      <Card className="p-5">
        <div className="flex flex-wrap items-center gap-3">
          <RunStateBadge state={summary.state} />
          {terminal ? (
            <StatusPill tone="idle" label="Terminal" />
          ) : (
            <span className="text-xs text-muted-foreground">
              may next become{" "}
              {allowedNext.map((state) => humanizeState(state)).join(", ") || "nothing"}
            </span>
          )}
          {summary.failure_reason ? (
            <span className="text-sm text-state-fail">{summary.failure_reason}</span>
          ) : null}
        </div>

        <Separator className="my-5" />

        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Base SHA" value={shortSha(summary.base_sha, 12)} mono />
          <Field
            label="Attempts"
            value={`${summary.attempts_used} of ${summary.attempt_budget}`}
            mono
          />
          <Field
            label="Duration"
            value={formatDuration(summary.started_at, summary.ended_at)}
            mono
          />
          <Field label="Trace ID" value={summary.trace_id ?? "—"} mono />
        </div>
      </Card>

      <Timeline transitions={detail.transitions} />

      {detail.policy ? <Policy policy={detail.policy} /> : null}

      {detail.usages.length > 0 ? <Findings usages={detail.usages} /> : null}

      {detail.attempts.length > 0 ? <Attempts attempts={detail.attempts} /> : null}

      <Verification verification={detail.verification} />

      {detail.artifacts.length > 0 ? <Evidence artifacts={detail.artifacts} /> : null}

      <PullRequest pullRequest={detail.pull_request} />
    </Page>
  );
}


function Timeline({ transitions }: { transitions: TransitionRecord[] }) {
  return (
    <Section title="Timeline" note={`${transitions.length} recorded transitions`}>
      <Card className="p-5">
        <ol className="space-y-0">
          {transitions.map((transition, index) => {
            const tone = runStateTone(transition.to_state);
            const last = index === transitions.length - 1;
            return (
              <li key={transition.sequence} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <span
                    className={cn("mt-1.5 size-2 shrink-0 rounded-full", TONE_DOT_CLASSES[tone])}
                  />
                  {!last ? <span className="w-px flex-1 bg-border" /> : null}
                </div>
                <div className={cn("min-w-0 flex-1", last ? "pb-0" : "pb-5")}>
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="font-mono text-xs text-muted-foreground tnum">
                      {formatTime(transition.occurred_at)}
                    </span>
                    <span className="text-sm font-medium">
                      {humanizeState(transition.to_state)}
                    </span>
                    <Badge variant="secondary" className="font-mono text-[10px]">
                      {transition.actor}
                    </Badge>
                  </div>
                  {transition.reason ? (
                    <p className="mt-0.5 text-sm text-muted-foreground">{transition.reason}</p>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      </Card>
    </Section>
  );
}

function Policy({ policy }: { policy: PolicyDecisionRecord }) {
  return (
    <Section title="Policy" note={`rule set ${policy.policy_version}`}>
      <Card className="p-5">
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill tone={policyTone(policy.decision)} label={policy.decision} />
          <Badge
            variant="outline"
            className={cn("text-[11px]", TONE_CLASSES[riskTone(policy.risk)])}
          >
            risk: {policy.risk}
          </Badge>
        </div>
        <p className="mt-3 text-sm text-muted-foreground">{policy.reason}</p>

        <Separator className="my-5" />

        <div className="grid gap-5 sm:grid-cols-3">
          <Permission label="Auto patch" allowed={policy.auto_patch} />
          <Permission label="Auto PR" allowed={policy.auto_pr} />
          {/* Never true. Displayed rather than omitted so the boundary in
              constraint 3 is visible instead of assumed. */}
          <Permission label="Auto merge" allowed={policy.auto_merge} neverAllowed />
        </div>

        <Separator className="my-5" />

        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Forbidden paths
            </div>
            <ul className="mt-2 space-y-1">
              {policy.forbidden_globs.map((glob) => (
                <li key={glob} className="flex items-center gap-2 font-mono text-[13px]">
                  <Ban className="size-3 shrink-0 text-state-blocked" />
                  {glob}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Required checks
            </div>
            <ul className="mt-2 space-y-1">
              {policy.required_checks.map((check) => (
                <li key={check} className="font-mono text-[13px]">
                  {check}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Card>
    </Section>
  );
}

function Permission({
  label,
  allowed,
  neverAllowed = false,
}: {
  label: string;
  allowed: boolean;
  neverAllowed?: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      {allowed ? (
        <CheckCircle2 className="size-4 text-state-pass" />
      ) : (
        <XCircle className={cn("size-4", neverAllowed ? "text-state-blocked" : "text-state-idle")} />
      )}
      <div>
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs text-muted-foreground">
          {allowed ? "permitted" : neverAllowed ? "never permitted" : "not permitted"}
        </div>
      </div>
    </div>
  );
}

function Findings({ usages }: { usages: UsageRecord[] }) {
  const files = new Set(usages.map((usage) => usage.file_path));
  return (
    <Section
      title="Affected usage"
      note={`${pluralize(usages.length, "hit")} across ${pluralize(files.size, "file")}`}
    >
      <Card className="divide-y divide-border p-0">
        {usages.map((usage) => (
          <div
            key={`${usage.file_path}:${usage.line_start}:${usage.identifier}`}
            className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-5 py-2.5"
          >
            <code className="font-mono text-[13px] break-all">{usage.file_path}</code>
            <span className="font-mono text-xs text-muted-foreground tnum">
              L{usage.line_start}
            </span>
            <code className="font-mono text-[13px] break-all text-muted-foreground">
              {usage.identifier}
            </code>
            {usage.surface ? (
              <span className="text-xs text-muted-foreground">{usage.surface}</span>
            ) : null}
          </div>
        ))}
      </Card>
    </Section>
  );
}

function Attempts({ attempts }: { attempts: PatchAttemptRecord[] }) {
  return (
    <Section title="Patch attempts" note="every attempt starts from the same pinned base SHA">
      <div className="space-y-3">
        {attempts.map((attempt) => (
          <Card key={attempt.attempt_number} className="p-5">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm font-semibold">Attempt {attempt.attempt_number}</span>
              <StatusPill tone={attemptTone(attempt.status)} label={attempt.status} />
              <span className="text-xs text-muted-foreground tnum">
                {formatDuration(attempt.started_at, attempt.ended_at)}
              </span>
            </div>

            <div className="mt-4 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              <ExitCode label="Build" code={attempt.build_exit_code} />
              <ExitCode label="Tests" code={attempt.test_exit_code} />
              <Field
                label="Files changed"
                value={attempt.files_changed === null ? "—" : attempt.files_changed}
                mono
              />
              <Field label="Model" value={attempt.patch_model} mono />
            </div>

            {attempt.sandbox_ref ? (
              <div className="mt-4">
                <Field label="Sandbox" value={attempt.sandbox_ref} mono />
              </div>
            ) : null}

            {attempt.failure_summary ? (
              <p className="mt-4 rounded-md border border-state-fail/30 bg-state-fail/5 p-3 text-sm text-muted-foreground">
                {attempt.failure_summary}
              </p>
            ) : null}
          </Card>
        ))}
      </div>
    </Section>
  );
}

/**
 * An absent exit code means the step never ran. It is rendered as unknown, never
 * as a pass — constraint 5: an unexecuted patch has no result at all.
 */
function ExitCode({ label, code }: { label: string; code: number | null }) {
  if (code === null) {
    return (
      <div>
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </div>
        <div className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground">
          <CircleDashed className="size-3.5" />
          did not run
        </div>
      </div>
    );
  }
  const passed = code === 0;
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "mt-1 flex items-center gap-1.5 text-sm font-medium",
          passed ? "text-state-pass" : "text-state-fail",
        )}
      >
        {passed ? <CheckCircle2 className="size-3.5" /> : <XCircle className="size-3.5" />}
        exit {code}
      </div>
    </div>
  );
}

function Verification({ verification }: { verification: VerificationRecord | null }) {
  if (!verification) {
    return (
      <Section title="Independent verification">
        <Card className="p-5">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <CircleDashed className="size-4" />
            No verification recorded. Nothing has graded this run, which is not the same as it
            having passed.
          </div>
        </Card>
      </Section>
    );
  }

  const independent = verification.verifier_agent !== verification.patch_agent;

  return (
    <Section title="Independent verification" note={`attempt ${verification.attempt_number}`}>
      <Card className="p-5">
        <div className="flex flex-wrap items-center gap-3">
          <StatusPill tone={verdictTone(verification.verdict)} label={verification.verdict} />
          {/* Constraint 6, shown rather than asserted. */}
          <StatusPill
            tone={independent ? "pass" : "fail"}
            label={independent ? "Verifier independent of patch agent" : "NOT INDEPENDENT"}
          />
        </div>

        <div className="mt-4 grid gap-5 sm:grid-cols-2">
          <Field
            label="Verifier"
            value={`${verification.verifier_agent} · ${verification.verifier_model}`}
            mono
          />
          <Field
            label="Patch author"
            value={`${verification.patch_agent} · ${verification.patch_model}`}
            mono
          />
        </div>

        {verification.checks.length > 0 ? (
          <>
            <Separator className="my-5" />
            <ul className="space-y-2">
              {verification.checks.map((check) => (
                <li key={check.name} className="flex items-center gap-2 text-sm">
                  {check.passed ? (
                    <CheckCircle2 className="size-4 shrink-0 text-state-pass" />
                  ) : (
                    <XCircle className="size-4 shrink-0 text-state-fail" />
                  )}
                  <code className="font-mono text-[13px]">{check.name}</code>
                </li>
              ))}
            </ul>
          </>
        ) : null}

        {verification.evidence_summary ? (
          <p className="mt-4 text-sm text-muted-foreground">{verification.evidence_summary}</p>
        ) : null}
      </Card>
    </Section>
  );
}

function Evidence({ artifacts }: { artifacts: ArtifactRecord[] }) {
  return (
    <Section title="Evidence" note="content-addressed; bytes live in object storage">
      <Card className="divide-y divide-border p-0">
        {artifacts.map((artifact) => (
          <div
            key={`${artifact.kind}:${artifact.content_sha256}`}
            className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3"
          >
            <FileDiff className="size-4 shrink-0 text-muted-foreground" />
            <span className="min-w-40 text-sm font-medium">
              {artifact.kind.replace(/_/g, " ").toLowerCase()}
            </span>
            <code className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
              {artifact.uri}
            </code>
            <span className="text-xs text-muted-foreground tnum">
              {formatBytes(artifact.size_bytes)}
            </span>
            <code className="hidden font-mono text-xs text-muted-foreground lg:block">
              sha256:{artifact.content_sha256.slice(0, 12)}…
            </code>
          </div>
        ))}
      </Card>
    </Section>
  );
}

function PullRequest({ pullRequest }: { pullRequest: PullRequestRecord | null }) {
  if (!pullRequest) {
    return (
      <Section title="Pull request">
        <Card className="p-5">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <CircleDashed className="size-4" />
            No pull request opened for this run.
          </div>
        </Card>
      </Section>
    );
  }

  return (
    <Section title="Pull request">
      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 space-y-1">
            <a
              href={pullRequest.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-base font-semibold hover:text-primary hover:underline"
            >
              #{pullRequest.number} {pullRequest.title}
              <ExternalLink className="size-3.5 shrink-0" />
            </a>
            <div className="font-mono text-xs text-muted-foreground">
              {pullRequest.head_branch} → {pullRequest.base_branch} @{" "}
              {shortSha(pullRequest.head_sha)}
            </div>
          </div>
          <StatusPill
            tone={pullRequest.state === "OPEN" ? "running" : "idle"}
            label={pullRequest.state}
          />
        </div>

        <Separator className="my-5" />

        {/* The automation boundary, stated on the page rather than left to the
            PR body. `merged_by_patchapi` is false by database constraint. */}
        <div className="flex items-start gap-2 rounded-md border border-state-pass/30 bg-state-pass/5 p-3">
          <ShieldAlert className="mt-0.5 size-4 shrink-0 text-state-pass" />
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">PatchAPI did not merge this.</span>{" "}
            {pullRequest.merged_by_patchapi
              ? "A merge was attributed to PatchAPI, which the schema forbids — investigate."
              : "Normal CODEOWNERS, branch protection, CI and human review remain in control."}
          </p>
        </div>

        <div className="mt-4 grid gap-5 sm:grid-cols-2">
          <Field label="Opened" value={formatTimestamp(pullRequest.opened_at)} mono />
          <Field label="Last observed" value={formatTimestamp(pullRequest.observed_at)} mono />
        </div>
      </Card>
    </Section>
  );
}
