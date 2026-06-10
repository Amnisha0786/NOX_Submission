# Sample data

Three files. All dimensions are in inches, weights in pounds, money in US dollars. The numbers are illustrative; do not read anything into the exact values.

## jobs.json

The batch of customer orders you need to nest right now. An array of orders:

| field | meaning |
|-------|---------|
| `order_id` | order identifier |
| `due_date` | when it is due (ISO date) |
| `parts` | the rectangular parts on the order |

Each part:

| field | meaning |
|-------|---------|
| `alloy` | material |
| `thickness_in` | plate thickness |
| `width_in`, `length_in` | the rectangle to cut |
| `quantity` | how many of this part |

## inventory.json

The stock you have to cut from. An array of items.

| field | meaning |
|-------|---------|
| `id` | item identifier |
| `kind` | `"plate"` (fresh stock) or `"drop"` (an existing remnant) |
| `alloy` | material |
| `thickness_in` | thickness |
| `width_in`, `length_in` | the rectangle |
| `quantity` | how many you have |
| `price_per_lb` | material price |
| `weight_lbs` | weight of a single piece (density times thickness times width times length) |
| `unit_cost` | cost of a single piece (`price_per_lb` times `weight_lbs`) |

How to treat stock:

- **Plates** are the menu of fresh material you can buy. Assume you can buy more of any listed plate at its size and price; the `quantity` is just what happens to be on hand.
- **Drops** are a finite bin. You have exactly the `quantity` shown, and each is one of a kind. A part cut from a drop is material you did not have to buy fresh.

## order_history.json

About a year of past customer part orders, one row per order line, oldest first. Use it to reason about which leftover sizes are likely to be reused, which is what tells you how much a drop is worth.

| field | meaning |
|-------|---------|
| `ordered_at` | order date (ISO date) |
| `alloy`, `thickness_in`, `width_in`, `length_in`, `quantity` | same shape as a job part |

## Densities (so you do not have to look them up)

| alloy | density (lb / in^3) |
|-------|---------------------|
| 6061-T6 | 0.0975 |
| 7075-T6 | 0.1010 |
