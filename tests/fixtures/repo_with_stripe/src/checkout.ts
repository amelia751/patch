// Runtime call site for a method removed in Stripe API version 2026-03-25.dahlia.
// The call throws at runtime rather than warning, which is why this ranks as
// breakage rather than as a deprecation to schedule.
import { loadStripe } from "@stripe/stripe-js";

const stripe = await loadStripe(process.env.STRIPE_PUBLISHABLE_KEY!);

export async function payWithCard(clientSecret: string, cardElement: unknown) {
  return stripe.handleCardPayment(clientSecret, cardElement);
}

export async function saveCard(clientSecret: string, cardElement: unknown) {
  return stripe.handleCardSetup(clientSecret, cardElement);
}
