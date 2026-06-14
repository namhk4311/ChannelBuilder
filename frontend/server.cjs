require("dotenv").config()
const express = require("express")
const cors = require("cors")
const path = require("path")

const app = express()
app.use(cors({ origin: "*" }))

// Healthcheck cho AgentBase Runtime
app.get("/health", (_, res) => res.status(200).json({ status: "ok" }))

// Proxy /api → backend (server-side). Browser chỉ gọi same-origin "/api" → né CORS
// + né việc endpoint AgentBase có thể gate token. API_PROXY_TARGET = URL public backend.
// require trong try/catch để local `pnpm serve` không có dep cũng không crash.
const API_TARGET = process.env.API_PROXY_TARGET || process.env.VITE_API_PROXY_TARGET
if (API_TARGET) {
  try {
    const { createProxyMiddleware } = require("http-proxy-middleware")
    app.use(
      createProxyMiddleware({
        target: API_TARGET,
        changeOrigin: true,
        secure: false,
        pathFilter: (pathname) => pathname.startsWith("/api"),
      })
    )
    console.log(`Proxy /api → ${API_TARGET}`)
  } catch (e) {
    console.warn(`http-proxy-middleware không nạp được (${e.message}) — /api sẽ không proxy`)
  }
} else {
  console.warn("API_PROXY_TARGET chưa set — /api sẽ không hoạt động")
}

// Normalize base path: ensure leading "/", strip trailing "/".
const rawBase = process.env.BASE_ROUTE || process.env.VITE_BASE_ROUTE || "/"
const BASE_PATH = ("/" + rawBase.replace(/^\/+|\/+$/g, "")).replace(/\/+$/, "") || "/"
const STATIC_MOUNT = BASE_PATH === "/" ? "/" : BASE_PATH
const SPA_ROUTE = BASE_PATH === "/" ? "/*splat" : `${BASE_PATH}/*splat`

app.use(STATIC_MOUNT, express.static(path.join(__dirname, "dist")))

app.get(SPA_ROUTE, function (_, res) {
  res.sendFile(path.join(__dirname, "dist", "index.html"))
})

const PORT = Number(process.env.PORT) || 7101
app.listen(PORT, () => {
  const suffix = BASE_PATH === "/" ? "" : BASE_PATH
  console.log(`Channel Builder serving at http://localhost:${PORT}${suffix}`)
})
