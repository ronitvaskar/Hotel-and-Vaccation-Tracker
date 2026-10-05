# Estimated Booking and Revenue Methodology

## Purpose

The model estimates market pressure from repeated visible availability observations. It does **not** claim access to a hotel's private booking ledger, room inventory system, cancellations, or final transacted revenue.

## Input consistency rule

Compare only observations with the same:

- property and room type;
- check-in and check-out dates;
- guest count and requested room quantity;
- meal preference and cancellation context where those are part of the source query.

The tracker stores these factors in `booking_conditions`, so the dashboard does not casually compare a two-guest weekday quote with a four-guest weekend quote.

## Visible-inventory signal

For two consecutive observations under the same condition:

```text
visible_unit_drop = max(0, prior_visible_units − current_visible_units)
```

When a visible-unit drop is observed, the tracker records it as **estimated units sold / demand signal**. It may instead reflect allocation changes, blocked inventory, platform mapping, release rules, a source refresh, or a cancellation/rebook sequence. The database retains both underlying snapshot values so the assumption can be reviewed.

An increase in visible units is recorded as an availability-increased event and is not treated as negative sales.

## Estimated room nights

```text
estimated_room_nights = visible_unit_drop × stay_nights
```

This is a signal for the selected room type and booking condition only. It is not market-wide confirmed room-night production.

## Estimated gross booking value

```text
estimated_gross_booking_value = visible_unit_drop × observed_selling_rate
```

`observed_selling_rate` is the current rate for the same property/room/condition and includes neither unobserved refunds nor back-office commissions. Where a rate is absent, no booking-value estimate is made. The app labels the result **Estimated gross value — not confirmed revenue**.

## Availability/occupancy proxy

When a verified total-unit count is available:

```text
visible_inventory_pressure = 1 − (visible_units_remaining / verified_total_units)
```

This is still an availability proxy, not a confirmed occupancy measure. In the included demo, all capacities are labelled `demo_assumption`; replace them with verified property inventory before using that metric in a decision.

## Booking velocity

For a property and fixed condition:

```text
estimated_booking_velocity = cumulative_visible_unit_drop / elapsed_observation_days
```

This is meaningful only after several observations. A single snapshot does not establish velocity.

## Recommended interpretation

- A sold-out transition plus price increase is a stronger pressure signal than either alone.
- A visible-unit drop with no price change may imply inventory pressure, but should be cross-checked on the next observation.
- Rate reductions can reflect promotions, weak demand, channel strategy, or package changes; compare meals/cancellation terms before concluding discounting.
- Review-rating and review-count changes are secondary signals, not sales evidence.

Every dashboard output should preserve the word **estimated** unless it comes from an approved owner/partner/internal booking source explicitly marked as confirmed.
