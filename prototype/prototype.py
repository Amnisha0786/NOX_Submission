#!/usr/bin/env python3
"""
Demand-aware drop valuation prototype for the Nox Metals nesting challenge.

This is intentionally NOT a production nesting/packing solver. It demonstrates
one core design idea: a leftover/drop should be valued by how likely it is to
serve future demand, not only by its immediate area.

Run from the repository root or pass paths:
    python prototype.py --jobs ../jobs.json --inventory ../inventory.json --history ../order_history.json
"""
from __future__ import annotations
import argparse, json, math, collections
from typing import Dict, Any, List, Tuple

DENSITY_LB_PER_IN3 = {"6061-T6": 0.0975, "7075-T6": 0.1010}


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fits_rect(w: float, l: float, stock_w: float, stock_l: float, kerf: float = 0.0) -> bool:
    """Return True if a part can fit in stock, allowing 90-degree rotation."""
    w2, l2 = w + kerf, l + kerf
    return (w2 <= stock_w and l2 <= stock_l) or (w2 <= stock_l and l2 <= stock_w)


def material_value(alloy: str, thickness: float, width: float, length: float, price_per_lb: float) -> float:
    return DENSITY_LB_PER_IN3[alloy] * thickness * width * length * price_per_lb


def summarize_jobs(jobs: List[Dict[str, Any]]) -> Dict[Tuple[str, float], Dict[str, float]]:
    summary = collections.defaultdict(lambda: {"lines": 0, "pieces": 0, "area": 0.0})
    for job in jobs:
        for p in job["parts"]:
            key = (p["alloy"], p["thickness_in"])
            summary[key]["lines"] += 1
            summary[key]["pieces"] += p["quantity"]
            summary[key]["area"] += p["width_in"] * p["length_in"] * p["quantity"]
    return dict(summary)


def historical_group_totals(history):
    totals = collections.defaultdict(lambda: {"lines": 0, "pieces": 0, "area": 0.0})
    for h in history:
        key = (h["alloy"], h["thickness_in"])
        totals[key]["lines"] += 1
        totals[key]["pieces"] += h["quantity"]
        totals[key]["area"] += h["width_in"] * h["length_in"] * h["quantity"]
    return dict(totals)


def drop_history_stats(drop: Dict[str, Any], history: List[Dict[str, Any]], totals) -> Dict[str, float]:
    """Estimate a drop's future usefulness from past orders of matching alloy/thickness."""
    fit_lines = 0
    fit_qty = 0
    fit_area = 0.0
    for h in history:
        same_material = h["alloy"] == drop["alloy"] and h["thickness_in"] == drop["thickness_in"]
        if same_material and fits_rect(h["width_in"], h["length_in"], drop["width_in"], drop["length_in"]):
            fit_lines += 1
            fit_qty += h["quantity"]
            fit_area += h["width_in"] * h["length_in"] * h["quantity"]

    group_total = max(1, totals.get((drop["alloy"], drop["thickness_in"]), {}).get("pieces", 0))

    # Probability proxy: a saturating curve based on how much historical demand could fit.
    # This is deliberately simple and explainable, not a trained forecast.
    reuse_probability = 1 - math.exp(-(fit_qty / group_total) * 2.5)

    # Confidence is lower when only a few historical lines support the estimate.
    confidence = min(1.0, math.sqrt(fit_lines / 30.0)) if fit_lines else 0.0

    expected_value = drop["unit_cost"] * reuse_probability * confidence
    return {
        "fit_lines": fit_lines,
        "fit_qty": fit_qty,
        "reuse_probability": reuse_probability,
        "confidence": confidence,
        "expected_value": expected_value,
    }


def pseudo_drop_value(alloy, thickness, width, length, price_per_lb, history, totals, min_keep_side=4.0):
    """Value a hypothetical leftover rectangle."""
    if width <= 0 or length <= 0 or min(width, length) < min_keep_side:
        return 0.0
    unit_cost = material_value(alloy, thickness, width, length, price_per_lb)
    temp = {
        "alloy": alloy,
        "thickness_in": thickness,
        "width_in": width,
        "length_in": length,
        "unit_cost": unit_cost,
    }
    return drop_history_stats(temp, history, totals)["expected_value"]


