# ADR 0019: Promotion Resolution Boundary

- Status: Accepted
- Date: 2026-08-05

## Context

Promotional pricing must support Store-specific targeting, Coupons, usage limits,
multiple discount strategies, and deterministic stacking without weakening the
existing Pricing and immutable commerce snapshot boundaries. Recalculating after
Checkout would allow mutable campaign configuration to change an accepted Order.

## Decision

Introduce Promotions as a Store-scoped bounded context. Pricing and Price Lists
remain the only source of unit prices. Promotion evaluation consumes production
Cart summaries after price resolution, resolves eligibility and stacking without
writes, and returns a deterministic breakdown capped by the Cart subtotal.

Checkout freezes applied Promotion, Coupon, amount, currency, priority, policy,
and source version into Promotion-owned Redemption rows. Usage advances only when
those snapshots are frozen. Order creation links the unchanged Checkout snapshots
without recalculation.

Promotion management, Coupon management, Redemption persistence, customer usage,
and identifier-only outbox events share request transactions. Repositories flush
only. Cross-Store and cross-user resources are concealed with `404`.

## Consequences

- Mutable campaign changes cannot alter Checkout or Order discount snapshots.
- Promotion calculations never replace or duplicate Pricing resolution.
- Evaluation can be retried without consuming usage or changing Cart data.
- Checkout creation is the redemption and usage boundary.
- Higher priority and exclusive behavior are stable and reproducible.
- The sum of frozen discount lines cannot exceed the Checkout subtotal.
- Shipping-rate interpretation of free-shipping Promotions remains deferred.
