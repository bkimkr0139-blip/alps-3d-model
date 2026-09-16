import { useEffect, useState } from "react";

// Shared 820px breakpoint — the mobile flattening CSS in index.css keys off
// the same width, and layout branches (cockpit mode, drawer placement) key
// off this hook.
export function useIsMobile(): boolean {
  const [mobile, setMobile] = useState(() => window.matchMedia("(max-width: 820px)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 820px)");
    const onChange = () => setMobile(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return mobile;
}
