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
if [ -f swiftKnowledgeBase/source-manifest.json ]; then
  # The knowledge base is committed through Git LFS. A clone made without the LFS client
  # holds pointer files; fetch the real bytes now, and refuse to start a studio that would
  # index 130-byte pointers as if they were standards documents.
  pointer_count=$(grep -rl --include='*.pdf' --include='*.xsd' --include='*.zip' \
    'version https://git-lfs.github.com/spec/v1' swiftKnowledgeBase 2>/dev/null | wc -l | tr -d ' ')
  if [ "$pointer_count" -gt 0 ]; then
    if command -v git-lfs >/dev/null 2>&1 || git lfs version >/dev/null 2>&1; then
      echo "Fetching $pointer_count Git LFS knowledge source(s)..."
      git lfs install --local >/dev/null 2>&1 || true
      git lfs pull
    fi
    pointer_count=$(grep -rl --include='*.pdf' --include='*.xsd' --include='*.zip' \
      'version https://git-lfs.github.com/spec/v1' swiftKnowledgeBase 2>/dev/null | wc -l | tr -d ' ')
    if [ "$pointer_count" -gt 0 ]; then
      echo "LFS_POINTER_NOT_FETCHED: $pointer_count knowledge source(s) are Git LFS pointers." >&2
      echo "Install Git LFS (https://git-lfs.com) and run: git lfs pull" >&2
      exit 3
    fi
  fi
  if [ -z "$(read_value KNOWLEDGE_MODE)" ] || [ "$(read_value KNOWLEDGE_MODE)" = "disabled" ]; then
    set_value KNOWLEDGE_MODE local
  fi
  set_value KNOWLEDGE_AUTO_SYNC_ON_START false
  knowledge_fetched=true
elif [ -n "${KNOWLEDGE_BUNDLE_URL:-}" ] || [ -n "${KNOWLEDGE_BUNDLE_PATH:-}" ]; then
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
  # Verify the mounted sources against the committed manifest, then index them in the
  # background: the first parse of ~160 standards documents takes minutes, the studio's
  # configured lane is usable immediately, and the knowledge-preview lane appears when the
  # sync finishes. Incremental afterwards; lexical-only without embedding credentials.
  docker compose exec -T backend python -m app.knowledge_base manifest
  docker compose exec -d -T backend sh -c \
    'python -m app.knowledge_base sync --quiet > /app/data/knowledge-sync.log 2>&1'
  echo "Knowledge sync running in the background; follow it with:"
  echo "  docker compose exec backend tail -f /app/data/knowledge-sync.log"
  echo "  make knowledge-status   (or docker compose exec backend python -m app.knowledge_base status)"
fi

echo "Financial Message Studio is ready: http://localhost:${frontend_port}"
echo "Backend readiness: http://localhost:${backend_port}/api/health/ready"
