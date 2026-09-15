# ALPS ALPINE Engineering Twin Workbench — System Documentation

**Version v1.0 · as of 2026-09-15 · Complete feature inventory**

This reference document inventories every feature, screen and characteristic currently implemented in the workbench, the differentiators versus existing solutions, the applicability within Alps Alpine, and the roadmap. It can be read at any time in the in-app **System Docs tab**, and downloaded as an `.md` file for meeting attachments, reporting, and onboarding material.

> **Honesty principle (the design philosophy of this system)** — every educational estimate on screen carries a △ educational estimate badge, every synthetic dataset a ◇ synthetic fixture badge. In-browser mock run results can never become sign-off evidence, and the gate JSON always shows the `MOCK_RESULT_PRESENT` blocker. Approved evidence is never overwritten — only new revisions are created. Status is conveyed by icon + wording, never color alone. The feature descriptions in this document follow the same principle.

---

## 1. System Overview

The **ALPS ALPINE Engineering Twin Workbench** is an engineering digital-twin platform that manages the entire product-engineering cycle — requirements definition → 3D design review → simulation → measurement correlation → gate review → production quality — in **a single web workbench**. On top of that come (1) the **EDA Training module** for learning IC design and circuit test, (2) the **ASIC 9-stage work center** that runs Alps Alpine's nine-stage ASIC development around gates and evidence, and (3) the **AirInput Field Twin** that analyzes a capacitive 3D sensing field — mechanics, circuits, process and quality on one screen.

```
Requirements (S03) → 3D Design Review (S04) → Dev/Test Board (S05) → System Model (E02)
     ↕                        ↕                        ↕                    ↕
  Process Twin (TS03–05) · AirInput Field Twin · EDA Training · ASIC 9-stage work center
     ↘ Result Compare (S08) · SWEEP variant compare · Test Correlation (S09) · Gate (S10) ↙
```

---

## 2. System Architecture

| Layer | Technology | Notes |
|---|---|---|
| Frontend | React 19 + TypeScript + Vite | SPA; product/variant state in a zustand store |
| 3D rendering | react-three-fiber 9 + three 0.186 (WebGL) | **Web-native 3D — no external runtime such as Unity required** |
| i18n | i18next (Korean·English·Japanese) | type-safe 3-locale sync |
| Auth | Keycloak (OpenID Connect) | role-based (e.g. demo.architect — Approver), logout/SSO |
| Backend | FastAPI (Python) | requirements · components · simulation runs · gates REST API |
| Workflow | Temporal | long-running execution and retries for the simulation pipeline |
| DB | PostgreSQL | product · variant · run · evidence metadata |

All 3D scenes (part geometry, wave propagation and waveforms, package cross-section, process flow) render in the browser with no server-side installation, and the simulation training runners (lint / simulation / synthesis / P&R) produce reproducible results from deterministic seeds (mulberry32).

---

## 3. Complete Screen & Feature List

### 3.1 Unified navigation bar (shared across all screens)

- **One-row hierarchy**: `PRODUCT ▸ VARIANT` selects → `VIEWS` (product-twin views) → `STANDALONE MODULES` → language switch.
- Every control shares the same height, rounding, font and micro-caption — one control system.
- Entering a standalone module (EDA training · ASIC center · system docs) dims and disables the product/variant selects and shows the "ⓘ standalone modules ignore the product/variant selection" hint — **the UI never lies**.
- Side panels and the bottom compare/correlation/gate frames collapse into **focus mode**, giving standalone modules the full width.
- The onboarding guide ("Where you are") walks through progress as a checklist.

### 3.2 Requirements & Trace (S03)

- Requirement list: safety grade (ASIL/QM), status (Test/Draft), priority, linked verification items (VER).
- Requirement ↔ component trace: click a requirement → the corresponding part highlights in the 3D view (bidirectional).
- Req→Ver coverage %, unresolved conflict count.

### 3.3 3D Design Review (S04)

- CAD-concept 3D viewer: click a part ↔ reverse-lookup its requirements.
- **Exploded view** slider, **X-ray (body opacity)** slider.
- Assembly-simulation playback: a cycle slider plays the press action and vehicle-vibration frames.
- Stress hot-spot display (explicitly labeled educational visualization — not life prediction).

### 3.4 Dev/Test Board (S05)

- Virtual test bench: push-switch / vehicle-vibration inputs → measured (synthetic) data channels.
- Side-by-side comparison with prediction-model results (Result Compare, S08).

### 3.5 System Model (E02)

- System block-model view: input → processing → output chain and signal flow.
- Prediction-model (analytical-mech-model etc.) parameters and result metrics.

