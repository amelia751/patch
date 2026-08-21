"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import Image from "next/image";
import { format, startOfDay, subDays } from "date-fns";
import { type DateRange } from "react-day-picker";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
import { getGCPCategoryIcon, getGCPServiceIcon } from "@/lib/gcp-icons";
import { Spinner } from "@/components/ui/spinner";
import {
  checkProviderSlug,
  connectProvider,
  disconnectProvider,
  fetchProvider,
  providersApiUrl as API_URL,
  registerProvider,
  type ProviderConnection,
  type ProviderRecord,
  type RegisterProviderInput,
} from "@/lib/providers";
import { ConnectionChip, ConnectionDialog } from "./connection-dialog";
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
  Building,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  Clock,
  Clock3,
  ExternalLink,
  Eye,
  FilePlus2,
  Globe,
  Info,
  Layers,
  Loader2,
  Mail,
  MapPin,
  Search,
  X,
} from "lucide-react";
import {
  CATEGORY_LABELS,
  CHANGE_KIND_LABELS,
  SERVICE_GROUP_LABELS,
  SERVICE_STATUS_LABELS,
  asProviderCategory,
  catalogChangeFromApi,
  catalogServiceFromApi,
  formatShortDate,
  formatWatchers,
  initials,
  sanitizeSlugInput,
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

const rowInputClass =
  "h-8 text-xs bg-transparent border-0 shadow-none px-0 focus-visible:ring-0 focus-visible:border-0 text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]/45";

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

/** Outline actions — same dark hover as the header theme toggle. */
const outlineButtonClass =
  "border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]";

const outlineMutedButtonClass =
  "border-[var(--border-color)] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]";

export function ProviderPortal() {
  const [profile, setProfile] = useState<ProviderRecord | null>(null);
  const [services, setServices] = useState<PublishedService[]>([]);
  const [tab, setTab] = useState("services");
  const [showRegister, setShowRegister] = useState(false);
  const [showHowItWorks, setShowHowItWorks] = useState(false);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  const loadServices = async (slug: string) => {
    setCatalogError(null);
    setCatalogLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/providers/${encodeURIComponent(slug)}/services`, {
        credentials: "include",
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(body?.detail || `Catalog unavailable (${response.status})`);
      }
      const rows = Array.isArray(body?.services) ? body.services : [];
      setServices(rows.map((row: Parameters<typeof catalogServiceFromApi>[0]) => catalogServiceFromApi(row)));
    } catch (error) {
      setServices([]);
      setCatalogError(
        error instanceof Error ? error.message : "Could not load the catalog",
      );
    } finally {
      setCatalogLoading(false);
    }
  };

  const refreshProfile = async (slug: string) => {
    const next = await fetchProvider(slug);
    setProfile(next);
    return next;
  };

  const openCatalog = async () => {
    setServices([]);
    setTab("services");
    setShowRegister(false);
    setCatalogError(null);
    setCatalogLoading(true);
    try {
      const next = await fetchProvider("google");
      setProfile(next);
      await loadServices(next.slug);
    } catch (error) {
      setCatalogError(
        error instanceof Error ? error.message : "Could not load the Google Cloud catalog",
      );
      setCatalogLoading(false);
    }
  };

  const handleRegistered = async (input: RegisterProviderInput) => {
    const next = await registerProvider(input);
    setProfile(next);
    setServices([]);
    setTab("services");
    setShowRegister(false);
  };

  const leaveProvider = () => {
    setProfile(null);
    setServices([]);
    setTab("services");
  };

  useEffect(() => {
    if (!profile) return;
    const pending = [profile.connections.catalog, profile.connections.changes].some(
      (item) => item?.status === "pending",
    );
    if (!pending) return;
    const handle = window.setInterval(() => {
      void refreshProfile(profile.slug)
        .then((next) => {
          if (next.connections.catalog?.status === "connected") {
            void loadServices(next.slug);
          }
        })
        .catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(handle);
  }, [profile]);

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
              <Building className="w-3 h-3 mr-2" />
              Profile
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="services" className="flex-1 m-0 p-0 overflow-hidden">
          <ServicesTab
            slug={profile.slug}
            services={services}
            connection={profile.connections.catalog}
            loading={catalogLoading}
            error={catalogError}
            onRetry={() => void loadServices(profile.slug)}
            onConnectionChange={async () => {
              const next = await refreshProfile(profile.slug);
              await loadServices(next.slug);
            }}
          />
        </TabsContent>

        <TabsContent value="changes" className="flex-1 m-0 p-0 overflow-hidden">
          <ChangesTab
            slug={profile.slug}
            connection={profile.connections.changes}
            onConnectionChange={() => void refreshProfile(profile.slug)}
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

    </>
  );
}

const SERVICE_STATUS_STYLE: Record<ServiceStatus, { color: string; bg: string }> = {
  live: { color: "text-[#10b981]", bg: "bg-[#10b981]/10 border-[#10b981]/30" },
  preview: { color: "text-amber-500", bg: "bg-amber-500/10 border-amber-500/30" },
  deprecated: { color: "text-red-500", bg: "bg-red-500/10 border-red-500/30" },
};

const SERVICE_STATUS_DOT: Record<ServiceStatus, string> = {
  live: "bg-[#10b981]",
  preview: "bg-amber-500",
  deprecated: "bg-red-500",
};

function ServicesTab({
  slug,
  services,
  connection,
  loading,
  error,
  onRetry,
  onConnectionChange,
}: {
  slug: string;
  services: PublishedService[];
  connection: ProviderConnection | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  onConnectionChange: () => Promise<void>;
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<ServiceStatus | "all">("all");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [expandedServices, setExpandedServices] = useState<Set<string>>(new Set());
  const [sourceOpen, setSourceOpen] = useState(false);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [sourceError, setSourceError] = useState<string | null>(null);

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

  const atDefaults = !searchQuery && statusFilter === "all";
  const resetFilters = () => {
    setSearchQuery("");
    setStatusFilter("all");
  };

  return (
    <div className="h-full flex flex-col bg-[var(--bg-primary)]">
      <div className="border-b border-[var(--border-color)] px-4 pt-4 pb-3 space-y-3">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-secondary)]" />
            <Input
              placeholder="Search Vertex, GKE, Cloud Storage…"
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
          <ConnectionChip connection={connection} onClick={() => setSourceOpen(true)} />
        </div>

        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
            Status
          </span>
          <div className="inline-flex flex-wrap items-center gap-1">
            <FilterChip
              tone="pill"
              active={statusFilter === "all"}
              onClick={() => setStatusFilter("all")}
            >
              All
            </FilterChip>
            {(Object.keys(SERVICE_STATUS_LABELS) as ServiceStatus[]).map((status) => (
              <FilterChip
                key={status}
                tone="pill"
                active={statusFilter === status}
                onClick={() => setStatusFilter(statusFilter === status ? "all" : status)}
              >
                <span className={cn("h-1.5 w-1.5 rounded-full", SERVICE_STATUS_DOT[status])} />
                <span className={cn(statusFilter === status && SERVICE_STATUS_STYLE[status].color)}>
                  {SERVICE_STATUS_LABELS[status]}
                </span>
              </FilterChip>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between gap-3">
          <p className="text-[11px] text-[var(--text-secondary)]">
            {`${filtered.length.toLocaleString()} ${filtered.length === 1 ? "service" : "services"}`}
            {statusFilter !== "all" && (
              <>
                <span className="mx-1.5 text-[var(--border-color)]">·</span>
                {SERVICE_STATUS_LABELS[statusFilter].toLowerCase()}
              </>
            )}
          </p>
          {!atDefaults && (
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

      <ConnectionDialog
        open={sourceOpen}
        onOpenChange={setSourceOpen}
        kind="catalog"
        connection={connection}
        pending={sourceBusy}
        error={sourceError}
        onConnect={async (url) => {
          setSourceBusy(true);
          setSourceError(null);
          try {
            await connectProvider(slug, "catalog", url);
            await onConnectionChange();
          } catch (err) {
            setSourceError(err instanceof Error ? err.message : "Could not connect");
          } finally {
            setSourceBusy(false);
          }
        }}
        onDisconnect={async () => {
          setSourceBusy(true);
          setSourceError(null);
          try {
            await disconnectProvider(slug, "catalog");
            await onConnectionChange();
            setSourceOpen(false);
          } catch (err) {
            setSourceError(err instanceof Error ? err.message : "Could not disconnect");
          } finally {
            setSourceBusy(false);
          }
        }}
      />
    </div>
  );
}

const CHANGE_PAGE_SIZE = 25;

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

function productFamily(product: string): string {
  const trimmed = product.trim();
  if (!trimmed) return "Google Cloud";
  return (
    trimmed
      .replace(/\s+(flexible|standard)\s+environment\b.*$/i, "")
      .replace(/\s+\((?:new|legacy)\)\s*$/i, "")
      .trim() || trimmed
  );
}

function collapseWhitespace(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function noteBody(change: PublishedChange): string {
  const summary = collapseWhitespace(change.summary || "");
  const title = collapseWhitespace(change.title);
  if (!summary) return title;
  const titleCore = title.replace(/…$/, "").trim();
  const summaryCore = summary.replace(/…$/, "").trim();
  if (summary.startsWith(titleCore) || title.startsWith(summaryCore)) return summary;
  return summary;
}

function summaryStem(text: string): string {
  return collapseWhitespace(text).slice(0, 80).toLowerCase();
}

function variantLabel(product: string, family: string): string {
  const rest = product.slice(family.length).replace(/^[\s\-–—:]+/, "").trim();
  if (!rest) return "";
  return rest
    .replace(/^flexible environment\s+/i, "Flexible · ")
    .replace(/^standard environment\s+/i, "Standard · ");
}

function formatDayHeading(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

type ChangeCluster = {
  id: string;
  dateKey: string;
  date: string;
  kind: ChangeKind;
  product: string;
  body: string;
  sourceUrl: string;
  members: PublishedChange[];
};

function clusterChanges(changes: PublishedChange[]): ChangeCluster[] {
  const clusters: ChangeCluster[] = [];
  const index = new Map<string, number>();
  for (const change of changes) {
    const product = productFamily(change.product || change.serviceId);
    const key = `${change.effectiveAt.slice(0, 10)}|${change.kind}|${product}|${summaryStem(noteBody(change))}`;
    const existing = index.get(key);
    if (existing !== undefined) {
      clusters[existing].members.push(change);
      continue;
    }
    index.set(key, clusters.length);
    clusters.push({
      id: change.id,
      dateKey: change.effectiveAt.slice(0, 10),
      date: change.effectiveAt,
      kind: change.kind,
      product,
      body: noteBody(change),
      sourceUrl: change.sourceUrl,
      members: [change],
    });
  }
  return clusters;
}

function groupClustersByDate(
  clusters: ChangeCluster[],
): { dateKey: string; label: string; clusters: ChangeCluster[] }[] {
  const groups: { dateKey: string; label: string; clusters: ChangeCluster[] }[] = [];
  const seen = new Map<string, number>();
  for (const cluster of clusters) {
    const at = seen.get(cluster.dateKey);
    if (at !== undefined) {
      groups[at].clusters.push(cluster);
      continue;
    }
    seen.set(cluster.dateKey, groups.length);
    groups.push({
      dateKey: cluster.dateKey,
      label: formatDayHeading(cluster.date),
      clusters: [cluster],
    });
  }
  return groups;
}

const KIND_TONE: Record<ChangeKind, string> = {
  deprecation: "text-red-400",
  replacement: "text-amber-400",
  new_identifier: "text-emerald-500",
  breaking_change: "text-red-400",
  feature: "text-emerald-500",
  fix: "text-sky-400",
  issue: "text-amber-400",
  security: "text-red-400",
  announcement: "text-[var(--text-secondary)]",
  change: "text-[var(--text-secondary)]",
  libraries: "text-sky-400",
  other: "text-[var(--text-secondary)]",
};

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

type TimePreset = "7d" | "30d" | "90d" | "all" | "custom";

const TIME_PRESETS: { id: Exclude<TimePreset, "custom">; label: string }[] = [
  { id: "7d", label: "7d" },
  { id: "30d", label: "30d" },
  { id: "90d", label: "90d" },
  { id: "all", label: "All" },
];

const FEATURED_KINDS: ChangeKind[] = [
  "feature",
  "breaking_change",
  "deprecation",
  "security",
  "fix",
];

const MORE_KINDS = (Object.keys(CHANGE_KIND_LABELS) as ChangeKind[]).filter(
  (kind) => !FEATURED_KINDS.includes(kind),
);

const SNAPSHOT_DAYS = 365;

function isoDay(date: Date): string {
  return format(date, "yyyy-MM-dd");
}

function presetBounds(preset: "7d" | "30d" | "90d"): { since: string; until: string } {
  const until = startOfDay(new Date());
  const back = preset === "7d" ? 6 : preset === "30d" ? 29 : 89;
  return { since: isoDay(subDays(until, back)), until: isoDay(until) };
}

function resolveTimeWindow(
  preset: TimePreset,
  custom: DateRange | undefined,
): { since?: string; until?: string; label: string } {
  if (preset === "custom" && custom?.from) {
    const since = isoDay(custom.from);
    const until = isoDay(custom.to ?? custom.from);
    const fromLabel = format(custom.from, "MMM d");
    const toLabel = format(custom.to ?? custom.from, "MMM d");
    return {
      since,
      until,
      label: since === until ? fromLabel : `${fromLabel} – ${toLabel}`,
    };
  }
  if (preset === "7d" || preset === "30d" || preset === "90d") {
    const bounds = presetBounds(preset);
    return {
      ...bounds,
      label: preset === "7d" ? "last 7 days" : preset === "30d" ? "last 30 days" : "last 90 days",
    };
  }
  return { label: "all time" };
}

function calendarSelection(preset: TimePreset, custom: DateRange | undefined): DateRange | undefined {
  if (preset === "custom") return custom;
  if (preset === "7d" || preset === "30d" || preset === "90d") {
    const bounds = presetBounds(preset);
    return { from: new Date(`${bounds.since}T00:00:00`), to: new Date(`${bounds.until}T00:00:00`) };
  }
  return undefined;
}

function matchesChangeFilter(
  change: PublishedChange,
  q: string,
  kind: ChangeKind | "all",
  since?: string,
  until?: string,
): boolean {
  if (kind !== "all" && change.kind !== kind) return false;
  const day = change.effectiveAt.slice(0, 10);
  if (since && day < since) return false;
  if (until && day > until) return false;
  if (!q) return true;
  return (
    change.title.toLowerCase().includes(q) ||
    (change.product || "").toLowerCase().includes(q) ||
    (change.summary || "").toLowerCase().includes(q) ||
    change.serviceId.toLowerCase().includes(q)
  );
}

function FilterChip({
  active,
  onClick,
  children,
  className,
  tone = "track",
}: {
  active?: boolean;
  onClick: () => void;
  children: ReactNode;
  className?: string;
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
        className,
      )}
    >
      {children}
    </button>
  );
}

function ChangesTab({
  slug,
  connection,
  onConnectionChange,
}: {
  slug: string;
  connection: ProviderConnection | null;
  onConnectionChange: () => void;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [kindFilter, setKindFilter] = useState<ChangeKind | "all">("all");
  const [timePreset, setTimePreset] = useState<TimePreset>("30d");
  const [customRange, setCustomRange] = useState<DateRange | undefined>();
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [changes, setChanges] = useState<PublishedChange[]>([]);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const timeWindow = useMemo(
    () => resolveTimeWindow(timePreset, customRange),
    [customRange, timePreset],
  );
  const selectedRange = calendarSelection(timePreset, customRange);
  const moreKindActive = kindFilter !== "all" && MORE_KINDS.includes(kindFilter);
  const atDefaults =
    !searchQuery && kindFilter === "all" && timePreset === "30d" && !customRange?.from;

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedQuery(searchQuery.trim()), 250);
    return () => window.clearTimeout(handle);
  }, [searchQuery]);

  useEffect(() => {
    setPage(1);
  }, [debouncedQuery, kindFilter, timeWindow.since, timeWindow.until]);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({
      limit: String(CHANGE_PAGE_SIZE),
      offset: String((page - 1) * CHANGE_PAGE_SIZE),
    });
    if (debouncedQuery) params.set("q", debouncedQuery);
    if (kindFilter !== "all") params.set("kind", kindFilter);
    if (timeWindow.since) params.set("since", timeWindow.since);
    if (timeWindow.until) params.set("until", timeWindow.until);
    setLoading(true);
    setError(null);
    void fetch(`${API_URL}/api/providers/${encodeURIComponent(slug)}/changes?${params}`, {
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
        const nextTotal = typeof body?.total === "number" ? body.total : mapped.length;
        setTotal(nextTotal);
        setChanges(mapped);
        listRef.current?.scrollTo({ top: 0 });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Could not load release notes");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [debouncedQuery, kindFilter, page, reload, slug, timeWindow.since, timeWindow.until, connection?.status]);

  const totalPages = Math.max(1, Math.ceil(total / CHANGE_PAGE_SIZE));

  const q = debouncedQuery.toLowerCase();
  const filtered = useMemo(
    () => changes.filter((change) => matchesChangeFilter(change, q, kindFilter, timeWindow.since, timeWindow.until)),
    [changes, kindFilter, q, timeWindow.since, timeWindow.until],
  );

  const datedClusters = useMemo(
    () => groupClustersByDate(clusterChanges(filtered)),
    [filtered],
  );

  const resetFilters = () => {
    setSearchQuery("");
    setDebouncedQuery("");
    setKindFilter("all");
    setTimePreset("30d");
    setCustomRange(undefined);
    setCalendarOpen(false);
    setMoreOpen(false);
  };

  return (
    <div className="h-full flex flex-col bg-[var(--bg-primary)]">
      <div className="border-b border-[var(--border-color)] px-4 pt-4 pb-3 space-y-3">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-secondary)]" />
            <Input
              placeholder="Search GKE, BigQuery, deprecations…"
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
          <ConnectionChip connection={connection} onClick={() => setSourceOpen(true)} />
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
              When
            </span>
            <div className="inline-flex items-center rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] p-0.5">
              {TIME_PRESETS.map((preset) => (
                <FilterChip
                  key={preset.id}
                  active={timePreset === preset.id}
                  onClick={() => {
                    setTimePreset(preset.id);
                    setCustomRange(undefined);
                    setCalendarOpen(false);
                  }}
                >
                  {preset.label}
                </FilterChip>
              ))}
              <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
                <PopoverTrigger asChild>
                  <button
                    type="button"
                    className={cn(
                      "h-7 inline-flex items-center gap-1.5 px-2.5 rounded-md text-[11px] font-medium transition-colors",
                      timePreset === "custom"
                        ? "bg-[var(--bg-primary)] text-[var(--text-primary)] shadow-sm"
                        : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-primary)]/70",
                    )}
                  >
                    <CalendarDays className="h-3 w-3" />
                    {timePreset === "custom" ? timeWindow.label : "Range"}
                  </button>
                </PopoverTrigger>
                <PopoverContent
                  align="start"
                  className="z-[200] w-fit p-3 border-[var(--border-color)] bg-[var(--bg-primary)] text-[var(--text-primary)]"
                >
                  <div className="px-1 pb-2">
                    <p className="text-xs font-medium text-[var(--text-primary)]">Published date</p>
                    <p className="text-[11px] text-[var(--text-secondary)] mt-0.5">
                      Pick a start and end day.
                    </p>
                  </div>
                  <Calendar
                    mode="range"
                    selected={selectedRange}
                    onSelect={(range) => {
                      setCustomRange(range);
                      if (range?.from) setTimePreset("custom");
                    }}
                    defaultMonth={selectedRange?.from}
                    disabled={{
                      after: new Date(),
                      before: subDays(new Date(), SNAPSHOT_DAYS),
                    }}
                    className="bg-transparent p-0 w-fit [--cell-size:2.25rem]"
                    classNames={{
                      root: "w-fit",
                      months: "relative flex w-fit flex-col",
                      month: "flex w-fit flex-col gap-3",
                      weekdays: "flex w-fit",
                      weekday:
                        "size-[--cell-size] text-[0.7rem] font-normal text-[var(--text-secondary)]",
                      week: "mt-1 flex w-fit",
                      day: "size-[--cell-size] p-0",
                    }}
                  />
                  <div className="flex items-center justify-between px-1 pt-2">
                    <p className="text-[11px] text-[var(--text-secondary)]">
                      {timePreset === "custom" && customRange?.from
                        ? timeWindow.label
                        : "Last 365 days available"}
                    </p>
                    {timePreset === "custom" && (
                      <button
                        type="button"
                        onClick={() => {
                          setTimePreset("30d");
                          setCustomRange(undefined);
                          setCalendarOpen(false);
                        }}
                        className="text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      >
                        Reset
                      </button>
                    )}
                  </div>
                </PopoverContent>
              </Popover>
            </div>
          </div>

          <div className="hidden sm:block h-5 w-px bg-[var(--border-color)]" />

          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
              Type
            </span>
            <div className="inline-flex flex-wrap items-center gap-1">
              <FilterChip
                tone="pill"
                active={kindFilter === "all"}
                onClick={() => setKindFilter("all")}
              >
                All
              </FilterChip>
              {FEATURED_KINDS.map((kind) => (
                <FilterChip
                  key={kind}
                  tone="pill"
                  active={kindFilter === kind}
                  onClick={() => setKindFilter(kindFilter === kind ? "all" : kind)}
                >
                  <span className={cn("h-1.5 w-1.5 rounded-full", KIND_DOT[kind])} />
                  <span className={cn(kindFilter === kind && KIND_TONE[kind])}>
                    {kind === "breaking_change" ? "Breaking" : CHANGE_KIND_LABELS[kind]}
                  </span>
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
                  align="end"
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
        </div>

        <div className="flex items-center justify-between gap-3">
          <p className="text-[11px] text-[var(--text-secondary)]">
            {loading && filtered.length === 0
              ? "Loading notes…"
              : `${total.toLocaleString()} ${total === 1 ? "note" : "notes"}`}
            {!loading && (
              <>
                <span className="mx-1.5 text-[var(--border-color)]">·</span>
                {timeWindow.label}
                {kindFilter !== "all" && (
                  <>
                    <span className="mx-1.5 text-[var(--border-color)]">·</span>
                    {CHANGE_KIND_LABELS[kindFilter].toLowerCase()}
                  </>
                )}
              </>
            )}
          </p>
          {!atDefaults && (
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

      <div ref={listRef} className="flex-1 overflow-y-auto p-4">
        <div className="max-w-3xl mx-auto space-y-6">
          {loading && datedClusters.length === 0 ? (
            <div className="flex items-center justify-center gap-2 py-10 text-xs text-[var(--text-secondary)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading release notes…
            </div>
          ) : error && datedClusters.length === 0 ? (
            <div className="text-center py-10">
              <p className="text-xs text-[var(--text-secondary)] mb-3">{error}</p>
              <Button
                size="sm"
                onClick={() => setReload((count) => count + 1)}
                className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
              >
                Retry
              </Button>
            </div>
          ) : datedClusters.length === 0 ? (
            <p className="text-xs text-[var(--text-secondary)] text-center py-10">
              No release notes match that filter.
            </p>
          ) : (
            datedClusters.map((group) => (
              <section key={group.dateKey}>
                <h3 className="sticky top-0 z-10 -mx-1 px-1 py-1.5 text-[11px] font-medium text-[var(--text-secondary)] bg-[var(--bg-primary)]/95 backdrop-blur-sm">
                  {group.label}
                </h3>
                <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg overflow-hidden">
                  {group.clusters.map((cluster) => (
                    <ChangeClusterRow key={cluster.id} cluster={cluster} />
                  ))}
                </div>
              </section>
            ))
          )}
        </div>
      </div>

      {totalPages > 1 && (
        <div className="flex-shrink-0 border-t border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-2">
          <Pagination>
            <PaginationContent className="gap-0.5">
              <PaginationItem>
                <PaginationPrevious
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
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
                      onClick={() => setPage(item)}
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
                  onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
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

      <ConnectionDialog
        open={sourceOpen}
        onOpenChange={setSourceOpen}
        kind="changes"
        connection={connection}
        pending={sourceBusy}
        error={sourceError}
        onConnect={async (url) => {
          setSourceBusy(true);
          setSourceError(null);
          try {
            await connectProvider(slug, "changes", url);
            onConnectionChange();
            setReload((value) => value + 1);
          } catch (err) {
            setSourceError(err instanceof Error ? err.message : "Could not connect");
          } finally {
            setSourceBusy(false);
          }
        }}
        onDisconnect={async () => {
          setSourceBusy(true);
          setSourceError(null);
          try {
            await disconnectProvider(slug, "changes");
            onConnectionChange();
            setReload((value) => value + 1);
            setSourceOpen(false);
          } catch (err) {
            setSourceError(err instanceof Error ? err.message : "Could not disconnect");
          } finally {
            setSourceBusy(false);
          }
        }}
      />
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

  const host = profile.website ? profile.website.replace(/^https?:\/\//, "") : "";

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
                    {CATEGORY_LABELS[asProviderCategory(profile.category)]}
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
          {host && profile.website && (
            <DetailRow icon={Globe} label="Website" value={host} href={profile.website} />
          )}
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
          {profile.contactUrl ? (
            <DetailRow
              icon={Mail}
              label="Contact"
              value={profile.contactUrl.replace(/^https?:\/\//, "")}
              href={profile.contactUrl}
            />
          ) : (
            profile.contactEmail && (
              <DetailRow
                icon={Mail}
                label="Contact"
                value={profile.contactEmail}
                href={`mailto:${profile.contactEmail}`}
              />
            )
          )}
          {profile.hq && <DetailRow icon={MapPin} label="Headquarters" value={profile.hq} />}
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
            { n: "2", title: "Connect a catalog URL", desc: "Paste a Service Usage link. Services are imported from that endpoint." },
            { n: "3", title: "Connect a changes URL", desc: "Paste a BigQuery or release-notes link. Project and table are read from it." },
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
  onRegister: (input: RegisterProviderInput) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [slugError, setSlugError] = useState<string | null>(null);
  const [slugChecking, setSlugChecking] = useState(false);
  const [website, setWebsite] = useState("");
  const [consoleUrl, setConsoleUrl] = useState("");
  const [docsUrl, setDocsUrl] = useState("");
  const [statusUrl, setStatusUrl] = useState("");
  const [email, setEmail] = useState("");
  const [hq, setHq] = useState("");
  const [since, setSince] = useState("");
  const [category, setCategory] = useState<ProviderCategory>("ai");
  const [description, setDescription] = useState("");
  const [attested, setAttested] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setName("");
    setSlug("");
    setSlugTouched(false);
    setSlugError(null);
    setSlugChecking(false);
    setWebsite("");
    setConsoleUrl("");
    setDocsUrl("");
    setStatusUrl("");
    setEmail("");
    setHq("");
    setSince("");
    setCategory("ai");
    setDescription("");
    setAttested(false);
    setError(null);
  };

  useEffect(() => {
    if (!open) return;
    const next = slugify(slug);
    if (!next) {
      setSlugError(null);
      setSlugChecking(false);
      return;
    }
    if (next.length < 3) {
      setSlugError("Slug must be at least 3 characters");
      setSlugChecking(false);
      return;
    }
    if (!/^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(next)) {
      setSlugError("Slug must start and end with a letter or number");
      setSlugChecking(false);
      return;
    }
    if (/--/.test(next)) {
      setSlugError("Slug cannot contain consecutive hyphens");
      setSlugChecking(false);
      return;
    }
    const timer = window.setTimeout(async () => {
      setSlugChecking(true);
      try {
        const result = await checkProviderSlug(next);
        setSlugError(result.available ? null : result.message || "This slug is already taken");
      } catch {
        setSlugError(null);
      } finally {
        setSlugChecking(false);
      }
    }, 500);
    return () => window.clearTimeout(timer);
  }, [open, slug]);

  const handleSubmit = async () => {
    if (!name.trim()) return setError("Enter an organization name.");
    if (!slugify(slug) || slugError || slugChecking) {
      return setError(slugError || "Enter a URL slug.");
    }
    if (email.trim() && email.includes(" ") && !email.includes("@")) {
      return setError("Enter a contact email or URL, or leave it blank.");
    }
    if (since.trim() && !/^\d{4}$/.test(since.trim())) {
      return setError("Since must be a four-digit year, or leave it blank.");
    }
    if (!description.trim()) return setError("Describe what you publish.");
    if (!attested) return setError("Confirm the trust boundary before registering.");
    setError(null);
    try {
      await onRegister({
        name: name.trim(),
        slug: slugify(slug),
        website: website.trim(),
        contact_email: email.includes("@") ? email.trim() : "",
        contact_url: email.includes("@") ? "" : email.trim(),
        category,
        description: description.trim(),
        hq: hq.trim(),
        since: since.trim(),
        console_url: consoleUrl.trim(),
        docs_url: docsUrl.trim(),
        status_url: statusUrl.trim(),
        attested: true,
      });
      reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not register.");
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) reset();
      }}
    >
      <DialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)] max-w-xl max-h-[90vh] flex flex-col gap-0 overflow-hidden p-0 sm:max-w-xl">
        <div className="shrink-0 px-6 pt-6 pb-4 border-b border-[var(--border-color)]">
          <DialogHeader className="space-y-0 text-left">
            <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
              Register as provider
            </DialogTitle>
            <DialogDescription className="text-xs text-[var(--text-secondary)] leading-relaxed pt-2">
              Public profile for this publisher. Organization, slug, category, and
              description are required.
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto px-6 py-5 space-y-5">
          <div className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-primary)] p-5 space-y-4">
            <Field label="Organization">
              <HintInput
                value={name}
                hint="Google Cloud"
                onValueChange={(next) => {
                  setName(next);
                  if (!slugTouched) setSlug(slugify(next));
                }}
                className={fieldClass}
              />
            </Field>
            <Field label="Slug">
              <div className="flex items-center">
                <span className="text-xs text-[var(--text-secondary)] px-3 py-2 bg-[var(--bg-tertiary)] border border-r-0 border-[var(--border-color)] rounded-l-md h-9 flex items-center">
                  providers/
                </span>
                <Input
                  value={slug}
                  onChange={(e) => {
                    setSlugTouched(true);
                    setSlug(sanitizeSlugInput(e.target.value));
                  }}
                  placeholder="slug"
                  className={cn(
                    fieldClass,
                    "font-mono rounded-l-none",
                    slugError && "border-red-500 focus-visible:border-red-500",
                  )}
                />
              </div>
              {slugChecking && (
                <p className="text-[10px] text-[var(--text-secondary)] flex items-center gap-1">
                  <Spinner className="h-3 w-3" />
                  Checking availability
                </p>
              )}
              {slugError && !slugChecking && (
                <p className="text-[10px] text-red-500">{slugError}</p>
              )}
              {!slugError && !slugChecking && slugify(slug).length >= 3 && (
                <p className="text-[10px] text-[#10b981] flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#10b981]" />
                  Slug is available
                </p>
              )}
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Category">
                <Select value={category} onValueChange={(v) => setCategory(v as ProviderCategory)}>
                  <SelectTrigger className={selectTriggerClass}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent
                    position="popper"
                    align="start"
                    side="bottom"
                    sideOffset={4}
                    className={cn(selectContentClass, "w-[var(--radix-select-trigger-width)]")}
                  >
                    {(Object.keys(CATEGORY_LABELS) as ProviderCategory[]).map((key) => (
                      <SelectItem key={key} value={key} className={selectItemClass}>
                        {CATEGORY_LABELS[key]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Since">
                <HintInput
                  value={since}
                  hint="2008"
                  onValueChange={(next) => setSince(next.replace(/\D/g, "").slice(0, 4))}
                  inputMode="numeric"
                  className={fieldClass}
                />
              </Field>
            </div>
            <Field label="Description">
              <HintTextarea
                value={description}
                hint="A suite of cloud services for compute, storage, data analytics, and machine learning."
                onValueChange={setDescription}
                className={textareaClass}
              />
            </Field>
          </div>

          <div className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-primary)] divide-y divide-[var(--border-color)]">
            <LinkRow icon={Globe} label="Website">
              <HintInput
                value={website}
                hint="cloud.google.com"
                onValueChange={setWebsite}
                className={rowInputClass}
              />
            </LinkRow>
            <LinkRow icon={ExternalLink} label="Console">
              <HintInput
                value={consoleUrl}
                hint="console.cloud.google.com"
                onValueChange={setConsoleUrl}
                className={rowInputClass}
              />
            </LinkRow>
            <LinkRow icon={Layers} label="Docs">
              <HintInput
                value={docsUrl}
                hint="cloud.google.com/docs"
                onValueChange={setDocsUrl}
                className={rowInputClass}
              />
            </LinkRow>
            <LinkRow icon={Eye} label="Status">
              <HintInput
                value={statusUrl}
                hint="status.cloud.google.com"
                onValueChange={setStatusUrl}
                className={rowInputClass}
              />
            </LinkRow>
            <LinkRow icon={Mail} label="Contact">
              <HintInput
                value={email}
                hint="cloud.google.com/contact"
                onValueChange={setEmail}
                className={rowInputClass}
              />
            </LinkRow>
            <LinkRow icon={MapPin} label="Headquarters">
              <HintInput
                value={hq}
                hint="1600 Amphitheatre Parkway, Mountain View, CA"
                onValueChange={setHq}
                className={rowInputClass}
              />
            </LinkRow>
          </div>

          <label className="flex items-start gap-2.5 rounded-xl border border-[var(--border-color)] bg-[var(--bg-secondary)] px-4 py-3 cursor-pointer">
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

        <DialogFooter className="shrink-0 border-t border-[var(--border-color)] bg-[var(--bg-primary)] px-6 py-4 gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            className={cn("h-8 text-xs", outlineMutedButtonClass)}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!!slugError || slugChecking}
            className="h-8 text-xs bg-primary hover:bg-primary-hover text-primary-foreground disabled:opacity-50"
          >
            Register
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ChangeClusterRow({ cluster }: { cluster: ChangeCluster }) {
  const [open, setOpen] = useState(false);
  const variants = cluster.members
    .map((member) => variantLabel(member.product || member.serviceId, cluster.product))
    .filter((label, index, all) => label && all.indexOf(label) === index);
  const count = cluster.members.length;

  return (
    <div className="border-b border-[var(--border-color)] last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="w-full text-left p-3 hover:bg-[var(--bg-tertiary)] transition-colors"
      >
        <div className="flex items-start gap-3">
          <Image
            src={getGCPServiceIcon(cluster.product)}
            alt=""
            width={20}
            height={20}
            className="h-5 w-5 object-contain mt-0.5 flex-shrink-0"
          />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-sm font-medium text-[var(--text-primary)] truncate">
                {cluster.product}
              </span>
              <span className={cn("text-[10px] font-medium flex-shrink-0", KIND_TONE[cluster.kind])}>
                {CHANGE_KIND_LABELS[cluster.kind]}
              </span>
              {count > 1 && (
                <span className="text-[10px] text-[var(--text-secondary)] flex-shrink-0">
                  {count}
                </span>
              )}
            </div>
            <p
              className={cn(
                "mt-1 text-xs text-[var(--text-secondary)] leading-relaxed",
                !open && "line-clamp-2",
              )}
            >
              {cluster.body}
            </p>
          </div>
          {open ? (
            <ChevronDown className="h-4 w-4 text-[var(--text-secondary)] mt-0.5 flex-shrink-0" />
          ) : (
            <ChevronRight className="h-4 w-4 text-[var(--text-secondary)] mt-0.5 flex-shrink-0" />
          )}
        </div>
      </button>
      {open && (variants.length > 1 || cluster.sourceUrl) && (
        <div className="px-3 pb-3 pl-11">
          {variants.length > 1 && (
            <div className="flex flex-wrap gap-1.5">
              {variants.map((label) => (
                <span
                  key={label}
                  className="rounded-md border border-[var(--border-color)] bg-[var(--bg-primary)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]"
                >
                  {label}
                </span>
              ))}
            </div>
          )}
          {cluster.sourceUrl && (
            <a
              href={cluster.sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-0.5 mt-2 text-[10px] text-[var(--text-secondary)] hover:text-primary transition-colors"
            >
              Source
              <ArrowUpRight className="h-3 w-3" />
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function canAcceptHint(value: string, hint: string): boolean {
  const current = value.trim();
  if (!hint) return false;
  if (current.toLowerCase() === hint.toLowerCase()) return false;
  return current.length === 0 || hint.toLowerCase().startsWith(current.toLowerCase());
}

function acceptHintKey(
  event: KeyboardEvent<HTMLElement>,
  value: string,
  hint: string,
  fill: (next: string) => void,
) {
  if (event.key !== "Tab" || event.shiftKey || event.altKey || event.metaKey) return;
  if (!canAcceptHint(value, hint)) return;
  event.preventDefault();
  event.stopPropagation();
  event.nativeEvent.stopImmediatePropagation();
  fill(hint);
}

function HintInput({
  value,
  hint,
  onValueChange,
  className,
  ...props
}: Omit<ComponentProps<typeof Input>, "value" | "onChange" | "placeholder"> & {
  value: string;
  hint: string;
  onValueChange: (next: string) => void;
}) {
  return (
    <Input
      {...props}
      value={value}
      placeholder={hint}
      onChange={(event) => onValueChange(event.target.value)}
      onKeyDownCapture={(event) => acceptHintKey(event, value, hint, onValueChange)}
      className={className}
    />
  );
}

function HintTextarea({
  value,
  hint,
  onValueChange,
  className,
}: {
  value: string;
  hint: string;
  onValueChange: (next: string) => void;
  className?: string;
}) {
  return (
    <Textarea
      value={value}
      placeholder={hint}
      onChange={(event) => onValueChange(event.target.value)}
      onKeyDownCapture={(event) => acceptHintKey(event, value, hint, onValueChange)}
      className={className}
    />
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-1.5 min-w-0">
      <Label className="text-xs text-[var(--text-secondary)]">{label}</Label>
      {children}
    </div>
  );
}

function LinkRow({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof Globe;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-4 px-4 py-3">
      <span className="inline-flex items-center gap-2 w-32 shrink-0 text-xs text-[var(--text-secondary)]">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

