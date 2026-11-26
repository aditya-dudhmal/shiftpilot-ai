#!/usr/bin/env bash
# Start ShiftPilot AI locally: backend on :8000, frontend on :5173.
# Requires Python 3.12+ and Node 20+. Demo mode needs no API key.
set -e
cd "$(dirname "$0")"
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install --no-audit --no-fund)
fi
(cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000) &
(cd frontend && npm run dev) &
wait
