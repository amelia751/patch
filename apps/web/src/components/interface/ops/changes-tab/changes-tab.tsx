"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
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
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
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
  GitBranch,
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
  isDocsOnly,
  isNotYetEffective,
  affectedRepos,
  runKey,
  type DetectionStatus,
  type FileHitKind,
  type ProjectChange,
} from "./data";
import { NoDetectionsEmptyState, NoProjectEmptyState } from "./empty-states";

const statusConfig: Record<
  DetectionStatus,
  { label: string; color: string; bgColor: string; dot: string }
> = {
  needs_you: {
    label: "Needs you",
    color: "text-red-500",
    bgColor: "bg-red-500/10 border-red-500/30",
    dot: "bg-red-500",
  },
  watching: {
    label: "Watching",
    color: "text-[var(--text-secondary)]",
    bgColor: "bg-[var(--bg-tertiary)] border-[var(--border-color)]",
    dot: "bg-[var(--text-secondary)]",
  },
  dismissed: {
    label: "Dismissed",
    color: "text-[var(--text-secondary)]",
    bgColor: "bg-[var(--bg-tertiary)] border-[var(--border-color)]",
    dot: "bg-[var(--bg-tertiary)]",
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

const PROVIDER_PAGE_SIZE = 8;

function pageWindow(current: number, total: number): (number | "ellipsis")[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, index) => index + 1);
  }
  const items: (number | "ellipsis")[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) items.push("ellipsis");
  for (let page = start; page <= end; page += 1) items.push(page);
  if (end < total - 1) items.push("ellipsis");
  items.push(total);
  return items;
}

const KIND_OPTIONS = Object.keys(CHANGE_KIND_LABELS) as ChangeKind[];
const STATUS_OPTIONS = Object.keys(statusConfig) as DetectionStatus[];

const FEATURED_KINDS: ChangeKind[] = [
  "deprecation",
  "breaking_change",
  "feature",
  "security",
  "fix",
];
const MORE_KINDS = KIND_OPTIONS.filter((kind) => !FEATURED_KINDS.includes(kind));

const KIND_DOT: Record<ChangeKind, string> = {
  deprecation: "bg-red-400",
  replacement: "bg-amber-400",
  new_identifier: "bg-emerald-500",
  breaking_change: "bg-red-400",
  feature: "bg-emerald-500",
  fix: "bg-sky-400",
  issue: "bg-amber-400",
  security: "bg-red-400",
  announcement: "bg-[var(--text-secondary)]",
  change: "bg-[var(--text-secondary)]",
  libraries: "bg-sky-400",
  other: "bg-[var(--text-secondary)]",
};

function FilterChip({
  active,
  onClick,
  children,
  tone = "pill",
}: {
  active?: boolean;
  onClick: () => void;
  children: ReactNode;
  tone?: "track" | "pill";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "h-7 inline-flex items-center gap-1.5 px-2.5 rounded-md text-[11px] font-medium transition-colors",
        tone === "track" &&
          (active
            ? "bg-[var(--bg-primary)] text-[var(--text-primary)] shadow-sm"
            : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-primary)]/70"),
        tone === "pill" &&
          (active
            ? "border border-[var(--border-color)] bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
            : "border border-[var(--border-color)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"),
      )}
    >
      {children}
    </button>
  );
}

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
  if (isNotYetEffective(change) || !isPastDay(change.effectiveAt)) {
    return `Takes effect ${day}`;
  }
  if (change.kind === "deprecation" || change.kind === "breaking_change") {
    return `Shutdown ${day}`;
  }
  return `Effective ${day}`;
}

function usageLabel(change: ProjectChange): string {
  if (isDocsOnly(change)) {
    return `${change.fileHits} docs refs · no runtime`;
  }
  if (isNotYetEffective(change)) {
    return "Not yet in effect";
  }
  if (change.status === "dismissed") {
    return "Dismissed";
  }
  if (change.fileHits > 0) {
    return `${change.fileHits} refs in ${change.fileCount} files`;
  }
  return "No usages in this project";
}

