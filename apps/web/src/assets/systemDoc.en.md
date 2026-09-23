# ALPS ALPINE Engineering Twin Workbench — System Documentation

**Version v1.3 · as of 2026-09-23 · Complete feature inventory**

This reference document inventories every feature, screen and characteristic currently implemented in the workbench, the differentiators versus existing solutions, the applicability within Alps Alpine, and the roadmap. It can be read in the in-app **System Docs tab** (visible when signed in as the admin account), and downloaded as an `.md` file for meeting attachments, reporting, and onboarding material.

> **Honesty principle (the design philosophy of this system)** — every educational estimate on screen carries a △ educational estimate badge, every synthetic dataset a ◇ synthetic fixture badge. In-browser mock run results can never become sign-off evidence, and the gate JSON always shows the `MOCK_RESULT_PRESENT` blocker. Approved evidence is never overwritten — only new revisions are created. Status is conveyed by icon + wording, never color alone. The feature descriptions in this document follow the same principle.

> **v1.3 (2026-09-23)** — the System Docs tab became admin-account-only: regardless of the `platform_admin` role, it appears in the navigation bar only for sessions signed in as the `admin` user (demo.admin and other admin-persona accounts are excluded).
>
> **v1.1 (2026-09-17) highlights** — premium instrument UI (design tokens, embossed shell, premium chart themes), an app-wide dark/light theme toggle (instrument 3D and scope glass stay dark; both modes pass the WCAG contrast audit), the language switcher pinned to the header top-right, the 3D cockpit landing (model tab), the 3D production-line twin (FactoryViewer), 3D review tools (section / measure / annotate), part-ID selection sync across panels, ASIC package-family 3D models with 1:1 bond-map fanout and realistic Au wires, product-chipset-flavored EDA missions and 3D scenes, and a dedicated AirInput test bench board (puck-module DUT).

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

- **One-row hierarchy**: `PRODUCT ▸ VARIANT` selects → `VIEWS` (product-twin views) → `STANDALONE MODULES`. The language switcher and the dark/light theme toggle are **pinned to the header top-right** — reachable from every screen.
- Every control shares the same height, rounding, font and micro-caption — one control system.
- **Premium instrument design**: `--alps-*` design tokens, an embossed-button metallic-panel shell and premium ECharts/SVG/canvas chart themes applied consistently across every screen. An app-wide **dark/light theme toggle** (instrument 3D and scope glass stay dark), with both modes passing the WCAG contrast audit.
- Entering a standalone module (EDA training · ASIC center · system docs) dims and disables the product/variant selects and shows the "ⓘ standalone modules ignore the product/variant selection" hint — **the UI never lies**.
- Side panels and the bottom compare/correlation/gate frames collapse into **focus mode**, giving standalone modules the full width.
- The onboarding guide ("Where you are") walks through progress as a checklist.

### 3.2 Requirements & Trace (S03)

- Requirement list: safety grade (ASIL/QM), status (Test/Draft), priority, linked verification items (VER).
- Requirement ↔ component trace: click a requirement → the corresponding part highlights in the 3D view (bidirectional).
- Req→Ver coverage %, unresolved conflict count.

### 3.3 3D Design Review (S04)

- CAD-concept 3D viewer: click a part ↔ reverse-lookup its requirements.
- **3D cockpit landing**: on the model tab the 3D view takes the full width and a glass HUD strip (product · variant | gate readiness GateDot | latest simulation runs | requirement↔part link chip) floats above the canvas; the requirement/simulation panels retreat into collapsible glass drawers.
- **Review toolbar (FR-03)**: section clipping (axis · offset), 2-point distance measurement (mm, STEP units), annotation pins (◈ client-local). With the toolbar off, the default experience stays clean.
- **Part-ID sync across panels (directive L187)**: the 3D view, circuit-verification rows and system-model nodes all highlight the same part ID together (both directions).
- **Exploded view** slider, **X-ray (body opacity)** slider.
- Assembly-simulation playback: a cycle slider plays the press action and vehicle-vibration frames.
- Stress hot-spot display (explicitly labeled educational visualization — not life prediction).

### 3.4 Dev/Test Board (S05)

- **Per-family DUT modules**: the bench PCB carries a family-specific DUT — tactile (push switch), encoder (slotted disk), MEMS (pressure gauge), AirInput (electrode puck module).
- 2-channel oscilloscope (real signal-chain state machine, RUN/STOP · bezel LEDs) with the F–S curve overlay cursor in sync.
- **AirInput puck board**: housing, PCB, electrode (variant A round pad / B split ring), cover glass and castellated terminals are mounted, and a fingertip stimulus (near/away) drives scope CH1 sense level, the CH2 touch hysteresis comparator and the board LED.
- **Circuit Test table**: compared side-by-side with real SPICE run results (source chip: business_id · tool_version) — Result Compare (S08).
- The bench DUT gets an emissive highlight only when it matches the selected part kind; on mismatch the HUD shows the honest "bench DUT = whole product" chip.

### 3.5 System Model (E02)

