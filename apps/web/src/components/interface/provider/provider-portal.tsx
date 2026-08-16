"use client";

import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  Clock3,
  Eye,
  FilePlus2,
  Info,
  Layers,
  Link2,
  Plus,
} from "lucide-react";
import {
  CATEGORY_LABELS,
  CHANGE_KIND_LABELS,
  GOOGLE_CLOUD_CHANGES,
  GOOGLE_CLOUD_PROVIDER,
  GOOGLE_CLOUD_SERVICES,
  SERVICE_STATUS_LABELS,
  daysUntil,
  formatShortDate,
  formatWatchers,
  initials,
  slugify,
  type ChangeKind,
  type ProviderCategory,
  type ProviderProfile,
  type PublishedChange,
  type PublishedService,
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

export function ProviderPortal() {
  const [profile, setProfile] = useState<ProviderProfile | null>(null);
  const [services, setServices] = useState<PublishedService[]>([]);
  const [changes, setChanges] = useState<PublishedChange[]>([]);
  const [tab, setTab] = useState("services");
  const [showRegister, setShowRegister] = useState(false);
  const [showHowItWorks, setShowHowItWorks] = useState(false);
  const [publishServiceOpen, setPublishServiceOpen] = useState(false);
  const [publishChangeOpen, setPublishChangeOpen] = useState(false);
  const [selectedService, setSelectedService] = useState<PublishedService | null>(null);

  const openCatalog = () => {
    setProfile(GOOGLE_CLOUD_PROVIDER);
    setServices(GOOGLE_CLOUD_SERVICES);
    setChanges(GOOGLE_CLOUD_CHANGES);
    setTab("services");
    setShowRegister(false);
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
                className="border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
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
            <TabsTrigger value="services" className={cn(tabTriggerClass, "relative")}>
              <Layers className="w-3 h-3 mr-2" />
              Services
              {services.length > 0 && (
                <span className="ml-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 text-[9px] text-white font-bold px-1">
                  {services.length}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="changes" className={cn(tabTriggerClass, "relative")}>
              <FilePlus2 className="w-3 h-3 mr-2" />
              Changes
              {changes.length > 0 && (
                <span className="ml-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 text-[9px] text-white font-bold px-1">
                  {changes.length}
                </span>
              )}
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
            onPublish={() => setPublishServiceOpen(true)}
            onSelect={setSelectedService}
          />
        </TabsContent>

        <TabsContent value="changes" className="flex-1 m-0 p-0 overflow-hidden">
          <ChangesTab
            changes={changes}
            services={services}
            onPublish={() => setPublishChangeOpen(true)}
          />
        </TabsContent>

        <TabsContent value="profile" className="flex-1 m-0 p-0 overflow-hidden">
          <ProfileTab profile={profile} serviceCount={services.length} onLeave={leaveProvider} />
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
      <ServiceDetailDialog
        service={selectedService}
        changes={changes}
        onOpenChange={(open) => {
          if (!open) setSelectedService(null);
        }}
      />
    </>
  );
}

function ServicesTab({
  services,
  onPublish,
  onSelect,
}: {
  services: PublishedService[];
  onPublish: () => void;
  onSelect: (service: PublishedService) => void;
}) {
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
    <div className="h-full overflow-y-auto bg-[var(--bg-secondary)]">
      <div className="max-w-5xl mx-auto px-6 py-6">
        <div className="flex items-center justify-end mb-4">
          <Button
            onClick={onPublish}
            className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            <Plus className="h-3.5 w-3.5 mr-1" />
            Publish service
          </Button>
        </div>
        <div className="grid md:grid-cols-2 gap-3">
          {services.map((service) => (
            <button
              key={service.id}
              type="button"
              onClick={() => onSelect(service)}
              className="text-left rounded-xl border border-[var(--border-color)] bg-[var(--bg-primary)] p-4 hover:border-primary/40 transition-colors group"
            >
              <div className="flex items-start justify-between gap-3 mb-2">
                <div>
                  <p className="text-sm font-semibold text-[var(--text-primary)] group-hover:text-primary transition-colors">
                    {service.name}
                  </p>
                  <p className="font-mono text-[10px] text-[var(--text-secondary)] mt-0.5">
                    {service.slug}
                  </p>
                </div>
                <StatusPill status={service.status} />
              </div>
              <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed mb-3 line-clamp-2">
                {service.summary}
              </p>
              <div className="flex flex-wrap gap-1.5 mb-3">
                {service.identifiers.slice(0, 2).map((id) => (
                  <span
                    key={id}
                    className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-secondary)] border border-[var(--border-color)] text-[var(--text-secondary)]"
                  >
                    {id}
                  </span>
                ))}
                {service.identifiers.length > 2 && (
                  <span className="text-[10px] text-[var(--text-secondary)] px-1">
                    +{service.identifiers.length - 2}
                  </span>
                )}
              </div>
              <div className="flex items-center justify-between text-[10px] text-[var(--text-secondary)]">
                <span className="inline-flex items-center gap-1">
                  <Eye className="h-3 w-3" />
                  {formatWatchers(service.watchers)} watching
                </span>
                <span>Updated {formatShortDate(service.lastPublishedAt)}</span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function ChangesTab({
  changes,
  services,
  onPublish,
}: {
  changes: PublishedChange[];
  services: PublishedService[];
  onPublish: () => void;
}) {
  const serviceName = (id: string) => services.find((s) => s.id === id)?.name ?? "Service";

  if (changes.length === 0) {
    return (
      <TabEmpty
        icon={FilePlus2}
        title="No change events"
        body="Announce a deprecation or replacement for one of your services. PatchAPI treats every claim as untrusted input."
        actionLabel="Publish change"
        onAction={onPublish}
        actionDisabled={services.length === 0}
        actionHint={services.length === 0 ? "Publish a service first." : undefined}
      />
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[var(--bg-secondary)]">
      <div className="max-w-5xl mx-auto px-6 py-6">
        <div className="flex items-center justify-end mb-4">
          <Button
            onClick={onPublish}
            disabled={services.length === 0}
            className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground disabled:opacity-40"
          >
            <Plus className="h-3.5 w-3.5 mr-1" />
            Publish change
          </Button>
        </div>
        <div className="space-y-3">
          {changes.map((change) => (
            <div
              key={change.id}
              className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-primary)] p-4"
            >
              <ChangeRow change={change} serviceName={serviceName(change.serviceId)} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ProfileTab({
  profile,
  serviceCount,
  onLeave,
}: {
  profile: ProviderProfile;
  serviceCount: number;
  onLeave: () => void;
}) {
  return (
    <div className="h-full overflow-y-auto bg-[var(--bg-secondary)]">
      <div className="max-w-xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-start gap-3">
          <div className="h-11 w-11 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-sm font-semibold text-primary flex-shrink-0">
            {initials(profile.name)}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">{profile.name}</h2>
              {profile.verified ? (
                <span className="inline-flex items-center gap-1 text-[10px] text-emerald-500">
                  <BadgeCheck className="h-3 w-3" />
                  Verified
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-[10px] text-amber-500">
                  <Clock3 className="h-3 w-3" />
                  Review pending
                </span>
              )}
            </div>
            <p className="text-[11px] text-[var(--text-secondary)] mt-0.5">
              <span className="font-mono">{profile.slug}</span>
              <span className="mx-1.5">·</span>
              {CATEGORY_LABELS[profile.category]}
              <span className="mx-1.5">·</span>
              {serviceCount} {serviceCount === 1 ? "service" : "services"}
            </p>
            <p className="text-xs text-[var(--text-secondary)] leading-relaxed mt-2">
              {profile.description}
            </p>
          </div>
        </div>

        <div className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-primary)] divide-y divide-[var(--border-color)]">
          <ProfileRow label="Website" value={profile.website.replace(/^https?:\/\//, "")} />
          <ProfileRow label="Contact" value={profile.contactEmail} />
          <ProfileRow label="Watching orgs" value={formatWatchers(profile.watchingOrgs)} />
          <ProfileRow label="Registered" value={formatShortDate(profile.registeredAt)} />
        </div>

        <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
          Provider material is untrusted input. Registering does not grant access to
          customer repositories, secrets, or merge rights.
        </p>

        <Button
          variant="outline"
          onClick={onLeave}
          className="h-8 text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
        >
          Leave catalog
        </Button>
      </div>
    </div>
  );
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
            className="h-7 text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
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
    onPublish({
      id: `svc_${slugify(slug || name)}_${Date.now()}`,
      name: name.trim(),
      slug: slugify(slug || name),
      summary: summary.trim() || "Published service. Identifiers are available for inventory.",
      status,
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
            className="h-7 text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
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
                  {(Object.keys(CHANGE_KIND_LABELS) as ChangeKind[]).map((key) => (
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
            className="h-7 text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
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

function ServiceDetailDialog({
  service,
  changes,
  onOpenChange,
}: {
  service: PublishedService | null;
  changes: PublishedChange[];
  onOpenChange: (open: boolean) => void;
}) {
  const related = useMemo(
    () => (service ? changes.filter((c) => c.serviceId === service.id) : []),
    [service, changes],
  );

  return (
    <Dialog open={!!service} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)] max-w-lg">
        {service && (
          <>
            <DialogHeader>
              <div className="flex items-center gap-2 mb-1">
                <StatusPill status={service.status} />
              </div>
              <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
                {service.name}
              </DialogTitle>
              <DialogDescription className="text-xs text-[var(--text-secondary)] leading-relaxed">
                {service.summary}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-1">
              <div>
                <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)] mb-2">
                  Identifiers
                </p>
                <div className="space-y-1.5">
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
              <div className="flex items-center justify-between text-[11px] text-[var(--text-secondary)]">
                <span className="inline-flex items-center gap-1">
                  <Eye className="h-3 w-3" />
                  {formatWatchers(service.watchers)} watching
                </span>
                <a
                  href={service.docsUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 hover:text-primary transition-colors"
                >
                  Docs
                  <ArrowUpRight className="h-3 w-3" />
                </a>
              </div>
              {related.length > 0 && (
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)] mb-2">
                    Attached changes
                  </p>
                  <div className="space-y-2">
                    {related.map((change) => (
                      <p key={change.id} className="text-xs text-[var(--text-primary)]">
                        {change.title}
                      </p>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        )}
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
          Effective
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

function ProfileRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3">
      <span className="text-xs text-[var(--text-secondary)]">{label}</span>
      <span className="text-xs text-[var(--text-primary)] truncate">{value}</span>
    </div>
  );
}

function StatusPill({ status }: { status: ServiceStatus }) {
  const styles: Record<ServiceStatus, string> = {
    live: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    preview: "text-amber-400 bg-amber-500/10 border-amber-500/20",
    deprecated: "text-red-400 bg-red-500/10 border-red-500/20",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium",
        styles[status],
      )}
    >
      {SERVICE_STATUS_LABELS[status]}
    </span>
  );
}

function KindPill({ kind }: { kind: ChangeKind }) {
  const styles: Record<ChangeKind, string> = {
    deprecation: "text-red-400 bg-red-500/10 border-red-500/20",
    replacement: "text-amber-400 bg-amber-500/10 border-amber-500/20",
    new_identifier: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    breaking_change: "text-red-400 bg-red-500/10 border-red-500/20",
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
