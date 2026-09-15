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
mkdir -p "$RUN_DIR" "$LOG_DIR"

kafka_bin() {
  printf '%s/bin/%s\n' "$KAFKA_HOME" "$1"
}

kafka_pid() {
  if [ -s "$KAFKA_PID" ]; then
    saved_pid="$(cat "$KAFKA_PID")"
    if ps -p "$saved_pid" -o args= 2>/dev/null | grep -q "kafka[.]Kafka $KAFKA_CONFIG"; then
      printf '%s
' "$saved_pid"
      return 0
    fi
    rm -f "$KAFKA_PID"
  fi
  found_pid="$(ps -eo pid=,comm=,args= | awk -v cfg="$KAFKA_CONFIG" '$2 ~ /java/ && $0 ~ /kafka[.]Kafka/ && index($0, cfg) {print $1; exit}')"
  [ -n "$found_pid" ] || return 1
  printf '%s
' "$found_pid"
}

worker_pid() {
  if [ -s "$WORKER_PID" ]; then
    saved_pid="$(cat "$WORKER_PID")"
    if ps -p "$saved_pid" -o args= 2>/dev/null | grep -q "python3 -m backend[.]worker"; then
      printf '%s
' "$saved_pid"
      return 0
    fi
    rm -f "$WORKER_PID"
  fi
  found_pid="$(pgrep -f '^python3 -m backend.worker' | head -n 1)"
  [ -n "$found_pid" ] || return 1
  printf '%s
' "$found_pid"
}

validate() {
  test -x "$(kafka_bin kafka-server-start.sh)"
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
  pid="$(kafka_pid 2>/dev/null || true)"
  if [ -z "$pid" ]; then
    rm -f "$KAFKA_PID"
    echo "kafka stopped"
    return 0
  fi
  "$(kafka_bin kafka-server-stop.sh)" >/dev/null 2>&1 || true
  pkill -f "/opt/kafka/bin/kafka-run-class.sh -name kafkaServer" >/dev/null 2>&1 || true
  pkill -f "kafka[.]Kafka $KAFKA_CONFIG" >/dev/null 2>&1 || true
  kill "$pid" 2>/dev/null || true
  if kill -0 "$pid" 2>/dev/null && command -v sudo >/dev/null 2>&1; then
    sudo pkill -f "/opt/kafka/bin/kafka-run-class.sh -name kafkaServer" >/dev/null 2>&1 || true
    sudo pkill -f "kafka[.]Kafka $KAFKA_CONFIG" >/dev/null 2>&1 || true
    sudo kill "$pid" >/dev/null 2>&1 || true
  fi
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || { rm -f "$KAFKA_PID"; echo "kafka stopped"; return 0; }
    sleep 1
  done
  kill -9 "$pid" 2>/dev/null || true
  if kill -0 "$pid" 2>/dev/null && command -v sudo >/dev/null 2>&1; then
    sudo kill -9 "$pid" >/dev/null 2>&1 || true
  fi
  rm -f "$KAFKA_PID"
  echo "kafka stopped"
}

start_worker() {
  if pid="$(worker_pid 2>/dev/null)" && [ -n "$pid" ]; then
    echo "worker running pid=$pid"
    return 0
  fi
  KAFKA_BOOTSTRAP_SERVERS="$KAFKA_BOOTSTRAP_SERVERS" nohup setsid python3 -m backend.worker >> "$WORKER_LOG" 2>&1 < /dev/null &
  echo "$!" > "$WORKER_PID"
  echo "worker started pid=$(cat "$WORKER_PID")"
}

stop_worker() {
  pid="$(worker_pid 2>/dev/null || true)"
  if [ -z "$pid" ]; then
    rm -f "$WORKER_PID"
    echo "worker stopped"
    return 0
  fi
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 10); do
    kill -0 "$pid" 2>/dev/null || { rm -f "$WORKER_PID"; echo "worker stopped"; return 0; }
    sleep 1
  done
  kill -9 "$pid" 2>/dev/null || true
  if kill -0 "$pid" 2>/dev/null && command -v sudo >/dev/null 2>&1; then
    sudo kill -9 "$pid" >/dev/null 2>&1 || true
  fi
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
    kafka_pid >/dev/null 2>&1 && echo "kafka running pid=$(kafka_pid)" || echo "kafka stopped"
    worker_pid >/dev/null 2>&1 && echo "worker running pid=$(worker_pid)" || echo "worker stopped"
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
