import { GOOGLE_CLOUD_PROVIDER } from "@/components/interface/provider/data";

export type MarketplaceOffer = {
  id: string;
  name: string;
  provider: string;
  product: string;
  description: string;
  category: string;
  logoUrl?: string;
  subscribed: boolean;
  watchingSince?: string;
};

export const MARKETPLACE_OFFERS: MarketplaceOffer[] = [
  {
    id: GOOGLE_CLOUD_PROVIDER.id,
    name: GOOGLE_CLOUD_PROVIDER.name,
    provider: GOOGLE_CLOUD_PROVIDER.name,
    product: "google cloud",
    description: GOOGLE_CLOUD_PROVIDER.description,
    category: "Cloud",
    logoUrl: GOOGLE_CLOUD_PROVIDER.logoUrl,
    subscribed: false,
  },
];

const storageKey = (projectId: string) => `patchapi.subscriptions.${projectId}`;

export function loadSubscribedIds(projectId: string): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(storageKey(projectId));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(
        (entry): entry is [string, string] => typeof entry[1] === "string",
      ),
    );
  } catch {
    return {};
  }
}

export function saveSubscribedIds(projectId: string, ids: Record<string, string>): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(storageKey(projectId), JSON.stringify(ids));
}

export function applySubscriptions(
  catalog: MarketplaceOffer[],
  ids: Record<string, string>,
): MarketplaceOffer[] {
  return catalog.map((offer) => ({
    ...offer,
    subscribed: offer.id in ids,
    watchingSince: ids[offer.id],
  }));
}
