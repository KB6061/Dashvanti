# Deploy Dashvanti to a New Unix Server

Use this guide to move Dashvanti to a fresh Ubuntu/RHEL/Amazon Linux style server with one command after DNS is ready.

## Before running

Point DNS A records to the new server public IP:

```text
customer.example.com   A   NEW_SERVER_IP
restaurant.example.com A   NEW_SERVER_IP
driver.example.com     A   NEW_SERVER_IP
admin.example.com      A   NEW_SERVER_IP
```

Open firewall/security group ports:

```text
22, 80, 443
```

Copy the project to the new server:

```bash
sudo mkdir -p /home/krishna/food
sudo chown -R "$USER:$USER" /home/krishna/food
rsync -az ./ /home/krishna/food/
```

Create or update `/home/krishna/food/.env` with the new domains, database, secrets, and URLs.

## Single command

```bash
cd /home/krishna/food
sudo bash deploy/deploy-new-server.sh \
  --customer customer.example.com \
  --restaurant restaurant.example.com \
  --driver driver.example.com \
  --admin admin.example.com \
  --email admin@example.com
```

## What the script does

- Installs Nginx.
- Installs Certbot in `/opt/certbot`.
- Writes `/etc/nginx/conf.d/dashvanti.conf`.
- Enables Nginx on boot.
- Applies SELinux proxy fixes when SELinux tools exist.
- Updates `.env` domain values.
- Starts Dashvanti services with `script/dashvanti-services.sh`.
- Requests Let's Encrypt HTTPS certificates.
- Adds `/etc/cron.d/certbot-renew`.
- Verifies all HTTPS portals.

## Required files

```text
/home/krishna/food/.env
/home/krishna/food/script/dashvanti-services.sh
/home/krishna/food/deploy/deploy-new-server.sh
```

## Service commands

```bash
cd /home/krishna/food
./script/dashvanti-services.sh start all
./script/dashvanti-services.sh stop all
./script/dashvanti-services.sh status all
sudo systemctl restart nginx
```

## Verify

```bash
curl -kI https://customer.example.com/
curl -kI https://restaurant.example.com/
curl -kI https://driver.example.com/
curl -kI https://admin.example.com/
```

Expected response:

```text
HTTP/1.1 302 Found
```

## Notes

- Do not hard-code database passwords in Android/mobile apps.
- Keep `.env` private.
- Use real production secrets on every new server.
- If HTTPS works but login POST returns `403`, check `CSRF_TRUSTED_ORIGINS`.
- If HTTPS returns `502` and Nginx logs show `Permission denied`, check SELinux:

```bash
sudo setsebool -P httpd_can_network_connect 1
```
