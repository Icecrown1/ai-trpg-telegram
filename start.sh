#!/usr/bin/env bash
set -e
pip install -r server/requirements.txt -q
if [ ! -d web/dist ]; then
  cd web && npm install --silent && npm run build && cd ..
fi
exec uvicorn server.main:app --host 0.0.0.0 --port 8000
