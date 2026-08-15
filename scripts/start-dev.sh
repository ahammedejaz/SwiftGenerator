#!/usr/bin/env sh
set -eu

if [ ! -x backend/.venv/bin/uvicorn ]; then
  echo "Backend environment is missing. Run: make install" >&2
  exit 1
fi

(cd backend && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
backend_pid=$!

cleanup() {
  kill "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd frontend
npm run dev
