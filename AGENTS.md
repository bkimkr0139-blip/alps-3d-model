# AGENTS.md

Conventions for anyone (human or agent) continuing work on this repo. Full
requirements: `docs/AlpsAlpine_Engineering_Digital_Twin_Workbench_개발지시서_v1.0.md`.
**세션 인수인계/병렬 작업 규칙: `docs/HANDOFF.md` 를 먼저 읽을 것** — 현재
상태, 남은 작업 목록, 병렬 작업 규칙, git 운영 규칙이 거기 있다. Current
plan/milestones: see the plan this was built from (M0 infra → M1
core/auth → M2 3D → M3 SPICE → M4 test correlation → M5 AI copilot → M6
Gate/audit → M7 external exposure).

## Running the stack

- Infra (Postgres/Redis/MinIO/OpenSearch/Keycloak/Temporal/observability):
  `make up` from repo root (needs `.env`, copy from `.env.example`).
- Postgres host port is **5433**, not 5432 — this machine already runs a
  Homebrew Postgres on 5432.
- API: `cd apps/api && .venv/bin/uvicorn app.main:app --reload --port 8000`.
- DB migrations live in `db/migrations` but the models they diff against are
  `apps/api/app/models/*`. Run them with the **API venv**, not `db/.venv`
  (which only has bare alembic/sqlalchemy, no FastAPI app deps):
  `cd db && /path/to/apps/api/.venv/bin/python -m alembic upgrade head`.
- Golden dataset seed (TACT Switch Variant A/B): `apps/api/.venv/bin/python scripts/seed_golden_dataset.py`
  against a running API + Keycloak. Idempotent — safe to re-run.
- Tests: `cd apps/api && .venv/bin/python -m pytest`. They run against
  `alps_twin_test` (a separate DB from the dev/demo `alps_twin` — never point
  tests at the dev DB, they truncate tables between tests).

### Full local process checklist (after a reboot / new session)

Everything below except `frpc` needs to be started manually — none of it is
a system service except `frpc` (LaunchAgent) and `nginx`/`docker` (brew
services, but Docker Desktop itself still needs to be running).

