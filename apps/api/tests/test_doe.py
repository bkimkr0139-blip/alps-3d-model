"""AN-04 DOE / optimization: response-surface regression + candidate ranking
over already-persisted process-run/CTQ data (지시서 §7 AN-04, FR-06 lite).

Pure-math tests use a synthetic dataset with a KNOWN linear relationship so
the fitted sensitivity/intercept can be asserted to a tight tolerance — not
just "the endpoint returns 200". Endpoint tests reuse the same synthetic
linear relationship end-to-end over real persisted ProcessRun/TestRun rows.
"""

import pytest

from app.doe import candidate_grid, fit_response_surface, rank_candidates
from app.security import CurrentUser

from .conftest import ARCHITECT, MECH_ENGINEER, as_user
from .test_process_twin import _cavity, _inspection, _lot, _mold, _operation, _process_run, _variant

# a role deliberately NOT in doe.CAN_RUN_DOE, for the 403 test
TEST_ENGINEER = CurrentUser(subject="test-tst", username="test.tst", roles=frozenset({"test_emc_engineer"}))


# -- pure regression math -----------------------------------------------------------


def test_fit_response_surface_recovers_known_linear_slope():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [2.0 * x + 10.0 for x in xs]  # exact, noiseless: slope=2, intercept=10
    fit = fit_response_surface(xs, ys)
    assert fit["slope"] == pytest.approx(2.0, abs=1e-6)
    assert fit["intercept"] == pytest.approx(10.0, abs=1e-6)
    assert fit["r_squared"] == pytest.approx(1.0, abs=1e-6)
    assert fit["direction"] == "increasing"
    assert fit["n_observations"] == 5


def test_fit_response_surface_decreasing_direction():
    xs = [0.09, 0.10, 0.11, 0.12]
    ys = [-3.0 * x + 50.0 for x in xs]
    fit = fit_response_surface(xs, ys)
    assert fit["slope"] == pytest.approx(-3.0, abs=1e-6)
    assert fit["direction"] == "decreasing"


def test_fit_response_surface_tolerates_noise_sign_still_correct():
    xs = [0.09, 0.10, 0.11, 0.12, 0.13]
    ys = [1000.0 * x + 210.0 + n for x, n in zip(xs, [0.3, -0.2, 0.1, -0.1, 0.2])]
    fit = fit_response_surface(xs, ys)
    assert fit["slope"] == pytest.approx(1000.0, abs=20.0)
    assert fit["direction"] == "increasing"
    assert fit["r_squared"] > 0.99


def test_fit_response_surface_rejects_insufficient_observations():
    with pytest.raises(ValueError, match="at least"):
        fit_response_surface([1.0, 2.0], [1.0, 2.0])


def test_fit_response_surface_rejects_zero_variance_parameter():
    with pytest.raises(ValueError, match="no variance"):
        fit_response_surface([5.0, 5.0, 5.0], [1.0, 2.0, 3.0])


def test_candidate_grid_evenly_spaced_inclusive():
    assert candidate_grid(0.0, 1.0, 5) == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0])
    assert candidate_grid(0.0, 1.0, 1) == []
    assert candidate_grid(1.0, 1.0, 5) == []


def test_rank_candidates_prefers_in_window_and_on_target():
    fit = {"slope": 2.0, "intercept": 0.0}  # predicted = 2*x
    candidates_in = [
        {"parameter_value": -1.0, "source": "grid"},  # y=-2, outside window[0,10]
        {"parameter_value": 0.0, "source": "grid"},  # y=0, in window, off target
        {"parameter_value": 5.0, "source": "observed"},  # y=10, in window, meets target [8,12]
        {"parameter_value": 6.0, "source": "grid"},  # y=12, in window, meets target
        {"parameter_value": 10.0, "source": "grid"},  # y=20, in window, off target
    ]
    ranked = rank_candidates(
        fit, candidates_in, window_min=0.0, window_max=10.0, target_min=8.0, target_max=12.0
    )
    # every candidate ranked, ranks are a permutation of 1..N
    assert sorted(c["rank"] for c in ranked) == [1, 2, 3, 4, 5]
    # the out-of-window candidate must rank last regardless of its predicted value
    assert max(ranked, key=lambda c: c["rank"])["parameter_value"] == -1.0
    # the two on-target, in-window candidates must outrank the off-target ones
    top_two = {c["parameter_value"] for c in sorted(ranked, key=lambda c: c["rank"])[:2]}
    assert top_two == {5.0, 6.0}
    for c in ranked:
        assert c["meets_target"] == (8.0 <= c["predicted_ctq"] <= 12.0)
        expected_in_window = 0.0 <= c["parameter_value"] <= 10.0
        assert c["in_window"] == expected_in_window


