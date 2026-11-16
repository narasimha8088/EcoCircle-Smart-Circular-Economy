"""
ai_engine/recommender.py
────────────────────────
Standalone AI recommendation engine used by Flask routes.
Can also be run directly for testing:
    python recommender.py
"""

# ── Emission factors (kg CO2 per kg of material produced) ──
EMISSION_FACTORS = {
    "electronics": 40,
    "mobile":      70,
    "laptop":      60,
    "appliance":   15,
    "furniture":   5,
    "clothing":    20,
    "vehicle":     10,
    "other":       8,
}

# ── Condition depreciation factors ─────────────────────────
CONDITION_FACTORS = {
    "new":  0.90,
    "good": 0.65,
    "fair": 0.40,
    "poor": 0.15,
}


def estimate_resale(purchase_price: float, age_years: float, condition: str) -> float:
    """Estimate current resale value using depreciation model."""
    cf = CONDITION_FACTORS.get(condition.lower(), 0.40)
    depreciation = max(0.0, 1 - (age_years * 0.12))
    return round(purchase_price * cf * depreciation, 2)


def carbon_saved(weight_kg: float, category: str, action: str = "reuse") -> float:
    """
    Calculate kg of CO2 saved by a circular action.
    Formula: weight × emission_factor × action_multiplier
    """
    ef = EMISSION_FACTORS.get(category.lower(), EMISSION_FACTORS["other"])
    multipliers = {"reuse": 0.85, "repair": 0.60, "recycle": 0.40, "sell": 0.75}
    m = multipliers.get(action.lower(), 0.5)
    return round(weight_kg * ef * m, 2)


def recommend(
    product_age: float,
    repair_cost: float,
    purchase_price: float,
    condition: str,
    category: str,
    weight_kg: float = 1.0,
) -> dict:
    """
    Core AI recommendation engine.

    Returns a dict with:
      - recommendation : str  (action to take)
      - reason         : str
      - sustainability_score : int (0-100)
      - icon           : str
      - estimated_resale : float
      - carbon_saved_kg  : float
      - repair_ratio     : float (%)
    """
    repair_ratio  = repair_cost / max(purchase_price, 1)
    resale_est    = estimate_resale(purchase_price, product_age, condition)
    co2           = carbon_saved(weight_kg, category)
    cond_lower    = condition.lower()

    # ── Decision Tree ──────────────────────────────────────
    if cond_lower in ("new",) and product_age < 1:
        action, reason, score, icon = (
            "Keep Using",
            "Product is still new. Keep using it to maximise lifespan.",
            90, "✅",
        )
    elif repair_ratio < 0.30 and cond_lower in ("fair", "good"):
        action, reason, score, icon = (
            "Repair",
            f"Repair cost (₹{repair_cost:.0f}) is only {repair_ratio*100:.0f}% of "
            f"original price. Repairing is economical and eco-friendly.",
            85, "🔧",
        )
    elif cond_lower in ("good", "fair") and resale_est > repair_cost:
        action, reason, score, icon = (
            "Resell",
            f"Estimated resale value ₹{resale_est:,.0f}. Selling gives someone "
            f"else a chance to use this product.",
            75, "💰",
        )
    elif repair_ratio < 0.60 and product_age < 5:
        action, reason, score, icon = (
            "Repair then Resell",
            "A small repair can significantly increase resale value.",
            70, "🔧💰",
        )
    elif cond_lower == "poor" and product_age > 5:
        action, reason, score, icon = (
            "Recycle",
            "Product is too old or damaged. Responsible recycling "
            "recovers valuable materials.",
            60, "♻️",
        )
    else:
        action, reason, score, icon = (
            "Donate",
            "If still functional, donating extends its life and helps others.",
            72, "🎁",
        )

    return {
        "recommendation":     action,
        "reason":             reason,
        "sustainability_score": score,
        "icon":               icon,
        "estimated_resale":   resale_est,
        "carbon_saved_kg":    co2,
        "repair_ratio":       round(repair_ratio * 100, 1),
    }


# ── Quick CLI test ──────────────────────────────────────────
if __name__ == "__main__":
    print("\n🤖 EcoCircle AI Engine — Quick Test\n")
    test_cases = [
        dict(product_age=3, repair_cost=3000, purchase_price=30000,
             condition="Good", category="laptop", weight_kg=2),
        dict(product_age=6, repair_cost=8000, purchase_price=15000,
             condition="Poor", category="mobile", weight_kg=0.2),
        dict(product_age=1, repair_cost=500, purchase_price=50000,
             condition="Good", category="electronics", weight_kg=5),
    ]
    for i, tc in enumerate(test_cases, 1):
        r = recommend(**tc)
        print(f"Test {i}: {tc['condition']} {tc['category']} ({tc['product_age']} yrs)")
        print(f"  → {r['icon']}  {r['recommendation']}")
        print(f"     Score: {r['sustainability_score']}  |  CO2 saved: {r['carbon_saved_kg']} kg")
        print(f"     {r['reason']}\n")