function noteTitle(change: ProjectChange): string {
  const kind = CHANGE_KIND_LABELS[change.kind];
  const stripped = change.title.replace(new RegExp(`^${kind}:\\s*`, "i"), "").trim();
  return stripped || change.title;
}

function RepoLabel({ repo }: { repo: string }) {
  const slash = repo.lastIndexOf("/");
  const owner = slash > 0 ? repo.slice(0, slash) : null;
  const name = slash > 0 ? repo.slice(slash + 1) : repo;
  return (
    <span className="min-w-0 truncate text-xs">
      {owner && <span className="text-[var(--text-secondary)]">{owner}/</span>}
      <span className="font-medium text-[var(--text-primary)]">{name}</span>
    </span>
  );
}

function ActionConfirmDialog({
  change,
  action,
  repo,
  onRepoChange,
  onConfirm,
}: {
  change: ProjectChange;
  action: ChangeActionId;
  repo: string | null;
  onRepoChange: (repo: string) => void;
  onConfirm: () => void;
}) {
  const copy = actionDialog(change, action);
  const repos = affectedRepos(change);
  const pickRepo = action !== "dismiss" && action !== "reopen" && repos.length > 1;
  const selected = repo ?? repos[0] ?? null;

  return (
    <>
      <AlertDialogHeader className="space-y-3 text-left">
        <AlertDialogTitle className="text-base text-[var(--text-primary)]">
          {copy.title}
        </AlertDialogTitle>
        <div className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] px-3 py-2.5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-[var(--border-color)] bg-[var(--bg-primary)]">
              <Image
                src={getGCPServiceIcon(change.product)}
                alt=""
                width={16}
                height={16}
                className="h-4 w-4 object-contain"
              />
            </div>
            <p className="min-w-0 flex-1 truncate text-xs text-[var(--text-secondary)]">
              {change.product}
              <span> · {usageLabel(change)}</span>
            </p>
            <Badge
              variant="outline"
              className={cn("shrink-0 text-[9px]", kindTone[change.kind])}
            >
              {CHANGE_KIND_LABELS[change.kind]}
            </Badge>
          </div>
          {noteTitle(change).toLowerCase() !== CHANGE_KIND_LABELS[change.kind].toLowerCase() && (
            <p className="mt-2 line-clamp-2 text-[13px] font-medium leading-snug text-[var(--text-primary)]">
              {noteTitle(change)}
            </p>
          )}
        </div>
        <AlertDialogDescription className="text-xs leading-relaxed text-[var(--text-secondary)]">
          {copy.body}
        </AlertDialogDescription>
      </AlertDialogHeader>

      {pickRepo && selected && (
        <div className="space-y-2">
          <p className="text-xs text-[var(--text-secondary)]">Choose a repository</p>
          <RadioGroup
            value={selected}
            onValueChange={onRepoChange}
            className="gap-0 overflow-hidden rounded-lg border border-[var(--border-color)]"
          >
            {repos.map((item) => (
              <label
                key={item}
                className={cn(
                  "flex cursor-pointer items-center gap-3 border-b border-[var(--border-color)] px-3 py-2.5 last:border-b-0",
                  item === selected
                    ? "bg-[var(--bg-tertiary)]"
                    : "hover:bg-[var(--bg-secondary)]",
                )}
              >
                <RadioGroupItem value={item} />
                <GitBranch className="h-3.5 w-3.5 shrink-0 text-[var(--text-secondary)]" />
                <RepoLabel repo={item} />
              </label>
            ))}
          </RadioGroup>
        </div>
      )}

      <AlertDialogFooter>
        <AlertDialogCancel>Cancel</AlertDialogCancel>
        <AlertDialogAction
          className={
            copy.destructive
              ? "bg-red-500 hover:bg-red-600 text-white focus:ring-red-500"
              : "bg-primary hover:bg-primary/90 text-primary-foreground"
          }
          onClick={onConfirm}
        >
          {copy.confirm}
        </AlertDialogAction>
      </AlertDialogFooter>
    </>
  );
}