1. `make up` (repo root) — Docker Compose infra.
2. `cd apps/api && .venv/bin/uvicorn app.main:app --port 8000` (background).
3. `cd apps/web && npm run dev -- --port 5173 --host 127.0.0.1` (background —
   `--host 127.0.0.1` matters, Vite defaults to IPv6-only `::1` which nginx's
   `proxy_pass http://127.0.0.1:...` can't reach).
4. Workers, one per task queue (background each):
   `apps/workers/cad-converter/.venv/bin/python worker.py`,
   `apps/workers/spice-worker/.venv/bin/python worker.py`,
   `apps/workers/mech-model/.venv/bin/python worker.py`.
5. `brew services start nginx` if not already running (serves
   `infra/nginx/local-gateway.conf` on :8090 — see M7 section).
6. `frpc` should already be running via LaunchAgent
   (`launchctl list | grep alps-twin`); if not,
   `launchctl load ~/Library/LaunchAgents/com.alps-twin.frpc.plist`.
7. Open **`http://localhost:8090`** (not :5173 directly — see M7 section).

Log everything to `/tmp/alps-logs/*.log`, never a bare `/tmp/<name>.log` —
see the M4 gotcha about a filename collision with an unrelated service on
this shared machine.

## Patterns established in M1 — follow these for new endpoints

- Every write endpoint: RBAC check first (`require_role(...)` dependency) →
  domain write → `record_audit(...)` → wrapped in `idempotent_write(...)` so a
  retried request with the same `Idempotency-Key` doesn't duplicate the write.
  See `app/routers/products.py` for the reference shape.
- Domain entities get `IdentifiedMixin` (UUID PK + unique human Business ID)
  and `ProvenanceMixin` (`created_by`/`created_at`). Technical bookkeeping
  tables (like `idempotency_records`) don't — see `app/models/idempotency.py`.
- New models: add the module, then import it in `app/models/__init__.py` so
  the mapper registry can resolve string-based `relationship()` refs, then
  `alembic revision --autogenerate`. Autogenerate has correctly picked up
  every table/enum/index so far — always review the generated migration
  before applying, don't blind-trust it forever.
- Baselines are append-mostly: `manifest` (JSONB) is frozen at creation and
  never rewritten; `status` transitioning ACTIVE→SUPERSEDED on the next
  Baseline for the same Variant is the one allowed mutation.
- Auth: JWT from Keycloak (`http://localhost:8081`, realm `alps-twin`),
  validated against its JWKS in `app/security.py`. Roles come from
  `realm_access.roles` — the ten roles from §4 of the spec, defined in
  `infra/keycloak/realm-export.json`. `platform_admin` bypasses every
  `require_role` check.

## M2 additions — artifacts, Temporal, CAD conversion

- Large-file upload is presigned-URL-based (§9.3): `POST /artifacts/uploads`
  creates an `Artifact`/`ArtifactVersion` row (`status=pending_upload`) and
  returns a MinIO presigned PUT URL; the client PUTs directly to MinIO; then
  `POST /artifacts/versions/{id}/promote` has the **server** download the
  object and compute its own SHA-256 — never trust a client-supplied hash.
  boto3 against MinIO needs `Config(signature_version="s3v4", s3={"addressing_style": "path"})`
  (see `app/storage.py`) or presigned URLs 403 with `SignatureDoesNotMatch`.
- `POST /simulation-runs` does NOT use the shared `idempotent_write` helper —
  it has an async side effect (starting a Temporal workflow) that must fire
  at most once, so it checks `IdempotencyRecord` itself before creating the
  DB row, and only starts the workflow on the branch that creates one.
- CAD conversion (STEP → glTF) lives in `apps/workers/cad-converter/`, its
  own venv (`cadquery-ocp` + `trimesh`, not conda-only `pythonocc-core`).
  **Split into two files on purpose**: `workflow_defn.py` (the
  `@workflow.defn` class, importing only `temporalio.workflow` — Temporal's
  sandbox re-imports whatever module defines the workflow class to run it
  deterministically, and flags any restricted call like `Path.resolve()` made
  at module import time) and `activities.py` (the actual OCP/DB/MinIO work,
  referenced from the workflow by **string name**, not by importing the
  function). Don't collapse these back into one file.
- Every worker (`apps/workers/*`) reuses `apps/api/app/*` for models/config
  instead of redefining them — it prepends `apps/api` to `sys.path`. Start
  the worker with `apps/workers/cad-converter/.venv/bin/python worker.py`.
- Test DB schema is `drop_all` + `create_all` every pytest session (see
  `tests/conftest.py`) — `create_all()` alone only adds missing tables, so a
  changed column on an existing table would otherwise test against a stale
  schema silently.
- No pytest coverage yet for an actual Temporal workflow run (would need a
  live worker + Temporal in the test harness) — that path is verified
  manually end-to-end (upload → promote → simulation-run → poll) but not
  automated. TODO before this is "done".

## M3 additions — SPICE, ERC, multi-worker task queues

- `apps/workers/spice-worker/` follows the exact same split as cad-converter:
  `workflow_defn.py` (import-light, references the activity by string name)
  + `activities.py` (the real work) + `worker.py` (registers both against its
  own Temporal task queue). Copy this shape for any new worker type.
- `app/routers/simulation_runs.py`'s `_WORKFLOW_BY_RUN_TYPE` maps
  `RunType -> (workflow name, task queue)` — each worker only needs to run
  the workers whose task queue it owns; the API doesn't care which process
  picks a job up.
- ERC here is **structural only** (ground reference exists, at least one
  source, no single-connection "floating" nets) over a raw SPICE netlist —
  see `apps/workers/spice-worker/erc.py`. This is NOT KiCad's real ERC
  (pin-type conflicts, footprint rules), which needs an actual `.kicad_sch`
  project file. Revisit if a real KiCad project ever replaces the synthetic
  netlist fixtures.
- ngspice sweeps use its `.control` `foreach ... alter ... op ... print`
  idiom (see `spice_runner.py`) — NOT `let x = list(...)` / `let x = [...]`,
  neither parses in ngspice-47's scripting language.
- No `ParameterSet`/`ModelVersion` entities yet (§9.1 lists them) — sweep
  inputs (`sweep_ohms`, `logic_low_threshold_v`) ride on `SimulationRun.parameters`
  (JSONB) instead. Deliberate scope cut for the vertical slice; promote to
  real entities if a second run type needs versioned reusable parameter sets.
- `scripts/seed_golden_dataset.py` now drives the **full** pipeline end to
  end (product/variant/requirement/component/baseline + CAD upload+convert+
  link + netlist upload+SPICE sweep), reading fixtures from `scripts/fixtures/`.
  Re-running it is idempotent (same Idempotency-Keys throughout) — verified
  row counts don't change on a second run. This is the golden-dataset
  regression fixture referenced in the plan.

## M4 additions — F-S model, test upload, correlation

- `apps/workers/mech-model/fs_model.py` is a deliberately simple three-segment
  analytical F-S curve (rise → snap-through drop → end-of-stroke stiffening),
  NOT a validated FEA/shell-buckling model — a real one drops in later with
  the same `(x_mm[], force_mN[])` return shape. Same worker split pattern as
  cad-converter/spice-worker (`workflow_defn.py` string-references the
  activity; `activities.py` does the real work).
- `SimulationRun.parameters` (JSONB, added in M3) now also carries mech-model
  inputs (`dome_thickness_mm`, `dome_diameter_mm`) — still no dedicated
  `ParameterSet`/`ModelVersion` entities (§9.1 lists them, deferred).
- Correlation math (`app/correlation.py`) runs **synchronously in the API
  request**, not a Temporal workflow — it's cheap numpy arithmetic on already-
  computed data, not worth job orchestration (§8.3 "PoC 과설계 방지").
- `POST /test-runs/{id}/measurements` takes a raw CSV multipart upload
  directly through the API (not the presigned-URL dance from M2/M3) — that
  flow is for large files per §9.3; test CSVs are small user uploads. The raw
  file is still stored as a CSV Artifact before parsing (FR-07: original
  never overwritten), and a second upload to the same TestRun is rejected —
  create a new TestRun for a re-test instead.
- Correlation requires both sides in **mm/mN** — mismatched units are
  rejected outright rather than silently converted (§5.3 unit normalization;
  §16 risk: "시험데이터의 단위·시간축·Calibration 불일치").
- **A numpy scalar (`numpy.bool_`, `numpy.float64`) passed straight into a
  SQLAlchemy column silently produces an opaque psycopg `dump_sequence`
  failure with no useful message.** `app/correlation.py` returns plain
  Python types for exactly this reason (`bool(...)`, `float(...)`) — do the
  same in any new numpy-touching code path before it hits the ORM.
- **Never log to a generic `/tmp/<name>.log` path** (e.g. `/tmp/api.log`) —
  this machine runs many unrelated long-lived services from other projects,
  and a filename collision silently interleaves someone else's process
  output into what looks like your own log (this happened here — wasted real
  debugging time chasing a phantom error). Use a project-scoped directory,
  e.g. `/tmp/alps-logs/*.log`, for every `nohup ... &` in this repo.
- Realm changes in `infra/keycloak/realm-export.json` only take effect on
  **first** container start — Keycloak persists to its Postgres DB (`KC_DB`),
  so `--import-realm` on a later restart sees the realm "already exists" and
  skips it. To pick up new users/roles: stop the `keycloak` container, `DROP
  DATABASE keycloak; CREATE DATABASE keycloak OWNER alps;`, then start it
  again — this invalidates old tokens (dev-only realm, no real consequence).

## M6 additions — Gate/approval/audit

- `app/gate_readiness.py` is the §12.2 "승인 전 필수 증적 누락 시 Gate 차단"
  check: a pure read-only query building a checklist (baseline exists, every
  requirement traced, SPICE/mech-model succeeded, correlation computed and
  ≥0.9 without extrapolation warning). It runs at **submit** time, not
  decision time, and is enforced server-side (`POST /gates/{id}/submit`
  returns 412 with the specific `missing` list) — the frontend's checklist
  display is read-only feedback, not the actual gate.
- Independence (§4) is enforced literally: `POST /gates/{id}/decisions`
  rejects if `actor == gate.submitted_by` (a `platform_admin` decider is the
  only exception). RBAC (`reviewer_approver` role) is checked first, so a
  same-user self-approval attempt returns 403 for the role reason before ever
  reaching the independence check — see `test_gates.py` for why that test
  asserts 403 and not some independence-specific code.
- `Gate.evidence_checklist` and `required_roles` are frozen once submitted —
  `Gate.status` is otherwise the only field written after creation, with
  `GateDecision` rows staying append-only (a changed mind is a new decision
  row, not an edit).
- `GET /gates/{id}/evidence-package` is the §FR-09 "Export 가능한 증적
  패키지" — bundles the frozen Baseline manifest + all comments + all
  decisions + the Gate's own audit-event slice into one document. This is
  the reference shape (`{gate, baseline, comments, decisions, audit_trail}`)
  for the "완료 보고" evidence bundle expected at the end of the vertical
  slice (§20 완료 보고 형식: "실행 및 테스트 결과").
- **The first vertical slice from §20 is now fully closed end-to-end**:
  `scripts/seed_golden_dataset.py` runs Variant A/B from nothing through
  Requirement→Component→CAD→SPICE→F-S model→Correlation→Baseline→Gate
  submit→independent-reviewer approval, idempotently. This is the
  regression fixture to re-run after any change touching that path.
- Gotcha for scripts (not just tests): an **idempotent POST's cached
  response body reflects creation-time state**, not current state — after
  `post()`-ing a Gate that idempotency might have short-circuited, `GET` it
  again before branching on `status` (see the fix in `seed_golden_dataset.py`
  — the first version of this script mistakenly branched on the stale cached
  `draft` status and tried to double-submit an already-approved Gate).

## M7 — external exposure (DONE, browser pass COMPLETE)

**Status as of 2026-09-13 (evening)**: The real-browser pass over
`https://alps-twin.wizbase.ai.kr` is done — via headless Chromium
(Playwright, `channel: "chromium"`; the bare chrome-headless-shell renders
no text glyphs on this machine, so use the full browser in new-headless
mode for any screenshot-based check). Verified visually with screenshots
(`/tmp/alps-browser-pass/`): Keycloak login click-through (PKCE), the full
workbench rendering as `demo.architect` — S03 requirements with ASIL
badges, the dome glTF in S04, run cards with tool versions, the S08
variant-compare sweep chart, S09 predicted-vs-measured correlation
(A: r=0.991, B: r=0.999), S11 gate checklist + approval history —
requirement-click selection sync, variant A→B switching, and **zero
console errors / zero HTTP ≥400**. Deliberately NOT clicked in the
browser: gate submit/approve buttons (both variants' gates are already
approved in the demo data; driving a new gate E2E would mutate demo state
— API-level coverage exists in `test_gates.py` if ever needed).

The browser pass surfaced and fixed three real bugs the curl-level M7
checks could never see — see the gotchas below. The repo still has **zero
git commits**; the fix went in with no baseline to diff against, which is
also why the broken import below survived this long.

Cert: Let's Encrypt via `certbot --nginx -d alps-twin.wizbase.ai.kr`
(non-interactive, reused the server's existing ACME account — no `-m` email
needed since one was already registered for the other `*.wizbase.ai.kr`
certs). Expires 2026-12-12, auto-renews via certbot's existing scheduled
task on that server (same mechanism as every other domain there).

### Done and verified
- Local nginx gateway (`infra/nginx/local-gateway.conf`, port 8090) combines
  Vite (5173), FastAPI (8000), and Keycloak (8081, under `/realms` and
  `/resources`) under one origin — installed via `brew install nginx`,
  config symlinked into `/opt/homebrew/etc/nginx/servers/`, running via
  `brew services start nginx`.
- Frontend now always talks same-origin: `apps/web/src/lib/api.ts` uses
  relative paths (no `VITE_API_URL`), `apps/web/src/lib/keycloak.ts` uses
  `window.location.origin`. **Dev workflow changed**: open
  `http://localhost:8090`, not `http://localhost:5173` directly — the app
  needs the gateway's `/realms`/`/api` proxying to function at all now.
- `frpc` (exact version 0.69.0, matching the server — see gotcha below)
  installed at `infra/frp/bin/frpc`, config at `infra/frp/frpc.toml`
  (gitignored, copy from `frpc.toml.example`), registered as a LaunchAgent
  (`infra/frp/com.alps-twin.frpc.plist`, symlinked into
  `~/Library/LaunchAgents/`) so it survives reboots/logouts.
- Keycloak client `alps-twin-web`'s redirect URIs/web origins updated (via
  Admin REST API, not a realm-file/DB-wipe round trip) to `localhost:8090`
  and `https://alps-twin.wizbase.ai.kr`.
