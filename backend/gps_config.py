import os

ENABLED = os.getenv('GPS_STREAMING_ENABLED', 'false').lower() == 'true'
REDIS_URL = os.getenv('GPS_REDIS_URL', 'redis://127.0.0.1:6379/2')
BROKERS = os.getenv('GPS_KAFKA_BROKERS', '127.0.0.1:9092')
TOPIC = 'driver_location_stream'
TTL = int(os.getenv('GPS_TTL_SECONDS', '45'))
ORIGINS = set(os.getenv('GPS_ALLOWED_ORIGINS', 'https://driver.dashvanti.com,https://customer.dashvanti.com,https://restaurant.dashvanti.com,https://admin.dashvanti.com').split(','))
FINAL = {'DELIVERED', 'REJECTED', 'CANCELLED', 'CANCELED'}
