#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0
cd /home/krishna/food
if command -v dnf >/dev/null; then
 packages=()
 for package in gcc make curl tar gzip python3;do command -v "$package" >/dev/null || packages+=("$package");done
 command -v java >/dev/null || packages+=(java-21-openjdk-headless)
 if [ ${#packages[@]} -gt 0 ];then dnf -y install "${packages[@]}";fi
elif command -v apt-get >/dev/null; then
 packages=()
 command -v gcc >/dev/null && command -v make >/dev/null || packages+=(build-essential)
 command -v java >/dev/null || packages+=(openjdk-21-jre-headless)
 for package in curl tar gzip python3;do command -v "$package" >/dev/null || packages+=("$package");done
 if [ ${#packages[@]} -gt 0 ];then apt-get update;apt-get install -y "${packages[@]}";fi
fi
if [ "$(awk '/MemTotal/ {print $2}' /proc/meminfo)" -lt 2000000 ] && [ ! -e /var/lib/dashvanti-streaming.swap ];then
 fallocate -l 1G /var/lib/dashvanti-streaming.swap
 chmod 600 /var/lib/dashvanti-streaming.swap
 mkswap /var/lib/dashvanti-streaming.swap
 swapon /var/lib/dashvanti-streaming.swap
 grep -q '^/var/lib/dashvanti-streaming.swap ' /etc/fstab || echo '/var/lib/dashvanti-streaming.swap none swap sw 0 0' >> /etc/fstab
fi
install -d -o krishna -g krishna /var/lib/dashvanti-redis /var/lib/dashvanti-kafka /var/log/dashvanti-kafka
if [ ! -x /opt/dashvanti-redis/bin/redis-server ]; then
 work=$(mktemp -d /tmp/dashvanti-redis.XXXXXX)
 curl --fail --location --retry 3 https://download.redis.io/releases/redis-7.4.6.tar.gz -o "$work/redis.tar.gz"
 curl --fail --location --retry 3 https://raw.githubusercontent.com/redis/redis-hashes/master/README -o "$work/hashes"
 hash=$(awk '$2 == "redis-7.4.6.tar.gz" {print $4}' "$work/hashes")
 test -n "$hash"
 printf '%s  %s\n' "$hash" "$work/redis.tar.gz" | sha256sum -c -
 tar -xzf "$work/redis.tar.gz" -C "$work"
 make -C "$work/redis-7.4.6" -j1 MALLOC=libc BUILD_TLS=no
 make -C "$work/redis-7.4.6" PREFIX=/opt/dashvanti-redis install
fi
if [ ! -x /opt/dashvanti-kafka/bin/kafka-server-start.sh ]; then
 work=$(mktemp -d /tmp/dashvanti-kafka.XXXXXX)
 artifact=kafka_2.13-4.1.1.tgz
 curl --fail --location --retry 3 "https://archive.apache.org/dist/kafka/4.1.1/$artifact" -o "$work/$artifact"
 curl --fail --location --retry 3 "https://archive.apache.org/dist/kafka/4.1.1/$artifact.sha512" -o "$work/hash"
 python3 - "$work/$artifact" "$work/hash" <<'PY'
import hashlib,re,sys
expected=re.sub(r'\s','',open(sys.argv[2]).read().split(':')[-1]).lower()
assert hashlib.sha512(open(sys.argv[1],'rb').read()).hexdigest()==expected,'Kafka checksum mismatch'
PY
 tar -xzf "$work/$artifact" -C /opt
 mv /opt/kafka_2.13-4.1.1 /opt/dashvanti-kafka
fi
if [ ! -f /var/lib/dashvanti-kafka/meta.properties ]; then
 cluster=$(/opt/dashvanti-kafka/bin/kafka-storage.sh random-uuid)
 sudo -u krishna env KAFKA_HEAP_OPTS='-Xms64m -Xmx128m' /opt/dashvanti-kafka/bin/kafka-storage.sh format -t "$cluster" -c deploy/streaming/kafka.properties
fi
sudo -u krishna .venv/bin/python -m pip install 'redis>=5.2,<7' 'aiokafka>=0.12,<0.14' 'geographiclib>=2,<3' 'websockets>=13,<16' 'uvicorn[standard]>=0.34,<1'
sudo -u krishna .venv/bin/python -m backend.migrate_gps_streaming
sudo -u krishna .venv/bin/python -m backend.migrate_order_stream
for service in redis-server kafka-server gps-streaming-service; do
 install -m 644 "deploy/streaming/$service.service" "/etc/systemd/system/$service.service"
done
systemctl daemon-reload
systemctl enable --now redis-server kafka-server
ready=false
for attempt in $(seq 1 60); do
 if KAFKA_HEAP_OPTS='-Xms64m -Xmx128m' /opt/dashvanti-kafka/bin/kafka-topics.sh --bootstrap-server 127.0.0.1:9092 --list >/tmp/dashvanti-topic-list 2>/dev/null; then ready=true;break;fi
 sleep 2
done
$ready
KAFKA_HEAP_OPTS='-Xms64m -Xmx128m' /opt/dashvanti-kafka/bin/kafka-topics.sh --bootstrap-server 127.0.0.1:9092 --create --if-not-exists --topic driver_location_stream --partitions 6 --replication-factor 1 --config retention.ms=21600000 --config max.message.bytes=16384
python3 deploy/streaming/configure.py
nginx -t
systemctl reload nginx
systemctl enable --now gps-streaming-service
for role in api customer restaurant driver admin; do systemctl restart "dashvanti@$role";done
echo 'GPS streaming deployment installed'
