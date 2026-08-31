// The false positive Layer B exists to reject. `createSource` is a removed
// Stripe.js method, but this one is an application helper that happens to share
// the name, so Layer A reports it and no rule confirms it.
const attachments = {
  createSource(name: string) {
    return { name };
  },
};

export const made = attachments.createSource("receipt.pdf");
