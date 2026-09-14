# ALPS ALPINE Engineering Twin Workbench — 핸즈오프 문서

> **이 문서의 목적**: 이 저장소에서 개발 세션(사람 또는 Claude)이 맥락 없이
> 병렬로 작업을 이어받을 수 있도록 현재 상태·실행 방법·규칙·남은 작업을 한
> 문서에 정리한다. 최종 갱신: 2026-09-14 (M9 + TACT P1 완료 시점).

---

## 1. 이 프로젝트는 무엇인가

ALPS ALPINE 공학용 디지털 트윈 워크벤치(AA-ETW). 제품 3종(TACT Switch,
Rotary Encoder, MEMS Pressure Sensor) × A/B Variant에 대해 요구사항 → 3D
모델 → 시뮬레이션(SPICE/기구) → 시험 → 상관 → 게이트 승인 → 공정(Lot/
금형/Cavity)까지 하나의 화면에서 추적한다.

- **라이브**: https://alps-twin.wizbase.ai.kr (frpc 터널 → 로컬 nginx :8090)
- **개발 지시서** (docs/ 아래, 우선순위 순):
  1. `AlpsAlpine_Engineering_Digital_Twin_Workbench_개발지시서_v1.0.md` — 베이스 (M0~M9 완료)
  2. `AlpsAlpine_AI_3D_System_Modeling_고도화_개발지시서_v1.0.md` — 고도화 (완료)
  3. `AlpsAlpine_TACT_Switch_Product_Process_Twin_고도화_개발지시서_v1.0.md` — Product–Process Twin (**P1 완료, P2 이후 미구현**)
  4. `AlpsAlpine_AirInput_3D_Interaction_Field_Twin_구현지시서_v1.0.md` — **P1(vertical slice) 완료, 나머지 미구현**
- **상세 기술 노트**: 루트 `AGENTS.md` — 마일스톤별 구현 사실·함정(gotcha)·
  시드 데이터 이야기가 모두 기록되어 있다. **작업 전 반드시 읽을 것.**

## 2. 스택 & 실행

| 구성 | 위치/포트 | 비고 |
|---|---|---|
| Web | `apps/web`, Vite dev :5173 | React 19 + TS, i18n ko/en/ja |
| API | `apps/api`, :8000 | FastAPI, venv는 `apps/api/.venv` |
| DB | PostgreSQL :5433 | docker `alps-twin-postgres-1`, user `alps`, db `alps_twin` |
| Keycloak | :8081 (realm `alps-twin`) | 공개 경유 경로는 `/realms/`, `/resources/` 만 |
| nginx 게이트웨이 | :8090 | web+API+Keycloak 단일 오리진 |
| frpc | infra/frp | `frpc -c infra/frp/frpc.toml` (토큰은 로컬 전용) |
| MinIO | docker :9000 | 아티팩트(S3) |
| AI | 로컬 Ollama `qwen2.5:32b` | 어시스턴트 패널 |

```bash
# 전체 스택 기동 (첫 실행 시 .env 필요 — .env.example 참조, 실값은 이 머신의 .env)
make up            # repo 루트에서. docker compose 기동 + keycloak realm import
cd apps/api && nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/alps-logs/api.log 2>&1 &
cd apps/web && npm run dev
```

- API **코드를 고친 뒤에는 반드시 재시작** (uvicorn --reload 아님).
- 로그는 반드시 `/tmp/alps-logs/` 아래에. bare `/tmp/*.log` 금지.
- **프로세스 종료 금지 규칙**: `pkill -f` 느슨한 패턴 절대 금지 — 다른
  프로젝트 서비스가 같은 머신/같은 frps를 공유한다. 정확한 PID만:
  `kill $(lsof -nP -iTCP:8000 -sTCP:LISTEN -t)`

## 3. 검증 루틴 (커밋/보고 전 필수)

```bash
cd apps/api && .venv/bin/python -m pytest            # 67 tests (M9 56 + P1 11)
cd apps/web && npx tsc -b && npx vite build && npx oxlint
```

브라우저 패스: `/tmp/alps-browser-pass/*.mjs` (Playwright, headless
chromium). 패턴: realm-export.json에서 demo.architect 비밀번호 읽기 →
로그인 → product select = `selects.nth(1)`(nth(0)은 언어), variant =
`nth(2)` → 탭은 `getByRole("heading", ...)`. 종료 시 consoleErrors /
pageErrors / badResponses(≥400) 전부 0 = **CLEAN**. 스크린샷도 같은 디렉터리.
예시: `p1-pass.mjs` (공정 트윈 탭), `m9-pass.mjs` (모델 리뷰/UQ/Gap).

