import hmac
import json
import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .alerts import AlertCenter
from .gtm import Conflict, decide, view_queue
from .hermes import HermesProbe
from .ledger import get_ledger
from .omnibus import evaluate_jev_system_one, evaluate_jev_trading_rung, get_omnibus_bundle, query_project_assistant
from .storage import dumps, loads


def isolated(function):
    try:
        return function()
    except Exception as exc:
        return {'status': 'unavailable', 'error': type(exc).__name__, 'message': 'Source missing, busy or invalid. Other panels remain independent.'}


class Application:
    def __init__(self, config):
        self.config = config
        self.token = secrets.token_urlsafe(32)
        self.probe = HermesProbe()
        try:
            self.alerts = AlertCenter(config)
        except Exception:
            self.alerts = None
        self.stop = threading.Event()
        self.threads = []

    def start(self):
        targets = [self.probe.run]
        if self.alerts:
            targets.extend((self.alerts.run_observer, self.alerts.run_sender))
        for target in targets:
            thread = threading.Thread(target=target, args=(self.stop,), daemon=True)
            thread.start()
            self.threads.append(thread)

    def get(self, route):
        handlers = {'/api/hermes': lambda: self.probe.get(self.config),
                    '/api/offline-ledger': lambda: get_ledger(self.config),
                    '/api/gtm-queue': lambda: view_queue(self.config.queue),
                    '/api/alerts': lambda: self.alerts.view() if self.alerts else {'status': 'unavailable', 'error': 'AlertStoreUnavailable'},
                    '/api/omnibus': get_omnibus_bundle}
        if route == '/api/session':
            return {'token': self.token}
        if route == '/api/guardrail/events':
            from .jev_guard import GUARDRAIL_LOG
            if GUARDRAIL_LOG.exists():
                try:
                    return json.loads(GUARDRAIL_LOG.read_text(encoding='utf-8'))
                except Exception:
                    return []
            return []
        if route == '/api/jev-cheap-read/fixtures':
            from .jev_cheap_read import list_cheap_read_fixtures
            return list_cheap_read_fixtures()
        if route == '/api/jev-agentic/events':
            from .jev_agentic import AGENTIC_JEV_LOG
            if AGENTIC_JEV_LOG.exists():
                try:
                    return json.loads(AGENTIC_JEV_LOG.read_text(encoding='utf-8'))
                except Exception:
                    return []
            return []
        if route == '/api/jev-composite-gate/presets':
            from .jev_composite_gate import GTM_OUTREACH_WEIGHTS, CODE_REVIEW_WEIGHTS, IDEA_VERDICT_WEIGHTS
            return {
                'weights': {
                    'gtm_outreach': GTM_OUTREACH_WEIGHTS,
                    'code_review': CODE_REVIEW_WEIGHTS,
                    'idea_verdict': IDEA_VERDICT_WEIGHTS,
                },
                'confidence_thresholds': {'floor': 0.50, 'ceiling': 0.90},
            }
        if route == '/api/jev-e2e/events':
            from .jev_e2e_pipeline import get_recent_e2e_events
            return get_recent_e2e_events()
        if route == '/api/hud':
            ledger = isolated(handlers['/api/offline-ledger'])
            hermes = isolated(handlers['/api/hermes'])
            alerts = isolated(handlers['/api/alerts'])
            return {'hermes': hermes, 'ledger': ledger, 'alerts': alerts}
        if route not in handlers:
            raise KeyError(route)
        return isolated(handlers[route])

    def post(self, route, payload):
        if route == '/api/gtm-queue':
            if set(payload) != {'id', 'revision', 'decision'} or any(type(v) is not str for v in payload.values()):
                raise ValueError('Expected id, revision and decision strings')
            return decide(self.config.queue, payload['id'], payload['revision'], payload['decision'])
        if route == '/api/alerts':
            if not self.alerts:
                raise ValueError('Alert store unavailable; other modules remain usable')
            if payload == {'action': 'test'}:
                self.alerts.queue_test()
            elif set(payload) == {'action', 'event_id'} and payload['action'] == 'retry' and type(payload['event_id']) is str:
                self.alerts.retry(payload['event_id'])
            else:
                raise ValueError('Unsupported alert action')
            return self.alerts.view()
        if route == '/api/assistant':
            query = payload.get('query', '')
            scope = payload.get('scope', 'all')
            if type(query) is not str or type(scope) is not str:
                raise ValueError('Expected query and scope strings')
            return query_project_assistant(query, scope)
        if route == '/api/jev-decide':
            state = payload.get('state', {})
            questions = payload.get('questions', {})
            if not isinstance(state, dict) or not isinstance(questions, dict):
                raise ValueError('Expected state and questions dicts')
            return evaluate_jev_system_one(state, questions)
        if route == '/api/jev-rung':
            judgments = payload.get('judgments', {})
            breach = bool(payload.get('hard_risk_breach', False))
            if not isinstance(judgments, dict):
                raise ValueError('Expected judgments dict')
            return evaluate_jev_trading_rung(judgments, hard_risk_breach=breach)
        if route == '/api/guardrail/bash':
            command = payload.get('command', '')
            if type(command) is not str:
                raise ValueError('Expected command string')
            from .jev_guard import check_bash_command
            verdict = check_bash_command(command)
            return {
                'allowed': verdict.allowed,
                'command': verdict.command,
                'risk_score': verdict.risk_score,
                'reason': verdict.reason,
                'irreversible': verdict.irreversible,
                'notice': verdict.notice,
            }
        if route == '/api/jev-cheap-read':
            mode = payload.get('mode', 'bool')
            path = payload.get('path', '')
            question = payload.get('question', '')
            if type(mode) is not str or type(path) is not str or type(question) is not str:
                raise ValueError('Expected mode, path, and question strings')
            from .jev_cheap_read import ask_jev_file_bool, ask_jev_file_choice, ask_jev_file_score
            m = mode.strip().lower()
            if m == 'bool':
                return ask_jev_file_bool(path, question, str(payload.get('yes_criteria', '')), str(payload.get('no_criteria', '')))
            if m == 'choice':
                opts = payload.get('options', [])
                if not isinstance(opts, list):
                    raise ValueError('Expected options list')
                return ask_jev_file_choice(path, question, [str(x) for x in opts])
            if m == 'score':
                lvs = payload.get('levels', ['low', 'moderate', 'high', 'strict'])
                if not isinstance(lvs, list):
                    raise ValueError('Expected levels list')
                return ask_jev_file_score(path, question, [str(x) for x in lvs])
            raise ValueError('Unsupported cheap-read mode')
        if route == '/api/jev-multi-file':
            mode = payload.get('mode', 'scout')
            targets = payload.get('targets', 'second-brain')
            question = payload.get('question', '')
            if type(mode) is not str or type(question) is not str:
                raise ValueError('Expected mode and question strings')
            from .jev_multi_file import ask_jev_files, pick_first_file, scout_and_pick
            m = mode.strip().lower()
            if m == 'ask_files':
                return ask_jev_files(targets, payload.get('questions') or question)
            if m == 'pick_first':
                cands = targets if isinstance(targets, list) else [t.strip() for t in str(targets).split(',') if t.strip()]
                return pick_first_file([str(x) for x in cands], question)
            if m == 'scout':
                return scout_and_pick(targets, question)
            raise ValueError('Unsupported multi-file mode')
        if route == '/api/jev-agentic':
            from .jev_agentic import ask_jev, triage_failure, judge_diff, gate_plan
            mode = str(payload.get('mode', 'default')).strip().lower()
            state = payload.get('state')
            paths = payload.get('paths')
            command = payload.get('command')
            questions = payload.get('questions')
            if mode == 'triage':
                return triage_failure(state or 'execution_failure', command=command, candidate_paths=paths)
            if mode == 'judge_diff':
                return judge_diff(str(state or ''), target_files=paths)
            if mode == 'gate_plan':
                return gate_plan(str(state or ''), target_paths=paths)
            return ask_jev(state=state, paths=paths, command=command, questions=questions)
        if route == '/api/jev-composite-score':
            from .jev_composite_gate import evaluate_composite_score
            return evaluate_composite_score(
                target_kind=str(payload.get('target_kind', 'gtm_outreach')),
                target_data=payload.get('target_data'),
                weights_override=payload.get('weights'),
            )
        if route == '/api/jev-confidence-gate':
            from .jev_composite_gate import evaluate_confidence_gate
            return evaluate_confidence_gate(
                action_type=str(payload.get('action_type', 'bash_gate')),
                command_or_target=str(payload.get('target') or payload.get('command') or 'ls -la'),
                context=payload.get('context'),
            )
        if route == '/api/jev-e2e':
            from .jev_e2e_pipeline import run_e2e_invoice_to_gtm_pipeline
            return run_e2e_invoice_to_gtm_pipeline(
                invoice_fixture=str(payload.get('invoice_fixture', 'adversarial_fixture.csv')),
                stage_to_outbox=bool(payload.get('stage_to_outbox', True)),
            )
        raise KeyError(route)


