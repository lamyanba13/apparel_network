FROM node:24.18.0-alpine

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

COPY frontend ./frontend

EXPOSE 3000

CMD ["corepack", "pnpm", "--filter", "@fashion-network/frontend", "dev", "--hostname", "0.0.0.0", "--port", "3000"]
