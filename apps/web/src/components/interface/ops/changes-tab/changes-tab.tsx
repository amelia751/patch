"use client";

import { useMemo, useState } from "react";
import Image from "next/image";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { getGCPServiceIcon } from "@/lib/gcp-icons";
import {
  CHANGE_KIND_LABELS,
  type ChangeKind,
} from "@/components/interface/provider/data";
import {
  Bell,
  ChevronDown,
  ChevronRight,
  Clock,
  ExternalLink,
  FileCode2,
  Filter,
  GitPullRequest,
  Search,
  X,
} from "lucide-react";
import {
  actionDialog,
  actionsFor,
  type ChangeAction,
  type ChangeActionId,
  type RunProgress,
} from "./actions";
import {
  HARDCODED_PROJECT_CHANGES,
  type DetectionSeverity,
  type DetectionStatus,
  type FileHitKind,
  type ProjectChange,
} from "./data";
import { NoDetectionsEmptyState, NoProjectEmptyState } from "./empty-states";

const statusConfig: Record<
  DetectionStatus,
  { label: string; color: string; bgColor: string; dot: string }
> = {
  affected: {
    label: "Affected",
    color: "text-red-500",
    bgColor: "bg-red-500/10 border-red-500/30",
    dot: "bg-red-500",
  },
  human_required: {
    label: "Human required",
    color: "text-amber-500",
    bgColor: "bg-amber-500/10 border-amber-500/30",
    dot: "bg-amber-500",
  },
  scheduled: {
    label: "Scheduled",
    color: "text-sky-400",
    bgColor: "bg-sky-400/10 border-sky-400/30",
    dot: "bg-sky-400",
  },
  docs_only: {
    label: "Docs only",
    color: "text-violet-400",
    bgColor: "bg-violet-400/10 border-violet-400/30",
    dot: "bg-violet-400",
  },
  watching: {
    label: "Watching",
    color: "text-[var(--text-secondary)]",
    bgColor: "bg-[var(--bg-tertiary)] border-[var(--border-color)]",
    dot: "bg-[var(--text-secondary)]",
  },
  ignored: {
    label: "Ignored",
    color: "text-[var(--text-secondary)]",
    bgColor: "bg-[var(--bg-tertiary)] border-[var(--border-color)]",
    dot: "bg-[var(--bg-tertiary)]",
  },
};

const severityConfig: Record<DetectionSeverity, { label: string; className: string }> = {
  critical: {
    label: "Critical",
    className: "bg-red-500/10 text-red-500 border-red-500/30",
  },
  high: {
    label: "High",
    className: "bg-amber-500/10 text-amber-500 border-amber-500/30",
  },
  medium: {
    label: "Medium",
    className: "bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border-[var(--border-color)]",
  },
  low: {
    label: "Low",
    className: "bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border-[var(--border-color)]",
  },
};

const kindTone: Record<ChangeKind, string> = {
  deprecation: "text-red-400 border-red-400/30",
  replacement: "text-amber-400 border-amber-400/30",
  new_identifier: "text-emerald-500 border-emerald-500/30",
  breaking_change: "text-red-400 border-red-400/30",
  feature: "text-emerald-500 border-emerald-500/30",
  fix: "text-sky-400 border-sky-400/30",
  issue: "text-amber-400 border-amber-400/30",
  security: "text-red-400 border-red-400/30",
  announcement: "text-[var(--text-secondary)] border-[var(--border-color)]",
  change: "text-[var(--text-secondary)] border-[var(--border-color)]",
  libraries: "text-sky-400 border-sky-400/30",
  other: "text-[var(--text-secondary)] border-[var(--border-color)]",
};

const fileKindLabel: Record<FileHitKind, string> = {
  runtime: "runtime",
  documentation: "docs",
  changelog: "changelog",
};

const KIND_OPTIONS = Object.keys(CHANGE_KIND_LABELS) as ChangeKind[];
const STATUS_OPTIONS = Object.keys(statusConfig) as DetectionStatus[];
const SEVERITY_OPTIONS = Object.keys(severityConfig) as DetectionSeverity[];