def make_server(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'JEV-HUD'

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format, *args):
            # Request bodies, query strings and source data never enter logs.
            pass

        def safe_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{app.config.port}', f'localhost:{app.config.port}'}

        def respond(self, status, body, content_type='application/json; charset=utf-8'):
            raw = body if isinstance(body, bytes) else dumps(body).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if not self.safe_host():
                return self.respond(403, {'error': 'Loopback host required'})
            route = urlsplit(self.path).path
            try:
                if route.startswith('/api/'):
                    return self.respond(200, app.get(route))
                route = '/static/index.html' if route == '/' else route
                if not route.startswith('/static/'):
                    raise KeyError(route)
                root = (app.config.home / 'static').resolve()
                path = (app.config.home / route.lstrip('/')).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    raise KeyError(route)
                content_type = 'text/javascript' if path.suffix == '.js' else (mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
                return self.respond(200, path.read_bytes(), content_type + '; charset=utf-8')
            except KeyError:
                self.respond(404, {'error': 'Not found'})
            except Exception as exc:
                self.respond(503, {'error': type(exc).__name__})

        def do_POST(self):
            if not self.safe_host():
                return self.respond(403, {'error': 'Loopback host required'})
            origin = self.headers.get('Origin')
            if origin != 'http://' + self.headers['Host'] or not hmac.compare_digest(self.headers.get('X-HUD-Token', ''), app.token):
                return self.respond(403, {'error': 'Same-origin human-review session required'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json' or self.headers.get('Transfer-Encoding'):
                return self.respond(415, {'error': 'Bounded JSON request required'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('Invalid body length')
                payload = loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError('Expected a JSON object')
                return self.respond(200, app.post(urlsplit(self.path).path, payload))
            except Conflict as exc:
                self.respond(409, {'error': str(exc)})
            except (ValueError, TypeError) as exc:
                self.respond(400, {'error': str(exc)})
            except KeyError:
                self.respond(404, {'error': 'Not found'})
            except Exception as exc:
                self.respond(503, {'error': type(exc).__name__})

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = False

    return Server(('127.0.0.1', app.config.port), Handler)