def test_rank_candidates_without_target_sorts_by_value_and_leaves_rank_none():
    fit = {"slope": 1.0, "intercept": 0.0}
    candidates_in = [{"parameter_value": v, "source": "grid"} for v in [3.0, 1.0, 2.0]]
    ranked = rank_candidates(fit, candidates_in, window_min=None, window_max=None, target_min=None, target_max=None)
    assert [c["parameter_value"] for c in ranked] == [1.0, 2.0, 3.0]
    assert all(c["rank"] is None and c["meets_target"] is None for c in ranked)


# -- endpoint: response surface + candidates over real persisted data --------------


def _doe_fixture(client, db_session, suffix: str = "DOE"):
    """4 lots on one operation with a KNOWN exact linear relationship between
    dome_thickness_mm (actual) and F–S peak (mN): peak = 1000*x + 210. The 4th
    lot's thickness (0.145) is outside the operation's approved window
    (0.07–0.13) — a real recorded constraint violation, not fabricated."""
    variant_id = _variant(client, suffix)
    mold = _mold(client, f"MOLD-{suffix}")
    cavity = _cavity(client, mold["id"], f"CAV-{suffix}", 1, "C1")
    op = _operation(client, f"OP-{suffix}", 10, 0.07, 0.13)

    specs = [
        ("A", 0.09, 300.0),
        ("B", 0.10, 310.0),
        ("C", 0.11, 320.0),
        ("D", 0.145, 355.0),  # out of window
    ]
    for tag, thickness, peak in specs:
        bid = f"LOT-{suffix}-{tag}"
        lot = _lot(client, variant_id, mold["id"], cavity["id"], bid, material="MAT-1")
        _process_run(client, lot["id"], op["id"], f"PR-{suffix}-{tag}", {"dome_thickness_mm": thickness})
        _inspection(client, db_session, variant_id, lot["id"], f"{suffix}-{tag}", [peak])
    return variant_id, op


def test_doe_study_fits_exact_linear_relationship_and_flags_violation(client, db_session):
    variant_id, op = _doe_fixture(client, db_session)
    as_user(client, MECH_ENGINEER)
    resp = client.post(
        "/api/v1/doe-studies",
        json={
            "business_id": "DOE-STUDY-1",
            "variant_id": variant_id,
            "operation_id": op["id"],
            "parameter": "dome_thickness_mm",
            "metric": "peak",
            "target_band": {"min": 260, "max": 360, "unit": "mN"},
            "candidate_grid_size": 5,
        },
    )
    as_user(client, ARCHITECT)
    assert resp.status_code == 201, resp.text
    study = resp.json()

    fit = study["fit"]
    assert fit["n_observations"] == 4
    assert fit["slope"] == pytest.approx(1000.0, abs=1.0)
    assert fit["intercept"] == pytest.approx(210.0, abs=1.0)
    assert fit["r_squared"] > 0.999
    assert fit["direction"] == "increasing"
    assert study["parameter_unit"] == "mm"
    assert study["metric_unit"] == "mN"
    assert study["target_band"]["source"] == "데모 사양·합성 데이터" or "합성" in study["target_band"]["source"]

    # the one out-of-window run is surfaced as a constraint violation
    assert len(study["constraint_violations"]) == 1
    violation = study["constraint_violations"][0]
    assert violation["process_run_business_id"] == "PR-DOE-D"
    assert violation["parameter_value"] == pytest.approx(0.145)
    assert violation["out_of_window"] is True

    candidates = study["candidates"]
    observed = {round(c["parameter_value"], 3): c for c in candidates if c["source"] == "observed"}
    assert set(observed) == {0.09, 0.10, 0.11, 0.145}
    # the out-of-window observed candidate is flagged even though it's in the data
    assert observed[0.145]["in_window"] is False
    for x in (0.09, 0.10, 0.11):
        assert observed[x]["in_window"] is True
    # fitted prediction matches the real observation almost exactly (near-noiseless fixture)
    assert observed[0.11]["predicted_ctq"] == pytest.approx(320.0, abs=1.0)

    # grid candidates stay within the approved window (no window bound given → grid
    # would fall back to observed range instead, so this also exercises the window path)
    grid = [c for c in candidates if c["source"] == "grid"]
    assert grid, "expected grid candidates across the approved window"
    for c in grid:
        assert 0.07 - 1e-9 <= c["parameter_value"] <= 0.13 + 1e-9
        assert c["in_window"] is True

    # ranking: an in-window candidate must outrank the out-of-window one even
    # though both meet the demo target band (§AN-04: never silently prefer an
    # out-of-window setting just because its predicted CTQ looks good)
    best = min(candidates, key=lambda c: c["rank"])
    assert best["in_window"] is True

    assert "확인" in study["disclaimer"] or "check" in study["disclaimer"].lower()