function formatDay(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function isPastDay(iso: string): boolean {
  return new Date(`${iso}T00:00:00Z`) <= new Date();
}

function sourceLabel(url: string): string {
  if (url.includes("/deprecations")) return "Deprecations";
  if (url.includes("/changelog")) return "Changelog";
  if (url.includes("/imagen")) return "Imagen models";
  if (url.includes("/models")) return "Models";
  if (url.includes("vertex-ai")) return "Vertex AI docs";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function timingLabel(change: ProjectChange): string | null {
  if (!change.effectiveAt) return null;
  const day = formatDay(change.effectiveAt);
  if (change.status === "scheduled" || !isPastDay(change.effectiveAt)) {
    return `Takes effect ${day}`;
  }
  if (change.kind === "deprecation" || change.kind === "breaking_change") {
    return `Shutdown ${day}`;
  }
  return `Effective ${day}`;
}

function usageLabel(change: ProjectChange): string {
  if (change.status === "docs_only") {
    return `${change.fileHits} docs refs · no runtime`;
  }
  if (change.status === "ignored") {
    return "Not a finding";
  }
  if (change.status === "scheduled") {
    return "Not yet in effect";
  }
  if (change.fileHits > 0) {
    return `${change.fileHits} refs in ${change.fileCount} files`;
  }
  return "No usages in this project";
}

export function ChangesTab({
  hasProject = true,
  onBrowseSubscriptions,
}: {
  hasProject?: boolean;
  projectId?: string;
  onBrowseSubscriptions?: () => void;
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<DetectionStatus | "all">("all");
  const [severityFilter, setSeverityFilter] = useState<DetectionSeverity | "all">("all");
  const [kindFilter, setKindFilter] = useState<ChangeKind | "all">("all");
  const [bannerOpen, setBannerOpen] = useState(true);
  const [statusOverride, setStatusOverride] = useState<Record<string, DetectionStatus>>({});
  const [progress, setProgress] = useState<Record<string, RunProgress>>({});
  const [pending, setPending] = useState<{
    change: ProjectChange;
    action: ChangeActionId;
  } | null>(null);
  const [expandedProviders, setExpandedProviders] = useState<Set<string>>(
    () => new Set(HARDCODED_PROJECT_CHANGES.map((change) => change.provider)),
  );
  const [expandedChanges, setExpandedChanges] = useState<Set<string>>(
    () =>
      new Set(
        HARDCODED_PROJECT_CHANGES.filter((change) => change.status === "affected" && change.source === "fixture").map(
          (c) => c.id,
        ),
      ),
  );

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return HARDCODED_PROJECT_CHANGES.filter((change) => {
      const status = statusOverride[change.id] ?? change.status;
      if (statusFilter !== "all" && status !== statusFilter) return false;
      if (severityFilter !== "all" && change.severity !== severityFilter) return false;
      if (kindFilter !== "all" && change.kind !== kindFilter) return false;
      if (!q) return true;
      const haystack = [
        change.title,
        change.summary,
        change.product,
        change.provider,
        change.kind,
        status,
        change.replacement ?? "",
        ...change.identifiers,
        ...change.files.map((file) => file.path),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [kindFilter, searchQuery, severityFilter, statusFilter, statusOverride]);

  const byProvider = useMemo(() => {
    const groups = new Map<string, ProjectChange[]>();
    for (const change of filtered) {
      const list = groups.get(change.provider) ?? [];
      list.push(change);
      groups.set(change.provider, list);
    }
    return groups;
  }, [filtered]);

  const counts = useMemo(() => {
    const tally = (status: DetectionStatus) =>
      HARDCODED_PROJECT_CHANGES.filter((c) => c.status === status).length;
    return {
      affected: tally("affected"),
      humanRequired: tally("human_required"),
      docsOnly: tally("docs_only"),
      scheduled: tally("scheduled"),
      watching: tally("watching"),
      ignored: tally("ignored"),
    };
  }, []);

  const filtersActive = Boolean(searchQuery) || statusFilter !== "all" || severityFilter !== "all" || kindFilter !== "all";

  const toggleProvider = (provider: string) => {
    setExpandedProviders((prev) => {
      const next = new Set(prev);
      if (next.has(provider)) next.delete(provider);
      else next.add(provider);
      return next;
    });
  };

  const displayStatus = (change: ProjectChange): DetectionStatus =>
    statusOverride[change.id] ?? change.status;

  const displayProgress = (change: ProjectChange): RunProgress =>
    progress[change.id] ?? "idle";

  const requestAction = (change: ProjectChange, action: ChangeActionId, run: RunProgress) => {
    if (run !== "idle") return;
    setPending({ change, action });
  };

  const applyAction = (change: ProjectChange, action: ChangeActionId) => {
    if (action === "start" || action === "review" || action === "prepare") {
      setProgress((prev) => ({ ...prev, [change.id]: "running" }));
    } else if (action === "dismiss") {
      setStatusOverride((prev) => ({ ...prev, [change.id]: "ignored" }));
    } else if (action === "reopen") {
      setStatusOverride((prev) => {
        const next = { ...prev };
        delete next[change.id];
        return next;
      });
    }
    setPending(null);
  };

  const actionClass = (tone: ChangeAction["tone"]) => {
    if (tone === "primary") {
      return "h-7 text-xs bg-primary text-primary-foreground hover:bg-primary/90";
    }
    if (tone === "ghost") {
      return "h-7 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]";
    }
    return "h-7 text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]";
  };

  const toggleChange = (id: string) => {
    setExpandedChanges((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (!hasProject) {
    return <NoProjectEmptyState />;
  }

  return (
    <div className="h-full flex flex-col bg-[var(--bg-primary)]">
      <div className="border-b border-[var(--border-color)] p-4 space-y-3">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-secondary)]" />
            <Input
              placeholder="Search kinds, models, files, statuses…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-8 pl-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
            />
          </div>
          <Select
            value={statusFilter}
            onValueChange={(value) => setStatusFilter(value as DetectionStatus | "all")}
          >
            <SelectTrigger className="h-8 w-[140px] text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <Filter className="h-3 w-3 mr-1" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
              <SelectItem value="all" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">
                All status
              </SelectItem>
              {STATUS_OPTIONS.map((status) => (
                <SelectItem
                  key={status}
                  value={status}
                  className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]"
                >
                  {statusConfig[status].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={kindFilter}
            onValueChange={(value) => setKindFilter(value as ChangeKind | "all")}
          >
            <SelectTrigger className="h-8 w-[150px] text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <SelectValue placeholder="Type" />
            </SelectTrigger>
            <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
              <SelectItem value="all" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">
                All types
              </SelectItem>
              {KIND_OPTIONS.map((kind) => (
                <SelectItem
                  key={kind}
                  value={kind}
                  className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]"
                >
                  {CHANGE_KIND_LABELS[kind]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={severityFilter}
            onValueChange={(value) => setSeverityFilter(value as DetectionSeverity | "all")}
          >
            <SelectTrigger className="h-8 w-[130px] text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <SelectValue placeholder="Severity" />
            </SelectTrigger>
            <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
              <SelectItem value="all" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">
                All severity
              </SelectItem>
              {SEVERITY_OPTIONS.map((severity) => (
                <SelectItem
                  key={severity}
                  value={severity}
                  className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]"
                >
                  {severityConfig[severity].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-5xl mx-auto space-y-3">
          {bannerOpen && (
            <div className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5">
              <Bell className="h-3.5 w-3.5 text-amber-500 mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-[var(--text-primary)]">
                  {counts.affected + counts.humanRequired} change
                  {counts.affected + counts.humanRequired === 1 ? "" : "s"} need attention
                </p>
                <p className="text-[11px] text-[var(--text-secondary)] mt-0.5 leading-relaxed">
                  {counts.affected} affected
                  {counts.humanRequired ? ` · ${counts.humanRequired} human required` : ""}
                  {counts.docsOnly ? ` · ${counts.docsOnly} docs only` : ""}
                  {counts.scheduled ? ` · ${counts.scheduled} scheduled` : ""}
                  {counts.watching ? ` · ${counts.watching} watching` : ""}
                  {counts.ignored ? ` · ${counts.ignored} ignored` : ""}
                  . Includes deprecations that already took effect.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setBannerOpen(false)}
                className="h-5 w-5 inline-flex items-center justify-center rounded-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                aria-label="Dismiss detection notice"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          )}

          {filtered.length === 0 ? (
            filtersActive ? (
              <div className="py-16 text-center">
                <p className="text-sm font-medium text-[var(--text-primary)]">No changes match that filter</p>
                <p className="text-xs text-[var(--text-secondary)] mt-1">Clear search, type, or status to see detections again.</p>
              </div>
            ) : (
              <NoDetectionsEmptyState onBrowseSubscriptions={onBrowseSubscriptions} />
            )
          ) : (
            Array.from(byProvider.entries()).map(([provider, changes]) => {
              const isExpanded = expandedProviders.has(provider);
              const groupAffected = changes.filter((c) => displayStatus(c) === "affected").length;
              const groupHuman = changes.filter((c) => displayStatus(c) === "human_required").length;
              const groupDocs = changes.filter((c) => displayStatus(c) === "docs_only").length;
              const groupScheduled = changes.filter((c) => displayStatus(c) === "scheduled").length;
              const groupWatching = changes.filter((c) => displayStatus(c) === "watching").length;
              const groupIgnored = changes.filter((c) => displayStatus(c) === "ignored").length;
              const logo =
                changes[0]?.providerSlug === "google"
                  ? "/google-cloud.svg"
                  : getGCPServiceIcon(changes[0]?.product ?? provider);

              return (
                <div
                  key={provider}
                  className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg overflow-hidden"
                >
                  <div
                    className="p-3 cursor-pointer hover:bg-[var(--bg-tertiary)] transition-colors flex items-center justify-between"
                    onClick={() => toggleProvider(provider)}
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex-shrink-0">
                        <Image
                          src={logo}
                          alt={provider}
                          width={20}
                          height={20}
                          className="h-5 w-5 object-contain"
                        />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-[var(--text-primary)]">
                            {provider}
                          </span>
                          <Badge
                            variant="outline"
                            className="text-[9px] text-[var(--text-secondary)] border-[var(--border-color)]"
                          >
                            {changes.length}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-[10px] flex-wrap">
                          {groupAffected > 0 && (
                            <span className="text-red-500">● {groupAffected} Affected</span>
                          )}
                          {groupHuman > 0 && (
                            <span className="text-amber-500">● {groupHuman} Human required</span>
                          )}
                          {groupDocs > 0 && (
                            <span className="text-violet-400">● {groupDocs} Docs only</span>
                          )}
                          {groupScheduled > 0 && (
                            <span className="text-sky-400">● {groupScheduled} Scheduled</span>
                          )}
                          {groupWatching > 0 && (
                            <span className="text-[var(--text-secondary)]">● {groupWatching} Watching</span>
                          )}
                          {groupIgnored > 0 && (
                            <span className="text-[var(--text-secondary)]">● {groupIgnored} Ignored</span>
                          )}
                        </div>
                      </div>
                    </div>
                    {isExpanded ? (
                      <ChevronDown className="h-4 w-4 text-[var(--text-secondary)]" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-[var(--text-secondary)]" />
                    )}
                  </div>

                  {isExpanded && (
                    <div className="border-t border-[var(--border-color)]">
                      {changes.map((change) => {
                        const open = expandedChanges.has(change.id);
                        const resolvedStatus = displayStatus(change);
                        const run = displayProgress(change);
                        const available = actionsFor(change, run, resolvedStatus);
                        const rowAction = available.find((item) => item.onRow);
                        const status = statusConfig[resolvedStatus];
                        const severity = severityConfig[change.severity];
                        const when = timingLabel(change);

                        return (
                          <div key={change.id} className="border-b border-[var(--border-color)] last:border-b-0">
                            <div
                              className="p-3 cursor-pointer hover:bg-[var(--bg-tertiary)] transition-colors"
                              onClick={() => toggleChange(change.id)}
                            >
                              <div className="flex items-start justify-between">
                                <div className="flex items-start gap-3 flex-1 min-w-0">
                                  <div className="relative mt-0.5 flex-shrink-0">
                                    <Image
                                      src={getGCPServiceIcon(change.product)}
                                      alt={change.product}
                                      width={20}
                                      height={20}
                                      className="h-5 w-5 object-contain"
                                    />
                                    <div
                                      className={cn(
                                        "absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border border-[var(--bg-tertiary)]",
                                        status.dot,
                                      )}
                                    />
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                      <span className="text-xs font-medium text-[var(--text-primary)]">
                                        {change.title}
                                      </span>
                                      <Badge variant="outline" className={cn("text-[9px]", status.bgColor, status.color)}>
                                        {status.label}
                                      </Badge>
                                      <Badge variant="outline" className={cn("text-[9px]", severity.className)}>
                                        {severity.label}
                                      </Badge>
                                      <Badge
                                        variant="outline"
                                        className={cn("text-[9px]", kindTone[change.kind])}
                                      >
                                        {CHANGE_KIND_LABELS[change.kind]}
                                      </Badge>
                                    </div>
                                    <div className="flex items-center gap-3 mt-1 text-[10px] text-[var(--text-secondary)] flex-wrap">
                                      {when && (
                                        <span className="flex items-center gap-1">
                                          <Clock className="h-3 w-3" />
                                          {when}
                                        </span>
                                      )}
                                      <span className="flex items-center gap-1">
                                        <FileCode2 className="h-3 w-3" />
                                        {usageLabel({ ...change, status: resolvedStatus })}
                                      </span>
                                    </div>
                                  </div>
                                </div>
                                <div className="flex items-center gap-1.5 ml-2 shrink-0">
                                  {rowAction && (
                                    <Button
                                      size="sm"
                                      variant={rowAction.tone === "primary" ? "default" : "outline"}
                                      className={actionClass(rowAction.tone)}
                                      disabled={run !== "idle" && rowAction.id === "start"}
                                      onClick={(event) => {
                                        event.stopPropagation();
                                        requestAction(change, rowAction.id, run);
                                      }}
                                    >
                                      {rowAction.id === "start" && run === "idle" && (
                                        <GitPullRequest className="h-3 w-3 mr-1" />
                                      )}
                                      {rowAction.label}
                                    </Button>
                                  )}
                                  {open ? (
                                    <ChevronDown className="h-4 w-4 text-[var(--text-secondary)]" />
                                  ) : (
                                    <ChevronRight className="h-4 w-4 text-[var(--text-secondary)]" />
                                  )}
                                </div>
                              </div>
                            </div>

                            {open && (
                              <div className="bg-[var(--bg-tertiary)] p-4 space-y-3">
                                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                                  {change.summary}
                                </p>

                                <div className="grid grid-cols-2 gap-4">
                                  <div>
                                    <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">
                                      Effective
                                    </label>
                                    <p className="text-xs text-[var(--text-primary)] mt-1">
                                      {change.effectiveAt
                                        ? `${formatDay(change.effectiveAt)}${
                                            isPastDay(change.effectiveAt) ? " · already in effect" : " · not yet"
                                          }`
                                        : "No effective date"}
                                    </p>
                                  </div>
                                  <div>
                                    <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">
                                      Replacement
                                    </label>
                                    <p className="text-xs text-[var(--text-primary)] font-mono mt-1">
                                      {change.replacement ?? "None — fail closed"}
                                    </p>
                                  </div>
                                  {change.repo && (
                                    <div>
                                      <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">
                                        Repository
                                      </label>
                                      <p className="text-xs text-[var(--text-primary)] mt-1">
                                        {change.repo}
                                      </p>
                                    </div>
                                  )}
                                  {change.announcedAt && (
                                    <div>
                                      <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">
                                        Announced
                                      </label>
                                      <p className="text-xs text-[var(--text-primary)] mt-1">
                                        {formatDay(change.announcedAt)}
                                      </p>
                                    </div>
                                  )}
                                  {change.migration && (
                                    <div>
                                      <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">
                                        Migration
                                      </label>
                                      <p className="text-xs text-[var(--text-primary)] mt-1 capitalize">
                                        {change.migration}
                                      </p>
                                    </div>
                                  )}
                                </div>

                                {change.identifiers.length > 0 && (
                                  <div>
                                    <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">
                                      Identifiers
                                    </label>
                                    <div className="flex flex-wrap gap-1 mt-1">
                                      {change.identifiers.map((id) => (
                                        <Badge
                                          key={id}
                                          variant="outline"
                                          className="text-[9px] font-mono text-[var(--text-primary)] border-[var(--border-color)]"
                                        >
                                          {id}
                                          {change.identifierCounts?.[id]
                                            ? ` · ${change.identifierCounts[id]}`
                                            : ""}
                                        </Badge>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {change.files.length > 0 && (
                                  <div>
                                    <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">
                                      Inventory
                                    </label>
                                    <div className="mt-1 bg-[var(--bg-secondary)] rounded p-2 space-y-1 max-h-40 overflow-y-auto">
                                      {change.files.map((file) => (
                                        <div
                                          key={file.path}
                                          className="flex items-center justify-between gap-3 text-[10px] font-mono"
                                        >
                                          <span className="text-[var(--text-primary)] truncate">
                                            {file.path}
                                          </span>
                                          <span className="text-[var(--text-secondary)] shrink-0">
                                            {file.kind ? `${fileKindLabel[file.kind]} · ` : ""}
                                            {file.hits}
                                          </span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                <div>
                                  <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">
                                    Release notes
                                  </label>
                                  {change.sourceUrls.length > 0 ? (
                                    <div className="flex flex-wrap gap-2 mt-1.5">
                                      {change.sourceUrls.map((url) => (
                                        <Button
                                          key={url}
                                          size="sm"
                                          variant="outline"
                                          className="h-7 text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]"
                                          asChild
                                        >
                                          <a href={url} target="_blank" rel="noreferrer">
                                            <ExternalLink className="h-3 w-3 mr-1" />
                                            {sourceLabel(url)}
                                          </a>
                                        </Button>
                                      ))}
                                    </div>
                                  ) : (
                                    <p className="text-xs text-[var(--text-secondary)] mt-1">
                                      No source link
                                    </p>
                                  )}
                                </div>

                                {available.length > 0 && (
                                  <div className="flex items-center gap-2 pt-1">
                                    {available.map((item) => (
                                      <Button
                                        key={item.id}
                                        size="sm"
                                        variant={item.tone === "primary" ? "default" : item.tone === "ghost" ? "ghost" : "outline"}
                                        className={cn(
                                          actionClass(item.tone),
                                          item.id === "dismiss" && item.tone === "ghost" && "ml-auto",
                                        )}
                                        disabled={run !== "idle" && (item.id === "start" || item.id === "review" || item.id === "prepare")}
                                        onClick={() => requestAction(change, item.id, run)}
                                      >
                                        {(item.id === "start" || item.id === "review") && run === "idle" && (
                                          <GitPullRequest className="h-3 w-3 mr-1" />
                                        )}
                                        {item.label}
                                      </Button>
                                    ))}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
          {pending && (
            <>
              <AlertDialogHeader>
                <AlertDialogTitle className="text-[var(--text-primary)]">
                  {actionDialog(pending.change, pending.action).title}
                </AlertDialogTitle>
                <AlertDialogDescription className="text-[var(--text-secondary)] leading-relaxed">
                  {actionDialog(pending.change, pending.action).body}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  className={
                    actionDialog(pending.change, pending.action).destructive
                      ? "bg-red-500 hover:bg-red-600 text-white focus:ring-red-500"
                      : "bg-primary hover:bg-primary/90 text-primary-foreground"
                  }
                  onClick={() => applyAction(pending.change, pending.action)}
                >
                  {actionDialog(pending.change, pending.action).confirm}
                </AlertDialogAction>
              </AlertDialogFooter>
            </>
          )}
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
