#!/usr/bin/env bash
set -Eeuo pipefail

action="${1:-status}"
target="${2:-all}"
core=(postgresql.service redis-server.service kafka-server.service)
apps=(dashvanti@api.service gps-streaming-service.service dashvanti-driver-partners.service)
web=(dashvanti@main.service dashvanti@customer.service dashvanti@restaurant.service dashvanti@driver.service dashvanti@admin.service)
extra=(dashvanti@docs.service dashvanti@driver-secure.service)
managed=("${core[@]}" "${apps[@]}" "${web[@]}" "${extra[@]}" nginx.service)
all=("${managed[@]}" dashvanti-monitor.timer)

usage() {
  printf 'Usage: dashvanti {start|stop|restart|status|check|logs|tail|enable} [all|web|api|gps|driver-partners|database|redis|kafka|nginx|main|customer|restaurant|driver|admin|docs|driver-secure]\n'
}
case "$action" in
  help|-h|--help) usage; exit 0 ;;
  start|stop|restart|status|check|logs|tail|enable) ;;
  *) usage >&2; exit 2 ;;
esac
case "$target" in
  all) units=("${all[@]}") ;;
  web) units=("${web[@]}") ;;
  api|main|customer|restaurant|driver|admin|docs|driver-secure) units=("dashvanti@$target.service") ;;
  driver-partners) units=(dashvanti-driver-partners.service) ;;
  gps) units=(gps-streaming-service.service) ;;
  database) units=(postgresql.service) ;;
  redis) units=(redis-server.service) ;;
  kafka) units=(kafka-server.service) ;;
  nginx) units=(nginx.service) ;;
  *) usage >&2; exit 2 ;;
esac
if (( $# > 2 )); then usage >&2; exit 2; fi
if (( EUID != 0 )) && [[ "$action" != status && "$action" != check ]]; then
  exec sudo -- "$0" "$@"
fi

endpoint() {
  case "$1" in
    dashvanti@api.service) printf 'http://127.0.0.1:8001/health' ;;
    dashvanti-driver-partners.service) printf 'http://127.0.0.1:8001/api/driver-partner/health' ;;
    gps-streaming-service.service) printf 'http://127.0.0.1:8002/health' ;;
    dashvanti@docs.service) printf 'http://127.0.0.1:8004/health' ;;
    dashvanti@driver-secure.service) printf 'https://127.0.0.1:8443/driver/login' ;;
    dashvanti@main.service) printf 'http://127.0.0.1:8084/' ;;
    dashvanti@customer.service) printf 'http://127.0.0.1:8080/customer/login' ;;
    dashvanti@restaurant.service) printf 'http://127.0.0.1:8081/restaurant/login' ;;
    dashvanti@driver.service) printf 'http://127.0.0.1:8082/driver/login' ;;
    dashvanti@admin.service) printf 'http://127.0.0.1:8083/admin/login' ;;
    nginx.service) printf 'http://127.0.0.1:80/' ;;
  esac
}
healthy() {
  local unit="$1" url code
  systemctl is-active --quiet "$unit" || return 1
  case "$unit" in
    postgresql.service) /usr/bin/pg_isready -q -h 127.0.0.1 -p 5432 ;;
    redis-server.service) [[ "$(timeout 3 /opt/dashvanti-redis/bin/redis-cli --raw ping 2>/dev/null)" == PONG ]] ;;
    kafka-server.service) timeout 2 bash -c 'exec 3<>/dev/tcp/127.0.0.1/9092' 2>/dev/null ;;
    *)
      url="$(endpoint "$unit")"
      [[ -n "$url" ]] || return 0
      if [[ "$unit" == nginx.service ]]; then
        code="$(curl -sS --max-time 3 -H 'Host: www.dashvanti.com' -o /dev/null -w '%{http_code}' "$url" 2>/dev/null)" || return 1
        [[ "$code" == 200 || "$code" == 301 || "$code" == 302 || "$code" == 308 ]]
      else
        code="$(curl -ksS --max-time 3 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null)" || return 1
        [[ "$code" == 200 ]]
      fi ;;
  esac
}
wait_ready() {
  local unit="$1" deadline=$((SECONDS + 75))
  while ! healthy "$unit"; do
    if (( SECONDS >= deadline )); then
      printf 'Not ready: %s. Run: sudo dashvanti logs\n' "$unit" >&2
      return 1
    fi
    sleep 1
  done
  printf 'Ready: %s\n' "$unit"
}
resume_monitor() {
  local unit
  for unit in "${managed[@]}"; do systemctl is-active --quiet "$unit" || return 0; done
  systemctl start dashvanti-monitor.timer
}
pause_monitor() {
  systemctl stop dashvanti-monitor.timer dashvanti-monitor.service
}
stop_selected() {
  pause_monitor
  if [[ "$target" == all ]]; then
    systemctl stop dashvanti.target "${managed[@]}"
  else
    systemctl stop "${units[@]}"
  fi
  printf 'Stopped: %s\n' "$target"
}
start_selected() {
  if [[ "$target" == all ]]; then
    systemctl start dashvanti.target
  else
    systemctl start "${units[@]}"
    if [[ "$target" == redis || "$target" == kafka || "$target" == database ]]; then
      dependencies_ready=true
      for dependency in "${core[@]}"; do
        if ! systemctl is-active --quiet "$dependency"; then dependencies_ready=false; fi
      done
      if [[ "$dependencies_ready" == true ]]; then
        systemctl start gps-streaming-service.service
        wait_ready gps-streaming-service.service
      fi
    fi
  fi
  local unit
  for unit in "${units[@]}"; do wait_ready "$unit"; done
  resume_monitor
}

case "$action" in
  status)
    printf '%-34s %-12s %-12s %s\n' SERVICE STATE BOOT HEALTH
    for unit in "${units[@]}"; do
      state="$(systemctl is-active "$unit" 2>/dev/null || true)"
      boot="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
      health=unavailable; if healthy "$unit"; then health=ready; fi
      printf '%-34s %-12s %-12s %s\n' "$unit" "$state" "$boot" "$health"
    done
    exit 0 ;;
  check)
    result=0
    for unit in "${units[@]}"; do
      if healthy "$unit"; then printf 'OK %s\n' "$unit"; else printf 'FAIL %s\n' "$unit"; result=1; fi
    done
    exit "$result" ;;
  logs|tail)
    journal=(); for unit in "${units[@]}"; do journal+=(-u "$unit"); done
    journal+=(-u dashvanti-monitor.service)
    if [[ "$action" == tail ]]; then exec journalctl -f "${journal[@]}"; fi
    exec journalctl --no-pager -n 100 "${journal[@]}" ;;
esac

exec 9>/run/lock/dashvanti-control.lock
if ! flock -n 9; then printf 'Another Dashvanti operation is running.\n' >&2; exit 75; fi
trap 'printf "Dashvanti operation failed; run sudo dashvanti status and sudo dashvanti logs.\n" >&2' ERR
logger -t dashvanti-control -- "$action $target requested"
case "$action" in
  enable)
    if [[ "$target" == all ]]; then systemctl enable dashvanti.target "${all[@]}"; else systemctl enable "${units[@]}"; fi ;;
  start) start_selected ;;
  stop) stop_selected ;;
  restart) stop_selected; start_selected ;;
esac
logger -t dashvanti-control -- "$action $target completed"
printf 'Complete: %s %s\n' "$action" "$target"
