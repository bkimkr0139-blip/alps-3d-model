# ALPS ALPINE Engineering Twin Workbench — 핸즈오프 문서

> **이 문서의 목적**: 이 저장소에서 개발 세션(사람 또는 Claude)이 맥락 없이
> 병렬로 작업을 이어받을 수 있도록 현재 상태·실행 방법·규칙·남은 작업을 한
> 문서에 정리한다. 최종 갱신: 2026-09-16 (UI/UX 3D-트윈 퍼스트 고도화 완료 —
> 사용자 브라우저 테스트 대기 중, **아래 §0 핸드오프 상태 먼저 읽을 것**).

## 0. 지금 세션 핸드오프 상태 (2026-09-16, 다음 세션이 먼저 읽을 것)

**UI/UX 3D-트윈 퍼스트 고도화 완료** — 사용자 지시("텍스트·숫자 위주 대신
실제 제품·부품·장비의 3D 디지털 트윈을 보고 체험하고 활용하는 화면으로")에
따른 전면 개편. 계획 파일
`~/.claude/plans/cosmic-riding-phoenix.md`의 W1~W6 전부 완료 + 실행 중
사용자 추가 지시 2건(공정 트윈 실사화, ASIC ⑤ 단계 템플릿별 패키지 모델)
까지 반영. **커밋은 로컬 `main`에만 있음 — push는 사용자가 직접**:
`cd /Users/wizbase/works/alps && git push` (classifier가 main push 차단).

이번 세션 커밋 (전부 웹 프론트, 라이브 스택 = vite dev :5173 → :8090 프록시에
즉시 반영, 게이트 전부 통과: tsc/vite 빌드 + oxlint 27 warnings 베이스라인 +
verify:seedl10n 101/0 + Playwright 헤드리스 CLEAN):

1. `57b262c` **W1** 디자인 토큰(`ui/tokens.ts`)+공유 UI 키트(`ui/kit.tsx` —
   HudPanel/HudChip/StatusBadge 등 캔버스 오버레이 패밀리 포함).
2. `07273ed` **W2** 3D 콕핏 셸 — model 탭이 풀폭 3D 첫 화면, HUD 스트립
   (게이트·런·요구 연동 칩), 좌우 패널은 글래스 드로어(`ui/GlassDrawer.tsx`)
   로 전환. 하단 sweep/correlation/gate/assistant 섹션 유지.
3. `5e82de0` **W3** 공정 라인 3D 트윈 — proc 탭에 FactoryViewer(순수 데이터
   레이어 `proc/factoryScene.ts` + 뷰어): 스테이션 상태는 관리도 데이터에서
   산출(in_control/rule_hit/excluded/idle), 클릭 시 기존 관리도 드로어,
   컨베이어 = Lot 타임라인. `ui/canvasText.ts` 추출.
4. `05e8dd1` **W4** 장비 트윈 — 벤치 HUD(DUT 칩·SPICE 출처·스코프 RUN/STOP,
   CH1/CH2 LED 베젤), ASIC 장비 런 랙 스트립(교정 카운트다운 바).
5. `a9d1071` **W5** 부품 선택 동기(지시서 L187) 완결 + FR-03 검토 도구 —
   model 탭 "검토" 툴바(단면 클리핑/2점 측정 mm/핀 주석 ◈로컬), 벤치 DUT가
   3D 선택 부품 종류와 매칭될 때만 하이라이트.
6. `4ec4d3b` **W3b** 공정 트윈 실사화(사용자 지시 "만화 같은 애니메이션 말고
   실사 환경수준") — 스테이션별 실제 장비 실루엣(프레스 프레임/사출성형기/
   로봇 조립 셀), 관리도 기반 안등(signal tower), 콘크리트 바닥+안전 레인
   라인+천장 조명+안개, 컨베이어 벨트+토트(처분색 띠), 기기명판. 데이터
   레이어(factoryScene.ts) 불변.
7. `cfa72f2` **ASIC ⑤ Package/3D Twin 템플릿·옵션별 모델**(사용자 지시) —
   `asic/packageScene.ts`가 ② 단계 선택 옵션의 pkg 문자열을 파싱해 패키지
   패밀리별 실루엣 생성: QFN(랜드+epad)·WLCSP(범프+RDL, 와이어 없음)·LGA·
   SOIC/SOP/TSSOP(양측 gull-wing 리드)·LQFP(4측), 몸체 비례·인덱스 노치·
   pin1 점. 다이 레벨은 템플릿 고유 센서(MEMS 스택 vs GMR+coil) 유지.
   계보 문자열·섹션 칩이 모델링된 pkg를 표시.
8. `1d57f6f`+`2fa26e5` **패키지 내부 구조 산업 표준 정합**(사용자 지시 — 분해도/
   mold-off에서 핀이 칩·센서 위에 뿌려진다는 보고 + "핀에 연결된 와이어로") —
   3결함 수정 + 와이어 실사화: (a) 본드 맵 재작성 — 핑거가 다이 주변 무어트에
   링을 이루고 와이어는 같은 변의 다이 패드↔핑거 1:1 부채꼴(QFN은 z/x 행 교차
   vs S/N 패드 순서라 와이어 절반이 다이를 가로질렀고, LGA는 랜드 그리드 좌표를
   써서 핑거가 다이 위에 놓임), 패드는 와이어 수만큼만 렌더; (b) 센서 배치 —
   QFN/WLCSP는 MEMS를 다이 위 모놀리식 적층, LGA는 별도 MEMS 다이+전용 패드
   와이어본딩, 협소 SOIC/SOP/TSSOP는 GMR을 다이 위 공동집적(기존엔 다이 발찌와
   겹쳐 파묻힘+공중 와이어); (c) `explodeAnchors`(EdaScene 선택 필드)로 분해
   레이어 케이크가 단면 순서(PCB→solder→package→die→bond→sensor→mold→mark)로
   분리; (d) 와이어=가는 Au 튜브(0.12, 오버랩 샘플링으로 연속 호)+패드 볼본드+
   핑거 스티치본드, 내부 핑거 팁은 외부 리드와 같은 은도금 구리(LEAD), LGA만
   ENIG 금. 검증: pkg_internals_e2e(mold-off+explode 스크린샷 A/B/D)·pkg_e2e·
   eda_e2e CLEAN.
9. `81f44d6` **EDA 교육 미션을 자사 제품 실리콘으로**(사용자 지시) — 교육용 5칩
   (4비트 카운터/ALU/FIFO/UART/RISC)을 앱 ASIC 9단계 시나리오 칩셋으로 재테마:
   TACT 스위치 채터링 필터(tact_debounce4)·터치 스냅 판정 ALU(touch_alu4)·
   AFE 샘플 링버퍼 FIFO(afe_sample_fifo)·센서값 UART 송신기(sensor_uart_tx)·
   AFE/SoC 제어 RISC 코어(afe_soc_core). 난이도 사다리·휴리스틱 엔진 불변
   (포트/신호명 유지 — 파형/시나리오/STA 프리셋 그대로 적용), topModule은
   MISSIONS+SIGNAL/SCENARIO/criticalPath 프리셋 맵에 반영, 스타터 RTL 헤더에
   제품 블록 명시, ko/en/ja 표시명·설명 교체. eda_e2e 셀렉터 갱신.
10. `71e25a1` **EDA 3D 씬 3종을 선택 제품 칩으로**(사용자 지시 "웨이퍼/설계
   결과물이 동일 샘플이면 안 된다") — 공정(웨이퍼→FEOL→BEOL)·합성(게이트
   클러스터)·레이아웃(층 케이크) 빌더가 전부 `silProfileOf(slug)` 실리콘
   프로파일을 따름: 미션별 다이 크기(TACT-DB4 9.5×7.0 순디지털 ~ AFE-SOC1
   15×11), 레이아웃 매크로=실기능 블록(DEBCNT/TOUCH_AFE/RING_RAM/TX_SHFT/
   RISC_CORE/SRAM32K…), 플로어플랜 슬라이더가 미션 전환 시 제품 다이 기본값
   세팅, 합성 바닥=다이 종횡비+혼성신호 미션은 AFE 아일랜드(하드매크로+MIM
   캡+가드링, near 코너), 공정 흐름=리티클 필드 2×2 반복+딥 n웰/MIM캡/폴리
   저항/실드 링+메모리 셀 어레이+비트라인+터치 전극 콤+패드 링 제품별 수.
   캔버스 HUD에 "◈ 트윈 대상 칩: 칩코드 · topModule · gates" 표기(i18n 3
   로케일 `eda.view3dChip`). 미지 slug는 구 제네릭 샘플 유지. 검증:
   eda_e2e(TACT-DB4 무아날로그 vs TCH-ALU4 analog 칩 단정 추가)+
   eda_sil_e2e(SoC/FIFO/UART 공정·레이아웃 스크린샷)+w6_sweep CLEAN.

**검증 스크립트**(`/tmp/alps-logs/`, 전부 PASS): cockpit_e2e(W2),
proc_e2e/proc_mobile_e2e(W3), bench_e2e(W4), review_e2e(W5), w6_sweep(8탭
ko + en/ja 스모크 + 390×844 모바일), pkg_e2e(템플릿 A~D × ⑤단계 캔버스+
pkg 칩 + B OPT-2 → TSSOP-16 재표적), pkg_internals_e2e(⑤ mold-off+분해도
0.45 스크린샷 A/B/D — 내부 구조 육안 검증용), eda_sil_e2e(EDA 미션별
공정·레이아웃 3D 스크린샷 FIFO/UART/SoC — 71e25a1 육안 검증용).

**다음 세션(또는 사용자)이 할 일**:
- **`git push`** (사용자 직접 실행 필요, 위 참조) + **웹 브라우저 검증** —
  사용자가 "완성하면 내가 웹으로 검증해볼게"라고 한 상태. model 탭 첫 화면,
  proc 탭 실사 라인, ASIC 탭 템플릿별 ⑤단계 모델 위주.
- **Temporal 좀비 워크플로 정리** — 이전 세션에 1개만 terminate되고
  ~111개 Running이 남아 있음(재시드로 sim_run 행은 없는데 재시도만 반복).
  사용자가 터미널에서 직접:
  `! docker exec alps-twin-temporal-1 temporal workflow delete --query "ExecutionStatus='Running'" --address 172.22.0.10:7233 --namespace default --reason "zombie: sim_run rows wiped by reseed"`
- 남은 별개 과제(이 세션 범위 아님): TACT AI-02 변경 영향분석, AirInput
  나머지 위상, `seed_airinput_field_twin` UUID 직렬화 버그(선존재).
- 주의: 캔버스 중앙 클릭은 모델을 빗나갈 수 있음(클릭 사다리 사용),
  `drei <Html>` 금지 관례, 검토 툴바 닫기가 mode를 off로 되돌림(W5 참조).

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
cd apps/api && .venv/bin/python -m pytest            # 175 tests (ASIC R3 포함) — 병렬 세션 공유 시 POSTGRES_APP_DB=alps_twin_pm 로 격리
cd apps/web && npx tsc -b && npx vite build && npx oxlint
cd apps/web && npm run verify:seedl10n               # seedL10n 한글 누출 검증기 (DB+라이브 API → en/ja 잔여 한글 0) — API:8000·DB:5433·Keycloak:8081 기동 필요
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
| **FA/CAPA** | **Defect→FA→CAPA 워크플로** (§5 항목 4, TS10): FailureAnalysis(사람이 입력하는 근거 기반 원인, AI 결론 아님) + CAPA 상태기계(draft→pending_review→approved/rejected→implemented→effectiveness_verified→closed, Gate와 동일 RBAC), append-only CapaEvent 이력, 효과검증은 실제 TestRun 연결(자유 텍스트 금지) |
| **AN-04** | **DOE·최적화**: `ProcessRun.actual`(기존 P1 데이터) 재사용 선형 반응표면 회귀(sensitivity), 승인 윈도우 기반 제약 위반 표시, 관측값+그리드 후보안 순위 비교, `doe_studies` 신규 엔티티(감사 가능 결과 저장), `proc` 탭 내 DOE 패널 |
| **AirInput P1** | **AirInput 감지 체인 vertical slice**: 4번째 제품군(PROD-AIRINPUT-SENSOR, Electrode Layout A/B), `model_type=proximity_capacitance`로 ΔC(d) 정전용량 근사 + ASIC 카운트/임계값 판정 요약 지표(`max_reliable_distance_mm`)까지 기존 mech-model 분석 dispatch에 4번째로 추가. 신규 3D 감지공간·ASIC/Algorithm 엔터티·SPICE·Gate는 의도적으로 미구현(AGENTS.md 참조) |

마이그레이션 head: `a9f9769ac53e` (FA/CAPA `8aaac1ba4a8b`와 AN-04 `f361e9578062`가
둘 다 `b8f2e4a6c7d1` 위에서 분기해 병합 직후 head가 2개였다 — `alembic merge`로
병합 리비전을 추가해 단일 head로 정리함; AirInput은 신규 테이블 없음).
테스트 **95개 전부 통과** (67 기존 + 8 FA/CAPA + 13 AN-04 + 7 AirInput), `tsc -b`/
`vite build`/`oxlint` 전부 clean — 3건 병합 후 재검증 완료.
최종 시드: `process-twin: mold=MOLD-TACT-01 cavities=2 operations=3 lots=4` + FA 1건·CAPA 2건(1건 종결+효과검증, 1건 승인 상태) + `doe: DOE-TACT-A-OP10-dome_thickness (dome_thickness_mm vs F-S peak, 4 observations)` + `PROD-AIRINPUT-SENSOR` Variant A/B.

**P2 추가 (2026-09-14, 이 세션)** — AN-03 관리도 + AI-03 이상 설명 완료.
마이그레이션 없음(읽기 전용 컴퓨팅). 테스트 105개 전부 통과(95 + P2 10).
브라우저 패스 CLEAN. 상세: AGENTS.md "TACT P2" 절. 시드에
`process-monitoring: lots=6 added (LOT-TACT-A-05..10)` 추가.

**S04 뷰어 수정 + AirInput 3D CAD + 분해도 시뮬레이션 (2026-09-14 저녁,
이 세션, 로컬 main만·미push — 위 §0 참조)** — 카메라 각도/회전 시 투명화
버그(전 제품 공유 버그)/바디 X-ray 슬라이더, AirInput 8-part 3D 모델
신규 제작(변형별 진짜 다른 지오메트리), 분해도 조립 시뮬레이션 신규
기능, 스테일 TACT fixture + idempotency 캐시로 인한 재변환 누락 발견·
수정. 마이그레이션 없음. pytest 105 전부 통과, tsc/vite/oxlint clean —
**브라우저 라이브 검증은 아직 없음**. 상세: AGENTS.md "S04 viewer
fixes", "AirInput vertical slice", "Stale STEP fixtures + exploded-view"
절.

**ASIC Twin v1.1 R1+R2+R3 (2026-09-15~16, R1+R2는 push 완료 `8af4a5e`,
R3는 로컬 — 위 §0 참조)** — ASIC 공동설계 루프 전체: R1 센서 신호체인
9테이블 + 게이트 정책 `alps-asic-v1.1` + Readiness 6단계, R2 trade
study/EDA ToolRun/테스트 프로그램 트윈/공급망/3개 언어 증적 보고서,
R3 가정 레지스터·영향 스캔·편차·게이트 연동(EPIC I) + 규칙 기반
근거-바운드 copilot 7 유스케이스 + shadow evaluation(EPIC J). pytest
175 전부 통과, `verify:seedl10n` 잔여 한글 0. 브라우저 패스는 사용자가
직접. 상세: AGENTS.md "ASIC v1.1 R2", "ASIC v1.1 R3" 절.

## 5. TACT 지시서 남은 작업 (병렬 작업 후보)

§12 16주 일정 기준, P1이 "3~9주 + AI/품질의 일부"에 해당. 남은 것:

1. ~~**AN-04 DOE·최적화**~~ — **완료** (branch `feature/an04-doe-optimization`):
   공정 인자(dome_thickness_mm) → CTQ(F–S peak) 선형 반응표면 회귀 + 후보안
   비교, `doe_studies` 신규 엔티티, `proc` 탭에 패널 추가. 상세는 §4 표와
   AGENTS.md "AN-04 DOE / optimization" 절 참조.
2. **AI-02 변경 영향분석** — 설계/공정 변경이 CTQ·요구사항에 미치는 영향
   전파(모델 캔버스 임팩트 패스와 연계).
3. ~~**AI-03 공정·품질 이상 설명**~~ — **완료** (TACT P2, 이 세션):
   관리도 사실 시트 → Ollama 조사 가설, `facts_used` 동봉, 숫자 생성 금지
   시스템 프롬프트. AGENTS.md "TACT P2" 절 참조.
4. ~~**Defect/FA/CAPA 워크플로**~~ — **완료** (`feature/fa-capa-workflow`
   브랜치, 위 §4 표 참고). FailureAnalysis + CAPA 상태기계·승인 흐름·
   append-only 이력 구현됨. 남은 것: 브라우저 CLEAN 검증, 라이브 재시드
   (병렬 작업 종료 후 중앙에서 수행), CAPA 제출 시 root_cause_confirmed
   증적 게이트(Gate의 §12.2 패턴 미적용), 독립성(제출자≠결정자) 체크 없음.
5. **재검증 → Release Gate E2E** — 원인 후보 → 재검증 시험 → 게이트 근거
   연결 (P1은 후보 표시까지만). CAPA 종결 단계의 좁은 범위(TestRun 연결)는
   위 FA/CAPA 항목에서 구현됨 — 이 항목은 Gate 자체와의 전체 연계가 남음.
6. ~~**관리도(Control chart)**~~ — **완료** (TACT P2, 이 세션): 강건 관리한계
   (median ± 3·1.4826·MAD, 규격한계 아님), 윈도우 이탈점 산정 제외(사유
   감사 가능), 규칙 위반 3종. AGENTS.md "TACT P2" 절 참조.
7. **AirInput 지시서** — ~~별도 신규 과제, 미착수~~ **P1(vertical slice) 완료**
   (2026-09-14): `model_type=proximity_capacitance` (ΔC(d) 근사 + ASIC 카운트/
   임계값 판정 요약), Product/Variant A·B, 상관 검증까지. **3D CAD 모델도
   같은 날 저녁 세션에 추가 완료**(8-part 어셈블리, 변형별 진짜 다른
   지오메트리 — 위 §4 "S04 뷰어 수정 + AirInput 3D CAD" 참조). 나머지(Dead
   Zone/Trajectory Replay, ASIC/Algorithm 엔터티, Robot scan import,
   AI01–AI12 화면, SPICE, Gate)는 여전히 미구현 — AGENTS.md "AirInput
   vertical slice" 절 참조.
8. **성능·보안·복구·일본어 QA, KPI 실증** — §12 15~16주.

## 6. 병렬 작업 규칙 (반드시 준수)

1. **한 파일은 한 세션만**: 같은 파일 동시 수정 금지. 작업 시작 전
   `git pull`, 종료 시 커밋→푸시로 짧게 동기화한다.
2. **DB 마이그레이션**: `db/migrations/versions/` 에 alembic revision 추가.
   head가 2개가 되지 않게 — 작업 직전 `alembic heads` 로 확인.
3. **테스트 DB**: pytest는 `{POSTGRES_APP_DB}_test` 를 drop/create한다.
   개발 DB `alps_twin` 을 향하지 않게 conftest를 건드리지 말 것. **병렬
   세션이 같은 테스트 DB를 쓰면 스키마가 섞여 drop_all이 실패한다** —
   이 세션은 `POSTGRES_APP_DB=alps_twin_pm pytest` 로
   `alps_twin_pm_test` 에 격리해서 돌린다(사례: fa-capa 세션의 capas FK가
   `alps_twin_test` 의 drop을 막음).
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
- **병렬 worktree가 같은 `alps_twin_test`에 서로 모르는 테이블을 추가하면**
  `conftest.py`의 세션 단위 `drop_all()`이 `DependentObjectsStillExist`로
  깨질 수 있다(예: AN-04 작업 중 다른 브랜치의 CAPA 테이블과 충돌). 상대
  브랜치 테이블을 지우지 말 것 — 자신의(추적 안 되는) `.env`에서
  `POSTGRES_APP_DB`를 임시로 다른 이름으로 바꿔 격리된 테스트 DB를 쓰는 것이
  안전하다. 상세: AGENTS.md "AN-04 DOE / optimization" 절.

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
