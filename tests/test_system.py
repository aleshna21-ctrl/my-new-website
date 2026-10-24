import concurrent.futures
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from hud.alerts import AlertCenter
from hud.config import Config
from hud.gtm import Conflict, approved_drafts, content_hash, decide, effective_status, read_queue, view_queue, write_queue
from hud.hermes import HermesProbe
from hud.ledger import evaluate_report, get_ledger
from hud.server import Application, make_server
from hud.storage import atomic_json, database, dumps, loads, read_json, utcnow, validate_money_strings
from offline_observer import export_once, install_event_capture
from offline_telemetry import BatchCounts, Money, annual_labor_cost, publish_reconciliation


class SystemTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.core = self.root / 'delivery-offline'
        self.core.mkdir()
        self.home = self.root / 'hud-interface'
        self.home.mkdir()
        self.queue = self.root / 'gtm' / 'staged_outreach.json'
        self.snapshot = self.home / 'inbox' / 'offline_snapshot.json'
        self.config = Config(self.home, self.queue, self.snapshot)
        self.dbpath = self.core / 'job_ledger.db'
        with database(self.dbpath) as db:
            db.execute('CREATE TABLE jobs(job_id TEXT PRIMARY KEY,job_type TEXT,state TEXT,attempt_count INTEGER,created_at TEXT,updated_at TEXT)')
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)', ('j1','reconcile','running',1,utcnow(),utcnow()))
        atomic_json(self.queue, [{'company_name':'Fixture','subject':'Review <script>','body':'Do not send','status':'needs_review'}])

    def tearDown(self):
        self.temp.cleanup()

    def event(self, suffix='one'):
        return {'event_id':suffix,'reference':'0123456789abcdef','kind':'transition','state':'completed'}

    def smtp(self):
        return {'JEV_SMTP_HOST':'invalid.example','JEV_SMTP_FROM':'owner@example.invalid', 'JEV_SMTP_TO':'owner@example.invalid'}

    def finish(self):
        with database(self.dbpath) as db:
            db.execute("UPDATE jobs SET state='completed' WHERE job_id='j1'")

    def test_money_exact_from_string(self):
        money = Money(amount='9007199254740993.12345678901234567890')
        self.assertEqual(json.loads(dumps(money.model_dump()))['amount'], money.amount)
        self.assertEqual(annual_labor_cost('1.25',12,Money(amount='54.00')).amount, '810.0000')
        for bad in [1.2, 1, True, 'NaN', 'Infinity']:
            with self.assertRaises((ValueError, ArithmeticError)):
                Money(amount=bad)

    def test_numeric_money_rejected(self):
        for raw in ['{"amount": 0.1}', '{"amount": 9007199254740993}']:
            with self.assertRaises(ValueError):
                validate_money_strings(loads(raw))

    def test_json_duplicate_nonfinite_float(self):
        for raw in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}']:
            with self.assertRaises(ValueError): loads(raw)
        self.assertEqual(loads('{"x":0.1}')['x'], Decimal('0.1'))
        with self.assertRaises(TypeError): dumps({'amount':0.1})

    def test_count_invariant_per_batch(self):
        report={'final':True,'batches':[{'batch_id':'a','received':2,'accepted':1,'quarantined':0,'duplicates':0},
                                         {'batch_id':'b','received':0,'accepted':1,'quarantined':0,'duplicates':0}]}
        self.assertEqual(evaluate_report(report)['status'],'BREACH')
        self.assertEqual(evaluate_report(None)['status'],'UNKNOWN')
        report['batches'][0]['received']=True
        with self.assertRaises(ValueError): evaluate_report(report)

    def test_snapshot_export_missing_optional(self):
        export_once(self.core,self.snapshot)
        result=get_ledger(self.config)
        self.assertEqual(result['invariant']['status'],'UNKNOWN')
        self.assertEqual(result['jobs'][0]['job_id'],'j1')
        self.assertIsNone(result['risk_profiles'])

    def test_final_report_and_staleness(self):
        self.finish()
        publish_reconciliation(self.core,'j1',[BatchCounts(batch_id='b1',received=4,accepted=2,quarantined=1,duplicates=1)],
                               risk_profiles={'labor':{'amount':'9007199254740993.0001','currency':'USD'}})
        export_once(self.core,self.snapshot)
        result=get_ledger(self.config)
        self.assertEqual(result['invariant']['status'],'PASS')
        self.assertEqual(result['risk_profiles']['data']['labor']['amount'],'9007199254740993.0001')
        snapshot=read_json(self.snapshot)
        snapshot['exported_at']=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
        atomic_json(self.snapshot,snapshot)
        self.assertEqual(get_ledger(self.config)['invariant']['status'],'STALE')

    def test_running_job_cannot_pass(self):
        publish_reconciliation(self.core,'j1',[BatchCounts(batch_id='b1',received=1,accepted=1,quarantined=0,duplicates=0)])
        export_once(self.core,self.snapshot)
        self.assertEqual(get_ledger(self.config)['invariant']['status'],'UNKNOWN')

    def test_durable_events_fast_transitions(self):
        install_event_capture(self.dbpath)
        with database(self.dbpath) as db:
            for state in ['quarantined','queued','running','completed']:
                db.execute('UPDATE jobs SET state=? WHERE job_id=?',(state,'j1'))
        result=export_once(self.core,self.snapshot)
        self.assertEqual([e['state'] for e in result['events']],['quarantined','completed'])
        self.assertTrue(result['ledger']['event_capture'])
        install_event_capture(self.dbpath)
        with database(self.dbpath) as db:
            db.execute('BEGIN')
            db.execute("UPDATE jobs SET state='quarantined'")
            db.rollback()
            self.assertEqual(db.execute('SELECT count(*) FROM hud_terminal_events').fetchone()[0],2)

    def test_no_ledger_creation_on_missing_source(self):
        missing=self.root/'missing'
        export_once(missing,self.snapshot)
        self.assertFalse(missing.exists())
        self.assertEqual(read_json(self.snapshot)['ledger']['status'],'unavailable')

    def test_approval_and_content_invalidation(self):
        view=view_queue(self.queue)
        result=decide(self.queue,view['drafts'][0]['id'],view['revision'],'approved')
        self.assertEqual(len(approved_drafts(self.queue)),1)
        draft=result['drafts'][0]
        draft['body']='Edited content'
        self.assertEqual(effective_status(draft),'needs_review')
        with self.assertRaises(Conflict): decide(self.queue,view['drafts'][0]['id'],view['revision'],'rejected')

    def test_concurrent_decisions_one_winner(self):
        view=view_queue(self.queue)
        def run(decision):
            try:
                decide(self.queue,view['drafts'][0]['id'],view['revision'],decision)
                return 'won'
            except Conflict: return 'conflict'
        with concurrent.futures.ThreadPoolExecutor(2) as executor:
            self.assertEqual(sorted(executor.map(run,['approved','rejected'])),['conflict','won'])

    def test_producer_cannot_self_approve(self):
        draft={'draft_id':'new','body':'test','status':'approved'}
        draft['approval_hash']=content_hash(draft)
        write_queue(self.queue,[draft])
        self.assertEqual(view_queue(self.queue)['drafts'][0]['effective_status'],'needs_review')
        self.assertTrue(Path(str(self.queue)+'.events.json').exists())

    def test_outbox_dedup_and_restart(self):
        alerts=AlertCenter(self.config,env={})
        alerts.enqueue(self.event());alerts.enqueue(self.event())
        self.assertEqual(alerts.view()['counts']['pending'],'1')
        with alerts.db() as db: db.execute("UPDATE alerts SET delivery_state='sending'")
        reloaded=AlertCenter(self.config,env={})
        self.assertEqual(reloaded.view()['counts']['uncertain'],'1')
        self.assertFalse(reloaded.send_one())

    def test_smtp_connection_failure_is_not_sent(self):
        alerts=AlertCenter(self.config,env=self.smtp());alerts.enqueue(self.event())
        with patch('hud.alerts.smtplib.SMTP',side_effect=OSError('secret-provider-data')): alerts.send_one()
        state=alerts.view()
        self.assertIsNone(state['last_sent_at'])
        self.assertNotIn('secret-provider-data',dumps(state))
        self.assertEqual(state['counts']['pending'],'1')

    def test_smtp_ambiguous_send(self):
        alerts=AlertCenter(self.config,env=self.smtp());alerts.enqueue(self.event())
        client=MagicMock();client.send_message.side_effect=TimeoutError('uncertain')
        with patch('hud.alerts.smtplib.SMTP',return_value=client):alerts.send_one()
        self.assertEqual(alerts.view()['counts']['uncertain'],'1')

    def test_smtp_metadata_only(self):
        alerts=AlertCenter(self.config,env=self.smtp());event=self.event();event['body']='sensitive financial amount';alerts.enqueue(event)
        client=MagicMock();client.send_message.return_value={}
        with patch('hud.alerts.smtplib.SMTP',return_value=client): alerts.send_one()
        message=client.send_message.call_args.args[0]
        self.assertNotIn('sensitive financial amount',message.as_string())
        self.assertEqual(alerts.view()['counts']['sent'],'1')

    def test_module_isolation(self):
        app=Application(self.config)
        self.assertEqual(app.get('/api/offline-ledger')['status'],'unavailable')
        self.assertEqual(app.get('/api/gtm-queue')['status'],'ok')
        self.queue.write_text('broken',encoding='utf-8')
        self.assertEqual(app.get('/api/gtm-queue')['status'],'unavailable')
        self.assertEqual(app.get('/api/alerts')['status'],'ok')

    def test_corrupt_alert_database_isolated(self):
        state=self.home/'state';state.mkdir();(state/'alerts.sqlite3').write_bytes(b'not SQLite')
        app=Application(self.config)
        self.assertEqual(app.get('/api/alerts')['status'],'unavailable')
        self.assertEqual(app.get('/api/gtm-queue')['status'],'ok')

    def test_hermes_offline_and_simulation_honesty(self):
        atomic_json(self.core/'inference_telemetry.json',{'max_retries':1,'attempts':[{'estimated_tokens':45}], 'is_simulated':True})
        export_once(self.core,self.snapshot)
        probe=HermesProbe()
        with patch('hud.hermes.urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=TimeoutError()
            probe.probe()
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'],1.5)
        data=probe.get(self.config)
        self.assertFalse(data['connected'])
        self.assertTrue(data['telemetry']['is_simulated'])
        self.assertNotIn('usage',data['telemetry'])

    def test_http_csrf_host_and_independent_routes(self):
        app=Application(replace(self.config,port=0))
        server=make_server(app)
        port=server.server_address[1]
        app.config=replace(app.config,port=port)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            connection=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
            connection.request('POST','/api/alerts',body='{"action":"test"}',headers={'Content-Type':'application/json'})
            response=connection.getresponse();self.assertEqual(response.status,403);response.read()
            connection.request('GET','/api/gtm-queue',headers={'Host':'evil.example'})
            response=connection.getresponse();self.assertEqual(response.status,403);response.read()
            connection.request('GET','/api/gtm-queue')
            response=connection.getresponse();self.assertEqual(response.status,200);response.read()
            connection.request('POST','/api/alerts',body='{"action":"test"}',headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{port}','X-HUD-Token':app.token})
            response=connection.getresponse();self.assertEqual(response.status,200);response.read()
            connection.close()
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
