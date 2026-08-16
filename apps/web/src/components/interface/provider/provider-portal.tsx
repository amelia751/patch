"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getGCPCategoryIcon, getGCPServiceIcon } from "@/lib/gcp-icons";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ArrowUpRight,
  BadgeCheck,
  Blocks,
  Building2,
  ChevronDown,
  ChevronRight,
  Clock,
  Clock3,
  ExternalLink,
  Eye,
  FilePlus2,
  Filter,
  Globe,
  Info,
  Layers,
  Link2,
  Loader2,
  Mail,
  MapPin,
  Plus,
  Search,
  Shield,
} from "lucide-react";
import {
  CATEGORY_LABELS,
  CHANGE_KIND_LABELS,
  GOOGLE_CLOUD_PROVIDER,
  SERVICE_GROUP_LABELS,
  SERVICE_STATUS_LABELS,
  catalogChangeFromApi,
  catalogServiceFromApi,
  daysUntil,
  formatShortDate,
  formatWatchers,
  inferServiceMeta,
  initials,
  slugify,
  type ChangeKind,
  type ProviderCategory,
  type ProviderProfile,
  type PublishedChange,
  type PublishedService,
  type ServiceGroup,
  type ServiceStatus,
} from "./data";

const fieldClass =
  "h-9 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] focus-visible:border-primary focus-visible:ring-1 focus-visible:ring-primary/25";

const textareaClass =
  "min-h-[88px] text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] focus-visible:border-primary focus-visible:ring-1 focus-visible:ring-primary/25";

const selectTriggerClass = cn(
  "h-9 w-full text-sm shadow-sm transition-colors",
  "bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]",
  "hover:bg-[var(--bg-tertiary)]",
  "[&>span]:text-[var(--text-primary)] data-[placeholder]:text-[var(--text-secondary)]",
  "[&_svg]:text-[var(--text-secondary)] [&_svg]:opacity-80",
  "focus:ring-1 focus:ring-primary/25 focus:border-primary",
);

const selectContentClass =
  "z-[200] overflow-hidden rounded-md border shadow-lg border-[var(--border-color)] bg-[var(--bg-primary)] text-[var(--text-primary)]";

const selectItemClass =
  "cursor-pointer rounded-sm py-2 pl-2 pr-8 text-sm outline-none text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]";

const tabTriggerClass =
  "flex-1 inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-[11px] font-medium transition-all data-[state=active]:bg-[var(--bg-primary)] data-[state=active]:text-[var(--text-tertiary)] data-[state=active]:shadow";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Outline actions — same dark hover as the header theme toggle. */
const outlineButtonClass =
  "border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]";

const outlineMutedButtonClass =
  "border-[var(--border-color)] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]";

