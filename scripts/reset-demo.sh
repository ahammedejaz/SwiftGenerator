#!/usr/bin/env sh
set -eu

api_base="${API_BASE_URL:-http://127.0.0.1:8000}"
if [ -n "${DEMO_RESET_KEY:-}" ]; then
  curl --fail --silent --show-error \
    -X POST \
    -H "X-Demo-Reset-Key: ${DEMO_RESET_KEY}" \
    "${api_base}/api/demo/reset"
else
  curl --fail --silent --show-error -X POST "${api_base}/api/demo/reset"
fi
printf '\n'
