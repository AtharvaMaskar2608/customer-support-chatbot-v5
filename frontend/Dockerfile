# Frontend image — static site served by nginx on :80.
# Build with the frontend/ dir as context:  docker build -t <repo>:frontend ./frontend
#
# API_BASE (the backend URL the browser calls) is injected AT CONTAINER START from the
# API_BASE env var — so switching from a server IP to a domain is just a different
# `docker run -e API_BASE=...`, with no rebuild.
FROM nginx:1.27-alpine

# envsubst (from gettext) renders env-config.js from its template at startup.
RUN apk add --no-cache gettext

# Static assets.
COPY index.html env-config.template.js /usr/share/nginx/html/
COPY js  /usr/share/nginx/html/js
COPY css /usr/share/nginx/html/css

# Site config + the startup hook that renders env-config.js.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY 40-env-config.sh /docker-entrypoint.d/40-env-config.sh
RUN chmod +x /docker-entrypoint.d/40-env-config.sh

EXPOSE 80
# The base nginx image's entrypoint runs /docker-entrypoint.d/*.sh, then starts nginx.