export function ChangesInbox({
  hasProject = true,
  onBrowseSubscriptions,
  progress,
  onCommitted,
  onOpenRun,
}: {
  hasProject?: boolean;
  projectId?: string;
  onBrowseSubscriptions?: () => void;
  progress: Record<string, RunProgress>;
  onCommitted: (change: ProjectChange, action: ChangeActionId) => void;
  onOpenRun: (change: ProjectChange) => void;
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<DetectionStatus | "all">("all");
  const [kindFilter, setKindFilter] = useState<ChangeKind | "all">("all");
  const [providerPage, setProviderPage] = useState<Record<string, number>>({});
  const [moreOpen, setMoreOpen] = useState(false);
  const [bannerOpen, setBannerOpen] = useState(true);
  const [statusOverride, setStatusOverride] = useState<Record<string, DetectionStatus>>({});
  const [pending, setPending] = useState<{
    change: ProjectChange;
    action: ChangeActionId;
  } | null>(null);
  const [pendingRepo, setPendingRepo] = useState<string | null>(null);
  const [expandedProviders, setExpandedProviders] = useState<Set<string>>(
    () => new Set(HARDCODED_PROJECT_CHANGES.map((change) => change.provider)),
  );
  const [expandedChanges, setExpandedChanges] = useState<Set<string>>(
    () =>
      new Set(
        HARDCODED_PROJECT_CHANGES.filter((change) => change.status === "needs_you" && change.source === "fixture").map(
          (c) => c.id,
        ),
      ),
  );

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return HARDCODED_PROJECT_CHANGES.filter((change) => {
      const status = statusOverride[change.id] ?? change.status;
      if (statusFilter !== "all" && status !== statusFilter) return false;
      if (kindFilter !== "all" && change.kind !== kindFilter) return false;
      if (!q) return true;
      const haystack = [
        change.title,
        change.summary,
        change.product,
        change.provider,
        change.repo ?? "",
        ...(change.repos ?? []),
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
  }, [kindFilter, searchQuery, statusFilter, statusOverride]);

  useEffect(() => {
    setProviderPage({});
  }, [kindFilter, searchQuery, statusFilter]);

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
      needsYou: tally("needs_you"),
      watching: tally("watching"),
      dismissed: tally("dismissed"),
    };
  }, []);

  const filtersActive = Boolean(searchQuery) || statusFilter !== "all" || kindFilter !== "all";
  const moreKindActive = kindFilter !== "all" && MORE_KINDS.includes(kindFilter);
  const resetFilters = () => {
    setSearchQuery("");
    setStatusFilter("all");
    setKindFilter("all");
    setProviderPage({});
    setMoreOpen(false);
  };

  const setPageFor = (provider: string, page: number) => {
    setProviderPage((prev) => ({ ...prev, [provider]: page }));
  };

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

  const displayProgress = (change: ProjectChange): RunProgress => {
    const repos = affectedRepos(change);
    if (repos.length > 1) return "idle";
    return progress[runKey(change)] ?? "idle";
  };

  const requestAction = (change: ProjectChange, action: ChangeActionId, run: RunProgress) => {
    if (run !== "idle") {
      onOpenRun(change);
      return;
    }
    const repos = affectedRepos(change);
    setPendingRepo(repos[0] ?? change.repo ?? null);
    setPending({ change, action });
  };

  const applyAction = (change: ProjectChange, action: ChangeActionId) => {
    if (action === "dismiss") {
      setStatusOverride((prev) => ({ ...prev, [change.id]: "dismissed" }));
    } else if (action === "reopen") {
      setStatusOverride((prev) => {
        const next = { ...prev };
        delete next[change.id];
        return next;
      });
    } else {
      onCommitted({ ...change, repo: pendingRepo ?? change.repo }, action);
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
      <div className="border-b border-[var(--border-color)] px-4 pt-4 pb-3 space-y-3">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-secondary)]" />
            <Input
              placeholder="Search kinds, models, files, statuses…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-8 pl-9 pr-8 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 h-5 w-5 inline-flex items-center justify-center rounded-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                aria-label="Clear search"
              >
                <X className="h-3 w-3" />
              </button>
            )}
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
        </div>

        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
            Type
          </span>
            <div className="inline-flex flex-wrap items-center gap-1">
              <FilterChip active={kindFilter === "all"} onClick={() => setKindFilter("all")}>
                All
              </FilterChip>
              {FEATURED_KINDS.map((kind) => (
                <FilterChip
                  key={kind}
                  active={kindFilter === kind}
                  onClick={() => setKindFilter(kindFilter === kind ? "all" : kind)}
                >
                  <span className={cn("h-1.5 w-1.5 rounded-full", KIND_DOT[kind])} />
                  {kind === "breaking_change" ? "Breaking" : CHANGE_KIND_LABELS[kind]}
                </FilterChip>
              ))}
              <Popover open={moreOpen} onOpenChange={setMoreOpen}>
                <PopoverTrigger asChild>
                  <button
                    type="button"
                    className={cn(
                      "h-7 inline-flex items-center gap-1.5 px-2.5 rounded-md border text-[11px] font-medium transition-colors",
                      "bg-[var(--bg-secondary)] border-[var(--border-color)]",
                      moreKindActive
                        ? "text-[var(--text-primary)]"
                        : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]",
                    )}
                  >
                    {moreKindActive ? (
                      <>
                        <span className={cn("h-1.5 w-1.5 rounded-full", KIND_DOT[kindFilter])} />
                        {CHANGE_KIND_LABELS[kindFilter]}
                      </>
                    ) : (
                      "More"
                    )}
                    <ChevronDown className="h-3 w-3 opacity-70" />
                  </button>
                </PopoverTrigger>
                <PopoverContent
                  align="start"
                  className="z-[200] w-52 p-1.5 border-[var(--border-color)] bg-[var(--bg-primary)]"
                >
                  {MORE_KINDS.map((kind) => (
                    <button
                      key={kind}
                      type="button"
                      onClick={() => {
                        setKindFilter(kindFilter === kind ? "all" : kind);
                        setMoreOpen(false);
                      }}
                      className={cn(
                        "w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-[12px] text-left transition-colors",
                        kindFilter === kind
                          ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
                          : "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]",
                      )}
                    >
                      <span className={cn("h-1.5 w-1.5 rounded-full", KIND_DOT[kind])} />
                      {CHANGE_KIND_LABELS[kind]}
                    </button>
                  ))}
                </PopoverContent>
              </Popover>
            </div>
        </div>

        <div className="flex items-center justify-between gap-3">
          <p className="text-[11px] text-[var(--text-secondary)]">
            {`${filtered.length.toLocaleString()} ${filtered.length === 1 ? "change" : "changes"}`}
            {statusFilter !== "all" && (
              <>
                <span className="mx-1.5 text-[var(--border-color)]">·</span>
                {statusConfig[statusFilter].label.toLowerCase()}
              </>
            )}
            {kindFilter !== "all" && (
              <>
                <span className="mx-1.5 text-[var(--border-color)]">·</span>
                {CHANGE_KIND_LABELS[kindFilter].toLowerCase()}
              </>
            )}
          </p>
          {filtersActive && (
            <button
              type="button"
              onClick={resetFilters}
              className="text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Reset
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-5xl mx-auto space-y-3">
          {bannerOpen && (
            <div className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5">
              <Bell className="h-3.5 w-3.5 text-amber-500 mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-[var(--text-primary)]">
                  {counts.needsYou} {counts.needsYou === 1 ? "release needs" : "releases need"} you
                </p>
                <p className="text-[11px] text-[var(--text-secondary)] mt-0.5 leading-relaxed">
                  {counts.watching} watching
                  {counts.dismissed ? ` · ${counts.dismissed} dismissed` : ""}.
                  Includes notes that already took effect.
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
              const totalPages = Math.max(1, Math.ceil(changes.length / PROVIDER_PAGE_SIZE));
              const page = Math.min(providerPage[provider] ?? 1, totalPages);
              const paged = changes.slice((page - 1) * PROVIDER_PAGE_SIZE, page * PROVIDER_PAGE_SIZE);
              const groupNeedsYou = changes.filter((c) => displayStatus(c) === "needs_you").length;
              const groupWatching = changes.filter((c) => displayStatus(c) === "watching").length;
              const groupDismissed = changes.filter((c) => displayStatus(c) === "dismissed").length;
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
                          {groupNeedsYou > 0 && (
                            <span className="text-red-500">● {groupNeedsYou} Need you</span>
                          )}
                          {groupWatching > 0 && (
                            <span className="text-[var(--text-secondary)]">● {groupWatching} Watching</span>
                          )}
                          {groupDismissed > 0 && (
                            <span className="text-[var(--text-secondary)]">● {groupDismissed} Dismissed</span>
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
                      {paged.map((change) => {
                        const open = expandedChanges.has(change.id);
                        const resolvedStatus = displayStatus(change);
                        const run = displayProgress(change);
                        const available = actionsFor(change, run, resolvedStatus);
                        const rowAction = available.find((item) => item.onRow);
                        const moreActions = available.filter((item) => !item.onRow);
                        const status = statusConfig[resolvedStatus];
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
                                  {affectedRepos(change).length > 0 && (
                                    <div>
                                      <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">
                                        Repository
                                      </label>
                                      <p className="text-xs font-mono text-[var(--text-primary)] mt-1">
                                        {affectedRepos(change).join(" · ")}
                                      </p>
                                    </div>
                                  )}
                                  <div>
                                    <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">
                                      Replacement
                                    </label>
                                    <p className="text-xs text-[var(--text-primary)] font-mono mt-1">
                                      {change.replacement ?? "None — fail closed"}
                                    </p>
                                  </div>
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

                                {moreActions.length > 0 && (
                                  <div className="flex items-center gap-2 pt-1">
                                    {moreActions.map((item) => (
                                      <Button
                                        key={item.id}
                                        size="sm"
                                        variant={item.tone === "primary" ? "default" : item.tone === "ghost" ? "ghost" : "outline"}
                                        className={cn(
                                          actionClass(item.tone),
                                          item.id === "dismiss" && item.tone === "ghost" && "ml-auto",
                                        )}
                                        onClick={() => requestAction(change, item.id, run)}
                                      >
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
                      {totalPages > 1 && (
                        <div className="border-t border-[var(--border-color)] bg-[var(--bg-primary)] px-3 py-2">
                          <Pagination>
                            <PaginationContent className="gap-0.5">
                              <PaginationItem>
                                <PaginationPrevious
                                  onClick={() => setPageFor(provider, Math.max(1, page - 1))}
                                  className={cn(
                                    "h-7 px-2 text-[11px] cursor-pointer bg-[var(--bg-primary)] border-[var(--border-color)] text-[var(--text-primary)]",
                                    "hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]",
                                    page === 1 && "pointer-events-none opacity-50",
                                  )}
                                />
                              </PaginationItem>
                              {pageWindow(page, totalPages).map((item, index) =>
                                item === "ellipsis" ? (
                                  <PaginationItem key={`ellipsis-${index}`}>
                                    <PaginationEllipsis className="h-7 w-7 text-[var(--text-secondary)]" />
                                  </PaginationItem>
                                ) : (
                                  <PaginationItem key={item}>
                                    <PaginationLink
                                      onClick={() => setPageFor(provider, item)}
                                      isActive={page === item}
                                      className={cn(
                                        "h-7 w-7 text-[11px] cursor-pointer border",
                                        page === item
                                          ? "bg-[var(--bg-tertiary)] border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
                                          : "bg-[var(--bg-primary)] border-transparent text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]",
                                      )}
                                    >
                                      {item}
                                    </PaginationLink>
                                  </PaginationItem>
                                ),
                              )}
                              <PaginationItem>
                                <PaginationNext
                                  onClick={() => setPageFor(provider, Math.min(totalPages, page + 1))}
                                  className={cn(
                                    "h-7 px-2 text-[11px] cursor-pointer bg-[var(--bg-primary)] border-[var(--border-color)] text-[var(--text-primary)]",
                                    "hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]",
                                    page === totalPages && "pointer-events-none opacity-50",
                                  )}
                                />
                              </PaginationItem>
                            </PaginationContent>
                          </Pagination>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)] sm:max-w-md">
          {pending && (
            <ActionConfirmDialog
              change={pending.change}
              action={pending.action}
              repo={pendingRepo}
              onRepoChange={setPendingRepo}
              onConfirm={() => applyAction(pending.change, pending.action)}
            />
          )}
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
