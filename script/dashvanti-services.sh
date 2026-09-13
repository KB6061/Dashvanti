#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/krishna/food}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8001}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
CUSTOMER_PORT="${CUSTOMER_PORT:-8080}"
RESTAURANT_PORT="${RESTAURANT_PORT:-8081}"
DRIVER_PORT="${DRIVER_PORT:-8082}"
ADMIN_PORT="${ADMIN_PORT:-8083}"
DOCS_PORT="${DOCS_PORT:-8004}"
DRIVER_HTTPS_PORT="${DRIVER_HTTPS_PORT:-8443}"
DRIVER_TLS_KEY="${DRIVER_TLS_KEY:-$APP_DIR/run/tls/driver.key}"
DRIVER_TLS_CERT="${DRIVER_TLS_CERT:-$APP_DIR/run/tls/driver.crt}"

RUN_DIR="$APP_DIR/run"
LOG_DIR="$APP_DIR/logs"
API_PID="$RUN_DIR/api.pid"
DOCS_PID="$RUN_DIR/api-docs.pid"
LEGACY_WEB_PID="$RUN_DIR/web.pid"
API_LOG="$LOG_DIR/api.log"
CONTROL_LOG="$LOG_DIR/service-control.log"
START_LOG="$LOG_DIR/service-start.log"
STOP_LOG="$LOG_DIR/service-stop.log"
RESTART_LOG="$LOG_DIR/service-restart.log"
UI_ACTIVITY_LOG="$LOG_DIR/ui-activity.log"
RESTAURANT_ORDER_LOG="${RESTAURANT_ORDER_LOG:-$LOG_DIR/restaurant-orders.log}"
ACTION_LOG="$CONTROL_LOG"

usage() {
  printf 'Usage: %s {start|stop|restart|status|logs|tail} [all|api|docs|driver-secure|customer|restaurant|driver|admin|web]\n' "$0"
}

setup() {
  cd "$APP_DIR"
  mkdir -p "$RUN_DIR" "$LOG_DIR"
  touch "$API_LOG" "$CONTROL_LOG" "$START_LOG" "$STOP_LOG" "$RESTART_LOG" "$UI_ACTIVITY_LOG" "$RESTAURANT_ORDER_LOG"
  touch "$LOG_DIR/customer-web.log" "$LOG_DIR/restaurant-web.log" "$LOG_DIR/driver-web.log" "$LOG_DIR/admin-web.log"
  touch "$LOG_DIR/customer-ui-activity.log" "$LOG_DIR/restaurant-ui-activity.log" "$LOG_DIR/driver-ui-activity.log" "$LOG_DIR/admin-ui-activity.log"
  if [ -f "$APP_DIR/.env" ]; then
    set -a
    . "$APP_DIR/.env"
    set +a
  fi
}

log_line() {
  local line
  line="$(date '+%Y-%m-%d %H:%M:%S') $*"
  printf '%s\n' "$line" | tee -a "$CONTROL_LOG" "$ACTION_LOG" >/dev/null
}

portal_port() {
  case "$1" in
    customer) printf '%s\n' "$CUSTOMER_PORT" ;;
    restaurant) printf '%s\n' "$RESTAURANT_PORT" ;;
    driver) printf '%s\n' "$DRIVER_PORT" ;;
    admin) printf '%s\n' "$ADMIN_PORT" ;;
    *) return 1 ;;
  esac
}

portal_pid_file() { printf '%s/%s-web.pid\n' "$RUN_DIR" "$1"; }
portal_log_file() { printf '%s/%s-web.log\n' "$LOG_DIR" "$1"; }
portal_ui_log_file() { printf '%s/%s-ui-activity.log\n' "$LOG_DIR" "$1"; }

pid_alive() {
  local pid_file="$1"
  [ -s "$pid_file" ] || return 1
  kill -0 "$(cat "$pid_file")" 2>/dev/null
}

