"""GOLD scenario catalog — the single source of truth (C9).

지시서 §11.2's validation scenarios as DETERMINISTIC tick trajectories.
The seed script references scenario ids when submitting replay runs; the
worker's replay branch executes them via signal_chain.run_replay; the
replay artifacts embed BOTH the expected bounds (from here) and the actual
measured verdicts, so a reviewer never has to trust the UI's rendering of
pass/fail.

Every trajectory is an explicit tick list (20 Hz, disclosed) — no hidden
parametric motion. Scenario engine defaults: ``surrogate`` (the tier the
browser actually runs interactively) except where fidelity demands the
solver (GOLD-06's ground-plate geometry is OUTSIDE the surrogate's training
geometry — running it through the surrogate would silently extrapolate a
structure it has never seen).
"""

from __future__ import annotations

GOLD_SEED = 20260914


def _approach(
    x_mm: float,
    y_mm: float,
    gap_from: float,
    gap_to: float,
    n: int,
    is_glove: bool = False,
) -> list[dict]:
    """Linear gap ramp gap_from → gap_to over n ticks."""
    return [
        {
            "x_mm": x_mm,
            "y_mm": y_mm,
            "gap_mm": round(gap_from + (gap_to - gap_from) * i / (n - 1), 3),
            "is_glove": is_glove,
        }
        for i in range(n)
    ]


def _hold(x_mm: float, y_mm: float, gap_mm: float, n: int, is_glove: bool = False) -> list[dict]:
    return [{"x_mm": x_mm, "y_mm": y_mm, "gap_mm": gap_mm, "is_glove": is_glove} for _ in range(n)]


def _retreat(x_mm: float, y_mm: float, gap_from: float, gap_to: float, n: int) -> list[dict]:
    return _approach(x_mm, y_mm, gap_from, gap_to, n)


def scenario_gold01() -> dict:
    """중앙 접근/후퇴: full detect cycle over the electrode center."""
    ticks = (
        _hold(0.0, 0.0, 28.0, 6)
        + _approach(0.0, 0.0, 28.0, 0.0, 30)
        + _hold(0.0, 0.0, 0.0, 10)
        + _retreat(0.0, 0.0, 0.0, 28.0, 30)
        + _hold(0.0, 0.0, 28.0, 6)
    )
    return {
        "id": "GOLD-01-CENTER-APPROACH",
        "description": "중앙 접근/후퇴 — 터치 체인 전체(IDLE→NEAR→TOUCH→IDLE) (지시서 §11.2)",
        "engine": "surrogate",
        "seed": GOLD_SEED,
        "asic_overrides": None,
        "expected": {
            # v2 must complete the full cycle: detect during the approach
            # (well before the touch hold ends) and fully release after retreat.
            "v2.first_nonidle_tick_max": 40,
            "v2.false_trigger_ticks_max": 0,
            "v1.false_trigger_ticks_max": 0,
        },
        "ticks": ticks,
    }


def scenario_gold02() -> dict:
    """가장자리 감도 저하: same approach over the pad EDGE (x = 12 mm)."""
    edge_x = 12.0  # pad radius is ~5.6 mm — 12 mm is fully off-pad
    ticks = (
        _hold(edge_x, 0.0, 28.0, 6)
        + _approach(edge_x, 0.0, 28.0, 0.0, 30)
        + _hold(edge_x, 0.0, 0.0, 10)
        + _retreat(edge_x, 0.0, 0.0, 28.0, 30)
        + _hold(edge_x, 0.0, 28.0, 6)
    )
    return {
        "id": "GOLD-02-EDGE-DEGRADATION",
        "description": f"가장자리(x={edge_x:g}mm, 패드 반경 밖) 감도 저하 — 중앙 대비 늦은 검출 (§11.2)",
        "engine": "surrogate",
        "seed": GOLD_SEED,
        "asic_overrides": None,
        "expected": {
            # Still a clean cycle, but detection must come LATER than the
            # center approach's (the degradation is the demonstrated fact).
            "v2.false_trigger_ticks_max": 0,
        },
        "ticks": ticks,
        "compare_note": "first_nonidle_tick must exceed GOLD-01's — checked in the seed/table, not here",
    }


def scenario_gold03() -> dict:
    """장갑 슬로우: gloved slow approach — sensitivity degrades, touch at
    contact must still register (porous-knit disclosed model)."""
    ticks = (
        _hold(0.0, 0.0, 28.0, 8)
        + _approach(0.0, 0.0, 28.0, 0.0, 40, is_glove=True)
        + _hold(0.0, 0.0, 0.0, 12, is_glove=True)
        + _retreat(0.0, 0.0, 0.0, 28.0, 20)
    )
    return {
        "id": "GOLD-03-GLOVE-SLOW",
        "description": "장갑(다공성 니트, ε1.3 공개 모델) 슬로우 접근 — 감도 저하, 접촉 검출 유지 (§11.2)",
        "engine": "surrogate",
        "seed": GOLD_SEED,
        "asic_overrides": None,
        "expected": {
            "v2.false_trigger_ticks_max": 0,
            # gloved signal is weaker; NEAR may or may not commit, but the
            # absolute TOUCH band must trip at contact
            "v2.missed_ticks_max": 24,
        },
        "ticks": ticks,
    }