def evaluate_cut_from_drop(drop, part, history, totals, kerf=0.1):
    """Compare the value of consuming a drop for a part vs preserving it."""
    if not (drop["alloy"] == part["alloy"] and drop["thickness_in"] == part["thickness_in"]):
        return None
    if not fits_rect(part["width_in"], part["length_in"], drop["width_in"], drop["length_in"], kerf):
        return None

    original_value = drop_history_stats(drop, history, totals)["expected_value"]
    saved_material = material_value(part["alloy"], part["thickness_in"], part["width_in"], part["length_in"], drop["price_per_lb"])

    best = None
    for pw, pl in [(part["width_in"], part["length_in"]), (part["length_in"], part["width_in"] )]:
        orientations = []
        if pw + kerf <= drop["width_in"] and pl + kerf <= drop["length_in"]:
            orientations.append((drop["width_in"], drop["length_in"], pw, pl))
        if pw + kerf <= drop["length_in"] and pl + kerf <= drop["width_in"]:
            orientations.append((drop["length_in"], drop["width_in"], pw, pl))
        for sw, sl, w, l in orientations:
            # Corner placement with two simple remnants; enough to demonstrate the valuation idea.
            remnants = [(sw - w - kerf, sl), (w, sl - l - kerf)]
            leftover_value = sum(
                pseudo_drop_value(drop["alloy"], drop["thickness_in"], rw, rl, drop["price_per_lb"], history, totals)
                for rw, rl in remnants
            )
            opportunity_cost = original_value - leftover_value
            net_score = saved_material - opportunity_cost
            row = {
                "drop_id": drop["id"],
                "drop_size": f"{drop['width_in']}x{drop['length_in']}",
                "saved_material": saved_material,
                "original_drop_future_value": original_value,
                "leftover_future_value": leftover_value,
                "opportunity_cost": opportunity_cost,
                "net_score": net_score,
            }
            if best is None or row["net_score"] > best["net_score"]:
                best = row
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", default="../jobs.json")
    ap.add_argument("--inventory", default="../inventory.json")
    ap.add_argument("--history", default="../order_history.json")
    args = ap.parse_args()

    jobs = load_json(args.jobs)
    inventory = load_json(args.inventory)
    history = load_json(args.history)
    drops = [x for x in inventory if x["kind"] == "drop"]
    totals = historical_group_totals(history)

    print("DATASET SUMMARY")
    print("---------------")
    print(f"current jobs: {len(jobs)}")
    print(f"inventory items: {len(inventory)} ({sum(1 for x in inventory if x['kind']=='plate')} fresh plate SKUs, {len(drops)} drops)")
    print(f"historical order lines: {len(history)}")

    print("\nCURRENT DEMAND BY MATERIAL GROUP")
    for key, s in sorted(summarize_jobs(jobs).items(), key=lambda kv: kv[1]["area"], reverse=True):
        print(f"{key[0]:7s} {key[1]:>5}: {s['pieces']:>3.0f} pieces, {s['area']:>7.0f} sq in")

    valued = []
    for d in drops:
        valued.append({**d, **drop_history_stats(d, history, totals)})
    valued.sort(key=lambda r: r["expected_value"], reverse=True)

    print("\nTOP DROPS TO PRESERVE IF POSSIBLE")
    print("drop       material   size      hist_qty_fit  confidence  expected_value")
    for r in valued[:8]:
        print(f"{r['id']:10s} {r['alloy']:7s} {r['thickness_in']:<4} {r['width_in']:>2}x{r['length_in']:<3} {r['fit_qty']:>12.0f} {r['confidence']:>10.2f} ${r['expected_value']:>8.2f}")

    print("\nLOW-VALUE DROPS TO CONSUME FIRST WHEN THEY FIT")
    for r in sorted(valued, key=lambda r: r["expected_value"])[:8]:
        print(f"{r['id']:10s} {r['alloy']:7s} {r['thickness_in']:<4} {r['width_in']:>2}x{r['length_in']:<3} expected future value ${r['expected_value']:.2f}")

    example_part = {"alloy": "6061-T6", "thickness_in": 0.5, "width_in": 10, "length_in": 10}
    choices = []
    for d in drops:
        row = evaluate_cut_from_drop(d, example_part, history, totals)
        if row:
            choices.append(row)
    choices.sort(key=lambda r: r["net_score"], reverse=True)

    print("\nEXAMPLE DECISION: one 6061-T6 0.5in 10x10 part")
    print("The prototype prefers drops with low opportunity cost, not simply the largest fitting drop.")
    print("drop       size    saved_material  original_value  leftover_value  net_score")
    for r in choices:
        print(f"{r['drop_id']:10s} {r['drop_size']:>6s} ${r['saved_material']:>8.2f}      ${r['original_drop_future_value']:>8.2f}       ${r['leftover_future_value']:>8.2f}   ${r['net_score']:>8.2f}")


if __name__ == "__main__":
    main()
