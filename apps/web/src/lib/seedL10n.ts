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

  // ── ASIC twin (seed_asic_twin + asic_gate_policy/asic_signal) ──
  // gate blockers (asic_gate_policy.py)
  "이 워크벤치의 ASIC 증적은 교육용 합성 데이터입니다. 실측 근거 없이는 출시 승인 게이트를 통과할 수 없습니다. (지시서 §15)": L(
    "이 워크벤치의 ASIC 증적은 교육용 합성 데이터입니다. 실측 근거 없이는 출시 승인 게이트를 통과할 수 없습니다. (지시서 §15)",
    "This workbench's ASIC evidence is educational synthetic data. Without measured backing it cannot pass the release-approval gate (spec §15).",
    "このワークベンチのASICエビデンスは教育用合成データです。実測の根拠がないまま出荷承認ゲートを通過することはできません (仕様書 §15)。",
  ),
  "보정 모델이 학습 데이터 범위를 벗어난 Corner/MC 결과가 있습니다. OOD 검토가 필요합니다.": L(
    "보정 모델이 학습 데이터 범위를 벗어난 Corner/MC 결과가 있습니다. OOD 검토가 필요합니다.",
    "A Corner/MC result falls outside the calibration model's training range — OOD review required.",
    "校正モデルの学習データ範囲を外れたCorner/MC結果があります。OODレビューが必要です。",
  ),
  // corner-study disclosure (asic_signal.py)
  "교육용 오류예산 전파 모델 (SYNTHETIC) — SPICE/TCAD 대체 아님": L(
    "교육용 오류예산 전파 모델 (SYNTHETIC) — SPICE/TCAD 대체 아님",
    "Educational error-budget propagation model (SYNTHETIC) — not a SPICE/TCAD substitute",
    "教育用エラーバジェット伝搬モデル (SYNTHETIC) — SPICE/TCADの代替ではない",
  ),
  // signal-chain blocks + notes (seed)
  "Shunt 저항 1 mΩ": L("Shunt 저항 1 mΩ", "Shunt resistor 1 mΩ", "シャント抵抗 1 mΩ"),
  "차동 증폭기 (G=50)": L("차동 증폭기 (G=50)", "Differential amplifier (G=50)", "差動増幅器 (G=50)"),
  "16-bit SAR ADC": L("16-bit SAR ADC", "16-bit SAR ADC", "16ビットSAR ADC"),
  "온도 보정 DSP": L("온도 보정 DSP", "Temperature-compensation DSP", "温度補償DSP"),
  "초기 테이프아웃안 — A0 마스크": L("초기 테이프아웃안 — A0 마스크", "Initial tape-out draft — mask A0", "初期テープアウト案 — マスクA0"),
  "r1 보정계수 갱신 + DSP FW 1.2.0 (ECO-001 반영 전 기준선)": L(
    "r1 보정계수 갱신 + DSP FW 1.2.0 (ECO-001 반영 전 기준선)",
    "r1 calibration-coefficient refresh + DSP FW 1.2.0 (baseline before ECO-001)",
    "r1較正係数更新 + DSP FW 1.2.0 (ECO-001反映前のベースライン)",
  ),
  // FA case (seed)
  "HTSL 1000h 후 site 3 감도 드리프트 -3.6% (규격 하한 98.5 mA/A 이탈)": L(
    "HTSL 1000h 후 site 3 감도 드리프트 -3.6% (규격 하한 98.5 mA/A 이탈)",
    "After 1000 h HTSL, site 3 sensitivity drifted -3.6% (below the 98.5 mA/A spec floor)",
    "HTSL 1000h後、site 3の感度が-3.6%ドリフト (規格下限98.5 mA/Aを逸脱)",
  ),
  "HTSL 125°C/1000h 바이어스 인가 후 상온 전기 시험에서 재현": L(
    "HTSL 125°C/1000h 바이어스 인가 후 상온 전기 시험에서 재현",
    "Reproduced in room-temperature electrical test after HTSL 125 °C/1000 h bias",
    "HTSL 125℃/1000hバイアス印加後の常温電気試験で再現",
  ),
  "site 3 감도 96.42 mA/A — 규격 하한 98.5 이탈, 타 site는 규격 내": L(
    "site 3 감도 96.42 mA/A — 규격 하한 98.5 이탈, 타 site는 규격 내",
    "Site 3 sensitivity 96.42 mA/A — below the 98.5 spec floor; other sites in spec",
    "site 3感度96.42 mA/A — 規格下限98.5を逸脱、他siteは規格内",
  ),
  "CSAM 분석에서 site 3의 2번 본드 패드 주변 층간 박리 확인": L(
    "CSAM 분석에서 site 3의 2번 본드 패드 주변 층간 박리 확인",
    "CSAM shows delamination around bond pad 2 of site 3",
    "CSAM分析でsite 3のボンドパッド2周辺の層間剥離を確認",
  ),
  "HTSL 이전 측정(pre-stress)에서는 5 site 모두 규격 내": L(
    "HTSL 이전 측정(pre-stress)에서는 5 site 모두 규격 내",
    "Pre-stress measurement: all 5 sites within spec",
    "HTSL前の測定(pre-stress)では5siteすべて規格内",
  ),
  "2번 본드 패드 히트싱크 응력 집중에 의한 와이어 본드 피로": L(
    "2번 본드 패드 히트싱크 응력 집중에 의한 와이어 본드 피로",
    "Wire-bond fatigue from heat-sink stress concentration on bond pad 2",
    "ボンドパッド2のヒートシンク応力集中によるワイヤボンド疲労",
  ),
  "몰드 컴파운드 수분 흡수에 의한 접속 부식": L(
    "몰드 컴파운드 수분 흡수에 의한 접속 부식",
    "Interconnect corrosion from moisture uptake of the mold compound",
    "モールド樹脂の吸湿による接続腐食",
  ),
  "HAST 통과 로트(CURR-LOT-2608C)에서는 동일 드리프트가 없음": L(
    "HAST 통과 로트(CURR-LOT-2608C)에서는 동일 드리프트가 없음",
    "No such drift in the HAST-passed lot (CURR-LOT-2608C)",
    "HAST合格ロット(CURR-LOT-2608C)では同じドリフトなし",
  ),
  "측정 시스템(테스터) 보정 이상": L("측정 시스템(테스터) 보정 이상", "Measurement-system (tester) calibration fault", "測定システム(テスター)校正異常"),
  "교차 측정에서도 site 3 드리프트 동일 재현 — 기기 원인 아님": L(
    "교차 측정에서도 site 3 드리프트 동일 재현 — 기기 원인 아님",
    "Cross-measurement reproduces the same site 3 drift — not the equipment",
    "交差測定でもsite 3ドリフトが同じ再現 — 設備起因ではない",
  ),
  "2번 본드 패드의 히트싱크 응력 집중에 의한 와이어 본드 피로 — HTSL 열사이클 중 패드 언더메탈 마이크로크랙이 성장해 접촉저항이 상승 (CSAM 박리 + 드리프트 온도의존성 재현으로 확인)": L(
    "2번 본드 패드의 히트싱크 응력 집중에 의한 와이어 본드 피로 — HTSL 열사이클 중 패드 언더메탈 마이크로크랙이 성장해 접촉저항이 상승 (CSAM 박리 + 드리프트 온도의존성 재현으로 확인)",
    "Wire-bond fatigue from heat-sink stress concentration on bond pad 2 — during HTSL thermal cycling the pad undermetal microcrack grew and raised contact resistance (confirmed by CSAM delamination + drift temperature dependence)",
    "ボンドパッド2のヒートシンク応力集中によるワイヤボンド疲労 — HTSL熱サイクル中にパッドアンダーメタルのマイクロクラックが成長し接触抵抗が上昇 (CSAM剥離+ドリフトの温度依存性再現で確認)",
  ),
  "패키지 설계·신뢰성 합의 (2026-09-12 RCA 리뷰)": L(
    "패키지 설계·신뢰성 합의 (2026-09-12 RCA 리뷰)",
    "Package design + reliability consensus (RCA review 2026-09-12)",
    "パッケージ設計・信頼性の合意 (2026-09-12 RCAレビュー)",
  ),
  // FA confirm tests (rendered in hypothesis brackets)
  "CSAM 층간 박리 확인": L("CSAM 층간 박리 확인", "CSAM delamination check", "CSAM層間剥離確認"),
  "드리프트 곡선 온도 의존성 재현": L("드리프트 곡선 온도 의존성 재현", "Reproduce drift-curve temperature dependence", "ドリフト曲線の温度依存性再現"),
  "HAST 재시험 비교": L("HAST 재시험 비교", "HAST retest comparison", "HAST再試験比較"),
  "교정 만료 여부 및 타 장비 교차 확인": L("교정 만료 여부 및 타 장비 교차 확인", "Check calibration expiry and cross-check on other equipment", "校正期限と他設備での交差確認"),
  // ECO (seed)
  "2번 본드 패드 히트싱크 완화 (A0→A1)": L(
    "2번 본드 패드 히트싱크 완화 (A0→A1)",
    "Bond pad 2 heat-sink relief (A0→A1)",
    "ボンドパッド2ヒートシンク緩和 (A0→A1)",
  ),
  "패드 언더메탈 두께 증가 + 와이어 본드 프로파일 변경. 테스트 프로그램은 site 3 HTSL 샘플링을 2배로 강화.": L(
    "패드 언더메탈 두께 증가 + 와이어 본드 프로파일 변경. 테스트 프로그램은 site 3 HTSL 샘플링을 2배로 강화.",
    "Thicker pad undermetal + revised wire-bond profile. Test program doubles site 3 HTSL sampling.",
    "パッドアンダーメタル厚増加+ワイヤボンドプロファイル変更。テストプログラムはsite 3のHTSLサンプリングを2倍に強化。",
  ),
  "본드 패드 언더메탈 0.8→1.2 µm": L("본드 패드 언더메탈 0.8→1.2 µm", "Bond pad undermetal 0.8→1.2 µm", "ボンドパッドアンダーメタル 0.8→1.2 µm"),
  "본드 프로파일 파라미터 3건 변경": L("본드 프로파일 파라미터 3건 변경", "3 bond-profile parameters changed", "ボンドプロファイルパラメータ3件変更"),
  "HTSL 샘플링 강화 (site 3 ×2)": L("HTSL 샘플링 강화 (site 3 ×2)", "HTSL sampling strengthened (site 3 ×2)", "HTSLサンプリング強化 (site 3 ×2)"),
  "패키지 변경 회귀: MC-002(신뢰성 여유) + A1 패키지 전기 시험": L(
    "패키지 변경 회귀: MC-002(신뢰성 여유) + A1 패키지 전기 시험",
    "Package-change regression: MC-002 (reliability margin) + A1 package electrical test",
    "パッケージ変更リグレッション: MC-002(信頼性マージン) + A1パッケージ電気試験",
  ),
  "site 3 재측정 99.99 mA/A — HTSL 재시험 3 lot 모두 규격 내 복원 확인": L(
    "site 3 재측정 99.99 mA/A — HTSL 재시험 3 lot 모두 규격 내 복원 확인",
    "Site 3 re-measured at 99.99 mA/A — all 3 HTSL retest lots restored within spec",
    "site 3再測定99.99 mA/A — HTSL再試験3ロットすべて規格内復帰を確認",
  ),
  "RCA 리뷰 패널 승인 (2026-09-14)": L("RCA 리뷰 패널 승인 (2026-09-14)", "RCA review panel approval (2026-09-14)", "RCAレビューパネル承認 (2026-09-14)"),
  // qualification plan + methods (seed)
  "전류 센서 ASIC 자동차용 G1 인증 매트릭스 (데모용 축소판: TC·TH·HTSL)": L(
    "전류 센서 ASIC 자동차용 G1 인증 매트릭스 (데모용 축소판: TC·TH·HTSL)",
    "Current-sensor ASIC automotive G1 qualification matrix (demo subset: TC·TH·HTSL)",
    "電流センサASIC車載G1認証マトリクス (デモ用縮小版: TC・TH・HTSL)",
  ),
  "AEC-Q100 TC (온도 사이클 -40↔125°C, 1000 cycle)": L(
    "AEC-Q100 TC (온도 사이클 -40↔125°C, 1000 cycle)",
    "AEC-Q100 TC (temperature cycle -40↔125 °C, 1000 cycles)",
    "AEC-Q100 TC (温度サイクル -40↔125℃、1000サイクル)",
  ),
  "AEC-Q100 TH (고온·고습 85°C/85%RH, 1000 h)": L(
    "AEC-Q100 TH (고온·고습 85°C/85%RH, 1000 h)",
    "AEC-Q100 TH (85 °C/85 %RH high temp & humidity, 1000 h)",
    "AEC-Q100 TH (高温高湿 85℃/85%RH、1000h)",
  ),
  "AEC-Q100 HTSL (고온 저장 125°C, 1000 h)": L(
    "AEC-Q100 HTSL (고온 저장 125°C, 1000 h)",
    "AEC-Q100 HTSL (high-temperature storage 125 °C, 1000 h)",
    "AEC-Q100 HTSL (高温保存 125℃、1000h)",
  ),
  "AEC-Q100 HTSL 재시험 (ECO A1 패키지, 1000 h)": L(
    "AEC-Q100 HTSL 재시험 (ECO A1 패키지, 1000 h)",
    "AEC-Q100 HTSL retest (ECO A1 package, 1000 h)",
    "AEC-Q100 HTSL再試験 (ECO A1パッケージ、1000h)",
  ),
  "ECO-001 효과 검증 재시험": L("ECO-001 효과 검증 재시험", "ECO-001 effectiveness-verification retest", "ECO-001効果検証再試験"),
  // safety trace (seed)
  "과전류를 정상 전류로 보고해서는 안 된다 (ASIL B)": L(
    "과전류를 정상 전류로 보고해서는 안 된다 (ASIL B)",
    "Overcurrent must never be reported as normal current (ASIL B)",
    "過電流を正常電流として報告してはならない (ASIL B)",
  ),
  "출력 클램프 + /FAULT low": L("출력 클램프 + /FAULT low", "Output clamp + /FAULT low", "出力クランプ + /FAULT low"),
  "측정 체인 이상을 200 ms 이내에 감지하여 safe state로 진입할 것": L(
    "측정 체인 이상을 200 ms 이내에 감지하여 safe state로 진입할 것",
    "Detect measurement-chain faults within 200 ms and enter the safe state",
    "測定チェーン異常を200ms以内に検出しsafe stateへ移行すること",
  ),
  "범위·경향 감시 (DSP 워치독 + 플라우저리 한정자)": L(
    "범위·경향 감시 (DSP 워치독 + 플라우저리 한정자)",
    "Range/trend monitoring (DSP watchdog + plausibility qualifier)",
    "範囲・傾向監視 (DSPウォッチドッグ+妥当性修飾子)",
  ),
  "ADC 출력 범위검사 + 션트 개락 감지 (TSR)": L(
    "ADC 출력 범위검사 + 션트 개락 감지 (TSR)",
    "ADC output range check + shunt open detection (TSR)",
    "ADC出力範囲検査+シャント断線検出 (TSR)",
  ),
  "이중 범위 한정자 + 기준전원 이중화 비교": L(
    "이중 범위 한정자 + 기준전원 이중화 비교",
    "Dual-range qualifier + redundant reference-source comparison",
    "デュアルレンジ修飾子+基準電源二重化比較",
  ),
  "션트 개락 감지 회로: 전류원 바이어스 + 컴퍼레이터 임계 0.9×FS": L(
    "션트 개락 감지 회로: 전류원 바이어스 + 컴퍼레이터 임계 0.9×FS",
    "Shunt-open detection circuit: current-source bias + comparator threshold 0.9×FS",
    "シャント断線検出回路: 電流源バイアス+コンパレータしきい値0.9×FS",
  ),
  "개락 감지 컴퍼레이터": L("개락 감지 컴퍼레이터", "Open-detection comparator", "断線検出コンパレータ"),
  // FMEDA + fault injection (seed)
  "션트 개락 (Open shunt)": L("션트 개락 (Open shunt)", "Shunt open", "シャント断線 (Open shunt)"),
  "ADC 출력 고정 (Stuck output)": L("ADC 출력 고정 (Stuck output)", "ADC output stuck", "ADC出力固定 (Stuck output)"),
  "기준전원 드리프트 (Reference drift)": L("기준전원 드리프트 (Reference drift)", "Reference-source drift", "基準電源ドリフト (Reference drift)"),
  "수치는 교육용 합성값입니다 (SYNTHETIC)": L(
    "수치는 교육용 합성값입니다 (SYNTHETIC)",
    "Values are educational synthetic figures (SYNTHETIC)",
    "数値は教育用合成値です (SYNTHETIC)",
  ),
  "HIL 전류 스텝 주입": L("HIL 전류 스텝 주입", "HIL current-step injection", "HIL電流ステップ注入"),
  "150 A 과전류 스텝 (정격 100 A, 500 ms 유지)": L(
    "150 A 과전류 스텝 (정격 100 A, 500 ms 유지)",
    "150 A overcurrent step (rated 100 A, held 500 ms)",
    "150A過電流ステップ (定格100A、500ms保持)",
  ),
  "100 ms 이내 /FAULT low + 출력 클램프 (safe state 진입)": L(
    "100 ms 이내 /FAULT low + 출력 클램프 (safe state 진입)",
    "/FAULT low within 100 ms + output clamp (safe-state entry)",
    "100ms以内に/FAULT low+出力クランプ (safe state移行)",
  ),
  "87 ms 내 /FAULT low + 클램프 확인 (5회 반복 모두 통과)": L(
    "87 ms 내 /FAULT low + 클램프 확인 (5회 반복 모두 통과)",
    "/FAULT low + clamp confirmed at 87 ms (all 5 repetitions passed)",
    "87ms以内に/FAULT low+クランプ確認 (5回反復すべて合格)",
  ),
  // measurement CSV parser findings (routers/asic.py _parse_measurement_csv)
  "파일이 행 경계에서 끝나지 않습니다(쓰기 중단 의심)": L(
    "파일이 행 경계에서 끝나지 않습니다(쓰기 중단 의심)",
    "File does not end on a row boundary (possible write interruption)",
    "ファイルが行境界で終わっていません(書き込み中断の疑い)",
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

  // ── ASIC gate blockers (asic_gate_policy.py) — only composed when present ──
  {
    re: /^교정 유효기간이 만료된 장비의 측정 (\d+)건이 증적에 포함되어 있습니다\.$/,
    en: (g) => `Evidence includes ${g[0]} measurement(s) taken on equipment past its calibration expiry.`,
    ja: (g) => `エビデンスに校正期限切れ設備での測定が${g[0]}件含まれています。`,
  },
  {
    re: /^증적이 여러 설계 리비전\((.+)\)에 걸쳐 있습니다\. 하나의 리비전으로 재증적화해야 합니다\.$/,
    en: (g) => `Evidence spans multiple design revisions (${g[0]}) — re-evidence on a single revision.`,
    ja: (g) => `エビデンスが複数の設計リビジョン(${g[0]})にまたがっています。単一リビジョンでの再エビデンス化が必要です。`,
  },
  {
    re: /^신뢰성 시험 실패 (\d+)건의 RCA 승인이 열려 있습니다\.$/,
    en: (g) => `${g[0]} reliability-test failure(s) still await RCA approval.`,
    ja: (g) => `信頼性試験不合格${g[0]}件のRCA承認が未完了です。`,
  },
  {
    re: /^유효기간이 지난 웨이버 (\d+)건이 있습니다\.$/,
    en: (g) => `${g[0]} waiver(s) past their expiry.`,
    ja: (g) => `期限切れのウェーバーが${g[0]}件あります。`,
  },
  {
    // asic_signal.py OOD reason — "<output>: 시험 온도 T°C 가 보정 범위 [a, b]°C를 벗어납니다"
    re: /^([A-Za-z0-9_]+): 시험 온도 (.+)°C 가 보정 범위 \[(.+), (.+)\]°C를 벗어납니다$/,
    en: (g) => `${g[0]}: test temperature ${g[1]}°C is outside the calibration range [${g[2]}, ${g[3]}]°C`,
    ja: (g) => `${g[0]}: 試験温度${g[1]}℃が校正範囲 [${g[2]}, ${g[3]}]℃を外れています`,
  },
  // measurement CSV parser findings (routers/asic.py)
  {
    re: /^(\d+)행이 불완전합니다\(부분 파일 의심\)$/,
    en: (g) => `Row ${g[0]} is incomplete (possible partial file)`,
    ja: (g) => `${g[0]}行目が不完全です(部分ファイルの疑い)`,
  },
  {
    re: /^value '(.+)'를 숫자로 해석할 수 없습니다$/,
    en: (g) => `Value '${g[0]}' cannot be parsed as a number`,
    ja: (g) => `値 '${g[0]}' を数値として解釈できません`,
  },
  {
    re: /^(.+)\/site=(\S+) 조합이 중복됩니다$/,
    en: (g) => `Duplicate ${g[0]}/site=${g[1]} combination`,
    ja: (g) => `${g[0]}/site=${g[1]} の組合せが重複しています`,
  },
  {
    re: /^(\d+)행의 타임스탬프가 이전 행보다 과거입니다$/,
    en: (g) => `Row ${g[0]}'s timestamp is earlier than the previous row`,
    ja: (g) => `${g[0]}行目のタイムスタンプが前の行より過去です`,
  },
  {
    re: /^temperature_c '(.+)'를 해석할 수 없습니다$/,
    en: (g) => `Cannot parse temperature_c '${g[0]}'`,
    ja: (g) => `temperature_c '${g[0]}' を解釈できません`,
  },
];