- System block-model view: input → processing → output chain and signal flow.
- Prediction-model (analytical-mech-model etc.) parameters and result metrics.

### 3.6 Process Twin (TS03–05)

- Manufacturing process twin: process steps, monitoring charts (follows the §5.1 legend rules).
- **3D fab-flow view**: wafer → front-end → packaging flow visualized in 3D.
- **3D production-line twin (FactoryViewer)**: a 3D line of stations laid out in process order (seq_no) glows with control-chart status colors (in-control / attention / violation / idle); clicking a station opens a drawer with its control chart, cavity drift and lot details. Conveyor dots carry lot disposition colors.
- Photoreal-style equipment silhouettes (annular lamp · press · molding machine · robot cell) plus a status-legend / OOW-counter / DOE-scroll HUD.

### 3.7 AirInput Field Twin (3D) — capacitive sensing module

- **3D models of finger, glove, surface, electrode and ground plate** plus an electric-field slice heatmap.
- **Two-tier analysis**: finite-difference Laplace solver (FD, reference solution) ↔ RBF surrogate (real-time client-side evaluation, OOD region flagging).
- Per-electrode capacitance (ΔC) curves, sensing-volume / dead-zone / false-detection heat volumes.
- **ASIC ↔ algorithm decision chain**: v1 fixed-threshold vs v2 baseline-hysteresis (IDLE/NEAR/TOUCH, debounce) comparison.
- Robot-scan prediction-vs-measurement verification, GOLD-01..06 scenario table, Surrogate/Solver tier panel.
- **Variant-following electrode geometry**: variant A (round pad) / B (split-ring) electrode shapes match across the solver, CAD, viewer and the test-bench puck at the same electrode center — no per-tab model mismatch.

### 3.8 EDA Training (IC Design & Circuit Test)

- Lint → circuit simulation (waveform viewer) → synthesis → Place&Route 3D: a hands-on EDA flow.
- Five missions flavored as Alps product chipsets: tact debounce counter, touch ALU, AFE sample FIFO, sensor UART TX and the **AFE SoC 32-bit RISC** (544 FF) — `silProfileOf` assigns a chipset profile per product template.
- Synthesis KPIs (FF/LUT counts), 3D layout (layered die, exploded view), educational waveforms.
- **Three 3D scene types (process / synthesis / layout)**: the synthesis scene is rendered photoreal-style down to standard-cell rows, M1 rails, Cu/Al wiring, Au vias and a seal ring.

### 3.9 ASIC Program — 9-stage work center (directive v1.0 §2 mapping)

| Stage | Screen content | Key gate |
|---|---|---|
| ① Requirement Review | requirement matrix; AI proposal creates draft links and verification items | REQ_TRACE_100 |
| ② Feasibility & Architecture | approve process/package options (OPT), risk and lead time | OPT_CONFIRMED |
| ③ Program Baseline | baseline e-signature | BASELINE_SIGNED |
| ④ ASIC Design | run lint / simulation / synthesis / P&R (reuses the EDA runners) | DESIGN_COMPLETE |
| ⑤ Engineering Sample | **package 3D twin** — package-family models (QFN/WLCSP/LGA/SOIC/LQFP) parsed from the template options, 1:1 bond-map fanout, **Au bond wires** (ball/stitch bonds → silver-plated fingers), sensor stack / cavity integration, explode anchors and a mold-off view + measurement-vs-prediction correlation (R², bias/MAE/RMSE) | CORRELATION_OK |
| ⑥ ECO & Test Program | change-impact analysis → ECO close → **mask/test-program revision bump + forced evidence re-approval** (§14.3) | ECO_CLOSED |
| ⑦ CS & Qualification | AEC-Q100 per-grade temperature table (`alps-asic-v1.0` policy), evidence/CAPA/waiver | QUAL_PASS |
| ⑧ Release & Evidence | evidence e-signature, readiness ladder (education_only→released), gate JSON | EVIDENCE_APPROVALS |
| ⑨ Production | lot SPC · Pareto, MRB disposition of the failing lot, shipment | LOT_RELEASE |

- 4 product templates (cap-touch AFE / current sensor / motor ripple / environmental sensor) × distinct gate states, missions and correlation parameters.
- Stage cockpit: current stage n/9, next gate, coverage, qualification rate and R² at a glance.
- **Equipment rack strip**: run-status LEDs + a calibration countdown bar (calibration_expires_at) + findings chips above the equipment-runs panel.
- The gate JSON honestly reports blockers (`MOCK_RESULT_PRESENT`, `EVIDENCE_APPROVALS`, …) and `decision_required` — **a release is never rubber-stamped**.

**v1.1 enhancement (backend-connected — spec v1.1 §4/§7/§8, current-sensor ASIC PoC)**