- JWT issuer validation now accepts multiple valid hosts
  (`app/config.py: keycloak_accepted_issuer_hosts`,
  `app/security.py: _decode`) instead of one hardcoded issuer — Keycloak
  stamps `iss` from whatever Host it was reached through (direct :8081,
  gateway :8090, or the public domain), and all are legitimate.
- End-to-end verified through the **actual** tunnel (not just locally): SSH
  to the server and curl `http://127.0.0.1:8080/...` with
  `-H "Host: alps-twin.wizbase.ai.kr"` to simulate what the remote nginx will
  send once it exists — login, token issuance with the correct `https://`
  issuer, and an authenticated API call all succeed this way right now.

### Remaining: a real browser pass — DONE, see M7 status above

### Gotchas found by the browser pass (2026-09-13, all fixed)
- **Never hand the SPA a presigned MinIO URL.** The 3D viewer used
  `download-url`'s presigned GET (`http://localhost:9000/...`): from any
  origin other than this Mac it's unreachable, and from the HTTPS page it's
  mixed content + CORS-blocked anyway. The unhandled failure **unmounted the
  whole React tree** — the user-visible symptom was "workbench flashes, then
  blank". Fix: `GET /api/v1/artifacts/versions/{id}/content` streams the
  object through the API (authenticated — presigned URLs bypass RBAC, so
  this is also the more correct security posture); the viewer fetches bytes
  via `api.artifactContent()` and parses with `GLTFLoader.parse`. `useGLTF`
  can't send auth headers, so it's gone from the viewer. `download-url`
  remains for tool-side use only.
- **A render error anywhere in the Canvas unmounts the entire app** (React
  default). `ViewerErrorBoundary` now wraps the `<Canvas>` so viewer failures
  degrade to an in-panel message. Keep that boundary when touching the
  viewer — it's the difference between "one panel broken" and "whole
  workbench blank".
- **`ThreeViewer.tsx` imported `"./store"` instead of `"../store"`** — a
  module that never existed. With no commits and no prior browser pass,
  nothing ever caught it; Vite 500s the whole import graph, which is another
  way to get the "blank after login" symptom. If Vite serves a 500 on a
  source module, `curl http://127.0.0.1:5173/src/<file>` prints the full
  transform error including the failing import.
- **The S04 canvas overflowed its grid cell** (948×1526px, painting over
  the S08/S09 charts and S11 gate). Percent-height inside an auto-height
  grid cell gives the R3F canvas no constraint. Fixed in `App.tsx`:
  middle column is `flex` + `minHeight: 0`, canvas wrapper `flex: 1` +
  `overflow: hidden`. Canvas measured 948×673 after the fix.

### Gotchas hit and fixed while building this
- **frpc/frps version must match exactly.** brew's `frpc` (0.71.0) logs in
  fine but every proxied request fails with `token in NewWorkConn doesn't
  match token from configuration`. Downloaded the exact `v0.69.0` darwin_arm64
  release from GitHub instead (`infra/frp/bin/frpc`) — do not `brew install
  frpc` and expect it to work against this server without checking versions
  match (`frps --version` on the server vs. the client binary) first.
- **`auth.additionalScopes` must be set client-side too, not just on frps.**
  The server's `/opt/frp/frps.toml` has
  `auth.additionalScopes = ["HeartBeats", "NewWorkConns"]`; if `frpc.toml`
  doesn't have the identical line, control-channel login succeeds (misleading
  — looks fine) but every actual proxied work connection fails with the same
  "token in NewWorkConn doesn't match" error. Copy this line from a working
  sibling project's frpc.toml on this machine (e.g. `~/works/bc-ai/frp/frpc.toml`)
  rather than guessing.
- **nginx's `$host` variable drops the port.** `proxy_set_header Host $host`
  turned `localhost:8090` into just `localhost` on the way to Keycloak,
  producing tokens with the wrong (portless) issuer. Use `$http_host`
  instead everywhere the original Host header (with port) needs to survive.
- **frp does not forward a client-supplied `X-Forwarded-Proto` through the
  tunnel** — frps overwrites it based on its own (always-plain-HTTP)
  connection from the remote nginx, regardless of what the real edge TLS
  termination set it to. Verified empirically with a debug `add_header`
  round-trip — don't waste time trying to "fix" this by forwarding the
  header again through frpc/nginx, it won't work. The fix that does work:
  derive the scheme from the Host header via an nginx `map` (see
  `local-gateway.conf`) since this deployment's topology is fixed and known
  (the public domain is only ever reachable over HTTPS).
- **`KC_PROXY_HEADERS: xforwarded`** had to be added to Keycloak's
  docker-compose env for it to trust `X-Forwarded-Proto`/`X-Forwarded-Host`
  at all (verified directly against Keycloak first, bypassing nginx, to
  isolate this from the frp issue above — that's the right debugging order:
  confirm the immediate hop trusts the header before chasing it further
  upstream).
- **Never `pkill -f <generic-name>` on this machine.** It killed another
  project's (`bc-ai`) `frpc` process, which shares this same frps server.
  Restored it immediately, but the lesson: this Mac runs many unrelated
  long-lived services from other projects (confirmed earlier too — see the
  `/tmp/api.log` collision in the M4 section) — always find and kill by
  exact PID scoped to a path check (`lsof -nP -iTCP:<port> -t`), never by a
  loose process-name pattern.

