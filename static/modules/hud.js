import {el,poll} from '../core.js';
export function start(){poll('hud','/api/hud',(root,data)=>{
  const h=data.hermes,l=data.ledger,a=data.alerts; const invariant=l.invariant?.status||'UNKNOWN';
  const model=h.models?.join(', ')||'No active model reported';
  const items=[['HERMES LOOPBACK',h.connected?'Connected':'Standby',model,h.connected?'good':'amber'],
    ['ZERO-LOSS COUNTS',invariant,'Received = Accepted + Quarantined + Duplicates',invariant==='PASS'?'good':invariant==='BREACH'?'bad':'amber'],
    ['LEDGER PULSE',l.status==='unavailable'?'Unavailable':`${l.counts?.running||'0'} running · ${l.counts?.completed||'0'} complete`,l.status==='unavailable'?'Counts unknown':`${l.counts?.quarantined||'0'} quarantined${l.status==='stale'?' · STALE':''}`,''],
    ['EMAIL DISPATCHER',a.armed?'Armed':'Not configured',a.last_sent_at?`Last sent ${a.last_sent_at}`:'No confirmed delivery',a.armed?'good':'amber']];
  root.replaceChildren(...items.map(([title,value,detail,cls])=>{const node=el('div',undefined,'pill');node.append(el('small',title),el('strong',value,cls),el('div',detail,'detail'));node.title=detail;return node;}));
});}
