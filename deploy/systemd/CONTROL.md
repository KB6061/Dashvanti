```bash
sudo dashvanti start
sudo dashvanti stop
sudo dashvanti restart
dashvanti status
dashvanti check
sudo dashvanti logs
sudo dashvanti tail
```

```bash
sudo dashvanti restart api
sudo dashvanti restart web
sudo dashvanti restart gps
sudo dashvanti restart customer
sudo dashvanti restart restaurant
sudo dashvanti restart driver
sudo dashvanti restart admin
sudo dashvanti restart main
```

`all` is the default. Other targets: `database`, `redis`, `kafka`, `nginx`, `docs`, `driver-secure`.

`dashvanti.target` starts the database, Redis, Kafka, API, streaming, homepage, four portals, existing documentation/secure-driver services, Nginx and monitor automatically at boot. Portals start after the API; streaming starts after its dependencies. Systemd restarts crashed processes. The command waits for real HTTP 200 responses, PostgreSQL readiness and Redis PING before reporting success. Kafka TCP readiness is followed by the streaming service's Kafka consumer health check. Concurrent control operations are rejected using a lock. Logs are in the systemd journal.

Stop/restart pauses the timer and running monitor before stopping application services. A successful start restores monitoring when every managed service is running. `stop` does not disable boot startup. `restart all` includes a graceful database/broker restart and briefly interrupts the website; `restart web`, `restart api` or `restart gps` limits downtime to the chosen component. No migrations or database deletion run during service controls.

Deployment:

```bash
cd /home/krishna/food
sudo bash deploy/systemd/install-control.sh
systemctl is-enabled dashvanti.target
```

The old `script/dashvanti-services.sh` command forwards to this controller when installed. Boot enablement and a full stop/start/restart are verified during deployment; an actual EC2 reboot requires a separate check.
