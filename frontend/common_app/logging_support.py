import ipaddress
import logging
import os
import re
import socket
import time
import uuid
from datetime import datetime, timezone
from logging.handlers import WatchedFileHandler
from pathlib import Path

_LAST_LOGGED = {}
_THROTTLE_SECONDS = float(os.getenv('LOG_REPEAT_THROTTLE_SECONDS', '3'))

ROLES = {'customer', 'restaurant', 'driver', 'admin'}
ACTIVITY = {
    '/customer/live-alerts': ('CustomerLiveAlerts', 'Alerts requested', 'Return live alerts', 'Live alerts returned'),
    '/customer/order-sound': ('CustomerOrderSound', 'Sound check requested', 'Check order sound', 'Order sound status returned'),
    '/customer/orders': ('CustomerOrdersViewed', 'Orders requested', 'Load customer orders', 'Customer orders returned'),
    '/customer/login': ('CustomerLogin', 'Login Initiated -> OTP Sent -> OTP Verified -> Session Created', 'Authenticate Customer', 'Customer authenticated successfully'),
    '/customer/order': ('CustomerOrderPlacement', 'Order Initiated -> Cart Validated -> Payment Started -> Order Created', 'Create Customer Order', 'Order created successfully'),
    '/restaurant/orders': ('RestaurantOrdersViewed', 'Orders requested -> Orders loaded', 'Load restaurant orders', 'Restaurant orders returned'),
    '/restaurant/update-status': ('RestaurantOrderStatusUpdated', 'Order selected -> Status changed -> Customer notified', 'Update order status', 'Order status updated'),
    '/driver/location/update': ('DriverLocationUpdated', 'GPS Captured -> Location Saved -> Tracking Updated', 'Save Driver GPS', 'Driver location saved'),
    '/driver/status/update': ('DriverStatusUpdated', 'Status selected -> Order updated -> Customer notified', 'Update Driver Status', 'Driver status updated'),
    '/driver/navigation/start': ('DriverNavigationStarted', 'Order assigned -> Navigation requested -> Route loaded', 'Start Driver Navigation', 'Driver navigation started'),
    '/admin/orders': ('AdminOrdersReviewed', 'Orders requested -> Filters applied -> Results loaded', 'Review orders', 'Admin orders returned'),
    '/admin/restaurants': ('AdminRestaurantsManaged', 'Restaurants requested -> Data loaded', 'Manage restaurants', 'Restaurant records returned'),
}


def clean(value, limit=512):
    return ''.join(c for c in str(value if value is not None else '-') if c.isprintable()).replace('|', '/').strip()[:limit] or '-'


def quote(value):
    return '"' + clean(value).replace('"', "'") + '"'


def normalized_path(path):
    path = '/' + str(path or '/').split('?', 1)[0].strip('/')
    return path[4:] if path.startswith('/api/') else path


def request_role(path):
    prefix = normalized_path(path).strip('/').split('/', 1)[0]
    return prefix.upper() if prefix in ROLES else 'SYSTEM'


def activity(path):
    return ACTIVITY.get(normalized_path(path).rstrip('/'), ('APIRequest', 'Request received -> Handler executed -> Response returned', 'Handle API request', 'Request completed'))[1]


def event_profile(path):
    clean_path = normalized_path(path).rstrip('/')
    if re.fullmatch(r'/customer/order/\d+/track', clean_path):
        return ('CustomerOrderTrackingViewed', 'Order selected -> Tracking loaded -> Driver location displayed', 'Load live tracking', 'Tracking details returned')
    if re.fullmatch(r'/restaurant/order/\d+/status', clean_path):
        return ('RestaurantOrderStatusUpdated', 'Order selected -> Status changed -> Customer notified', 'Update order status', 'Order status updated')
    if re.fullmatch(r'/(customer|restaurant|driver|admin)/order/\d+', clean_path):
        return ('OrderDetailsViewed', 'Order selected -> Details loaded', 'Load order details', 'Order details returned')
    return ACTIVITY.get(clean_path, ('APIRequest', 'Request received -> Handler executed -> Response returned', 'Handle API request', 'Request completed'))


def user_id(value):
    value = str(value or '')
    return value if re.fullmatch(r'[0-9]{1,20}', value) else '-'


def client_ip(peer, forwarded='', trusted=None):
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return '-'
    networks = trusted if trusted is not None else os.getenv('LOG_TRUSTED_PROXIES', '127.0.0.1/32,::1/128').split(',')
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


def _order_id(path, fields):
    if fields.get('order_id'):
        return clean(fields.get('order_id'), 40)
    match = re.search(r'/order(?:s)?/(\d+)|/order/(\d+)', normalized_path(path))
    return next((g for g in (match.groups() if match else ()) if g), '-')


