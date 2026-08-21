"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { getGCPServiceIcon } from "@/lib/gcp-icons";
import { CheckCircle2, Rss, ScanSearch, Search, Store, Unplug } from "lucide-react";
import { SectionRail, SectionRailButton } from "@/components/interface/shared/section-rail";
import {
  MOCK_GOOGLE_OFFER,
  MOCK_SUBSCRIBED_KEY,
  SUBSCRIBE_SCAN_STEPS,
  type MarketplaceOffer,
} from "./data";
import {
  MarketplaceEmptyState,
  NoProjectEmptyState,
  SubscribedEmptyState,
} from "./empty-states";

type Section = "subscribed" | "marketplace";

function readMockSubscribed(): boolean {
  if (typeof window === "undefined") return false;
  return window.sessionStorage.getItem(MOCK_SUBSCRIBED_KEY) === "1";
}

function writeMockSubscribed(next: boolean) {
  if (typeof window === "undefined") return;
  if (next) window.sessionStorage.setItem(MOCK_SUBSCRIBED_KEY, "1");
  else window.sessionStorage.removeItem(MOCK_SUBSCRIBED_KEY);
}

function mockOffer(subscribed: boolean): MarketplaceOffer {
  return {
    ...MOCK_GOOGLE_OFFER,
    subscribed,
    watchingSince: subscribed
      ? new Date().toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
          year: "numeric",
        })
      : undefined,
  };
}

export function SubscriptionTab({
  hasProject = true,
  onOpenChanges,
}: {
  hasProject?: boolean;
  projectId?: string;
  onOpenChanges?: () => void;
}) {
  const [section, setSection] = useState<Section>("marketplace");
  const [subscribed, setSubscribed] = useState(false);
  const [query, setQuery] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanStep, setScanStep] = useState(0);
  const [unsubscribeOpen, setUnsubscribeOpen] = useState(false);
  const scanTimer = useRef<number | null>(null);

  useEffect(() => {
    setSubscribed(readMockSubscribed());
    return () => {
      if (scanTimer.current !== null) window.clearInterval(scanTimer.current);
    };
  }, []);

  const offers = useMemo(() => [mockOffer(subscribed)], [subscribed]);
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

  const startScan = () => {
    setScanning(true);
    setScanStep(0);
    let step = 0;
    if (scanTimer.current !== null) window.clearInterval(scanTimer.current);
    scanTimer.current = window.setInterval(() => {
      step += 1;
      if (step >= SUBSCRIBE_SCAN_STEPS.length) {
        if (scanTimer.current !== null) window.clearInterval(scanTimer.current);
        scanTimer.current = null;
        writeMockSubscribed(true);
        setSubscribed(true);
        setScanning(false);
        setConfirmOpen(false);
        setScanStep(0);
        setSection("subscribed");
        onOpenChanges?.();
        return;
      }
      setScanStep(step);
    }, 850);
  };

  const unsubscribe = () => {
    writeMockSubscribed(false);
    setSubscribed(false);
    setUnsubscribeOpen(false);
    setSection("marketplace");
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
                    onSubscribe={() => setConfirmOpen(true)}
                    onUnsubscribe={() => setUnsubscribeOpen(true)}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <Dialog
        open={confirmOpen}
        onOpenChange={(open) => {
          if (scanning) return;
          setConfirmOpen(open);
        }}
      >
        <DialogContent className="sm:max-w-[440px] bg-[var(--bg-primary)] border-[var(--border-color)]">
          {scanning ? (
            <div className="py-4">
              <div className="flex items-center justify-center mb-4">
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                  <Spinner className="h-5 w-5 text-primary" />
                </div>
              </div>
              <DialogHeader className="text-center sm:text-center">
                <DialogTitle className="text-[var(--text-primary)]">
                  Scanning your codebase
                </DialogTitle>
                <DialogDescription className="text-[var(--text-secondary)]">
                  {SUBSCRIBE_SCAN_STEPS[scanStep]}
                </DialogDescription>
              </DialogHeader>
              <div className="mt-5 space-y-2">
                {SUBSCRIBE_SCAN_STEPS.map((label, index) => {
                  const done = index < scanStep;
                  const current = index === scanStep;
                  return (
                    <div
                      key={label}
                      className="flex items-center gap-2 text-xs"
                    >
                      {done ? (
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" />
                      ) : current ? (
                        <Spinner className="h-3.5 w-3.5 text-primary flex-shrink-0" />
                      ) : (
                        <span className="h-3.5 w-3.5 rounded-full border border-[var(--border-color)] flex-shrink-0" />
                      )}
                      <span
                        className={
                          current
                            ? "text-[var(--text-primary)]"
                            : done
                              ? "text-[var(--text-secondary)]"
                              : "text-[var(--text-secondary)]/50"
                        }
                      >
                        {label}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle className="text-[var(--text-primary)]">
                  Watch Google Cloud in this project?
                </DialogTitle>
                <DialogDescription className="text-[var(--text-secondary)] leading-relaxed">
                  We will scan this repository for Google Cloud APIs and models, then match
                  them against the catalog. Matches — including deprecations and replacements —
                  show up on Changes. Nothing is written to the repo until you review a pull
                  request.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter className="gap-2 sm:gap-0">
                <Button
                  type="button"
                  variant="outline"
                  className="border-[var(--border-color)] text-[var(--text-secondary)]"
                  onClick={() => setConfirmOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  className="bg-primary hover:bg-primary/90 text-primary-foreground"
                  onClick={startScan}
                >
                  <ScanSearch className="h-3.5 w-3.5 mr-1.5" />
                  Scan and watch
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog open={unsubscribeOpen} onOpenChange={setUnsubscribeOpen}>
        <AlertDialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-[var(--text-primary)]">
              Unsubscribe from Google Cloud?
            </AlertDialogTitle>
            <AlertDialogDescription className="text-[var(--text-secondary)] leading-relaxed">
              This project will stop watching Google Cloud for deprecations and replacements.
              You can subscribe again anytime.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-500 hover:bg-red-600 text-white focus:ring-red-500"
              onClick={unsubscribe}
            >
              Unsubscribe
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
