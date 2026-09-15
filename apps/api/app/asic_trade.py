"""Deterministic arithmetic trade study for EPIC B (지시서 §4).

Pure arithmetic over the option rows' declared NRE/unit-cost/schedule/risk
JSONB — no solver, no invented numbers: everything the study reports comes
from the options' own entries, and an undecided entry is carried through as
TBD, never zero (수용기준: 미확정 값은 TBD이며 0으로 계산되지 않는다).

Scenarios: every unit-cost component declares {best, base, worst} bands, so
each option gets three totals (수용기준: 단일 숫자가 아니라 Base/Best/Worst).
NRE amortization + breakeven come from the volume grid [MOQ .. 10× annual
volume] against the cheapest *complete* alternative.
"""

TOOL_VERSION = "asic-trade-study-v1"

# severity → penalty weight for the supply-risk axis (high = worst)
_SEVERITY_W = {"high": 3.0, "medium": 2.0, "low": 1.0}
# risk kinds that belong to the 공급 (supply) axis; the rest are noted but
# do not feed the weighted score
_SUPPLY_KINDS = {"supply_single", "long_lead", "equipment_availability"}

NRE_COMPONENTS = (
    "design", "ip", "mask", "mpw_shuttle", "pkg_tooling", "test_dev", "reliability",
)
UNIT_COMPONENTS = ("wafer", "assembly", "final_test", "logistics")  # additive money
FRACTION_COMPONENTS = ("die_yield", "scrap")  # fractions, not money


def _tbd_entries(table: dict) -> list[str]:
    """Components explicitly declared TBD (amount_tbd / base_tbd flag).

    model_dump() serializes undeclared optional fields as explicit nulls, so
    "key exists" must never be read as "value declared" — only these flags
    mark TBD."""
    out = []
    for k, v in (table or {}).items():
        if isinstance(v, dict) and (v.get("amount_tbd") is not None or v.get("base_tbd")):
            out.append(k)
    return sorted(out)


def _component_amount(entry: dict, scenario: str) -> float | None:
    """Pick the scenario amount from a unit-cost entry; None = TBD.

    Absent component → 0.0 (not applicable). Present but explicitly TBD →
    None (수용기준: TBD ≠ 0). A declared entry without the requested band
    edge falls back to base; a declared entry with no number at all is TBD.
    """
    if not entry:
        return 0.0
    if entry.get("amount_tbd") is not None or entry.get("base_tbd"):
        return None
    if scenario in ("best", "worst") and entry.get(scenario) is not None:
        return float(entry[scenario])
    base = entry.get("base")
    return float(base) if base is not None else None


def option_totals(option, scenario: str = "base") -> dict:
    """One option's NRE + per-unit money at its declared qty basis.

    die_yield scales the wafer cost per good die (die_per_wafer entry when
    given); scrap adds the declared fraction on top of conversion steps.
    Any TBD component nulls the totals and names itself.
    """
    nre_tbd = _tbd_entries(option.nre or {})
    nre_total: float | None = None
    if not nre_tbd:
        nre_total = sum(
            float((option.nre or {}).get(c, {}).get("amount", 0.0)) for c in NRE_COMPONENTS
        )

    unit_tbd = _tbd_entries(option.unit_cost or {})
    unit_total: float | None = None
    per_unit: dict = {}
    if not unit_tbd:
        money = 0.0
        for c in UNIT_COMPONENTS:
            v = _component_amount((option.unit_cost or {}).get(c, {}), scenario)
            if v is None:
                money = None
                break
            money += v
            per_unit[c] = v
        if money is not None:
            wafer_entry = (option.unit_cost or {}).get("wafer", {})
            yield_v = _component_amount((option.unit_cost or {}).get("die_yield", {}), scenario)
            scrap_v = _component_amount((option.unit_cost or {}).get("scrap", {}), scenario)
            dies = float(wafer_entry.get("dies_per_wafer", 0.0)) or None
            if dies and yield_v is not None:
                # wafer cost per GOOD die — the yield's whole economic point
                per_unit["wafer_per_good_die"] = round(per_unit.get("wafer", 0.0) / (dies * yield_v), 6)
                money = money - per_unit.get("wafer", 0.0) + per_unit["wafer_per_good_die"]
            if scrap_v is not None:
                adder = money * scrap_v
                per_unit["scrap_adder"] = round(adder, 6)
                money += adder
            unit_total = round(money, 6)

    sched = option.schedule or []
    weeks = [
        s.get(f"weeks_{scenario}" if scenario != "base" else "weeks_base", s.get("weeks_base"))
        for s in sched
    ]
    weeks = [float(w) for w in weeks if w is not None]
    schedule_total = round(sum(weeks), 2) if len(weeks) == len(sched) and sched else None

    risks = option.risks or []
    supply_penalty = sum(
        _SEVERITY_W.get(r.get("severity"), 1.0)
        for r in risks
        if r.get("kind") in _SUPPLY_KINDS
    )
    return {
        "option_id": str(option.id),
        "business_id": option.business_id,
        "foundry": option.foundry,
        "node": option.node,
        "package": option.package,
        "nre_total": nre_total,
        "nre_tbd_components": nre_tbd,
        "unit_cost_total": unit_total,
        "unit_cost_detail": per_unit,
        "unit_tbd_components": unit_tbd,
        "schedule_weeks_total": schedule_total,
        "supply_risk_penalty": supply_penalty,
        "risks": risks,
    }


