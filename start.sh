#!/usr/bin/env bash
set -e
pip install -r server/requirements.txt -q

# rebuild the frontend when sources changed (hash of web/src + configs)
cd web
HASH=$(find src index.html package.json vite.config.js -type f -exec md5sum {} \; | sort | md5sum | cut -d' ' -f1)
if [ ! -d dist ] || [ "$(cat dist/.build-hash 2>/dev/null)" != "$HASH" ]; then
  [ -d node_modules ] || npm install --silent
  npm run build
  echo "$HASH" > dist/.build-hash
fi
cd ..

exec uvicorn server.main:app --host 0.0.0.0 --port 8000
