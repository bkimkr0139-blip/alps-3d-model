"""ASIC Twin v1.1 backend tests (EPIC A·E·F·G — 고도화지시서 §4/§7/§8).

Pinned here: the equipment-import parser records facts (partial file, time
reversal, duplicates) and never silently fixes them; the same raw file can
never become two runs; gate blockers (CALIBRATION_EXPIRED / MODEL_OOD /
QUAL_FAILURE_OPEN / MOCK_RESULT_PRESENT) appear exactly when their evidence
does, with the qual matrix reading latest-row-per-group; the FA→RCA→ECO
closed loop refuses to close without regression + verification evidence; and
every write sits behind its role gate.

Every test stands alone (tables are truncated between tests) — no ordering.
"""

import io

from fastapi.testclient import TestClient

from tests.conftest import (
    APPROVER,
    ARCHITECT,
    ASIC_ENGINEER,
    QUALITY_ENGINEER,
    TEST_ENGINEER,
    as_user,
)

TPL = "current_sensor"
CSV_OK = "name,value,unit,site,ts\nsensitivity,99.98,mA/A,1,2026-09-01T02:00:00Z\n"

BLOCKS = [
    {
        "key": "shunt",
        "kind": "sensor",
        "label": "Shunt 1 mOhm",
        "params": {"nominal": 100.0, "calib_min": -40.0, "calib_max": 125.0},
        "error_budget": {"offset": 0.08, "noise": 0.25},
    },
    {
        "key": "adc",
        "kind": "mixed",
        "label": "SAR ADC",
        "params": {"bits": 16},
        "error_budget": {"inl": 0.15},
    },
]
SPEC = [{"output": "sensitivity", "nominal": 100.0, "min": 98.5, "max": 101.5, "unit": "mA/A"}]


def _import_run(client: TestClient, bid: str, csv_bytes: bytes | None = None,
                calib: str = "2027-06-30T00:00:00Z") -> dict:
    # distinct bytes per run — identical bytes are a 409 by design (dedup)
    if csv_bytes is None:
        marker = int.from_bytes(bid.encode(), "big") % 10**9
        csv_bytes = (CSV_OK + f"marker,{marker}\n").encode()
    with as_user(client, TEST_ENGINEER):  # CAN_IMPORT
        resp = client.post(
            "/api/v1/asic/measurement-runs/import",
            files={"file": ("run.csv", io.BytesIO(csv_bytes), "text/csv")},
            data={
                "business_id": bid,
                "template_id": TPL,
                "equipment_id": "T2000-01",
                "equipment_type": "sem_tester",
                "calibration_expires_at": calib,
                "executed_at": "2026-09-01T02:00:00Z",
            },
        )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _chain(client: TestClient, bid: str = "ASIC-T-CHAIN", calib_max: float = 125.0) -> dict:
    blocks = [
        {**b, "params": {**b["params"], "calib_max": calib_max}} if "calib_max" in b["params"] else b
        for b in BLOCKS
    ]
    with as_user(client, ARCHITECT):  # CAN_DESIGN
        resp = client.post(
            "/api/v1/asic/signal-chains",
            json={"business_id": bid, "template_id": TPL, "blocks": blocks},
        )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _study(client: TestClient, chain_id: str, bid: str = "ASIC-T-MC", seed: int = 42) -> dict:
    with as_user(client, ARCHITECT):  # CAN_DESIGN
        resp = client.post(
            "/api/v1/asic/corner-studies",
            json={
                "business_id": bid,
                "signal_chain_id": chain_id,
                "kind": "monte_carlo",
                "n_draws": 100,
                "seed": seed,
                "spec": SPEC,
            },
        )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _qual_plan(client: TestClient, bid: str = "ASIC-T-QUAL") -> dict:
    with as_user(client, ARCHITECT):  # CAN_QUAL
        resp = client.post(
            "/api/v1/asic/qualification-plans",
            json={"business_id": bid, "template_id": TPL, "grade": "G1"},
        )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _qual_row(client: TestClient, plan_id: str, bid: str, group: str, status: str, **extra) -> dict:
    with as_user(client, ARCHITECT):  # CAN_QUAL
        resp = client.post(
            f"/api/v1/asic/qualification-plans/{plan_id}/results",
            json={
                "business_id": bid,
                "group": group,
                "method": "AEC-Q100 HTSL (demo)",
                "condition": {"temp_c": 125, "duration_h": 1000},
                "samples": "1 lot",
                "status": status,
                **extra,
            },
        )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _fa_case(client: TestClient, bid: str = "ASIC-T-FA", observations: bool = True) -> dict:
    with as_user(client, ASIC_ENGINEER):  # CAN_FA
        resp = client.post(
            "/api/v1/asic/fa-cases",
            json={
                "business_id": bid,
                "template_id": TPL,
                "scope": "lot",
                "lot_ref": "T-LOT-1",
                "symptom": "demo symptom",
                **({"observations": [{"fact": "site 3 drifted", "source": "bench"}]} if observations else {}),
            },
        )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _post_root_cause(client: TestClient, case_id: str, payload: dict):
    with as_user(client, ASIC_ENGINEER):  # CAN_FA
        return client.post(f"/api/v1/asic/fa-cases/{case_id}/root-cause", json=payload)


