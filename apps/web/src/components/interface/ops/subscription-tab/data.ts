import { GOOGLE_CLOUD_PROVIDER } from "@/components/interface/provider/data";

export type MarketplaceOffer = {
  id: string;
  slug: string;
  name: string;
  provider: string;
  product: string;
  description: string;
  category: string;
  logoUrl?: string;
  subscribed: boolean;
  watchingSince?: string;
};

export const MOCK_GOOGLE_OFFER: MarketplaceOffer = {
  id: GOOGLE_CLOUD_PROVIDER.slug,
  slug: GOOGLE_CLOUD_PROVIDER.slug,
  name: GOOGLE_CLOUD_PROVIDER.name,
  provider: GOOGLE_CLOUD_PROVIDER.name,
  product: GOOGLE_CLOUD_PROVIDER.slug,
  description: GOOGLE_CLOUD_PROVIDER.description,
  category: GOOGLE_CLOUD_PROVIDER.category,
  logoUrl: GOOGLE_CLOUD_PROVIDER.logoUrl,
  subscribed: false,
};

export const MOCK_SUBSCRIBED_KEY = "patch.subscription.mock.google";
export const MOCK_CHANGES_SCAN_KEY = "patch.changes.mock.scan";
export const MOCK_SUBSCRIBE_SCAN_EVENT = "patchSubscribeScan";
export const MOCK_CHANGES_SCAN_MS = 10_000;