## M5 (partial) — i18n + onboarding + AI assist (DONE, browser pass COMPLETE)

**Status as of 2026-09-13 (night)**: Three features shipped on top of the
finished M0–M7 stack: (1) ko/en/ja i18n with a header switcher + browser
auto-detect, (2) a state-derived onboarding guide strip, (3) an AI assistant
panel driving the API in natural language (FR-08/S10 un-deferred partially —
see scope note below). Verified: 34/34 pytest green, `tsc -b` + `vite build`
+ `oxlint` clean, and a headless-Chromium pass over the public URL in all
three languages (screenshots `/tmp/alps-browser-pass/shot-i18n-*.png`).

### i18n conventions (follow for any new UI string)

- Locales are **TS modules, not JSON**: `apps/web/src/i18n/locales/en.ts`
  exports the object and `type Resources = typeof en`; `ko.ts`/`ja.ts` are
  annotated `: Resources` — a key added to one locale but not the others is a
  **compile error**, not a runtime gap. Keep that parity discipline.
- Typed `t()` comes from `declare module "i18next" { interface
  CustomTypeOptions { resources: { translation: Resources } } }` in en.ts.
  Keys built at runtime from API data (enum values, checklist keys) don't fit
  the literal key union — use the `enumLabel(t, group, value)` /
  `checklistLabel(t, key)` helpers in `src/i18n/index.ts` (`as never` cast +
  `defaultValue`), don't inline new casts.
- Detection order `["localStorage","navigator"]` with
  `lookupLocalStorage: "alps-lang"` and `caches: []` — the LanguageSwitcher
  writes `alps-lang` itself. `load: "languageOnly"` (no region suffixes).
- `applyDocumentLanguage` (in `src/i18n/index.ts`) keeps
  `document.documentElement.lang` and `document.title` in sync on
  `languageChanged`. New top-level strings (title, head) go there too.
- Interpolation uses `{{n}}` (not `{{count}}`) where a number is embedded —
  `count` triggers i18next's plural machinery and needs plural forms per
  locale. Don't accidentally reintroduce it.

### Onboarding guide

- `apps/web/src/components/OnboardingGuide.tsx` derives its 8 steps purely
  from data the Workbench already fetched (plus its own async
  listCorrelations/listGates fetches when relevant) — there is **no backend
  "onboarding state"**. The first undone step renders as an amber "→" chip
  with a hint line; an all-done variant shows every chip "✓".
- Collapse state is a single global localStorage flag
  (`alps-onboarding-dismissed`), not per-user server state — deliberate PoC
  scope cut; per-user persistence would need a users table (see known gaps).

### AI assistant — architecture and constraints

- Backend: `apps/api/app/assistant/{client,store,tools,loopback,prompts,service}.py`
  + `app/routers/assistant.py`. Tool loop is **manual** (`while
  stop_reason == "tool_use"`), not the SDK tool runner, because write tools
  must halt the loop for human confirmation.
- **Loopback with the end user's token**: every tool executes as
  `GET/POST {internal_api_base_url}/api/v1/...` carrying the **caller's own
  bearer token** (httpx client from `get_loopback_client()`). The assistant
  therefore inherits the exact RBAC/validation/gate-readiness paths — it
  cannot escalate privileges. Don't replace this with service-account calls.
- Write tools (`create_baseline`, `open_gate`, `submit_gate`,
  `add_gate_comment`, `decide_gate`) are intercepted in-loop: the loop stores
  a PendingAction (in-process, TTL 15 min) and returns a confirmation card to
  the UI. Confirm/cancel is a separate endpoint; confirm executes via
  loopback POST with `Idempotency-Key: ai-assist-{action_id}`. 4xx from the
  loopback is returned as `status:"failed"` **data**, not an HTTP error (the
  model needs to see it).
- The canonical thread is **server-owned**: the chat response includes
  `thread` (JSON-safe, thinking blocks preserved) and the client echoes it
  back untouched on the next turn. After a confirm/cancel the client swaps
  the synthetic `requires_user_confirmation` tool_result for the real outcome
  and re-calls chat so the model summarizes — one code path for both.
- **In-memory PendingActionStore assumes a single uvicorn worker** (PoC
  assumption, consistent with the rest of the stack). Multi-worker or restart
  = pending cards expire (client shows the localized "expired" message).
  Restarting the API invalidates pending cards.
- Key resolution is deterministic: `settings.anthropic_api_key` or
  `ANTHROPIC_API_KEY` env, else **503** with a clear message (the UI shows a
  localized "not configured" card — quiet failure is forbidden). No profile
  fallbacks. Model/config: `anthropic_model` (default `claude-opus-5`),
  `assistant_max_tool_rounds`, `assistant_max_messages` (40, over → 422),
  `assistant_pending_ttl_seconds`.
- §10.2 guardrails live in `prompts.py`: answer only in `ui_language`, cite
  only tool results (no invented numbers), never finalize ISO
  26262/AEC-Q100/EMC compliance judgments, never claim unexecuted actions,
  remind that gate decisions carry a human e-signature.
- Tool results are truncated before returning to the model (lists → 20 items,
  strings → 500 chars, whole result → 8KB) — keep that when adding tools.

### Test pattern for the assistant (new in this repo)

`tests/test_assistant.py` introduces a reusable shape: a scripted
`FakeAnthropic` (dependency-overridden via `get_anthropic_client`) + the
**real app under an ephemeral uvicorn server** (session fixture, port 0) as
the loopback target, so confirms exercise real routing/validation/RBAC.
`httpx.MockTransport` variant asserts the user's Authorization header is
forwarded verbatim. Note `AUTH = {"Authorization": "Bearer ..."}` is required
on every assistant call in tests — HTTPBearer rejects headerless requests
even when `get_current_user` is overridden. Copy this pattern for future
LLM-loop tests; never let a test call the real API.

**Scope note**: the assistant reads and drives the existing API surface but
is not the full §10.2/S10 copilot (no proactive analysis, no artifact
generation, no per-project knowledge retrieval). Key still needed in `.env`:
`ANTHROPIC_API_KEY=...` (user adds it; never paste it into chat/logs).

## S04 3D model upgrade — named STEP assembly + PBR viewer (DONE, browser pass COMPLETE)

The S04 fixture is now a **7-part named XCAF assembly** of a 4.5×4.5 mm SMD
tact switch (Switch Housing, Contact Pad, Metal Dome, Plunger, Epoxy Seal,
Terminal 1/2) converted per-part with PBR materials, rendered in an
environment-lit viewer with part selection. Verified end-to-end 2026-09-14
(pytest 34, tsc/vite/oxlint, live reseed, headless pass over the public URL —
screenshots `/tmp/alps-browser-pass/s04-assembly-*.png`).

Facts that were expensive to learn (do not re-derive):

- **OCP XCAF**: `Sequence_TDF_Label` lives in `OCP.collections`, NOT
  `OCP.TDF`. `NewDocument` returns a TUPLE — index `[0]` is the doc.
  `BRepPrimAPI_MakeSphere` angle1/angle2 are **latitudes from the equator**
  ([-π/2, π/2]), not polar angles; a spherical cap = `(asin of base-circle
  latitude, π/2)`. Verified write/read sequences live in
  `apps/workers/cad-converter/generate_sample_step.py` / `convert.py`.