find_api_pid() {
  local candidate cmd
  for candidate in $(pgrep -f "uvicorn backend.main:app" 2>/dev/null || true); do
    cmd="$(ps -p "$candidate" -o args= 2>/dev/null || true)"
    [[ "$cmd" == "python3 -m uvicorn backend.main:app --host $API_HOST --port $API_PORT"* ]] && printf '%s\n' "$candidate" && return 0
  done
  return 1
}

find_portal_pid() {
  local role="$1" port candidate cmd
  port="$(portal_port "$role")"
  for candidate in $(pgrep -f "frontend/manage.py runserver" 2>/dev/null || true); do
    cmd="$(ps -p "$candidate" -o args= 2>/dev/null || true)"
    [[ "$cmd" == "python3 frontend/manage.py runserver $WEB_HOST:$port"* ]] && printf '%s\n' "$candidate" && return 0
  done
  return 1
}

api_running() {
  pid_alive "$API_PID" || { local pid; pid="$(find_api_pid || true)"; [ -n "$pid" ] && printf '%s\n' "$pid" > "$API_PID"; }
}

portal_running() {
  local role="$1" pid_file pid
  pid_file="$(portal_pid_file "$role")"
  pid_alive "$pid_file" || { pid="$(find_portal_pid "$role" || true)"; [ -n "$pid" ] && printf '%s\n' "$pid" > "$pid_file"; }
}

wait_for_url() {
  local name="$1" url="$2" i
  for i in $(seq 1 25); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      log_line "$name ready: $url"
      return 0
    fi
    sleep 1
  done
  log_line "$name did not become ready: $url"
  return 1
}

start_api() {
  if api_running; then
    log_line "api already running pid=$(cat "$API_PID")"
    return 0
  fi
  log_line "running backend migration"
  python3 -m backend.migrate >> "$API_LOG" 2>&1
  log_line "starting api on $API_HOST:$API_PORT"
  nohup setsid python3 -m uvicorn backend.main:app --host "$API_HOST" --port "$API_PORT" >> "$API_LOG" 2>&1 < /dev/null &
  printf '%s\n' "$!" > "$API_PID"
  wait_for_url api "http://$API_HOST:$API_PORT/health"
}

start_portal() {
  local role="$1" port pid_file log_file ui_log
  port="$(portal_port "$role")"
  pid_file="$(portal_pid_file "$role")"
  log_file="$(portal_log_file "$role")"
  ui_log="$(portal_ui_log_file "$role")"
  if portal_running "$role"; then
    log_line "$role web already running pid=$(cat "$pid_file")"
    return 0
  fi
  log_line "starting $role portal on $WEB_HOST:$port"
  PORTAL_ROLE="$role" DJANGO_ACTIVITY_LOG="$ui_log" nohup setsid python3 frontend/manage.py runserver "$WEB_HOST:$port" --insecure --noreload --verbosity 0 >> "$log_file" 2>&1 < /dev/null &
  printf '%s\n' "$!" > "$pid_file"
  if [ "$role" = "admin" ]; then
    wait_for_url "$role web" "http://127.0.0.1:$port/admin/login"
  else
    wait_for_url "$role web" "http://127.0.0.1:$port/$role/login"
  fi
}

stop_pid_file() {
  local name="$1" pid_file="$2" finder="$3" pid=""
  [ -s "$pid_file" ] && pid="$(cat "$pid_file")"
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    pid="$($finder || true)"
  fi
  if [ -z "$pid" ]; then
    log_line "$name already stopped"
    rm -f "$pid_file"
    return 0
  fi
  log_line "stopping $name pid=$pid"
  kill "$pid" 2>/dev/null || true
  local i
  for i in $(seq 1 10); do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$pid_file"
      log_line "$name stopped"
      return 0
    fi
    sleep 1
  done
  log_line "force stopping $name pid=$pid"
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$pid_file"
}

