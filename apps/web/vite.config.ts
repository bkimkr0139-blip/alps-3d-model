import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Requests reach Vite via the local nginx gateway (infra/nginx/local-
    // gateway.conf) and, in production-style demo use, the frps tunnel
    // (infra/frp/frpc.toml) — both rewrite the Host header, which Vite's
    // dev-server DNS-rebinding protection otherwise rejects with a 403.
    allowedHosts: ['localhost', 'alps-twin.wizbase.ai.kr'],
  },
})
