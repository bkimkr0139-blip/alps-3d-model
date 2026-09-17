// AXOS 피드백 버튼이 자동 기록하는 "화면 컨텍스트".
// 이 앱은 라우터가 없고 centerTab이 곧 경로다 — 탭별 목적·메뉴 라벨 키를 여기서
// 정의해 위젯이 제출 페이로드(source_route/source_menu/화면 목적)를 채운다.
// 라벨 텍스트는 i18n(purpose.* / panels.*)으로 3 로케일 동기화.

// i18next의 리터럴 키 타입 그대로 — t()의 타입 검사를 통과시킨다.
type MenuKey =
  | "panels.viewer3d"
  | "panels.testbench"
  | "panels.sysmodel"
  | "panels.proctwin"
  | "panels.air"
  | "panels.eda"
  | "panels.asic"
  | "panels.docs";
type PurposeKey =
  | "axos.purpose.model"
  | "axos.purpose.bench"
  | "axos.purpose.sysmodel"
  | "axos.purpose.proc"
  | "axos.purpose.air"
  | "axos.purpose.eda"
  | "axos.purpose.asic"
  | "axos.purpose.docs";

export function screenContextOf(tab: string): { route: string; menuKey: MenuKey; purposeKey: PurposeKey } {
  const route = `/${tab}`;
  switch (tab) {
    case "model":
      return { route, menuKey: "panels.viewer3d", purposeKey: "axos.purpose.model" };
    case "bench":
      return { route, menuKey: "panels.testbench", purposeKey: "axos.purpose.bench" };
    case "sysmodel":
      return { route, menuKey: "panels.sysmodel", purposeKey: "axos.purpose.sysmodel" };
    case "proc":
      return { route, menuKey: "panels.proctwin", purposeKey: "axos.purpose.proc" };
    case "air":
      return { route, menuKey: "panels.air", purposeKey: "axos.purpose.air" };
    case "eda":
      return { route, menuKey: "panels.eda", purposeKey: "axos.purpose.eda" };
    case "asic":
      return { route, menuKey: "panels.asic", purposeKey: "axos.purpose.asic" };
    default:
      return { route, menuKey: "panels.docs", purposeKey: "axos.purpose.docs" };
  }
}
