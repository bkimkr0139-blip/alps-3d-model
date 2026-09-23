# ALPS ALPINE Engineering Twin Workbench — 핸즈오프 문서

> **이 문서의 목적**: 이 저장소에서 개발 세션(사람 또는 Claude)이 맥락 없이
> 병렬로 작업을 이어받을 수 있도록 현재 상태·실행 방법·규칙·남은 작업을 한
> 문서에 정리한다. 최종 갱신: 2026-09-23 (시스템 문서 플랫폼 관리자 전용
> 게이트 — **아래 §0 핸드오프 상태 먼저 읽을 것**).

## 0. 지금 세션 핸드오프 상태 (2026-09-23, 다음 세션이 먼저 읽을 것)

**시스템 문서 탭 플랫폼 관리자 전용 게이트(사용자 지시 "시스템 문서는
admin/admin123@ 로 로긴하면 보이게")** — 역할 기반 설계: `App.tsx`가 토큰
`realm_access.roles`의 `platform_admin`으로 `isAdmin` 판정, DOCS 네비 그룹
(디바이더+System Docs 탭)을 관리자 세션에서만 렌더. username 매칭이 아니라서
새 관리자는 Keycloak에서 platform_admin 롤만 부여하면 된다. 데모 계정 중
문서 보이는 계정: `admin`, `demo.admin`(둘 다 platform_admin — 신설 admin은
gitignored `infra/keycloak/realm-export.json`에도 반영해 배포 패리티 유지).
시스템 문서 v1.1→v1.2(2026-09-23): 3 로케일 버전·날짜 행 + 도입부 "관리자
로그인 시 표시" 문구 + §3.11 관리자 전용 불릿, `SystemDocs.tsx` 다운로드
파일명 v1.2.

- **디버그 교훈(재발 방지)**: 첫 검증에서 탭이 안 보였던 원인은 앱이 아니라
  **라이브 realm에 platform_admin 롤 매핑이 실제로는 없었던 것** — kcadm
  `role-mappings/realm` 확인을 "available" 목록으로 대신해 오판. 또 kcadm을
  docker exec bash -s로 돌릴 때 `UID`는 bash 읽기전용 변수라 사용자 id 조회가
  조용히 실패(AUID 등 다른 이름 사용). 토큰 클레임 확정은 ROPC가 가장 빠름:
  `curl .../openid-connect/token -d grant_type=password -d client_id=alps-twin-web
  -d username=admin --data-urlencode "password=..."` → JWT payload 2번째
  세그먼트 base64url 디코드(토큰 자체는 출력 금지, 클레임만).
- **검증**: 빌드 + oxlint 베이스라인 이하 + Playwright
  `/tmp/alps-logs/docs-admin-check.mjs` 9항목 ALL PASS — demo.architect 탭
  숨김/네비 정상/pageerror 0, admin 탭 표시+v1.2 렌더+다운로드 v1.2+모델 탭
  회귀+pageerror 0, 스크린샷 육안 대조.

**AXOS 피드백 폐루프 1회전 완주(FB-0001 — 승인→지시서→구현→complete)** —
`feedback/FB-0001.json`(브라우저 검증 건, "3D 뷰어 초기 카메라가 측면이라 주요
형상 확인이 어렵다")을 실제 과제로 소비했다:

- **승인/착수**: `feedback.py approve FB-0001 --by bkimkr0139-blip --org "ALPS
  ETW"` → `dev_queue/FB-0001.md` 지시서 자동 생성 → `start` 착수.
- **구현** — S04(model 탭) 3D 뷰어 카메라:
  (a) 기본 시점을 정면 3/4 뷰로 교체(`ThreeViewer.tsx` DEFAULT_CAM_POS
  `[7,9,9]`, 고도 ~38° — 구값 `[6,11,8]`은 고도 ~48°라 수직 상부 룩이었음.
  후보 A `[8,7,10]`은 AirInput 납작 슬라브가 읽히지 않아 기각, TACT·엔코더·
  MEMS·AirInput 4제품 스크린샷 비교로 선정).
  (b) **카메라 저장/복원** — `SavedCamera`(Bounds 자식, useBounds)가
  OrbitControls `end`에서 제품(버전 집합)별 localStorage
  `alps.s04-cam.<sceneKey>`에 시점 기록, 다음 진입 시 `moveTo().lookAt()`으로
  fit goal을 덮어써 복원(Bounds의 ~1초 트윈이 저장 시점으로 이어짐 — 사용자
  드래그 개입 시 Bounds 'start' 리스너가 끊으므로 사용자 항상 우선).
  (c) **기본 시점 버튼** — TwinControls "기본 시점으로"(store
  `viewResetNonce` 카운터로 연타도 매번 발화): 저장본 삭제 + `api.reset()`으로
  기본 방향 리핏. i18n 3 로케일 `twin.viewReset` 신설.
- **검증**: tsc/vite 빌드 + oxlint 27 warnings 베이스라인(수정 파일 0) +
  verify:seedl10n 101/0 + Playwright `/tmp/alps-logs/fb0001-check.mjs` 7항목
  ALL PASS(진입시 저장키 없음→드래그 저장→pose 유한수→리로드 복원→기본 시점
  버튼→저장본 삭제→pageerror 0) + 4상태 스크린샷 육안 대조(기본/드래그/
  복원=드래그 동일/리셋=기본 동일).

**핫픽스: ASIC 9단계 ④ ASIC 설계 빈 화면(사용자 리포트)** — 원인은
`asicCharts.tsx` Histogram의 `counts.map((c, i)` 매개변수 `c`가 테마 토글
작업(3468143)에서 도입된 팔레트 `const c = useSvgPalette()`를 가려
`c.series[0]` 크래시 → 에러 바운더리 없어 탭 전체가 배경만 남음.
매개변수를 `n`으로 개명해 픽스. 회귀 시점은 git으로 입증(3468143 이전엔
fill이 리터럴 hex라 무해). 교훈: **컴포넌트 스코프의 짧은 변수명(c/p/s)에
map 매개변수 이름을 재사용 금지 — tsc가 못 잡는 런타임 셰도잉 크래시.**
검증: Playwright로 9단계 전수 클릭 ALL PASS + s4 히스토그램 rect 24개 렌더 +
pageerror 0 (`/tmp/alps-logs/asic-s4-check.mjs`).

**AXOS 피드백 버튼 폐루프 이식 완료(사용자 지시 "피드백 버튼을 이렇게
만들어줘")** — 하이퐁 IOC 포털의 AXOS 피드백 버튼(우측 고정 세로 토글 탭 +
Context Drawer + 제출 모달)을 ALPS에 이식했다. 설계 원칙: **웹 접수는
axos-si 플러그인 피드백 큐의 또 하나의 채널** — 레코드는 저장소 루트
`feedback/FB-####.json`(axos-si `feedback.py`와 동일 스키마, 플러그인 이식
지시서의 자동 기록 맥락은 `channel` 키로 추가: source/menu/filters/
screen_version/reference_time). 개발팀은 같은 큐를 CLI로 소비:

```bash
python3 ~/works/axos-si/skills/axos-feedback-loop/scripts/feedback.py --root . list
# approve → dev_queue/FB-####.md 지시서 생성(Claude 세션이 읽어 실행)
```

이번 작업 (커밋 상단의 피드백 버튼 커밋):

- **API** `apps/api/app/routers/feedback.py` + `app/schemas/feedback.py` —
  `POST/GET /api/v1/feedback`(파일 저장소, DB 아님; ID는 `.sequence` 상수위
  방식이라 반려 후에도 번호 재발급 안 됨; 우선순위는 정규 어휘 상/중/하만),
  `app/main.py` 라우트 등록. **STORE_DIR은 `parents[4]` = 저장소 루트 —
  단수 오차면 `apps/feedback`에 기록되는 버그(실제 발생, 회귀 테스트로 고정).**
- **웹** `components/AxosFeedbackWidget.tsx`(named export, 전역 1회 마운트 —
  App.tsx에서 standalone 모드 포함 전 탭) + `lib/screenContext.ts`(탭→경로/
  메뉴라벨/목적) + `lib/api.ts` `feedbackApi` + i18n 3 로케일 `axos` 섹션.
  위젯 동작은 이식 지시서 그대로: 우측 중앙 세로 "AXOS" 탭(zIndex 1150,
  AssistantPanel FAB 1000과 비충돌) → 드로어(화면 목적+최근 피드백 5건,
  w320/max85vw, 오버레이 클릭 닫힘) → 모달(분류 5종·제목*·현행*·목표·
  기대효과·우선순위 4단계→상/중/하 사상, 경로·메뉴·필터·화면버전·제출자·
  시각 자동 기록, 빈 필수값은 제출 버튼 비활성) → 성공 화면 1.4초 후 폼
  초기화. Tailwind 없음 → 토큰 인라인 스타일(AXOS 브랜드 시안 =
  color-mix(info 62%, #061724)), 신규 npm 디펜던시 0(아이콘 인라인 SVG).
- **설정** 저장소 루트 `axos.config.yml`(feedback_loop.enabled) 신설,
  `.gitignore` += `/feedback/`, `/dev_queue/`(제출자 계정 포함 런타임 기록).
- **검증** pytest 186건 전부 통과(test_feedback.py 6건 포함), tsc/
  vite 빌드 + oxlint 27 warnings 베이스라인 유지, Playwright 브라우저 e2e
  25항목 ALL PASS(`/tmp/alps-logs/axos-fb-check.mjs` — 로그인→버튼→드로어→
  빈 제출 차단→접수→1.4초 성공→레코드 스키마·자동 맥락 검증→드로어 목록
  반영→오버레이 닫힘→proc 탭·라이트 테마), CLI `--root . list/show` 로 웹
  접수 건 그대로 조회 확인(폐루프 1회전 중 접수 구간 실증).

**UI/UX 3D-트윈 퍼스트 고도화 완료** — 사용자 지시("텍스트·숫자 위주 대신
실제 제품·부품·장비의 3D 디지털 트윈을 보고 체험하고 활용하는 화면으로")에
따른 전면 개편. 계획 파일
`~/.claude/plans/cosmic-riding-phoenix.md`의 W1~W6 전부 완료 + 실행 중
사용자 추가 지시(공정 트윈 실사화, ASIC ⑤ 단계 템플릿별 패키지 모델, S04
실물 재질, 배경 토글, 상용 수준 프리미엄 UI)까지 반영. **전부 push 완료**
(origin/main 동기 — 세션에서 `cd /Users/wizbase/works/alps && git push`
로 푸시됨).

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

11. `64bf2d0` **합성 3D를 장난감 큐브→배치된 산업 다이로**(사용자 지시 "합성
   3D가 도형 스타일에서 실사 스타일 산업표준 모델로") — `buildSynthesisScene`
   전면 재구성: 게이트 타입별 클러스터=표준셀 **로우** 배치 영역(플린스 트레이,
   셀 0.72×0.12×0.63 flat strip, pitch 1.05) + M1 VDD/VSS 전원 레일(행 경계
   공유, 청/적) + Cu M2(수평)/Ag M3(수직) BEOL 배선 + Au 비아 실린더 + 뚜껑
   있는 다이 기판(베이스+랩드 리드, top y 0.18) + **Au 실링 링** + 포토 정합
   키 4코너. 재질 전반 금속화(metalness 0.55~0.95) — `EdaScene.studio` 플래그
   신설로 합성 씬만 drei `Environment`(Lightformer 4면, **생성형 env — HDR
   에셋·네트워크 없음**)+`ContactShadows`(frames=1, 씬 키 재마운트) 적용.
   폭발 슬라이더=명시 `explodeAnchors`(die→label→analog→cell→m1→m2→via→m3→
   kpi→drc 제작 순 리프트). KPI 타워를 짧은 금속 게이지 포스트로 재조형(높이
   캡 2.4, 0.42 각). CAP 160→96(로우+레일+배선≈셀당 1.4 메시 — SoC 3,346게이트
   도 예산 내). 범례 칩에 m1/m2/m3/via 추가. 검증: eda_e2e+eda_sil_e2e+
   eda_synth_soc(신규, SoC 합성 뷰+폭발 스크린샷)+w6_sweep CLEAN, 빌드·lint
   27·seedl10n 101/0.

12. `1a81582` **레이아웃 3D도 합성 3D와 동일 실사 트리트먼트**(사용자 지시
   "레이아웃 3D도 합성 3D처럼 실사 스타일로") — `buildLayoutScene`: 케이크
   구조 유지 + `studio: true`(합성과 같은 생성형 환경광+ContactShadows),
   기판=베벨 엣지 있는 베이스+랩드 리드 2중, 매크로 블록=어두운 플린스 트레이
   위 착지(합성 배치 트레이와 동일 어휘), 금속 전반 업그레이드 — 패드 0.95/
   실링 0.92(Au 톤 통일)/M1 레일 0.85/M2~M6·전원 그리드 0.9·비아 0.95,
   emissive 0.22→0.12로 낮춰 환경 반사가 하이라이트를 담당. 폭발 앵커=
   레지스트리 Y 고정(추가 서브박스가 리프트 순서를 바꾸지 않음). 검증:
   eda_e2e+eda_sil_e2e+w6_sweep CLEAN.

13. `dc82079` **공정 3D도 동일 실사 트리트먼트**(사용자 지시) — `buildProcessScene`:
   스텝 디테일 유지 + `studio: true`(3D 씬 3종 전부 스튜디오 환경광), 신규
   `EdaScene.shadowY`(기본 −0.32, 웨이퍼 슬라브가 y −0.5까지 내려가 공정만
   −0.55 — 그림자 평면이 슬라브를 가로지르지 않음). 재질 정합: 패드 metalness
   1.0/rough 0.24·실링=Au 톤 통일(0.92/0.25), M1~M6·비트라인/실드 0.88~0.92+
   emissive 낮춰 환경 반사 담당, via1 0.95/0.22, STI=CMP 광택(rough 0.45),
   패시베이션=유리(rough 0.25), 웨이퍼 노치/플랫 금속 마감. 검증: eda_e2e+
   eda_sil_e2e+w6_sweep CLEAN.

14. `a633769` **S04 3D 모델 실물 재질**(사용자 지시 "핀은 구리색, 버튼·케이스
    등 산업표준 소재의 원래 색") — `convert.py` MATERIAL_BY_KEYWORD: 터미널=
    인청동 구리(0.80,0.45,0.28, metal 1.0/rough 0.32), 플런저=POM 백색,
    lcp/pbt 블랙 rough 0.42(사출 광택). 근본 원인 진정: GLB 머티리얼은 정상
    (런타임 `__THREE_DEVTOOLS__` 덤프로 입증) — RoomEnvironment 백실 조도가
    0.04 알베도 LCP를 중간회색으로 세척. ThreeViewer의 환경을 **생성형 다크
    스튜디오**(PMREM MeshBasicMaterial 패널, color×intensity>1=HDR 라이트,
    측면 스트립 라이트=곡면 금속 버티컬 하이라이트)로 교체+직사광 축소.
    레지네레이션: 각 변량의 최신 succeeded cad_convert run의 입력 STEP을 재사
    용해 신규 run POST(/tmp/alps-logs/regen_cad_glb.py)→8변량 전부 relink,
    0 실패(새 RUN-CAD-REALISM 런이 Result Compare에 보임). 워커 수정 시:
    apps/workers/cad-converter는 소스 기반 자체 .venv — ps/lsof로 정확 PID
    찾아 kill 후 nohup 재기동(로그 /tmp/alps-logs/cad-converter.log).
15. `9a64cb9` **S04 배경 밝/어둠 토글**(사용자 지시 "케이스가 어두운데 배경도
    어두워 제품 구분이 안 된다") — store `viewerBg` dark|light(변량 전환에
    안 보존), TwinControls 토글 버튼(`twin.bgLight`/`twin.bgDark` ko/en/ja),
    ViewerEnvironment가 BG_THEMES로 모드별 env 재구축(배경색+패널 강도 함께
    전환 — 머티리얼이 리라이트되지 배경만 바뀌는 게 아님), Canvas 전환 0.25s.
16. `6f9f7b7` **프리미엄 인스트루먼트 디자인 언어 기반**(사용자 지시 "상용제품
    수준 … 폰트·양각 메뉴버튼·메탈릭 UI/UX … 유사 제품 디자인 전수 조사 이상
    으로") — 유사 조사( Siemens 다크 HMI 템플릿, ISA-101 고성능 HMI: 무채
    표면+색은 신호 전용, 레이어드 톤)를 "정밀 계기" 언어로 치환: index.html
    Pretendard Variable(다이내믹 서브셋)+JetBrains Mono 프리커넥트/로드,
    tokens.ts 레이어드 다크(bg.page→card→panel→raise, metalHeader/Panel/
    Raise/Well 브러시드 그라디언트, rim 라이트)+emboss 섀도 3종(lift/panel/
    well)+tracking, kit.tsx 카드·th(실크스크린 대문자 트래킹)·Kpi(웰+모노)·
    btn(양각 키), index.css 전역 버튼 호버/프레스/포커스+씬 스크롤바,
    App.tsx 메탈릭 헤더+키캡 탭(LED pip). 820px 미디어쿼리 불변.
17. `c5cd4e4` **프리미엄 그래프/모니터링 패스** — 신규 `ui/chartTheme.ts`
    (공용 ECharts 베이스: 헤어라인 스파인 #3b4a63, 모노 틱 라벨 10px, 대시
    스캐폴드 그리드, 다크 글래스 모노 툴팁, TRACE_PALETTE+traceGlow 자체색
    발광)을 SweepChart(변량별 팔레트색)/TestCorrelationPanel(예측=사이언
    글로우+실측=앰버 마커, 잔차 Δ 차트 포함)/DoeStudyPanel/AirSignalChart
    (밀집 카테고리축 splitLine off)에 전파, ProcessMonitoring SVG 관리도는
    웰 베젤+관리한계 밴드 미팅트+드롭섀도 트레이스+모노 눈금. 검증: 빌드·
    lint 27·seedl10n 101/0+w6_sweep PASS, 차트 3종 스크린샷 육안 확인.
18. `7ddd604` **대비 전수검사** — 셀렉트 팝업 option 색상 토큰화 + 전 탭
    Playwright TreeWalker 대비 감사(전경색×합성 배경 알파 합성) 4.5:1/3:1
    미달 전부 수정, 다크 모드 CLEAN.
19. `e87d68a` **로터리 인코더 CAD 정합** — 다이얼 노브 메시 + 케이스 안쪽
    포텐셔미터 연결부(샤프트·브래킷·기어 링크) 모델링, 미구현 부품 해소.
20. `3468143` **앱 전역 다크/라이트 테마 토글** — 헤더 ☀/☾ 버튼
    (`store.uiTheme`, localStorage `alps.ui-theme`, 마운트 전 `<html>`
    data-theme 반영으로 깜빡임 없음). `index.css` 전면 `--alps-*` 변수화 +
    라이트 팔레트(페이지 #dde3ec 계열, 상태색은 라이트용으로 어두운 톤 —
    faint #51627a / ok #0c6b43 / ok-alt #136a32 / attention #8a5606 /
    accent-orange #a83a0b / idle #526178). 파서 경계 처리: tokens는
    var() 문자열, three.js 머티리얼용 `rawStatus`/`rawAccent` raw hex 유지,
    ECharts는 `useChartTheme()` 모드별 콘크리트 팔레트, SVG 차트는
    `useSvgPalette()`, 칩/버튼 틴트는 `color-mix(in srgb, var N%,
    transparent)`. **계기 유리(keep-dark)**: 스코프 패널·F-S 오버레이·
    sysmodel 웰·회로도 캔버스·EDA 코드 에디터·온보딩 스트립은 라이트에서도
    다크 유지(라이트 베젤 + 다크 글래스, 컨테이너에 `color:"#e2e8f0"` 핀).
    검증: 빌드+lint 27+seedl10n 101/0+w6_sweep PASS, **다크/라이트 각 8탭
    대비 감사 전부 CLEAN**(라이트 초기 246건 → 루트원인 7종 수정),
    토글 버튼 왕복 + 양 모드 스크린샷 육안 확인(/tmp/alps-logs/
    theme_*.png). 대비 감사 하네스: `/tmp/alps-logs/contrast_audit2.mjs`
    (THEME=light|dark).
21. `509e6b5` **AirInput 개발/테스트 보드 일치**(사용자 지시 "AirInput
    Proximity Sensor 개발/테스트 보드가 상이하다") — 벤치 탭이 제품명
    "sensor" 포착으로 MEMS 압력 보드를 보여주던 것을 `air` 패밀리 신설로
    수정: AirScene과 동일 재질·기하의 puck 모듈 DUT(하우징 셸/PCB/전극/
    ASIC 패들/커버 글래스, 실물 34×28 벤치 스케일 0.36 공표), **선택 변량의
    전극 레이아웃 추종**(App→variantName prop, A 센터패드/B 스플릿 링),
    캐스텔레이션 단자→MCU 배선, 손끝 스티뮬러스 버튼(스코프 CH1 감지 레벨·
    CH2 터치 컴패레이터 히스테리시스, F-S/ΔC(d) 커서 동기). 부수 수정:
    air 탭 Layout B 스플릿 링이 x=0에 그려지던 것을 솔버/CAD와 동일한
    ELECTRODE_CENTER_X=5로.
22. `4ccad34` **언어 선택기 헤더 우상단 고정**(사용자 지시) — 내비바 끝에
    있어 줄바꿈에 따라 밀리던 언어 select를 헤더 우측 그룹(테마 토글 옆)
    으로 이동 + 메탈 레이즈/엠보스 스타일 일치.
    검증(21·22 공통): 빌드+lint 27+seedl10n 101/0, Playwright 하니스
    `/tmp/alps-logs/air_bench_check.mjs`(언어 헤더 y<탭 y, 벤치 A/B DUT 칩,
    손끝 토글 스코프 반응, 0 콘솔 에러), **다크/라이트 대비 감사 재실행
    전부 CLEAN**, 스크린샷 air_bench_{A,A_near,B}.png·air_tab_B.png
    육안 확인.
23. `b6531c3` **시스템 문서 v1.1**(사용자 지시 "시스템문서 작업내용 모두
    추가와 업데이트") — `systemDoc.{ko,en,ja}.md` 3개 로케일(222행 병렬
    유지)에 누락된 전체 작업 반영: 상단 **v1.1 (2026-09-17) 주요 업데이트**
    인용구 신설, §3.1 프리미엄 계기 디자인+헤더 우상단 언어/테마 고정,
    §3.3 3D 콕핏 랜딩·검토 툴바(FR-03)·전 패널 부품 ID 동기화(L187),
    §3.4 패밀리별 DUT 모듈+AirInput puck 보드 전면 재작성, §3.6
    FactoryViewer 생산라인 3D 트윈, §3.7 변량 추종 전극 지오메트리,
    §3.8 자사 칩셋 플레이버 미션+합성 3D 실사, §3.9 ⑤ 패키지 패밀리/
    본드맵/Au 와이어+장비 랙 스트립, §4 프리미엄 테마 행, §8 디자인
    시스템·생산라인 3D 스택 행. 다운로드 파일명 v1.0→v1.1
    (SystemDocs.tsx). 검증: 빌드+lint 27+seedl10n 101/0, Playwright
    `/tmp/alps-logs/sysdoc_check.mjs`(ko/en/ja v1.1 렌더+puck/
    FactoryViewer/QFN 행 단정, 0 콘솔 에러), sysdoc_ko.png 육안 확인.
24. `2249db6` **MEMS 압력센서 내부 구성 산업표준화**(사용자 지시 "내부 부품
    구성도 산업표준 cad기준으로 정확하게") —
    `generate_pressure_sensor_step.py` 5→12부품 재작성: Kovar 씰 링(리드가
    그 위에 심용접 — 이전엔 기판 위 0.35 mm 공중 부양), 은 에포키 다이 어태치,
    에칭 기준 진공 공동 + 감지 다이어프램 캡, 피조 브리지 스트레인 바 4본,
    Al 다이 패드/Ni-Au 기판 패드, Au 베지어 튜브 본드 와이어 4가닥
    (`BRepOffsetAPI_MakePipe`+`OCP.collections.Array1_gp_Pnt`). convert.py에
    신규 키워드 6종("substrate"/"die" 제너릭 항목 **앞**에 삽입 — 스캔은
    첫 매치 승리). VAR-SEN-A/B 라이브 cad_convert 재링크 0 실패,
    `internals_check.mjs` 브라우저 검증(X-ray+폭발에서 내부 전노출, 0 콘솔
    에러).
25. `783cd15` **TACT 스위치 내부 구성 산업표준화**(동일 지시) —
    `generate_sample_step.py` 7→10부품: 하우징을 몰딩 컵(바닥 0.5/벽 0.35
    mm)으로 파고 중앙 컬럼으로 우물 바닥 지지, 링 캐비티에 **Stationary
    Contacts**(스탬프 레그 4본 — 돔 림이 맞닿는 정접점, 신규), 돔을 팁 위에
    안착(패드 상 0.12 mm 스냅 갭 = ThreeViewer DOME_TRAVEL_MM와 일치),
    Terminal 3/4 추가로 4단자 완성. 필렛 술어를 외곽 모서리 한정으로 축소
    (얇은 내벽 모서리에 0.3 mm 필렛 → 실패 시 폴백이 필렛 전부 상실).
    VAR-TACT-A/B 재링크 0 실패, MEMS와 동일 스크립트로 브라우저 검증.

**검증 스크립트**(`/tmp/alps-logs/`, 전부 PASS): cockpit_e2e(W2),
proc_e2e/proc_mobile_e2e(W3), bench_e2e(W4), review_e2e(W5), w6_sweep(8탭
ko + en/ja 스모크 + 390×844 모바일), pkg_e2e(템플릿 A~D × ⑤단계 캔버스+
pkg 칩 + B OPT-2 → TSSOP-16 재표적), pkg_internals_e2e(⑤ mold-off+분해도
0.45 스크린샷 A/B/D — 내부 구조 육안 검증용), eda_sil_e2e(EDA 미션별
공정·레이아웃 3D 스크린샷 FIFO/UART/SoC — 71e25a1 육안 검증용).

**다음 세션(또는 사용자)이 할 일**:
- **AXOS 피드백 폐루프 1회전 완료(2026-09-21, 상단 블록)** — (b) 개발팀 루트는
  approve→start→구현→complete까지 완주. 남은 것: (a) 사용자 웹검증 — 드로어
  "최근 피드백"에서 FB-0001의 반영완료 배지 확인 포함. (c) axos-si 플러그인
  쪽 미수정 과제(이미 사용자 보고됨): `check_requirement_coverage.py`가
  usage에 `--config`를 표시하지만 실제로는 파싱하지 않음(하드코딩 경로).
  플러그인 쪽 템플릿 치환 누락 1건 추가 발견: 지시서 헤더의
  `{{RECORD_PATH}}`가 치환되지 않고 리터럴로 남음(feedback.py
  INSTRUCTION_TEMPLATE 렌더 시 이 키만 누락).
- **ASIC ④ 설계 빈화면 핫픽스 웹검증(6d0900f)** — ASIC 탭 9단계 레일에서
  "④ ASIC Design" 클릭 → 배경만 보이던 화면에 설계 런 버튼·KPI·VER 매트릭스·
  코너 스터디 히스토그램(24 bins)이 떠야 함. 브라우저 e2e는 ALL PASS
  (`/tmp/alps-logs/asic-s4-check.mjs` — 9단계 전수 클릭, pageerror 0).
- **웹 브라우저 검증** —
  사용자가 "완성하면 내가 웹으로 검증해볼게"라고 한 상태. model 탭 첫 화면
  (실물 재질 + 밝/어둠 배경 토글), proc 탭 실사 라인, ASIC 탭 템플릿별 ⑤단계
  모델, 프리미엄 셸/그래프 전반, **헤더 ☀/☾ 다크·라이트 테마 토글**(3468143 —
  라이트에서도 스코프/회로도 계기 글래스는 다크 유지가 의도된 디자인),
  **헤더 우상단 언어 선택기**(4ccad34), **벤치 탭 AirInput puck 보드**
  (509e6b5 — 변량 A/B 전극 레이아웃 추종, 손끝 버튼→스코프),
  **시스템 문서 탭 v1.1**(b6531c3 — 3개 로케일, 다운로드 파일명도 v1.1).
  **MEMS·TACT 3D 내부 구성**(2249db6/783cd15 — model 탭에서 X-ray 슬라이더를
  최소로, 폭발 슬라이더를 최대로: MEMS는 리드·씰 링·다이 공동·다이어프램·본드
  와이어, TACT는 컵 하우징·정접점 팁 위 돔·4단자).
- **세션 시작 참고**: 시스템 문서는 이제 구현과 1:1 동기 상태(b6531c3).
  이후 기능을 추가하면 §3 해당 소절과 버전/날짜 줄을 함께 갱신할 것 —
  문서는 앱에 번들(`?raw`)되므로 md 수정만으로 라이브 반영된다.
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
