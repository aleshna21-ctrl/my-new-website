import threading
import time
import urllib.request

from .ledger import snapshot
from .storage import loads, utcnow


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Hermes redirects are refused')


class HermesProbe:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {'connected': False, 'state': 'standby', 'models': [], 'checked_at': None}

    def probe(self):
        started = time.monotonic()
        result = {'connected': False, 'state': 'standby', 'models': [], 'checked_at': utcnow()}
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open('http://127.0.0.1:8080/v1/models', timeout=1.5) as response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise ValueError('Model response exceeds bound')
                data = loads(raw)
            ids = [item['id'] for item in data['data'] if isinstance(item, dict) and isinstance(item.get('id'), str)]
            result.update(connected=True, state='connected', models=ids[:10])
        except Exception as exc:
            result['error'] = type(exc).__name__
        result['latency_ms'] = str(round((time.monotonic() - started) * 1000))
        with self.lock:
            self.state = result

    def run(self, stop):
        while not stop.is_set():
            self.probe()
            stop.wait(5)

    def get(self, config):
        with self.lock:
            result = dict(self.state)
        result['endpoint'] = 'http://127.0.0.1:8080/v1'
        result['max_tokens'] = 4096
        try:
            data, stale = snapshot(config)
            telemetry = data.get('hermes')
            if not isinstance(telemetry, dict):
                raise ValueError('No inference telemetry')
            attempts = telemetry.get('attempts', [])
            if not isinstance(attempts, list):
                raise ValueError('Invalid attempts list')
            result['telemetry'] = telemetry
            result['snapshot_stale'] = stale
            result['repair_bound_breach'] = len(attempts) > 2 or telemetry.get('max_retries') != 1
            result['usage_note'] = 'estimated_tokens includes prompt and output; it is not measured completion usage.'
        except Exception as exc:
            result['telemetry'] = None
            result['telemetry_error'] = type(exc).__name__
        return result
