Systemd services run as krishna and load /home/krishna/food/.env.
Enabled instances: api, docs, driver-secure, customer, restaurant, driver, admin.
Services restart after crashes. The monitor runs every minute and restarts
services after three failed HTTP checks. Disk >=90% and memory >=95% generate
journal alerts. Driver HTTPS checks skip certificate validation for the local CA.

Status:
  systemctl status 'dashvanti@*' dashvanti-monitor.timer
  cat /var/lib/dashvanti-monitor/status.json
Logs:
  journalctl -u dashvanti@customer -f
  journalctl -u dashvanti-monitor.service -n 20
Controls:
  sudo script/dashvanti-services.sh restart customer

Monitoring alerts are local; no external notification channel is configured.
Reboot startup is enabled; an actual server reboot has not been tested.
