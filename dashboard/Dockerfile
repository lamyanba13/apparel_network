FROM node:24.18.0-alpine AS dependencies

ENV COREPACK_HOME=/corepack \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /workspace

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/package.json ./frontend/package.json
COPY dashboard/package.json ./dashboard/package.json
RUN --mount=type=cache,id=fashion-network-pnpm,target=/pnpm/store \
    corepack pnpm config set store-dir /pnpm/store \
    && corepack pnpm install --frozen-lockfile


FROM dependencies AS development

COPY dashboard ./dashboard

EXPOSE 3000

CMD ["corepack", "pnpm", "--filter", "@fashion-network/dashboard", "dev", "--hostname", "0.0.0.0", "--port", "3000"]


FROM dependencies AS builder

COPY dashboard ./dashboard
RUN corepack pnpm --filter @fashion-network/dashboard build


FROM node:24.18.0-alpine AS production

ENV HOSTNAME=0.0.0.0 \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

WORKDIR /app

RUN rm -rf \
    /opt/yarn-v1.22.22 \
    /usr/local/lib/node_modules/corepack \
    /usr/local/lib/node_modules/npm \
    && rm -f \
    /usr/local/bin/corepack \
    /usr/local/bin/npm \
    /usr/local/bin/npx \
    /usr/local/bin/pnpm \
    /usr/local/bin/pnpx \
    /usr/local/bin/yarn \
    /usr/local/bin/yarnpkg

COPY --from=builder --chown=node:node /workspace/dashboard/.next/standalone ./
COPY --from=builder --chown=node:node /workspace/dashboard/.next/static ./dashboard/.next/static
COPY --from=builder --chown=node:node /workspace/dashboard/public ./dashboard/public

USER node

EXPOSE 3000

CMD ["node", "dashboard/server.js"]
