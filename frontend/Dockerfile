# syntax=docker/dockerfile:1.6

# ---- Build stage ----
FROM node:22-alpine AS build
WORKDIR /app

RUN corepack enable && corepack prepare pnpm@11 --activate

ARG ENVIRONMENT

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

RUN pnpm install --frozen-lockfile

# Copy source (.dockerignore strips local env files)
COPY . .

# Copy the env file for the target environment into .env so Vite picks it up
COPY .env .env

RUN pnpm build

# ---- Runtime stage ----
FROM node:22-alpine AS runtime
WORKDIR /app

ARG ENVIRONMENT

ENV NODE_ENV=production

# Only server.cjs runtime deps — no app bundling happens here.
RUN npm init -y >/dev/null && \
    npm install --omit=dev --silent express@^5 cors@^2 dotenv@^17 && \
    npm cache clean --force

COPY --from=build /app/dist ./dist
COPY .env.${ENVIRONMENT} .env
COPY server.cjs ./

EXPOSE 7101

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- "http://localhost:${PORT}${BASE_ROUTE:-/}" >/dev/null 2>&1 || exit 1

CMD ["node", "server.cjs"]