def _approve_rca(client: TestClient, case: dict, evidence_bid: str) -> None:
    resp = _post_root_cause(client, case["id"], {
        "root_cause": "rc", "cause_class": "package",
        "evidence_business_ids": [evidence_bid],
    })
    assert resp.status_code == 200, resp.text


def _gate(client: TestClient) -> dict:
    resp = client.get(f"/api/v1/asic/gate-report/{TPL}")
    assert resp.status_code == 200
    return resp.json()


def _blocker_codes(report: dict) -> list[str]:
    return sorted(b["code"] for b in report["blockers"])


# ── parser facts (EPIC E) ───────────────────────────────────────────────────


def test_parser_records_facts_and_never_fixes():
    from app.routers.asic import _parse_measurement_csv

    messy = (
        # no trailing newline → partial_file
        "name,value,unit,site,ts,temperature_c\n"
        "sensitivity,99.9,mA/A,1,2026-09-01T02:00:00Z,\n"
        "offset,12.5,uV,1,2026-09-01T02:01:00Z,25.0\n"
        # duplicate (name, site)
        "offset,12.5,uV,1,2026-09-01T02:02:00Z,25.0\n"
        # unparseable value
        "gain,x,mA/A,2,2026-09-01T02:03:00Z,\n"
        # unparseable temperature
        "gain,1.2,mA/A,2,2026-09-01T02:04:00Z,hot\n"
        # time reversal + incomplete row, then EOF mid-row
        "gain,1.3,mA/A,2,2026-09-01T01:00:00Z,\n"
        "gain,1.4,mA/A,2"
    )
    points, findings = _parse_measurement_csv(messy.encode())
    codes = [f["code"] for f in findings]
    assert "partial_file" in codes
    assert "duplicate_block" in codes
    assert "unparseable_value" in codes
    assert "unparseable_temperature" in codes
    assert "time_reversal" in codes
    assert "partial_row" in codes
    # parseable rows survive untouched — never silently repaired away
    assert len(points) >= 3

    clean_points, clean_findings = _parse_measurement_csv(CSV_OK.encode())
    assert clean_findings == []
    assert len(clean_points) == 1
    assert clean_points[0]["value"] == 99.98


