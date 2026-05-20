#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_LOG="${BACKEND_LOG:-/tmp/aot-web-backend.log}"
FRONTEND_LOG="${FRONTEND_LOG:-/tmp/aot-web-frontend.log}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-9119}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
FRONTEND_PATTERN="$ROOT_DIR/web/node_modules/.bin/vite"

log() {
  printf '[dev-dashboard] %s\n' "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

wait_for_backend() {
  local retries=30
  local url="http://${BACKEND_HOST}:${BACKEND_PORT}/api/status"
  while (( retries > 0 )); do
    if curl --max-time 2 -sS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    retries=$((retries - 1))
  done
  return 1
}

wait_for_frontend() {
  local retries=20
  while (( retries > 0 )); do
    if lsof -tiTCP:"${FRONTEND_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    retries=$((retries - 1))
  done
  return 1
}

start_backend() {
  require_cmd aot
  require_cmd curl

  log "Starting backend on ${BACKEND_HOST}:${BACKEND_PORT}"
  nohup aot dashboard --no-open --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" >"${BACKEND_LOG}" 2>&1 &

  if ! wait_for_backend; then
    log "Backend failed to become ready; tailing ${BACKEND_LOG}:"
    tail -n 80 "${BACKEND_LOG}" || true
    exit 1
  fi

  log "Backend ready at http://${BACKEND_HOST}:${BACKEND_PORT}"
}

start_frontend() {
  require_cmd npm
  require_cmd lsof

  log "Starting frontend on ${FRONTEND_HOST}:${FRONTEND_PORT}"
  nohup env NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost npm --prefix "${ROOT_DIR}/web" run dev -- --host "${FRONTEND_HOST}" --strictPort >"${FRONTEND_LOG}" 2>&1 &

  if ! wait_for_frontend; then
    log "Frontend failed to become ready; tailing ${FRONTEND_LOG}:"
    tail -n 80 "${FRONTEND_LOG}" || true
    exit 1
  fi

  log "Frontend ready at http://${FRONTEND_HOST}:${FRONTEND_PORT}"
}

stop_backend() {
  if command -v aot >/dev/null 2>&1; then
    aot dashboard --stop >/dev/null 2>&1 || true
  fi
}

stop_frontend() {
  local pids
  pids="$(lsof -tiTCP:"${FRONTEND_PORT}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    kill ${pids} >/dev/null 2>&1 || true
    sleep 1
    pids="$(lsof -tiTCP:"${FRONTEND_PORT}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      kill -9 ${pids} >/dev/null 2>&1 || true
    fi
  fi
  pkill -f "$FRONTEND_PATTERN" >/dev/null 2>&1 || true
}

show_status() {
  log "Backend status:"
  if command -v aot >/dev/null 2>&1; then
    aot dashboard --status || true
  else
    echo "aot not found in PATH"
  fi

  log "Frontend status:"
  if command -v lsof >/dev/null 2>&1; then
    local line
    line="$(lsof -nP -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${line}" ]]; then
      printf '%s\n' "${line}"
    else
      echo "No Vite dev server process found on port ${FRONTEND_PORT}."
    fi
  else
    echo "lsof not found in PATH"
  fi
}

show_logs() {
  log "Backend log: ${BACKEND_LOG}"
  if [[ -f "${BACKEND_LOG}" ]]; then
    tail -n 80 "${BACKEND_LOG}"
  else
    echo "(no backend log found)"
  fi
  echo
  log "Frontend log: ${FRONTEND_LOG}"
  if [[ -f "${FRONTEND_LOG}" ]]; then
    tail -n 80 "${FRONTEND_LOG}"
  else
    echo "(no frontend log found)"
  fi
}

usage() {
  cat <<EOF
Usage: scripts/dev-dashboard.sh <command>

Commands:
  start           Start backend + frontend (cleaning stale processes first)
  start-backend   Start backend only
  start-frontend  Start frontend only
  stop            Stop backend + frontend
  status          Show backend + frontend process status
  logs            Tail backend + frontend logs
  restart         Stop then start both services
EOF
}

cmd="${1:-start}"

case "${cmd}" in
  start)
    stop_backend
    stop_frontend
    start_backend
    start_frontend
    log "Dev mode is up:"
    log "  Backend  -> http://${BACKEND_HOST}:${BACKEND_PORT}"
    log "  Frontend -> http://${FRONTEND_HOST}:${FRONTEND_PORT}"
    log "  Logs     -> ${BACKEND_LOG} / ${FRONTEND_LOG}"
    ;;
  start-backend)
    stop_backend
    start_backend
    ;;
  start-frontend)
    stop_frontend
    start_frontend
    ;;
  stop)
    stop_backend
    stop_frontend
    log "Stopped backend and frontend."
    ;;
  status)
    show_status
    ;;
  logs)
    show_logs
    ;;
  restart)
    stop_backend
    stop_frontend
    start_backend
    start_frontend
    log "Restarted backend and frontend."
    ;;
  *)
    usage
    exit 1
    ;;
esac
