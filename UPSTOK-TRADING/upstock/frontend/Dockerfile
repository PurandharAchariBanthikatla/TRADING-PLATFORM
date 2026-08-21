# syntax=docker/dockerfile:1.7
FROM node:20.18.1-bookworm-slim AS base
ENV NODE_ENV=production

# --- deps: install once, cached across builds ---
FROM base AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --include=dev

# --- builder: compile the standalone Next.js output ---
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- runtime: minimal, non-root, only the standalone server output ---
FROM base AS runtime
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 PORT=3000

RUN groupadd --gid 10001 nodegroup \
    && useradd --uid 10001 --gid nodegroup --shell /usr/sbin/nologin --create-home nodeuser \
    && apt-get update && apt-get install -y --no-install-recommends curl=7.88.1-10+deb12u12 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder --chown=nodeuser:nodegroup /app/.next/standalone ./
COPY --from=builder --chown=nodeuser:nodegroup /app/.next/static ./.next/static
COPY --from=builder --chown=nodeuser:nodegroup /app/public ./public

USER nodeuser

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD curl --fail http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