def test_doe_study_requires_at_least_three_observations(client, db_session):
    variant_id = _variant(client, "DOE2")
    mold = _mold(client, "MOLD-DOE2")
    cavity = _cavity(client, mold["id"], "CAV-DOE2", 1, "C1")
    op = _operation(client, "OP-DOE2", 10, 0.07, 0.13)
    for tag, thickness, peak in (("A", 0.09, 300.0), ("B", 0.10, 310.0)):
        lot = _lot(client, variant_id, mold["id"], cavity["id"], f"LOT-DOE2-{tag}")
        _process_run(client, lot["id"], op["id"], f"PR-DOE2-{tag}", {"dome_thickness_mm": thickness})
        _inspection(client, db_session, variant_id, lot["id"], f"DOE2-{tag}", [peak])

    resp = client.post(
        "/api/v1/doe-studies",
        json={
            "business_id": "DOE-STUDY-2",
            "variant_id": variant_id,
            "operation_id": op["id"],
            "parameter": "dome_thickness_mm",
        },
    )
    assert resp.status_code == 422
    assert "at least" in resp.text


def test_doe_study_unknown_variant_or_operation_404(client, db_session):
    variant_id, op = _doe_fixture(client, db_session, "DOE3")
    import uuid

    resp = client.post(
        "/api/v1/doe-studies",
        json={
            "business_id": "DOE-STUDY-3",
            "variant_id": str(uuid.uuid4()),
            "operation_id": op["id"],
            "parameter": "dome_thickness_mm",
        },
    )
    assert resp.status_code == 404

    resp = client.post(
        "/api/v1/doe-studies",
        json={
            "business_id": "DOE-STUDY-4",
            "variant_id": variant_id,
            "operation_id": str(uuid.uuid4()),
            "parameter": "dome_thickness_mm",
        },
    )
    assert resp.status_code == 404


def test_doe_study_get_and_list(client, db_session):
    variant_id, op = _doe_fixture(client, db_session, "DOE5")
    created = client.post(
        "/api/v1/doe-studies",
        json={
            "business_id": "DOE-STUDY-5",
            "variant_id": variant_id,
            "operation_id": op["id"],
            "parameter": "dome_thickness_mm",
        },
    ).json()

    fetched = client.get(f"/api/v1/doe-studies/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["business_id"] == "DOE-STUDY-5"

    listed = client.get(f"/api/v1/twins/{variant_id}/doe-studies").json()
    assert [s["business_id"] for s in listed] == ["DOE-STUDY-5"]


# -- RBAC ----------------------------------------------------------------------------


def test_doe_study_requires_manufacturing_or_engineering_role(client, db_session):
    variant_id, op = _doe_fixture(client, db_session, "DOE6")
    as_user(client, TEST_ENGINEER)
    resp = client.post(
        "/api/v1/doe-studies",
        json={
            "business_id": "DOE-STUDY-6",
            "variant_id": variant_id,
            "operation_id": op["id"],
            "parameter": "dome_thickness_mm",
        },
    )
    assert resp.status_code == 403
    as_user(client, ARCHITECT)
