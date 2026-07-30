#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
cd "$repository_root"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker with Compose v2 is required." >&2
  exit 1
fi

if [ ! -f .env.development ]; then
  cp .env.example .env.development
  echo "Created .env.development from .env.example."
fi

docker compose config --quiet
docker compose up --build --detach
docker compose --profile tools run --rm verify

echo "Fashion Network is ready at http://localhost"