def _score(totals: list[dict], weights: dict) -> list[dict]:
    """Normalized 0..1 per axis (lower-is-better), then weighted sum.

    An option missing an axis (TBD) keeps its known axes but its total is
    flagged partial and ranks below complete options only via the missing
    axis scoring as 0 — the report names why (수용기준: TBD ≠ 0은 금지, so
    partial totals are labelled, never silently summed as 0).
    """
    def norm(vals: list[float | None]) -> list[float | None]:
        known = [v for v in vals if v is not None]
        if not known:
            return [None] * len(vals)
        lo, hi = min(known), max(known)
        span = hi - lo
        if span <= 0:
            return [1.0 if v is not None else None for v in vals]
        return [None if v is None else round((hi - v) / span, 4) for v in vals]

    cost_s = norm([t["unit_cost_total"] for t in totals])
    sched_s = norm([t["schedule_weeks_total"] for t in totals])
    supply_s = norm([t["supply_risk_penalty"] for t in totals])
    tech_vals = []
    tech_missing = "_tech_missing"
    for t in totals:
        tech_vals.append(t.get("tech_score"))
    tech_known = [v for v in tech_vals if v is not None]
    if tech_known:
        lo, hi = min(tech_known), max(tech_known)
        span = hi - lo
        tech_s = [
            None if v is None else (1.0 if span <= 0 else round((v - lo) / span, 4))
            for v in tech_vals
        ]
    else:
        tech_s = [None] * len(totals)

    scored = []
    for i, t in enumerate(totals):
        axes = {
            "cost": cost_s[i], "schedule": sched_s[i],
            "supply": supply_s[i], "technology": tech_s[i],
        }
        tbd_axes = sorted(a for a, v in axes.items() if v is None)
        complete = not tbd_axes
        score = round(sum(
            float(weights.get(a, 0.0)) * (v if v is not None else 0.0)
            for a, v in axes.items()
        ), 4)
        scored.append({
            "option_id": t["option_id"],
            "business_id": t["business_id"],
            "axes": axes,
            "tbd_axes": tbd_axes,
            "complete": complete,
            "score": score if complete else None,
            "partial_score": None if complete else score,
        })
    return scored


def _amortize(t: dict, volumes: list[int]) -> list[dict]:
    """NRE-도화된 총단가 곡선: unit + NRE/volume over the volume grid.

    TBD in either term marks the whole curve null for that option —
    the acceptance rule forbids computing TBD as zero.
    """
    if t["nre_total"] is None or t["unit_cost_total"] is None:
        return [{"volume": v, "total_cost": None} for v in volumes]
    return [
        {"volume": v, "total_cost": round(t["unit_cost_total"] + t["nre_total"] / v, 6)}
        for v in volumes
    ]


def _breakeven(mine: list[dict], other: list[dict]) -> int | None:
    """First grid volume where `mine`'s total drops below `other`'s."""
    for a, b in zip(mine, other):
        if a["total_cost"] is None or b["total_cost"] is None:
            continue
        if a["total_cost"] <= b["total_cost"]:
            return a["volume"]
    return None


def compute_trade_study(options: list, weights: dict, annual_volume: int) -> dict:
    """Full study body stored in TradeStudy.result (see model docstring)."""
    weights = weights or {"cost": 0.4, "schedule": 0.2, "technology": 0.2, "supply": 0.2}
    wsum = sum(float(v) for v in weights.values())
    if wsum <= 0:
        raise ValueError("trade study weights must sum to a positive number")
    weights = {k: float(v) / wsum for k, v in weights.items()}

    base = [option_totals(o, "base") for o in options]
    best = [option_totals(o, "best") for o in options]
    worst = [option_totals(o, "worst") for o in options]
    for t, o in zip(base, options):
        t["tech_score"] = o.tech_score

    lo = max(1, min((o.moq or 1000) for o in options))
    hi = max(int(annual_volume) * 10, lo * 10)
    grid = sorted({round(lo * (hi / lo) ** (i / 11)) for i in range(12)})

    scored = _score(base, weights)

    curves = {t["option_id"]: _amortize(t, grid) for t in base}
    complete = [t for t in base if t["nre_total"] is not None and t["unit_cost_total"] is not None]
    breakevens: dict = {}
    for t in base:
        others = [o for o in complete if o["option_id"] != t["option_id"]]
        if not others or t["option_id"] not in curves or curves[t["option_id"]][0]["total_cost"] is None:
            breakevens[t["option_id"]] = None
            continue
        cheapest_other = min(others, key=lambda o: o["unit_cost_total"] + o["nre_total"] / grid[-1])
        breakevens[t["option_id"]] = _breakeven(curves[t["option_id"]], curves[cheapest_other["option_id"]])

    per_option = []
    for i, t in enumerate(base):
        per_option.append({
            **t,
            "scenarios": {
                "best": {"unit_cost_total": best[i]["unit_cost_total"]},
                "base": {"unit_cost_total": base[i]["unit_cost_total"]},
                "worst": {"unit_cost_total": worst[i]["unit_cost_total"]},
            },
            "tech_score": t["tech_score"],
            "score": scored[i],
            "amortized": curves[t["option_id"]],
            "breakeven_volume_vs_cheapest": breakevens[t["option_id"]],
            "annual_volume_cost": (
                round(t["unit_cost_total"] * annual_volume + t["nre_total"], 2)
                if t["unit_cost_total"] is not None and t["nre_total"] is not None
                else None
            ),
        })

    ranked = sorted(
        per_option,
        key=lambda p: (p["score"]["score"] is None, -(p["score"]["score"] or p["score"]["partial_score"] or 0)),
    )
    return {
        "tool_version": TOOL_VERSION,
        "weights": weights,
        "annual_volume": annual_volume,
        "volume_grid": grid,
        "per_option": per_option,
        "ranking": [p["option_id"] for p in ranked],
        "tbd_note": (
            "TBD 항목은 0으로 계산되지 않습니다 — 해당 옵션의 합계/축은 null로 "
            "표시되고 부분 점수는 partial_score로만 제공됩니다."
        ),
    }
