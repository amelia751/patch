import Link from "next/link";
import { ArrowRight, ExternalLink, ShieldQuestion } from "lucide-react";

import { Page, Section } from "@/components/patch/page";
import { ApiFailure, EmptyState } from "@/components/patch/api-state";
import { CheckNowButton } from "@/components/patch/check-now-button";
import { StatusPill } from "@/components/patch/status";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { listChanges } from "@/lib/api/client";
import type { ChangeRecord } from "@/lib/api/types";
import { daysUntil, formatDate, formatTimestamp, pluralize } from "@/lib/format";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function ChangesPage() {
  const result = await listChanges();

  return (
    <Page
      title="Changes"
      description="Provider changes PatchAPI has ingested and normalized. Provider material is untrusted input — every claim below links back to the source it came from."
      actions={<CheckNowButton providerId="google" />}
    >
      {result.status !== "ok" ? (
        <ApiFailure result={result} what="change" />
      ) : result.data.changes.length === 0 ? (
        <EmptyState
          title="No provider changes ingested"
          detail="The store answered and holds no change events yet."
        />
      ) : (
        <Section title={pluralize(result.data.changes.length, "change")}>
          <div className="space-y-4">
            {result.data.changes.map((change) => (
              <ChangeCard key={`${change.provider}:${change.change_id}`} change={change} />
            ))}
          </div>
        </Section>
      )}
    </Page>
  );
}

function ChangeCard({ change }: { change: ChangeRecord }) {
  const days = daysUntil(change.effective_at);
  const urgent = days !== null && days <= 14;

  return (
    <Card className="overflow-hidden p-0">
      <div className="flex flex-wrap items-start justify-between gap-4 p-5">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="font-mono text-[11px] uppercase">
              {change.provider}
            </Badge>
            <StatusPill
              tone={urgent ? "fail" : "human"}
              label={change.change_kind.replace(/_/g, " ").toLowerCase()}
            />
            {change.open_runs > 0 ? (
              <StatusPill tone="running" label={pluralize(change.open_runs, "run")} />
            ) : null}
          </div>
          <h3 className="text-lg font-semibold tracking-tight">{change.title}</h3>
          <p className="font-mono text-xs text-muted-foreground">{change.change_id}</p>
        </div>

        <div className="text-right">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Effective
          </div>
          <div className={cn("mt-1 text-lg font-semibold tnum", urgent && "text-state-fail")}>
            {formatDate(change.effective_at)}
          </div>
          {days !== null ? (
            <div
              className={cn(
                "text-xs tnum",
                urgent ? "text-state-fail" : "text-muted-foreground",
              )}
            >
              {days < 0
                ? `${Math.abs(days)} days ago`
                : days === 0
                  ? "today"
                  : `in ${days} days`}
            </div>
          ) : null}
        </div>
      </div>

      <Separator />

      <div className="grid gap-5 p-5 sm:grid-cols-2">
        <div className="space-y-2">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Affected identifiers
          </div>
          <ul className="space-y-1">
            {change.affected_identifiers.map((identifier) => (
              <li key={identifier} className="font-mono text-[13px] break-all">
                {identifier}
              </li>
            ))}
          </ul>
        </div>

        <div className="space-y-2">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Recommended replacement
          </div>
          {change.recommended_replacement ? (
            <div className="font-mono text-[13px] break-all text-state-pass">
              {change.recommended_replacement}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">
              None stated by the provider — a migration would need a human.
            </div>
          )}
        </div>
      </div>

      <Separator />

      <div className="space-y-3 p-5">
        <EvidenceLine change={change} />
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {change.source_urls.map((url) => (
            <a
              key={url}
              href={url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-primary hover:underline"
            >
              <ExternalLink className="size-3" />
              {url.replace(/^https?:\/\//, "")}
            </a>
          ))}
        </div>
      </div>

      <Separator />

      <div className="flex flex-wrap items-center justify-between gap-3 bg-muted/30 px-5 py-3">
        <div className="text-sm text-muted-foreground tnum">
          <span className="font-medium text-foreground">
            {pluralize(change.affected_repositories, "repository", "repositories")}
          </span>{" "}
          affected · {pluralize(change.total_runs, "run")} · detected{" "}
          {formatTimestamp(change.detected_at)}
        </div>
        <Link
          href={`/impact?change=${encodeURIComponent(change.change_id)}`}
          className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
        >
          View impact
          <ArrowRight className="size-3.5" />
        </Link>
      </div>
    </Card>
  );
}

/**
 * States whether a hashed provider snapshot backs this change.
 *
 * Roadmap §15.4 wants ingestion to be reproducible from a captured source. When
 * nothing was captured the dashboard has to say so — otherwise a change with no
 * evidence looks exactly like one with evidence.
 */
function EvidenceLine({ change }: { change: ChangeRecord }) {
  if (change.source_sha256) {
    return (
      <div className="flex items-start gap-2">
        <StatusPill tone="pass" label="Source snapshot captured" />
        <code className="mt-0.5 font-mono text-xs break-all text-muted-foreground">
          sha256:{change.source_sha256.slice(0, 24)}…
        </code>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-2">
      <ShieldQuestion className="mt-0.5 size-4 shrink-0 text-state-human" />
      <p className="text-sm text-muted-foreground">
        <span className="font-medium text-state-human">No source snapshot captured.</span> Runs that
        need provider evidence must fail closed rather than infer a migration from the summary
        above.
      </p>
    </div>
  );
}
