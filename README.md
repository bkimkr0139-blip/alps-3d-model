# ALPS ALPINE Engineering Twin Workbench (AA-ETW)

ALPS ALPINE 전자부품 3종(TACT Switch · Rotary Encoder · MEMS Pressure
Sensor)의 **설계 → 시뮬레이션 → 시험 → 승인 → 공정·품질**을 하나의 워크벤치에서
추적하는 엔지니어링 디지털 트윈 PoC.

- **라이브 데모**: https://alps-twin.wizbase.ai.kr (frpc 터널 → 로컬 nginx)
- **데모 데이터**: 전부 합성 데이터이며 화면에 "합성 데이터"로 표기
- **개발 인수인계**: `docs/HANDOFF.md` / **기술 노트·함정 목록**: `AGENTS.md`

## 주요 기능

| 영역 | 내용 |
|---|---|
| 3D Product Twin | 명명 부품 어셈블리 STEP → 부품별 PBR GLB 변환, 부품 클릭 → 요구사항 연동 하이라이트 |
| 시뮬레이션 | SPICE(회로) + 기구 F–S 해석 워커(Temporal 큐), Variant 간 스윕 비교 |
| 시험·상관 | F–S 곡선 CSV 업로드, RMSE/상관계수 산출, 베이스라인 승인, 게이트 워크플로 |
| 모델 신뢰 | 인과관계 그래프·임팩트 패스(human_approved vs ai_inferred), 모델 캔버스, 모델 카드, 규칙 기반 모델 리뷰, UQ(Monte-Carlo 밴드), Gap 분석 |
| 공정 트윈 (TACT P1) | 금형·Cavity 맵, 공정 라우트(Setpoint/Actual 분리·윈도우 플래그), Lot 계보, Lot별 F–S 검사, 불량, MAD 강건 Cavity 비교(Cp/Cpk), 근거형 원인 후보(모두 "확인 필요") |
| 공정 모니터링 (TACT P2) | AN-03 시계열 관리도(강건 관리한계·윈도우 이탈 제외·규칙 위반 3종), AI-03 이상 설명(사실 기반 조사 가설, facts_used 동봉) |
| AI 어시스턴트 | 로컬 Ollama(`qwen2.5:32b`) — 판정 없는 조사 보조, 최종 판정은 사람 승인 |
| 플랫폼 | RBAC 5롤(Keycloak), Append-only 감사로그, Idempotency-Key 멱등 쓰기, i18n(ko/en/ja) |

## 스택

React 19 + TypeScript + Vite · FastAPI(SQLAlchemy + Alembic, 33 테이블) ·
PostgreSQL · Redis · MinIO(S3) · OpenSearch · Temporal · Keycloak ·
nginx · frp · OpenTelemetry/Grafana/Loki/Prometheus · Ollama

## 빠른 시작

```bash
cp .env.example .env   # 실제 비밀번호 채우기 (이 파일은 커밋되지 않음)
make up                # docker compose 스택 + Keycloak realm import
cd apps/api && nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/alps-logs/api.log 2>&1 &
cd apps/web && npm install && npm run dev   # http://localhost:5173
```

데모 데이터 시드(멱등 — 고정 Idempotency-Key, 재실행 시 중복 없음):

```bash
apps/api/.venv/bin/python scripts/seed_golden_dataset.py
```

데모 계정: `demo.architect` / `demo.admin` / `demo.approver` /
`demo.test_engineer` / `demo.mech_engineer` (비밀번호는 Keycloak realm
임포트 파일에 있으며 머신 로컬 전용 — 저장소에 커밋되지 않음).

| 포트 | 서비스 |
|---|---|
| 5173 | Web (Vite) |
| 8000 | API (FastAPI) |
| 5433 | PostgreSQL (호스트 측 — 5432는 로컬 Homebrew와 충돌 회피) |
| 8081 | Keycloak |
| 8090 | nginx 게이트웨이 (web+API+Keycloak 단일 오리진) |

## 테스트 & 검증

