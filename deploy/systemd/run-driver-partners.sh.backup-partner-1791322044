#!/bin/bash
set -euo pipefail
cd /home/krishna/food
set -a
source .env
set +a
exec .venv/bin/python -m backend.driver_partner_worker