stop_api() { stop_pid_file api "$API_PID" find_api_pid; }
stop_portal() { local role="$1"; stop_pid_file "$role web" "$(portal_pid_file "$role")" "find_portal_pid $role"; }
stop_legacy_web() {
  [ -s "$LEGACY_WEB_PID" ] || return 0
  stop_pid_file legacy-web "$LEGACY_WEB_PID" "find_portal_pid customer"
}


find_docs_pid() {
  pgrep -f '^python3 -m uvicorn backend.docs:app --host ' | head -n 1
}

docs_running() {
  pid_alive "$DOCS_PID" || { local pid; pid="$(find_docs_pid || true)"; [ -n "$pid" ] && printf '%s\n' "$pid" > "$DOCS_PID"; }
}

start_docs() {
  if docs_running; then return 0; fi
  log_line "starting API documentation portal on $WEB_HOST:$DOCS_PORT"
  nohup setsid python3 -m uvicorn backend.docs:app --host "$WEB_HOST" --port "$DOCS_PORT" >> "$LOG_DIR/api-docs.log" 2>&1 < /dev/null &
  printf '%s\n' "$!" > "$DOCS_PID"
  wait_for_url api-docs "http://127.0.0.1:$DOCS_PORT/health"
}

stop_docs() { stop_pid_file api-docs "$DOCS_PID" find_docs_pid; }


find_driver_secure_pid() { pgrep -f '^python3 -m uvicorn driver_https:application ' | head -n 1; }
driver_secure_running() {
  pid_alive "$RUN_DIR/driver-secure.pid" || { local pid; pid="$(find_driver_secure_pid || true)"; [ -n "$pid" ] && printf '%s\n' "$pid" > "$RUN_DIR/driver-secure.pid"; }
}
start_driver_secure() {
  if driver_secure_running; then return 0; fi
  if [ ! -r "$DRIVER_TLS_KEY" ] || [ ! -r "$DRIVER_TLS_CERT" ]; then log_line "driver HTTPS certificate not configured"; return 0; fi
  PORTAL_ROLE=driver DJANGO_ACTIVITY_LOG="$LOG_DIR/driver-secure-activity.log" nohup setsid python3 -m uvicorn driver_https:application --app-dir frontend --host "$WEB_HOST" --port "$DRIVER_HTTPS_PORT" --ssl-keyfile "$DRIVER_TLS_KEY" --ssl-certfile "$DRIVER_TLS_CERT" --no-access-log >> "$LOG_DIR/driver-secure.log" 2>&1 < /dev/null &
  printf '%s\n' "$!" > "$RUN_DIR/driver-secure.pid"
}
stop_driver_secure() { stop_pid_file driver-secure "$RUN_DIR/driver-secure.pid" find_driver_secure_pid; }

for_each_target() {
  local action="$1" target="${2:-all}"
  case "$target" in
    all)
      "$action" api
      "$action" driver-secure
      "$action" docs
      "$action" customer
      "$action" restaurant
      "$action" driver
      "$action" admin
      ;;
    web)
      "$action" customer
      "$action" restaurant
      "$action" driver
      "$action" admin
      ;;
    api|docs|driver-secure|customer|restaurant|driver|admin)
      "$action" "$target"
      ;;
    *) usage; exit 2 ;;
  esac
}

start_target() {
  case "$1" in
    api) start_api ;;
    docs) start_docs ;;
    driver-secure) start_driver_secure ;;
    customer|restaurant|driver|admin) start_portal "$1" ;;
  esac
}

stop_target() {
  case "$1" in
    api) stop_api ;;
    docs) stop_docs ;;
    driver-secure) stop_driver_secure ;;
    customer|restaurant|driver|admin) stop_portal "$1" ;;
  esac
}

restart_target() {
  stop_target "$1"
  start_target "$1"
}