## 4. 완료된 마일스톤 (전부 브라우저 CLEAN 검증 완료)

| 단계 | 내용 |
|---|---|
| M0~M5 | 인프라, 인증(RBAC 5롤), 요구사항·추적, CAD→GLB 변환(부품별 PBR), SPICE/기구 시뮬 워커, 아티팩트 버전링 |
| M6 | 시험 데이터 업로드(CSV), 상관(RMSE/상관계수), 베이스라인, 게이트 승인 |
| M7 | i18n(ko/en/ja), S04 3D 고도화(7부품 어셈블리·환경광), Phase 2~4: 제품 3종, AI 어시스턴트(로컬 Ollama), 테스트 벤치/스코프 |
| M8 | 모델 캔버스, 임팩트 패스, 모델 카드, 벤치 F–S 커서 |
| M9 | Port Contracts(unit_dimension·check_link_units), Model Review(규칙 기반 findings), UQ lite(Monte-Carlo 밴드), Gap 분석 |
| **TACT P1** | **공정 트윈**: 금형 1식·Cavity 2개, 공정 라우트(Setpoint/Actual 분리·윈도우), Lot 계보, Lot별 F–S 검사, 불량, Cavity 비교(AN-02/03, MAD 강건 통계), 근거형 원인 후보(AI-01), 신규 웹 탭 "공정 트윈 (TS03~05)" |
| **AirInput P1** | **AirInput 감지 체인 vertical slice**: 4번째 제품군(PROD-AIRINPUT-SENSOR, Electrode Layout A/B), `model_type=proximity_capacitance`로 ΔC(d) 정전용량 근사 + ASIC 카운트/임계값 판정 요약 지표(`max_reliable_distance_mm`)까지 기존 mech-model 분석 dispatch에 4번째로 추가. 신규 3D 감지공간·ASIC/Algorithm 엔터티·SPICE·Gate는 의도적으로 미구현(AGENTS.md 참조) |

마이그레이션 head: `b8f2e4a6c7d1` (33 테이블). 테스트 67개 전부 통과.
최종 시드: `process-twin: mold=MOLD-TACT-01 cavities=2 operations=3 lots=4`.

## 5. TACT 지시서 남은 작업 (병렬 작업 후보)

§12 16주 일정 기준, P1이 "3~9주 + AI/품질의 일부"에 해당. 남은 것:

1. **AN-04 DOE·최적화** — 공정 인자(dome_thickness 등) → CTQ 반응표면,
   P1의 process_runs/검사 데이터를 재사용 가능.
2. **AI-02 변경 영향분석** — 설계/공정 변경이 CTQ·요구사항에 미치는 영향
   전파(모델 캔버스 임팩트 패스와 연계).
3. **AI-03 공정·품질 이상 설명** — 원인 후보를 Ollama로 설명 생성(단,
   숫자 생성 금지·check_required 유지).
4. **Defect/FA/CAPA 워크플로** — Defect 엔터티는 있음. FA(불량분석)·CAPA
   상태 기계와 승인 흐름이 없음.
5. **재검증 → Release Gate E2E** — 원인 후보 → 재검증 시험 → 게이트 근거
   연결 (P1은 후보 표시까지만).
6. **관리도(Control chart)** — AN-03의 Cp/Cpk까지만 구현, 시계열 관리도 없음.
7. **AirInput 지시서** — ~~별도 신규 과제, 미착수~~ **P1(vertical slice) 완료**
   (2026-09-14): `model_type=proximity_capacitance` (ΔC(d) 근사 + ASIC 카운트/
   임계값 판정 요약), Product/Variant A·B, 상관 검증까지. 나머지(3D 감지공간/
   Dead Zone/Trajectory Replay, ASIC/Algorithm 엔터티, Robot scan import,
   AI01–AI12 화면, Gate)는 여전히 미구현 — AGENTS.md "AirInput vertical
   slice" 절 참조.
8. **성능·보안·복구·일본어 QA, KPI 실증** — §12 15~16주.

## 6. 병렬 작업 규칙 (반드시 준수)

1. **한 파일은 한 세션만**: 같은 파일 동시 수정 금지. 작업 시작 전
   `git pull`, 종료 시 커밋→푸시로 짧게 동기화한다.
2. **DB 마이그레이션**: `db/migrations/versions/` 에 alembic revision 추가.
   head가 2개가 되지 않게 — 작업 직전 `alembic heads` 로 확인.
