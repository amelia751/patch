import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { Page, Section } from "@/components/patch/page";
import { ApiFailure, EmptyState } from "@/components/patch/api-state";
import { RunStateBadge } from "@/components/patch/status";
import { Card } from "@/components/ui/card";
import { listRuns } from "@/lib/api/client";
import { formatDuration, formatTimestamp, pluralize, shortSha } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function RunsPage({
  searchParams,
}: {
  searchParams: Promise<{ change?: string; repository?: string }>;
}) {
  const { change, repository } = await searchParams;
  const result = await listRuns({ changeId: change, repository });

  return (
    <Page
      title="Runs"
      description="Remediation runs and the deterministic state each one is in. State comes from Postgres, never inferred from an agent's summary."
    >
      {result.status !== "ok" ? (
        <ApiFailure result={result} what="run" />
      ) : result.data.runs.length === 0 ? (
        <EmptyState
          title="No runs recorded"
          detail="The store answered and holds no remediation runs for this filter."
        />
      ) : (
        <Section title={pluralize(result.data.runs.length, "run")}>
          <Card className="overflow-hidden p-0">
            <div className="divide-y divide-border">
              {result.data.runs.map((run) => (
                <Link
                  key={run.run_id}
                  href={`/runs/${run.run_id}`}
                  className="flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-4 transition-colors hover:bg-muted/40"
                >
                  <div className="min-w-56 flex-1">
                    <div className="font-mono text-sm font-medium">{run.repository}</div>
                    <div className="mt-0.5 font-mono text-xs text-muted-foreground">
                      {run.change_id}
                    </div>
                  </div>

                  <RunStateBadge state={run.state} />

                  <div className="text-xs text-muted-foreground tnum">
                    base <code className="font-mono">{shortSha(run.base_sha)}</code>
                  </div>

                  <div className="text-xs text-muted-foreground tnum">
                    attempt {run.attempts_used}/{run.attempt_budget}
                  </div>

                  <div className="text-xs text-muted-foreground tnum">
                    {formatDuration(run.started_at, run.ended_at)}
                  </div>

                  <div className="hidden text-xs text-muted-foreground tnum lg:block">
                    {formatTimestamp(run.started_at)}
                  </div>

                  <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                </Link>
              ))}
            </div>
          </Card>
        </Section>
      )}
    </Page>
  );
}