- **trimesh 5.1.0 PBR**: factor values must be floats (ints are dropped by
  the glTF exporter). Identical materials are **deduped by hash** in the GLB,
  so three.js shares ONE Material instance across parts — the viewer clones
  every mesh material at parse time (`prepareAssemblyScene`) or the selection
  highlight's emissive tint would light unrelated parts.
- **Viewer geometry conventions**: STEP is Z-up, glTF/three Y-up → the
  renderer wraps content in `<group rotation={[-Math.PI/2,0,0]}>`. Do NOT add
  `<Center>` around it: drei `Bounds fit` already targets the measured box
  center, and (empirically, fov 40, diagonal view) `margin={1.4}` is too
  tight for flat+tall models — the near corner's perspective overflows the
  frame bottom. `margin={2.0}` frames the switch with room. `Bounds` clips
  camera near/far from the same measurement.
- **Part naming through the pipeline**: trimesh node names keep the XCAF
  label text but **underscores replace spaces** ("Switch_Housing"). The
  viewer normalizes both sides (`lower()` + strip non-alphanumerics), so
  spaces/underscores don't matter. Only 3 of the 7 parts map to seeded
  Components — clicking Plunger/Terminals/Epoxy clears the selection (no
  component behind them); that's by design.
- **Derived-artifact re-conversion**: the GLB derivative's business_id is
  deterministic (`{input_version.business_id}-gltf`), so converting the same
  input version twice used to hit a UniqueViolation. `activities.py` now
  reuses the existing derived Artifact and **appends version N+1**
  (`…-gltf-v2`, storage key `artifacts/{id}/v2/derived.glb`). RUN-CAD-03's
  failed rows in the demo DB are the recorded history of that collision
  (before the fix); RUN-CAD-04 holds the good assembly GLBs.
- **Seed presigned-URL expiry**: `upload_and_promote` retries once with a
  fresh upload key when the PUT gets a non-2xx (presigned URLs expire after
  1h); each retry leaves one orphaned PENDING artifact_version row (never
  served, harmless).
- **Worker restart gotcha (bit twice)**: `pgrep -f "cad-converter/.venv/bin/
  python worker.py"` matches NOTHING — venv python resolves to
  `…/MacOS/Python worker.py` in ps. List with `ps aux | grep worker.py` and
  identify each PID's worker via `lsof -a -p PID -d cwd -Fn` (the cwd is the
  worker dir). Stale old-code workers silently steal queue tasks and convert
  with old code — that's how RUN-CAD-02 got a merged-mesh GLB on 2026-09-14.
- Viewer env lighting: drei `<Environment preset>` fetches remote HDRIs this
  deployment can't reach — use the RoomEnvironment PMREM pattern in
  `ThreeViewer.tsx` (`ViewerEnvironment`).

## Phase 2 — three ALPS product families, product selector (DONE, browser pass COMPLETE)

The demo dataset is now **3 products × 2 variants** (seeded by the
product-table-driven `scripts/seed_golden_dataset.py`): TACT Switch
(unchanged), **Rotary Encoder** (`rotary_encoder_asm.step`, 9 named parts,
detent-torque prediction + 47k-pullup push-switch sweep) and **MEMS Pressure
Sensor** (`mems_sensor_asm.step`, 5 named parts, bridge-transfer prediction +
piezoresistive half-bridge sweep 4.5–5.5 kΩ). Verified end-to-end 2026-09-14
(pytest 34, tsc/vite/oxlint, reseed + correlation/gate repair, API
verification `/tmp/alps-logs/verify_phase2.py` ALL CHECKS PASSED, headless
pass `/tmp/alps-browser-pass/phase2-pass.mjs` RESULT: CLEAN across all three
products — screenshots `p2-*.png`).

Facts that were expensive to learn (do not re-derive):

- **Curve-metric contract is triple-synced** — mech worker
  `activities.py MODEL_METRICS`, API `app/correlation.py CURVE_FAMILIES`,
  frontend `TestCorrelationPanel CURVE_FAMILIES`. model_type → metric prefix
  → (x_unit, y_unit): `fs_dome→force_mN_at_x (mm/mN)`,
  `detent_torque→torque_mNm_at_deg (deg/mN·m)`,
  `bridge_transfer→vout_mv_at_kpa (kPa/mV)`. The correlation API validates
  measurement units against the RUN's parsed family (the old hard-coded
  mm/mN check in `routers/correlations.py` is gone). The sweep chart contract
  (`Rcontact` element + `out` node + `v_out_rc_*` metrics) is unchanged and
  shared by all three netlists — for the sensor, `Rcontact` IS the swept
  piezoresistor.
- **Idempotency cache can silently regress data**: the seed's idempotent
  simulation-run POST returns the cached *creation-time* body, so after the
  Phase 2 reseed the TACT variants got re-linked to the old pre-upgrade
  RUN-CAD-02 GLB (the cached body), undoing Phase 1's RUN-CAD-04 link. The
  seed's CAD block now re-lists the variant's runs and links the NEWEST
  succeeded `cad_convert` output (`fix_tact_link.py` was the one-off repair).
  Correlation POSTs that FAIL are not cached — their Idempotency-Keys stay
  free for a retry after fixing the cause.
- **API code changes need an uvicorn restart** (exact PID via
  `lsof -nP -iTCP:8000 -sTCP:LISTEN -t`); the Phase 2 seed ran against the
  old process and every new-product correlation failed with the old unit
  check.
- **Bounds must re-fit when the loaded model SET changes**: the old
  `key={hasScene ? "loaded" : "empty"}` kept the first product's fitted
  camera, rendering the 5 mm sensor as a speck after the tall encoder (and
  the canvas-center click then missed → no highlight). `ThreeViewer` now keys
  `Bounds` by the sorted loaded-version list. Header selects are now
  `[0]=language, [1]=product, [2]=variant` (browser scripts take note).
- New materials in `convert.py MATERIAL_BY_KEYWORD` are keyword-first-hit:
  `encoder frame`→aluminum, `shaft`→stainless, `detent`→spring steel,
  `substrate`→FR4, `die`→silicon, `lid`→nickel, `solder`→solder, `port`→PPA,
  `base`→PBT. "Contact Rotor/Stator" hit the pre-existing `contact`→gold rule.
- The sensor GLB is ~33k triangles (16 small spheres at 0.2 rad angular
  deflection dominate) — 612 KB, fine for the viewer.
- **Stale-worker UniqueViolation + sticky error_message (fixed 2026-09-14)**:
  a pre-S04-code worker process INSERTed the derived GLB artifact without
  the get-or-append lookup → `UniqueViolation` on
  `ix_artifacts_business_id`; Temporal's retry then succeeded, but the
  success path never cleared `run.error_message`, so a SUCCEEDED run
  displayed a raw psycopg error in the UI (`SimulationPanel` renders
  error_message regardless of status). Fixes: all three workers now clear
  `error_message` on success; the cad-converter get-or-create catches
  `IntegrityError` → rollback → adopt the winner's artifact → append
  version (concurrent-conversion race hardening). Verified by RUN-CAD-05
  (same input version, clean append → v4, no error). Remember: after ANY
  worker code change, restart ALL worker processes — old-code processes
  on the same Temporal queue process tasks with old logic.