// ── ASIC R2 (seed_asic_r2 + asic_trade/asic_testprog + trade-study router) ──
// (appended to EXACT before seedTr; see the const above — TS hoisting does
// not apply, so these live in the object literal's tail via this spread)

const EXACT_R2: Record<string, LStr> = {
  // trade-study / option prose (seed_asic_r2)
  "55nm 균형안 — pkg_tooling TBD (0으로 계산되지 않음)": L(
    "55nm 균형안 — pkg_tooling TBD (0으로 계산되지 않음)",
    "55nm balanced option — pkg_tooling TBD (never computed as zero)",
    "55nmバランス案 — pkg_tooling TBD (0として計算しない)",
  ),
  "28nm 고정밀 안 — NRE 높지만 단가·정밀도 우위": L(
    "28nm 고정밀 안 — NRE 높지만 단가·정밀도 우위",
    "28nm high-precision option — higher NRE, better unit cost & precision",
    "28nm高精度案 — NREは高いが単価・精度に有利",
  ),
  "90nm 저가안 — 기술·공급 리스크로 가중 점수 하락 예상": L(
    "90nm 저가안 — 기술·공급 리스크로 가중 점수 하락 예상",
    "90nm low-cost option — weighted score expected to drop on tech/supply risk",
    "90nm低コスト案 — 技術・供給リスクで加重スコア低下を見込み",
  ),
  "가중 점수 1위 옵션으로 확정 — TBD 항목 해소 후 1차 벤더 계약 진행": L(
    "가중 점수 1위 옵션으로 확정 — TBD 항목 해소 후 1차 벤더 계약 진행",
    "Confirmed as the top weighted-score option — vendor contract proceeds after TBDs resolve",
    "加重スコア1位のオプションで確定 — TBD解消後に1次ベンダー契約を進める",
  ),
  "견적 대기 — 2차 벤더 협상 중 (TBD 규칙 시연)": L(
    "견적 대기 — 2차 벤더 협상 중 (TBD 규칙 시연)",
    "Quote pending — second-vendor negotiation in progress (TBD rule demo)",
    "見積待ち — 2次ベンダー交渉中 (TBDルールの実演)",
  ),
  "G2 등급 라인 가용성": L("G2 등급 라인 가용성", "G2-grade line availability", "G2グレードラインの可用性"),
  "단일 공급망 — 2차 소스 없음": L(
    "단일 공급망 — 2차 소스 없음",
    "Single supply chain — no second source",
    "単一サプライチェーン — セカンドソースなし",
  ),
  "단가 협정 전 환율 변동": L("단가 협정 전 환율 변동", "FX movement before price agreement", "価格協定前の為替変動"),
  "200mm 웨이퍼 공급 변동": L("200mm 웨이퍼 공급 변동", "200mm wafer supply fluctuation", "200mmウェハ供給変動"),
  // module prose (asic_trade.py / asic_testprog.py / routers/asic.py)
  "TBD 항목은 0으로 계산되지 않습니다 — 해당 옵션의 합계/축은 null로 표시되고 부분 점수는 partial_score로만 제공됩니다.": L(
    "TBD 항목은 0으로 계산되지 않습니다 — 해당 옵션의 합계/축은 null로 표시되고 부분 점수는 partial_score로만 제공됩니다.",
    "TBD entries are never computed as zero — the option's totals/axes stay null and only a partial_score is offered.",
    "TBD項目は0として計算されません — 当該オプションの合計/軸はnullで表示され、部分スコアはpartial_scoreでのみ提供されます。",
  ),
  "cost_rate_per_site_hour 미확정 flow의 원가는 null(TBD)로 표시되며 0으로 계산되지 않습니다.": L(
    "cost_rate_per_site_hour 미확정 flow의 원가는 null(TBD)로 표시되며 0으로 계산되지 않습니다.",
    "A flow without a cost_rate_per_site_hour shows cost as null (TBD) — never computed as zero.",
    "cost_rate_per_site_hourが未確定のフローの原価はnull(TBD)で表示され、0として計算されません。",
  ),
  "동일 limits로 wafer sort에서 이미 검출 — final test 반복은 검토 후 제거 가능": L(
    "동일 limits로 wafer sort에서 이미 검출 — final test 반복은 검토 후 제거 가능",
    "Already detected at wafer sort with identical limits — the final-test repeat can be removed after review",
    "同一limitsでウェハソートで検出済み — ファイナルテストの反復はレビュー後に削除可能",
  ),
  "trim/cal·bin 등 목적이 다른 항목 또는 limits 상이 — 제거 대상 아님": L(
    "trim/cal·bin 등 목적이 다른 항목 또는 limits 상이 — 제거 대상 아님",
    "Different purpose (trim/cal, bin) or different limits — not a removal candidate",
    "トリム/較正・ビンなど目的が異なる項目またはlimits不一致 — 削除対象ではない",
  ),
  "wafer sort에서 커버되는 결함 클래스가 final test에서 재확인되지 않음": L(
    "wafer sort에서 커버되는 결함 클래스가 final test에서 재확인되지 않음",
    "A defect class covered at wafer sort is not re-verified at final test",
    "ウェハソートでカバーされる欠陥クラスがファイナルテストで再確認されていない",
  ),
  // trade-study panel surface (titles · foundries · risks the UI renders)
  "전류 센서 ASIC 공정/파트너 선택 (2026-09)": L(
    "전류 센서 ASIC 공정/파트너 선택 (2026-09)",
    "Current-sensor ASIC process/partner selection (2026-09)",
    "電流センサーASIC工程/パートナー選定 (2026-09)",
  ),
  "마스크 리드타임 변동": L(
    "마스크 리드타임 변동",
    "Mask lead-time fluctuation",
    "マスクリードタイム変動",
  ),
  "F1 Fab (교육용 가명)": L(
    "F1 Fab (교육용 가명)",
    "F1 Fab (educational alias)",
    "F1 Fab (教育用仮名)",
  ),
  "F2 Fab (교육용 가명)": L(
    "F2 Fab (교육용 가명)",
    "F2 Fab (educational alias)",
    "F2 Fab (教育用仮名)",
  ),
  "F3 Fab (교육용 가명)": L(
    "F3 Fab (교육용 가명)",
    "F3 Fab (educational alias)",
    "F3 Fab (教育用仮名)",
  ),
  "Contact 전도성 확인": L(
    "Contact 전도성 확인",
    "Contact continuity check",
    "Contact 導通確認",
  ),
  "DC 파라미터 (오프셋)": L(
    "DC 파라미터 (오프셋)",
    "DC parameters (offset)",
    "DC パラメータ (オフセット)",
  ),
  "감도 스윕 (100 A 등가)": L(
    "감도 스윕 (100 A 등가)",
    "Sensitivity sweep (100 A equiv.)",
    "感度スイープ (100 A 等価)",
  ),
  "오프셋 트림/캘리브레이션": L(
    "오프셋 트림/캘리브레이션",
    "Offset trim/calibration",
    "オフセット トリム/キャリブレーション",
  ),
  "최종 빈 분류": L(
    "최종 빈 분류",
    "Final bin classification",
    "最終ビン分類",
  ),
  "ADC 블록 (G=8.0)": L("ADC 블록 (G=8.0)", "ADC block (G=8.0)", "ADC ブロック (G=8.0)"),
  "AFE 블록 (G=12.5)": L("AFE 블록 (G=12.5)", "AFE block (G=12.5)", "AFE ブロック (G=12.5)"),
  "HUM 블록 (G=9.0)": L("HUM 블록 (G=9.0)", "HUM block (G=9.0)", "HUM ブロック (G=9.0)"),
  "LPF 블록 (G=5.5)": L("LPF 블록 (G=5.5)", "LPF block (G=5.5)", "LPF ブロック (G=5.5)"),
  "RIPPLE 블록 (G=22.0)": L("RIPPLE 블록 (G=22.0)", "RIPPLE block (G=22.0)", "RIPPLE ブロック (G=22.0)"),
  "TEMP 블록 (G=4.0)": L("TEMP 블록 (G=4.0)", "TEMP block (G=4.0)", "TEMP ブロック (G=4.0)"),
  "Capacitive Sensing ASIC 센서 프론트엔드": L(
    "Capacitive Sensing ASIC 센서 프론트엔드",
    "Capacitive Sensing ASIC sensor frontend",
    "Capacitive Sensing ASIC センサーフロントエンド",
  ),
  "Motor Ripple Counter 센서 프론트엔드": L(
    "Motor Ripple Counter 센서 프론트엔드",
    "Motor Ripple Counter sensor frontend",
    "Motor Ripple Counter センサーフロントエンド",
  ),
  "Environmental Sensor ASIC 센서 프론트엔드": L(
    "Environmental Sensor ASIC 센서 프론트엔드",
    "Environmental Sensor ASIC sensor frontend",
    "Environmental Sensor ASIC センサーフロントエンド",
  ),
  "Capacitive Sensing ASIC 공정 선택 검토 (P1-07 팩)": L(
    "Capacitive Sensing ASIC 공정 선택 검토 (P1-07 팩)",
    "Capacitive Sensing ASIC process selection review (P1-07 pack)",
    "Capacitive Sensing ASIC プロセス選定検討 (P1-07 パック)",
  ),
  "Motor Ripple Counter 공정 선택 검토 (P1-07 팩)": L(
    "Motor Ripple Counter 공정 선택 검토 (P1-07 팩)",
    "Motor Ripple Counter process selection review (P1-07 pack)",
    "Motor Ripple Counter プロセス選定検討 (P1-07 パック)",
  ),
  "Environmental Sensor ASIC 공정 선택 검토 (P1-07 팩)": L(
    "Environmental Sensor ASIC 공정 선택 검토 (P1-07 팩)",
    "Environmental Sensor ASIC process selection review (P1-07 pack)",
    "Environmental Sensor ASIC プロセス選定検討 (P1-07 パック)",
  ),
  "DC 파라미터": L("DC 파라미터", "DC parameters", "DC パラメータ"),
  "OSAT-K1 (교육용 가명)": L("OSAT-K1 (교육용 가명)", "OSAT-K1 (educational alias)", "OSAT-K1 (教育用仮名)"),
  "Subcon-X (교육용 가명)": L("Subcon-X (교육용 가명)", "Subcon-X (educational alias)", "Subcon-X (教育用仮名)"),
  "P1-07 검증 팩 옵션 (교육용 가명·합성 단가)": L(
    "P1-07 검증 팩 옵션 (교육용 가명·합성 단가)",
    "P1-07 verification pack option (educational alias, synthetic unit price)",
    "P1-07 検証パック オプション (教育用仮名・合成単価)",
  ),
};

// merge into the EXACT table above (the spread keeps one lookup for seedTr)
Object.assign(EXACT, EXACT_R2);

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
