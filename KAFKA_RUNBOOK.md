# Dashvanti Kafka Runbook

## Start Kafka

```bash
cd /home/krishna/food
sudo script/dashvanti-kafka.sh start
```

## Stop Kafka

```bash
cd /home/krishna/food
sudo script/dashvanti-kafka.sh stop
```

## Restart Kafka

```bash
cd /home/krishna/food
sudo script/dashvanti-kafka.sh restart
```

## Check Kafka status

```bash
cd /home/krishna/food
sudo script/dashvanti-kafka.sh status
```

## View Kafka logs

```bash
cd /home/krishna/food
sudo script/dashvanti-kafka.sh logs
```

## How Kafka works in Dashvanti

Dashvanti uses Kafka as a background event pipeline.

```text
Portal action
  -> FastAPI saves data in Oracle
  -> Backend writes event into OUTBOX table
  -> Kafka worker reads OUTBOX
  -> Worker publishes event to Kafka topic dashvanti.events
  -> Notification, dispatch, analytics, payout, and audit services consume events
```

## Order event flow

```text
Customer places order
  -> Order saved in Oracle
  -> OUTBOX event ORDER_CREATED
  -> Kafka topic dashvanti.events
  -> Restaurant alert
  -> Driver assignment
  -> Admin analytics
```

## Main Dashvanti Kafka events

```text
ORDER_CREATED
ORDER_ACCEPTED
DRIVER_ASSIGNED
DRIVER_ACCEPTED
DRIVER_LOCATION_UPDATED
ORDER_PICKED_UP
ORDER_DELIVERED
PAYMENT_COMPLETED
REFUND_REQUESTED
PAYOUT_CREATED
```

## Kafka deployment script

The deployment script uses the existing Kafka installation at `/opt/kafka`.

```bash
/home/krishna/food/script/dashvanti-kafka.sh
```

The script starts Kafka, creates the `dashvanti.events` topic, starts the backend Kafka worker, and keeps logs under `/home/krishna/food/logs`.
