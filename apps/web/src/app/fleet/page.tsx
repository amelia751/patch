import Link from "next/link";
import { Info, ShieldBan } from "lucide-react";

import { Page, Section } from "@/components/patch/page";
import { ApiFailure, EmptyState } from "@/components/patch/api-state";
import { Stat, StatusPill } from "@/components/patch/status";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { readFleet } from "@/lib/api/client";
import type { AuditEventRecord, FleetActorRecord } from "@/lib/api/types";
import { formatTimestamp, pluralize } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function FleetPage() {
  const result = await readFleet();

  return (
    <Page
      title="Fleet & governance"
      description="What the fleet actually did, aggregated from the append-only audit trail. Refused actions are the evidence that the narrow tool surface and the policy allowlists hold."
    >
      {result.status !== "ok" ? (
        <ApiFailure result={result} what="fleet snapshot" />
      ) : (
        <>
          <ProvenanceNote />

          <Denials denials={result.data.denials} />

          <Section
            title="Observed actors"
            note={
              result.data.policy_versions.length > 0
                ? `policy rule sets in use: ${result.data.policy_versions.join(", ")}`
                : undefined
            }
          >
            {result.data.observed_actors.length === 0 ? (
              <EmptyState
                title="No actors observed"
                detail="The audit trail answered and holds no events."
              />
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                {result.data.observed_actors.map((actor) => (
                  <ActorCard key={actor.actor} actor={actor} />
                ))}
              </div>
            )}
          </Section>
        </>
      )}
    </Page>
  );
}

/**
 * The distinction this page must not blur: these are observations, not a
 * capability grant read from Agent Registry. Presenting observed actions as
 * declared permissions would overstate what the enterprise has asserted.
 */
function ProvenanceNote() {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/30 p-4">
      <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <p className="text-sm text-muted-foreground">
        This page reports <span className="font-medium text-foreground">observed behaviour</span>{" "}
        from the audit trail — which actors acted, and what was refused. It is not an Agent Registry
        capability listing. A tool an agent never called does not appear here, and absence is not
        evidence that the grant is missing.
      </p>
    </div>
  );
}

function Denials({ denials }: { denials: AuditEventRecord[] }) {
  return (
    <Section title="Refused actions" note={`${pluralize(denials.length, "denial")} recorded`}>
      {denials.length === 0 ? (
        <EmptyState
          title="No refusals recorded"
          detail="Nothing has attempted an action the policy or tool surface denied."
        />
      ) : (
        <div className="space-y-3">
          {denials.map((denial, index) => (
            <Card
              key={`${denial.actor}:${denial.action}:${denial.occurred_at}:${index}`}
              className="border-state-blocked/30 bg-state-blocked/5 p-5"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-3">
                  <ShieldBan className="mt-0.5 size-4 shrink-0 text-state-blocked" />
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <code className="font-mono text-sm font-medium">{denial.action}</code>
                      <Badge variant="secondary" className="font-mono text-[10px]">
                        {denial.actor}
                      </Badge>
                    </div>
                    {denial.target ? (
                      <code className="block font-mono text-xs break-all text-muted-foreground">
                        {denial.target}
                      </code>
                    ) : null}
                  </div>
                </div>
                <StatusPill tone="blocked" label="DENIED" />
              </div>

              {denial.reason ? (
                <p className="mt-3 text-sm text-muted-foreground">{denial.reason}</p>
              ) : null}

              <Separator className="my-4" />

              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground tnum">
                <span>{formatTimestamp(denial.occurred_at)}</span>
                {denial.repository ? (
                  <span className="font-mono">{denial.repository}</span>
                ) : null}
                {denial.trace_id ? (
                  <span className="font-mono">trace {denial.trace_id}</span>
                ) : null}
                {denial.run_id ? (
                  <Link
                    href={`/runs/${denial.run_id}`}
                    className="font-medium text-primary hover:underline"
                  >
                    View run
                  </Link>
                ) : null}
              </div>
            </Card>
          ))}
        </div>
      )}
    </Section>
  );
}

function ActorCard({ actor }: { actor: FleetActorRecord }) {
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <code className="font-mono text-sm font-semibold">{actor.actor}</code>
        {actor.models.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {actor.models.map((model) => (
              <Badge key={model} variant="outline" className="font-mono text-[10px]">
                {model}
              </Badge>
            ))}
          </div>
        ) : null}
      </div>

      <div className="mt-4 grid grid-cols-3 gap-4">
        <Stat label="Succeeded" value={actor.succeeded} />
        <Stat label="Denied" value={actor.denied} tone={actor.denied > 0 ? "fail" : undefined} />
        <Stat label="Failed" value={actor.failed} tone={actor.failed > 0 ? "fail" : undefined} />
      </div>

      <Separator className="my-4" />

      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Actions observed
      </div>
      <ul className="mt-2 space-y-1">
        {actor.actions.map((action) => (
          <li key={action} className="font-mono text-[13px] break-all">
            {action}
          </li>
        ))}
      </ul>

      <div className="mt-4 text-xs text-muted-foreground tnum">
        Last seen {formatTimestamp(actor.last_seen_at)}
      </div>
    </Card>
  );
}
