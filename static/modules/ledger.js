import {el,poll,note,details,table,stats} from '../core.js';
export function start(){poll('ledger','/api/offline-ledger',(root,data)=>{
  const inv=data.invariant; const body=[el('p',`${inv.status} · reconciliation counts`,`state ${inv.status==='PASS'?'good':inv.status==='BREACH'?'bad':'amber'}`),note(inv.reason)];
  if(inv.totals)body.push(stats(inv.totals));else body.push(el('div','No final batch counters were published. Job completion alone does not prove reconciliation.','empty'));
  if(inv.failed_batches?.length)body.push(note(`Failing batches: ${inv.failed_batches.join(', ')}`,'bad'));
  if(inv.recorded_at)body.push(note(`Report: ${inv.recorded_at} · Job ${inv.job_id||'unspecified'}`));
  body.push(table(['Job','State','Attempts','Updated'],data.jobs.map(j=>[j.job_id,j.state,j.attempt_count,j.updated_at])));
  body.push(note(`${data.jobs.length} most recent rows · Export ${data.exported_at}${data.status==='stale'?' · STALE':''}`));
  body.push(details('Quarantined rows',data.quarantine??'Not exported. No rows are inferred from job state.'));
  body.push(details('Exact Decimal risk profiles',data.risk_profiles??'Not exported. Financial values will render as exact strings.'));
  body.push(note(data.event_capture?'Transactional terminal-event capture installed.':'Event capture is not installed; every transition cannot be guaranteed.','note '+(data.event_capture?'':'amber')));
  if(Object.keys(data.source_errors||{}).length)body.push(details('Source availability',data.source_errors));
  root.replaceChildren(...body);
});}