- **Signal-chain revisions (EPIC A)**: r1→r2 promotion creates a NEW revision and supersedes the old one (immutability rule); per-block error budgets and content_hash shown in stages ②③.
- **Corner/MC analysis (EPIC A)**: seeded error-budget Monte-Carlo → P50/P95/P99, violation rate and the **real 24-bin sample histogram**; a corner temperature outside the calibrated range raises a MODEL OOD badge; same seed = identical result (reproducibility §12).
- **Equipment measurement import (EPIC E)**: raw tester CSV bytes are promoted to a sha256 artifact BEFORE parsing. **The same file can never become two runs** (409). Partial files, time reversals and duplicate blocks are recorded as findings (no silent fixes, §7). Calibration expiry is stored as data and turns into a gate blocker.
- **Qualification matrix + closed loop (EPIC F·G)**: AEC-Q100 verdicts read the latest row per group. A failed row is dispositioned through an FA case — RCA approval is **a human-dedicated role** and refuses (422) without observed facts + check evidence. ECO close refuses (412) without regression evidence + a verification measurement run; closing moves the FA case to verified, closing the loop.
- **Functional-safety trace**: SG→FSR→TSR→HW tree + FMEDA (distribution, DC, FIT, source hash) + fault injection (expected/observed) rendered in stage ⑦.
- **Gate policy `alps-asic-v1.1`**: new blockers `CALIBRATION_EXPIRED`, `MODEL_OOD`, `MIXED_REVISION_EVIDENCE`, `QUAL_FAILURE_OPEN`, `WAIVER_EXPIRED` plus the unconditional `MOCK_RESULT_PRESENT`. Six-step Readiness Ladder (education_only→…→controlled_pilot reachable; production_candidate/released unreachable). **The gate report renders the server value verbatim** — the UI never invents blockers.
- Every write is role-gated (import=test, RCA=ASIC/quality engineer, ECO close=architect/approver). Korean demo strings coming from the backend are localized at render time for en/ja.

**v1.1 R2 enhancement (spec §10 — foundry, package, test program, evidence)**

- **Trade Study (EPIC B)**: weighted NRE/unit-cost/lead-time scoring across process & package options. Undetermined axes are never computed as 0 — partial score plus named TBD axes. The decision records rationale and residual risks; money is visible only to CAN_COST roles. Stage ③.
- **EDA ToolRun (EPIC C)**: `real_adapter` runs must carry the tool output sha256 + lineage; `mock` runs stay honestly visible as the `MOCK_RESULT_PRESENT` gate blocker. Stage ④.
- **Test program twin (EPIC D)**: per-flow items/time/coverage for wafer_sort & final_test plus **cross-target analysis** (same-limits duplicates flagged as drop candidates, coverage gaps surfaced — review-only, nothing auto-applied). Cost is null (TBD) where the per-site-hour rate is undetermined — never computed as 0. Stage ⑥.
- **Supply chain & lot genealogy (EPIC H)**: foundry/OSAT/subcon partner status, PCN tracking, lot travelers carrying silicon/mask/package revisions, wafer maps with yield/retest rates and overkill/underkill confusion (with source_class chip). Stage ⑨.
- **Product verification packs (P1-07)**: dedicated seeds for all four product templates — the current-sensor template (B) carries the full R1+R2 closed loop, A/C/D carry verification packs (signal chain, trade study, test flows).
- **Evidence report (P1-08)**: `GET /asic/templates/{id}/evidence-report?lang=ko|en|ja` — design, measurements, qualification, safety, test program, supply chain and gate sections in all three languages. Money is excluded (CAN_COST views only), TBDs are named rather than zero-filled, and SYNTHETIC/MOCK sources never read as measured in any language. The panel follows the UI language automatically.

### 3.10 Result compare · correlation · gate (bottom frame)

- **SPICE Resistance Sweep — Variant Compare (S08)**: overlay-compare two or more variants on identical axes and units (§12.2).
- **Test & Correlation (S09)**: prediction vs measurement correlation table.
- **Gate (S10)**: gate submission / review status.
- **Assistant**: LLM assistant panel (queries, screen guidance).

### 3.11 System Docs tab (this document)

- This document rendered in-app + a `.md` download button (reporting / onboarding attachment).
- A standalone reference menu, independent of the product/variant context.
- **admin account only (v1.3)** — matched on the token's `preferred_username` being `admin`; any other session never renders the tab.

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
| Premium instrument UI & theme | design-token shell (embossed buttons, metallic panels), premium chart themes, app-wide dark/light toggle (instrument glass stays dark) | commercial-grade screen quality; readability under any lighting |
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
- **Design system**: `--alps-*` CSS variable tokens + `ui/tokens.ts`·`ui/kit.tsx` (HudPanel/Chip/GateDot) + `useChartTheme` (canvas)·`useSvgPalette` (SVG)·the premium ECharts theme; dark/light via `ui/useTheme.ts` + `:root[data-theme]` overrides
- **Production-line 3D**: `proc/factoryScene.ts` (pure builder over a plain-array scene spec) + `FactoryViewer` — station status colors, conveyor lot dots, click drawers
- **Determinism**: `strSeed` + mulberry32; same seed → same waveform/KPI
- **Document**: this file `apps/web/src/assets/systemDoc.en.md` (bundled at build time, `?raw` import)
