import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

/**
 * BASE_ROUTE is the single source of truth for the app mount path.
 * Read from env (VITE_BASE_ROUTE preferred so it's exposed to the client too).
 * server.cjs reads the same value → dev/build/serve stay in sync.
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const rawBase = env.VITE_BASE_ROUTE || env.BASE_ROUTE || '/'
  const baseRoute = ('/' + rawBase.replace(/^\/+|\/+$/g, '')).replace(/\/+$/, '') || '/'

  return {
    // Vite `base` controls asset URLs in the built index.html — must match
    // the path the app is served under.
    base: baseRoute === '/' ? '/' : `${baseRoute}/`,
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    server: {
      // PORT (process env) thắng VITE_PORT — cho phép tool/preview gán port động.
      port: Number(process.env.PORT) || Number(env.VITE_PORT) || 7101,
      cors: true,
      origin: `http://localhost:${Number(process.env.PORT) || Number(env.VITE_PORT) || 7101}`,
      headers: {
        'Access-Control-Allow-Origin': '*',
      },
      // Dev-only API proxy. Matches the axios baseURL `/api`; target points
      // at your backend. Set VITE_API_PROXY_TARGET in `.env` (default
      // http://localhost:8000) — same-origin in the browser avoids CORS.
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
        },
      },
    },
  }
})