### 3.6 Process Twin (TS03–05)

- Manufacturing process twin: process steps, monitoring charts (follows the §5.1 legend rules).
- **3D fab-flow view**: wafer → front-end → packaging flow visualized in 3D.

### 3.7 AirInput Field Twin (3D) — capacitive sensing module

- **3D models of finger, glove, surface, electrode and ground plate** plus an electric-field slice heatmap.
- **Two-tier analysis**: finite-difference Laplace solver (FD, reference solution) ↔ RBF surrogate (real-time client-side evaluation, OOD region flagging).
- Per-electrode capacitance (ΔC) curves, sensing-volume / dead-zone / false-detection heat volumes.
- **ASIC ↔ algorithm decision chain**: v1 fixed-threshold vs v2 baseline-hysteresis (IDLE/NEAR/TOUCH, debounce) comparison.
- Robot-scan prediction-vs-measurement verification, GOLD-01..06 scenario table, Surrogate/Solver tier panel.

### 3.8 EDA Training (IC Design & Circuit Test)

- Lint → circuit simulation (waveform viewer) → synthesis → Place&Route 3D: a hands-on EDA flow.
- Missions: 4-bit counter, 4-bit ALU, synchronous FIFO, UART TX, **32-bit RISC** (544 FF).
- Synthesis KPIs (FF/LUT counts), 3D layout (layered die, exploded view), educational waveforms.

### 3.9 ASIC Program — 9-stage work center (directive v1.0 §2 mapping)

| Stage | Screen content | Key gate |
|---|---|---|
| ① Requirement Review | requirement matrix; AI proposal creates draft links and verification items | REQ_TRACE_100 |
| ② Feasibility & Architecture | approve process/package options (OPT), risk and lead time | OPT_CONFIRMED |
| ③ Program Baseline | baseline e-signature | BASELINE_SIGNED |
| ④ ASIC Design | run lint / simulation / synthesis / P&R (reuses the EDA runners) | DESIGN_COMPLETE |
| ⑤ Engineering Sample | **package 3D twin** (die, bond wires, mold, solder, MEMS) + measurement-vs-prediction correlation (R², bias/MAE/RMSE) | CORRELATION_OK |
| ⑥ ECO & Test Program | change-impact analysis → ECO close → **mask/test-program revision bump + forced evidence re-approval** (§14.3) | ECO_CLOSED |
| ⑦ CS & Qualification | AEC-Q100 per-grade temperature table (`alps-asic-v1.0` policy), evidence/CAPA/waiver | QUAL_PASS |
| ⑧ Release & Evidence | evidence e-signature, readiness ladder (education_only→released), gate JSON | EVIDENCE_APPROVALS |
| ⑨ Production | lot SPC · Pareto, MRB disposition of the failing lot, shipment | LOT_RELEASE |

- 4 product templates (cap-touch AFE / current sensor / motor ripple / environmental sensor) × distinct gate states, missions and correlation parameters.
- Stage cockpit: current stage n/9, next gate, coverage, qualification rate and R² at a glance.
- The gate JSON honestly reports blockers (`MOCK_RESULT_PRESENT`, `EVIDENCE_APPROVALS`, …) and `decision_required` — **a release is never rubber-stamped**.

### 3.10 Result compare · correlation · gate (bottom frame)

- **SPICE Resistance Sweep — Variant Compare (S08)**: overlay-compare two or more variants on identical axes and units (§12.2).
- **Test & Correlation (S09)**: prediction vs measurement correlation table.
- **Gate (S10)**: gate submission / review status.
- **Assistant**: LLM assistant panel (queries, screen guidance).

### 3.11 System Docs tab (this document)

- This document rendered in-app + a `.md` download button (reporting / onboarding attachment).
- A standalone reference menu, independent of the product/variant context.

---

## 4. Features and Advantages

| Feature | Description | Advantage |
|---|---|---|
| Full-cycle single workbench | requirements → design → verification → production evidence in one context | eliminates tool-to-tool copying and manual reports; raises traceability |
| Honest data layer | educational-estimate / synthetic-fixture badges, mock results blocked from sign-off, immutable evidence (new revisions only) | learning/demo data can never contaminate real decisions — the basis of audit readiness |
| Web-native 3D | WebGL (r3f) based, no install, no plugins | anyone reviews instantly in a browser; minimal deployment cost |
| Variant & product scale | product × variant template structure, same-axis comparison | lower derived-model management cost |
| Deterministic replay | seeded runners, state-machine gates | reproducible training and regression testing |
| 3-locale UI | ko/en/ja fully synchronized | Japan HQ – Korea – overseas sites working simultaneously |
| SSO & role approval | Keycloak, e-signature approvals (approver recorded) | clear audit trail and accountability |

