# syntax=docker/dockerfile:1.6
# VNG Insider — frontend (React/Vite) cho AgentBase Runtime.
# server.cjs serve static + proxy /api → backend. Contract AgentBase: port 8080 + /health.

# ---- Build stage ----
FROM node:22-alpine AS build
WORKDIR /app

RUN corepack enable && corepack prepare pnpm@11 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

# Build với default env: VITE_API_BASE_URL=/api, VITE_BASE_ROUTE=/.
# Browser gọi same-origin "/api"; server.cjs proxy sang backend lúc runtime
# (qua API_PROXY_TARGET) → không cần nhúng URL backend vào bundle.
RUN pnpm build

# ---- Runtime stage ----
FROM node:22-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=8080

# Chỉ deps cho server.cjs (serve static + proxy /api) — image gọn.
RUN npm init -y >/dev/null && \
    npm install --omit=dev --silent express@^5 cors@^2 dotenv@^17 http-proxy-middleware@^3 && \
    npm cache clean --force

COPY --from=build /app/dist ./dist
COPY server.cjs ./

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- "http://localhost:${PORT}/health" >/dev/null 2>&1 || exit 1

CMD ["node", "server.cjs"]
