#!/usr/bin/env bash
set -euo pipefail
docker network inspect dashvanti-net >/dev/null 2>&1 || docker network create dashvanti-net
docker rm -f dashvanti-api dashvanti-web dashvanti-gateway dashvanti-migrate 2>/dev/null || true
docker build -t dashvanti:latest /home/krishna/food
docker run --rm --name dashvanti-migrate --network dashvanti-net --env-file /home/krishna/food/.env dashvanti:latest python -m backend.migrate
docker volume create dashvanti_uploads >/dev/null
docker volume create dashvanti_sessions >/dev/null
docker run -d --name dashvanti-api --network dashvanti-net --env-file /home/krishna/food/.env -v dashvanti_uploads:/opt/dashvanti_fs dashvanti:latest
docker run -d --name dashvanti-web --network dashvanti-net --env-file /home/krishna/food/.env -v dashvanti_sessions:/tmp/dashvanti_sessions -w /app/frontend dashvanti:latest uvicorn config.asgi:application --host 0.0.0.0 --port 8000
docker run -d --name dashvanti-gateway --network dashvanti-net -p 8080:80 -v /home/krishna/food/deploy/nginx.server.conf:/etc/nginx/conf.d/default.conf:ro -v /home/krishna/food/frontend/static:/srv/static:ro nginx:1.27-alpine