## Phase 3 — AI assist provider switch: Anthropic → local Ollama (DONE, E2E CLEAN)

The assistant no longer uses the Anthropic API (the key's credit balance ran
dry and the user chose the free local path). It now speaks the **OpenAI
chat-completions format** through the official `openai` SDK, defaulting to
the Mac Studio's local daemon: `llm_base_url=http://127.0.0.1:11434/v1`,
`llm_model=qwen2.5:32b` (96 GB M3 Ultra; 32k context confirmed via
`ollama ps`). Switching to a hosted provider (OpenAI/Upstage/OpenRouter/
Gemini-compat) is a pure config change — `LLM_BASE_URL`/`LLM_API_KEY`/
`LLM_MODEL` in `.env`. Verified 2026-09-14: pytest 36, tsc/oxlint/vite,
local E2E (`/tmp/alps-logs/e2e_ollama_chat.py`) and public-site browser pass
(`/tmp/alps-browser-pass/phase3-assistant.mjs`, RESULT: CLEAN, screenshot
`phase3-assistant.png`) — the 32B model chains 3–7 tools per answer
(products → variants → runs) and answers in the UI language.

Expensive lessons (do not re-derive):

- **Pydantic strips unknown thread keys**: the router's `ChatMessage` had
  only `{role, content}` — enough for the old Anthropic shape (everything
  lived inside content blocks) but it SILENTLY DROPPED `tool_calls` and
  `tool_call_id` on the parse→model_dump round trip, so an echoed thread
  failed sanitization with "bad tool message". They are now explicit fields.
  Symptom worth remembering: sanitize passes when called in-process but 422s
  through the HTTP layer.
- **qwen2.5 invents UUIDs** when asked about a business_id it hasn't
  resolved: it called `get_simulation_runs` with a plausible-looking but
  nonexistent variant id and reported "data missing". Fix was prompt
  hardening in `prompts.py` (NEVER invent ids — resolve business_id → UUID
  through get_products → get_variants; on empty result, re-resolve and retry
  once) plus `temperature=0.1`. After that it chains discovery tools
  correctly. Don't remove those rules.
