#!/usr/bin/env sh
set -eu

api_base="${API_BASE_URL:-http://127.0.0.1:8000}"
curl --fail --silent --show-error \
  -H "Content-Type: application/json" \
  -X POST \
  --data @scripts/samples/mt541-generate.json \
  "${api_base}/api/messages/generate"
printf '\n'
