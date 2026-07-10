// Runtime config. Overwritten at container start from the API_BASE env var
// (see 40-env-config.sh). Committed empty so local `python -m http.server` has no 404
// and app.js falls back to http://localhost:8000.
window.__API_BASE__ = "";
