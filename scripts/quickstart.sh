#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$root"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Docker with the Compose plugin is required for make quickstart." >&2
  exit 2
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "OpenSSL is required to generate local development secrets." >&2
  exit 2
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from deterministic development defaults."
fi

set_value() {
  key=$1
  value=$2
  temporary=".env.tmp.$$"
  awk -v key="$key" -v value="$value" '
    BEGIN { found = 0 }
    index($0, key "=") == 1 { print key "=" value; found = 1; next }
    { print }
    END { if (!found) print key "=" value }
  ' .env > "$temporary"
  mv "$temporary" .env
}

read_value() {
  awk -F= -v key="$1" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' .env
}

backend_port=${BACKEND_PORT:-$(read_value BACKEND_PORT)}
frontend_port=${FRONTEND_PORT:-$(read_value FRONTEND_PORT)}
backend_port=${backend_port:-8000}
frontend_port=${frontend_port:-3000}

if [ -z "$(read_value SESSION_HMAC_SECRET)" ]; then
  set_value SESSION_HMAC_SECRET "$(openssl rand -hex 32)"
fi
if [ -z "$(read_value AI_CACHE_HMAC_SECRET)" ]; then
  set_value AI_CACHE_HMAC_SECRET "$(openssl rand -hex 32)"
fi
if [ -z "$(read_value DATA_ENCRYPTION_KEY)" ]; then
  set_value DATA_ENCRYPTION_KEY "$(openssl rand -base64 32 | tr -d '\n')"
fi

mkdir -p swiftKnowledgeBase
knowledge_fetched=false
if [ -n "${KNOWLEDGE_BUNDLE_URL:-}" ] || [ -n "${KNOWLEDGE_BUNDLE_PATH:-}" ]; then
  "$root/scripts/knowledge-fetch.sh"
  set_value KNOWLEDGE_MODE local
  set_value KNOWLEDGE_AUTO_SYNC_ON_START false
  knowledge_fetched=true
fi

docker compose up --build --detach

attempt=0
until docker compose exec -T backend python -c \
  "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health/ready')" \
  >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 90 ]; then
    docker compose logs --tail=100 backend frontend
    echo "Quickstart timed out waiting for backend readiness." >&2
    exit 1
  fi
  sleep 2
done

if [ "$knowledge_fetched" = true ]; then
  docker compose exec -T backend python -m app.knowledge_base sync --quiet
fi

echo "Financial Message Studio is ready: http://localhost:${frontend_port}"
echo "Backend readiness: http://localhost:${backend_port}/api/health/ready"
