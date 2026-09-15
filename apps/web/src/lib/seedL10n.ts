import { L, pickL, type LStr } from "./lstr";

// Demo-dataset localization overlay. The golden dataset (scripts/seed_golden_dataset.py)
// authors its texts in Korean and the API stores single text columns, and a few
// backend rule engines compose their messages server-side — under the ja UI this
// panel rewrites those strings at render time. Two tiers:
//   EXACT  — key is the exact stored string (seed rows, static backend messages)
//   RULES  — regex over composed backend messages; group $1.. are spliced into
//            per-language templates. Group text that is itself a stored string
//            (e.g. an operation name) is re-run through seedTr first.
// A miss always falls back to the stored text, so new data degrades honestly.

const EXACT: Record<string, LStr> = {
  // ── requirements (seed: TACT/ENCODER/SENSOR/AIR *_REQUIREMENTS) ──
  "사용자가 누를 때 더 명확한 클릭감(Tactile feedback)을 느껴야 한다.": L(
    "사용자가 누를 때 더 명확한 클릭감(Tactile feedback)을 느껴야 한다.",
    "Pressing the switch must produce a clearer tactile click feel.",
    "押したときにより明確なクリック感(タクタイルフィードバック)が得られること。",
  ),
  "차량 진동 조건에서 오작동(false trigger)이 발생하지 않아야 한다.": L(
    "차량 진동 조건에서 오작동(false trigger)이 발생하지 않아야 한다.",
    "No false trigger under automotive vibration conditions.",
    "車両振動条件で誤動作(false trigger)が発生しないこと。",
  ),
  "지정된 수명(최소 100만 사이클) 동안 접점 저항이 규정 범위 내에 있어야 한다.": L(
    "지정된 수명(최소 100만 사이클) 동안 접점 저항이 규정 범위 내에 있어야 한다.",
    "Contact resistance must stay within spec over the rated life (min 1M cycles).",
    "規定寿命(最低100万サイクル)の間、接触抵抗が規定範囲内であること。",
  ),
  "로터리 인코더 조작 시 일정하고 명확한 디텐트 감각이 느껴져야 한다.": L(
    "로터리 인코더 조작 시 일정하고 명확한 디텐트 감각이 느껴져야 한다.",
    "Rotating the encoder must give a consistent, clear detent feel.",
    "ロータリーエンコーダ操作時、一貫した明確なディテント感が得られること。",
  ),
  "차량 진동 조건에서 출력 채널 오동작(chattering)이 발생하지 않아야 한다.": L(
    "차량 진동 조건에서 출력 채널 오동작(chattering)이 발생하지 않아야 한다.",
    "No output channel chattering under automotive vibration conditions.",
    "車両振動条件で出力チャネルの誤動作(chattering)が発生しないこと。",
  ),
  "지정된 회전 수명(최소 30만 사이클) 동안 접점 저항이 규정 범위 내에 있어야 한다.": L(
    "지정된 회전 수명(최소 30만 사이클) 동안 접점 저항이 규정 범위 내에 있어야 한다.",
    "Contact resistance must stay within spec over the rated rotation life (min 300k cycles).",
    "規定回転寿命(最低30万サイクル)の間、接触抵抗が規定範囲内であること。",
  ),
  "지정 압력 범위(40~400kPa) 전 구간에서 규정 감도 이상의 출력을 제공해야 한다.": L(
    "지정 압력 범위(40~400kPa) 전 구간에서 규정 감도 이상의 출력을 제공해야 한다.",
    "Output must meet the specified sensitivity across the full rated range (40–400 kPa).",
    "指定圧力範囲(40~400kPa)の全領域で規定感度以上の出力を提供すること。",
  ),
  "동작 온도 범위에서 측정 정확도가 규정 오차 이내여야 한다.": L(
    "동작 온도 범위에서 측정 정확도가 규정 오차 이내여야 한다.",
    "Measurement accuracy must stay within the specified error over the operating temperature range.",
    "動作温度範囲で測定精度が規定誤差以内であること。",
  ),
  "리플로우 공정 후 솔더 접합 신뢰성이 확보되어야 한다.": L(
    "리플로우 공정 후 솔더 접합 신뢰성이 확보되어야 한다.",
    "Solder-joint reliability must be assured after the reflow process.",
    "リフロー工程後のはんだ接合信頼性が確保されること。",
  ),
  "지정된 접근 거리 이내에서 손가락 접근을 안정적으로 검출해야 한다.": L(
    "지정된 접근 거리 이내에서 손가락 접근을 안정적으로 검출해야 한다.",
    "Finger approach must be detected reliably within the specified distance.",
    "指定接近距離以内で指の接近を安定して検出できること。",
  ),
  "노이즈 환경에서 오검출(false trigger)이 발생하지 않아야 한다.": L(
    "노이즈 환경에서 오검출(false trigger)이 발생하지 않아야 한다.",
    "No false detection under noisy environments.",
    "ノイズ環境で誤検出(false trigger)が発生しないこと。",
  ),
  "대표 장갑 착용 조건에서도 규정된 축소 검출거리 이내에서 검출되어야 한다.": L(
    "대표 장갑 착용 조건에서도 규정된 축소 검출거리 이내에서 검출되어야 한다.",
    "Detection must hold within the specified reduced distance for the representative glove condition.",
    "代表手袋着用条件でも規定の縮小検出距離以内で検出できること。",
  ),
  // requirement source strings (seed)
  "AlpsAlpine_Engineering_Digital_Twin_Workbench_개발지시서_v1.0 §12.1": L(
    "AlpsAlpine_Engineering_Digital_Twin_Workbench_개발지시서_v1.0 §12.1",
    "AlpsAlpine Engineering Digital Twin Workbench spec v1.0 §12.1",
    "AlpsAlpine Engineering Digital Twin Workbench開発仕様書 v1.0 §12.1",
  ),
  "AlpsAlpine_AirInput_3D_Interaction_Field_Twin_구현지시서_v1.0 §1.2/§11.2": L(
    "AlpsAlpine_AirInput_3D_Interaction_Field_Twin_구현지시서_v1.0 §1.2/§11.2",
    "AlpsAlpine AirInput 3D Interaction Field Twin spec v1.0 §1.2/§11.2",
    "AlpsAlpine AirInput 3D Interaction Field Twin実装仕様書 v1.0 §1.2/§11.2",
  ),

  // ── model canvas: causal relations (seed: _*_CAUSAL) ──
  "조작 입력력": L("조작 입력력", "Actuation force", "操作入力力"),
  "돔 변형(스냅)": L("돔 변형(스냅)", "Dome deformation (snap)", "ドーム変形(スナップ)"),
  "접점 접촉·바운스": L("접점 접촉·바운스", "Contact touch · bounce", "接点接触・バウンス"),
  "접촉 저항 R_c": L("접촉 저항 R_c", "Contact resistance R_c", "接触抵抗 R_c"),
  "출력 로우 레벨 V_OL": L("출력 로우 레벨 V_OL", "Output low level V_OL", "出力ローレベル V_OL"),
  "Debounce 지연": L("Debounce 지연", "Debounce delay", "デバウンス遅延"),
  "조작감 명확함": L("조작감 명확함", "Clear actuation feel", "操作感の明確さ"),
  "플런저 가력이 구면 금속 돔을 좌굴시켜 스냅스루": L(
    "플런저 가력이 구면 금속 돔을 좌굴시켜 스냅스루",
    "Plunger load buckles the domed metal disc into snap-through",
    "プランジャー加圧が球面金属ドームを座屈させスナップスルー",
  ),
  "스냅 접촉 순간 접점계 반동으로 접점 바운스 발생": L(
    "스냅 접촉 순간 접점계 반동으로 접점 바운스 발생",
    "Snap-through recoil of the contact system causes contact bounce",
    "スナップ接触瞬間の接点系反動で接点バウンスが発生",
  ),
  "접촉 압력 증가 → 필름 저항 감소": L("접촉 압력 증가 → 필름 저항 감소", "Contact pressure up → film resistance down", "接触圧力増加 → フィルム抵抗低減"),
  "풀업 분배: V_OL = V_CC·R_c/(R_c + R_pu)": L(
    "풀업 분배: V_OL = V_CC·R_c/(R_c + R_pu)",
    "Pull-up divider: V_OL = V_CC·R_c/(R_c + R_pu)",
    "プルアップ分圧: V_OL = V_CC·R_c/(R_c + R_pu)",
  ),
  "바운스 구간은 논리 확정 불가 → t_db 동안 대기": L(
    "바운스 구간은 논리 확정 불가 → t_db 동안 대기",
    "Bouncing interval is logic-indeterminate → wait for t_db",
    "バウンス区間は論理確定不可 → t_dbの間待機",
  ),
  "AI 추론: 응답 지연이 짧을수록 즉각감 향상 — 사람 검토 전": L(
    "AI 추론: 응답 지연이 짧을수록 즉각감 향상 — 사람 검토 전",
    "AI inference: shorter response delay improves immediacy — before human review",
    "AI推論: 応答遅延が短いほど即応感が向上 — 人のレビュー前",
  ),
  "회전 토크": L("회전 토크", "Rotation torque", "回転トルク"),
  "스프링 좌굴": L("스프링 좌굴", "Spring buckling", "スプリング座屈"),
  "로터 접촉 압력": L("로터 접촉 압력", "Rotor contact pressure", "ローター接触圧力"),
  "채널 접촉저항·채터링": L("채널 접촉저항·채터링", "Channel contact resistance · chattering", "チャネル接触抵抗・チャタリング"),
  "차량 진동": L("차량 진동", "Vehicle vibration", "車両振動"),
  "채널 채터링": L("채널 채터링", "Channel chattering", "チャネルチャタリング"),
  "디코드 오카운트": L("디코드 오카운트", "Decode miscount", "デコード誤カウント"),
  "디텐트 토크 곡선": L("디텐트 토크 곡선", "Detent torque curve", "ディテントトルク曲線"),
  "디텐트 감각": L("디텐트 감각", "Detent feel", "ディテント感"),
  "로터 회전이 디텐트 스프링을 좌굴시켜 디텐트 형성": L(
    "로터 회전이 디텐트 스프링을 좌굴시켜 디텐트 형성",
    "Rotor rotation buckles the detent spring, forming the detent",
    "ローター回転がディテントスプリングを座屈させディテントを形成",
  ),
  "스프링 반력이 로터–스테이터 접촉압을 결정": L(
    "스프링 반력이 로터–스테이터 접촉압을 결정",
    "Spring reaction force sets rotor–stator contact pressure",
    "スプリング反力がローター–ステーター接触圧を決定",
  ),
  "접촉압 변동이 채널 저항과 점속을 변조": L(
    "접촉압 변동이 채널 저항과 점속을 변조",
    "Contact-pressure variation modulates channel resistance and continuity",
    "接触圧変動がチャネル抵抗と導通を変調",
  ),
  "하우징 전달 진동이 접점 이탈을 유발 (REQ-NOJITTER)": L(
    "하우징 전달 진동이 접점 이탈을 유발 (REQ-NOJITTER)",
    "Housing-transmitted vibration separates the contacts (REQ-NOJITTER)",
    "ハウジング伝搬振動が接点離脱を誘発 (REQ-NOJITTER)",
  ),
  "채터링 구간은 위상 디코드에서 유효 펄스로 오판 가능": L(
    "채터링 구간은 위상 디코드에서 유효 펄스로 오판 가능",
    "Chattering intervals can be misread as valid pulses in phase decoding",
    "チャタリング区間は位相デコードで有効パルスと誤判定され得る",
  ),
  "AI 추론: 피크/밸리 토크 비율이 클릭감 명확성 결정 — 사람 검토 전": L(
    "AI 추론: 피크/밸리 토크 비율이 클릭감 명확성 결정 — 사람 검토 전",
    "AI inference: peak/valley torque ratio sets click-feel clarity — before human review",
    "AI推論: ピーク/バレー・トルク比がクリック感の明確さを決定 — 人のレビュー前",
  ),
  "인가 압력": L("인가 압력", "Applied pressure", "印加圧力"),
  "다이어프램 변형": L("다이어프램 변형", "Diaphragm deflection", "ダイヤフラム変形"),
  "브리지 출력 V_out": L("브리지 출력 V_out", "Bridge output V_out", "ブリッジ出力 V_out"),
  "보정 출력": L("보정 출력", "Compensated output", "補正出力"),
  "솔더 접합 상태": L("솔더 접합 상태", "Solder-joint condition", "はんだ接合状態"),
  "출력 드리프트": L("출력 드리프트", "Output drift", "出力ドリフト"),
  "보정 후 선형성": L("보정 후 선형성", "Post-compensation linearity", "補正後の直線性"),
  "측정 신뢰감": L("측정 신뢰감", "Measurement trust", "計測の信頼感"),
  "압력이 실리콘 다이어프램에 막 응력 유발": L(
    "압력이 실리콘 다이어프램에 막 응력 유발",
    "Pressure induces membrane stress in the silicon diaphragm",
    "圧力がシリコンダイヤフラムに膜応力を誘起",
  ),
  "피에조저항 변화 → 휘트스톤 브리지 불균형 전압": L(
    "피에조저항 변화 → 휘트스톤 브리지 불균형 전압",
    "Piezoresistive change → Wheatstone bridge imbalance voltage",
    "ピエゾ抵抗変化 → ホイートストンブリッジの不平衡電圧",
  ),
  "게인·오프셋·온도 보상 보정식 적용": L(
    "게인·오프셋·온도 보상 보정식 적용",
    "Apply gain/offset/temperature compensation equations",
    "ゲイン・オフセット・温度補償の補正式を適用",
  ),
  "솔더 볼 피로/크랙이 접촉 저항을 변화시켜 드리프트 유발": L(
    "솔더 볼 피로/크랙이 접촉 저항을 변화시켜 드리프트 유발",
    "Solder-ball fatigue/cracks change contact resistance, causing drift",
    "はんだボール疲労/クラックが接触抵抗を変化させドリフトを誘発",
  ),
  "AI 추론: 직선성·재현성이 사용자 신뢰감 결정 — 사람 검토 전": L(
    "AI 추론: 직선성·재현성이 사용자 신뢰감 결정 — 사람 검토 전",
    "AI inference: linearity and repeatability set user trust — before human review",
    "AI推論: 直線性・再現性がユーザーの信頼感を決定 — 人のレビュー前",
  ),

  // ── model canvas: elements (seed: _*_ELEMENTS) ──
  "조작 입력력 F_act": L("조작 입력력 F_act", "Actuation force F_act", "操作入力力 F_act"),
  "돔 스냅 기구": L("돔 스냅 기구", "Dome snap mechanism", "ドームスナップ機構"),
  "F(δ): 구면 바이어스 스프링 스냅스루": L(
    "F(δ): 구면 바이어스 스프링 스냅스루",
    "F(δ): spherical bias-spring snap-through",
    "F(δ): 球面バイアススプリングのスナップスルー",
  ),
  "Debounce 필터": L("Debounce 필터", "Debounce filter", "デバウンスフィルタ"),
  "조작감 (명확함·가벼움)": L("조작감 (명확함·가벼움)", "Actuation feel (clear · light)", "操作感(明確・軽快)"),
  "디텐트 스프링": L("디텐트 스프링", "Detent spring", "ディテントスプリング"),
  "T(θ): 스프링 좌굴 스냅": L("T(θ): 스프링 좌굴 스냅", "T(θ): spring-buckling snap", "T(θ): スプリング座屈スナップ"),
  "로터–스테이터 접촉": L("로터–스테이터 접촉", "Rotor–stator contact", "ローター–ステーター接触"),
  "채널 펄스·채터링": L("채널 펄스·채터링", "Channel pulses · chattering", "チャネルパルス・チャタリング"),
  "A/B 2채널 위상차 90°": L("A/B 2채널 위상차 90°", "A/B 2-channel, 90° phase difference", "A/B 2チャネル位相差90°"),
  "θ = 360°·cnt/(N·감속비)": L("θ = 360°·cnt/(N·감속비)", "θ = 360°·cnt/(N·gear ratio)", "θ = 360°·cnt/(N・減速比)"),
  "펄스 디코드": L("펄스 디코드", "Pulse decoding", "パルスデコード"),
  "디텐트 감각 (클릭감)": L("디텐트 감각 (클릭감)", "Detent feel (click feel)", "ディテント感(クリック感)"),
  "다이어프램 변형 ε": L("다이어프램 변형 ε", "Diaphragm strain ε", "ダイヤフラム歪み ε"),
  "피에조 브리지 V_out": L("피에조 브리지 V_out", "Piezo bridge V_out", "ピエゾブリッジ V_out"),
  "온도 보상·보정": L("온도 보상·보정", "Temperature compensation · calibration", "温度補償・校正"),
  "솔더 볼 접합": L("솔더 볼 접합", "Solder-ball joint", "はんだボール接合"),

  // ── model canvas: links (seed: _*_LINKS) ──
  "가력 변위 δ": L("가력 변위 δ", "Applied displacement δ", "加圧変位 δ"),
  "스냅 접촉 압력": L("스냅 접촉 압력", "Snap contact pressure", "スナップ接触圧力"),
  "접촉 면적·압력": L("접촉 면적·압력", "Contact area · pressure", "接触面積・圧力"),
  "V_OL 강하": L("V_OL 강하", "V_OL pull-down", "V_OL立下り"),
  "응답 지연감": L("응답 지연감", "Perceived response delay", "応答遅延感"),
  "토크 T(θ)": L("토크 T(θ)", "Torque T(θ)", "トルク T(θ)"),
  "접촉 압력": L("접촉 압력", "Contact pressure", "接触圧力"),
  "접촉 상태": L("접촉 상태", "Contact state", "接触状態"),
  "각도 피드백": L("각도 피드백", "Angle feedback", "角度フィードバック"),
  "압력 P": L("압력 P", "Pressure P", "圧力 P"),
  "변형률 ε": L("변형률 ε", "Strain ε", "歪み ε"),
  "드리프트 성분": L("드리프트 성분", "Drift component", "ドリフト成分"),
  "변형률": L("변형률", "Strain", "歪み"),
  "브리지 출력": L("브리지 출력", "Bridge output", "ブリッジ出力"),
  "출력 전압": L("출력 전압", "Output voltage", "出力電圧"),
  "접촉 저항": L("접촉 저항", "Contact resistance", "接触抵抗"),
  "채널 펄스": L("채널 펄스", "Channel pulse", "チャネルパルス"),
  "토크": L("토크", "Torque", "トルク"),

  // ── model card (seed: fam["card"]) ──
  "F–S 스냅 커브 + 접점 저항 모델": L("F–S 스냅 커브 + 접점 저항 모델", "F–S snap curve + contact resistance model", "F–Sスナップ曲線+接触抵抗モデル"),
  "조작력–행정 곡선과 로직 로우 마진을 예측해 돔 두께/직경 변경이 조작감과 전기 규격에 미치는 영향을 평가한다.": L(
    "조작력–행정 곡선과 로직 로우 마진을 예측해 돔 두께/직경 변경이 조작감과 전기 규격에 미치는 영향을 평가한다.",
    "Predicts the force–stroke curve and logic-low margin to assess how dome thickness/diameter changes affect actuation feel and electrical specs.",
    "操作力–ストローク曲線とロジックロー・マージンを予測し、ドーム厚/直径の変更が操作感と電気規格に与える影響を評価する。",
  ),
  "금속 돔을 축대칭 바이어스 스프링으로 근사": L(
    "금속 돔을 축대칭 바이어스 스프링으로 근사",
    "Metal dome approximated as an axisymmetric bias spring",
    "金属ドームを軸対称バイアススプリングで近似",
  ),
  "접점 필름 저항은 상온 정적 접촉 기준": L(
    "접점 필름 저항은 상온 정적 접촉 기준",
    "Contact film resistance based on room-temperature static contact",
    "接点フィルム抵抗は常温静的接触基準",
  ),
  "하우징 강체 가정, 단자 기생 성분 무시": L(
    "하우징 강체 가정, 단자 기생 성분 무시",
    "Rigid housing assumed; terminal parasitics neglected",
    "ハウジングは剛体仮定、端子の寄生成分は無視",
  ),
  "디텐트 토크 + 채터링 모델": L("디텐트 토크 + 채터링 모델", "Detent torque + chattering model", "ディテントトルク+チャタリングモデル"),
  "디텐트 토크 곡선과 A/B 채널 채터링을 예측해 회전감과 진동 내성을 평가한다.": L(
    "디텐트 토크 곡선과 A/B 채널 채터링을 예측해 회전감과 진동 내성을 평가한다.",
    "Predicts the detent torque curve and A/B channel chattering to assess rotation feel and vibration robustness.",
    "ディテントトルク曲線とA/Bチャネルのチャタリングを予測し、回転感と振動耐性を評価する。",
  ),
  "디텐트 스프링 좌굴을 준정적 토크 곡선으로 근사": L(
    "디텐트 스프링 좌굴을 준정적 토크 곡선으로 근사",
    "Detent-spring buckling approximated as a quasi-static torque curve",
    "ディテントスプリング座屈を準静的トルク曲線で近似",
  ),
  "접점 마모는 수명 초기 구간에서 무시": L(
    "접점 마모는 수명 초기 구간에서 무시",
    "Contact wear neglected in the early-life region",
    "接点摩耗は寿命初期区間で無視",
  ),
  "차량 진동은 규격 스펙트럼 가진 기준": L(
    "차량 진동은 규격 스펙트럼 가진 기준",
    "Vehicle vibration based on standard-spectrum excitation",
    "車両振動は規格スペクトラム加振基準",
  ),
  "브리지 전달 + 온도 보상 모델": L("브리지 전달 + 온도 보상 모델", "Bridge transfer + temperature compensation model", "ブリッジ伝達+温度補償モデル"),
  "인가 압력–브리지 출력 전달특성과 보정 후 정확도를 예측해 감도/온도 특성을 평가한다.": L(
    "인가 압력–브리지 출력 전달특성과 보정 후 정확도를 예측해 감도/온도 특성을 평가한다.",
    "Predicts applied-pressure → bridge-output transfer and post-compensation accuracy to assess sensitivity/temperature characteristics.",
    "印加圧力–ブリッジ出力の伝達特性と補正後精度を予測し、感度/温度特性を評価する。",
  ),
  "다이어프램 소변형 선형 탄성 범위": L(
    "다이어프램 소변형 선형 탄성 범위",
    "Diaphragm within the small-strain linear elastic range",
    "ダイヤフラムは微小歪み線形弾性範囲",
  ),
  "피에조저항 계수는 온도 25°C 기준": L(
    "피에조저항 계수는 온도 25°C 기준",
    "Piezoresistive coefficients referenced to 25 °C",
    "ピエゾ抵抗係数は温度25℃基準",
  ),
  "리플로우 후 솔더 접합은 초기 상태 가정": L(
    "리플로우 후 솔더 접합은 초기 상태 가정",
    "Solder joints assumed in as-reflowed condition",
    "リフロー後のはんだ接合は初期状態と仮定",
  ),
  "합성 데이터 기반 데모 카드. 유효범위 밖 입력의 예측은 정상 결과로 표시되지 않는다 (지시서 금지 #4).": L(
    "합성 데이터 기반 데모 카드. 유효범위 밖 입력의 예측은 정상 결과로 표시되지 않는다 (지시서 금지 #4).",
    "Demo card on synthetic data. Out-of-envelope predictions are not shown as normal results (spec prohibition #4).",
    "合成データに基づくデモカード。有効範囲外の入力に対する予測は正常な結果として表示されない(仕様書禁止#4)。",
  ),

  // ── process operations / lots / quality (seed) ──
  "돔 프레스 성형": L("돔 프레스 성형", "Dome press forming", "ドームプレス成形"),
  "플런저 인서트 성형": L("플런저 인서트 성형", "Plunger insert molding", "プランジャーインサート成形"),
  "조립": L("조립", "Assembly", "組立"),
  "작동력 규격 상한 초과 (데모 합성 데이터)": L(
    "작동력 규격 상한 초과 (데모 합성 데이터)",
    "Actuation force above spec upper limit (demo synthetic data)",
    "操作力規格上限超過(デモ合成データ)",
  ),
  "클릭비 저하 (데모 합성 데이터)": L(
    "클릭비 저하 (데모 합성 데이터)",
    "Click-ratio degradation (demo synthetic data)",
    "クリック比低下(デモ合成データ)",
  ),
  "데모 합성 Lot (source: synthetic)": L("데모 합성 Lot (source: synthetic)", "Demo synthetic lot (source: synthetic)", "デモ合成ロット(source: synthetic)"),
  "데모 합성 Lot — 관리도 시계열 보강 (source: synthetic)": L(
    "데모 합성 Lot — 관리도 시계열 보강 (source: synthetic)",
    "Demo synthetic lot — control-chart time series extension (source: synthetic)",
    "デモ合成ロット — 管理図時系列補強(source: synthetic)",
  ),
  "데모 합성 데이터 — 실제 금형 아님 (source: synthetic)": L(
    "데모 합성 데이터 — 실제 금형 아님 (source: synthetic)",
    "Demo synthetic data — not a real mold (source: synthetic)",
    "デモ合成データ — 実際の金型ではない(source: synthetic)",
  ),
  "TACT 돔 프레스 금형": L("TACT 돔 프레스 금형", "TACT dome press mold", "TACTドームプレス金型"),

  // ── backend static messages (rule engines, disclaimers) ──
  "요소의 대표 출력 단위가 정의되지 않아 인터페이스 호환성을 검증할 수 없습니다.": L(
    "요소의 대표 출력 단위가 정의되지 않아 인터페이스 호환성을 검증할 수 없습니다.",
    "The element's representative output unit is undefined, so interface compatibility cannot be verified.",
    "要素の代表出力単位が未定義のため、インタフェース互換性を検証できません。",
  ),
  "요소에 대표 단위를 정의하거나 포트 계약으로 단위를 명시하세요.": L(
    "요소에 대표 단위를 정의하거나 포트 계약으로 단위를 명시하세요.",
    "Define a representative unit on the element or state the unit in a port contract.",
    "要素に代表単位を定義するか、ポート契約で単位を明示してください。",
  ),
  "원리 기반 모델 요소는 수식 또는 모델 코드 참조를 가져야 합니다.": L(
    "원리 기반 모델 요소는 수식 또는 모델 코드 참조를 가져야 합니다.",
    "Physics-based model elements must carry an equation or a model-code reference.",
    "物理ベースモデル要素は数式またはモデルコード参照を持つ必要があります。",
  ),
  "수식 텍스트 또는 FMU 변수 참조를 등록하세요.": L(
    "수식 텍스트 또는 FMU 변수 참조를 등록하세요.",
    "Register an equation text or an FMU variable reference.",
    "数式テキストまたはFMU変数参照を登録してください。",
  ),
  "포트 단위를 일치시키거나 명시적 변환을 정의한 뒤 링크를 수정하세요.": L(
    "포트 단위를 일치시키거나 명시적 변환을 정의한 뒤 링크를 수정하세요.",
    "Match the port units or define an explicit conversion, then fix the link.",
    "ポート単位を一致させるか、明示的な変換を定義してからリンクを修正してください。",
  ),
  "같은 차원 내 다른 단위라면 unit_conversion에 변환식을 명시하세요.": L(
    "같은 차원 내 다른 단위라면 unit_conversion에 변환식을 명시하세요.",
    "If the units differ within the same dimension, state the conversion in unit_conversion.",
    "同じ次元内の異なる単位なら、unit_conversionに変換式を明示してください。",
  ),
  "검사 데이터 부족": L("검사 데이터 부족", "Insufficient inspection data", "検査データ不足"),
  "이 Lot에는 업로드된 검사 결과가 없습니다 — 원인 판별 전 검사 데이터를 먼저 수집하세요.": L(
    "이 Lot에는 업로드된 검사 결과가 없습니다 — 원인 판별 전 검사 데이터를 먼저 수집하세요.",
    "No uploaded inspection results for this lot — collect inspection data before root-cause determination.",
    "このロットにはアップロードされた検査結果がありません — 原因判定の前に検査データを先に収集してください。",
  ),
  "모든 후보는 확인 필요(조사 우선순위)이며 원인 확정이 아닙니다. 최종 판정은 담당 엔지니어의 승인이 필요합니다.": L(
    "모든 후보는 확인 필요(조사 우선순위)이며 원인 확정이 아닙니다. 최종 판정은 담당 엔지니어의 승인이 필요합니다.",
    "Every candidate is check-required (investigation priority), not a confirmed cause. Final judgment needs the responsible engineer's approval.",
    "すべての候補は確認必要(調査優先度)であり原因の確定ではありません。最終判定は担当エンジニアの承認が必要です。",
  ),
  "Cavity 중심(중앙값) 차이가 데이터 산포의 2배를 넘습니다 — 재현 여부를 확인할 필요가 있습니다 (원인 확정이 아니라 조사 우선순위).": L(
    "Cavity 중심(중앙값) 차이가 데이터 산포의 2배를 넘습니다 — 재현 여부를 확인할 필요가 있습니다 (원인 확정이 아니라 조사 우선순위).",
    "The cavity center (median) difference exceeds twice the data spread — worth checking for reproducibility (an investigation priority, not a confirmed cause).",
    "キャビティ中心(中央値)の差がデータばらつきの2倍を超えています — 再現性の確認が必要です(原因確定ではなく調査優先度)。",
  ),
  "Cavity 비교에는 Cavity별 2개 이상의 검사값이 필요합니다.": L(
    "Cavity 비교에는 Cavity별 2개 이상의 검사값이 필요합니다.",
    "Cavity comparison needs at least 2 inspection values per cavity.",
    "キャビティ比較にはキャビティごとに2件以上の検査値が必要です。",
  ),
  "관리한계는 실측(윈도우 이탈 제외) 데이터의 중위값 ± 3σ(강건 추정)이며 규격한계가 아닙니다. 이상 신호는 원인 확정이 아니라 조사 우선순위입니다.": L(
    "관리한계는 실측(윈도우 이탈 제외) 데이터의 중위값 ± 3σ(강건 추정)이며 규격한계가 아닙니다. 이상 신호는 원인 확정이 아니라 조사 우선순위입니다.",
    "Control limits are median ± 3σ (robust estimate) of measured data excluding window violations — not spec limits. Signals are investigation priorities, not confirmed causes.",
    "管理限界は実測(ウィンドウ逸脱除外)データの中央値 ± 3σ(ロバスト推定)であり規格限界ではありません。異常信号は原因確定ではなく調査優先度です。",
  ),
  "일정 오프셋 형태의 잔차 — 파라미터 편차 가능성": L(
    "일정 오프셋 형태의 잔차 — 파라미터 편차 가능성",
    "Constant-offset residual pattern — possible parameter deviation",
    "一定オフセット型の残差 — パラメータ偏差の可能性",
  ),
  "입력에 따라 증가하는 잔차 — 스케일/구조 오차 가능성": L(
    "입력에 따라 증가하는 잔차 — 스케일/구조 오차 가능성",
    "Input-proportional residual growth — possible scale/structure error",
    "入力に応じて増加する残差 — スケール/構造誤差の可能性",
  ),
  "잔차가 무작위 노이즈에 가까움 — 시험/정렬 확인 필요": L(
    "잔차가 무작위 노이즈에 가까움 — 시험/정렬 확인 필요",
    "Residuals close to random noise — check test setup/alignment",
    "残差がランダムノイズに近い — 試験/アライメント確認必要",
  ),
  "실측 커버 밖 예측 구간 포함 — 검증 범위 확인 필요": L(
    "실측 커버 밖 예측 구간 포함 — 검증 범위 확인 필요",
    "Includes predictions outside measured coverage — check the validated range",
    "実測カバー外の予測区間を含む — 検証範囲の確認必要",
  ),
  // backend rule message tails are handled in RULES below.

  // ── helper strings that seeded CSV/notes may surface ──
  "벤치 측정 데이터": L("벤치 측정 데이터", "Bench measurement data", "ベンチ計測データ"),
  "기구 해석 결과치 (곡선/토크)": L("기구 해석 결과치 (곡선/토크)", "Mechanical analysis results (curve/torque)", "機構解析結果値(曲線/トルク)"),
  "SPICE 스위프 결과치": L("SPICE 스위프 결과치", "SPICE sweep results", "SPICEスイープ結果値"),
  // model_review.py AI-06 finding detail/resolution
  "AI-inferred 관계는 승인 전까지 Gate Evidence로 사용할 수 없습니다.": L(
    "AI-inferred 관계는 승인 전까지 Gate Evidence로 사용할 수 없습니다.",
    "AI-inferred relations cannot be used as gate evidence until approved.",
    "AI推論関係は承認までGate Evidenceとして使用できません。",
  ),
  "각 인과관계를 검토해 human_approved로 승인하거나 제거하세요.": L(
    "각 인과관계를 검토해 human_approved로 승인하거나 제거하세요.",
    "Review each causal relation and approve it as human_approved or remove it.",
    "各因果関係を確認し、human_approvedで承認するか削除してください。",
  ),
  // schemas/doe.py target-band source + study disclaimer
  "데모 사양·합성 데이터": L("데모 사양·합성 데이터", "demo spec · synthetic data", "デモ仕様・合成データ"),
  "회귀·후보 비교는 확인 필요 정보이며, AI/최적화가 최종 해를 임의로 확정하지 않습니다. 후보 실행은 담당 엔지니어 승인 후 진행하세요.":
    L(
      "회귀·후보 비교는 확인 필요 정보이며, AI/최적화가 최종 해를 임의로 확정하지 않습니다. 후보 실행은 담당 엔지니어 승인 후 진행하세요.",
      "Regression and candidate comparison are check-required information; AI/optimization never finalizes a single solution on its own. Candidate runs proceed after the responsible engineer's approval.",
      "回帰・候補比較は確認要の情報であり、AI/最適化が最終解を独自に確定することはありません。候補の実行は担当エンジニアの承認後に進めてください。",
    ),
};