---

## 5. Differentiation vs Existing Solutions

| Compared against | Limits of the existing approach | What this system does differently |
|---|---|---|
| Traditional PLM (document-centric) | 3D, simulation and decisions scattered per tool; the goal is document registration | **live twin + evidence chain integrated** — the screen you look at is the evidence |
| Standalone simulators (SPICE/FEM tools) | results exist as files outside the workbench, disconnected from requirements | run results connect instantly to requirements, gates and correlation panels |
| Game-engine digital twins (Unity etc.) | runtime install · licenses · web deployment burden, IT negotiation required | 3D implemented with web standards alone — **no Unity dependency** (directive requirement met) |
| Excel/email ASIC program management | stages, gates, evidence and ECO state live in people's heads | the 9-stage work center enforces gates, blockers, evidence revisions and ECOs on one screen |
| Internal training (documents + tests) | no hands-on environment, risk of mishandling real equipment | training modules (EDA · ASIC) **physically separated from real sign-off** |
| Generic BI dashboards | can only display status, cannot drive action | every metric leads directly to the next action (approve · MRB · ECO) in a workflow |

The core differentiator is that **honesty is built into the system** — the path from educational/demo results to a real release decision is structurally blocked (the immutable `MOCK_RESULT_PRESENT` blocker, unreachable readiness levels marked ✕, the immutable-approved-evidence rule), so a demonstration environment and real gates can coexist inside the same tool.

---

## 6. Applicability within Alps Alpine

1. **1:1 product-portfolio templates** — tactile switches, proximity/air-input sensors, current sensors, motor ripple, environmental sensors and the cap-touch AFE ASIC already exist as templates. New products start by cloning a template.
2. **One screen across departments** — sales (requirements), design (3D · EDA), quality (gates · MRB · SPC) and production (process twin) work on the same data, each in their own view.
3. **ASIC outsource / in-house development management** — the 9-stage work center tracks stage-by-stage evidence with customers and partner foundries (spec baseline, ES correlation, ECO revisions, AEC-Q100 qualification).
4. **Onboarding junior / mid-career engineers** — EDA training (combinational · sequential · protocol · RISC missions) and the ASIC 9-stage simulation provide safe hands-on practice that never touches real development data.
5. **Customer review material** — demo exploded views, waveforms and correlation charts instantly in a browser; information grading managed with the confidentiality classification display.
6. **Training-to-practice transition** — the runner and gate concepts learned in the training modules use the same UI as the production work center, minimizing relearning cost.

---

## 7. Roadmap

| Direction | Content | Priority |
|---|---|---|
| Real-data integration | educational geometry → real CAD; synthetic measurements → real instruments / data loggers | high |
| Real EDA integration | open-source toolchain (Yosys/nextpnr etc.) or commercial-tool wrappers, gradually replacing the mock runners | high |
| Connectors | PLM · requirements management (e.g. JAMA family) · MES/QMS integration, §13.2 AI anomaly alerts (hold remains in the external QMS) | medium |
| Surrogate advancement | AirInput RBF → deep surrogates, DOE automation, refined OOD handling | medium |
| Collaboration | comments · screenshot sharing, review sessions (screen sync), approval-routing rule engine | medium |
| Deployment & accessibility | mobile/tablet optimization, offline review packages (evidence + 3D) export, WCAG accessibility | medium |
| Document automation | multilingual auto-generation of this system document, evidence-based report extraction | low |

> Current constraints (stated honestly): the 3D geometry, measurements and EDA runners are educational synthetics, and simulation results are not sign-off grade. Only once the real-data integration items above are completed do the upper readiness-ladder levels (released) become reachable — that is design, not a bug.

---

## 8. Technology Stack Summary (for developers)

- **Frontend**: React 19 + TS + Vite · zustand · react-three-fiber 9/three 0.186 · i18next · Keycloak JS adapter
- **Backend**: FastAPI · PostgreSQL · Temporal workflows
- **3D scene contract**: `EdaScene` (mode: synthesis/layout/process/package) + the `EdaBox` primitive — EDA training, the ASIC package twin and the process flow all reuse the same viewer (`Eda3DViewer`)
- **Determinism**: `strSeed` + mulberry32; same seed → same waveform/KPI
- **Document**: this file `apps/web/src/assets/systemDoc.en.md` (bundled at build time, `?raw` import)