3. **테스트 DB**: pytest는 `alps_twin_test` 를 truncate한다. 개발 DB
   `alps_twin` 을 향하지 않게 conftest를 건드리지 말 것.
4. **시드 재실행**: `scripts/seed_golden_dataset.py` 는 멱등(fixed
   Idempotency-Key). 재실행해도 중복 없이 append만. 단, **API가 최신 코드로
   떠 있어야 한다** (구버전 API + 신규 Read 스키마 = 500, 아래 §8 참조).
5. **시크릿**: `.env`, `infra/frp/frpc.toml`,
   `infra/keycloak/realm-export.json`(alps-twin-api 클라이언트 시크릿 포함)은
   gitignore — 절대 커밋 금지. 데모 계정 비밀번호(demo1234)는 공개 데모용이라
   시드 스크립트에 하드코딩되어 있음(의도).
6. **게이트/승인 금지**: 공개 데모 데이터 위에서 브라우저로 APPROVE 버튼을
   누르지 않는다(시드 스크립트의 API 호출만 예외).

## 7. 도메인 규칙 (지시서 금지 조항 — 위반 시 리젝)

- 실제 MES/QMS/설비에 무승인 Write 금지 (데모는 전부 합성 데이터, 화면에
  "합성 데이터" 표기 유지).
- **AI는 합격/출하/원인의 최종 판정을 내리지 않는다** — 원인 후보는 항상
  `confidence="check_required"` (확인 필요) + 근거(evidence) 첨부.
- 실제 생산 기록은 FACT: 윈도우 이탈 공정은 거절이 아니라
  `out_of_window` 플래그 + `window_findings` (시뮬레이션 차단과 구분).
- 상관을 인과로 단정 금지. 승인 Baseline/Raw data/감사로그 덮어쓰기 금지.
- 시뮬레이션 숫자·물성·공차·규격값 임의 생성 금지 (데모 스펙 밴드는
  "데모 사양·합성 데이터"로 출처 표기).
- Calibration/Validation 데이터 혼용 금지. 유효범위 밖 예측 정상 표시 금지.
- AI-inferred 관계는 승인 전까지 Gate Evidence 불가.

## 8. 자주 터지는 함정 (상세는 AGENTS.md 각 마일스톤 절)

- **idempotent_write는 생성 시점 응답 본문을 캐시**한다. Read 스키마에
  새 필수 필드를 추가하면 오래된 캐시 리플레이가 500이 된다 → 새 Read
  필드는 `= None` 기본값 (P1의 `TestRunRead.lot_id` 사례).
- Alembic enum: 컬럼 복사 시 `ENUM.copy()` + `create_type=False`.
  SQLAlchemy는 enum **이름**(대문자 라벨)을 저장.
- FastAPI 신버전 `app.routes`는 `_IncludedRouter` 로 경로가 안 보인다 →
  `TestClient(app).get("/openapi.json").json()["paths"]` 로 검증.
- RBAC: 테스트런/검사 플랜 생성은 ARCHITECT 불가 → 테스트는
  `as_user(client, MECH_ENGINEER)`.
- 통계 규칙은 MAD 강건 통계(σ=1.4826·MAD): 일시 이상과 반복 편차 구분이
  지시서 요구(AN-02). 단순 mean/sd 규칙으로 되돌리지 말 것.
- 웹: 중앙 탭은 App.tsx의 h3 배열, 로케일 타입은 en.ts가 정의
  (`Resources = typeof en`) — ko/ja에 키 추가 시 en에도.
- oxlint: effect 안 동기 setState 금지 → `key` 기반 remount로 해결.

## 9. git 운영

- 원격: `https://github.com/bkimkr0139-blip/alps-3d-model` (main).
- 커밋 메시지 끝에 `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
- 커밋 전 `git status` 로 시크릿 파일이 스테이징되지 않았는지 확인.
- 커밋 단위: 마일스톤/기능 단위로. 푸시는 세션 종료 시 또는 의미 있는
  검증(CLEAN) 통과 시점에.

## 10. 세션 시작 체크리스트

1. `git pull` → `AGENTS.md` + 이 문서 읽기
2. 스택 상태 확인: `curl -s localhost:8000/healthz`, `docker ps | grep alps`
3. 작업 브랜치/범위를 이 문서 §5에서 선택, §6 규칙 준수
4. 완료 후: pytest + tsc/vite/oxlint + 브라우저 패스 → 커밋/푸시 →
   AGENTS.md에 마일스톤 절 추가, 이 문서의 상태 갱신