```bash
cd apps/api && .venv/bin/python -m pytest            # 77 tests (테스트 DB: {POSTGRES_APP_DB}_test)
cd apps/web && npx tsc -b && npx vite build && npx oxlint
```

브라우저 E2E 패스 스크립트는 저장소 밖 `/tmp/alps-browser-pass/*.mjs`
(Playwright). 모든 마일스톤은 콘솔 에러 0 · HTTP ≥400 0 기준으로 검증됨.

## 저장소 구조

```
apps/
  api/        FastAPI (routers, models, schemas, tests)
  web/        React 19 + TS (3D 뷰어, 벤치, 캔버스, 공정 트윈, i18n)
  workers/    cad-converter (STEP→GLB PBR) · spice-worker · mech-model
db/           Alembic 마이그레이션 (head: b8f2e4a6c7d1)
docs/         개발 지시서 4종 + HANDOFF.md
infra/        docker-compose · Keycloak · nginx · frp · 관측성 · helm
scripts/      seed_golden_dataset.py + STEP 픽스처
tests/        unit / integration / e2e
AGENTS.md     세션별 구현 사실·기술 함정 전체 기록
```

## 개발 문서

| 문서 | 내용 |
|---|---|
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | **세션 인수인계** — 현재 상태, 남은 작업, 병렬 작업 규칙, git 운영 |
| [`AGENTS.md`](AGENTS.md) | 마일스톤별 구현 세부사항과 검증된 함정(gotcha) 목록 |
| `docs/AlpsAlpine_Engineering_Digital_Twin_Workbench_개발지시서_v1.0.md` | 베이스 지시서 (M0–M9) |
| `docs/AlpsAlpine_AI_3D_System_Modeling_고도화_개발지시서_v1.0.md` | 고도화 지시서 (모델 캔버스·리뷰·UQ·Gap) |
| `docs/AlpsAlpine_TACT_Switch_Product_Process_Twin_고도화_개발지시서_v1.0.md` | Product–Process Twin 지시서 (P1 완료) |
| `docs/AlpsAlpine_AirInput_3D_Interaction_Field_Twin_구현지시서_v1.0.md` | 차기 과제 (미착수) |

## 진행 상태

| 단계 | 상태 |
|---|---|
| M0–M6 (인프라·인증·3D·SPICE·시험·상관·게이트) | ✅ 완료 |
| M7 + S04 고도화 + Phase 2~4 (3제품·AI·벤치·트윈 인터랙션) | ✅ 완료 |
| M8 (모델 캔버스·임팩트 패스·모델 카드) | ✅ 완료 |
| M9 (Port Contracts·모델 리뷰·UQ·Gap) | ✅ 완료 |
| TACT P1 (공정 트윈 버티컬 슬라이스) | ✅ 완료 |
| TACT P2 (AN-03 관리도 + AI-03 이상 설명) | ✅ 마이그레이션 프리·읽기 전용 컴퓨팅, 브라우저 패스 CLEAN |
| TACT P2+ (DOE, AI-02, FA/CAPA, 게이트 E2E 등) | ⬜ `docs/HANDOFF.md` §5 참조 (FA/CAPA·AirInput은 병렬 세션 진행 중) |
| AirInput 3D Interaction Field Twin | ⬜ 미착수 |

## 보안 노트

- **커밋 금지 파일** (`.gitignore`): `.env`, `infra/frp/frpc.toml`(frps 토큰),
  `infra/keycloak/realm-export.json`(**alps-twin-api 클라이언트 시크릿 포함**).
  새 클론에서는 각자 준비해야 한다.
- `.env.example`은 플레이스홀더만 포함 (실값 금지).
- 데모 데이터는 합성이며, 실제 고객 설계 데이터·실 MES/QMS 연동은 없다.
- 도메인 금지 규칙(지시서 공통): AI의 최종 합격/원인 판정 금지, 근거 없는
  수치 생성 금지, Baseline/Raw data/감사로그 덮어쓰기 금지 — 세부는
  `docs/HANDOFF.md` §7.
