#!/bin/bash
set -euo pipefail
cd /home/krishna/food
set -a
. ./.env
set +a
exec .venv/bin/python -m uvicorn backend.gps_streaming:app --host 127.0.0.1 --port 8002 --ws websockets --ws-max-size 4096 --ws-ping-interval 20 --ws-ping-timeout 20 --no-access-log
