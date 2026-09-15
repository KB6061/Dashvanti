#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/krishna/food}"
KAFKA_HOME="${KAFKA_HOME:-/opt/kafka}"
KAFKA_CONFIG="${KAFKA_CONFIG:-$KAFKA_HOME/config/server.properties}"
KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-127.0.0.1:9092}"
KAFKA_TOPIC="${KAFKA_TOPIC:-dashvanti.events}"
RUN_DIR="$APP_DIR/run"
LOG_DIR="$APP_DIR/logs"
KAFKA_PID="$RUN_DIR/kafka.pid"
WORKER_PID="$RUN_DIR/kafka-worker.pid"
KAFKA_LOG="$LOG_DIR/kafka.log"
WORKER_LOG="$LOG_DIR/kafka-worker.log"

cd "$APP_DIR"
umask 000
mkdir -p "$RUN_DIR" "$LOG_DIR"
chmod 777 "$LOG_DIR" >/dev/null 2>&1 || true
touch "$KAFKA_LOG" "$WORKER_LOG"
chmod 666 "$KAFKA_LOG" "$WORKER_LOG" >/dev/null 2>&1 || true

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    "$@"
  fi
}

repair_permissions() {
  as_root chmod 777 "$KAFKA_HOME/logs" "$KAFKA_HOME/kraft-data" >/dev/null 2>&1 || true
  as_root chmod 666 "$KAFKA_HOME"/logs/* >/dev/null 2>&1 || true
}

kafka_bin() {
  printf '%s/bin/%s\n' "$KAFKA_HOME" "$1"
}

kafka_pid() {
  local saved_pid found_pid
  if [ -s "$KAFKA_PID" ]; then
    saved_pid="$(cat "$KAFKA_PID")"
    if ps -p "$saved_pid" -o comm=,args= 2>/dev/null | grep -q "java .*kafka[.]Kafka $KAFKA_CONFIG"; then
      printf '%s\n' "$saved_pid"
      return 0
    fi
    rm -f "$KAFKA_PID"
  fi
  found_pid="$(ps -eo pid=,comm=,args= | awk -v cfg="$KAFKA_CONFIG" '$2 ~ /java/ && $0 ~ /kafka[.]Kafka/ && index($0, cfg) {print $1; exit}')"
  [ -n "$found_pid" ] || return 1
  printf '%s\n' "$found_pid"
}

worker_pid() {
  local saved_pid found_pid
  if [ -s "$WORKER_PID" ]; then
    saved_pid="$(cat "$WORKER_PID")"
    if ps -p "$saved_pid" -o args= 2>/dev/null | grep -q "python3 -m backend[.]worker"; then
      printf '%s\n' "$saved_pid"
      return 0
    fi
    rm -f "$WORKER_PID"
  fi
  found_pid="$(pgrep -f '^python3 -m backend.worker' | head -n 1 || true)"
  [ -n "$found_pid" ] || return 1
  printf '%s\n' "$found_pid"
}

validate() {
  test -x "$(kafka_bin kafka-server-start.sh)"
  test -x "$(kafka_bin kafka-server-stop.sh)"
  test -x "$(kafka_bin kafka-topics.sh)"
  test -f "$KAFKA_CONFIG"
  python3 -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('confluent_kafka') else 1)"
  python3 -m py_compile backend/worker.py backend/services/kafka_event_service.py
  echo "kafka deploy validation passed"
}

wait_kafka() {
  for _ in $(seq 1 60); do
    if "$(kafka_bin kafka-topics.sh)" --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" --list >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_kafka() {
  local pid
  repair_permissions
  if pid="$(kafka_pid 2>/dev/null)" && [ -n "$pid" ]; then
    echo "kafka running pid=$pid"
    return 0
  fi
  nohup setsid "$(kafka_bin kafka-server-start.sh)" "$KAFKA_CONFIG" >> "$KAFKA_LOG" 2>&1 < /dev/null &
  echo "$!" > "$KAFKA_PID"
  wait_kafka
  "$(kafka_bin kafka-topics.sh)" --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" --create --if-not-exists --topic "$KAFKA_TOPIC" --partitions 3 --replication-factor 1 >/dev/null
  echo "kafka started pid=$(cat "$KAFKA_PID")"
}

stop_kafka() {
  local pid
  pid="$(kafka_pid 2>/dev/null || true)"
  if [ -z "$pid" ]; then
    rm -f "$KAFKA_PID"
    echo "kafka stopped"
    return 0
  fi
  "$(kafka_bin kafka-server-stop.sh)" >/dev/null 2>&1 || true
  as_root pkill -f "kafka[.]Kafka $KAFKA_CONFIG" >/dev/null 2>&1 || true
  as_root pkill -f "$KAFKA_HOME/bin/kafka-run-class.sh -name kafkaServer" >/dev/null 2>&1 || true
  as_root kill "$pid" >/dev/null 2>&1 || true
  for _ in $(seq 1 20); do
    kafka_pid >/dev/null 2>&1 || { rm -f "$KAFKA_PID"; echo "kafka stopped"; return 0; }
    sleep 1
  done
  as_root kill -9 "$pid" >/dev/null 2>&1 || true
  rm -f "$KAFKA_PID"
  echo "kafka stopped"
}

start_worker() {
  local pid
  if pid="$(worker_pid 2>/dev/null)" && [ -n "$pid" ]; then
    echo "worker running pid=$pid"
    return 0
  fi
  touch "$WORKER_LOG"
  chmod 666 "$WORKER_LOG" >/dev/null 2>&1 || true
  KAFKA_BOOTSTRAP_SERVERS="$KAFKA_BOOTSTRAP_SERVERS" nohup setsid python3 -m backend.worker >> "$WORKER_LOG" 2>&1 < /dev/null &
  echo "$!" > "$WORKER_PID"
  sleep 2
  if ! worker_pid >/dev/null 2>&1; then
    tail -n 40 "$WORKER_LOG" >&2 || true
    return 1
  fi
  echo "worker started pid=$(cat "$WORKER_PID")"
}

stop_worker() {
  local pid
  pid="$(worker_pid 2>/dev/null || true)"
  if [ -z "$pid" ]; then
    rm -f "$WORKER_PID"
    echo "worker stopped"
    return 0
  fi
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 10); do
    worker_pid >/dev/null 2>&1 || { rm -f "$WORKER_PID"; echo "worker stopped"; return 0; }
    sleep 1
  done
  as_root kill -9 "$pid" >/dev/null 2>&1 || true
  rm -f "$WORKER_PID"
  echo "worker stopped"
}

case "${1:-status}" in
  validate)
    validate
    ;;
  start)
    validate
    start_kafka
    start_worker
    echo "kafka ready"
    ;;
  stop)
    stop_worker
    stop_kafka
    ;;
  restart)
    "$0" stop
    "$0" start
    ;;
  status)
    if pid="$(kafka_pid 2>/dev/null)" && [ -n "$pid" ]; then echo "kafka running pid=$pid"; else echo "kafka stopped"; fi
    if pid="$(worker_pid 2>/dev/null)" && [ -n "$pid" ]; then echo "worker running pid=$pid"; else echo "worker stopped"; fi
    ;;
  logs)
    tail -n 80 "$KAFKA_LOG" 2>/dev/null || true
    tail -n 80 "$WORKER_LOG" 2>/dev/null || true
    ;;
  *)
    echo "Usage: $0 {validate|start|stop|restart|status|logs}"
    exit 2
    ;;
esac
