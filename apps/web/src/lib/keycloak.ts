import Keycloak from "keycloak-js";

// Same-origin, not an absolute env-configured host: Keycloak is reverse-
// proxied under /realms and /resources on whatever origin served this page
// (local gateway at :8090, or the public tunnel domain) — see
// infra/nginx/local-gateway.conf and AGENTS.md's M7 section. A hardcoded
// "http://localhost:8081" would 404 the moment this is opened from anywhere
// other than this Mac.
export const keycloak = new Keycloak({
  url: window.location.origin,
  realm: import.meta.env.VITE_KEYCLOAK_REALM,
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID,
});

let initPromise: Promise<boolean> | null = null;

export function initKeycloak(): Promise<boolean> {
  if (!initPromise) {
    initPromise = keycloak.init({ onLoad: "login-required", pkceMethod: "S256" });
  }
  return initPromise;
}