def _role_fields(role, fields):
    uid = user_id(fields.get('user_id'))
    name = fields.get('user_name') or fields.get('name') or '-'
    phone = fields.get('phone') or '-'
    if role == 'CUSTOMER':
        return f'CustomerName={quote(name)} | CustomerID={uid} | Phone={clean(phone, 60)}'
    if role == 'RESTAURANT':
        return f'RestaurantName={quote(name)} | RestaurantID={uid}'
    if role == 'DRIVER':
        return f'DriverName={quote(name)} | DriverID={uid}'
    if role == 'ADMIN':
        return f'AdminName={quote(name)} | AdminID={uid}'
    return f'UserID={uid}'


def _status_text(level, status, failed):
    if failed:
        return 'EXCEPTION'
    if status >= 400:
        return 'FAILED'
    if level == logging.WARNING:
        return 'WARNING'
    return 'SUCCESS'


def _map_related(path):
    value = normalized_path(path).lower()
    return any(token in value for token in ('map', 'tracking', 'location', 'route-distance', 'navigation'))


def _should_log(path, method, status, identity, ip):
    if _map_related(path):
        return True
    now = time.monotonic()
    key = (normalized_path(path), method, int(status), user_id(identity), ip)
    last = _LAST_LOGGED.get(key, 0)
    if now - last < _THROTTLE_SECONDS:
        return False
    _LAST_LOGGED[key] = now
    if len(_LAST_LOGGED) > 5000:
        cutoff = now - 60
        for old_key, old_time in list(_LAST_LOGGED.items()):
            if old_time < cutoff:
                _LAST_LOGGED.pop(old_key, None)
    return True


def _level(status, duration, failed):
    if failed or status >= 400:
        return logging.ERROR
    if duration > 1000:
        return logging.WARNING
    return logging.INFO


class CleanRequestFormatter(logging.Formatter):
    converter = time.gmtime

    def format(self, record):
        timestamp = datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        return (
            f'{timestamp} [{record.levelname}] EVENT={clean(record.event)} | {record.identity_fields} | '
            f'Timeline={quote(record.timeline)} | ActionItem={quote(record.action_item)} | Status={quote(record.status_text)} | '
            f'API={clean(record.method, 12)} {clean(record.path, 240)} | HTTPStatus={record.status} | Duration={record.duration:.0f}ms | '
            f'OrderID={clean(record.order_id, 40)} | Device={clean(record.device, 120)} | AppVersion={clean(record.app_version, 40)} | '
            f'IP={clean(record.client_ip, 60)} | Geo={clean(record.geo, 120)} | CorrelationID={clean(record.correlation_id, 80)} | '
            f'RequestID={clean(record.request_id, 80)} | ServerNode={clean(record.server_node, 80)} | '
            f'BuildVersion={clean(record.build_version, 60)} | Outcome={quote(record.outcome)}'
        )


def configure_logging(name, path=None):
    logger = logging.getLogger(name)
    if not logger.handlers:
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            handler = WatchedFileHandler(path, encoding='utf-8', delay=True)
        else:
            handler = logging.StreamHandler()
        logger.addHandler(handler)
    for handler in logger.handlers:
        handler.setFormatter(CleanRequestFormatter())
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def log_request(logger, path, status, started, identity='-', ip='-', failed=False, method='REQUEST', context=None):
    context = dict(context or {})
    path = normalized_path(path)
    duration = (time.perf_counter() - started) * 1000
    if not _should_log(path, method, status, identity, ip):
        return False
    level = _level(status, duration, failed)
    event, timeline, action, ok_outcome = event_profile(path)
    status_text = _status_text(level, status, failed)
    outcome = context.get('outcome') or (ok_outcome if status < 400 and not failed else 'Request failed; support can review correlation details')
    context.setdefault('user_id', identity)
    logger.log(level, '', extra={
        'event': context.get('event') or event,
        'identity_fields': _role_fields(request_role(path), context),
        'timeline': context.get('timeline') or timeline,
        'action_item': context.get('action_item') or action,
        'status_text': status_text,
        'method': method,
        'path': path,
        'status': status,
        'duration': duration,
        'order_id': _order_id(path, context),
        'device': context.get('device') or '-',
        'app_version': context.get('app_version') or os.getenv('APP_VERSION', '-'),
        'client_ip': ip,
        'geo': context.get('geo') or '-',
        'correlation_id': context.get('correlation_id') or str(uuid.uuid4()),
        'request_id': context.get('request_id') or 'req-' + uuid.uuid4().hex[:12],
        'server_node': os.getenv('SERVER_NODE', socket.gethostname()),
        'build_version': os.getenv('BUILD_VERSION', os.getenv('APP_VERSION', '-')),
        'outcome': outcome,
    })
    return True