def scenario_gold04(split_ring: bool = False) -> dict:
    """노이즈 오타검출 — THE money scenario: finger parked deep-IDLE,
    hostile noise. v1's fixed absolute threshold chatters; v2's
    baseline+debounce must stay silent. The hold gap is per layout so the
    park is genuinely IDLE in both: layout A's solid pad at 12 mm sits
    ~23 counts under the NEAR threshold (surrogate ≈127 counts), but
    layout B's half-rings couple from all sides of the fingertip (≈164
    counts at 12 mm — already NEAR, so a false trigger is undefined).
    At 24 mm the B surrogate reads ≈124 counts — the same ~26-count
    headroom (verified offline: v1 false-triggers 4 ticks, v2 silent)."""
    hold_gap = 24.0 if split_ring else 12.0
    ticks = _hold(0.0, 0.0, hold_gap, 60)
    return {
        "id": "GOLD-04-NOISE-FALSE-TRIGGER",
        "description": (
            f"노이즈 오타검출 — {hold_gap:.0f}mm 홀드+고노이즈(σ50 counts): "
            "v1 오타검출 ≥1, v2 = 0 (§11.2)"
        ),
        "engine": "surrogate",
        "seed": GOLD_SEED,
        "asic_overrides": {"noise_sigma_counts": 50.0},
        "expected": {
            "v1.false_trigger_ticks_min": 1,
            "v2.false_trigger_ticks_max": 0,
            "v2.state_changes_max": 2,
        },
        "ticks": ticks,
    }


def scenario_gold05() -> dict:
    """유효범위 밖 호버 (z=35 > DOE 28): surrogate must FLAG OOD —
    the prediction must never display as a normal result (지시서)."""
    ticks = _hold(0.0, 0.0, 35.0, 20)
    return {
        "id": "GOLD-05-OOD-HOVER",
        "description": "유효범위 밖 호버(gap 35mm > DOE 28mm) — OOD 플래그 필수, 정상 결과 표시 금지 (§11.2)",
        "engine": "surrogate",
        "seed": GOLD_SEED,
        "asic_overrides": None,
        "expected": {"ood_flagged": True},
        "ticks": ticks,
    }


def scenario_gold06() -> dict:
    """금속/접지 영향 (variant B): grounded plate 6 mm above the touch
    surface shunts the field — same approach as GOLD-01 but solved by the
    FD solver on the plate geometry (OUTSIDE surrogate training geometry)."""
    ticks = (
        _hold(0.0, 0.0, 28.0, 6)
        + _approach(0.0, 0.0, 28.0, 0.0, 24)
        + _hold(0.0, 0.0, 0.0, 8)
    )
    return {
        "id": "GOLD-06-GROUND-PLATE",
        "description": "금속/접지판 인접 — 접지 가드에 의한 ΔC 감쇠를 dc 트레이스로 확인, FD 솔버 엔진 (§11.2)",
        "engine": "solver",
        "seed": GOLD_SEED,
        "asic_overrides": None,
        "expected": {"v2.false_trigger_ticks_max": 0},
        "ticks": ticks,
    }


def default_scenarios(split_ring: bool) -> list[dict]:
    """Scenario set for one variant: 01–05 always; 06 only for layout B
    (its guard geometry rides the B seed's ground-plate parameters)."""
    scen = [scenario_gold01(), scenario_gold02(), scenario_gold03(), scenario_gold04(), scenario_gold05()]
    if split_ring:
        scen.append(scenario_gold06())
    return scen


SCENARIO_IDS = [
    "GOLD-01-CENTER-APPROACH",
    "GOLD-02-EDGE-DEGRADATION",
    "GOLD-03-GLOVE-SLOW",
    "GOLD-04-NOISE-FALSE-TRIGGER",
    "GOLD-05-OOD-HOVER",
    "GOLD-06-GROUND-PLATE",
]


def scenario_by_id(scenario_id: str, split_ring: bool = False) -> dict:
    known = {
        s["id"]: s
        for s in (
            scenario_gold01(),
            scenario_gold02(),
            scenario_gold03(),
            scenario_gold04(split_ring=split_ring),
            scenario_gold05(),
            scenario_gold06(),
        )
    }
    if scenario_id not in known:
        raise ValueError(f"unknown scenario {scenario_id!r}; known: {sorted(known)}")
    return known[scenario_id]