- The thread canonical form CHANGED (Anthropic blocks → OpenAI messages:
  assistant entries carry top-level `tool_calls`, results are `role:"tool"`
  messages keyed by `tool_call_id`). `AssistantPanel.replaceToolResult`
  matches the new shape; the pending-action wire key stays `tool_use_id`
  (holds the provider's tool-call id) so tests/UI churn stayed minimal.
- Ollama tool-calling facts measured on 0.31.1: `/v1/chat/completions`
  returns proper `tool_calls` with generated call ids and JSON-string
  `arguments`, `finish_reason:"tool_calls"`; daemon context is 32768 (see
  `ollama ps`), so no num_ctx workarounds are needed.
- The API maps provider failures for the UI: `APIConnectionError` → 503
  ("cannot reach the LLM — is it running?" → the panel's localized
  unavailable note), `APIStatusError` → 502. `anthropic` is gone from
  requirements.txt; the leftover `ANTHROPIC_API_KEY` line in `.env` is
  inert (settings use `extra="ignore"`) and can be deleted.
- Read-tool questions are safe to demo freely; NEVER execute (approve) an
  assistant write card on the public demo data — the E2E covers the write
  path via proposal + CANCEL only.

## M8 — Model Canvas / Impact Paths / Model Card / bench F–S overlay (DONE, browser pass COMPLETE)

The first vertical slice of
`docs/AlpsAlpine_AI_3D_System_Modeling_고도화_개발지시서_v1.0.md` shipped
2026-09-14: (① DT-03/AI-06) causal_relations + `GET /api/v1/twins/{id}/impact-paths`
with human-approved vs AI-inferred edge distinction; (② SM-01/E02)
model_elements/model_links domain-colored SVG canvas with §9.3 bidirectional
3D-part links; (③ SL-02) bench F–S/torque/transfer overlay whose cursor
syncs to the actuation animation; (④ TC-03/E10) Model Card with trust
ladder + validity envelope, plus assistant tool `get_impact_paths`.
Verified: pytest 40, tsc/vite/oxlint, headless pass
`/tmp/alps-browser-pass/phase5-model-canvas.mjs` RESULT: CLEAN (screenshots
`sm-*.png`, `bench-fs-*.png`).

Facts that were expensive to learn (do not re-derive):

- **Alembic + `Enum(PyEnum)` gotchas (hit both, cost a downgrade/re-upgrade)**:
  (1) `op.create_table` re-emits `CREATE TYPE` for enum-typed columns even
  after a standalone `ENUM(...).create(checkfirst=True)` → DuplicateObject and
  a failed-transaction rollback. Fix: build the table-column copies with
  `ENUM.copy()` + `create_type = False` (see
  `db/migrations/versions/a1f4c8d92b73_*.py`). (2) SQLAlchemy persists the
  enum member **NAME** ("MECHANICAL"), not the value ("mechanical") — the PG
  enum labels must be the uppercase names even though Pydantic serializes
  `.value` in API responses. Keep those two facts together.
- **idempotent_write caches run BEFORE `compute()`** — any validation that
  must not break a retried replay (e.g. model-card already-exists 409) has to
  live **inside** `compute()`, not before the wrapper. Same root cause as the
  "cached creation-time body" lesson from Phase 2.
- **Curve-family contract is now mirrored in FOUR places** (was three):
  mech worker `MODEL_METRICS`, API `app/correlation.py CURVE_FAMILIES`, web
  `apps/web/src/lib/curve.ts` (shared by TestCorrelationPanel and the bench
  FSOverlay). Add a new product family in all four or the overlay/correlation
  silently falls back to `force_mN_at_x`.
- **Circular-import escape for components that share a store**: `FSOverlay`
  and `TestBench` both needed `useBenchStore`; defining it in either
  component file cycles. Store slices live in `src/store.ts` — put shared
  cross-component state there, not next to the first component that uses it.
- Bench↔twin sync contract: FSOverlay's cursor uses the SAME exponential
  approach (`act += (target − act) · min(1, dt·22)`) as TwinAnimator; encoder
  sweeps in a loop (`(act + dt·0.35) % 1.15`) while `useBenchStore.rotating`;
  MEMS tracks `(pressure − 40) / 360` directly (no animation — pressure IS
  the input). Keep the constants in lockstep or bench motion and 3D motion
  visibly diverge.
- Kansei chips in the overlay are **illustrative** (labelled so in the UI per
  §10.2 — not a validated kansei model). If a real kansei model lands, wire
  it to actual metrics and drop the disclaimer.
- Browser-script gotcha: the bench has TWO monospace spans — `[0]` is the
  run-id label, `[1]` is the live cursor readout. `span[style*='monospace']`
  + `.nth(1)` (`.first()` grabs the label and reports "cursor didn't move").

## M9 — Port Contracts / Model Review / UQ lite / Gap analysis (DONE, browser pass COMPLETE)

Second slice of
`docs/AlpsAlpine_AI_3D_System_Modeling_고도화_개발지시서_v1.0.md`, shipped
2026-09-14: (① SM-01) port_contracts + unit-dimension gate on model-link
create (dimension conflict → 422; same dim/different units → 422 unless the
link carries an explicit `unit_conversion` string), cyan/amber port dots on
the canvas; (② AI-02) rule-based append-only Model Review (MV-01..05 →
model_review_findings with run_no snapshot; POST is deliberately NOT
idempotent — a re-POST is a NEW run); MV-04 validity-envelope check blocks
mech runs whose parameters fall outside the model card (422); (③ SL-03)
seeded-LHS Monte Carlo UQ over the same `fs_model.py` physics (importlib),
`source:"assumed"` inputs, same seed ⇒ byte-identical results (MV-05), SVG
histogram + p05/p50/p95 + target band; (④ AI-05) gap-analysis endpoint:
residual stats + rule-based cause candidates, every one `check_required`
(확인 필요) — never a verdict. Migration `c7e21a4f9b05` (27 tables). PCB
bench artwork redone to industry-standard 45° Manhattan routing with
exact pin/pad alignment, J1 3-pin header + probe wires matched. Verified:
pytest 56, tsc/vite/oxlint, browser pass `m9-pass.mjs` + `m9-bench-zoom.mjs`
RESULT: CLEAN.

- **`unit_dimension(None)` must return `None`, not the dimensionless ""**
  entry — an absent unit means "not declared" (unknown), and treating it as
  dimensionless made seeded MPa links 422. Regression:
  `test_absent_link_unit_is_not_dimensionless`.
- `check_link_units` levels: "ok" | "warning" (unknown unit — savable) |
  "conversion_required" | "error". Ports override element units when both
  exist. Frontend mirrors the table in `apps/web/src/lib/units.ts` — keep
  in sync.
- **Review POST has NO idempotency on purpose** (append-only ledger,
  re-POST = new run_no). UQ, in contrast, uses `idempotent_write` like every
  other compute endpoint. `record_audit` needs a real entity_id → `db.flush()`
  after bulk-inserting findings, then audit per row.
- Curve metric names embed the literal axis: `force_mN_at_x_0.00` matches
  prefix `force_mN_at_x_`. Gap analysis reads measurements sorted by x and
  residuals = predicted − measured; constant-offset detection must be
  `abs(mean) > 2*sd + 1e-12` (a perfect offset has sd = 0).
- Browser-script gotchas: the language switcher is `select` nth(0) — product
  is nth(1), variant nth(2), and the variant list only populates after the
  product select. Center tabs are `h3` headings, not buttons →
  `getByRole("heading", { name: /개발\/테스트 보드/ })`. The bench 3D canvas
  is the tallest canvas with y > 150 (the last canvas is a 150px chart strip).

## TACT P1 — Product–Process Twin vertical slice (DONE, browser pass COMPLETE)

Per `docs/AlpsAlpine_TACT_Switch_Product_Process_Twin_고도화_개발지시서_v1.0.md`
§13 first Vertical Slice. 67 pytest (56 old + 11 in
`apps/api/tests/test_process_twin.py`), migration head `b8f2e4a6c7d1`
(33 tables), new web center tab `proc` ("공정 트윈 (TS03~05)").

- **Models** `app/models/process_twin.py`: Mold, Cavity, ProcessOperation
  (window = JSONB `[{parameter, unit, min, max}]`), Lot (variant/mold/
  cavity/material_lot/work_order/disposition), ProcessRun (`setpoint` vs
  `actual` JSONB + `out_of_window` bool + `window_findings` JSONB), Defect.
  TestRun gained nullable `lot_id` (nullable — see cache lesson below).
- **Flag, don't reject** (MV-04 applies to simulations only): an
  out-of-window process run is stored with `out_of_window=True` and
  findings; the API returns 201 either way. Lot dispositions (ok/
  quarantine/reject) are seed/human inputs — the app never computes them.
- **Root-cause candidates** (`POST /ai/root-cause-hypotheses`, no auth/
  idempotency — read-only compute): 4 rules (process_out_of_window,
  cavity_bias, material_lot, insufficient_data), every candidate
  `confidence="check_required"` with evidence chips (`kind`, `business_id`),
  Korean details, and a disclaimer. Never a verdict (AI-04).
- **Robust stats per AN-02** (반복 편차 vs 일시 이상): drift and
  cavity-bias rules use median/MAD (`1.4826·MAD`), NOT mean/sd — a single
  outlier lot inflating its cavity sd is exactly the case MAD exists for.
  Cp/Cpk use classic mean/sd only when spec_lsl+spec_usl are supplied.
  CavityComparison carries `drift_suspected` + `check_note`.
- **Caching gotcha recurrence (M8 lesson)**: idempotent_write replays the
  body cached at creation time. `TestRunRead.lot_id` had to be
  `uuid.UUID | None = None` or the re-seed 500'd replaying the pre-P1
  cached body of VAR-TACT-A-TR-FS-01. Any new Read-model field: default None.
- Seed story (`seed_process_twin` in scripts/seed_golden_dataset.py):
  MOLD-TACT-01 rev B + CAV-TACT-01/02, ops 10/20/30 (돔 프레스/플런저
  인서트/조립) with windows; 4 lots on VAR-TACT-A — LOT-TACT-A-04 is the
  designed anomaly (different material lot, op10 actual 0.145 out of
  0.07–0.13 window, peak 365 above the demo band, 2 defects, quarantine).
  Normal lots share MAT-SUS304-0912 so the material rule stays quiet, and
  MAD keeps drift_suspected=False (one-off anomaly ≠ recurring drift)
  while the per-lot cavity_bias candidate still fires.
- Web: `ProcessTwin.tsx` (disposition badges icon+text per §5.1, lot table
  → LotDetail genealogy drill-down, CavityStrip Cp/Cpk cards, root-cause
  button). Demo spec band 260–360 mN is a module const applied only for
  PROD-TACT-SWITCH and labelled 데모 사양·합성 데이터.

## AN-04 DOE / optimization

Per `docs/AlpsAlpine_TACT_Switch_Product_Process_Twin_고도화_개발지시서_v1.0.md`
§7 AN-04 (extends base-spec FR-06). 80 pytest (67 old + 13 in
`apps/api/tests/test_doe.py`), migration `f361e9578062` (34 tables), new
"DOE / optimization" panel inside the existing `proc` tab (below the lot
table, not a new center tab).

- **Decision: no `ProcessRun.parameters` column was added.** P1's
  `ProcessRun.actual` JSONB (`{parameter: value}`, keyed by process
  parameter name) already IS per-run structured process-parameter data —
  AN-04 regresses directly against it via a new `_gather_observations()` in
  `app/routers/doe.py`, joining `ProcessRun.actual[parameter]` (x) to the
  lot's own `TestRun`/`Measurement` CTQ value (y, via `_ctq_value` **imported
  from** `app.routers.process_twin` — deliberately not duplicated, and
  `process_twin.py` itself was not touched, to keep this diff's overlap with
  concurrent process-twin work near zero). A lot with more than one
  inspection run averages its CTQ values (still real data).
- **The P1 seed data itself has real parameter variance** (dome_thickness_mm
  actual: 0.09/0.10/0.11/0.145 mm across the 4 TACT-A lots, one of them
  already out-of-window) — no synthetic DOE grid had to be invented on top
  of it. The regression is real but **noisy**: three "normal" lots trend
  slightly *down* (thicker dome → lower peak) while the one out-of-window
  anomaly lot swings sharply up, so the fitted linear sensitivity
  (slope≈+723 mN/mm, intercept≈254, **R²≈0.68**) is dominated by that single
  point. This is disclosed as-is (real n=4 fit), not smoothed or hidden —
  §7 bans fabricating a *better-looking* number as much as fabricating one
  from nothing. Don't "fix" this by adjusting seed peak values to make R²
  prettier; a mediocre R² on n=4 production lots is itself a realistic AN-04
  demo story (small-sample DOE sensitivity is exactly this shaky in practice).
