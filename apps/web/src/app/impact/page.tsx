import Link from "next/link";
import { AlertTriangle, FileCode2 } from "lucide-react";

import { Page, Section } from "@/components/patch/page";
import { ApiFailure, EmptyState } from "@/components/patch/api-state";
import { RunStateBadge, Stat, StatusPill } from "@/components/patch/status";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { listChanges, listRepositoryImpact } from "@/lib/api/client";
import type { RepositoryImpactRecord, UsageRecord } from "@/lib/api/types";
import { formatPercent, formatTimestamp, pluralize, shortSha } from "@/lib/format";
import { TONE_CLASSES, detectionLabel, riskTone } from "@/lib/run-state";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function ImpactPage({
  searchParams,
}: {
  searchParams: Promise<{ change?: string }>;
}) {
  const { change: changeId } = await searchParams;
  const [impact, changes] = await Promise.all([
    listRepositoryImpact(changeId),
    listChanges(),
  ]);

  const changeList = changes.status === "ok" ? changes.data.changes : [];

  return (
    <Page
      title="Organization impact"
      description="Exposure read from the API usage inventory, not from cloning every repository. Counts are evidence about the commit each repository was last indexed at."
    >
      {changeList.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Scope
          </span>
          <ScopeChip href="/impact" active={!changeId} label="All identifiers" />
          {changeList.map((change) => (
            <ScopeChip
              key={change.change_id}
              href={`/impact?change=${encodeURIComponent(change.change_id)}`}
              active={changeId === change.change_id}
              label={change.change_id}
            />
          ))}
        </div>
      ) : null}

      {impact.status !== "ok" ? (
        <ApiFailure result={impact} what="change" backHref="/impact" />
      ) : impact.data.repositories.length === 0 ? (
        <EmptyState
          title="No repositories in scope"
          detail={
            changeId
              ? `No change with id "${changeId}" is known, so nothing could be scoped to it.`
              : "The store answered and holds no in-scope repositories."
          }
        />
      ) : (
        <ImpactBody repositories={impact.data.repositories} />
      )}
    </Page>
  );
}

function ScopeChip({ href, active, label }: { href: string; active: boolean; label: string }) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded-full border px-3 py-1 font-mono text-xs transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground",
      )}
    >
      {label}
    </Link>
  );
}

function ImpactBody({ repositories }: { repositories: RepositoryImpactRecord[] }) {
  const affected = repositories.filter((repository) => repository.affected);
  const totalUsages = repositories.reduce((sum, r) => sum + r.usage_count, 0);
  const totalFiles = repositories.reduce((sum, r) => sum + r.file_count, 0);

  return (
    <>
      <Card className="p-5">
        <div className="grid gap-6 sm:grid-cols-4">
          <Stat
            label="Repositories scanned"
            value={repositories.length}
            hint="in-scope and not archived"
          />
          <Stat
            label="Affected"
            value={affected.length}
            tone={affected.length > 0 ? "fail" : "pass"}
            hint={
              affected.length === 0
                ? "inventory matched nothing"
                : "at least one inventoried usage"
            }
          />
          <Stat label="Usages" value={totalUsages} hint="individual inventory hits" />
          <Stat label="Files" value={totalFiles} hint="distinct paths" />
        </div>
      </Card>

      <Section
        title="Repositories"
        note="Unaffected repositories are listed too — “we looked and found nothing” is a different claim from “we did not look”."
      >
        <div className="space-y-4">
          {repositories.map((repository) => (
            <RepositoryCard key={repository.repository} repository={repository} />
          ))}
        </div>
      </Section>
    </>
  );
}

function RepositoryCard({ repository }: { repository: RepositoryImpactRecord }) {
  const byFile = groupByFile(repository.usages);

  return (
    <Card className="overflow-hidden p-0">
      <div className="flex flex-wrap items-start justify-between gap-4 p-5">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-mono text-base font-semibold">{repository.repository}</h3>
            {repository.affected ? (
              <StatusPill tone="fail" label="Affected" />
            ) : (
              <StatusPill tone="pass" label="Not affected" />
            )}
            <Badge
              variant="outline"
              className={cn("text-[11px]", TONE_CLASSES[riskTone(repository.criticality)])}
            >
              criticality: {repository.criticality}
            </Badge>
            {repository.owner_team ? (
              <Badge variant="secondary" className="text-[11px]">
                {repository.owner_team}
              </Badge>
            ) : null}
          </div>
          <div className="text-xs text-muted-foreground tnum">
            Indexed at{" "}
            <code className="font-mono">{shortSha(repository.indexed_sha)}</code> ·{" "}
            {formatTimestamp(repository.indexed_at)}
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="text-right">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">Usages</div>
            <div className="text-xl font-semibold tnum">{repository.usage_count}</div>
          </div>
          <div className="text-right">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">Files</div>
            <div className="text-xl font-semibold tnum">{repository.file_count}</div>
          </div>
          {repository.latest_run_id && repository.latest_run_state ? (
            <Link href={`/runs/${repository.latest_run_id}`} className="shrink-0">
              <RunStateBadge state={repository.latest_run_state} />
            </Link>
          ) : (
            <StatusPill tone="idle" label="No run" />
          )}
        </div>
      </div>

      {repository.usages.length > 0 ? (
        <>
          <Separator />
          <div className="divide-y divide-border">
            {byFile.map(([filePath, usages]) => (
              <FileGroup key={filePath} filePath={filePath} usages={usages} />
            ))}
          </div>
        </>
      ) : null}
    </Card>
  );
}

function FileGroup({ filePath, usages }: { filePath: string; usages: UsageRecord[] }) {
  return (
    <div className="px-5 py-3">
      <div className="flex items-center gap-2">
        <FileCode2 className="size-3.5 shrink-0 text-muted-foreground" />
        <code className="font-mono text-[13px] break-all">{filePath}</code>
        <span className="text-xs text-muted-foreground tnum">
          {pluralize(usages.length, "hit")}
        </span>
      </div>
      <ul className="mt-2 space-y-1.5 pl-5">
        {usages.map((usage) => (
          <li
            key={`${usage.identifier}:${usage.line_start}`}
            className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm"
          >
            <span className="font-mono text-xs text-muted-foreground tnum">
              L{usage.line_start}
              {usage.line_end && usage.line_end !== usage.line_start ? `–${usage.line_end}` : ""}
            </span>
            <code className="font-mono text-[13px] break-all">{usage.identifier}</code>
            <Badge
              variant="outline"
              className={cn(
                "text-[10px]",
                usage.detection_layer === "C_SEMANTIC" && "border-state-human/40 text-state-human",
              )}
            >
              {detectionLabel(usage.detection_layer)} · {formatPercent(usage.confidence)}
            </Badge>
            {usage.surface ? (
              <span className="text-xs text-muted-foreground">{usage.surface}</span>
            ) : null}
            {/* A model-derived finding is flagged so a reviewer knows which
                hits are literal matches and which are inferred. */}
            {usage.detection_layer === "C_SEMANTIC" ? (
              <span className="inline-flex items-center gap-1 text-xs text-state-human">
                <AlertTriangle className="size-3" />
                semantic finding
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function groupByFile(usages: UsageRecord[]): [string, UsageRecord[]][] {
  const grouped = new Map<string, UsageRecord[]>();
  for (const usage of usages) {
    const existing = grouped.get(usage.file_path);
    if (existing) existing.push(usage);
    else grouped.set(usage.file_path, [usage]);
  }
  return [...grouped.entries()];
}
