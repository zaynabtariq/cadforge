import json
import time
import urllib.error
import urllib.request
import uuid


class BridgeError(RuntimeError):
    def __init__(self, code, message, status=502):
        super().__init__(message)
        self.code, self.status = code, status


class BridgeClient:
    """No global endpoint; each connector is bound to one verified SSH tunnel."""
    def __init__(self, endpoint):
        self.endpoint = endpoint.rstrip('/')

    def call(self, route, body=None, *, key=None, timeout=150):
        deadline = time.monotonic() + timeout
        get = route in ('/health', '/ready') or route.startswith('/requests/')
        headers = {'Content-Type': 'application/json'}
        if not get: headers['Idempotency-Key'] = key or str(uuid.uuid4())
        req = urllib.request.Request(self.endpoint + route, headers=headers,
            data=None if get else json.dumps(body or {}, allow_nan=False).encode())
        try:
            with urllib.request.urlopen(req, timeout=min(40, timeout)) as response:
                data = response.read(8 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            try: detail = json.load(exc)
            except Exception: detail = {}
            raise BridgeError(detail.get('code', 'bridge_http_error'),
                              detail.get('message', 'Fusion rejected the request'), exc.code) from None
        except (OSError, urllib.error.URLError):
            raise BridgeError('unreachable', 'Fusion connection is unavailable', 503) from None
        if len(data) > 8 * 1024 * 1024:
            raise BridgeError('result_too_large', 'Bridge response exceeds limit')
        result = json.loads(data)
        if result.get('code') == 'pending':
            request_id, session_id = result['request_id'], result['session_id']
            while time.monotonic() < deadline:
                current = self.call('/requests/' + request_id, timeout=min(10, max(1, deadline-time.monotonic())))
                if current['session_id'] != session_id:
                    raise BridgeError('session_changed', 'Fusion restarted; inspect state before retrying', 409)
                if current['state'] in ('completed', 'failed', 'cancelled'):
                    result = current['result']; break
                time.sleep(.3)
            else:
                raise BridgeError('pending', 'Operation is still pending; it was not replayed', 504)
        if result.get('error') is True or result.get('success') is False:
            raise BridgeError(result.get('code', 'fusion_error'), result.get('message', 'Fusion operation failed'))
        return result