export function ProviderPortal() {
  const [profile, setProfile] = useState<ProviderProfile | null>(null);
  const [services, setServices] = useState<PublishedService[]>([]);
  const [changes, setChanges] = useState<PublishedChange[]>([]);
  const [tab, setTab] = useState("services");
  const [showRegister, setShowRegister] = useState(false);
  const [showHowItWorks, setShowHowItWorks] = useState(false);
  const [publishServiceOpen, setPublishServiceOpen] = useState(false);
  const [publishChangeOpen, setPublishChangeOpen] = useState(false);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const openCatalog = async () => {
    setProfile(GOOGLE_CLOUD_PROVIDER);
    setServices([]);
    setChanges([]);
    setTab("services");
    setShowRegister(false);
    setCatalogError(null);
    setCatalogLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/providers/google`, {
        credentials: "include",
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(body?.detail || `Catalog unavailable (${response.status})`);
      }
      const rows = Array.isArray(body?.services) ? body.services : [];
      setServices(rows.map((row: Parameters<typeof catalogServiceFromApi>[0]) => catalogServiceFromApi(row)));
    } catch (error) {
      setCatalogError(
        error instanceof Error ? error.message : "Could not load the Google Cloud catalog",
      );
    } finally {
      setCatalogLoading(false);
    }
  };

  const handleRegistered = (next: ProviderProfile) => {
    setProfile(next);
    setServices([]);
    setChanges([]);
    setTab("services");
    setShowRegister(false);
  };

  const leaveProvider = () => {
    setProfile(null);
    setServices([]);
    setChanges([]);
    setTab("services");
  };

  if (!profile) {
    return (
      <>
        <div className="h-full flex items-center justify-center bg-[var(--bg-secondary)]">
          <div className="text-center max-w-md px-4">
            <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
              <Blocks className="h-5 w-5 text-[var(--text-secondary)]" />
            </div>
            <div className="flex items-center justify-center gap-2 mb-2">
              <h2 className="text-lg font-medium text-[var(--text-primary)]">No provider yet</h2>
              <button
                type="button"
                onClick={() => setShowHowItWorks(true)}
                className="p-1 rounded-full hover:bg-[var(--bg-tertiary)] transition-colors"
                aria-label="How it works"
              >
                <Info className="h-4 w-4 text-[var(--text-secondary)]" strokeWidth={1} />
              </button>
            </div>
            <p className="text-sm text-[var(--text-secondary)] mb-6">
              Register this organization as a provider to publish services
            </p>
            <div className="flex flex-col gap-2">
              <Button
                onClick={() => setShowRegister(true)}
                className="bg-primary hover:bg-primary/90 text-primary-foreground"
              >
                <Blocks className="h-4 w-4 mr-2" />
                Register as provider
              </Button>
              <Button
                variant="outline"
                onClick={openCatalog}
                className={outlineButtonClass}
              >
                Open Google Cloud catalog
              </Button>
            </div>
          </div>
        </div>

        <RegisterDialog
          open={showRegister}
          onOpenChange={setShowRegister}
          onRegister={handleRegistered}
        />
        <HowItWorksDialog open={showHowItWorks} onOpenChange={setShowHowItWorks} />
      </>
    );
  }

  return (
    <>
      <Tabs value={tab} onValueChange={setTab} className="h-full flex flex-col">
        <div className="border-b border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-2 transition-colors">
          <TabsList className="inline-flex w-full h-9 items-center justify-between rounded-lg bg-[var(--bg-secondary)] p-1 text-[var(--text-secondary)] transition-colors">
            <TabsTrigger value="services" className={tabTriggerClass}>
              <Layers className="w-3 h-3 mr-2" />
              Services
            </TabsTrigger>
            <TabsTrigger value="changes" className={tabTriggerClass}>
              <FilePlus2 className="w-3 h-3 mr-2" />
              Changes
            </TabsTrigger>
            <TabsTrigger value="profile" className={tabTriggerClass}>
              <Building2 className="w-3 h-3 mr-2" />
              Profile
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="services" className="flex-1 m-0 p-0 overflow-hidden">
          <ServicesTab
            services={services}
            loading={catalogLoading}
            error={catalogError}
            onRetry={() => void openCatalog()}
            onPublish={() => setPublishServiceOpen(true)}
          />
        </TabsContent>

        <TabsContent value="changes" className="flex-1 m-0 p-0 overflow-hidden">
          <ChangesTab
            services={services}
            localChanges={changes}
            onPublish={() => setPublishChangeOpen(true)}
          />
        </TabsContent>

        <TabsContent value="profile" className="flex-1 m-0 p-0 overflow-hidden">
          <ProfileTab
            profile={profile}
            services={services}
            onLeave={leaveProvider}
          />
        </TabsContent>
      </Tabs>

      <PublishServiceDialog
        open={publishServiceOpen}
        onOpenChange={setPublishServiceOpen}
        onPublish={(service) => {
          setServices((prev) => [service, ...prev]);
          setTab("services");
        }}
      />
      <PublishChangeDialog
        open={publishChangeOpen}
        onOpenChange={setPublishChangeOpen}
        services={services}
        onPublish={(change) => {
          setChanges((prev) => [change, ...prev]);
          setTab("changes");
        }}
      />
    </>
  );
}

const SERVICE_STATUS_STYLE: Record<ServiceStatus, { color: string; bg: string }> = {
  live: { color: "text-[#10b981]", bg: "bg-[#10b981]/10 border-[#10b981]/30" },
  preview: { color: "text-amber-500", bg: "bg-amber-500/10 border-amber-500/30" },
  deprecated: { color: "text-red-500", bg: "bg-red-500/10 border-red-500/30" },
};

function ServicesTab({
  services,
  loading,
  error,
  onRetry,
  onPublish,
}: {
  services: PublishedService[];
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  onPublish: () => void;
}) {
  if (loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center bg-[var(--bg-primary)]">
        <Loader2 className="h-5 w-5 animate-spin text-[var(--text-secondary)] mb-3" />
        <p className="text-xs text-[var(--text-secondary)]">Loading Google Cloud services…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex flex-col items-center justify-center bg-[var(--bg-primary)] px-4">
        <div className="text-center max-w-md">
          <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
            <Layers className="h-5 w-5 text-[var(--text-secondary)]" />
          </div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
            Catalog unavailable
          </h2>
          <p className="text-xs text-[var(--text-secondary)] mb-6 leading-relaxed">{error}</p>
          {onRetry && (
            <Button
              size="sm"
              onClick={onRetry}
              className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              Retry
            </Button>
          )}
        </div>
      </div>
    );
  }
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<ServiceStatus | "all">("all");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [expandedServices, setExpandedServices] = useState<Set<string>>(new Set());

  const filtered = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    return services.filter((service) => {
      const matchesSearch =
        !q ||
        service.name.toLowerCase().includes(q) ||
        service.slug.toLowerCase().includes(q) ||
        service.product.toLowerCase().includes(q) ||
        service.identifiers.some((id) => id.toLowerCase().includes(q));
      const matchesStatus = statusFilter === "all" || service.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [services, searchQuery, statusFilter]);

  const grouped = useMemo(() => {
    const next: Record<string, PublishedService[]> = {};
    for (const service of filtered) {
      if (!next[service.group]) next[service.group] = [];
      next[service.group].push(service);
    }
    return next;
  }, [filtered]);

  const toggleGroup = (group: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };

  const toggleService = (id: string) => {
    setExpandedServices((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (services.length === 0) {
    return (
      <TabEmpty
        icon={Layers}
        title="No services yet"
        body="An organization can publish multiple services. Add the first API surface and the identifiers enterprises call."
        actionLabel="Publish service"
        onAction={onPublish}
      />
    );
  }

  return (
    <div className="h-full flex flex-col bg-[var(--bg-primary)]">
      <div className="border-b border-[var(--border-color)] p-4">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-secondary)]" />
            <Input
              placeholder="Search services..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-8 pl-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
            />
          </div>
          <Select
            value={statusFilter}
            onValueChange={(value) => setStatusFilter(value as ServiceStatus | "all")}
          >
            <SelectTrigger className="h-8 w-[130px] text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <Filter className="h-3 w-3 mr-1" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
              <SelectItem value="all" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">All status</SelectItem>
              <SelectItem value="live" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Live</SelectItem>
              <SelectItem value="preview" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Preview</SelectItem>
              <SelectItem value="deprecated" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Deprecated</SelectItem>
            </SelectContent>
          </Select>
          <Button
            onClick={onPublish}
            className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            <Plus className="h-3.5 w-3.5 mr-1" />
            Publish service
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-5xl mx-auto space-y-3">
          {Object.keys(grouped).length === 0 ? (
            <p className="text-xs text-[var(--text-secondary)] text-center py-10">
              No services match that filter.
            </p>
          ) : (
            Object.entries(grouped).map(([group, items]) => {
              const isExpanded = !collapsedGroups.has(group);
              const live = items.filter((s) => s.status === "live").length;
              const deprecated = items.filter((s) => s.status === "deprecated").length;
              const preview = items.filter((s) => s.status === "preview").length;

              return (
                <div
                  key={group}
                  className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg overflow-hidden"
                >
                  <div
                    className="p-3 cursor-pointer hover:bg-[var(--bg-tertiary)] transition-colors flex items-center justify-between"
                    onClick={() => toggleGroup(group)}
                  >
                    <div className="flex items-center gap-3">
                      <Image
                        src={getGCPCategoryIcon(group)}
                        alt={SERVICE_GROUP_LABELS[group as ServiceGroup] || group}
                        width={20}
                        height={20}
                        className="h-5 w-5 object-contain"
                      />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-[var(--text-primary)]">
                            {SERVICE_GROUP_LABELS[group as ServiceGroup] || group}
                          </span>
                          <Badge variant="outline" className="text-[9px] text-[var(--text-secondary)] border-[var(--border-color)]">
                            {items.length}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-[10px]">
                          {live > 0 && (
                            <span className="text-[#10b981]">● {live} Live</span>
                          )}
                          {preview > 0 && (
                            <span className="text-amber-500">● {preview} Preview</span>
                          )}
                          {deprecated > 0 && (
                            <span className="text-red-500">● {deprecated} Deprecated</span>
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
                      {items.map((service) => {
                        const open = expandedServices.has(service.id);
                        const status = SERVICE_STATUS_STYLE[service.status];
                        return (
                          <div
                            key={service.id}
                            className="border-b border-[var(--border-color)] last:border-b-0"
                          >
                            <div
                              className="p-3 cursor-pointer hover:bg-[var(--bg-tertiary)] transition-colors"
                              onClick={() => toggleService(service.id)}
                            >
                              <div className="flex items-start justify-between">
                                <div className="flex items-start gap-3 flex-1 min-w-0">
                                  <div className="relative mt-0.5 flex-shrink-0">
                                    <Image
                                      src={getGCPServiceIcon(service.product)}
                                      alt={service.product}
                                      width={20}
                                      height={20}
                                      className="h-5 w-5 object-contain"
                                    />
                                    <div
                                      className={cn(
                                        "absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border border-[var(--bg-tertiary)]",
                                        service.status === "live" && "bg-[#10b981]",
                                        service.status === "preview" && "bg-amber-500",
                                        service.status === "deprecated" && "bg-red-500",
                                      )}
                                    />
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                      <span className="text-xs font-medium text-[var(--text-primary)]">
                                        {service.name}
                                      </span>
                                      <Badge variant="outline" className={cn("text-[9px]", status.bg, status.color)}>
                                        {SERVICE_STATUS_LABELS[service.status]}
                                      </Badge>
                                      {service.product !== service.name && (
                                        <Badge variant="outline" className="text-[9px] text-[var(--text-secondary)] border-[var(--border-color)]">
                                          {service.product}
                                        </Badge>
                                      )}
                                    </div>
                                    <div className="flex items-center gap-3 mt-1 text-[10px] text-[var(--text-secondary)]">
                                      <span className="font-mono">{service.slug}</span>
                                      <span className="flex items-center gap-1">
                                        <Layers className="h-3 w-3" />
                                        {service.identifiers.length} identifiers
                                      </span>
                                      {service.watchers > 0 && (
                                        <span className="flex items-center gap-1">
                                          <Eye className="h-3 w-3" />
                                          {formatWatchers(service.watchers)} watching
                                        </span>
                                      )}
                                      <span className="flex items-center gap-1">
                                        <Clock className="h-3 w-3" />
                                        {formatShortDate(service.lastPublishedAt)}
                                      </span>
                                    </div>
                                  </div>
                                </div>
                                {open ? (
                                  <ChevronDown className="h-4 w-4 text-[var(--text-secondary)] ml-2" />
                                ) : (
                                  <ChevronRight className="h-4 w-4 text-[var(--text-secondary)] ml-2" />
                                )}
                              </div>
                            </div>

                            {open && (
                              <div className="bg-[var(--bg-tertiary)] p-4 space-y-3">
                                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                                  {service.summary}
                                </p>
                                <div>
                                  <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">
                                    Identifiers
                                  </label>
                                  <div className="mt-1 space-y-1.5">
                                    {service.identifiers.map((id) => (
                                      <p
                                        key={id}
                                        className="font-mono text-[12px] text-[var(--text-primary)] px-2 py-1.5 rounded-md bg-[var(--bg-secondary)] border border-[var(--border-color)]"
                                      >
                                        {id}
                                      </p>
                                    ))}
                                  </div>
                                </div>
                                <div className="flex items-center gap-2 pt-1">
                                  <a
                                    href={service.docsUrl}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="inline-flex"
                                  >
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      className={cn("h-7 text-xs", outlineButtonClass)}
                                    >
                                      <ExternalLink className="h-3 w-3 mr-1" />
                                      View docs
                                    </Button>
                                  </a>
                                </div>
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
    </div>
  );
}

const CHANGE_PAGE_SIZE = 75;

function matchesChangeFilter(
  change: PublishedChange,
  q: string,
  kind: ChangeKind | "all",
): boolean {
  if (kind !== "all" && change.kind !== kind) return false;
  if (!q) return true;
  return (
    change.title.toLowerCase().includes(q) ||
    (change.product || "").toLowerCase().includes(q) ||
    (change.summary || "").toLowerCase().includes(q) ||
    change.serviceId.toLowerCase().includes(q)
  );
}

function ChangesTab({
  services,
  localChanges,
  onPublish,
}: {
  services: PublishedService[];
  localChanges: PublishedChange[];
  onPublish: () => void;
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [kindFilter, setKindFilter] = useState<ChangeKind | "all">("all");
  const [changes, setChanges] = useState<PublishedChange[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedQuery(searchQuery.trim()), 250);
    return () => window.clearTimeout(handle);
  }, [searchQuery]);

  useEffect(() => {
    setOffset(0);
    setChanges([]);
  }, [debouncedQuery, kindFilter]);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({
      limit: String(CHANGE_PAGE_SIZE),
      offset: String(offset),
    });
    if (debouncedQuery) params.set("q", debouncedQuery);
    if (kindFilter !== "all") params.set("kind", kindFilter);
    setLoading(true);
    setError(null);
    void fetch(`${API_URL}/api/providers/google/changes?${params}`, {
      credentials: "include",
      signal: controller.signal,
    })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(body?.detail || `Release notes unavailable (${response.status})`);
        }
        const rows = Array.isArray(body?.changes) ? body.changes : [];
        const mapped = rows
          .map((row: Parameters<typeof catalogChangeFromApi>[0]) => catalogChangeFromApi(row))
          .filter((change: PublishedChange | null): change is PublishedChange => change !== null);
        setTotal(typeof body?.total === "number" ? body.total : mapped.length);
        setChanges((prev) => (offset === 0 ? mapped : [...prev, ...mapped]));
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Could not load release notes");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [debouncedQuery, kindFilter, offset]);

  const q = debouncedQuery.toLowerCase();
  const filtered = useMemo(() => {
    const remote = changes.filter((change) => matchesChangeFilter(change, q, kindFilter));
    const extras = localChanges.filter((change) => matchesChangeFilter(change, q, kindFilter));
    const seen = new Set(remote.map((change) => change.id));
    return [...extras.filter((change) => !seen.has(change.id)), ...remote];
  }, [changes, kindFilter, localChanges, q]);

  const serviceName = (change: PublishedChange) =>
    change.product ||
    services.find((s) => s.id === change.serviceId)?.name ||
    services.find((s) => s.product === change.serviceId)?.name ||
    change.serviceId;

  if (loading && filtered.length === 0) {
    return (
      <div className="h-full flex items-center justify-center bg-[var(--bg-secondary)]">
        <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading release notes…
        </div>
      </div>
    );
  }

  if (error && filtered.length === 0) {
    return (
      <TabEmpty
        icon={FilePlus2}
        title="Release notes unavailable"
        body={error}
        actionLabel="Publish change"
        onAction={onPublish}
        actionDisabled={services.length === 0}
      />
    );
  }

  return (
    <div className="h-full flex flex-col bg-[var(--bg-secondary)]">
      <div className="px-4 py-3 border-b border-[var(--border-color)] bg-[var(--bg-primary)]">
        <div className="max-w-5xl mx-auto flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-secondary)]" />
            <Input
              placeholder="Search release notes…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-8 pl-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
            />
          </div>
          <Select
            value={kindFilter}
            onValueChange={(value) => setKindFilter(value as ChangeKind | "all")}
          >
            <SelectTrigger className="h-8 w-[150px] text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <Filter className="h-3 w-3 mr-1" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
              <SelectItem value="all" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">
                All types
              </SelectItem>
              {(Object.keys(CHANGE_KIND_LABELS) as ChangeKind[]).map((key) => (
                <SelectItem
                  key={key}
                  value={key}
                  className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]"
                >
                  {CHANGE_KIND_LABELS[key]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            onClick={onPublish}
            disabled={services.length === 0}
            className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground disabled:opacity-40"
          >
            <Plus className="h-3.5 w-3.5 mr-1" />
            Publish change
          </Button>
        </div>
        <p className="max-w-5xl mx-auto mt-2 text-[10px] text-[var(--text-secondary)]">
          {filtered.length.toLocaleString()}
          {total > filtered.length ? ` of ${total.toLocaleString()}` : ""} notes
          {loading ? " · loading…" : ""}
          · last 365 days · untrusted provider input
        </p>
      </div>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-6 py-6 space-y-3">
          {filtered.length === 0 ? (
            <p className="text-xs text-[var(--text-secondary)] text-center py-10">
              No release notes match that filter.
            </p>
          ) : (
            filtered.map((change, index) => (
              <div
                key={`${change.id}:${index}`}
                className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-primary)] p-4"
              >
                <ChangeRow change={change} serviceName={serviceName(change)} />
              </div>
            ))
          )}
          {changes.length < total && (
            <div className="flex justify-center pt-2">
              <Button
                variant="outline"
                onClick={() => setOffset(changes.length)}
                disabled={loading}
                className={cn("h-8 text-xs", outlineButtonClass)}
              >
                Show more ({(total - changes.length).toLocaleString()} left)
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ProfileTab({
  profile,
  services,
  onLeave,
}: {
  profile: ProviderProfile;
  services: PublishedService[];
  onLeave: () => void;
}) {
  const products = useMemo(() => {
    if (profile.featuredProducts?.length) return profile.featuredProducts;
    const seen = new Set<string>();
    const next: string[] = [];
    for (const service of services) {
      if (seen.has(service.product)) continue;
      seen.add(service.product);
      next.push(service.product);
      if (next.length >= 8) break;
    }
    return next;
  }, [profile.featuredProducts, services]);

  const host = profile.website.replace(/^https?:\/\//, "");

  return (
    <div className="h-full overflow-y-auto bg-[var(--bg-secondary)]">
      <div className="max-w-2xl mx-auto px-6 py-8 space-y-5">
        <div className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-primary)] p-5">
          <div className="flex items-start gap-4">
            {profile.logoUrl ? (
              <div className="h-14 w-14 rounded-2xl bg-white border border-[var(--border-color)] flex items-center justify-center flex-shrink-0 shadow-sm">
                <Image
                  src={profile.logoUrl}
                  alt={profile.name}
                  width={32}
                  height={32}
                  className="h-8 w-8 object-contain"
                />
              </div>
            ) : (
              <div className="h-14 w-14 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center text-base font-semibold text-primary flex-shrink-0">
                {initials(profile.name)}
              </div>
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h2 className="text-base font-semibold text-[var(--text-primary)] tracking-tight">
                      {profile.name}
                    </h2>
                    {profile.verified ? (
                      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-500">
                        <BadgeCheck className="h-3 w-3" />
                        Verified publisher
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/25 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-500">
                        <Clock3 className="h-3 w-3" />
                        Review pending
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-[var(--text-secondary)] mt-1">
                    {CATEGORY_LABELS[profile.category]}
                    {profile.since && (
                      <>
                        <span className="mx-1.5">·</span>
                        Since {profile.since}
                      </>
                    )}
                    {profile.hq && (
                      <>
                        <span className="mx-1.5">·</span>
                        {profile.hq}
                      </>
                    )}
                  </p>
                </div>
              </div>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed mt-3">
                {profile.description}
              </p>
            </div>
          </div>
        </div>

        {products.length > 0 && (
          <div className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-primary)] p-5">
            <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)] mb-3">
              Surfaces
            </p>
            <div className="flex flex-wrap gap-2">
              {products.map((product) => (
                <span
                  key={product}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] px-2 py-1.5 text-[11px] text-[var(--text-primary)]"
                >
                  <Image
                    src={getGCPServiceIcon(product)}
                    alt=""
                    width={14}
                    height={14}
                    className="h-3.5 w-3.5 object-contain"
                  />
                  {product}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-primary)] divide-y divide-[var(--border-color)]">
          <DetailRow icon={Globe} label="Website" value={host} href={profile.website} />
          {profile.consoleUrl && (
            <DetailRow
              icon={ExternalLink}
              label="Console"
              value={profile.consoleUrl.replace(/^https?:\/\//, "")}
              href={profile.consoleUrl}
            />
          )}
          {profile.docsUrl && (
            <DetailRow
              icon={Layers}
              label="Docs"
              value={profile.docsUrl.replace(/^https?:\/\//, "")}
              href={profile.docsUrl}
            />
          )}
          {profile.statusUrl && (
            <DetailRow
              icon={Eye}
              label="Status"
              value={profile.statusUrl.replace(/^https?:\/\//, "")}
              href={profile.statusUrl}
            />
          )}
          <DetailRow icon={Mail} label="Contact" value={profile.contactEmail} href={`mailto:${profile.contactEmail}`} />
          {profile.hq && <DetailRow icon={MapPin} label="Headquarters" value={profile.hq} />}
        </div>

        <div className="flex items-start gap-2.5 rounded-xl border border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-3">
          <Shield className="h-3.5 w-3.5 text-[var(--text-secondary)] mt-0.5 flex-shrink-0" />
          <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
            Provider material is untrusted input. Opening this catalog does not grant
            access to customer repositories, secrets, or merge rights.
          </p>
        </div>

        <Button
          variant="outline"
          onClick={onLeave}
          className={cn("h-8 text-xs", outlineMutedButtonClass)}
        >
          Leave catalog
        </Button>
      </div>
    </div>
  );
}

function DetailRow({
  icon: Icon,
  label,
  value,
  href,
}: {
  icon: typeof Globe;
  label: string;
  value: string;
  href?: string;
}) {
  const inner = (
    <>
      <span className="inline-flex items-center gap-2 text-xs text-[var(--text-secondary)]">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </span>
      <span className="inline-flex items-center gap-1 text-xs text-[var(--text-primary)] truncate min-w-0">
        <span className="truncate">{value}</span>
        {href && <ArrowUpRight className="h-3 w-3 text-[var(--text-secondary)] flex-shrink-0" />}
      </span>
    </>
  );

  if (href) {
    return (
      <a
        href={href}
        target={href.startsWith("mailto:") ? undefined : "_blank"}
        rel={href.startsWith("mailto:") ? undefined : "noreferrer"}
        className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-[var(--bg-tertiary)] transition-colors"
      >
        {inner}
      </a>
    );
  }

  return <div className="flex items-center justify-between gap-4 px-4 py-3">{inner}</div>;
}

function TabEmpty({
  icon: Icon,
  title,
  body,
  actionLabel,
  onAction,
  actionDisabled,
  actionHint,
}: {
  icon: typeof Layers;
  title: string;
  body: string;
  actionLabel: string;
  onAction: () => void;
  actionDisabled?: boolean;
  actionHint?: string;
}) {
  return (
    <div className="h-full flex items-center justify-center bg-[var(--bg-primary)]">
      <div className="text-center max-w-md px-4">
        <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <Icon className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">{title}</h2>
        <p className="text-xs text-[var(--text-secondary)] mb-6 leading-relaxed">{body}</p>
        <Button
          size="sm"
          onClick={onAction}
          disabled={actionDisabled}
          className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground disabled:opacity-40"
        >
          <Plus className="h-3 w-3 mr-1" />
          {actionLabel}
        </Button>
        {actionHint && (
          <p className="text-[11px] text-[var(--text-secondary)] mt-3">{actionHint}</p>
        )}
      </div>
    </div>
  );
}

function HowItWorksDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] bg-[var(--bg-primary)] border-[var(--border-color)]">
        <DialogHeader>
          <DialogTitle className="text-[var(--text-primary)]">How providers work</DialogTitle>
          <DialogDescription className="text-[var(--text-secondary)]">
            One organization, many services — then structured change events.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-4">
          {[
            { n: "1", title: "Register as a provider", desc: "This organization becomes a publisher. You never receive customer source." },
            { n: "2", title: "Publish services", desc: "An org can list multiple APIs, each with the identifiers enterprises actually call." },
            { n: "3", title: "Announce changes", desc: "Deprecations and replacements attach to a service, with a source URL." },
            { n: "4", title: "Runs stop at the PR", desc: "PatchAPI treats your catalog as untrusted input and opens a pull request for review." },
          ].map((step) => (
            <div key={step.n} className="flex gap-3">
              <div className="flex-shrink-0 h-6 w-6 rounded border border-[var(--border-color)] bg-[var(--bg-secondary)] flex items-center justify-center">
                <span className="text-xs font-medium text-[var(--text-secondary)]">{step.n}</span>
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">{step.title}</h3>
                <p className="text-xs text-[var(--text-secondary)]">{step.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RegisterDialog({
  open,
  onOpenChange,
  onRegister,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRegister: (profile: ProviderProfile) => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [website, setWebsite] = useState("");
  const [email, setEmail] = useState("");
  const [category, setCategory] = useState<ProviderCategory>("ai");
  const [description, setDescription] = useState("");
  const [attested, setAttested] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setName("");
    setSlug("");
    setSlugTouched(false);
    setWebsite("");
    setEmail("");
    setCategory("ai");
    setDescription("");
    setAttested(false);
    setError(null);
  };

  const handleSubmit = () => {
    if (!name.trim()) return setError("Enter an organization name.");
    if (!slugify(slug)) return setError("Enter a URL slug.");
    if (!email.trim() || !email.includes("@")) return setError("Enter a contact email.");
    if (!attested) return setError("Confirm the trust boundary before registering.");
    onRegister({
      id: `prov_${slugify(slug) || "new"}`,
      name: name.trim(),
      slug: slugify(slug),
      website: website.trim() || "https://example.com",
      contactEmail: email.trim(),
      category,
      description:
        description.trim() ||
        "Newly registered provider. Publish services and change events from this catalog.",
      verified: false,
      registeredAt: new Date().toISOString(),
      watchingOrgs: 0,
    });
    reset();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) reset();
      }}
    >
      <DialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)] max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
            Register as provider
          </DialogTitle>
          <DialogDescription className="text-xs text-[var(--text-secondary)] leading-relaxed">
            Hardcoded for now — nothing is written to a backend. One org, many services.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3.5 py-1">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Organization">
              <Input
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  if (!slugTouched) setSlug(slugify(e.target.value));
                }}
                placeholder="Acme AI"
                className={fieldClass}
              />
            </Field>
            <Field label="Slug">
              <Input
                value={slug}
                onChange={(e) => {
                  setSlugTouched(true);
                  setSlug(slugify(e.target.value));
                }}
                placeholder="acme-ai"
                className={cn(fieldClass, "font-mono")}
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Website">
              <Input
                value={website}
                onChange={(e) => setWebsite(e.target.value)}
                placeholder="https://acme.ai"
                className={fieldClass}
              />
            </Field>
            <Field label="Contact email">
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="api@acme.ai"
                className={fieldClass}
              />
            </Field>
          </div>
          <Field label="Category">
            <Select value={category} onValueChange={(v) => setCategory(v as ProviderCategory)}>
              <SelectTrigger className={selectTriggerClass}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className={selectContentClass}>
                {(Object.keys(CATEGORY_LABELS) as ProviderCategory[]).map((key) => (
                  <SelectItem key={key} value={key} className={selectItemClass}>
                    {CATEGORY_LABELS[key]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="What you publish">
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Model IDs and deprecation dates for the Acme image API."
              className={textareaClass}
            />
          </Field>
          <label className="flex items-start gap-2.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] px-3 py-2.5 cursor-pointer">
            <input
              type="checkbox"
              checked={attested}
              onChange={(e) => setAttested(e.target.checked)}
              className="mt-0.5 accent-[hsl(var(--primary))]"
            />
            <span className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
              I understand provider material is untrusted input. This does not grant
              access to customer repositories, secrets, or merge rights.
            </span>
          </label>
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            className={cn("h-7 text-xs", outlineMutedButtonClass)}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            className="h-7 text-xs bg-primary hover:bg-primary-hover text-primary-foreground"
          >
            Register
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PublishServiceDialog({
  open,
  onOpenChange,
  onPublish,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPublish: (service: PublishedService) => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [summary, setSummary] = useState("");
  const [identifiers, setIdentifiers] = useState("");
  const [docsUrl, setDocsUrl] = useState("");
  const [status, setStatus] = useState<ServiceStatus>("live");
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setName("");
    setSlug("");
    setSlugTouched(false);
    setSummary("");
    setIdentifiers("");
    setDocsUrl("");
    setStatus("live");
    setError(null);
  };

  const handleSubmit = () => {
    if (!name.trim()) return setError("Enter a service name.");
    const ids = identifiers
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (ids.length === 0) return setError("List at least one identifier.");
    const meta = inferServiceMeta(name);
    onPublish({
      id: `svc_${slugify(slug || name)}_${Date.now()}`,
      name: name.trim(),
      slug: slugify(slug || name),
      summary: summary.trim() || "Published service. Identifiers are available for inventory.",
      status,
      product: meta.product,
      group: meta.group,
      identifiers: ids,
      docsUrl: docsUrl.trim() || "https://example.com/docs",
      watchers: 0,
      lastPublishedAt: new Date().toISOString(),
    });
    reset();
    onOpenChange(false);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) reset();
      }}
    >
      <DialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)] max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
            Publish a service
          </DialogTitle>
          <DialogDescription className="text-xs text-[var(--text-secondary)] leading-relaxed">
            Add another API surface under this organization. Hardcoded — nothing is sent.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3.5 py-1">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Name">
              <Input
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  if (!slugTouched) setSlug(slugify(e.target.value));
                }}
                placeholder="Image Generate"
                className={fieldClass}
              />
            </Field>
            <Field label="Slug">
              <Input
                value={slug}
                onChange={(e) => {
                  setSlugTouched(true);
                  setSlug(slugify(e.target.value));
                }}
                placeholder="image-generate"
                className={cn(fieldClass, "font-mono")}
              />
            </Field>
          </div>
          <Field label="Status">
            <Select value={status} onValueChange={(v) => setStatus(v as ServiceStatus)}>
              <SelectTrigger className={selectTriggerClass}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className={selectContentClass}>
                {(Object.keys(SERVICE_STATUS_LABELS) as ServiceStatus[]).map((key) => (
                  <SelectItem key={key} value={key} className={selectItemClass}>
                    {SERVICE_STATUS_LABELS[key]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Summary">
            <Textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="What this service is, in one or two sentences."
              className={textareaClass}
            />
          </Field>
          <Field label="Identifiers" hint="One per line, or comma-separated.">
            <Textarea
              value={identifiers}
              onChange={(e) => setIdentifiers(e.target.value)}
              placeholder={"acme-image-3\nacme-image-3-fast"}
              className={cn(textareaClass, "font-mono")}
            />
          </Field>
          <Field label="Docs URL">
            <Input
              value={docsUrl}
              onChange={(e) => setDocsUrl(e.target.value)}
              placeholder="https://docs.acme.ai/image"
              className={fieldClass}
            />
          </Field>
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            className={cn("h-7 text-xs", outlineMutedButtonClass)}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            className="h-7 text-xs bg-primary hover:bg-primary-hover text-primary-foreground"
          >
            Publish
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PublishChangeDialog({
  open,
  onOpenChange,
  services,
  onPublish,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  services: PublishedService[];
  onPublish: (change: PublishedChange) => void;
}) {
  const [serviceId, setServiceId] = useState(services[0]?.id ?? "");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<ChangeKind>("deprecation");
  const [effectiveAt, setEffectiveAt] = useState("2026-08-17");
  const [retired, setRetired] = useState("");
  const [replacement, setReplacement] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setServiceId(services[0]?.id ?? "");
    setTitle("");
    setKind("deprecation");
    setEffectiveAt("2026-08-17");
    setRetired("");
    setReplacement("");
    setSourceUrl("");
    setError(null);
  };

  const handleSubmit = () => {
    if (!serviceId) return setError("Publish a service first.");
    if (!title.trim()) return setError("Enter a title.");
    const ids = retired
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean);
    onPublish({
      id: `chg_${Date.now()}`,
      serviceId,
      title: title.trim(),
      kind,
      status: "published",
      effectiveAt: new Date(`${effectiveAt}T00:00:00Z`).toISOString(),
      retiredIdentifiers: ids,
      recommendedReplacement: replacement.trim() || null,
      sourceUrl: sourceUrl.trim() || "https://example.com/changelog",
      publishedAt: new Date().toISOString(),
    });
    reset();
    onOpenChange(false);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (v) {
          setServiceId((current) =>
            services.some((s) => s.id === current) ? current : (services[0]?.id ?? ""),
          );
        } else {
          reset();
        }
      }}
    >
      <DialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)] max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
            Publish a change
          </DialogTitle>
          <DialogDescription className="text-xs text-[var(--text-secondary)] leading-relaxed">
            Attach a sourced event to one of this organization’s services.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3.5 py-1">
          <Field label="Service">
            <Select value={serviceId} onValueChange={setServiceId} disabled={services.length === 0}>
              <SelectTrigger className={selectTriggerClass}>
                <SelectValue placeholder="Select a service" />
              </SelectTrigger>
              <SelectContent className={selectContentClass}>
                {services.map((service) => (
                  <SelectItem key={service.id} value={service.id} className={selectItemClass}>
                    {service.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Title">
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Imagen 4 identifiers retire"
              className={fieldClass}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Kind">
              <Select value={kind} onValueChange={(v) => setKind(v as ChangeKind)}>
                <SelectTrigger className={selectTriggerClass}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className={selectContentClass}>
                  {(["deprecation", "replacement", "new_identifier", "breaking_change"] as ChangeKind[]).map((key) => (
                    <SelectItem key={key} value={key} className={selectItemClass}>
                      {CHANGE_KIND_LABELS[key]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Effective date">
              <Input
                type="date"
                value={effectiveAt}
                onChange={(e) => setEffectiveAt(e.target.value)}
                className={fieldClass}
              />
            </Field>
          </div>
          <Field label="Retired identifiers" hint="Optional. One per line.">
            <Textarea
              value={retired}
              onChange={(e) => setRetired(e.target.value)}
              placeholder="imagen-4.0-generate-001"
              className={cn(textareaClass, "font-mono")}
            />
          </Field>
          <Field label="Recommended replacement">
            <Input
              value={replacement}
              onChange={(e) => setReplacement(e.target.value)}
              placeholder="gemini-3.1-flash-image"
              className={cn(fieldClass, "font-mono")}
            />
          </Field>
          <Field label="Source URL">
            <Input
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://ai.google.dev/gemini-api/docs/deprecations"
              className={fieldClass}
            />
          </Field>
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            className={cn("h-7 text-xs", outlineMutedButtonClass)}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            className="h-7 text-xs bg-primary hover:bg-primary-hover text-primary-foreground"
          >
            Publish
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ChangeRow({
  change,
  serviceName,
}: {
  change: PublishedChange;
  serviceName?: string;
}) {
  const days = daysUntil(change.effectiveAt);
  const urgent = days <= 14;

  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
          <KindPill kind={change.kind} />
          {serviceName && (
            <span className="text-[10px] text-[var(--text-secondary)]">{serviceName}</span>
          )}
        </div>
        <p className="text-sm font-medium text-[var(--text-primary)] leading-snug">
          {change.title}
        </p>
        {change.summary && change.summary !== change.title && (
          <p className="mt-1.5 text-[11px] text-[var(--text-secondary)] leading-relaxed">
            {change.summary}
          </p>
        )}
        {change.retiredIdentifiers.length > 0 && (
          <div className="mt-2 space-y-1">
            {change.retiredIdentifiers.map((id) => (
              <p key={id} className="font-mono text-[11px] text-[var(--text-secondary)]">
                {id}
              </p>
            ))}
            {change.recommendedReplacement && (
              <p className="font-mono text-[11px] text-emerald-500">
                → {change.recommendedReplacement}
              </p>
            )}
          </div>
        )}
        <a
          href={change.sourceUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 mt-2 text-[10px] text-[var(--text-secondary)] hover:text-primary transition-colors"
        >
          <Link2 className="h-3 w-3" />
          Source
          <ArrowUpRight className="h-3 w-3" />
        </a>
      </div>
      <div className="text-right flex-shrink-0">
        <p className="text-[10px] uppercase tracking-wider text-[var(--text-secondary)]">
          Published
        </p>
        <p
          className={cn(
            "text-sm font-semibold tabular-nums mt-0.5",
            urgent ? "text-red-400" : "text-[var(--text-primary)]",
          )}
        >
          {formatShortDate(change.effectiveAt)}
        </p>
        <p className={cn("text-[10px] tabular-nums", urgent ? "text-red-400" : "text-[var(--text-secondary)]")}>
          {days < 0 ? `${Math.abs(days)}d ago` : days === 0 ? "today" : `in ${days}d`}
        </p>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      <Label className="text-xs text-[var(--text-secondary)]">{label}</Label>
      {children}
      {hint && <p className="text-[10px] text-[var(--text-secondary)]">{hint}</p>}
    </div>
  );
}

function KindPill({ kind }: { kind: ChangeKind }) {
  const styles: Record<ChangeKind, string> = {
    deprecation: "text-red-400 bg-red-500/10 border-red-500/20",
    replacement: "text-amber-400 bg-amber-500/10 border-amber-500/20",
    new_identifier: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    breaking_change: "text-red-400 bg-red-500/10 border-red-500/20",
    feature: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    fix: "text-sky-400 bg-sky-500/10 border-sky-500/20",
    issue: "text-amber-400 bg-amber-500/10 border-amber-500/20",
    security: "text-red-400 bg-red-500/10 border-red-500/20",
    announcement: "text-[var(--text-secondary)] bg-[var(--bg-tertiary)] border-[var(--border-color)]",
    change: "text-[var(--text-secondary)] bg-[var(--bg-tertiary)] border-[var(--border-color)]",
    libraries: "text-sky-400 bg-sky-500/10 border-sky-500/20",
    other: "text-[var(--text-secondary)] bg-[var(--bg-tertiary)] border-[var(--border-color)]",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium",
        styles[kind],
      )}
    >
      {CHANGE_KIND_LABELS[kind]}
    </span>
  );
}
