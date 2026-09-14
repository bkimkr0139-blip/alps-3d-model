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
import os
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
) -> dict:
    run = post(
        client,
        "/api/v1/simulation-runs",
        idem_key=f"seed-run-{business_id}",
        body={
            "business_id": business_id,
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
            return run
        time.sleep(0.5)
    raise TimeoutError(f"simulation run {business_id} did not finish within {timeout_s}s")


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
AIRINPUT_COMPONENTS = [
    {"suffix": "CMP-ELECTRODE", "name": "Capacitive Electrode PCB"},
    {"suffix": "CMP-COVER", "name": "Cover Lens"},
]

# Electrode Layout A/B = the spec's two geometry variants (§1.2), expressed
# as electrode_area_mm2/cover parameters on the proximity_capacitance model.
# step_fixture is genuinely per-variant (unlike the other three products,
# which share one fixture between A/B) — see generate_airinput_step.py: the
# electrode shape (solid pad vs. split-ring) and cover-lens thickness are
# real geometric differences, not just simulation parameters.
AIRINPUT_VARIANTS = [
    {
        "business_id": "VAR-AIR-A",
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
    for comp in AIRINPUT_COMPONENTS:
        business_id = f"{variant_business_id}-{comp['suffix']}"
        component = post(
            client,
            "/api/v1/components",
            idem_key=f"seed-{business_id}",
            body={"business_id": business_id, "variant_id": variant_id, "name": comp["name"]},
        )
        comp_ids.append(component["id"])

    for req_id, req in zip(req_ids, AIRINPUT_REQUIREMENTS):
        for comp_id, comp in zip(comp_ids, AIRINPUT_COMPONENTS):
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


def main() -> None:
    token = get_token("demo.architect", "demo1234")
    test_token = get_token("demo.mech_engineer", "demo1234")
    approver_token = get_token("demo.approver", "demo1234")
    with (
        httpx.Client(base_url=API_URL, headers={"Authorization": f"Bearer {token}"}) as client,
        httpx.Client(base_url=API_URL, headers={"Authorization": f"Bearer {test_token}"}) as test_client,
        httpx.Client(base_url=API_URL, headers={"Authorization": f"Bearer {approver_token}"}) as approver_client,
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


if __name__ == "__main__":
    main()
