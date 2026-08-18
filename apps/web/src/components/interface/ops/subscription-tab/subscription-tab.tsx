"use client";

import { useEffect, useMemo, useState } from "react";
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
import { cn } from "@/lib/utils";
import { getGCPServiceIcon } from "@/lib/gcp-icons";
import { CheckCircle2, Rss, Search, Store, Unplug } from "lucide-react";
import {
  fetchProjectProviders,
  subscribeProjectProvider,
  unsubscribeProjectProvider,
} from "@/lib/providers";
import { type MarketplaceOffer } from "./data";
import {
  MarketplaceEmptyState,
  NoProjectEmptyState,
  SubscribedEmptyState,
} from "./empty-states";

type Section = "subscribed" | "marketplace";

export function SubscriptionTab({
  hasProject = true,
  projectId,
}: {
  hasProject?: boolean;
  projectId?: string;
}) {
  const [section, setSection] = useState<Section>("subscribed");
  const [offers, setOffers] = useState<MarketplaceOffer[]>([]);
  const [query, setQuery] = useState("");
  const [pending, setPending] = useState<{
    offer: MarketplaceOffer;
    action: "subscribe" | "unsubscribe";
  } | null>(null);

  const loadOffers = async (id: string) => {
    const rows = await fetchProjectProviders(id);
    setOffers(
      rows.map((row) => ({
        id: row.slug,
        slug: row.slug,
        name: row.name,
        provider: row.name,
        product: row.slug,
        description: row.description,
        category: row.category,
        logoUrl: row.logoUrl,
        subscribed: row.subscribed,
        watchingSince: row.subscribed_at
          ? new Date(row.subscribed_at).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
              year: "numeric",
            })
          : undefined,
      })),
    );
  };

  useEffect(() => {
    if (!projectId) {
      setOffers([]);
      return;
    }
    void loadOffers(projectId).catch(() => setOffers([]));
  }, [projectId]);

  const subscribed = offers.filter((offer) => offer.subscribed);
  const available = offers.filter((offer) => !offer.subscribed);

  const visible = useMemo(() => {
    const pool = section === "subscribed" ? subscribed : offers;
    const q = query.trim().toLowerCase();
    if (!q) return pool;
    return pool.filter(
      (offer) =>
        offer.name.toLowerCase().includes(q) ||
        offer.provider.toLowerCase().includes(q) ||
        offer.category.toLowerCase().includes(q) ||
        offer.description.toLowerCase().includes(q),
    );
  }, [offers, query, section, subscribed]);

  const toggle = (slug: string, next: boolean) => {
    if (!projectId) return;
    const action = next
      ? subscribeProjectProvider(projectId, slug)
      : unsubscribeProjectProvider(projectId, slug);
    void action.then(() => loadOffers(projectId)).catch(() => undefined);
  };

  if (!hasProject) {
    return <NoProjectEmptyState />;
  }

  const poolEmpty = section === "subscribed" ? subscribed.length === 0 : offers.length === 0;

  return (
    <div className="h-full flex min-w-0 overflow-hidden bg-[var(--bg-primary)]">
      <div className="w-56 flex-shrink-0 border-r border-[var(--border-color)] p-3 space-y-1">
        <button
          type="button"
          onClick={() => setSection("subscribed")}
          className={cn(
            "w-full flex items-center justify-between px-3 py-2 text-xs rounded-lg transition-colors",
            section === "subscribed"
              ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]",
          )}
        >
          <div className="flex items-center gap-2">
            <Rss className="h-4 w-4" />
            <span className="font-medium">Subscribed</span>
          </div>
          {subscribed.length > 0 && (
            <Badge
              variant="outline"
              className="text-[9px] h-5 bg-[#10b981]/10 text-[#10b981] border-[#10b981]/30"
            >
              {subscribed.length}
            </Badge>
          )}
        </button>
        <button
          type="button"
          onClick={() => setSection("marketplace")}
          className={cn(
            "w-full flex items-center justify-between px-3 py-2 text-xs rounded-lg transition-colors",
            section === "marketplace"
              ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]",
          )}
        >
          <div className="flex items-center gap-2">
            <Store className="h-4 w-4" />
            <span className="font-medium">Marketplace</span>
          </div>
          {available.length > 0 && (
            <Badge
              variant="outline"
              className="text-[9px] h-5 text-[var(--text-secondary)] border-[var(--border-color)]"
            >
              {available.length}
            </Badge>
          )}
        </button>
      </div>

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
                  ? "Providers this project watches for deprecations and replacements."
                  : "Providers you can watch for deprecations and replacements."}
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
                    onSubscribe={() => setPending({ offer, action: "subscribe" })}
                    onUnsubscribe={() => setPending({ offer, action: "unsubscribe" })}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-[var(--text-primary)]">
              {pending?.action === "unsubscribe"
                ? `Unsubscribe from ${pending.offer.name}?`
                : `Subscribe to ${pending?.offer.name}?`}
            </AlertDialogTitle>
            <AlertDialogDescription className="text-[var(--text-secondary)] leading-relaxed">
              {pending?.action === "unsubscribe"
                ? `This project will stop watching ${pending.offer.name} for deprecations and replacements. You can subscribe again anytime.`
                : `This project will watch ${pending?.offer.name} for deprecations and replacements. You can unsubscribe anytime.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={
                pending?.action === "unsubscribe"
                  ? "bg-red-500 hover:bg-red-600 text-white focus:ring-red-500"
                  : "bg-primary hover:bg-primary/90 text-primary-foreground"
              }
              onClick={() => {
                if (!pending) return;
                toggle(pending.offer.id, pending.action === "subscribe");
                setPending(null);
              }}
            >
              {pending?.action === "unsubscribe" ? "Unsubscribe" : "Subscribe"}
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
