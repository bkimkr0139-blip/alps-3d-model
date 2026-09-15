"""Seeds the golden demo dataset: three ALPS product families (TACT Switch,
Rotary Encoder, MEMS Pressure Sensor), each with an A/B variant pair used as
the regression fixture for the vertical slices (§12.1, §20).

Run against a live stack:
    apps/api/.venv/bin/python scripts/seed_golden_dataset.py

Idempotent: every write carries a fixed Idempotency-Key, so re-running this
script does not create duplicates. The TACT product's business ids and
idempotency keys are unchanged from the original single-product dataset —
re-running against an existing deployment only appends the two new products.
"""

import hashlib
import json
import os
import random
import sys
import time
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
load_dotenv(REPO_ROOT / ".env")

KEYCLOAK_URL = "http://localhost:8081"
API_URL = "http://localhost:8000"
REALM = os.environ.get("KEYCLOAK_REALM", "alps-twin")


def get_token(username: str, password: str) -> str:
    resp = httpx.post(
        f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
        data={
            "client_id": "alps-twin-web",
            "grant_type": "password",
            "username": username,
            "password": password,
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def post(client: httpx.Client, path: str, idem_key: str, body: dict) -> dict:
    resp = client.post(path, json=body, headers={"Idempotency-Key": idem_key})
    if resp.status_code >= 400:
        print(f"FAILED {path}: {resp.status_code} {resp.text}", file=sys.stderr)
        resp.raise_for_status()
    return resp.json()


def upload_and_promote(
    client: httpx.Client, *, business_id: str, kind: str, filename: str, content: bytes
) -> str:
    """Presigned-upload flow (§9.3), returns the promoted artifact_version_id.

    Presigned PUT URLs expire after 1h. Re-running this script after that
    expiry gets a 403 on the PUT; the retry mints a fresh upload (fresh
    Idempotency-Key → new PENDING version + new URL) instead of reusing the
    stale one. Each expired retry leaves one orphaned PENDING artifact_version
    row behind (never promoted, harmless — the API only serves PROMOTED).
    """
    upload = post(
        client,
        "/api/v1/artifacts/uploads",
        idem_key=f"seed-upload-{business_id}",
        body={"business_id": business_id, "kind": kind, "name": business_id, "filename": filename},
    )
    put_resp = httpx.put(upload["upload_url"], content=content)
    if put_resp.status_code >= 400:  # most likely: expired presigned signature
        upload = post(
            client,
            "/api/v1/artifacts/uploads",
            idem_key=f"seed-upload-{business_id}-{uuid.uuid4().hex[:8]}",
            body={"business_id": business_id, "kind": kind, "name": business_id, "filename": filename},
        )
        put_resp = httpx.put(upload["upload_url"], content=content)
    put_resp.raise_for_status()
    promote = client.post(
        f"/api/v1/artifacts/versions/{upload['artifact_version_id']}/promote",
        json={"sha256": hashlib.sha256(content).hexdigest()},
    )
    promote.raise_for_status()
    return upload["artifact_version_id"]


def run_simulation_and_wait(
    client: httpx.Client, *, business_id: str, variant_id: str, run_type: str,
    input_artifact_version_id: str | None = None,
    parameters: dict | None = None, timeout_s: float = 20.0,
    max_attempts: int = 3,
) -> dict:
    """POST a simulation run and poll it to a terminal state.

    A FAILED run is retried under a fresh ``-fxN`` business_id — which is
    also a fresh Idempotency-Key. The idempotency ledger caches the original
    failure response forever, so re-running this seed against a DB that
    recorded a failure under an old, since-fixed worker silently replays the
    stale failure and the section quietly degrades (the 2026-09-15 VAR-AIR
    "Object of type UUID is not JSON serializable" warning was exactly this:
    the worker fix had shipped, but the unsuffixed keys still replayed the
    pre-fix FAILED rows). If every attempt fails, raise — never skip a
    section and leave a half-seeded dataset behind.
    """
    last_error = "no attempt made"
    for attempt in range(1, max_attempts + 1):
        bid = business_id if attempt == 1 else f"{business_id}-fx{attempt - 1}"
        if len(bid) > 64:  # result_metrics.business_id is VARCHAR(64)
            break
        run = post(
            client,
            "/api/v1/simulation-runs",
            idem_key=f"seed-run-{bid}",
            body={
                "business_id": bid,
                "variant_id": variant_id,
                "run_type": run_type,
                **({"input_artifact_version_id": input_artifact_version_id} if input_artifact_version_id else {}),
                **({"parameters": parameters} if parameters else {}),
            },
        )
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            run = client.get(f"/api/v1/simulation-runs/{run['id']}").json()
            if run["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.5)
        if run["status"] not in ("succeeded", "failed"):
            raise TimeoutError(f"simulation run {bid} did not finish within {timeout_s}s")
        if run["status"] == "succeeded":
            return run
        last_error = run.get("error_message") or "failed"
        print(
            f"WARNING: {bid} failed ({last_error[:120]})"
            + ("; retrying fresh" if attempt < max_attempts else ""),
            file=sys.stderr,
        )
    raise RuntimeError(f"simulation run {business_id} failed after retries: {last_error}")


def upload_csv_measurements(
    test_client: httpx.Client, *, test_run_id: str, csv_bytes: bytes, filename: str,
    x_unit: str, y_unit: str,
) -> list[dict]:
    resp = test_client.post(
        f"/api/v1/test-runs/{test_run_id}/measurements",
        files={"file": (filename, csv_bytes, "text/csv")},
        data={"x_unit": x_unit, "y_unit": y_unit},
    )
    if resp.status_code == 409:  # already uploaded by a prior run of this script
        return test_client.get(f"/api/v1/test-runs/{test_run_id}/measurements").json()
    resp.raise_for_status()
    return resp.json()


TACT_REQUIREMENTS = [
    {
        "suffix": "REQ-CLICK",
        "text": "사용자가 누를 때 더 명확한 클릭감(Tactile feedback)을 느껴야 한다.",
        "verification_method": "test",
        "safety_class": "QM",
    },
    {
        "suffix": "REQ-NOFALSE",
        "text": "차량 진동 조건에서 오작동(false trigger)이 발생하지 않아야 한다.",
        "verification_method": "test",
        "safety_class": "ASIL_A",
    },
    {
        "suffix": "REQ-LIFE",
        "text": "지정된 수명(최소 100만 사이클) 동안 접점 저항이 규정 범위 내에 있어야 한다.",
        "verification_method": "test",
        "safety_class": "QM",
    },
]
TACT_COMPONENTS = [
    {"suffix": "CMP-DOME", "name": "Metal Dome"},
    {"suffix": "CMP-HOUSING", "name": "Switch Housing"},
    {"suffix": "CMP-CONTACT", "name": "Contact Pad"},
]

ENCODER_REQUIREMENTS = [
    {
        "suffix": "REQ-DETENT",
        "text": "로터리 인코더 조작 시 일정하고 명확한 디텐트 감각이 느껴져야 한다.",
        "verification_method": "test",
        "safety_class": "QM",
    },
    {
        "suffix": "REQ-NOJITTER",
        "text": "차량 진동 조건에서 출력 채널 오동작(chattering)이 발생하지 않아야 한다.",
        "verification_method": "test",
        "safety_class": "ASIL_A",
    },
    {
        "suffix": "REQ-LIFE",
        "text": "지정된 회전 수명(최소 30만 사이클) 동안 접점 저항이 규정 범위 내에 있어야 한다.",
        "verification_method": "test",
        "safety_class": "QM",
    },
]
ENCODER_COMPONENTS = [
    {"suffix": "CMP-FRAME", "name": "Encoder Frame"},
    {"suffix": "CMP-SHAFT", "name": "Shaft"},
    {"suffix": "CMP-SPRING", "name": "Detent Spring"},
    {"suffix": "CMP-ROTOR", "name": "Contact Rotor"},
    {"suffix": "CMP-STATOR", "name": "Contact Stator"},
    {"suffix": "CMP-BASE", "name": "Base"},
]

SENSOR_REQUIREMENTS = [
    {
        "suffix": "REQ-SENS",
        "text": "지정 압력 범위(40~400kPa) 전 구간에서 규정 감도 이상의 출력을 제공해야 한다.",
        "verification_method": "test",
        "safety_class": "QM",
    },
    {
        "suffix": "REQ-ACC",
        "text": "동작 온도 범위에서 측정 정확도가 규정 오차 이내여야 한다.",
        "verification_method": "test",
        "safety_class": "ASIL_B",
    },
    {
        "suffix": "REQ-MOUNT",
        "text": "리플로우 공정 후 솔더 접합 신뢰성이 확보되어야 한다.",
        "verification_method": "test",
        "safety_class": "QM",
    },
]
SENSOR_COMPONENTS = [
    {"suffix": "CMP-SUBSTRATE", "name": "Package Substrate"},
    {"suffix": "CMP-DIE", "name": "Silicon Die"},
    {"suffix": "CMP-LID", "name": "Metal Lid"},
    {"suffix": "CMP-PORT", "name": "Pressure Port"},
    {"suffix": "CMP-BALLS", "name": "Solder Balls"},
]

# The full golden dataset: 3 products × 2 variants. Component names MUST
# match the STEP part names of the fixture assemblies (the 3D viewer maps
# GLB node names to components by name), and mech `model_type` must be one
# the mech-model worker knows (fs_dome / detent_torque / bridge_transfer).
# `test_suffix` feeds TP-{s}/TR-{s}-01/CORR-{s}-01 business ids; the TACT
# value "FS" keeps the original dataset's idempotency keys unchanged.
PRODUCTS: list[dict] = [
    {
        "business_id": "PROD-TACT-SWITCH",
        "name": "TACT Switch",
        "description": "Automotive TACT switch product line",
        "variants": [
            {
                "business_id": "VAR-TACT-A",
                "name": "TACT Switch Variant A (baseline height)",
                "requirements": TACT_REQUIREMENTS,
                "components": TACT_COMPONENTS,
                "step_fixture": "tact_switch_asm.step",
                "netlist_fixture": "variant_a_contact.cir",
                "sweep_ohms": [0.1, 1, 10, 100, 500, 1000],
                "logic_low_threshold_v": 1.0,
                "mech_parameters": {"model_type": "fs_dome", "dome_thickness_mm": 0.10, "dome_diameter_mm": 6.0},
                "measured_fixture": "variant_a_fs_measured.csv",
                "x_unit": "mm", "y_unit": "mN",
                "test_suffix": "FS",
                "test_plan_name": "F-S Curve Bench Test",
                "equipment_id": "FS-BENCH-01",
            },
            {
                "business_id": "VAR-TACT-B",
                "name": "TACT Switch Variant B (reduced height)",
                "requirements": TACT_REQUIREMENTS,
                "components": TACT_COMPONENTS,
                "step_fixture": "tact_switch_asm.step",
                "netlist_fixture": "variant_b_contact.cir",
                "sweep_ohms": [0.1, 1, 10, 100, 500, 1000],
                "logic_low_threshold_v": 1.0,
                "mech_parameters": {"model_type": "fs_dome", "dome_thickness_mm": 0.09, "dome_diameter_mm": 5.5},
                "measured_fixture": "variant_b_fs_measured.csv",
                "x_unit": "mm", "y_unit": "mN",
                "test_suffix": "FS",
                "test_plan_name": "F-S Curve Bench Test",
                "equipment_id": "FS-BENCH-01",
            },
        ],
    },
    {
        "business_id": "PROD-ROTARY-ENCODER",
        "name": "Rotary Encoder",
        "description": "Automotive rotary encoder product line (detent torque + push switch)",
        "variants": [
            {
                "business_id": "VAR-ENC-A",
                "name": "Rotary Encoder Variant A (12-detent)",
                "requirements": ENCODER_REQUIREMENTS,
                "components": ENCODER_COMPONENTS,
                "step_fixture": "rotary_encoder_asm.step",
                "netlist_fixture": "encoder_push_switch.cir",
                "sweep_ohms": [0.1, 1, 10, 100, 500, 1000],
                "logic_low_threshold_v": 1.0,
                "mech_parameters": {"model_type": "detent_torque", "detent_count": 12, "peak_torque_mNm": 3.5},
                "measured_fixture": "variant_a_detent_measured.csv",
                "x_unit": "deg", "y_unit": "mN·m",
                "test_suffix": "DT",
                "test_plan_name": "Detent Torque Bench Test",
                "equipment_id": "TORQUE-BENCH-01",
            },
            {
                "business_id": "VAR-ENC-B",
                "name": "Rotary Encoder Variant B (24-detent, light)",
                "requirements": ENCODER_REQUIREMENTS,
                "components": ENCODER_COMPONENTS,
                "step_fixture": "rotary_encoder_asm.step",
                "netlist_fixture": "encoder_push_switch.cir",
                "sweep_ohms": [0.1, 1, 10, 100, 500, 1000],
                "logic_low_threshold_v": 1.0,
                "mech_parameters": {"model_type": "detent_torque", "detent_count": 24, "peak_torque_mNm": 2.8},
                "measured_fixture": "variant_b_detent_measured.csv",
                "x_unit": "deg", "y_unit": "mN·m",
                "test_suffix": "DT",
                "test_plan_name": "Detent Torque Bench Test",
                "equipment_id": "TORQUE-BENCH-01",
            },
        ],
    },
    {
        "business_id": "PROD-MEMS-SENSOR",
        "name": "MEMS Pressure Sensor",
        "description": "Piezoresistive MEMS pressure sensor product line (bridge transfer)",
        "variants": [
            {
                "business_id": "VAR-SEN-A",
                "name": "Pressure Sensor Variant A (high sensitivity)",
                "requirements": SENSOR_REQUIREMENTS,
                "components": SENSOR_COMPONENTS,
                "step_fixture": "mems_sensor_asm.step",
                "netlist_fixture": "sensor_bridge.cir",
                "sweep_ohms": [4500, 4750, 5000, 5250, 5500],
                "logic_low_threshold_v": 1.0,
                "mech_parameters": {"model_type": "bridge_transfer", "supply_voltage_v": 3.0, "sensitivity_mv_per_v_per_kpa": 0.8},
                "measured_fixture": "variant_a_transfer_measured.csv",
                "x_unit": "kPa", "y_unit": "mV",
                "test_suffix": "BT",
                "test_plan_name": "Bridge Transfer Bench Test",
                "equipment_id": "DAQ-PRESSURE-01",
            },
            {
                "business_id": "VAR-SEN-B",
                "name": "Pressure Sensor Variant B (standard sensitivity)",
                "requirements": SENSOR_REQUIREMENTS,
                "components": SENSOR_COMPONENTS,
                "step_fixture": "mems_sensor_asm.step",
                "netlist_fixture": "sensor_bridge.cir",
                "sweep_ohms": [4500, 4750, 5000, 5250, 5500],
                "logic_low_threshold_v": 1.0,
                "mech_parameters": {"model_type": "bridge_transfer", "supply_voltage_v": 3.0, "sensitivity_mv_per_v_per_kpa": 0.65},
                "measured_fixture": "variant_b_transfer_measured.csv",
                "x_unit": "kPa", "y_unit": "mV",
                "test_suffix": "BT",
                "test_plan_name": "Bridge Transfer Bench Test",
                "equipment_id": "DAQ-PRESSURE-01",
            },
        ],
    },
]


def _family_of(spec: dict) -> str:
    return {
        "fs_dome": "tact",
        "detent_torque": "encoder",
        "bridge_transfer": "mems",
    }[spec["mech_parameters"]["model_type"]]


# 지시서 ①②④ lite seed data: causal chains (AI-06), canvas blocks/flows
# (E02), model cards (TC-03). Labels follow the dataset's Korean requirement
# style; every evidence entry pins a REAL run/test-run business_id created
# above — no invented numbers (§10.2).
_TACT_CAUSAL = [
    ("조작 입력력", "mechanical", "돔 변형(스냅)", "mechanical", "drives",
     "플런저 가력이 구면 금속 돔을 좌굴시켜 스냅스루", ["mech"], "human_approved", None),
    ("돔 변형(스냅)", "mechanical", "접점 접촉·바운스", "mechanical", "drives",
     "스냅 접촉 순간 접점계 반동으로 접점 바운스 발생", ["test"], "human_approved", None),
    ("접점 접촉·바운스", "mechanical", "접촉 저항 R_c", "electrical", "affects",
     "접촉 압력 증가 → 필름 저항 감소", ["spice"], "human_approved", None),
    ("접촉 저항 R_c", "electrical", "출력 로우 레벨 V_OL", "electrical", "drives",
     "풀업 분배: V_OL = V_CC·R_c/(R_c + R_pu)", ["spice"], "human_approved", None),
    ("출력 로우 레벨 V_OL", "electrical", "Debounce 지연", "control", "affects",
     "바운스 구간은 논리 확정 불가 → t_db 동안 대기", [], "rule_derived", None),
    ("Debounce 지연", "control", "조작감 명확함", "kansei", "affects",
     "AI 추론: 응답 지연이 짧을수록 즉각감 향상 — 사람 검토 전", ["test"], "ai_inferred", 0.62),
]
_TACT_ELEMENTS = [
    ("ACT", "조작 입력력 F_act", "mechanical", None, "N", None, {"x": 50, "y": 110}),
    ("DOME", "돔 스냅 기구", "mechanical", "F(δ): 구면 바이어스 스프링 스냅스루", "mm", "CMP-DOME", {"x": 245, "y": 70}),
    ("PAD", "접점 접촉·바운스", "mechanical", None, None, "CMP-CONTACT", {"x": 245, "y": 240}),
    ("RC", "접촉 저항 R_c", "electrical", "R_c = R_bulk + R_film(A, P)", "Ω", "CMP-CONTACT", {"x": 470, "y": 240}),
    ("VOL", "출력 로우 레벨 V_OL", "electrical", "V_OL = V_CC·R_c/(R_c + R_pu)", "V", None, {"x": 470, "y": 70}),
    ("DBF", "Debounce 필터", "control", "y[n] = maj(x[n−1..n−3]), t_db ≈ 4 ms", None, None, {"x": 700, "y": 70}),
    ("KAN", "조작감 (명확함·가벼움)", "kansei", None, None, None, {"x": 920, "y": 70}),
]
_TACT_LINKS = [
    ("ACT", "DOME", "가력 변위 δ", "mm"),
    ("DOME", "PAD", "스냅 접촉 압력", "MPa"),
    ("PAD", "RC", "접촉 면적·압력", None),
    ("RC", "VOL", "R_c", "Ω"),
    ("VOL", "DBF", "V_OL 강하", "V"),
    ("DBF", "KAN", "응답 지연감", None),
]

_ENCODER_CAUSAL = [
    ("회전 토크", "mechanical", "스프링 좌굴", "mechanical", "drives",
     "로터 회전이 디텐트 스프링을 좌굴시켜 디텐트 형성", ["mech"], "human_approved", None),
    ("스프링 좌굴", "mechanical", "로터 접촉 압력", "mechanical", "drives",
     "스프링 반력이 로터–스테이터 접촉압을 결정", ["mech"], "human_approved", None),
    ("로터 접촉 압력", "mechanical", "채널 접촉저항·채터링", "electrical", "affects",
     "접촉압 변동이 채널 저항과 점속을 변조", ["spice"], "human_approved", None),
    ("차량 진동", "mechanical", "채널 채터링", "electrical", "affects",
     "하우징 전달 진동이 접점 이탈을 유발 (REQ-NOJITTER)", ["test"], "rule_derived", None),
    ("채널 채터링", "electrical", "디코드 오카운트", "control", "affects",
     "채터링 구간은 위상 디코드에서 유효 펄스로 오판 가능", [], "rule_derived", None),
    ("디텐트 토크 곡선", "mechanical", "디텐트 감각", "kansei", "affects",
     "AI 추론: 피크/밸리 토크 비율이 클릭감 명확성 결정 — 사람 검토 전", ["mech"], "ai_inferred", 0.58),
]
_ENCODER_ELEMENTS = [
    ("TRQ", "회전 토크 T", "mechanical", None, "mN·m", None, {"x": 50, "y": 90}),
    ("SPR", "디텐트 스프링", "mechanical", "T(θ): 스프링 좌굴 스냅", None, "CMP-SPRING", {"x": 245, "y": 190}),
    ("ROT", "로터–스테이터 접촉", "mechanical", None, None, "CMP-ROTOR", {"x": 445, "y": 90}),
    ("SIG", "채널 펄스·채터링", "electrical", "A/B 2채널 위상차 90°", None, "CMP-STATOR", {"x": 645, "y": 190}),
    ("DEC", "펄스 디코드", "control", "θ = 360°·cnt/(N·감속비)", None, None, {"x": 850, "y": 90}),
    ("KAN", "디텐트 감각 (클릭감)", "kansei", None, None, None, {"x": 645, "y": 340}),
]
_ENCODER_LINKS = [
    ("TRQ", "SPR", "토크 T(θ)", "mN·m"),
    ("SPR", "ROT", "접촉 압력", "N"),
    ("ROT", "SIG", "접촉 상태", None),
    ("SIG", "DEC", "A/B 펄스", None),
    ("DEC", "KAN", "각도 피드백", None),
]

_MEMS_CAUSAL = [
    ("인가 압력", "mechanical", "다이어프램 변형", "mechanical", "drives",
     "압력이 실리콘 다이어프램에 막 응력 유발", ["mech"], "human_approved", None),
    ("다이어프램 변형", "mechanical", "브리지 출력 V_out", "electrical", "drives",
     "피에조저항 변화 → 휘트스톤 브리지 불균형 전압", ["mech"], "human_approved", None),
    ("브리지 출력 V_out", "electrical", "보정 출력", "control", "drives",
     "게인·오프셋·온도 보상 보정식 적용", [], "rule_derived", None),
    ("솔더 접합 상태", "mechanical", "출력 드리프트", "electrical", "affects",
     "솔더 볼 피로/크랙이 접촉 저항을 변화시켜 드리프트 유발", ["test"], "rule_derived", None),
    ("보정 후 선형성", "control", "측정 신뢰감", "kansei", "affects",
     "AI 추론: 직선성·재현성이 사용자 신뢰감 결정 — 사람 검토 전", ["test"], "ai_inferred", 0.60),
]
_MEMS_ELEMENTS = [
    ("PRS", "인가 압력 P", "mechanical", None, "kPa", None, {"x": 50, "y": 90}),
    ("DIA", "다이어프램 변형 ε", "mechanical", "ε ∝ P·r²/(E·t²)", None, "CMP-DIE", {"x": 250, "y": 190}),
    ("BRG", "피에조 브리지 V_out", "electrical", "V_out = V_s·ΔR/R", "mV", "CMP-DIE", {"x": 470, "y": 90}),
    ("TCMP", "온도 보상·보정", "control", "V_corr = G·(V_out − k_T·ΔT)", None, None, {"x": 470, "y": 300}),
    ("SOLD", "솔더 볼 접합", "mechanical", None, None, "CMP-BALLS", {"x": 250, "y": 380}),
    ("KAN", "측정 신뢰감", "kansei", None, None, None, {"x": 700, "y": 190}),
]
_MEMS_LINKS = [
    ("PRS", "DIA", "압력 P", "kPa"),
    ("DIA", "BRG", "변형률 ε", None),
    ("BRG", "TCMP", "V_out", "mV"),
    ("SOLD", "TCMP", "드리프트 성분", None),
    ("TCMP", "KAN", "보정 출력", None),
]

_FAMILIES: dict[str, dict] = {
    "tact": {
        "causal": _TACT_CAUSAL,
        "elements": _TACT_ELEMENTS,
        "links": _TACT_LINKS,
        # (element_suffix, business suffix, name, direction, quantity, unit)
        "ports": [
            ("ACT", "F", "가력 변위 δ", "out", "displacement", "mm"),
            ("DOME", "DIN", "가력 변위 δ", "in", "displacement", "mm"),
            ("DOME", "POUT", "접촉 압력", "out", "pressure", "MPa"),
            ("PAD", "PIN", "접촉 압력", "in", "pressure", "MPa"),
            ("PAD", "POUT", "접촉 압력", "out", "pressure", "MPa"),
            ("RC", "PIN", "접촉 압력", "in", "pressure", "MPa"),
            ("RC", "ROUT", "접촉 저항", "out", "resistance", "Ω"),
            ("VOL", "RIN", "접촉 저항", "in", "resistance", "Ω"),
            ("VOL", "VOUT", "출력 전압", "out", "voltage", "V"),
            ("DBF", "VIN", "출력 전압", "in", "voltage", "V"),
        ],
        "uq": {
            "model_type": "fs_dome",
            "inputs": [
                {"name": "dome_thickness_mm", "distribution": "triangular",
                 "params": {"min": 0.07, "mode": 0.10, "max": 0.13}, "unit": "mm", "source": "assumed"},
                {"name": "dome_diameter_mm", "distribution": "triangular",
                 "params": {"min": 5.0, "mode": 6.0, "max": 6.5}, "unit": "mm", "source": "assumed"},
            ],
            # 데모 목표 밴드(합성): 두 variant의 공칭 피크(325/272 mN)를 포함
            "target_band": {"min": 260.0, "max": 360.0, "unit": "mN",
                            "source": "demo spec band (synthetic)"},
        },
        "card": {
            "title": "F–S 스냅 커브 + 접점 저항 모델",
            "purpose": "조작력–행정 곡선과 로직 로우 마진을 예측해 돔 두께/직경 변경이 조작감과 전기 규격에 미치는 영향을 평가한다.",
            "equation": "F(δ): fs_dome 해석 + V_OL = V_CC·R_c/(R_c + R_pu)",
            "assumptions": [
                "금속 돔을 축대칭 바이어스 스프링으로 근사",
                "접점 필름 저항은 상온 정적 접촉 기준",
                "하우징 강체 가정, 단자 기생 성분 무시",
            ],
            "validity": [
                {"parameter": "dome_thickness_mm", "unit": "mm", "min": 0.07, "max": 0.13},
                {"parameter": "dome_diameter_mm", "unit": "mm", "min": 5.0, "max": 6.5},
            ],
        },
    },
    "encoder": {
        "causal": _ENCODER_CAUSAL,
        "elements": _ENCODER_ELEMENTS,
        "links": _ENCODER_LINKS,
        "ports": [
            ("TRQ", "TOUT", "토크", "out", "torque", "mN·m"),
            ("SPR", "TIN", "토크", "in", "torque", "mN·m"),
            ("SPR", "FOUT", "접촉 압력", "out", "force", "N"),
            ("ROT", "FIN", "접촉 압력", "in", "force", "N"),
            ("SIG", "PULSE_OUT", "채널 펄스", "out", "count", "ea"),
            ("DEC", "PULSE_IN", "채널 펄스", "in", "count", "ea"),
        ],
        "uq": {
            "model_type": "detent_torque",
            "inputs": [
                {"name": "detent_count", "distribution": "uniform",
                 "params": {"min": 8, "max": 28}, "unit": "ea", "source": "assumed"},
                {"name": "peak_torque_mNm", "distribution": "triangular",
                 "params": {"min": 2.0, "mode": 3.5, "max": 4.5}, "unit": "mN·m", "source": "assumed"},
            ],
            "target_band": {"min": 2.0, "max": 4.5, "unit": "mN·m",
                            "source": "demo spec band (synthetic)"},
        },
        "card": {
            "title": "디텐트 토크 + 채터링 모델",
            "purpose": "디텐트 토크 곡선과 A/B 채널 채터링을 예측해 회전감과 진동 내성을 평가한다.",
            "equation": "T(θ): detent_torque 해석 + θ = 360°·cnt/(N·감속비)",
            "assumptions": [
                "디텐트 스프링 좌굴을 준정적 토크 곡선으로 근사",
                "접점 마모는 수명 초기 구간에서 무시",
                "차량 진동은 규격 스펙트럼 가진 기준",
            ],
            "validity": [
                {"parameter": "detent_count", "unit": "ea", "min": 8, "max": 28},
                {"parameter": "peak_torque_mNm", "unit": "mN·m", "min": 2.0, "max": 4.5},
            ],
        },
    },
    "mems": {
        "causal": _MEMS_CAUSAL,
        "elements": _MEMS_ELEMENTS,
        "links": _MEMS_LINKS,
        "ports": [
            ("PRS", "POUT", "인가 압력", "out", "pressure", "kPa"),
            ("DIA", "PIN", "인가 압력", "in", "pressure", "kPa"),
            ("DIA", "SOUT", "변형률", "out", "strain", "ratio"),
            ("BRG", "SIN", "변형률", "in", "strain", "ratio"),
            ("BRG", "VOUT", "브리지 출력", "out", "voltage", "mV"),
            ("TCMP", "VIN", "브리지 출력", "in", "voltage", "mV"),
        ],
        "uq": {
            "model_type": "bridge_transfer",
            "inputs": [
                {"name": "supply_voltage_v", "distribution": "uniform",
                 "params": {"min": 2.7, "max": 5.5}, "unit": "V", "source": "assumed"},
                {"name": "sensitivity_mv_per_v_per_kpa", "distribution": "triangular",
                 "params": {"min": 0.5, "mode": 0.8, "max": 1.0}, "unit": "mV/V/kPa", "source": "assumed"},
            ],
            "target_band": {"min": 700.0, "max": 1100.0, "unit": "mV",
                            "source": "demo spec band (synthetic)"},
        },
        "card": {
            "title": "브리지 전달 + 온도 보상 모델",
            "purpose": "인가 압력–브리지 출력 전달특성과 보정 후 정확도를 예측해 감도/온도 특성을 평가한다.",
            "equation": "V_out = V_s·ΔR/R (bridge_transfer) + V_corr = G·(V_out − k_T·ΔT)",
            "assumptions": [
                "다이어프램 소변형 선형 탄성 범위",
                "피에조저항 계수는 온도 25°C 기준",
                "리플로우 후 솔더 접합은 초기 상태 가정",
            ],
            "validity": [
                {"parameter": "supply_voltage_v", "unit": "V", "min": 2.7, "max": 5.5},
                {"parameter": "sensitivity_mv_per_v_per_kpa", "unit": "mV/V/kPa", "min": 0.5, "max": 1.0},
            ],
        },
    },
}


def seed_model_canvas(
    client: httpx.Client,
    variant_business_id: str,
    variant_id: str,
    spec: dict,
    comp_ids: list[str],
) -> None:
    """지시서 lite: causal chain + canvas + model card per variant. All POSTs
    carry stable business_ids + Idempotency-Keys, so reseeds are no-ops."""
    fam = _FAMILIES[_family_of(spec)]
    comp_by_suffix = dict(zip((c["suffix"] for c in spec["components"]), comp_ids))

    def evidence(kinds: list[str]) -> list[dict]:
        out = []
        if "mech" in kinds:
            out.append({"kind": "simulation_run", "business_id": f"{variant_business_id}-RUN-MECH-01",
                        "note": "기구 해석 결과치 (곡선/토크)"})
        if "spice" in kinds:
            out.append({"kind": "simulation_run", "business_id": f"{variant_business_id}-RUN-SPICE-01",
                        "note": "SPICE 스위프 결과치"})
        if "test" in kinds:
            out.append({"kind": "test_run", "business_id": f"{variant_business_id}-TR-{spec['test_suffix']}-01",
                        "note": "벤치 측정 데이터"})
        return out

    for i, (src, sdom, dst, tdom, rel, mech_txt, kinds, prov, conf) in enumerate(fam["causal"], start=1):
        post(
            client,
            f"/api/v1/variants/{variant_id}/causal-relations",
            idem_key=f"seed-{variant_business_id}-CR-{i:02d}",
            body={
                "business_id": f"{variant_business_id}-CR-{i:02d}",
                "source_label": src,
                "source_domain": sdom,
                "target_label": dst,
                "target_domain": tdom,
                "relation_type": rel,
                "mechanism": mech_txt,
                "evidence": evidence(kinds),
                "provenance": prov,
                **({"confidence": conf} if conf is not None else {}),
            },
        )

    elem_ids: dict[str, str] = {}
    for suffix, name, domain, equation, unit, comp_suffix, pos in fam["elements"]:
        element = post(
            client,
            f"/api/v1/variants/{variant_id}/model-elements",
            idem_key=f"seed-{variant_business_id}-ME-{suffix}",
            body={
                "business_id": f"{variant_business_id}-ME-{suffix}",
                "name": name,
                "domain": domain,
                **({"equation_text": equation} if equation else {}),
                **({"unit": unit} if unit else {}),
                **({"geometry_component_id": comp_by_suffix[comp_suffix]} if comp_suffix else {}),
                "position": pos,
            },
        )
        elem_ids[suffix] = element["id"]

    # Port contracts BEFORE links — link creation validates unit compatibility
    # against these (SM-01/MV-02), so the seeded graph must post them first.
    for esuffix, psuffix, name, direction, quantity, unit in fam["ports"]:
        post(
            client,
            f"/api/v1/model-elements/{elem_ids[esuffix]}/ports",
            idem_key=f"seed-{variant_business_id}-MP-{psuffix}",
            body={
                "business_id": f"{variant_business_id}-MP-{psuffix}",
                "name": name,
                "direction": direction,
                "quantity": quantity,
                "unit": unit,
            },
        )

    for i, (src, dst, signal, unit) in enumerate(fam["links"], start=1):
        post(
            client,
            f"/api/v1/variants/{variant_id}/model-links",
            idem_key=f"seed-{variant_business_id}-ML-{i:02d}",
            body={
                "business_id": f"{variant_business_id}-ML-{i:02d}",
                "source_element_id": elem_ids[src],
                "target_element_id": elem_ids[dst],
                "signal": signal,
                **({"unit": unit} if unit else {}),
                "kind": "signal",
            },
        )

    card = fam["card"]
    post(
        client,
        f"/api/v1/variants/{variant_id}/model-card",
        idem_key=f"seed-{variant_business_id}-MC-01",
        body={
            "business_id": f"{variant_business_id}-MC-01",
            "title": card["title"],
            "purpose": card["purpose"],
            "equation_text": card["equation"],
            "assumptions": card["assumptions"],
            "evidence": evidence(["mech", "spice", "test"]),
            "validity_envelope": card["validity"],
            "trust_state": "validated_for_purpose",
            "notes": "합성 데이터 기반 데모 카드. 유효범위 밖 입력의 예측은 정상 결과로 표시되지 않는다 (지시서 금지 #4).",
        },
    )

    # UQ lite (SL-03): seeded LHS Monte Carlo per family. Same seed ⇒ identical
    # results (MV-05); distributions are labeled "assumed" — the API never
    # invents engineering numbers (지시서 금지 #1).
    uq = fam["uq"]
    post(
        client,
        f"/api/v1/variants/{variant_id}/uq",
        idem_key=f"seed-{variant_business_id}-UQ-01",
        body={
            "business_id": f"{variant_business_id}-UQ-01",
            "model_type": uq["model_type"],
            "n_samples": 2000,
            "seed": 42,
            "inputs": uq["inputs"],
            "target_band": uq["target_band"],
        },
    )

    # Rule-based model review (AI-02): append-only run #1 so findings show out
    # of the box. No Idempotency-Key — a reseed appends a fresh snapshot by
    # design (the ledger never replays or overwrites).
    review_resp = client.post(f"/api/v1/twins/{variant_id}/model-review")
    if review_resp.status_code >= 400:
        print(f"WARNING: {variant_business_id} model review failed: {review_resp.text}", file=sys.stderr)
    else:
        findings = review_resp.json()["findings"]
        print(
            f"  review run: {len(findings)} findings "
            f"({sum(1 for f in findings if f['severity'] == 'error')} error / "
            f"{sum(1 for f in findings if f['severity'] == 'warning')} warning / "
            f"{sum(1 for f in findings if f['severity'] == 'suggestion')} suggestion)"
        )


def seed_variant(
    client: httpx.Client,
    test_client: httpx.Client,
    approver_client: httpx.Client,
    product_id: str,
    spec: dict,
) -> str:
    variant_business_id = spec["business_id"]
    variant = post(
        client,
        f"/api/v1/products/{product_id}/variants",
        idem_key=f"seed-{variant_business_id}",
        body={"business_id": variant_business_id, "name": spec["name"]},
    )
    variant_id = variant["id"]

    req_ids = []
    for req in spec["requirements"]:
        business_id = f"{variant_business_id}-{req['suffix']}"
        requirement = post(
            client,
            "/api/v1/requirements",
            idem_key=f"seed-{business_id}",
            body={
                "business_id": business_id,
                "variant_id": variant_id,
                "text": req["text"],
                "verification_method": req["verification_method"],
                "safety_class": req["safety_class"],
                "owner": "demo.architect",
                "source": "AlpsAlpine_Engineering_Digital_Twin_Workbench_개발지시서_v1.0 §12.1",
            },
        )
        req_ids.append(requirement["id"])

    comp_ids = []
    for comp in spec["components"]:
        business_id = f"{variant_business_id}-{comp['suffix']}"
        component = post(
            client,
            "/api/v1/components",
            idem_key=f"seed-{business_id}",
            body={"business_id": business_id, "variant_id": variant_id, "name": comp["name"]},
        )
        comp_ids.append(component["id"])

    # Trace every requirement to every component for the demo dataset — a real
    # design would trace selectively, but the golden dataset just needs a
    # non-empty, deterministic graph to regress against.
    for req_id, req in zip(req_ids, spec["requirements"]):
        for comp_id, comp in zip(comp_ids, spec["components"]):
            link_business_id = f"{variant_business_id}-{req['suffix']}-{comp['suffix']}"
            post(
                client,
                f"/api/v1/requirements/{req_id}/trace-links",
                idem_key=f"seed-{link_business_id}",
                body={
                    "business_id": link_business_id,
                    "target_type": "component",
                    "target_id": comp_id,
                },
            )

    # CAD: upload the product's named STEP assembly, convert to glTF, and link
    # the SAME derived version to ALL components — the viewer dedupes by
    # artifact_version_id, so all components fetch/parse one assembly GLB whose
    # node names match these names. Assembly tessellation at 0.02 mm deflection
    # takes longer than the merged conversion did, hence the longer timeout.
    step_bytes = (FIXTURES_DIR / spec["step_fixture"]).read_bytes()
    step_version_id = upload_and_promote(
        client,
        business_id=f"{variant_business_id}-CAD-ASM",
        kind="step",
        filename=spec["step_fixture"],
        content=step_bytes,
    )
    cad_run = run_simulation_and_wait(
        client,
        business_id=f"{variant_business_id}-RUN-CAD-02",
        variant_id=variant_id,
        run_type="cad_convert",
        input_artifact_version_id=step_version_id,
        timeout_s=120.0,
    )
    # Idempotent POST returns the cached *creation-time* run body — on a
    # reseed that can be an older conversion (e.g. the pre-upgrade RUN-CAD-02)
    # while a newer succeeded CAD run exists. Link the NEWEST succeeded
    # cad_convert run's output instead of blindly trusting the cached body.
    all_runs = client.get(f"/api/v1/variants/{variant_id}/simulation-runs").json()
    cad_succeeded = [
        r
        for r in all_runs
        if r["run_type"] == "cad_convert" and r["status"] == "succeeded" and r.get("output_artifact_version_id")
    ]
    link_run = max(cad_succeeded, key=lambda r: r["created_at"]) if cad_succeeded else None
    if link_run is not None:
        for comp_id in comp_ids:
            client.patch(
                f"/api/v1/components/{comp_id}/link-artifact",
                json={"artifact_version_id": link_run["output_artifact_version_id"]},
            ).raise_for_status()
    elif cad_run["status"] != "succeeded":
        print(f"WARNING: {variant_business_id} CAD conversion failed: {cad_run['error_message']}", file=sys.stderr)

    # SPICE: upload the product's circuit and run the resistance sweep (FR-04).
    netlist_bytes = (FIXTURES_DIR / spec["netlist_fixture"]).read_bytes()
    netlist_version_id = upload_and_promote(
        client,
        business_id=f"{variant_business_id}-NETLIST",
        kind="netlist",
        filename=spec["netlist_fixture"],
        content=netlist_bytes,
    )
    spice_run = run_simulation_and_wait(
        client,
        business_id=f"{variant_business_id}-RUN-SPICE-01",
        variant_id=variant_id,
        run_type="spice_analysis",
        input_artifact_version_id=netlist_version_id,
        parameters={
            "sweep_ohms": spec["sweep_ohms"],
            "logic_low_threshold_v": spec["logic_low_threshold_v"],
        },
    )
    if spice_run["status"] != "succeeded":
        print(f"WARNING: {variant_business_id} SPICE run failed: {spice_run['error_message']}", file=sys.stderr)

    # Prediction model: analytical curve (FR-05), then correlate against a
    # synthetic "measured" bench-test CSV (FR-07, §5.3).
    mech_run = run_simulation_and_wait(
        client,
        business_id=f"{variant_business_id}-RUN-MECH-01",
        variant_id=variant_id,
        run_type="mech_model",
        parameters=spec["mech_parameters"],
    )
    if mech_run["status"] != "succeeded":
        print(f"WARNING: {variant_business_id} mech model run failed: {mech_run['error_message']}", file=sys.stderr)

    suffix = spec["test_suffix"]
    test_plan = post(
        test_client,
        "/api/v1/test-plans",
        idem_key=f"seed-{variant_business_id}-TP-{suffix}",
        body={"business_id": f"{variant_business_id}-TP-{suffix}", "variant_id": variant_id, "name": spec["test_plan_name"]},
    )
    test_run = post(
        test_client,
        "/api/v1/test-runs",
        idem_key=f"seed-{variant_business_id}-TR-{suffix}-01",
        body={
            "business_id": f"{variant_business_id}-TR-{suffix}-01",
            "test_plan_id": test_plan["id"],
            "executed_at": "2026-09-10T09:00:00Z",
            "equipment_id": spec["equipment_id"],
        },
    )
    csv_bytes = (FIXTURES_DIR / spec["measured_fixture"]).read_bytes()
    measurements = upload_csv_measurements(
        test_client,
        test_run_id=test_run["id"],
        csv_bytes=csv_bytes,
        filename=spec["measured_fixture"],
        x_unit=spec["x_unit"],
        y_unit=spec["y_unit"],
    )

    correlation = None
    if mech_run["status"] == "succeeded" and measurements:
        corr_resp = test_client.post(
            "/api/v1/correlations",
            headers={"Idempotency-Key": f"seed-{variant_business_id}-CORR-{suffix}-01"},
            json={
                "business_id": f"{variant_business_id}-CORR-{suffix}-01",
                "simulation_run_id": mech_run["id"],
                "test_run_id": test_run["id"],
            },
        )
        if corr_resp.status_code >= 400:
            print(f"WARNING: {variant_business_id} correlation failed: {corr_resp.text}", file=sys.stderr)
        else:
            correlation = corr_resp.json()

    baseline = post(
        client,
        "/api/v1/baselines",
        idem_key=f"seed-{variant_business_id}-BL-01",
        body={"business_id": f"{variant_business_id}-BL-01", "variant_id": variant_id},
    )

    # Gate: submit (blocked on evidence per §12.2), independent reviewer
    # approves — this is the last step of the first vertical slice (§20).
    gate = post(
        client,
        "/api/v1/gates",
        idem_key=f"seed-{variant_business_id}-GATE-VV",
        body={
            "business_id": f"{variant_business_id}-GATE-VV",
            "variant_id": variant_id,
            "baseline_id": baseline["id"],
            "name": "Virtual Verification Complete",
        },
    )
    # Idempotent POST returns the cached *creation-time* body — re-fetch for
    # the live status before deciding whether a submit/decide step is needed.
    gate_status = client.get(f"/api/v1/gates/{gate['id']}").json()["status"]
    if gate_status == "draft":
        submit_resp = client.post(f"/api/v1/gates/{gate['id']}/submit")
        if submit_resp.status_code == 200:
            gate_status = submit_resp.json()["status"]
        else:
            print(f"WARNING: {variant_business_id} gate submit failed: {submit_resp.text}", file=sys.stderr)
            gate_status = "submit_failed"

    if gate_status == "pending_review":
        approver_client.post(
            f"/api/v1/gates/{gate['id']}/comments",
            headers={"Idempotency-Key": f"seed-{variant_business_id}-GATE-COMMENT-1"},
            json={
                "business_id": f"{variant_business_id}-GATE-COMMENT-1",
                "text": "Evidence package reviewed: SPICE margin and model correlation both within tolerance.",
            },
        )
        decide_resp = approver_client.post(
            f"/api/v1/gates/{gate['id']}/decisions",
            headers={"Idempotency-Key": f"seed-{variant_business_id}-GATE-DECISION-1"},
            json={
                "business_id": f"{variant_business_id}-GATE-DECISION-1",
                "decision": "approved",
                "comment": "Virtual verification evidence sufficient; approved for prototype test stage.",
            },
        )
        if decide_resp.status_code < 400:
            gate_status = decide_resp.json()["decision"]

    corr_summary = (
        f"rmse={correlation['rmse']:.2f}{spec['y_unit']} corr={correlation['correlation_coefficient']:.3f}"
        if correlation
        else "none"
    )
    seed_model_canvas(client, variant_business_id, variant_id, spec, comp_ids)
    print(
        f"{variant_business_id}: variant={variant_id} baseline={baseline['id']} "
        f"cad={cad_run['status']} spice={spice_run['status']} mech={mech_run['status']} "
        f"correlation=({corr_summary}) gate={gate_status}"
    )
    return variant_id


def _fs_curve_csv(peak_mn: float) -> bytes:
    """Synthetic F–S curve (demo data): force rises to the actuation peak at
    ~0.10 mm stroke, then relaxes — shape only, the peak carries the story."""
    rows = []
    for i in range(21):
        x = i * 0.015
        if x <= 0.10:
            y = peak_mn * (x / 0.10) ** 1.6
        else:
            y = peak_mn * (0.45 + 0.55 * ((0.30 - x) / 0.20) ** 1.2)
        rows.append(f"{x:.3f},{max(y, 0.0):.1f}")
    return ("x_value,y_value\n" + "\n".join(rows) + "\n").encode()


# --- AirInput vertical slice (4th product family, proximity_capacitance) --
#
# Deliberately NOT added to PRODUCTS/seed_variant() above: that pipeline
# assumes every product gets a CAD assembly (STEP→glTF), a SPICE circuit
# sweep and a Model Canvas/UQ config (_FAMILIES). This vertical slice is
# scoped to the mech-model→correlation chain only (per the AirInput
# implementation spec §14 "첫 Vertical Slice", built the same minimal-infra
# way the other three product families reuse the analytical model dispatch)
# — no new 3D geometry, no SPICE/ASIC circuit netlist, no Model Canvas. See
# AGENTS.md "AirInput vertical slice" section for the full scope-cut
# rationale. Gate submission is skipped for the same reason: gate_readiness's
# `spice_analysis_succeeded` check is unconditional for every variant, and
# fabricating a SPICE netlist for a product with no represented circuit here
# would be exactly the invented-evidence problem HANDOFF.md §7 forbids.
AIRINPUT_REQUIREMENTS = [
    {
        "suffix": "REQ-DETECT",
        "text": "지정된 접근 거리 이내에서 손가락 접근을 안정적으로 검출해야 한다.",
        "verification_method": "test",
        # QM, not ASIL: §1.2 "첫 PoC에서는 자동차 기능안전 입력을 직접 제어하지 않는다 —
        # 설명·설계검증용 Shadow 환경으로 한정한다."
        "safety_class": "QM",
    },
    {
        "suffix": "REQ-NOFALSE",
        "text": "노이즈 환경에서 오검출(false trigger)이 발생하지 않아야 한다.",
        "verification_method": "test",
        "safety_class": "QM",
    },
    {
        "suffix": "REQ-GLOVE",
        "text": "대표 장갑 착용 조건에서도 규정된 축소 검출거리 이내에서 검출되어야 한다.",
        # No physical glove bench test in this vertical slice yet — current
        # evidence is the bare-vs-glove mech-model run comparison only.
        "verification_method": "analysis",
        "safety_class": "QM",
    },
]
# Full CAD bill of materials — names must exactly match the part names in
# generate_airinput_step.py: the S04 viewer matches GLB node names to
# components by normalized name, so a missing/renamed row leaves a CAD part
# unclickable and untraceable (the old 2-row list did exactly that — 6 of
# the 8 CAD parts had no Component row on S04).
AIRINPUT_COMPONENTS = [
    {"suffix": "CMP-HOUSING", "name": "AirInput Housing"},
    {"suffix": "CMP-ELECTRODE", "name": "Capacitive Electrode PCB"},
    {"suffix": "CMP-ASIC", "name": "Capacitive Sensing ASIC"},
    {"suffix": "CMP-RESISTOR", "name": "Filter Resistor"},
    {"suffix": "CMP-CAPACITOR", "name": "Decoupling Capacitor"},
    {"suffix": "CMP-FPC", "name": "FPC Connector"},
    {"suffix": "CMP-COVER", "name": "Cover Lens"},
]
# The 8th CAD part's name genuinely differs per variant (solid center pad vs
# split ring, generate_airinput_step.build_assembly_parts) —
# seed_airinput_variant appends the matching row per variant.
AIRINPUT_ELECTRODE_PARTS = {
    "a": {"suffix": "CMP-ELPAD", "name": "Electrode Pad"},
    "b": {"suffix": "CMP-ELPAD", "name": "Split-Ring Electrode"},
}

# Electrode Layout A/B = the spec's two geometry variants (§1.2), expressed
# as electrode_area_mm2/cover parameters on the proximity_capacitance model.
# step_fixture is genuinely per-variant (unlike the other three products,
# which share one fixture between A/B) — see generate_airinput_step.py: the
# electrode shape (solid pad vs. split-ring) and cover-lens thickness are
# real geometric differences, not just simulation parameters.
AIRINPUT_VARIANTS = [
    {
        "business_id": "VAR-AIR-A",
        "layout": "a",
        "name": "AirInput Proximity Sensor Variant A (Electrode Layout A — center pad)",
        "mech_parameters": {
            "model_type": "proximity_capacitance",
            "electrode_area_mm2": 100.0,
            "cover_thickness_mm": 1.0,
            "cover_dielectric_constant": 4.0,
            "is_glove": False,
        },
        "measured_fixture": "variant_a_proximity_measured.csv",
        "step_fixture": "airinput_sensor_a.step",
    },
    {
        "business_id": "VAR-AIR-B",
        "layout": "b",
        "name": "AirInput Proximity Sensor Variant B (Electrode Layout B — larger split-ring)",
        "mech_parameters": {
            "model_type": "proximity_capacitance",
            "electrode_area_mm2": 160.0,
            "cover_thickness_mm": 1.2,
            "cover_dielectric_constant": 3.2,
            "is_glove": False,
        },
        "measured_fixture": "variant_b_proximity_measured.csv",
        "step_fixture": "airinput_sensor_b.step",
    },
]


def seed_airinput_variant(
    client: httpx.Client, test_client: httpx.Client, product_id: str, spec: dict
) -> str:
    variant_business_id = spec["business_id"]
    variant = post(
        client,
        f"/api/v1/products/{product_id}/variants",
        idem_key=f"seed-{variant_business_id}",
        body={"business_id": variant_business_id, "name": spec["name"]},
    )
    variant_id = variant["id"]

    req_ids = []
    for req in AIRINPUT_REQUIREMENTS:
        business_id = f"{variant_business_id}-{req['suffix']}"
        requirement = post(
            client,
            "/api/v1/requirements",
            idem_key=f"seed-{business_id}",
            body={
                "business_id": business_id,
                "variant_id": variant_id,
                "text": req["text"],
                "verification_method": req["verification_method"],
                "safety_class": req["safety_class"],
                "owner": "demo.architect",
                "source": "AlpsAlpine_AirInput_3D_Interaction_Field_Twin_구현지시서_v1.0 §1.2/§11.2",
            },
        )
        req_ids.append(requirement["id"])

    comp_ids = []
    # Shared BOM + this variant's own electrode part (its CAD name differs
    # between Layout A and B).
    comps = [*AIRINPUT_COMPONENTS, AIRINPUT_ELECTRODE_PARTS[spec["layout"]]]
    for comp in comps:
        business_id = f"{variant_business_id}-{comp['suffix']}"
        component = post(
            client,
            "/api/v1/components",
            idem_key=f"seed-{business_id}",
            body={"business_id": business_id, "variant_id": variant_id, "name": comp["name"]},
        )
        comp_ids.append(component["id"])

    for req_id, req in zip(req_ids, AIRINPUT_REQUIREMENTS):
        for comp_id, comp in zip(comp_ids, comps):
            link_business_id = f"{variant_business_id}-{req['suffix']}-{comp['suffix']}"
            post(
                client,
                f"/api/v1/requirements/{req_id}/trace-links",
                idem_key=f"seed-{link_business_id}",
                body={
                    "business_id": link_business_id,
                    "target_type": "component",
                    "target_id": comp_id,
                },
            )

    # CAD: same upload/convert/link pattern as seed_variant() for the other
    # three products. Unlike them, the STEP fixture genuinely differs per
    # variant (see AIRINPUT_VARIANTS/generate_airinput_step.py), so this
    # can't reuse seed_variant() as-is — it's inlined here instead.
    step_bytes = (FIXTURES_DIR / spec["step_fixture"]).read_bytes()
    step_version_id = upload_and_promote(
        client,
        business_id=f"{variant_business_id}-CAD-ASM",
        kind="step",
        filename=spec["step_fixture"],
        content=step_bytes,
    )
    cad_run = run_simulation_and_wait(
        client,
        business_id=f"{variant_business_id}-RUN-CAD-01",
        variant_id=variant_id,
        run_type="cad_convert",
        input_artifact_version_id=step_version_id,
        timeout_s=120.0,
    )
    if cad_run["status"] != "succeeded":
        print(f"WARNING: {variant_business_id} CAD conversion failed: {cad_run.get('error_message')}", file=sys.stderr)
    all_runs = client.get(f"/api/v1/variants/{variant_id}/simulation-runs").json()
    cad_succeeded = [
        r
        for r in all_runs
        if r["run_type"] == "cad_convert" and r["status"] == "succeeded" and r.get("output_artifact_version_id")
    ]
    link_run = max(cad_succeeded, key=lambda r: r["created_at"]) if cad_succeeded else None
    if link_run is not None:
        for comp_id in comp_ids:
            client.patch(
                f"/api/v1/components/{comp_id}/link-artifact",
                json={"artifact_version_id": link_run["output_artifact_version_id"]},
            )

    # Bare-finger prediction (FR-05 analytical model), correlated against a
    # synthetic measured bench-scan CSV (FR-07, §5.3) — same as the other
    # three product families.
    bare_run = run_simulation_and_wait(
        client,
        business_id=f"{variant_business_id}-RUN-MECH-01",
        variant_id=variant_id,
        run_type="mech_model",
        parameters=spec["mech_parameters"],
    )
    if bare_run["status"] != "succeeded":
        print(f"WARNING: {variant_business_id} bare-finger mech run failed: {bare_run['error_message']}", file=sys.stderr)

    # Glove condition (§1.2 "Bare finger와 대표 Glove 조건"): a second run on
    # the same variant with is_glove=True, illustrative-prediction only — no
    # physical glove bench data in this vertical slice (see REQ-GLOVE above).
    glove_run = run_simulation_and_wait(
        client,
        business_id=f"{variant_business_id}-RUN-MECH-02-GLOVE",
        variant_id=variant_id,
        run_type="mech_model",
        parameters={**spec["mech_parameters"], "is_glove": True},
    )
    if glove_run["status"] != "succeeded":
        print(f"WARNING: {variant_business_id} glove mech run failed: {glove_run['error_message']}", file=sys.stderr)

    test_plan = post(
        test_client,
        "/api/v1/test-plans",
        idem_key=f"seed-{variant_business_id}-TP-PROX",
        body={
            "business_id": f"{variant_business_id}-TP-PROX",
            "variant_id": variant_id,
            "name": "Proximity Capacitance Bench Scan",
        },
    )
    test_run = post(
        test_client,
        "/api/v1/test-runs",
        idem_key=f"seed-{variant_business_id}-TR-PROX-01",
        body={
            "business_id": f"{variant_business_id}-TR-PROX-01",
            "test_plan_id": test_plan["id"],
            "executed_at": "2026-09-14T09:00:00Z",
            "equipment_id": "AIRINPUT-ROBOT-SCAN-01",
        },
    )
    csv_bytes = (FIXTURES_DIR / spec["measured_fixture"]).read_bytes()
    measurements = upload_csv_measurements(
        test_client,
        test_run_id=test_run["id"],
        csv_bytes=csv_bytes,
        filename=spec["measured_fixture"],
        x_unit="mm",
        y_unit="fF",
    )

    correlation = None
    if bare_run["status"] == "succeeded" and measurements:
        corr_resp = test_client.post(
            "/api/v1/correlations",
            headers={"Idempotency-Key": f"seed-{variant_business_id}-CORR-PROX-01"},
            json={
                "business_id": f"{variant_business_id}-CORR-PROX-01",
                "simulation_run_id": bare_run["id"],
                "test_run_id": test_run["id"],
            },
        )
        if corr_resp.status_code >= 400:
            print(f"WARNING: {variant_business_id} correlation failed: {corr_resp.text}", file=sys.stderr)
        else:
            correlation = corr_resp.json()

    baseline = post(
        client,
        "/api/v1/baselines",
        idem_key=f"seed-{variant_business_id}-BL-01",
        body={"business_id": f"{variant_business_id}-BL-01", "variant_id": variant_id},
    )

    corr_summary = (
        f"rmse={correlation['rmse']:.2f}fF corr={correlation['correlation_coefficient']:.3f}"
        if correlation
        else "none"
    )
    print(
        f"{variant_business_id}: variant={variant_id} baseline={baseline['id']} "
        f"cad={cad_run['status']} mech_bare={bare_run['status']} mech_glove={glove_run['status']} "
        f"correlation=({corr_summary}) gate=not_submitted(no SPICE run — see AGENTS.md)"
    )
    return variant_id


def seed_airinput_product(client: httpx.Client, test_client: httpx.Client) -> None:
    product = post(
        client,
        "/api/v1/products",
        idem_key="seed-PROD-AIRINPUT-SENSOR",
        body={
            "business_id": "PROD-AIRINPUT-SENSOR",
            "name": "AirInput Proximity Sensor",
            "description": (
                "Capacitive proximity/gesture sensing module (electrode → ASIC → "
                "gesture decision vertical slice; synthetic demo data)"
            ),
        },
    )
    for variant_spec in AIRINPUT_VARIANTS:
        seed_airinput_variant(client, test_client, product["id"], variant_spec)


# --- AirInput 3D Interaction Field Twin (§6.2 two-tier + §11.2 GOLD) -------
#
# Rides the SAME mech_model run_type via model_type dispatch — no new
# endpoints, no new worker. Per variant: FD field curve → surrogate DOE →
# sensitivity volume → synthetic correlation → GOLD replays.

# Dev gotcha (seen twice on the CAD side): a FAILED run is cached forever
# under its idempotency key — after fixing a worker bug mid-development,
# rerun with ALPS_FIELD_TWIN_SEED_SUFFIX=-r2 to get fresh keys.
FIELD_TWIN_IDEM_SUFFIX = os.environ.get("ALPS_FIELD_TWIN_SEED_SUFFIX", "")

AIRINPUT_FIELD_VARIANTS = [
    {
        "business_id": "VAR-AIR-A",
        "split_ring": False,
        "electrode_area_mm2": 100.0,
        "cover_thickness_mm": 1.0,
        "cover_dielectric_constant": 4.0,
        "ground_plate": None,
    },
    {
        "business_id": "VAR-AIR-B",
        "split_ring": True,
        "electrode_area_mm2": 160.0,
        "cover_thickness_mm": 1.2,
        "cover_dielectric_constant": 3.2,
        # §11.2 금속/접지 scenario structure for GOLD-06 (solver engine):
        # grounded plate 6 mm above the touch surface (z = 6.5 + 6).
        "ground_plate": [0.0, 0.0, 12.5, 12.0, 10.0],
    },
]


def get_artifact_json(client: httpx.Client, artifact_version_id: str) -> dict:
    resp = client.get(f"/api/v1/artifacts/versions/{artifact_version_id}/content")
    resp.raise_for_status()
    return json.loads(resp.content)


def seed_airinput_field_twin(client: httpx.Client, test_client: httpx.Client) -> None:
    sfx = FIELD_TWIN_IDEM_SUFFIX
    print("== AirInput 3D Interaction Field Twin seeding ==")
    product = post(
        client,
        "/api/v1/products",
        idem_key="seed-PROD-AIRINPUT-SENSOR",
        body={
            "business_id": "PROD-AIRINPUT-SENSOR",
            "name": "AirInput Proximity Sensor",
        },
    )
    variants = client.get(f"/api/v1/products/{product['id']}/variants").json()
    for spec in AIRINPUT_FIELD_VARIANTS:
        bid = spec["business_id"]
        variant_id = next(v["id"] for v in variants if v["business_id"] == bid)

        geo = {
            "electrode_area_mm2": spec["electrode_area_mm2"],
            "cover_thickness_mm": spec["cover_thickness_mm"],
            "cover_dielectric_constant": spec["cover_dielectric_constant"],
            "split_ring": spec["split_ring"],
        }
        print(f"[{bid}] variant={variant_id}", flush=True)

        # ① FD reference curve + field-grid artifact (potential slice)
        field_run = run_simulation_and_wait(
            client,
            business_id=f"{bid}-RUN-FIELD-01{sfx}",
            variant_id=variant_id,
            run_type="mech_model",
            parameters={"model_type": "electrostatic_field", **geo},
            timeout_s=300.0,
        )
        if field_run["status"] != "succeeded":
            print(f"WARNING: {bid} field run failed: {field_run['error_message']}", file=sys.stderr)
            continue
        field_payload = get_artifact_json(client, field_run["output_artifact_version_id"])
        print(f"[{bid}] RUN-FIELD-01 ok — touch ΔC={field_payload['touch_pose_channels_fF']}", flush=True)

        # ② Surrogate DOE (~114 FD solves, ~6 min) + TS-parity artifact
        surrogate_run = run_simulation_and_wait(
            client,
            business_id=f"{bid}-RUN-SURROGATE-01{sfx}",
            variant_id=variant_id,
            run_type="mech_model",
            parameters={"model_type": "surrogate_train", **geo},
            timeout_s=1200.0,
        )
        if surrogate_run["status"] != "succeeded":
            print(f"WARNING: {bid} surrogate run failed: {surrogate_run['error_message']}", file=sys.stderr)
            continue
        surrogate_payload = get_artifact_json(client, surrogate_run["output_artifact_version_id"])
        print(f"[{bid}] RUN-SURROGATE-01 ok — holdout rmse={surrogate_payload['channels']['E1']['holdout']['rmse_fF']} fF", flush=True)

        # ③ Sensitivity volume (감지영역/Dead Zone grid, surrogate tier)
        volume_run = run_simulation_and_wait(
            client,
            business_id=f"{bid}-RUN-VOLUME-01{sfx}",
            variant_id=variant_id,
            run_type="mech_model",
            parameters={"model_type": "sensitivity_volume", "surrogate_payload": surrogate_payload},
            timeout_s=300.0,
        )
        if volume_run["status"] != "succeeded":
            print(f"WARNING: {bid} volume run failed: {volume_run['error_message']}", file=sys.stderr)
        else:
            print(f"[{bid}] RUN-VOLUME-01 ok", flush=True)

        # ④ Synthetic bench CSV from the FD curve + seeded noise — the
        # "measured" side of the 예측-실측 check. SYNTHETIC by construction
        # (equipment id + filename disclose it); never presented as bench data.
        test_plan = post(
            test_client,
            "/api/v1/test-plans",
            idem_key=f"seed-{bid}-TP-FIELD{sfx}",
            body={
                "business_id": f"{bid}-TP-FIELD{sfx}",
                "variant_id": variant_id,
                "name": "Field-Twin Proximity Scan (synthetic FD-derived)",
            },
        )
        test_run = post(
            test_client,
            "/api/v1/test-runs",
            idem_key=f"seed-{bid}-TR-PROX-02{sfx}",
            body={
                "business_id": f"{bid}-TR-PROX-02{sfx}",
                "test_plan_id": test_plan["id"],
                "executed_at": "2026-09-14T11:00:00Z",
                "equipment_id": "SYNTHETIC-GENERATOR-FD-01",
            },
        )
        curve = field_payload["curve"]
        rng = random.Random(20260914)
        csv_lines = ["x_value,y_value"]
        for x, y in zip(curve["distance_mm"], curve["delta_c_total_fF"]):
            noise = rng.gauss(0.0, 0.03 * y + 0.0005)
            csv_lines.append(f"{x:.4f},{max(y + noise, 0.0):.6f}")
        csv_bytes = ("\n".join(csv_lines) + "\n").encode("utf-8")
        csv_name = f"variant_{'b' if spec['split_ring'] else 'a'}_field_twin_synthetic.csv"
        upload_csv_measurements(
            test_client,
            test_run_id=test_run["id"],
            csv_bytes=csv_bytes,
            filename=csv_name,
            x_unit="mm",
            y_unit="fF",
        )
        corr_resp = test_client.post(
            "/api/v1/correlations",
            headers={"Idempotency-Key": f"seed-{bid}-CORR-FIELD-01{sfx}"},
            json={
                "business_id": f"{bid}-CORR-FIELD-01{sfx}",
                "simulation_run_id": field_run["id"],
                "test_run_id": test_run["id"],
            },
        )
        corr_summary = f"failed HTTP {corr_resp.status_code}: {corr_resp.text[:140]}"
        if corr_resp.status_code < 400:
            c = corr_resp.json()
            corr_summary = f"rmse={c['rmse']:.4f}fF r={c['correlation_coefficient']:.3f}"
        print(f"[{bid}] TR-PROX-02 + CORR-FIELD-01: {corr_summary} (synthetic, disclosed)", flush=True)

        # ⑤ GOLD scenario replays (§11.2) — surrogate engine embeds the
        # promoted payload; GOLD-06 runs the solver on the plate geometry.
        scenario_ids = [
            "GOLD-01-CENTER-APPROACH",
            "GOLD-02-EDGE-DEGRADATION",
            "GOLD-03-GLOVE-SLOW",
            "GOLD-04-NOISE-FALSE-TRIGGER",
            "GOLD-05-OOD-HOVER",
        ]
        if spec["split_ring"]:
            scenario_ids.append("GOLD-06-GROUND-PLATE")
        for sid in scenario_ids:
            sid_short = "-".join(sid.split("-")[:2])  # GOLD-01 … matches worker naming
            params = {
                "model_type": "algorithm_replay",
                "scenario_id": sid,
                "surrogate_payload": surrogate_payload,
                **geo,
            }
            if sid == "GOLD-06-GROUND-PLATE":
                params.pop("surrogate_payload")
                params["geometry"] = {"ground_plate": spec["ground_plate"]}
            rp = run_simulation_and_wait(
                client,
                # short run id — result-metric business ids append the metric
                # name and result_metrics.business_id is VARCHAR(64)
                # (e.g. "VAR-AIR-A-RP-GOLD-01-r4-replay_gold-01_v1_false_triggers")
                business_id=f"{bid}-RP-{sid_short}{sfx}",
                variant_id=variant_id,
                run_type="mech_model",
                parameters=params,
                timeout_s=900.0,
            )
            if rp["status"] != "succeeded":
                print(f"WARNING: {bid} {sid} replay failed: {rp['error_message']}", file=sys.stderr)
                continue
            rp_metrics = {m["name"]: m["value"] for m in client.get(f"/api/v1/simulation-runs/{rp['id']}").json().get("metrics", [])}
            pass_flag = rp_metrics.get(f"replay_{sid_short.lower()}_pass")
            print(f"[{bid}] {sid}: pass={pass_flag}", flush=True)


def seed_process_twin(
    client: httpx.Client,
    test_client: httpx.Client,
    approver_client: httpx.Client,
    variant_ids: dict[str, str],
) -> None:
    """TACT Product–Process Twin vertical slice (지시서 §13 첫 Vertical Slice,
    §2.1 권장 대상): 금형 1식·Cavity 2개, 정상 Lot 3 + Cavity 편차 Lot 1,
    공정 3공정 (Setpoint/Actual 분리, 1건 윈도우 이탈), Lot별 F–S 검사,
    불량 2건. All synthetic demo fixtures — dispositions are seed inputs,
    never AI judgments (AI-04)."""
    variant_a = variant_ids.get("VAR-TACT-A")
    if not variant_a:
        print("WARNING: VAR-TACT-A missing — process twin seed skipped", file=sys.stderr)
        return

    mold = post(
        client,
        "/api/v1/molds",
        idem_key="seed-MOLD-TACT-01",
        body={
            "business_id": "MOLD-TACT-01",
            "name": "TACT 돔 프레스 금형",
            "tool_revision": "B",
            "process": "metal dome stamping",
            "notes": "데모 합성 데이터 — 실제 금형 아님 (source: synthetic)",
        },
    )
    cavities = {}
    for bid, no, label in (("CAV-TACT-01", 1, "Cavity 1"), ("CAV-TACT-02", 2, "Cavity 2")):
        cavities[bid] = post(
            client,
            f"/api/v1/molds/{mold['id']}/cavities",
            idem_key=f"seed-{bid}",
            body={"business_id": bid, "cavity_no": no, "label": label},
        )

    operations = {}
    for bid, seq, name, equipment, param, unit, lo, hi in (
        ("OP-TACT-10", 10, "돔 프레스 성형", "PRESS-01", "dome_thickness_mm", "mm", 0.07, 0.13),
        ("OP-TACT-20", 20, "플런저 인서트 성형", "MOLD-02", "plunger_diameter_mm", "mm", 2.55, 2.65),
        ("OP-TACT-30", 30, "조립", "ASM-CELL-3", "assembly_height_mm", "mm", 2.85, 3.05),
    ):
        operations[bid] = post(
            client,
            "/api/v1/process-operations",
            idem_key=f"seed-{bid}",
            body={
                "business_id": bid,
                "name": name,
                "seq_no": seq,
                "equipment": equipment,
                "window": [{"parameter": param, "unit": unit, "min": lo, "max": hi}],
            },
        )

    def _runs_for_lot(
        lot_id: str,
        lot_bid: str,
        op10_actual: float,
        op20_actual: float = 2.60,
        op30_actual: float = 2.95,
    ) -> None:
        # OP-TACT-20/30 used to be hardcoded to the setpoint on every lot —
        # zero variance, so AN-04's response-surface fit (which requires
        # np.ptp(x) > 0, §7 never fabricate a trend from flat data) always
        # 422'd for plunger_diameter_mm/assembly_height_mm even though the
        # UI lets a user pick either parameter. Real per-lot variation (like
        # OP-TACT-10 already had) is what makes those two selectable.
        actuals = {
            "OP-TACT-10": {"dome_thickness_mm": op10_actual},
            "OP-TACT-20": {"plunger_diameter_mm": op20_actual},
            "OP-TACT-30": {"assembly_height_mm": op30_actual},
        }
        setpoints = {
            "OP-TACT-10": {"dome_thickness_mm": 0.10},
            "OP-TACT-20": {"plunger_diameter_mm": 2.60},
            "OP-TACT-30": {"assembly_height_mm": 2.95},
        }
        for seq, op_bid in (("10", "OP-TACT-10"), ("20", "OP-TACT-20"), ("30", "OP-TACT-30")):
            post(
                client,
                "/api/v1/process-runs",
                idem_key=f"seed-{lot_bid}-PR-{seq}",
                body={
                    "business_id": f"{lot_bid}-PR-{seq}",
                    "lot_id": lot_id,
                    "operation_id": operations[op_bid]["id"],
                    "setpoint": setpoints[op_bid],
                    "actual": actuals[op_bid],
                    "started_at": "2026-09-08T09:00:00Z",
                    "operator": "cell-3",
                },
            )

    # 정상 3 Lot (C1/C2 혼재) + Cavity 편차·윈도우 이탈 Lot 1 (§2.1). plunger/
    # assembly columns give OP-TACT-20/30 the same kind of small in-window
    # lot-to-lot variation OP-TACT-10 already had (see _runs_for_lot note).
    lot_specs = [
        ("LOT-TACT-A-01", "CAV-TACT-01", "MAT-SUS304-0912", "ok", 0.10, 324.0, 2.58, 2.93),
        ("LOT-TACT-A-02", "CAV-TACT-02", "MAT-SUS304-0912", "ok", 0.11, 318.0, 2.61, 2.96),
        ("LOT-TACT-A-03", "CAV-TACT-01", "MAT-SUS304-0912", "ok", 0.09, 331.0, 2.59, 2.94),
        # 이상 Lot: 돔 두께 0.145mm(윈도우 0.07–0.13 이탈) → 피크 365mN(규격 360 초과)
        ("LOT-TACT-A-04", "CAV-TACT-02", "MAT-SUS304-0919", "quarantine", 0.145, 365.0, 2.63, 2.99),
    ]
    plan = client.get(f"/api/v1/variants/{variant_a}/test-plans").json()
    test_plan_id = plan[0]["id"] if plan else None
    for lot_bid, cav_bid, material, disposition, op10_actual, peak, op20_actual, op30_actual in lot_specs:
        lot = post(
            client,
            "/api/v1/lots",
            idem_key=f"seed-{lot_bid}",
            body={
                "business_id": lot_bid,
                "variant_id": variant_a,
                "mold_id": mold["id"],
                "cavity_id": cavities[cav_bid]["id"],
                "material_lot_id": material,
                "work_order_id": "WO-TACT-2609",
                "produced_at": "2026-09-08T09:00:00Z",
                "quantity": 5000,
                "disposition": disposition,
                "notes": "데모 합성 Lot (source: synthetic)",
            },
        )
        _runs_for_lot(lot["id"], lot_bid, op10_actual, op20_actual, op30_actual)
        # Lot별 F–S 검사 (검사는 test_run으로, lot_id로 계보 연결)
        if test_plan_id:
            tr = post(
                test_client,
                "/api/v1/test-runs",
                idem_key=f"seed-{lot_bid}-TR-01",
                body={
                    "business_id": f"{lot_bid}-TR-01",
                    "test_plan_id": test_plan_id,
                    "lot_id": lot["id"],
                    "executed_at": "2026-09-08T11:00:00Z",
                    "equipment_id": "FS-TESTER-01",
                },
            )
            upload_csv_measurements(
                test_client,
                test_run_id=tr["id"],
                csv_bytes=_fs_curve_csv(peak),
                filename=f"{lot_bid}-fs.csv",
                x_unit="mm",
                y_unit="mN",
            )
        if disposition != "ok":
            def1 = post(
                client,
                "/api/v1/defects",
                idem_key=f"seed-{lot_bid}-DEF-1",
                body={
                    "business_id": f"{lot_bid}-DEF-1",
                    "lot_id": lot["id"],
                    "defect_class": "force_high",
                    "severity": "major",
                    "quantity": 12,
                    "note": "작동력 규격 상한 초과 (데모 합성 데이터)",
                },
            )
            post(
                client,
                "/api/v1/defects",
                idem_key=f"seed-{lot_bid}-DEF-2",
                body={
                    "business_id": f"{lot_bid}-DEF-2",
                    "lot_id": lot["id"],
                    "defect_class": "click_ratio_low",
                    "severity": "minor",
                    "quantity": 30,
                    "note": "클릭비 저하 (데모 합성 데이터)",
                },
            )
            seed_fa_capa(client, test_client, approver_client, lot_bid, lot["id"], def1["id"], test_plan_id)
    print(
        "process-twin: mold=MOLD-TACT-01 cavities=2 operations=3 lots=4 "
        "(normal=3 quarantine=1, one out-of-window run, defects=2, "
        "fa=1 capa=2 [1 closed w/ verified retest, 1 approved])"
    )

    # AN-04 DOE / optimization (지시서 §7 AN-04): response-surface regression
    # of dome_thickness_mm (OP-TACT-10 actual) vs. F–S peak over the 4 lots
    # just seeded above (real persisted ProcessRun+TestRun data — no
    # fabricated coefficients, §7). Target band mirrors the demo spec band
    # already shown in ProcessTwin.tsx (260–360 mN, labelled 데모 사양·합성 데이터).
    post(
        client,
        "/api/v1/doe-studies",
        idem_key="seed-DOE-TACT-A-OP10-dome_thickness",
        body={
            "business_id": "DOE-TACT-A-OP10-dome_thickness",
            "variant_id": variant_a,
            "operation_id": operations["OP-TACT-10"]["id"],
            "parameter": "dome_thickness_mm",
            "metric": "peak",
            "target_band": {"min": 260, "max": 360, "unit": "mN"},
            "candidate_grid_size": 5,
        },
    )
    print("doe: DOE-TACT-A-OP10-dome_thickness (dome_thickness_mm vs F-S peak, 4 observations)")


def seed_fa_capa(
    client: httpx.Client,
    test_client: httpx.Client,
    approver_client: httpx.Client,
    lot_bid: str,
    lot_id: str,
    defect_id: str,
    test_plan_id: str | None,
) -> None:
    """Defect → FailureAnalysis → CAPA (HANDOFF §5 item 4, TS10). One FA on
    the anomaly lot's force_high defect, two CAPAs in different lifecycle
    states — one driven all the way to CLOSED with effectiveness verified
    against a real retest TestRun (never a free-text claim), one left at
    APPROVED to show the ledger mid-flight. `client` = demo.architect
    (system_architect, in CAN_MANAGE_QUALITY); `approver_client` =
    demo.approver (reviewer_approver, the only role that may decide/close)."""
    fa = post(
        client,
        f"/api/v1/defects/{defect_id}/failure-analyses",
        idem_key=f"seed-FA-{lot_bid}-1",
        body={
            "business_id": f"FA-{lot_bid}-1",
            "method": "5-Why",
            "findings": (
                f"{lot_bid} 작동력 상한 초과 불량 분석: OP-TACT-10(돔 프레스) 실측 두께가 "
                "승인 윈도우(0.07–0.13mm)를 벗어난 0.145mm로 기록됨 — F-S 피크(365mN)가 "
                "규격 상한(360mN)을 초과한 것과 시기적으로 일치."
            ),
            "analyst": "demo.mech_engineer",
            "analyzed_at": "2026-09-09T09:00:00Z",
            "root_cause": "돔 프레스 공정(OP-TACT-10) 두께 설정 편차로 성형 두께가 상한을 초과하여 작동력이 상승함.",
            "root_cause_confirmed": True,
            "evidence": [
                {
                    "kind": "process_run",
                    "business_id": f"{lot_bid}-PR-10",
                    "note": "돔 프레스 실측 0.145mm (윈도우 0.07–0.13mm)",
                },
                {
                    "kind": "test_run",
                    "business_id": f"{lot_bid}-TR-01",
                    "note": "F-S 피크 365mN (데모 스펙 상한 360mN)",
                },
            ],
        },
    )

    # -- CAPA 1: corrective, driven to CLOSED with a verified retest ---------
    capa1 = post(
        client,
        f"/api/v1/failure-analyses/{fa['id']}/capas",
        idem_key=f"seed-CAPA-{lot_bid}-1",
        body={
            "business_id": f"CAPA-{lot_bid}-1",
            "title": "돔 프레스 공정 파라미터 재관리",
            "capa_type": "corrective",
            "description": "돔 프레스 두께 관리 범위를 재설정하고 공정 파라미터를 재조정한다.",
            "owner": "demo.mech_engineer",
            "due_date": "2026-09-20T00:00:00Z",
        },
    )
    # Idempotent-create cache lesson (AGENTS.md M8): re-fetch live status
    # before deciding which (non-idempotent, Gate-style) transition to try.
    status1 = client.get(f"/api/v1/capas/{capa1['id']}").json()["status"]
    if status1 == "draft":
        r = client.post(
            f"/api/v1/capas/{capa1['id']}/submit",
            json={"business_id": f"CAPA-{lot_bid}-1-EV-SUBMIT", "comment": "원인 확정, 대책안 제출"},
        )
        status1 = _capa_step(r, f"CAPA-{lot_bid}-1 submit", status1)
    if status1 == "pending_review":
        r = approver_client.post(
            f"/api/v1/capas/{capa1['id']}/decisions",
            json={
                "business_id": f"CAPA-{lot_bid}-1-EV-DEC",
                "decision": "approved",
                "comment": "근거(공정 윈도우 이탈) 확인, 대책안 승인",
            },
        )
        status1 = _capa_step(r, f"CAPA-{lot_bid}-1 decide", status1)
    if status1 == "approved":
        r = client.post(
            f"/api/v1/capas/{capa1['id']}/implement",
            json={"business_id": f"CAPA-{lot_bid}-1-EV-IMPL", "comment": "돔 프레스 파라미터 재설정 완료"},
        )
        status1 = _capa_step(r, f"CAPA-{lot_bid}-1 implement", status1)
    if status1 == "implemented" and test_plan_id:
        # A real retest TestRun on the same lot/plan (never a free-text
        # "fixed" claim) — the effectiveness-verification anchor.
        retest = post(
            test_client,
            "/api/v1/test-runs",
            idem_key=f"seed-{lot_bid}-TR-RETEST-01",
            body={
                "business_id": f"{lot_bid}-TR-RETEST-01",
                "test_plan_id": test_plan_id,
                "lot_id": lot_id,
                "executed_at": "2026-09-21T11:00:00Z",
                "equipment_id": "FS-TESTER-01",
            },
        )
        upload_csv_measurements(
            test_client,
            test_run_id=retest["id"],
            csv_bytes=_fs_curve_csv(320.0),
            filename=f"{lot_bid}-retest-fs.csv",
            x_unit="mm",
            y_unit="mN",
        )
        r = client.post(
            f"/api/v1/capas/{capa1['id']}/verify-effectiveness",
            json={
                "business_id": f"CAPA-{lot_bid}-1-EV-VERIFY",
                "test_run_id": retest["id"],
                "comment": "재검사 결과 F-S 피크 320mN — 규격(360mN) 이내로 재발 없음 확인",
            },
        )
        status1 = _capa_step(r, f"CAPA-{lot_bid}-1 verify", status1)
    if status1 == "effectiveness_verified":
        r = approver_client.post(
            f"/api/v1/capas/{capa1['id']}/close",
            json={"business_id": f"CAPA-{lot_bid}-1-EV-CLOSE", "comment": "효과 검증 확인, CAPA 종결"},
        )
        status1 = _capa_step(r, f"CAPA-{lot_bid}-1 close", status1)

    # -- CAPA 2: preventive, left APPROVED (mid-flight ledger state) --------
    capa2 = post(
        client,
        f"/api/v1/failure-analyses/{fa['id']}/capas",
        idem_key=f"seed-CAPA-{lot_bid}-2",
        body={
            "business_id": f"CAPA-{lot_bid}-2",
            "title": "돔 프레스 공정 SPC 관리도 도입",
            "capa_type": "preventive",
            "description": "돔 두께에 대한 관리도를 도입하여 윈도우 이탈을 사전에 탐지한다.",
            "owner": "demo.mech_engineer",
        },
    )
    status2 = client.get(f"/api/v1/capas/{capa2['id']}").json()["status"]
    if status2 == "draft":
        r = client.post(
            f"/api/v1/capas/{capa2['id']}/submit",
            json={"business_id": f"CAPA-{lot_bid}-2-EV-SUBMIT", "comment": "예방조치안 제출"},
        )
        status2 = _capa_step(r, f"CAPA-{lot_bid}-2 submit", status2)
    if status2 == "pending_review":
        r = approver_client.post(
            f"/api/v1/capas/{capa2['id']}/decisions",
            json={"business_id": f"CAPA-{lot_bid}-2-EV-DEC", "decision": "approved", "comment": "예방조치안 승인"},
        )
        status2 = _capa_step(r, f"CAPA-{lot_bid}-2 decide", status2)


def _capa_step(resp: httpx.Response, label: str, fallback_status: str) -> str:
    if resp.status_code >= 400:
        print(f"WARNING: {label} failed: {resp.text}", file=sys.stderr)
        return fallback_status
    return resp.json()["status"]


def seed_process_monitoring(
    client: httpx.Client,
    test_client: httpx.Client,
    variant_ids: dict[str, str],
) -> None:
    """AN-03 관리도용 시계열 보강: VAR-TACT-A에 정상 Lot 6개(LOT-TACT-A-05..10)
    를 추가한다 — 모두 윈도우 내(0.07–0.13) 값으로, 관리도 한계 산정 기준을
    채우고 LOT-04의 0.145(윈도우 이탈)가 유일한 이탈점으로 보이는 안정 공정
    데모를 만든다. Append-only: 고정 idem 키라 재실행 무해."""
    variant_a = variant_ids.get("VAR-TACT-A")
    if not variant_a:
        print("WARNING: VAR-TACT-A missing — process monitoring seed skipped", file=sys.stderr)
        return

    mold = client.get("/api/v1/molds").json()[0]  # MOLD-TACT-01 from seed_process_twin
    # cavities have no list endpoint — re-POST with the seed_process_twin idem
    # keys; idempotent_write returns the existing rows.
    cavities = {}
    for bid, no, label in (("CAV-TACT-01", 1, "Cavity 1"), ("CAV-TACT-02", 2, "Cavity 2")):
        cavities[bid] = post(
            client,
            f"/api/v1/molds/{mold['id']}/cavities",
            idem_key=f"seed-{bid}",
            body={"business_id": bid, "cavity_no": no, "label": label},
        )["id"]
    ops = {o["business_id"]: o["id"] for o in client.get("/api/v1/process-operations").json()}
    plan = client.get(f"/api/v1/variants/{variant_a}/test-plans").json()
    test_plan_id = plan[0]["id"] if plan else None

    # (lot, cavity, material, dome_thickness, peak_mN, produced_at, op10_started_at,
    # plunger_diameter_mm, assembly_height_mm) — the last two used to be hardcoded
    # constants across every lot here and in seed_process_twin, which left AN-04's
    # response-surface fit with zero variance (always 422 "충분한지 확인하세요")
    # for those two of the three selectable parameters. See _runs_for_lot note.
    lot_specs = [
        ("LOT-TACT-A-05", "CAV-TACT-01", "MAT-SUS304-0912", 0.105, 328.0, "2026-09-09T09:00:00Z", "2026-09-09T09:05:00Z", 2.60, 2.95),
        ("LOT-TACT-A-06", "CAV-TACT-02", "MAT-SUS304-0912", 0.095, 322.0, "2026-09-09T13:00:00Z", "2026-09-09T13:05:00Z", 2.57, 2.92),
        ("LOT-TACT-A-07", "CAV-TACT-01", "MAT-SUS304-0916", 0.115, 335.0, "2026-09-10T09:00:00Z", "2026-09-10T09:05:00Z", 2.62, 2.98),
        ("LOT-TACT-A-08", "CAV-TACT-02", "MAT-SUS304-0916", 0.100, 326.0, "2026-09-10T13:00:00Z", "2026-09-10T13:05:00Z", 2.59, 2.95),
        ("LOT-TACT-A-09", "CAV-TACT-01", "MAT-SUS304-0916", 0.095, 319.0, "2026-09-11T09:00:00Z", "2026-09-11T09:05:00Z", 2.61, 2.93),
        ("LOT-TACT-A-10", "CAV-TACT-02", "MAT-SUS304-0912", 0.105, 324.0, "2026-09-11T13:00:00Z", "2026-09-11T13:05:00Z", 2.58, 2.97),
    ]
    for lot_bid, cav_bid, material, dome, peak, produced_at, started_at, plunger, assembly in lot_specs:
        lot = post(
            client,
            "/api/v1/lots",
            idem_key=f"seed-{lot_bid}",
            body={
                "business_id": lot_bid,
                "variant_id": variant_a,
                "mold_id": mold["id"],
                "cavity_id": cavities[cav_bid],
                "material_lot_id": material,
                "work_order_id": "WO-TACT-2609",
                "produced_at": produced_at,
                "quantity": 5000,
                "disposition": "ok",
                "notes": "데모 합성 Lot — 관리도 시계열 보강 (source: synthetic)",
            },
        )
        actuals = {
            "10": {"dome_thickness_mm": dome},
            "20": {"plunger_diameter_mm": plunger},
            "30": {"assembly_height_mm": assembly},
        }
        setpoints = {
            "10": {"dome_thickness_mm": 0.10},
            "20": {"plunger_diameter_mm": 2.60},
            "30": {"assembly_height_mm": 2.95},
        }
        for seq in ("10", "20", "30"):
            post(
                client,
                "/api/v1/process-runs",
                idem_key=f"seed-{lot_bid}-PR-{seq}",
                body={
                    "business_id": f"{lot_bid}-PR-{seq}",
                    "lot_id": lot["id"],
                    "operation_id": ops[f"OP-TACT-{seq}"],
                    "setpoint": setpoints[seq],
                    "actual": actuals[seq],
                    "started_at": started_at,
                    "operator": "cell-3",
                },
            )
        if test_plan_id:
            tr = post(
                test_client,
                "/api/v1/test-runs",
                idem_key=f"seed-{lot_bid}-TR-01",
                body={
                    "business_id": f"{lot_bid}-TR-01",
                    "test_plan_id": test_plan_id,
                    "lot_id": lot["id"],
                    "executed_at": produced_at.replace("T09", "T11").replace("T13", "T15"),
                    "equipment_id": "FS-TESTER-01",
                },
            )
            upload_csv_measurements(
                test_client,
                test_run_id=tr["id"],
                csv_bytes=_fs_curve_csv(peak),
                filename=f"{lot_bid}-fs.csv",
                x_unit="mm",
                y_unit="mN",
            )
    print(
        "process-monitoring: lots=6 added (LOT-TACT-A-05..10, all in-window) "
        "— control-chart basis n=9 with LOT-04 as the lone excluded outlier"
    )


# ── ASIC Twin v1.1 R1 (지시서 §17 PoC: 전류 센서 ASIC) ──────────────────────

ASIC_CS_TEMPLATE = "current_sensor"


def asic_post(
    cl: httpx.Client, path: str, idem_key: str, body: dict, *, list_path: str | None = None,
    match_bid: str | None = None,
) -> dict:
    """POST with a fixed Idempotency-Key. Status guards (RCA already approved,
    ECO already analyzed/closed…) live OUTSIDE idempotent_write, so a re-run
    gets a plain 409 instead of a cached replay — on 409 return the current
    row fetched from list_path so the seed stays idempotent."""
    r = cl.post(path, json=body, headers={"Idempotency-Key": idem_key})
    if r.status_code in (200, 201):
        return r.json()
    if r.status_code == 409 and list_path:
        for row in cl.get(list_path).json():
            if row["business_id"] == match_bid:
                return row
        raise RuntimeError(f"409 on {path} but {match_bid} not found in {list_path}")
    print(f"FAILED {path}: {r.status_code} {r.text}", file=sys.stderr)
    r.raise_for_status()


def _asic_sensor_csv(sens_by_site: dict[int, float], *, executed_hour: int = 2) -> bytes:
    """Synthetic T2000 electrical-test CSV: sensitivity + offset per site."""
    lines = ["name,value,unit,raw_value,raw_unit,site,temperature_c,ts"]
    for i, (site, sens) in enumerate(sorted(sens_by_site.items())):
        lines.append(
            f"sensitivity,{sens:.3f},mA/A,{sens * 1000:.1f},mA,{site},25.0,"
            f"2026-09-10T{executed_hour:02d}:0{i}:00Z"
        )
    lines.append(
        f"offset_uv,{-11.2 - len(sens_by_site) * 0.1:.2f},uV,-11.2,uV,1,25.0,"
        f"2026-09-10T{executed_hour:02d}:10:00Z"
    )
    return ("\n".join(lines) + "\n").encode()


def asic_import_run(
    temc_client: httpx.Client, *, bid: str, csv_bytes: bytes, calibration_expires_at: str,
    executed_at: str, lot_ref: str,
) -> dict:
    r = temc_client.post(
        "/api/v1/asic/measurement-runs/import",
        files={"file": (f"{bid}.csv", csv_bytes, "text/csv")},
        data={
            "business_id": bid, "template_id": ASIC_CS_TEMPLATE,
            "equipment_id": "T2000-KR-02", "equipment_type": "sem_tester",
            "equipment_model": "Advantest T2000", "firmware": "5.1.2",
            "calibration_expires_at": calibration_expires_at,
            "program_revision": "TP-CS-2026-09", "operator": "demo.test_engineer",
            "executed_at": executed_at, "lot_ref": lot_ref,
        },
        headers={"Idempotency-Key": f"seed-asic-{bid}"},
    )
    if r.status_code == 201:
        return r.json()
    if r.status_code == 409:  # same bytes re-seeded after an idem-record wipe
        runs = temc_client.get(f"/api/v1/asic/templates/{ASIC_CS_TEMPLATE}/measurement-runs").json()
        for row in runs:
            if row["business_id"] == bid:
                return row
    print(f"FAILED import {bid}: {r.status_code} {r.text}", file=sys.stderr)
    r.raise_for_status()


def seed_asic_twin(client: httpx.Client, temc_client: httpx.Client, asic_client: httpx.Client) -> None:
    """전류 센서 ASIC 폐루프 데모 (지시서 §17 PoC, EPIC A·E·F·G R1).

    한 판의 이야기: 신호체인 r1→r2 승격 → Corner/MC(교육용 오류예산 모델,
    SYNTHETIC) → T2000 전기 시험 3건(그 중 HTSL 후 측정 1건이 교정 만료 —
    CALIBRATION_EXPIRED 블로커의 씨앗) → AEC-Q100 G1 매트릭스에서 HTSL 1건
    실패 → FA 케이스(RCA 승인은 인간 전담) → ECO A0→A1 → 회귀+재검증으로
    종결 → 재시험 pass. 최종 게이트는 MOCK_RESULT_PRESENT + CALIBRATION_EXPIRED
    만 남는다(§15: 플랫폼은 출시 판정을 대체하지 않는다).
    """
    t = ASIC_CS_TEMPLATE

    # ── EPIC A: 신호체인 r1 → r2 (r2 생성 시 r1 자동 supersede) ─────────────
    base_blocks = [
        {"key": "shunt", "kind": "sensor", "label": "Shunt 저항 1 mΩ",
         "params": {"nominal": 100.0, "calib_min": -40.0, "calib_max": 125.0},
         "error_budget": {"offset": 0.08, "noise": 0.25, "drift": 0.012},
         "requirement_ids": ["REQ-CS-SENS"]},
        {"key": "afe", "kind": "analog", "label": "차동 증폭기 (G=50)",
         "params": {"gain": 50.0},
         "error_budget": {"offset": 0.06, "gain_error": 0.12, "drift": 0.008, "noise": 0.1},
         "requirement_ids": ["REQ-CS-AFE"]},
        {"key": "adc", "kind": "mixed", "label": "16-bit SAR ADC",
         "params": {"bits": 16}, "error_budget": {"inl": 0.15, "dnl": 0.05, "noise": 0.08},
         "requirement_ids": ["REQ-CS-ADC"]},
        {"key": "dsp", "kind": "digital", "label": "온도 보정 DSP",
         "params": {"fw": "1.2.0"}, "error_budget": {}},
    ]
    chain_r1 = asic_post(client, "/api/v1/asic/signal-chains", "seed-asic-chain-r1", {
        "business_id": "ASIC-CS-CHAIN-R1", "template_id": t, "blocks": base_blocks,
        "note": "초기 테이프아웃안 — A0 마스크",
    }, list_path=f"/api/v1/asic/templates/{t}/signal-chains", match_bid="ASIC-CS-CHAIN-R1")
    chain_r2 = asic_post(client, "/api/v1/asic/signal-chains", "seed-asic-chain-r2", {
        "business_id": "ASIC-CS-CHAIN-R2", "template_id": t, "blocks": base_blocks,
        "note": "r1 보정계수 갱신 + DSP FW 1.2.0 (ECO-001 반영 전 기준선)",
    }, list_path=f"/api/v1/asic/templates/{t}/signal-chains", match_bid="ASIC-CS-CHAIN-R2")

    spec_full = [
        {"output": "sensitivity", "nominal": 100.0, "min": 98.5, "max": 101.5, "unit": "mA/A"},
        {"output": "offset_uv", "nominal": 0.0, "min": -25.0, "max": 25.0, "unit": "uV"},
        {"output": "inl_lsb", "nominal": 1.0, "max": 1.5, "unit": "LSB"},
    ]
    mc1 = asic_post(client, "/api/v1/asic/corner-studies", "seed-asic-mc-001", {
        "business_id": "ASIC-CS-MC-001", "signal_chain_id": chain_r2["id"], "kind": "monte_carlo",
        "n_draws": 2000, "spec": spec_full,
    }, list_path=f"/api/v1/asic/templates/{t}/corner-studies", match_bid="ASIC-CS-MC-001")
    print(f"asic: chain r1/r2 + MC-001 (seed={mc1['seed']}, OOD={mc1['result']['model_ood']})")

    # ── EPIC E: T2000 전기 시험 3건 ─────────────────────────────────────────
    run_pre = asic_import_run(temc_client, bid="ASIC-CS-EL-PRE",
                              csv_bytes=_asic_sensor_csv({1: 99.98, 2: 100.02, 3: 100.01, 4: 99.97, 5: 100.05}),
                              calibration_expires_at="2027-06-30T00:00:00Z",
                              executed_at="2026-06-10T02:00:00Z", lot_ref="CURR-LOT-2609A")
    run_post = asic_import_run(temc_client, bid="ASIC-CS-EL-HTSL-POST",
                               csv_bytes=_asic_sensor_csv({1: 99.9, 2: 99.85, 3: 96.42, 4: 99.9, 5: 99.88},
                                                          executed_hour=5),
                               calibration_expires_at="2026-03-01T00:00:00Z",  # HTSL 후 측정 시 이미 만료
                               executed_at="2026-08-20T05:00:00Z", lot_ref="CURR-LOT-2609A")
    run_verify = asic_import_run(temc_client, bid="ASIC-CS-EL-VERIFY",
                                 csv_bytes=_asic_sensor_csv({1: 99.97, 2: 100.01, 3: 99.99, 4: 100.02, 5: 100.0},
                                                            executed_hour=8),
                                 calibration_expires_at="2027-06-30T00:00:00Z",
                                 executed_at="2026-09-12T08:00:00Z", lot_ref="CURR-LOT-2609B")

    # ── EPIC G(전반): FA 케이스 → 가설 → RCA 승인(인간) ────────────────────
    fa_case = asic_post(asic_client, "/api/v1/asic/fa-cases", "seed-asic-fa-001", {
        "business_id": "ASIC-CS-FA-001", "template_id": t, "scope": "lot",
        "lot_ref": "CURR-LOT-2609A",
        "symptom": "HTSL 1000h 후 site 3 감도 드리프트 -3.6% (규격 하한 98.5 mA/A 이탈)",
        "repro_condition": "HTSL 125°C/1000h 바이어스 인가 후 상온 전기 시험에서 재현",
        "observations": [
            {"fact": "site 3 감도 96.42 mA/A — 규격 하한 98.5 이탈, 타 site는 규격 내",
             "source": "ASIC-CS-EL-HTSL-POST"},
            {"fact": "CSAM 분석에서 site 3의 2번 본드 패드 주변 층간 박리 확인",
             "source": "CSAM (Sonoscan D9500)"},
            {"fact": "HTSL 이전 측정(pre-stress)에서는 5 site 모두 규격 내",
             "source": "ASIC-CS-EL-PRE"},
        ],
        "location": {"ref": "die/bond-pad-2", "x": 812, "y": 340, "note": "site 3 다이 좌표계"},
    }, list_path=f"/api/v1/asic/templates/{t}/fa-cases", match_bid="ASIC-CS-FA-001")
    asic_client.patch(
        f"/api/v1/asic/fa-cases/{fa_case['id']}",
        json={"hypotheses": [
            {"text": "2번 본드 패드 히트싱크 응력 집중에 의한 와이어 본드 피로",
             "confirm_tests": ["CSAM 층간 박리 확인", "드리프트 곡선 온도 의존성 재현"], "excluded": False},
            {"text": "몰드 컴파운드 수분 흡수에 의한 접속 부식",
             "confirm_tests": ["HAST 재시험 비교"], "excluded": True,
             "exclusion_basis": "HAST 통과 로트(CURR-LOT-2608C)에서는 동일 드리프트가 없음"},
            {"text": "측정 시스템(테스터) 보정 이상",
             "confirm_tests": ["교정 만료 여부 및 타 장비 교차 확인"], "excluded": True,
             "exclusion_basis": "교차 측정에서도 site 3 드리프트 동일 재현 — 기기 원인 아님"},
        ], "status": "analyzing"},
    )

    # ── EPIC F: AEC-Q100 G1 매트릭스 ────────────────────────────────────────
    plan = asic_post(client, "/api/v1/asic/qualification-plans", "seed-asic-qual-plan", {
        "business_id": "ASIC-CS-QUAL-G1", "template_id": t, "grade": "G1",
        "standard_version": "AEC-Q100 Rev-H",
        "note": "전류 센서 ASIC 자동차용 G1 인증 매트릭스 (데모용 축소판: TC·TH·HTSL)",
    }, list_path=f"/api/v1/asic/templates/{t}/qualification-plans", match_bid="ASIC-CS-QUAL-G1")

    def qual_row(bid: str, grp: str, method: str, condition: dict, status: str, idem: str,
                 *, post_run=None, failed_param=None, fa_case_id=None) -> dict:
        return asic_post(client, f"/api/v1/asic/qualification-plans/{plan['id']}/results", idem, {
            "business_id": bid, "group": grp, "method": method, "condition": condition,
            "samples": "3 lot × 77", "lots": ["CURR-LOT-2609A", "CURR-LOT-2609B", "CURR-LOT-2609C"],
            "pre_electrical_run_id": run_pre["id"],
            **({"post_electrical_run_id": post_run["id"]} if post_run else {}),
            "status": status,
            **({"failed_param": failed_param} if failed_param else {}),
            **({"fa_case_id": fa_case_id} if fa_case_id else {}),
        })

    qual_row("ASIC-CS-QUAL-TC", "TC", "AEC-Q100 TC (온도 사이클 -40↔125°C, 1000 cycle)",
             {"temp_min_c": -40, "temp_max_c": 125, "cycles": 1000}, "pass", "seed-asic-qual-tc")
    qual_row("ASIC-CS-QUAL-TH", "TH", "AEC-Q100 TH (고온·고습 85°C/85%RH, 1000 h)",
             {"temp_c": 85, "rh": 85, "duration_h": 1000}, "pass", "seed-asic-qual-th")
    qual_row("ASIC-CS-QUAL-HTSL", "HTSL", "AEC-Q100 HTSL (고온 저장 125°C, 1000 h)",
             {"temp_c": 125, "duration_h": 1000}, "fail", "seed-asic-qual-htsl",
             post_run=run_post, failed_param="sensitivity", fa_case_id=fa_case["id"])

    # RCA 승인 (인간 전용 — 관찰 사실 + 확인 증적이 모두 존재한 뒤에야 가능)
    asic_post(asic_client, f"/api/v1/asic/fa-cases/{fa_case['id']}/root-cause", "seed-asic-rca-001", {
        "root_cause": "2번 본드 패드의 히트싱크 응력 집중에 의한 와이어 본드 피로 — "
                      "HTSL 열사이클 중 패드 언더메탈 마이크로크랙이 성장해 접촉저항이 상승 "
                      "(CSAM 박리 + 드리프트 온도의존성 재현으로 확인)",
        "cause_class": "package", "comment": "패키지 설계·신뢰성 합의 (2026-09-12 RCA 리뷰)",
        "evidence_business_ids": ["ASIC-CS-EL-HTSL-POST", "ASIC-CS-QUAL-HTSL"],
    }, list_path=f"/api/v1/asic/templates/{t}/fa-cases", match_bid="ASIC-CS-FA-001")

    qual_row("ASIC-CS-QUAL-HTSL-RT", "HTSL", "AEC-Q100 HTSL 재시험 (ECO A1 패키지, 1000 h)",
             {"temp_c": 125, "duration_h": 1000, "note": "ECO-001 효과 검증 재시험"}, "pass",
             "seed-asic-qual-htsl-rt", post_run=run_verify)

    # ── EPIC G(후반): ECO → 회귀 → 종결 (재검증 없으면 412) ─────────────────
    eco = asic_post(asic_client, "/api/v1/asic/ecos", "seed-asic-eco-001", {
        "business_id": "ASIC-CS-ECO-001", "template_id": t, "fa_case_business_id": "ASIC-CS-FA-001",
        "trigger": "fa_case", "title": "2번 본드 패드 히트싱크 완화 (A0→A1)",
        "description": "패드 언더메탈 두께 증가 + 와이어 본드 프로파일 변경. "
                       "테스트 프로그램은 site 3 HTSL 샘플링을 2배로 강화.",
        "design_rev_from": "A0", "design_rev_to": "A1", "mask_revision": "MASK-A1",
        "test_program_revision": "TP-CS-2026-09-A1",
        "impact": [
            {"area": "package", "detail": "본드 패드 언더메탈 0.8→1.2 µm"},
            {"area": "process", "detail": "본드 프로파일 파라미터 3건 변경"},
            {"area": "test_program", "detail": "HTSL 샘플링 강화 (site 3 ×2)"},
        ],
    }, list_path=f"/api/v1/asic/templates/{t}/ecos", match_bid="ASIC-CS-ECO-001")
    eco = asic_post(asic_client, f"/api/v1/asic/ecos/{eco['id']}/analyze", "seed-asic-eco-an", {
        "design_rev_from": "A0", "design_rev_to": "A1", "mask_revision": "MASK-A1",
        "test_program_revision": "TP-CS-2026-09-A1",
        "impact": eco.get("impact") or [],
    }, list_path=f"/api/v1/asic/templates/{t}/ecos", match_bid="ASIC-CS-ECO-001")
    mc2 = asic_post(client, "/api/v1/asic/corner-studies", "seed-asic-mc-002", {
        "business_id": "ASIC-CS-MC-002", "signal_chain_id": chain_r2["id"], "kind": "monte_carlo",
        "n_draws": 3000,
        "spec": [{"output": "sensitivity", "nominal": 100.0, "min": 98.5, "max": 101.5, "unit": "mA/A"},
                 {"output": "offset_uv", "nominal": 0.0, "min": -25.0, "max": 25.0, "unit": "uV"}],
    }, list_path=f"/api/v1/asic/templates/{t}/corner-studies", match_bid="ASIC-CS-MC-002")
    eco = asic_post(asic_client, f"/api/v1/asic/ecos/{eco['id']}/regression", "seed-asic-eco-reg", {
        "regression_run_ids": [mc2["business_id"], run_verify["business_id"]],
        "comment": "패키지 변경 회귀: MC-002(신뢰성 여유) + A1 패키지 전기 시험",
    }, list_path=f"/api/v1/asic/templates/{t}/ecos", match_bid="ASIC-CS-ECO-001")
    eco = asic_post(client, f"/api/v1/asic/ecos/{eco['id']}/close", "seed-asic-eco-close", {
        "verification_run_business_id": "ASIC-CS-EL-VERIFY",
        "verification_note": "site 3 재측정 99.99 mA/A — HTSL 재시험 3 lot 모두 규격 내 복원 확인",
        "comment": "RCA 리뷰 패널 승인 (2026-09-14)",
    }, list_path=f"/api/v1/asic/templates/{t}/ecos", match_bid="ASIC-CS-ECO-001")

    # ── EPIC F: 기능안전 트레이스 SG→FSR→TSR→HW + FMEDA + 고장주입 ──────────
    sg = asic_post(client, "/api/v1/asic/safety-items", "seed-asic-sg-1", {
        "business_id": "ASIC-CS-SG-1", "template_id": t, "level": "safety_goal",
        "title": "과전류를 정상 전류로 보고해서는 안 된다 (ASIL B)",
        "asil": "B", "safe_state": "출력 클램프 + /FAULT low",
    }, list_path=f"/api/v1/asic/templates/{t}/safety-items", match_bid="ASIC-CS-SG-1")
    fsr = asic_post(client, "/api/v1/asic/safety-items", "seed-asic-fsr-1", {
        "business_id": "ASIC-CS-FSR-1", "template_id": t, "level": "fsr",
        "parent_business_id": "ASIC-CS-SG-1",
        "title": "측정 체인 이상을 200 ms 이내에 감지하여 safe state로 진입할 것",
        "asil": "B", "safety_mechanism": "범위·경향 감시 (DSP 워치독 + 플라우저리 한정자)",
        "response_time_ms": 200.0,
    }, list_path=f"/api/v1/asic/templates/{t}/safety-items", match_bid="ASIC-CS-FSR-1")
    tsr = asic_post(client, "/api/v1/asic/safety-items", "seed-asic-tsr-1", {
        "business_id": "ASIC-CS-TSR-1", "template_id": t, "level": "tsr",
        "parent_business_id": "ASIC-CS-FSR-1",
        "title": "ADC 출력 범위검사 + 션트 개락 감지 (TSR)",
        "asil": "B", "safety_mechanism": "이중 범위 한정자 + 기준전원 이중화 비교",
        "diagnostic_coverage_pct": 90.0, "response_time_ms": 100.0,
    }, list_path=f"/api/v1/asic/templates/{t}/safety-items", match_bid="ASIC-CS-TSR-1")
    asic_post(client, "/api/v1/asic/safety-items", "seed-asic-hw-1", {
        "business_id": "ASIC-CS-HW-1", "template_id": t, "level": "hw_req",
        "parent_business_id": "ASIC-CS-TSR-1",
        "title": "션트 개락 감지 회로: 전류원 바이어스 + 컴퍼레이터 임계 0.9×FS",
        "asil": "B", "safety_mechanism": "개락 감지 컴퍼레이터",
        "diagnostic_coverage_pct": 95.0, "response_time_ms": 10.0,
    }, list_path=f"/api/v1/asic/templates/{t}/safety-items", match_bid="ASIC-CS-HW-1")

    fmeda_source = b"FMEDA workbook (synthetic demo) - current sensor A1"
    fmeda_hash = hashlib.sha256(fmeda_source).hexdigest()
    for i, (bid, mode, dist, dc, fit) in enumerate((
        ("ASIC-CS-FMEDA-1", "션트 개락 (Open shunt)", 30.0, 95.0, 8.0),
        ("ASIC-CS-FMEDA-2", "ADC 출력 고정 (Stuck output)", 25.0, 90.0, 12.0),
        ("ASIC-CS-FMEDA-3", "기준전원 드리프트 (Reference drift)", 15.0, 70.0, 5.0),
    )):
        asic_post(client, "/api/v1/asic/fmeda-items", f"seed-asic-fmeda-{i + 1}", {
            "business_id": bid, "safety_item_business_id": "ASIC-CS-TSR-1",
            "failure_mode": mode, "distribution_pct": dist, "dc_pct": dc, "fit_rate": fit,
            "source_ref": "FMEDA_WS_CS_A1.xlsx#TSR", "source_hash": fmeda_hash,
            "formula_version": "SN29500-2024 + IEC 62380:2004",
            "note": "수치는 교육용 합성값입니다 (SYNTHETIC)",
        })
    asic_post(client, "/api/v1/asic/fault-injections", "seed-asic-fi-001", {
        "business_id": "ASIC-CS-FI-001", "safety_item_business_id": "ASIC-CS-TSR-1",
        "method": "HIL 전류 스텝 주입", "stimulus": "150 A 과전류 스텝 (정격 100 A, 500 ms 유지)",
        "expected": "100 ms 이내 /FAULT low + 출력 클램프 (safe state 진입)",
        "observed": "87 ms 내 /FAULT low + 클램프 확인 (5회 반복 모두 통과)",
        "status": "pass", "executed_by": "demo.architect", "executed_at": "2026-09-13T04:00:00Z",
    })

    # ── 최종 게이트 리포트 확인 ─────────────────────────────────────────────
    report = client.get(f"/api/v1/asic/gate-report/{t}").json()
    codes = sorted(b["code"] for b in report["blockers"])
    print(
        "asic: 전류 센서 폐루프 시드 완료 — chains r1/r2, MC×2, runs×3, qual×4(HTSL fail→재시험 pass), "
        f"FA→RCA→ECO-001 종결, safety SG→FSR→TSR→HW+FMEDA×3+FI×1 | "
        f"gate={report['status']} blockers={codes} readiness={report['readiness']}"
    )


class RefreshingAuth(httpx.Auth):
    """Password-grant login, refreshed transparently on 401.

    Keycloak access tokens live ~5 min (realm default) while the seed —
    especially the AirInput FD-solver section — runs far longer than that,
    so a token captured once at startup expires mid-run.
    """

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._token: str | None = None

    def _login(self) -> str:
        self._token = get_token(self.username, self.password)
        return self._token

    def auth_flow(self, request: httpx.Request):
        if self._token is None:
            self._login()
        request.headers["Authorization"] = f"Bearer {self._token}"
        response = yield request
        if response.status_code == 401:
            self._login()
            request.headers["Authorization"] = f"Bearer {self._token}"
            yield request


def main() -> None:
    with (
        httpx.Client(base_url=API_URL, auth=RefreshingAuth("demo.architect", "demo1234")) as client,
        httpx.Client(base_url=API_URL, auth=RefreshingAuth("demo.mech_engineer", "demo1234")) as test_client,
        httpx.Client(base_url=API_URL, auth=RefreshingAuth("demo.approver", "demo1234")) as approver_client,
        httpx.Client(base_url=API_URL, auth=RefreshingAuth("demo.test_engineer", "demo1234")) as temc_client,
        httpx.Client(base_url=API_URL, auth=RefreshingAuth("demo.asic_engineer", "demo1234")) as asic_client,
    ):
        for product_spec in PRODUCTS:
            product = post(
                client,
                "/api/v1/products",
                idem_key=f"seed-{product_spec['business_id']}",
                body={
                    "business_id": product_spec["business_id"],
                    "name": product_spec["name"],
                    "description": product_spec["description"],
                },
            )
            variant_ids = {}
            for variant_spec in product_spec["variants"]:
                variant_ids[variant_spec["business_id"]] = seed_variant(
                    client, test_client, approver_client, product["id"], variant_spec
                )
            # Process-Twin vertical slice targets the TACT family only (§2.1
            # 권장 대상: TACT Switch 제품군 1개).
            if product_spec["business_id"] == "PROD-TACT-SWITCH":
                seed_process_twin(client, test_client, approver_client, variant_ids)
                seed_process_monitoring(client, test_client, variant_ids)

        # AirInput vertical slice: 4th product family, mech-model→correlation
        # only (see seed_airinput_product for the scope-cut rationale).
        seed_airinput_product(client, test_client)
        # AirInput 3D Interaction Field Twin: FD solver + surrogate + GOLD
        # replays on the same two variants (§6.2 two-tier, §11.2 scenarios).
        seed_airinput_field_twin(client, test_client)

        # ASIC Twin v1.1 R1: 전류 센서 폐루프 PoC (§17) — EPIC A·E·F·G.
        seed_asic_twin(client, temc_client, asic_client)
        # ASIC Twin v1.1 R2: EPIC B·C·D·H + 템플릿 4종 검증 팩 (P1-07).
        seed_asic_r2(client, temc_client, asic_client)




# ── ASIC Twin v1.1 R2 (지시서 §10 R2: EPIC B·C·D·H + 템플릿 4종 팩) ───────────

_TP_R2_REV = {
    "silicon_revision": "A1", "compatible_mask_rev": "MASK-A1", "compatible_package_rev": "PKG-A1",
}


def seed_asic_r2(client: httpx.Client, temc_client: httpx.Client, asic_client: httpx.Client) -> None:
    """전류 센서 ASIC R2 한 판 (EPIC B·C·D·H, 지시서 §4·§10).

    공급망은 '청결'하게 심는다 — 승인 파트너만 lot 경로에, PCN은 즉시 승인,
    품질조치는 종결 — 최종 게이트 블로커는 R1과 동일한
    MOCK_RESULT_PRESENT + CALIBRATION_EXPIRED 두 개로 유지된다. PCN 대기·
    미승인 파트너·계보 파손 상태는 pytest가 만든다.
    """
    t = ASIC_CS_TEMPLATE

    # ── EPIC C: EDA ToolRun — 실제 SPICE(real_adapter) 2건 + 공개 mock 1건 ──
    netlist = b"* current_sensor A1 sense chain, ngspice netlist (synthetic demo)"
    ih = hashlib.sha256(netlist).hexdigest()
    tr1 = asic_post(temc_client, "/api/v1/asic/tool-runs", "seed-asic-r2-tr-1", {
        "business_id": "ASIC-CS-TR-SPICE-001", "template_id": t, "design_revision": 2,
        "tool": "ams", "tool_version": "ngspice-44", "runner_class": "real_adapter",
        "environment": {"simulator": "ngspice-44", "host_os": "linux", "cpu": "x86_64"},
        "command_profile": "ngspice -b cs_a1_sense.sp",
        "input_hash": ih, "output_hash": hashlib.sha256(b"raw-waveform-v1").hexdigest(),
        "exit_code": 0,
        "metrics": {"sensitivity_ma_a": 100.12, "offset_uv": 3.1, "sim_time_s": 41.7},
        "note": "외부 SPICE 실행 브리지 (real_adapter)",
    }, list_path=f"/api/v1/asic/templates/{t}/tool-runs", match_bid="ASIC-CS-TR-SPICE-001")
    # 동일 (template, tool, input_hash) 재실행 → 같은 lineage에 append
    tr2 = asic_post(temc_client, "/api/v1/asic/tool-runs", "seed-asic-r2-tr-2", {
        "business_id": "ASIC-CS-TR-SPICE-002", "template_id": t, "design_revision": 2,
        "tool": "ams", "tool_version": "ngspice-44", "runner_class": "real_adapter",
        "environment": {"simulator": "ngspice-44", "host_os": "linux", "cpu": "x86_64"},
        "command_profile": "ngspice -b cs_a1_sense.sp",
        "input_hash": ih, "output_hash": hashlib.sha256(b"raw-waveform-v2-retry").hexdigest(),
        "exit_code": 0, "metrics": {"sensitivity_ma_a": 100.12, "note": "재실행 재현성 확인"},
        "note": "동일 입력 재실행 — lineage_id가 SPICE-001과 동일해야 한다",
    }, list_path=f"/api/v1/asic/templates/{t}/tool-runs", match_bid="ASIC-CS-TR-SPICE-002")
    same_lineage = tr1["lineage_id"] == tr2["lineage_id"]
    if not same_lineage:
        print("WARNING: SPICE-001/002 lineage_id 불일치 (수용기준 4 위반)", file=sys.stderr)
    asic_post(temc_client, "/api/v1/asic/tool-runs", "seed-asic-r2-tr-3", {
        "business_id": "ASIC-CS-TR-LINT-001", "template_id": t, "design_revision": 2,
        "tool": "lint", "tool_version": "edulint-2026.1-mock", "runner_class": "mock",
        "input_hash": hashlib.sha256(b"rtl snapshot r2 (synthetic)").hexdigest(),
        "exit_code": 0, "metrics": {"violations": 0},
        "note": "공개된 mock 실행 — 게이트 MOCK_RESULT_PRESENT 블로커와 연동 (교육용)",
    }, list_path=f"/api/v1/asic/templates/{t}/tool-runs", match_bid="ASIC-CS-TR-LINT-001")
    print(f"asic r2: tool runs 3건 (spice lineage 동일={same_lineage}, lint=mock 공개)")

    # ── EPIC B: 제조 옵션 3종 + Trade Study + 의사결정 ──────────────────────
    def nre(mask, design, ip, mpw):
        return {
            "design": {"amount": design, "currency": "KRW", "basis_date": "2026-09-01"},
            "ip": {"amount": ip, "currency": "KRW", "basis_date": "2026-09-01"},
            "mask": {"amount": mask, "currency": "KRW", "basis_date": "2026-09-01"},
            "mpw_shuttle": {"amount": mpw, "currency": "KRW", "basis_date": "2026-09-01"},
            "pkg_tooling": {"amount": 180_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
            "test_dev": {"amount": 120_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
            "reliability": {"amount": 90_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
        }

    def unit(wafer, dies, assembly, ft, die_yield):
        return {
            "wafer": {"base": wafer, "best": round(wafer * 0.95, 1), "worst": round(wafer * 1.10, 1),
                      "unit": "KRW", "dies_per_wafer": dies, "basis_date": "2026-09-01"},
            "assembly": {"base": assembly, "best": round(assembly * 0.95, 1),
                         "worst": round(assembly * 1.15, 1), "unit": "KRW", "basis_date": "2026-09-01"},
            "final_test": {"base": ft, "best": round(ft * 0.95, 1), "worst": round(ft * 1.10, 1),
                           "unit": "KRW", "basis_date": "2026-09-01"},
            "logistics": {"base": 40.0, "best": 36.0, "worst": 52.0, "unit": "KRW",
                          "basis_date": "2026-09-01"},
            "die_yield": {"base": die_yield, "basis_date": "2026-09-01"},
            "scrap": {"base": 0.008, "basis_date": "2026-09-01"},
        }

    sched = [
        {"phase": "pdk_ip", "weeks_base": 6, "weeks_best": 5, "weeks_worst": 9},
        {"phase": "design", "weeks_base": 14, "weeks_best": 12, "weeks_worst": 20},
        {"phase": "tapeout", "weeks_base": 10, "weeks_best": 8, "weeks_worst": 14},
        {"phase": "wafer", "weeks_base": 12, "weeks_best": 10, "weeks_worst": 16},
        {"phase": "assembly", "weeks_base": 6, "weeks_best": 5, "weeks_worst": 9},
        {"phase": "qualification", "weeks_base": 14, "weeks_best": 12, "weeks_worst": 18},
    ]
    opt_a = asic_post(asic_client, "/api/v1/asic/manufacturing-options", "seed-asic-r2-opt-a", {
        "business_id": "ASIC-CS-OPT-A28", "template_id": t,
        "foundry": "F1 Fab (교육용 가명)", "node": "28nm", "wafer_size_mm": 300,
        "voltage_option": "3.3V", "device_option": "current sensor A1",
        "temperature_grade": "AEC-Q100 G1", "package": "QFN-32", "osat": "OSAT-K1",
        "moq": 5000, "tech_score": 4, "nre": nre(2_400_000_000, 900_000_000, 750_000_000, 0),
        "unit_cost": unit(980_000, 8200, 210.0, 85.0, 0.82),
        "schedule": sched,
        "risks": [{"kind": "long_lead", "note": "마스크 셋 리드타임 10주", "severity": "medium"}],
        "note": "28nm 고정밀 안 — NRE 높지만 단가·정밀도 우위",
    }, list_path=f"/api/v1/asic/templates/{t}/manufacturing-options", match_bid="ASIC-CS-OPT-A28")
    opt_b = asic_post(asic_client, "/api/v1/asic/manufacturing-options", "seed-asic-r2-opt-b", {
        "business_id": "ASIC-CS-OPT-B55", "template_id": t,
        "foundry": "F2 Fab (교육용 가명)", "node": "55nm", "wafer_size_mm": 200,
        "voltage_option": "5V", "device_option": "current sensor A1",
        "temperature_grade": "AEC-Q100 G1", "package": "QFN-32", "osat": "OSAT-K1",
        "moq": 3000, "tech_score": 3,
        "nre": {
            "design": {"amount": 520_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
            "ip": {"amount": 300_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
            "mask": {"amount": 350_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
            "pkg_tooling": {"amount_tbd": "견적 대기 — 2차 벤더 협상 중 (TBD 규칙 시연)"},
            "test_dev": {"amount": 110_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
            "reliability": {"amount": 85_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
        },
        "unit_cost": unit(620_000, 2600, 205.0, 85.0, 0.78),
        "schedule": sched,
        "risks": [{"kind": "long_lead", "note": "200mm 웨이퍼 공급 변동", "severity": "medium"}],
        "note": "55nm 균형안 — pkg_tooling TBD (0으로 계산되지 않음)",
    }, list_path=f"/api/v1/asic/templates/{t}/manufacturing-options", match_bid="ASIC-CS-OPT-B55")
    opt_c = asic_post(asic_client, "/api/v1/asic/manufacturing-options", "seed-asic-r2-opt-c", {
        "business_id": "ASIC-CS-OPT-C90", "template_id": t,
        "foundry": "F3 Fab (교육용 가명)", "node": "90nm", "wafer_size_mm": 200,
        "voltage_option": "5V", "device_option": "current sensor A1",
        "temperature_grade": "AEC-Q100 G2", "package": "SOIC-8", "osat": "OSAT-K2 (가칭)",
        "moq": 2000, "tech_score": 2,
        "nre": {
            "design": {"amount": 380_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
            "ip": {"amount": 210_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
            "mask": {"amount": 220_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
            "pkg_tooling": {"amount": 95_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
            "test_dev": {"amount": 90_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
            "reliability": {"amount": 70_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
        },
        "unit_cost": unit(410_000, 1500, 180.0, 78.0, 0.72),
        "schedule": [dict(s, weeks_base=w + 2, weeks_best=w + 1, weeks_worst=w + 4) for s, w in
                     zip(sched, (4, 12, 8, 10, 6, 12))],
        "risks": [
            {"kind": "supply_single", "note": "단일 공급망 — 2차 소스 없음", "severity": "high"},
            {"kind": "equipment_availability", "note": "G2 등급 라인 가용성", "severity": "medium"},
        ],
        "note": "90nm 저가안 — 기술·공급 리스크로 가중 점수 하락 예상",
    }, list_path=f"/api/v1/asic/templates/{t}/manufacturing-options", match_bid="ASIC-CS-OPT-C90")

    study = asic_post(asic_client, "/api/v1/asic/trade-studies", "seed-asic-r2-ts-1", {
        "business_id": "ASIC-CS-TS-001", "template_id": t,
        "title": "전류 센서 ASIC 공정/파트너 선택 (2026-09)",
        "option_ids": [opt_a["id"], opt_b["id"], opt_c["id"]],
        "weights": {"cost": 0.4, "schedule": 0.2, "technology": 0.2, "supply": 0.2},
        "annual_volume": 2_000_000,
        "note": "연 200만 개 기준 — TBD 옵션(B55)은 partial_score만 산출",
    }, list_path=f"/api/v1/asic/templates/{t}/trade-studies", match_bid="ASIC-CS-TS-001")
    winner_id = study["result"]["ranking"][0]
    study = asic_post(client, f"/api/v1/asic/trade-studies/{study['id']}/decision",
                      "seed-asic-r2-ts-decide", {
        "option_id": winner_id,
        "rationale": "가중 점수 1위 옵션으로 확정 — TBD 항목 해소 후 1차 벤더 계약 진행",
        "residual_risks": ["마스크 리드타임 변동", "단가 협정 전 환율 변동"],
    }, list_path=f"/api/v1/asic/templates/{t}/trade-studies", match_bid="ASIC-CS-TS-001")
    print(f"asic r2: options 3종(1 TBD) + trade study 결정={study['decision']['option_id'] == winner_id}")

    # ── EPIC D: test flow 2종 + wafer map + 한계값 변경 검토안 ──────────────
    def flow_items(*, full: bool) -> list[dict]:
        items = [
            {"seq": 1, "stage": "contact", "name": "Contact 전도성 확인",
             "limits": {"high": 5.0, "unit": "ohm"}, "expected_duration_s": 0.05,
             "site_count": 8, "instrument": "T2000-CHA1",
             "defect_coverage": [{"defect_class": "open", "coverage_pct": 96.0},
                                 {"defect_class": "short", "coverage_pct": 94.0}],
             "failure_mode_refs": ["FM-CS-OPEN"]},
            {"seq": 2, "stage": "dc", "name": "DC 파라미터 (오프셋)",
             "limits": {"low": -25.0, "high": 25.0, "unit": "uV"}, "temperature_c": 25.0,
             "expected_duration_s": 0.12, "site_count": 8, "instrument": "T2000-CHA2",
             "defect_coverage": [{"defect_class": "parametric", "coverage_pct": 90.0},
                                 {"defect_class": "leakage", "coverage_pct": 88.0}],
             "requirement_ids": ["REQ-CS-AFE"]},
            {"seq": 3, "stage": "analog", "name": "감도 스윕 (100 A 등가)",
             "limits": {"low": 98.5, "high": 101.5, "unit": "mA/A"}, "temperature_c": 25.0,
             "expected_duration_s": 0.30, "site_count": 4, "instrument": "T2000-CHA3",
             "pattern": "SENS_SWEEP_v3",
             "defect_coverage": [{"defect_class": "parametric", "coverage_pct": 95.0}],
             "requirement_ids": ["REQ-CS-SENS"]},
            {"seq": 4, "stage": "trim_cal", "name": "오프셋 트림/캘리브레이션",
             "expected_duration_s": 0.45, "site_count": 4, "instrument": "T2000-CHA2",
             "requirement_ids": ["REQ-CS-AFE"]},
            {"seq": 5, "stage": "final_bin", "name": "최종 빈 분류",
             "expected_duration_s": 0.02, "site_count": 8},
        ]
        if full:  # final test 전용: ESD/랜치업 + 인터페이스
            items.insert(3, {
                "seq": 4, "stage": "interface", "name": "ESD (HBM 2kV)",
                "expected_duration_s": 0.08, "site_count": 2, "instrument": "ESD-HBM",
                "defect_coverage": [{"defect_class": "esd", "coverage_pct": 92.0}],
                "failure_mode_refs": ["FM-CS-ESD"]})
            items.insert(4, {
                "seq": 5, "stage": "interface", "name": "Latch-up (25mA)",
                "expected_duration_s": 0.10, "site_count": 2, "instrument": "LU-25MA",
                "defect_coverage": [{"defect_class": "latchup", "coverage_pct": 90.0}],
                "failure_mode_refs": ["FM-CS-LU"]})
            items[6]["seq"] = 7
            items[5]["seq"] = 6
        return items

    fs = asic_post(asic_client, "/api/v1/asic/test-flows", "seed-asic-r2-tf-ws", {
        "business_id": "ASIC-CS-TP-WS-1", "template_id": t,
        "program_revision": 1, "target": "wafer_sort", "cost_rate_per_site_hour": None,
        **_TP_R2_REV,
        "note": "wafer sort — cost rate 미확정(TBD)·오프셋 항목 요구사항 링크 포함",
        "items": flow_items(full=False),
    }, list_path=f"/api/v1/asic/templates/{t}/test-flows", match_bid="ASIC-CS-TP-WS-1")
    ff = asic_post(asic_client, "/api/v1/asic/test-flows", "seed-asic-r2-tf-ft", {
        "business_id": "ASIC-CS-TP-FT-1", "template_id": t,
        "program_revision": 1, "target": "final_test", "cost_rate_per_site_hour": 14500.0,
        **_TP_R2_REV,
        "note": "final test — site-hour 단가 14,500 KRW, wafer sort와 항목 계보 비교 대상",
        "items": flow_items(full=True),
    }, list_path=f"/api/v1/asic/templates/{t}/test-flows", match_bid="ASIC-CS-TP-FT-1")

    # SYNTHETIC wafer map: 24×24, 불량 다이 12개 고정 주입, site 3 편향
    rng = random.Random(20260915)
    rows = cols = 24
    bad_xy = [(3 + (i * 5) % 20, 4 + (i * 7) % 19) for i in range(12)]
    bins = []
    for y in range(rows):
        for x in range(cols):
            site = 1 + ((x // 6) + (y // 12)) % 4
            if (x, y) in bad_xy:
                b = 3 if site != 3 else 2  # site 3은 재시험(bin2)으로 탈출 1건 의도
                if (x, y) == bad_xy[4]:
                    b = 1  # underkill 1건 (SYNTHETIC, 공개)
            elif site == 3 and rng.random() < 0.06:
                b = 3  # site 3 오버킬 편향
            elif rng.random() < 0.05:
                b = 2  # 재시험
            else:
                b = 1
            bins.append({"x": x, "y": y, "bin": b, "site": site})
    wm = asic_post(temc_client, "/api/v1/asic/wafer-maps", "seed-asic-r2-wm-1", {
        "business_id": "ASIC-CS-WM-001", "template_id": t, "lot_ref": "LOT-CS-A1-01",
        "wafer_ref": "W03", "test_flow_id": fs["id"], "grid": {"rows": rows, "cols": cols},
        "bins": bins, "source_class": "SYNTHETIC",
        "ground_truth": {"bad_xy": [list(p) for p in bad_xy],
                         "note": "교육용 합성 fixture — 주입 불량 좌표 (공개)"},
        "note": "site 3 오버킬 편향 + underkill 1건 의도 주입 (SYNTHETIC)",
    }, list_path=f"/api/v1/asic/templates/{t}/wafer-maps", match_bid="ASIC-CS-WM-001")
    conf = (wm.get("analysis") or {}).get("confusion") or {}
    print(f"asic r2: wafer map yield={wm['analysis']['yield_pct']}% "
          f"retest={wm['analysis']['retest_rate_pct']}% "
          f"overkill={conf.get('overkill_count')} underkill={conf.get('escaped_underkill')}")

    # 한계값 변경 검토안 (적용은 인간 — seed에서는 proposed로 남긴다)
    ft_detail = next(
        f for f in client.get(f"/api/v1/asic/templates/{t}/test-flows").json()
        if f["id"] == ff["id"]
    )
    offset_item = next(it for it in ft_detail["items"] if it["name"] == "DC 파라미터 (오프셋)")
    asic_post(asic_client, f"/api/v1/asic/test-flows/{ff['id']}/limit-changes",
              "seed-asic-r2-lc-1", {
        "item_id": offset_item["id"],
        "new_limits": {"low": -20.0, "high": 20.0, "unit": "uV"},
        "rationale": "FMEDA 분석 결과 오프셋 가드밴드 축소 여지 — 커버리지 유지 확인 후 검토",
    })
    print("asic r2: test flows 2종 + wafer map + 오프셋 한계값 변경 검토안(proposed)")

    # ── EPIC H: 파트너 3종 + lot 여행 + 증적 + PCN(승인) + 품질조치(종결) ────
    fab = asic_post(client, "/api/v1/asic/partners", "seed-asic-r2-pt-fab", {
        "business_id": "PRT-F1-FAB", "name": "F1 Fab (교육용 가명)", "kind": "foundry",
        "approved_scope": {"processes": ["28nm"], "sites": ["Korea"]},
    }, list_path="/api/v1/asic/partners", match_bid="PRT-F1-FAB")
    osat = asic_post(client, "/api/v1/asic/partners", "seed-asic-r2-pt-osat", {
        "business_id": "PRT-OSAT-K1", "name": "OSAT-K1 (교육용 가명)", "kind": "osat",
        "approved_scope": {"packages": ["QFN-32"], "sites": ["Vietnam"]},
    }, list_path="/api/v1/asic/partners", match_bid="PRT-OSAT-K1")
    asic_post(client, "/api/v1/asic/partners", "seed-asic-r2-pt-sub", {
        "business_id": "PRT-SUBCON-X", "name": "Subcon-X (교육용 가명)", "kind": "subcon",
        "note": "conditional — lot 경로에 투입 전 승인 필요 (게이트 규칙 데모)",
    }, list_path="/api/v1/asic/partners", match_bid="PRT-SUBCON-X")
    client.post(f"/api/v1/asic/partners/{fab['id']}/approve", headers={"Idempotency-Key": "seed-asic-r2-pt-fab-ap"})
    osat_r = client.post(f"/api/v1/asic/partners/{osat['id']}/approve", headers={"Idempotency-Key": "seed-asic-r2-pt-osat-ap"})
    if osat_r.status_code not in (200, 409):
        osat_r.raise_for_status()

    lt = asic_post(temc_client, "/api/v1/asic/lot-travelers", "seed-asic-r2-lt-1", {
        "business_id": "ASIC-CS-LOT-A1-01", "template_id": t, "lot_ref": "LOT-CS-A1-01",
        "silicon_revision": "A1", "mask_rev": "MASK-A1", "package_rev": "PKG-A1",
        "parent_lot_refs": ["CURR-LOT-2609A"],
        "steps": [
            {"partner_business_id": "PRT-F1-FAB", "step": "wafer fab (28nm)", "result": "pass"},
            {"partner_business_id": "PRT-OSAT-K1", "step": "assembly (QFN-32)", "result": "pass"},
            {"partner_business_id": "PRT-OSAT-K1", "step": "final test", "result": "pass"},
        ],
        "note": "ECO A1 실리콘 첫 양산 lot — 계보 완결 (게이트 청결 유지)",
    }, list_path=f"/api/v1/asic/templates/{t}/lot-travelers", match_bid="ASIC-CS-LOT-A1-01")

    report_hash = hashlib.sha256(b"OSAT-K1 final test report LOT-CS-A1-01 (synthetic)").hexdigest()
    asic_post(temc_client, "/api/v1/asic/partner-artifacts", "seed-asic-r2-pa-1", {
        "business_id": "ASIC-CS-PA-001", "partner_business_id": "PRT-OSAT-K1",
        "template_id": t, "lot_traveler_id": lt["id"], "kind": "test_report",
        "file_hash": report_hash,
        "meta": {"pages": 7, "site_yields": {"1": 0.996, "2": 0.995, "3": 0.958}},
        "note": "OSAT 최종 시험 리포트 (합성 치환본)",
    }, list_path=f"/api/v1/asic/templates/{t}/partner-artifacts", match_bid="ASIC-CS-PA-001")

    pcn = asic_post(temc_client, "/api/v1/asic/partner-changes", "seed-asic-r2-pcn-1", {
        "business_id": "ASIC-CS-PCN-001", "partner_business_id": "PRT-OSAT-K1",
        "kind": "site_transfer",
        "description": "final test 라인 일부를 Vietnam 제2사이트로 이전 — 장비 동일 모델 이관",
        "affected_template_ids": [t],
        "note": "승인 절차 데모 — seed에서는 즉시 승인하여 게이트를 청결하게 유지",
    }, list_path=f"/api/v1/asic/templates/{t}/partner-changes", match_bid="ASIC-CS-PCN-001")
    asic_post(client, f"/api/v1/asic/partner-changes/{pcn['id']}/review", "seed-asic-r2-pcn-review", {
        "decision": "approved",
        "note": "동일 장비 이관 + CPK 데이터 동등 확인 (2026-09-15 품질 리뷰)",
    }, list_path=f"/api/v1/asic/templates/{t}/partner-changes", match_bid="ASIC-CS-PCN-001")

    qa = asic_post(client, "/api/v1/asic/quality-actions", "seed-asic-r2-qa-1", {
        "business_id": "ASIC-CS-QA-001", "template_id": t, "lot_traveler_id": lt["id"],
        "lot_ref": "LOT-CS-A1-01", "action": "8d",
        "reason": "site 3 오버킬 편향 (wafer map 분석) — 프로브 카드 접촉 저항 의심",
        "fa_case_id": None,
        "note": "프로브 카드 교체 + 재측정으로 종결된 사례 (데모)",
    }, list_path=f"/api/v1/asic/templates/{t}/quality-actions", match_bid="ASIC-CS-QA-001")
    qa_close = client.post(f"/api/v1/asic/quality-actions/{qa['id']}/close",
                           json={"note": "프로브 카드 교체 후 site 3 수율 정상 복원 확인"},
                           headers={"Idempotency-Key": "seed-asic-r2-qa-close"})
    if qa_close.status_code not in (200, 409):
        qa_close.raise_for_status()

    # ── 템플릿 4종 검증 팩 (P1-07): 나머지 3템플릿 라이트 팩 ────────────────
    _seed_template_pack(client, asic_client, "cap_afe", "Capacitive Sensing ASIC",
                        [("AFE", 12.5), ("ADC", 8.0)])
    _seed_template_pack(client, asic_client, "motor_ripple", "Motor Ripple Counter",
                        [("RIPPLE", 22.0), ("LPF", 5.5)])
    _seed_template_pack(client, asic_client, "env_sensor", "Environmental Sensor ASIC",
                        [("HUM", 9.0), ("TEMP", 4.0)])

    # ── 최종 게이트: R1과 동일한 두 블로커만 ────────────────────────────────
    report = client.get(f"/api/v1/asic/gate-report/{t}").json()
    codes = sorted(b["code"] for b in report["blockers"])
    expected = ["CALIBRATION_EXPIRED", "MOCK_RESULT_PRESENT"]
    if codes != expected:
        print(f"WARNING: R2 gate blockers = {codes} (expected {expected})", file=sys.stderr)
    print(
        "asic r2: 전류 센서 R2 시드 완료 — tool runs×3(real 2+mock 1), options×3+TS 결정, "
        "test flows×2, wafer map(overkill/underkill 공개), lot 여행+증적+PCN 승인+QA 종결, "
        f"gate={codes} readiness={report['readiness']}"
    )


def _seed_template_pack(client: httpx.Client, asic_client: httpx.Client,
                        template_id: str, label: str, blocks_spec: list) -> None:
    """P1-07 검증 팩 (라이트): 신호체인 r1 + Corner MC + 옵션 2종 + Trade Study
    + 테스트 플로우 쌍 — 템플릿별 작업센터가 빈 패널 없이 뜨는 최소 증적.
    전류 센서(§17 PoC)는 seed_asic_twin/seed_asic_r2가 더 풍부한 팩을 심는다."""
    t = template_id
    blocks = [
        {"key": "sensor", "kind": "sensor", "label": f"{label} 센서 프론트엔드",
         "params": {"nominal": 100.0},
         "error_budget": {"offset": 0.1, "noise": 0.2, "drift": 0.01},
         "requirement_ids": [f"REQ-{t.upper()}-SENS"]},
    ]
    for key, gain in blocks_spec:
        blocks.append({
            "key": key.lower(), "kind": "analog", "label": f"{key} 블록 (G={gain})",
            "params": {"gain": gain},
            "error_budget": {"offset": 0.05, "gain_error": 0.1, "noise": 0.08},
        })
    asic_post(client, "/api/v1/asic/signal-chains", f"seed-tp-{t}-chain-1", {
        "business_id": f"ASIC-{t.upper()}-CHAIN-R1", "template_id": t, "blocks": blocks,
        "note": "P1-07 검증 팩 — 템플릿 기본 신호체인 (SYNTHETIC)",
    }, list_path=f"/api/v1/asic/templates/{t}/signal-chains", match_bid=f"ASIC-{t.upper()}-CHAIN-R1")
    chain = client.get(f"/api/v1/asic/templates/{t}/signal-chains").json()[0]
    asic_post(client, "/api/v1/asic/corner-studies", f"seed-tp-{t}-mc-1", {
        "business_id": f"ASIC-{t.upper()}-MC-001", "signal_chain_id": chain["id"],
        "kind": "monte_carlo", "n_draws": 1000,
        "spec": [{"output": "sensitivity", "nominal": 100.0, "min": 98.0, "max": 102.0,
                  "unit": "mA/A"}],
    }, list_path=f"/api/v1/asic/templates/{t}/corner-studies", match_bid=f"ASIC-{t.upper()}-MC-001")

    def _opt(bid: str, foundry: str, node: str, moq: int, tech: int, wafer_cost: float,
             die_yield: float, mask: int) -> dict:
        return asic_post(asic_client, "/api/v1/asic/manufacturing-options",
                         f"seed-tp-{t}-{bid.lower()}", {
            "business_id": f"ASIC-{t.upper()}-{bid}", "template_id": t,
            "foundry": foundry, "node": node, "voltage_option": "3.3V",
            "temperature_grade": "AEC-Q100 G1", "package": "QFN-24", "moq": moq,
            "tech_score": tech,
            "nre": {
                "design": {"amount": 400_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
                "ip": {"amount": 250_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
                "mask": {"amount": mask, "currency": "KRW", "basis_date": "2026-09-01"},
                "pkg_tooling": {"amount": 120_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
                "test_dev": {"amount": 90_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
                "reliability": {"amount": 70_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
            },
            "unit_cost": {
                "wafer": {"base": wafer_cost, "best": round(wafer_cost * 0.95, 1),
                          "worst": round(wafer_cost * 1.1, 1), "unit": "KRW",
                          "dies_per_wafer": 5000, "basis_date": "2026-09-01"},
                "assembly": {"base": 190.0, "best": 180.0, "worst": 215.0, "unit": "KRW",
                             "basis_date": "2026-09-01"},
                "final_test": {"base": 75.0, "best": 71.0, "worst": 85.0, "unit": "KRW",
                               "basis_date": "2026-09-01"},
                "logistics": {"base": 35.0, "best": 32.0, "worst": 45.0, "unit": "KRW",
                              "basis_date": "2026-09-01"},
                "die_yield": {"base": die_yield, "basis_date": "2026-09-01"},
                "scrap": {"base": 0.008, "basis_date": "2026-09-01"},
            },
            "schedule": [
                {"phase": "design", "weeks_base": 12, "weeks_best": 10, "weeks_worst": 16},
                {"phase": "tapeout", "weeks_base": 9, "weeks_best": 8, "weeks_worst": 12},
                {"phase": "wafer", "weeks_base": 11, "weeks_best": 10, "weeks_worst": 14},
                {"phase": "qualification", "weeks_base": 13, "weeks_best": 11, "weeks_worst": 17},
            ],
            "note": "P1-07 검증 팩 옵션 (교육용 가명·합성 단가)",
        }, list_path=f"/api/v1/asic/templates/{t}/manufacturing-options",
            match_bid=f"ASIC-{t.upper()}-{bid}")

    o1 = _opt("OPT-1", "F1 Fab (교육용 가명)", "40nm", 4000, 4, 700_000.0, 0.80, 500_000_000)
    o2 = _opt("OPT-2", "F3 Fab (교육용 가명)", "90nm", 2000, 3, 380_000.0, 0.74, 210_000_000)
    asic_post(asic_client, "/api/v1/asic/trade-studies", f"seed-tp-{t}-ts-1", {
        "business_id": f"ASIC-{t.upper()}-TS-001", "template_id": t,
        "title": f"{label} 공정 선택 검토 (P1-07 팩)",
        "option_ids": [o1["id"], o2["id"]],
        "weights": {"cost": 0.4, "schedule": 0.2, "technology": 0.2, "supply": 0.2},
        "annual_volume": 1_000_000,
        "note": "P1-07 검증 팩 — 의사결정은 열어둔다 (검토 워크플로 데모)",
    }, list_path=f"/api/v1/asic/templates/{t}/trade-studies", match_bid=f"ASIC-{t.upper()}-TS-001")

    for target, cost in (("wafer_sort", None), ("final_test", 13800.0)):
        bid = f"ASIC-{t.upper()}-TP-{'WS' if target == 'wafer_sort' else 'FT'}-1"
        asic_post(asic_client, "/api/v1/asic/test-flows", f"seed-tp-{t}-{target}", {
            "business_id": bid, "template_id": t, "program_revision": 1, "target": target,
            "cost_rate_per_site_hour": cost, **_TP_R2_REV,
            "note": "P1-07 검증 팩 테스트 플로우 (합성 항목)",
            "items": [
                {"seq": 1, "stage": "contact", "name": "Contact 전도성 확인",
                 "limits": {"high": 5.0, "unit": "ohm"}, "expected_duration_s": 0.05,
                 "site_count": 4,
                 "defect_coverage": [{"defect_class": "open", "coverage_pct": 95.0},
                                     {"defect_class": "short", "coverage_pct": 93.0}]},
                {"seq": 2, "stage": "dc", "name": "DC 파라미터",
                 "limits": {"low": -25.0, "high": 25.0, "unit": "uV"},
                 "expected_duration_s": 0.12, "site_count": 4,
                 "defect_coverage": [{"defect_class": "parametric", "coverage_pct": 88.0}],
                 "requirement_ids": [f"REQ-{t.upper()}-SENS"]},
                {"seq": 3, "stage": "final_bin", "name": "최종 빈 분류",
                 "expected_duration_s": 0.02, "site_count": 4},
            ],
        }, list_path=f"/api/v1/asic/templates/{t}/test-flows", match_bid=bid)


if __name__ == "__main__":
    main()
