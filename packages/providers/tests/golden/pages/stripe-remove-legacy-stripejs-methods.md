# Removes deprecated Payment Intents, Setup Intents, and Sources methods from Stripe.js

## What’s new

Removes several deprecated methods from Stripe.js in favor of equivalent methods with clearer naming and improved functionality.

## Why is this a breaking change?

The following methods have been removed and will throw an error if called:

**Payment Intents API:**

- `handleCardPayment`
- `confirmPaymentIntent`
- `handleFpxPayment`

**Setup Intents API:**

- `handleCardSetup`
- `confirmSetupIntent`

**Sources API:**

- `createSource`
- `retrieveSource`

## Impact

If your integration uses any of the deprecated methods, you must update your code to use different methods, as in the following examples:

### Payment Intents API methods

- Replace `handleCardPayment` with [confirmCardPayment](https://docs.stripe.com/js/payment_intents/confirm_card_payment?api-version=2026-03-25.dahlia), which has a similar API signature and behavior.

```javascript
// Before (deprecated)
stripe.handleCardPayment(clientSecret, cardElement);

// After
stripe.confirmCardPayment(clientSecret, {
  payment_method: {
    card: cardElement,
  },
});
```

- Replace `confirmPaymentIntent` with the more explicit [confirmCardPayment](https://docs.stripe.com/js/payment_intents/confirm_card_payment?api-version=2026-03-25.dahlia).

```javascript
// Before (deprecated)
stripe.confirmPaymentIntent(clientSecret, {
  payment_method: {
    card: cardElement,
  },
});

// After
stripe.confirmCardPayment(clientSecret, {
  payment_method: {
    card: cardElement,
  },
});
```

- Replace `handleFpxPayment` with [confirmFpxPayment](https://docs.stripe.com/js/payment_intents/confirm_fpx_payment?api-version=2026-03-25.dahlia), which has an identical API signature and behavior.

```javascript
// Before (deprecated)
stripe.handleFpxPayment(clientSecret, {
  payment_method: {
    fpx: fpxBankElement,
  },
});

// After
stripe.confirmFpxPayment(clientSecret, {
  payment_method: {
    fpx: fpxBankElement,
  },
});
```

### Setup Intents API methods

- Replace handleCardSetup` with [confirmCardSetup](https://docs.stripe.com/js/setup_intents/confirm_card_setup?api-version=2026-03-25.dahlia), which has a similar API signature and behavior.

```javascript
// Before (deprecated)
stripe.handleCardSetup(clientSecret, cardElement);

// After
stripe.confirmCardSetup(clientSecret, {
  payment_method: {
    card: cardElement,
  },
});
```

- Replace `confirmSetupIntent` with the more explicit [confirmCardSetup](https://docs.stripe.com/js/setup_intents/confirm_card_setup?api-version=2026-03-25.dahlia).

```javascript
// Before (deprecated)
stripe.confirmSetupIntent(clientSecret, {
  payment_method: {
    card: cardElement,
  },
});

// After
stripe.confirmCardSetup(clientSecret, {
  payment_method: {
    card: cardElement,
  },
});
```

### Sources API methods

If your code uses methods like `createSource` and `retrieveSource` from the legacy Sources API, [migrate your integration to use the Payment Methods API](https://docs.stripe.com/payments/payment-methods/transitioning.md) instead.

The [Payment Methods API](https://docs.stripe.com/payments/payment-methods.md) provides better support for payment methods, reusability, and compliance requirements.

## Related changes

- [Changes the Address Element state field to default to Latin-formatted characters](https://docs.stripe.com/changelog/dahlia/2026-03-25/address-element-getvalue-and-change-event-formatting.md)
- [Updates the elements.update() method to return a Promise](https://docs.stripe.com/changelog/dahlia/2026-03-25/elements-update-returns-promise.md)
- [Removes support for boolean values in options.layout.radios](https://docs.stripe.com/changelog/dahlia/2026-03-25/disallow-booleans-for-radios.md)
- [Renames Checkout initialization method](https://docs.stripe.com/changelog/dahlia/2026-03-25/rename-init-checkout-to-init-checkout-elements.md)
- [Renames Embedded Checkout initialization method](https://docs.stripe.com/changelog/dahlia/2026-03-25/rename-init-embedded-checkout-to-create-embedded-checkout-page.md)