start_services() {
  ACTION_LOG="$START_LOG"
  setup
  log_line "start requested target=${1:-all}"
  if [ "${1:-all}" != "api" ]; then start_api; fi
  for_each_target start_target "${1:-all}"
  log_line "start complete target=${1:-all}"
}

stop_services() {
  ACTION_LOG="$STOP_LOG"
  setup
  log_line "stop requested target=${1:-all}"
  if [ "${1:-all}" = "all" ]; then
    stop_legacy_web
    stop_docs
    stop_driver_secure
    for role in customer restaurant driver admin; do stop_portal "$role"; done
    stop_api
  else
    for_each_target stop_target "$1"
  fi
  log_line "stop complete target=${1:-all}"
}

restart_services() {
  ACTION_LOG="$RESTART_LOG"
  setup
  log_line "restart requested target=${1:-all}"
  if [ "${1:-all}" = "all" ]; then
    stop_legacy_web
    stop_docs
    stop_driver_secure
    for role in customer restaurant driver admin; do stop_portal "$role"; done
    stop_api
    start_api
    start_docs
    start_driver_secure
    for role in customer restaurant driver admin; do start_portal "$role"; done
  else
    if [ "$1" != "api" ]; then start_api; fi
    for_each_target restart_target "$1"
  fi
  log_line "restart complete target=${1:-all}"
}

status_services() {
  setup
  if api_running; then
    printf 'api: running pid=%s url=http://%s:%s/health\n' "$(cat "$API_PID")" "$API_HOST" "$API_PORT"
  else
    printf 'api: stopped\n'
  fi
  for role in customer restaurant driver admin; do
    local port pid_file
    port="$(portal_port "$role")"
    pid_file="$(portal_pid_file "$role")"
    if portal_running "$role"; then
      printf '%s portal: running pid=%s url=http://%s:%s\n' "$role" "$(cat "$pid_file")" "$WEB_HOST" "$port"
    else
      printf '%s portal: stopped url=http://%s:%s\n' "$role" "$WEB_HOST" "$port"
    fi
  done
  if docs_running; then printf 'API docs: running http://%s:%s/docs\n' "$WEB_HOST" "$DOCS_PORT"; else printf 'API docs: stopped\n'; fi
  printf 'logs:\n'
  printf '  service control: %s\n' "$CONTROL_LOG"
  printf '  api output:      %s\n' "$API_LOG"
  printf '  restaurant orders: %s\n' "$RESTAURANT_ORDER_LOG"
  for role in customer restaurant driver admin; do
    printf '  %-10s web: %s\n' "$role" "$(portal_log_file "$role")"
    printf '  %-10s ui:  %s\n' "$role" "$(portal_ui_log_file "$role")"
  done
}

show_logs() {
  setup
  status_services
  printf '\nWatch logs:\n'
  printf 'tail -f %s %s %s/customer-web.log %s/restaurant-web.log %s/driver-web.log %s/admin-web.log\n' "$API_LOG" "$RESTAURANT_ORDER_LOG" "$LOG_DIR" "$LOG_DIR" "$LOG_DIR" "$LOG_DIR"
}

tail_logs() {
  setup
  tail -f "$API_LOG" "$RESTAURANT_ORDER_LOG" "$LOG_DIR/customer-web.log" "$LOG_DIR/restaurant-web.log" "$LOG_DIR/driver-web.log" "$LOG_DIR/admin-web.log" "$LOG_DIR/customer-ui-activity.log" "$LOG_DIR/restaurant-ui-activity.log" "$LOG_DIR/driver-ui-activity.log" "$LOG_DIR/admin-ui-activity.log"
}

case "${1:-}" in
  start) start_services "${2:-all}" ;;
  stop) stop_services "${2:-all}" ;;
  restart) restart_services "${2:-all}" ;;
  status) status_services ;;
  logs) show_logs ;;
  tail) tail_logs ;;
  *) usage; exit 2 ;;
esac
