import ipaddress
import logging
import os
import re
import time
from logging.handlers import WatchedFileHandler
from pathlib import Path

ROLES = {'customer', 'restaurant', 'driver', 'admin'}
ACTIVITIES = {
    '/customer/live-alerts': 'Customer checking live alerts',
    '/customer/order-sound': 'Customer checking order sound',
    '/customer/orders': 'Customer viewing orders',
    '/restaurant/orders': 'Restaurant checking orders',
    '/restaurant/update-status': 'Restaurant updating order status',
    '/driver/location/update': 'Driver sending GPS update',
    '/driver/status/update': 'Driver updating status',
    '/driver/navigation/start': 'Driver starting navigation',
    '/admin/orders': 'Admin reviewing orders',
    '/admin/restaurants': 'Admin managing restaurants',
}

def clean(value, limit=512):
    return ''.join(c for c in str(value) if c.isprintable())[:limit]

def request_role(path):
    prefix = path.strip('/').split('/', 1)[0]
    return prefix.upper() if prefix in ROLES else 'SYSTEM'

def activity(path):
    return ACTIVITIES.get(path.rstrip('/'), 'API request')

def user_id(value):
    value = str(value or '')
    return value if re.fullmatch(r'[0-9]{1,20}', value) else '-'

def client_ip(peer, forwarded='', trusted=None):
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return '-'
    networks = trusted if trusted is not None else os.getenv(
        'LOG_TRUSTED_PROXIES', '127.0.0.1/32,::1/128'
    ).split(',')
    try:
        networks = [ipaddress.ip_network(n.strip()) for n in networks if n.strip()]
        if not any(address in n for n in networks):
            return str(address)
        chain = [ipaddress.ip_address(p.strip()) for p in forwarded.split(',') if p.strip()]
    except ValueError:
        return str(address)
    for candidate in reversed(chain):
        address = candidate
        if not any(address in n for n in networks):
            break
    return str(address)

class CleanRequestFormatter(logging.Formatter):
    converter = time.gmtime

    def format(self, record):
        timestamp = self.formatTime(record, '%Y-%m-%d %H:%M:%S')
        return (
            f'{timestamp} [{record.levelname}] {record.role} REQUEST '
            f'{clean(record.path)} RESPONSE {record.status} Duration={record.duration:.0f}ms\n'
            f'Activity: {record.activity}\n'
            f'UserID: {user_id(record.user_id)}\n'
            f'IP: {record.client_ip}'
        )

def configure_logging(name, path=None):
    logger = logging.getLogger(name)
    if not logger.handlers:
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            handler = WatchedFileHandler(path, encoding='utf-8', delay=True)
        else:
            handler = logging.StreamHandler()
        handler.setFormatter(CleanRequestFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger

def log_request(logger, path, status, started, identity='-', ip='-', failed=False):
    path = path.split('?', 1)[0]
    duration = (time.perf_counter() - started) * 1000
    level = logging.ERROR if failed or status >= 400 else (
        logging.WARNING if duration > 1000 else logging.INFO
    )
    logger.log(level, '', extra={
        'role': request_role(path), 'path': path.split('?', 1)[0],
        'status': status, 'duration': duration, 'activity': activity(path),
        'user_id': identity, 'client_ip': ip,
    })
