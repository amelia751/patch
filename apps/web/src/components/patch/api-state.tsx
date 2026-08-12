import Link from "next/link";
import { AlertTriangle, PlugZap, SearchX } from "lucide-react";

import type { ApiResult } from "@/lib/api/client";
import { cn } from "@/lib/utils";

/**
 * How the dashboard renders not being able to see something.
 *
 * These states exist because "the store is unreachable" and "the store is
 * empty" must never look alike. Each one names what is wrong and what would
 * fix it, so a reader is never left to infer that PatchAPI found nothing when
 * in fact PatchAPI could not look.
 */

function Notice({
  icon,
  title,
  children,
  tone = "warn",
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  tone?: "warn" | "neutral";
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-lg border p-4",
        tone === "warn"
          ? "border-state-human/35 bg-state-human/5"
          : "border-border bg-muted/30",
      )}
    >
      <div className={cn("mt-0.5", tone === "warn" ? "text-state-human" : "text-muted-foreground")}>
        {icon}
      </div>
      <div className="min-w-0 space-y-1">
        <div className="text-sm font-medium">{title}</div>
        <div className="text-sm text-muted-foreground">{children}</div>
      </div>
    </div>
  );
}

export function UnwiredNotice({ dependency, reason }: { dependency: string; reason: string }) {
  return (
    <Notice icon={<PlugZap className="size-4" />} title="This view has no data source">
      <p>
        The control plane is running but reports{" "}
        <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">{dependency}</code> as
        unconfigured: {reason}.
      </p>
      <p className="mt-2">
        It is failing closed rather than showing an empty result. Start the wired server with{" "}
        <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">DATABASE_URL</code> set —
        see <span className="font-medium">apps/web/README.md</span>.
      </p>
    </Notice>
  );
}

export function UnreachableNotice({ reason }: { reason: string }) {
  return (
    <Notice icon={<AlertTriangle className="size-4" />} title="The control plane did not answer">
      <p>{reason}</p>
      <p className="mt-2">
        This is not evidence that nothing is affected — nothing could be read at all.
      </p>
    </Notice>
  );
}

export function NotFoundNotice({ what, backHref }: { what: string; backHref?: string }) {
  return (
    <Notice icon={<SearchX className="size-4" />} title={`No such ${what}`} tone="neutral">
      <p>The control plane has no record of it.</p>
      {backHref ? (
        <p className="mt-2">
          <Link href={backHref} className="font-medium text-primary hover:underline">
            Back
          </Link>
        </p>
      ) : null}
    </Notice>
  );
}

/** Renders the failure branches of an `ApiResult`, or null when it succeeded. */
export function ApiFailure<T>({
  result,
  what,
  backHref,
}: {
  result: ApiResult<T>;
  what: string;
  backHref?: string;
}) {
  if (result.status === "ok") return null;
  if (result.status === "unwired") {
    return <UnwiredNotice dependency={result.dependency} reason={result.reason} />;
  }
  if (result.status === "unreachable") {
    return <UnreachableNotice reason={result.reason} />;
  }
  return <NotFoundNotice what={what} backHref={backHref} />;
}

/** A genuinely empty result — the store answered and had nothing. */
export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="rounded-lg border border-dashed p-10 text-center">
      <div className="text-sm font-medium">{title}</div>
      {detail ? <div className="mt-1 text-sm text-muted-foreground">{detail}</div> : null}
    </div>
  );
}
