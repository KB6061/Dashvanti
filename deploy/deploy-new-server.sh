#!/usr/bin/env bash
set -euo pipefail

APP_DIR=${APP_DIR:-/home/krishna/food}
EMAIL=
CUSTOMER=
RESTAURANT=
DRIVER=
ADMIN=

while [[ $# -gt 0 ]]; do
  case "$1" in
    --email) EMAIL="$2"; shift 2 ;;
    --customer) CUSTOMER="$2"; shift 2 ;;
    --restaurant) RESTAURANT="$2"; shift 2 ;;
    --driver) DRIVER="$2"; shift 2 ;;
    --admin) ADMIN="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$EMAIL" || -z "$CUSTOMER" || -z "$RESTAURANT" || -z "$DRIVER" || -z "$ADMIN" ]]; then
  echo "Usage: sudo bash deploy/deploy-new-server.sh --customer HOST --restaurant HOST --driver HOST --admin HOST --email EMAIL" >&2
  exit 1
fi

cd "$APP_DIR"

if command -v dnf >/dev/null 2>&1; then
  dnf install -y nginx python3 python3-pip
elif command -v apt-get >/dev/null 2>&1; then
  apt-get update
  apt-get install -y nginx python3 python3-pip python3-venv
else
  echo "Unsupported package manager. Install nginx/python3 manually." >&2
  exit 1
fi

python3 -m venv /opt/certbot
/opt/certbot/bin/pip install --upgrade pip certbot certbot-nginx

cat >/etc/nginx/conf.d/dashvanti.conf <<EOF
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 80;
    server_name $CUSTOMER;
    client_max_body_size 25m;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
    }
}

server {
    listen 80;
    server_name $RESTAURANT;
    client_max_body_size 25m;
    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
    }
}

server {
    listen 80;
    server_name $DRIVER;
    client_max_body_size 25m;
    location / {
        proxy_pass http://127.0.0.1:8082;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
    }
}

server {
    listen 80;
    server_name $ADMIN;
    client_max_body_size 25m;
    location / {
        proxy_pass http://127.0.0.1:8083;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
    }
}
EOF

chmod 644 /etc/nginx/conf.d/dashvanti.conf
restorecon -v /etc/nginx/conf.d/dashvanti.conf 2>/dev/null || true

if command -v semanage >/dev/null 2>&1; then
  semanage port -m -t http_port_t -p tcp 8080 2>/dev/null || true
  semanage port -m -t http_port_t -p tcp 8081 2>/dev/null || true
  semanage port -m -t http_port_t -p tcp 8082 2>/dev/null || true
  semanage port -m -t http_port_t -p tcp 8083 2>/dev/null || true
fi
setsebool -P httpd_can_network_connect 1 2>/dev/null || true

if [[ -f .env ]]; then
  sed -i.bak-new-server \
    -e "s#^ALLOWED_HOSTS=.*#ALLOWED_HOSTS=*,$CUSTOMER,$RESTAURANT,$DRIVER,$ADMIN,localhost,127.0.0.1#" \
    -e "s#^CSRF_TRUSTED_ORIGINS=.*#CSRF_TRUSTED_ORIGINS=https://$CUSTOMER,https://$RESTAURANT,https://$DRIVER,https://$ADMIN,http://127.0.0.1:8080,http://127.0.0.1:8081,http://127.0.0.1:8082,http://127.0.0.1:8083#" \
    -e "s#^PUBLIC_URL=.*#PUBLIC_URL=https://$CUSTOMER#" \
    -e "s#^CUSTOMER_URL=.*#CUSTOMER_URL=https://$CUSTOMER#" \
    -e "s#^RESTAURANT_URL=.*#RESTAURANT_URL=https://$RESTAURANT#" \
    -e "s#^DRIVER_URL=.*#DRIVER_URL=https://$DRIVER#" \
    -e "s#^ADMIN_URL=.*#ADMIN_URL=https://$ADMIN#" \
    .env
fi

nginx -t
systemctl enable --now nginx

./script/dashvanti-services.sh start all
sleep 8

/opt/certbot/bin/certbot --nginx \
  -d "$CUSTOMER" \
  -d "$RESTAURANT" \
  -d "$DRIVER" \
  -d "$ADMIN" \
  --non-interactive --agree-tos -m "$EMAIL" --redirect

cat >/etc/cron.d/certbot-renew <<'EOF'
SHELL=/bin/bash
PATH=/sbin:/bin:/usr/sbin:/usr/bin:/opt/certbot/bin
17 3 * * * root /opt/certbot/bin/certbot renew --quiet --deploy-hook "/usr/bin/systemctl reload nginx"
EOF
chmod 644 /etc/cron.d/certbot-renew

systemctl reload nginx

curl -kI "https://$CUSTOMER/" | head -1
curl -kI "https://$RESTAURANT/" | head -1
curl -kI "https://$DRIVER/" | head -1
curl -kI "https://$ADMIN/" | head -1
