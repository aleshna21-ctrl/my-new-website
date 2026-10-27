import threading
import time
import urllib.request
from typing import Any, Dict

from inference_adapter import LiveLocalModelAdapter, get_default_adapter
from .ledger import snapshot
from .storage import loads, utcnow


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Hermes redirects are refused')


class HermesProbe:
    """Telemetry and health probe for Hermes runtime, delegating to inference_adapter."""

    def __init__(self, adapter: LiveLocalModelAdapter = None):
        self.lock = threading.Lock()
        self.adapter = adapter or get_default_adapter()
        self.state: Dict[str, Any] = {'connected': False, 'state': 'standby', 'models': [], 'checked_at': None}

    def probe(self):
        started = time.monotonic()
        h = self.adapter.health(probe_live=True)
        with self.lock:
            self.state = {
                'connected': h.reachable,
                'state': h.state,
                'models': h.models[:10],
                'checked_at': utcnow(),
                'latency_ms': str(h.get('latency_ms', '0')),
            }
            if not h.reachable:
                self.state['error'] = h.get('live_probe_detail', 'Offline')

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
