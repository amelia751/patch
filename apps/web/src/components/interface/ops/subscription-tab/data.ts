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