def test_same_file_never_becomes_two_runs(client: TestClient):
    csv_bytes = CSV_OK.encode()
    first = _import_run(client, "ASIC-T-RUN-A", csv_bytes)
    resp = client.post(
        "/api/v1/asic/measurement-runs/import",
        files={"file": ("run.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={
            "business_id": "ASIC-T-RUN-B",  # different business_id, SAME bytes
            "template_id": TPL,
            "equipment_id": "T2000-01",
            "equipment_type": "sem_tester",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["existing_business_id"] == first["business_id"]


# ── gate policy (EPIC A + E + F) ────────────────────────────────────────────


def test_empty_template_blocks_on_mock_and_starts_ladder_bottom(client: TestClient):
    report = _gate(client)
    assert "MOCK_RESULT_PRESENT" in _blocker_codes(report)
    assert report["status"] == "blocked"
    assert report["policy_version"] == "alps-asic-v1.1"
    assert report["readiness"] == "education_only"
    assert report["readiness_reachable"] is True


def test_calibration_expired_blocker_tracks_evidence(client: TestClient):
    _import_run(client, "ASIC-T-CAL-OK", calib="2030-01-01T00:00:00Z")
    assert "CALIBRATION_EXPIRED" not in _blocker_codes(_gate(client))
    _import_run(client, "ASIC-T-CAL-EXPIRED", calib="2020-01-01T00:00:00Z")
    report = _gate(client)
    assert "CALIBRATION_EXPIRED" in _blocker_codes(report)
    blocker = next(b for b in report["blockers"] if b["code"] == "CALIBRATION_EXPIRED")
    assert "ASIC-T-CAL-EXPIRED" in blocker["evidence"]
    assert "ASIC-T-CAL-OK" not in blocker["evidence"]


def test_model_ood_blocker_and_histogram_reproducible(client: TestClient):
    chain = _chain(client, calib_max=100.0)  # G1 corner at 125°C leaves the range
    study = _study(client, chain["id"])
    assert study["result"]["model_ood"] is True
    assert study["result"]["ood_reason"]
    # the real sampled distribution, not a client-invented one
    per_out = study["result"]["per_output"][0]
    assert len(per_out["hist"]["edges"]) == 25
    assert len(per_out["hist"]["counts"]) == 24
    assert sum(per_out["hist"]["counts"]) == study["result"]["n_draws_total"]
    # same seed → identical quantiles + histogram (§12 reproducibility)
    replay = _study(client, chain["id"], bid="ASIC-T-MC-REPLAY", seed=study["seed"])
    assert replay["result"]["per_output"][0]["p50"] == per_out["p50"]
    assert replay["result"]["per_output"][0]["hist"]["counts"] == per_out["hist"]["counts"]

    assert "MODEL_OOD" in _blocker_codes(_gate(client))


def test_qual_matrix_reads_latest_row_per_group(client: TestClient):
    plan = _qual_plan(client)
    case = _fa_case(client, bid="ASIC-T-FA-QUAL")
    # the failure is linked to an FA case but the RCA is not yet approved → open
    _qual_row(client, plan["id"], "ASIC-T-Q-HTSL-V1", "HTSL", "fail", fa_case_id=case["id"])
    report = _gate(client)
    assert "QUAL_FAILURE_OPEN" in _blocker_codes(report)
    # no runs/studies yet → ladder bottom regardless of the qual matrix state
    assert report["readiness"] == "education_only"

    # approving the RCA dispositions the failure (append-only: the fail row
    # is never overwritten — the FA case moves to rca_approved)
    _approve_rca(client, case, "ASIC-T-Q-HTSL-V1")
    assert "QUAL_FAILURE_OPEN" not in _blocker_codes(_gate(client))

    # the GROUP verdict still fails (latest HTSL row = fail) until the retest…
    _import_run(client, "ASIC-T-RUN-DEPTH")
    chain = _chain(client, "ASIC-T-CHAIN-DEPTH")
    _study(client, chain["id"], bid="ASIC-T-MC-DEPTH")
    assert _gate(client)["readiness"] == "validated_shadow"

    # …and the retest (append-only history) supersedes the fail: latest row
    # per group wins, so the matrix completes
    _qual_row(client, plan["id"], "ASIC-T-Q-HTSL-V2", "HTSL", "pass")
    assert _gate(client)["readiness"] == "controlled_pilot"


# ── FA → RCA → ECO closed loop (EPIC G) ─────────────────────────────────────


def test_rca_approval_records_event_and_blocks_re_approval(client: TestClient):
    case = _fa_case(client)
    plan = _qual_plan(client)
    _qual_row(client, plan["id"], "ASIC-T-Q-EVID", "HTSL", "fail")

    resp = _post_root_cause(client, case["id"], {"root_cause": "demo root cause",
                                                 "cause_class": "package",
                                                 "evidence_business_ids": ["ASIC-T-Q-EVID"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["root_cause_confirmed"] is True
    assert body["status"] == "rca_approved"
    # append-only event ledger records the human approval
    events = client.get(f"/api/v1/asic/fa-cases/{case['id']}/events").json()
    assert any(e["event_type"] == "rca_approved" for e in events)

    # re-approval is a conflict
    resp = _post_root_cause(client, case["id"], {"root_cause": "demo root cause",
                                                 "cause_class": "package",
                                                 "evidence_business_ids": ["ASIC-T-Q-EVID"]})
    assert resp.status_code == 409


def test_rca_guards(client: TestClient):
    no_obs = _fa_case(client, bid="ASIC-T-FA-NOOBS", observations=False)
    resp = _post_root_cause(client, no_obs["id"], {
        "root_cause": "x", "cause_class": "package", "evidence_business_ids": ["E1"]})
    assert resp.status_code == 422

    case = _fa_case(client, bid="ASIC-T-FA-GUARD")
    resp = _post_root_cause(client, case["id"], {
        "root_cause": "x", "cause_class": "package", "evidence_business_ids": []})
    assert resp.status_code == 422
    resp = _post_root_cause(client, case["id"], {
        "root_cause": "x", "cause_class": "package", "evidence_business_ids": ["NOPE-404"]})
    assert resp.status_code == 422
    assert "NOPE-404" in resp.json()["detail"]["unresolved"]


def test_eco_close_requires_regression_and_verification(client: TestClient):
    plan = _qual_plan(client)
    _qual_row(client, plan["id"], "ASIC-T-Q-ECO-EVID", "HTSL", "fail")
    case = _fa_case(client, bid="ASIC-T-FA-ECO")
    _approve_rca(client, case, "ASIC-T-Q-ECO-EVID")

    # trigger=fa_case requires an RCA-approved case
    fresh = _fa_case(client, bid="ASIC-T-FA-FRESH")
    resp = client.post(
        "/api/v1/asic/ecos",
        json={
            "business_id": "ASIC-T-ECO-FRESH",
            "template_id": TPL,
            "fa_case_business_id": fresh["business_id"],
            "trigger": "fa_case",
            "title": "must fail",
        },
    )
    assert resp.status_code == 422

    with as_user(client, ARCHITECT):  # CAN_ECO
        resp_eco = client.post(
            "/api/v1/asic/ecos",
            json={
                "business_id": "ASIC-T-ECO",
                "template_id": TPL,
                "fa_case_business_id": case["business_id"],
                "trigger": "fa_case",
                "title": "demo fix",
                "design_rev_from": "A0",
                "design_rev_to": "A1",
            },
        )
    assert resp_eco.status_code == 201, resp_eco.text
    eco = resp_eco.json()
    assert eco["status"] == "open"

    # closing with no regression evidence → 412 (수용기준: ECO 완료만으로 종결 불가)
    resp = client.post(
        f"/api/v1/asic/ecos/{eco['id']}/close",
        json={"verification_run_business_id": "ASIC-T-VERIFY", "verification_note": "n"},
    )
    assert resp.status_code == 412

    # regression ids must resolve to real evidence
    resp = client.post(
        f"/api/v1/asic/ecos/{eco['id']}/regression",
        json={"regression_run_ids": ["GHOST-RUN"]},
    )
    assert resp.status_code == 422

    verify_run = _import_run(client, "ASIC-T-VERIFY")
    with as_user(client, ARCHITECT):
        resp = client.post(
            f"/api/v1/asic/ecos/{eco['id']}/regression",
            json={"regression_run_ids": [verify_run["business_id"]]},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "regression_pending"

    with as_user(client, ARCHITECT):  # CAN_ECO_CLOSE
        resp = client.post(
            f"/api/v1/asic/ecos/{eco['id']}/close",
            json={
                "verification_run_business_id": verify_run["business_id"],
                "verification_note": "site 3 back in spec",
            },
        )
    assert resp.status_code == 200
    closed = resp.json()
    assert closed["status"] == "closed"
    assert closed["closed_at"] is not None
    # the FA case follows the ECO to verified — the loop closes
    fa_after = client.get(f"/api/v1/asic/templates/{TPL}/fa-cases").json()
    assert next(f for f in fa_after if f["id"] == case["id"])["status"] == "verified"
    # closing twice is a conflict
    resp = client.post(
        f"/api/v1/asic/ecos/{eco['id']}/close",
        json={"verification_run_business_id": verify_run["business_id"], "verification_note": "n"},
    )
    assert resp.status_code == 409


# ── RBAC ────────────────────────────────────────────────────────────────────


def test_write_roles_are_gated(client: TestClient):
    # import: test_emc_engineer ok, quality_engineer not
    with as_user(client, TEST_ENGINEER):
        resp = client.post(
            "/api/v1/asic/measurement-runs/import",
            files={"file": ("r.csv", io.BytesIO(CSV_OK.encode()), "text/csv")},
            data={
                "business_id": "ASIC-T-RBAC-RUN",
                "template_id": TPL,
                "equipment_id": "T2000-02",
                "equipment_type": "sem_tester",
            },
        )
        assert resp.status_code == 201, resp.text

    def _post_as(user, path, payload):
        with as_user(client, user):
            return client.post(path, json=payload)

    assert _post_as(QUALITY_ENGINEER, "/api/v1/asic/signal-chains",
                    {"business_id": "ASIC-T-RBAC-X", "template_id": TPL, "blocks": BLOCKS}).status_code == 403
    assert _post_as(TEST_ENGINEER, "/api/v1/asic/qualification-plans",
                    {"business_id": "ASIC-T-RBAC-Q", "template_id": TPL, "grade": "G1"}).status_code == 403
    # RCA is electrical/quality only — test_emc is not; a passing role still
    # hits the evidence guard (422), proving role ≠ guard
    case = _fa_case(client, bid="ASIC-T-FA-RBAC")
    assert _post_as(TEST_ENGINEER, f"/api/v1/asic/fa-cases/{case['id']}/root-cause",
                    {"root_cause": "rc", "cause_class": "design",
                     "evidence_business_ids": ["E"]}).status_code == 403
    assert _post_as(ASIC_ENGINEER, f"/api/v1/asic/fa-cases/{case['id']}/root-cause",
                    {"root_cause": "rc", "cause_class": "design",
                     "evidence_business_ids": []}).status_code == 422
    # ECO close is architect/reviewer only
    close_body = {"verification_run_business_id": "V", "verification_note": "n"}
    assert _post_as(ASIC_ENGINEER, "/api/v1/asic/ecos/00000000-0000-0000-0000-000000000000/close",
                    close_body).status_code == 403
    assert _post_as(APPROVER, "/api/v1/asic/ecos/00000000-0000-0000-0000-000000000000/close",
                    close_body).status_code == 404