- **Compute is pure and DB-free** (`app/doe.py`: `fit_response_surface`,
  `predict`, `candidate_grid`, `rank_candidates`) — same split as
  `app/correlation.py`, and the reason the regression/ranking math has real
  unit tests against a *known* synthetic linear relationship (not just an
  endpoint-returns-200 check). Degree-1 (linear) fit only — FR-06 marks
  Bayesian Optimization optional and P1's per-parameter sample sizes (single
  digits) don't support a higher-order polynomial. `np.polyfit(x, y, 1)`,
  same primitive `app/routers/correlations.py`'s gap-analysis already uses
  for its residual-trend slope.
- **Persisted as `DoeStudy`** (`app/models/doe.py`, `doe_studies` table) —
  same precedent as `CorrelationRecord`/`UQAnalysis`: cheap synchronous
  compute (§8.3 PoC 과설계 방지, no Temporal workflow) but the *result* is a
  durable, re-fetchable evidence row (`observations`, `fit`, `candidates`,
  `constraint_violations` all JSONB). `POST /api/v1/doe-studies` uses
  `idempotent_write` + `record_audit` like every other write endpoint;
  `GET /api/v1/doe-studies/{id}` and `GET /api/v1/twins/{variant_id}/doe-studies`
  are open reads (no auth), consistent with every other read endpoint in
  this repo (see "Known gaps" below).
- **RBAC**: `require_role("manufacturing_engineer", "mechanical_engineer",
  "system_architect")` — the first use of the `manufacturing_engineer` role
  anywhere in this codebase (it existed in the Keycloak realm/§4 table since
  M1 but nothing had used it until now). Kept as its own constant in
  `app/routers/doe.py` rather than importing `process_twin.py`'s
  `CAN_MANAGE_PROCESS` — same "minimize overlap with concurrent work" reason
  as not touching `_ctq_value`'s home module.
- **Candidates = observed x's (real data) ∪ an evenly spaced grid across the
  operation's approved window** (falls back to the observed x-range if the
  parameter has no declared window bound). Grid points are hypothetical
  *inputs* to the disclosed linear model, not fabricated *outputs* — §7 only
  bans invented result numbers. Ranking (`rank_candidates`) sorts
  (in-window first, meets-target first, closest to target center) — a sort
  over already-computed numbers, never a solver picking one "optimal"
  answer (AN-04: "AI가 단일 해를 임의 확정하지 않는다"). An out-of-window
  observed candidate (like the seeded 0.145 mm lot) can still "meet target"
  on predicted CTQ alone — the ranking deliberately still puts in-window
  candidates ahead of it; see `test_rank_candidates_prefers_in_window_and_on_target`.
- **Scope cuts vs. full FR-06** (documented on `DoeStudy`'s docstring too):
  no Grid/Random/Latin-Hypercube *experiment design* generation — the
  regression runs over process data that already exists, real production
  runs ARE the design points. No Bayesian Optimization (explicitly optional
  per FR-06). No multi-objective Pareto front — the available process-twin
  data has exactly one CTQ per study; revisit if a second CTQ metric per lot
  becomes available.
- **Shared-infra pytest collision (new gotcha, not this repo's bug)**: a
  concurrent worktree's Defect/FA/CAPA work had already added `capas`/
  `capa_events`/`failure_analyses` tables directly to the shared
  `alps_twin_test` Postgres database. Since `conftest.py`'s session-scoped
  `Base.metadata.drop_all()` only knows about tables imported into *this*
  worktree's `app.models`, it failed with `DependentObjectsStillExist`
  trying to drop `test_runs` (which `capas` has an FK into) — this is a
  structural limitation of two branches sharing one non-namespaced test DB
  via `drop_all`/`create_all`, not something either branch did wrong. Fixed
  locally for this session by pointing this worktree's own (gitignored,
  untracked) `.env` at an isolated `POSTGRES_APP_DB=alps_twin_an04` (so
  pytest's `{postgres_app_db}_test` no longer collides with the shared
  `alps_twin_test`) rather than dropping the other branch's tables. Whoever
  merges both branches to `main` will hit the same drop_all clash on the
  real shared `alps_twin_test` the first time after merge — resolves itself
  once both branches' models are imported together in the same `app.models`
  tree (drop_all then sees every table and orders drops correctly).
- Web: new `DoeStudyPanel.tsx`, mounted inside `ProcessTwin.tsx` below the
  lot table (not a new center tab) — a select for (operation, parameter)
  pairs built from `GET /api/v1/process-operations`'s `window` bounds, a
  "run" button, an ECharts scatter (real observations) + dashed line
  (fitted trend, drawn from the two x-extremes only — this IS a straight
  line, so no need for a sampled polyline), the constraint-violations list,
  and the ranked candidate table. `defaultTargetBand` reuses `ProcessTwin`'s
  existing `TACT_SPEC_BAND` (260–360 mN) for `PROD-TACT-SWITCH`, still
  labelled `데모 사양·합성 데이터` end to end (schema default → seed →
  UI note).
- Seed: `seed_process_twin()` in `scripts/seed_golden_dataset.py` posts one
  more idempotent call at the end (`seed-DOE-TACT-A-OP10-dome_thickness`) —
  dome_thickness_mm (OP-TACT-10) vs. F–S peak over the same 4 already-seeded
  TACT-A lots. Not executed against the live dev stack in this session (the
  shared `uvicorn` on :8000 wasn't restarted, per the parallel-work rule —
  old code there doesn't have this router yet); verified instead end-to-end
  via `TestClient` against an isolated scratch DB, reproducing the exact
  fit/candidates shown above. Browser verification is deferred to whoever
  restarts the API with this branch merged in.

## Known gaps / deliberately deferred

- **Read endpoints have no auth.** There is no router-level/global auth
  dependency — e.g. `GET /api/v1/products` and `download-url` return data to
  anonymous callers (verified: 200 with no token). Writes are RBAC-gated and
  the new artifact `content` endpoint requires a valid token, but read
  gating (§4 열람 권한, ABAC) is unwritten follow-on work, not a small fix.
- ABAC (project/security-classification scoping) is not implemented — RBAC
  only on writes. Fine-grained "who can see which project" is follow-on work.
- No `users` table — identity is Keycloak's JWT claims only, not duplicated
  locally. `created_by`/`actor` fields store the Keycloak username string.
- No AI Copilot (FR-08/S10/M5) — explicitly deferred by the user; every other
  milestone in the original plan is now done. *(Partially un-deferred
  2026-09-13: the M5 section above ships a read+confirm-write assistant.
  Still missing for full FR-08: proactive analysis, artifact generation,
  per-project retrieval.)*
- Docker Desktop is still at ~7.7GB memory allocation. Everything so far runs
  as host processes against dockerized infra (not containerized itself), so
  this hasn't bitten yet — revisit before containerizing apps/workers for M7.
- FMEA/NCR/CAPA (§9.1, S12 Quality screen) not implemented — out of scope for
  the first vertical slice per the plan.
- Only one Gate type ("Virtual Verification Complete") is wired up; the
  other §FR-09 gate stages (Design Ready, Prototype Test Complete, Production
  Readiness) use the same model/endpoints but nothing seeds or drives them.
