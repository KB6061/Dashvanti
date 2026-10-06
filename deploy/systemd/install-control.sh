#!/usr/bin/env bash
set -euo pipefail
cd /home/krishna/food
install -m 0755 script/dashvanti-control.sh /usr/local/bin/dashvanti
if [[ ! -e /usr/bin/dashvanti && ! -L /usr/bin/dashvanti ]]; then
  ln -s /usr/local/bin/dashvanti /usr/bin/dashvanti
elif [[ "$(readlink /usr/bin/dashvanti)" != /usr/local/bin/dashvanti ]]; then
  printf '/usr/bin/dashvanti already exists; installation stopped.\n' >&2
  exit 1
fi
install -m 0644 deploy/systemd/dashvanti.target /etc/systemd/system/dashvanti.target
install -m 0755 deploy/systemd/monitor.py /usr/local/libexec/dashvanti-monitor.py
units=(postgresql redis-server kafka-server gps-streaming-service nginx dashvanti-monitor)
for name in "${units[@]}"; do
  install -d "/etc/systemd/system/$name.service.d"
  printf '[Unit]\nPartOf=dashvanti.target\n' > "/etc/systemd/system/$name.service.d/dashvanti-lifecycle.conf"
done
install -d /etc/systemd/system/dashvanti@.service.d
printf '[Unit]\nPartOf=dashvanti.target\n' > /etc/systemd/system/dashvanti@.service.d/dashvanti-lifecycle.conf
for role in main customer restaurant driver admin docs driver-secure; do
  install -d "/etc/systemd/system/dashvanti@$role.service.d"
  printf '[Unit]\nWants=dashvanti@api.service\nAfter=dashvanti@api.service\n' > "/etc/systemd/system/dashvanti@$role.service.d/dashvanti-order.conf"
done
install -d /etc/systemd/system/dashvanti-monitor.timer.d
printf '[Unit]\nPartOf=dashvanti.target\nAfter=dashvanti@api.service gps-streaming-service.service nginx.service\n' > /etc/systemd/system/dashvanti-monitor.timer.d/dashvanti-lifecycle.conf
cat >> /etc/systemd/system/dashvanti-monitor.service.d/dashvanti-lifecycle.conf <<'EOF'
After=nginx.service gps-streaming-service.service dashvanti@api.service dashvanti@main.service dashvanti@customer.service dashvanti@restaurant.service dashvanti@driver.service dashvanti@admin.service
EOF
cat >> /etc/systemd/system/gps-streaming-service.service.d/dashvanti-lifecycle.conf <<'EOF'
Wants=postgresql.service
After=postgresql.service redis-server.service kafka-server.service
EOF
for name in nginx postgresql; do
  printf '[Service]\nRestart=on-failure\nRestartSec=5\n' >> "/etc/systemd/system/$name.service.d/dashvanti-lifecycle.conf"
done
printf '[Unit]\nAfter=dashvanti@api.service gps-streaming-service.service dashvanti@main.service dashvanti@customer.service dashvanti@restaurant.service dashvanti@driver.service dashvanti@admin.service\n' >> /etc/systemd/system/nginx.service.d/dashvanti-lifecycle.conf
if command -v restorecon >/dev/null; then
  restorecon /usr/local/bin/dashvanti /usr/bin/dashvanti /usr/local/libexec/dashvanti-monitor.py /etc/systemd/system/dashvanti.target
  restorecon -R /etc/systemd/system/*.service.d /etc/systemd/system/dashvanti-monitor.timer.d
fi
bash -n /usr/local/bin/dashvanti
systemctl daemon-reload
/usr/local/bin/dashvanti enable
/usr/local/bin/dashvanti start
