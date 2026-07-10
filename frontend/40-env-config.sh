#!/bin/sh
# Rendered by the nginx image's entrypoint before the server starts.
# Writes env-config.js from its template, substituting ${API_BASE} at container start.
# Set the backend URL (server IP now, domain later) with:  docker run -e API_BASE=...
set -e

envsubst '${API_BASE}' \
  < /usr/share/nginx/html/env-config.template.js \
  > /usr/share/nginx/html/env-config.js

echo "env-config: API_BASE=${API_BASE:-<empty — app.js falls back to http://localhost:8000>}"
