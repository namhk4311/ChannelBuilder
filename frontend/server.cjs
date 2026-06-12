require("dotenv").config()
const express = require("express")
const cors = require("cors")
const path = require("path")

const app = express()
app.use(cors({ origin: '*' }))

// Normalize base path: ensure leading "/", strip trailing "/".
// Reads same env as vite (VITE_BASE_ROUTE) so dev/build/serve stay in sync.
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
