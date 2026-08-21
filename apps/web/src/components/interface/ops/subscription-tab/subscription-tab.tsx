"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getGCPServiceIcon } from "@/lib/gcp-icons";
import { CheckCircle2, Rss, Search, Store, Unplug } from "lucide-react";
import { SectionRail, SectionRailButton } from "@/components/interface/shared/section-rail";
import { MOCK_GOOGLE_OFFER, type MarketplaceOffer } from "./data";
import {
  MarketplaceEmptyState,
  NoProjectEmptyState,
  SubscribedEmptyState,
} from "./empty-states";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Section = "subscribed" | "marketplace";

function formatWatchingSince(iso?: string | null): string | undefined {
  if (!iso) return undefined;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return undefined;
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function offerFromProvider(row: Record<string, unknown>): MarketplaceOffer {
  return {
    id: String(row.slug ?? row.id ?? "google"),
    slug: String(row.slug ?? "google"),
    name: String(row.name ?? MOCK_GOOGLE_OFFER.name),
    provider: String(row.name ?? MOCK_GOOGLE_OFFER.provider),
    product: String(row.slug ?? MOCK_GOOGLE_OFFER.product),
    description: String(row.description ?? MOCK_GOOGLE_OFFER.description),
    category: String(row.category ?? MOCK_GOOGLE_OFFER.category),
    logoUrl: String(row.logo_url || row.logoUrl || MOCK_GOOGLE_OFFER.logoUrl || ""),
    subscribed: Boolean(row.subscribed),
    watchingSince: formatWatchingSince(
      typeof row.subscribed_at === "string" ? row.subscribed_at : undefined,
    ),
  };
}

export function SubscriptionTab({
  hasProject = true,
  projectId,
  onOpenChanges,
}: {
  hasProject?: boolean;
  projectId?: string;
  onOpenChanges?: () => void;
}) {
  const [section, setSection] = useState<Section>("marketplace");
  const [offers, setOffers] = useState<MarketplaceOffer[]>([MOCK_GOOGLE_OFFER]);
  const [query, setQuery] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [unsubscribeOpen, setUnsubscribeOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadOffers = useCallback(async (id: string) => {
    const response = await fetch(`${API_URL}/api/projects/${id}/providers`, {
      credentials: "include",
    });
    if (!response.ok) {
      throw new Error(`providers ${response.status}`);
    }
    const payload = (await response.json()) as { providers?: Record<string, unknown>[] };
    const next = (payload.providers ?? []).map(offerFromProvider);
    setOffers(next.length > 0 ? next : [MOCK_GOOGLE_OFFER]);
    if (next.some((offer) => offer.subscribed)) {
      setSection("subscribed");
    }
    return next;
  }, []);

  useEffect(() => {
    if (!hasProject || !projectId) return;
    void loadOffers(projectId).catch(() => {
      setOffers([MOCK_GOOGLE_OFFER]);
    });
  }, [hasProject, loadOffers, projectId]);

  const watching = offers.filter((offer) => offer.subscribed);
  const available = offers.filter((offer) => !offer.subscribed);

  const visible = useMemo(() => {
    const pool = section === "subscribed" ? watching : offers;
    const q = query.trim().toLowerCase();
    if (!q) return pool;
    return pool.filter(
      (offer) =>
        offer.name.toLowerCase().includes(q) ||
        offer.provider.toLowerCase().includes(q) ||
        offer.category.toLowerCase().includes(q) ||
        offer.description.toLowerCase().includes(q),
    );
  }, [offers, query, section, watching]);

  const confirmSubscribe = async () => {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/projects/${projectId}/providers/google`, {
        method: "PUT",
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(`subscribe ${response.status}`);
      }
      await loadOffers(projectId);
      setConfirmOpen(false);
      setSection("subscribed");
      onOpenChanges?.();
    } catch {
      setError("Could not subscribe. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const unsubscribe = async () => {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/projects/${projectId}/providers/google`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(`unsubscribe ${response.status}`);
      }
      await loadOffers(projectId);
      setUnsubscribeOpen(false);
      setSection("marketplace");
    } catch {
      setError("Could not unsubscribe. Try again.");
    } finally {
      setBusy(false);
    }
  };

  if (!hasProject) {
    return <NoProjectEmptyState />;
  }

  const poolEmpty = section === "subscribed" ? watching.length === 0 : offers.length === 0;

  return (
    <div className="h-full flex min-w-0 overflow-hidden bg-[var(--bg-primary)]">
      <SectionRail>
        <SectionRailButton
          active={section === "subscribed"}
          icon={Rss}
          label="Subscribed"
          count={watching.length > 0 ? watching.length : undefined}
          countTone="green"
          onClick={() => setSection("subscribed")}
        />
        <SectionRailButton
          active={section === "marketplace"}
          icon={Store}
          label="Marketplace"
          count={available.length > 0 ? available.length : undefined}
          countTone="muted"
          onClick={() => setSection("marketplace")}
        />
      </SectionRail>

      <div className="flex-1 min-w-0 overflow-y-auto">
        {poolEmpty && !query.trim() ? (
          section === "subscribed" ? (
            <SubscribedEmptyState onBrowse={() => setSection("marketplace")} />
          ) : (
            <MarketplaceEmptyState />
          )
        ) : (
          <div className="w-full mx-auto p-3 sm:p-4 md:p-6 space-y-4 sm:space-y-6">
            <div>
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                {section === "subscribed" ? "Subscribed" : "Marketplace"}
              </h2>
              <p className="mt-1 max-w-xl text-xs text-[var(--text-secondary)] leading-relaxed">
                {section === "subscribed"
                  ? "Providers this project watches for API and service releases."
                  : "Providers you can watch for API and service releases."}
              </p>
            </div>

            <div className="relative w-full">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-secondary)]" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={
                  section === "subscribed" ? "Search subscribed providers..." : "Search marketplace..."
                }
                className="h-8 w-full pl-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
              />
            </div>

            {visible.length === 0 ? (
              <p className="text-xs text-[var(--text-secondary)] py-10 text-center">
                No services match that search.
              </p>
            ) : (
              <div
                className="grid gap-3"
                style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 220px), 1fr))" }}
              >
                {visible.map((offer) => (
                  <OfferCard
                    key={offer.id}
                    offer={offer}
                    onSubscribe={() => setConfirmOpen(true)}
                    onUnsubscribe={() => setUnsubscribeOpen(true)}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)] sm:max-w-md">
          <AlertDialogHeader className="space-y-3 text-left">
            <AlertDialogTitle className="text-base text-[var(--text-primary)]">
              Subscribe
            </AlertDialogTitle>
            <div className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] px-3 py-2.5">
              <div className="flex items-center gap-2.5">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-[var(--border-color)] bg-[var(--bg-primary)]">
                  <Image
                    src={MOCK_GOOGLE_OFFER.logoUrl || getGCPServiceIcon("google cloud")}
                    alt=""
                    width={16}
                    height={16}
                    className="h-4 w-4 object-contain"
                  />
                </div>
                <p className="min-w-0 flex-1 truncate text-xs text-[var(--text-secondary)]">
                  Google Cloud
                  <span> · API and service releases</span>
                </p>
              </div>
            </div>
            <AlertDialogDescription className="text-xs leading-relaxed text-[var(--text-secondary)]">
              PatchAPI will scan this project for relevant Google Cloud usage. We will not change your repo.
            </AlertDialogDescription>
            {error && <p className="text-xs text-red-500">{error}</p>}
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-primary hover:bg-primary/90 text-primary-foreground"
              onClick={(event) => {
                event.preventDefault();
                void confirmSubscribe();
              }}
              disabled={busy}
            >
              {busy ? "Subscribing…" : "Subscribe"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={unsubscribeOpen} onOpenChange={setUnsubscribeOpen}>
        <AlertDialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-[var(--text-primary)]">
              Unsubscribe from Google Cloud?
            </AlertDialogTitle>
            <AlertDialogDescription className="text-[var(--text-secondary)] leading-relaxed">
              This project will stop watching Google Cloud for API and service releases.
              You can subscribe again anytime.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {error && <p className="px-6 text-xs text-red-500">{error}</p>}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-500 hover:bg-red-600 text-white focus:ring-red-500"
              onClick={(event) => {
                event.preventDefault();
                void unsubscribe();
              }}
              disabled={busy}
            >
              {busy ? "Unsubscribing…" : "Unsubscribe"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function OfferCard({
  offer,
  onSubscribe,
  onUnsubscribe,
}: {
  offer: MarketplaceOffer;
  onSubscribe: () => void;
  onUnsubscribe: () => void;
}) {
  return (
    <div className="group relative overflow-hidden bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg py-3 pl-3 pr-3 text-left sm:py-4 sm:pl-4 sm:pr-4 flex flex-col">
      {offer.subscribed && (
        <span className="absolute top-0 right-0 rounded-bl-md px-2 py-0.5 text-[9px] font-medium uppercase tracking-wide bg-[#10b981] text-white dark:bg-[#10b981]/15 dark:text-[#10b981] dark:border-l dark:border-b dark:border-[#10b981]/30">
          Subscribed
        </span>
      )}
      <div className="flex items-center gap-2 sm:gap-3 mb-2 sm:mb-3">
        <div className="flex items-center justify-center w-7 h-7 sm:w-8 sm:h-8 rounded-md bg-[var(--bg-primary)] border border-[var(--border-color)]">
          <Image
            src={offer.logoUrl || getGCPServiceIcon(offer.product)}
            alt=""
            width={18}
            height={18}
            className="h-[18px] w-[18px] object-contain"
          />
        </div>
      </div>

      <h3 className="text-xs sm:text-sm font-medium text-[var(--text-primary)] leading-snug mb-1">
        {offer.name}
      </h3>
      <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed mb-3 flex-1">
        {offer.description}
      </p>

      {offer.subscribed ? (
        <>
          {offer.watchingSince && (
            <p className="text-[10px] text-[var(--text-secondary)] mb-3">
              Watching since {offer.watchingSince}
            </p>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-full text-xs h-8 border-[var(--border-color)] text-[var(--text-secondary)] hover:text-red-500 hover:border-red-500/30"
            onClick={onUnsubscribe}
          >
            <Unplug className="h-3.5 w-3.5 mr-1.5" />
            Unsubscribe
          </Button>
        </>
      ) : (
        <Button
          type="button"
          size="sm"
          className="w-full text-xs h-8 bg-primary text-primary-foreground shadow-sm hover:bg-primary/90"
          onClick={onSubscribe}
        >
          <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" />
          Subscribe
        </Button>
      )}
    </div>
  );
}