// Composed backend messages — regex per message with per-language templates.
// $1..$9 splice the captured groups; `g` entries already matched through
// seedTr get translated (operation names etc.), so rules call seedTr on the
// groups they want localized.
type Rule = { re: RegExp; en: (g: string[]) => string; ja: (g: string[]) => string };

const RULES: Rule[] = [
  {
    re: /^블록 '(.+)'에 단위가 없습니다 \(MV-01\)$/,
    en: (g) => `Block '${seedTr(g[0], "en")}' has no unit (MV-01)`,
    ja: (g) => `ブロック '${seedTr(g[0], "ja")}' に単位がありません (MV-01)`,
  },
  {
    re: /^블록 '(.+)'에 수식이 없습니다 \(MV-01\)$/,
    en: (g) => `Block '${seedTr(g[0], "en")}' has no equation (MV-01)`,
    ja: (g) => `ブロック '${seedTr(g[0], "ja")}' に数式がありません (MV-01)`,
  },
  {
    re: /^링크 '(.+)' 단위 차원 불일치 \(MV-02\)$/,
    en: (g) => `Link '${seedTr(g[0], "en")}' unit dimension mismatch (MV-02)`,
    ja: (g) => `リンク '${seedTr(g[0], "ja")}' 単位次元不一致 (MV-02)`,
  },
  {
    re: /^링크 '(.+)' 단위 확인 필요 \(MV-02\)$/,
    en: (g) => `Link '${seedTr(g[0], "en")}' unit check required (MV-02)`,
    ja: (g) => `リンク '${seedTr(g[0], "ja")}' 単位確認必要 (MV-02)`,
  },
  {
    // model_review.py AI-06 finding title
    re: /^사람 승인 전 AI 추론 인과관계 (\d+)건 \(AI-06\)$/,
    en: (g) => `${g[0]} AI-inferred causal relation(s) awaiting human approval (AI-06)`,
    ja: (g) => `人間承認前のAI推論因果関係 ${g[0]}件 (AI-06)`,
  },
  {
    re: /^(.+) 공정 윈도우 이탈$/,
    en: (g) => `${seedTr(g[0], "en")} process window violation`,
    ja: (g) => `${seedTr(g[0], "ja")} 工程ウィンドウ逸脱`,
  },
  {
    re: /^이 Lot의 (.+) 실측값이 승인 윈도우를 벗어났습니다 \((.+)\)\. 공정조건과 품질특성의 관련성을 확인하세요\.$/,
    en: (g) =>
      `This lot's ${seedTr(g[0], "en")} measured value left the approved window (${g[1]}). Check the relation between process conditions and the quality characteristic.`,
    ja: (g) =>
      `このロットの${seedTr(g[0], "ja")}実測値が承認ウィンドウ外です (${g[1]})。工程条件と品質特性の関連性を確認してください。`,
  },
  {
    re: /^Cavity (.+) 편차 의심$/,
    en: (g) => `Cavity ${g[0]} deviation suspected`,
    ja: (g) => `キャビティ ${g[0]} 偏差疑い`,
  },
  {
    re: /^이 Lot의 검사값이 같은 금형의 다른 Cavity 분포 대비 유의하게 (높게|낮게) 나옵니다 \(Δ=(.+), 한계≈(.+)\)\. Cavity 치수·마모·보전 이력을 확인하세요\.$/,
    en: (g) =>
      `This lot's inspection values are significantly ${g[0] === "높게" ? "higher" : "lower"} than the other-cavity distribution of the same mold (Δ=${g[1]}, limit≈${g[2]}) — check cavity dimensions, wear and maintenance history.`,
    ja: (g) =>
      `このロットの検査値は同じ金型の他キャビティ分布より有意に${g[0] === "높게" ? "高く" : "低く"}出ています (Δ=${g[1]}, 限界≈${g[2]})。キャビティ寸法・摩耗・保全履歴を確認してください。`,
  },
  {
    re: /^원자재 Lot (.+) 공통성 의심$/,
    en: (g) => `Raw-material lot ${g[0]} commonality suspected`,
    ja: (g) => `原材料ロット ${g[0]} 共通性疑い`,
  },
  {
    re: /^동일 원자재 Lot를 사용한 다른 Lot에서도 불량이 기록되어 있습니다 \((\d+)건\)\. 자재 검사성적서와 공급이력을 확인하세요\.$/,
    en: (g) => `Other lots using the same raw-material lot also have recorded defects (${g[0]} cases) — check the material certificates and supply history.`,
    ja: (g) => `同じ原材料ロットを使用した他のロットにも不良が記録されています (${g[0]}件)。材料検査成績書と供給履歴を確認してください。`,
  },
  {
    re: /^표본수 부족\(기준 n=(\d+) < (\d+)\) — 관리한계를 산정하지 않았습니다\. (.+)$/,
    en: (g) => `Sample count too low (n=${g[0]} < ${g[1]}) — control limits not computed. ${seedTr(g[2], "en")}`,
    ja: (g) => `サンプル数不足(基準 n=${g[0]} < ${g[1]}) — 管理限界を算定しませんでした。${seedTr(g[2], "ja")}`,
  },
  {
    re: /^잔차 평균 (.+) 가 표준편차 (.+)의 2배를 넘습니다\. 모델 파라미터\(예: 물성·치수\)가 실측 대비 일정하게 치우쳤을 가능성이 있습니다\.$/,
    en: (g) =>
      `Residual mean ${g[0]} exceeds twice the standard deviation ${g[1]}. Model parameters (e.g. material properties, dimensions) may be consistently biased against measurements.`,
    ja: (g) =>
      `残差平均 ${g[0]} が標準偏差 ${g[1]} の2倍を超えています。モデルパラメータ(例: 物性・寸法)が実測に対して一貫してずれている可能性があります。`,
  },
  {
    re: /^잔차 기울기 (.+) 로 x에 따라 체계적으로 변합니다\. 선형 스케일 계수 미적합 또는 구조\(형상\) 단순화의 영향일 수 있습니다\.$/,
    en: (g) =>
      `Residual slope ${g[0]} varies systematically with x. A linear scale coefficient misfit or the effect of structural (geometry) simplification is possible.`,
    ja: (g) =>
      `残差の傾き ${g[0]} がxに応じて体系的に変化しています。線形スケール係数の未適合、または構造(形状)単純化の影響の可能性があります。`,
  },
  {
    re: /^체계적 성분 대비 변동이 (.+)배 큽니다\. 측정 노이즈, 커서 정렬\(x축 보간\), 시험 셋업 반복성을 먼저 확인하세요\.$/,
    en: (g) =>
      `Variation is ${g[0]}× larger than the systematic component. Check measurement noise, cursor alignment (x-axis interpolation) and test-setup repeatability first.`,
    ja: (g) =>
      `系統的成分より変動が${g[0]}倍大きいです。計測ノイズ、カーソル整合(x軸補間)、試験セットアップの繰返し性を先に確認してください。`,
  },
  {
    re: /^실측이 x=\[(.+)\] (.+)만 커버합니다\. 그 밖의 예측 구간은 검증된 것이 아니므로 상관 지표 해석에 주의하세요\.$/,
    en: (g) =>
      `Measurements only cover x=[${g[0]}] ${g[1]}. Predictions outside that range are not validated — interpret correlation metrics with care.`,
    ja: (g) =>
      `実測は x=[${g[0]}] ${g[1]} のみをカバーします。それ以外の予測区間は検証されていないため、相関指標の解釈に注意してください。`,
  },
  {
    re: /^(.+)=(.+) 가 유효 범위 \[(.+)\] (.+)을 벗어납니다$/,
    en: (g) => `${g[0]}=${g[1]} is outside the valid range [${g[2]}] ${g[3]}`,
    ja: (g) => `${g[0]}=${g[1]} が有効範囲 [${g[2]}] ${g[3]} を外れています`,
  },
];

/** Overlay one stored/composed string into the ui language; a miss returns
 * the original text unchanged (honest fallback for data added later). */
export function seedTr(text: string | null | undefined, lang: string | null | undefined): string {
  if (!text) return "";
  if (lang !== "ko") {
    const hit = EXACT[text];
    if (hit) return pickL(hit, lang);
    for (const rule of RULES) {
      const m = rule.re.exec(text);
      if (m) return (lang === "ja" ? rule.ja : rule.en)(m.slice(1));
    }
  }
  return text;
}

/** Render-time helper bound to the current ui language. */
export function makeSeedTr(lang: string | null | undefined) {
  return (text: string | null | undefined) => seedTr(text, lang);
}
