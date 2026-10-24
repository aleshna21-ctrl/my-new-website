import {el,poll,note,details} from '../core.js';
export function start(){poll('hermes','/api/hermes',(root,data)=>{
  const body=[]; const telemetry=data.telemetry;
  body.push(el('p',data.connected?'Runtime connected':'Runtime on standby',`state ${data.connected?'good':'amber'}`));
  body.push(note(`${data.endpoint} · Probe ${data.latency_ms||'—'} ms`));
  body.push(note(`Active model: ${data.models?.join(', ')||'not reported'}`));
  if(!telemetry){body.push(el('div','No inference history has been exported yet. Endpoint health is independent of history.','empty'));root.replaceChildren(...body);return;}
  if(telemetry.is_simulated||String(telemetry.execution_mode).includes('simulat'))body.push(note('SIMULATED RESULT — not evidence of a live Hermes inference.','badge amber'));
  if(data.snapshot_stale)body.push(note('Snapshot is stale. The probe above is independent and current.','note amber'));
  body.push(note(`Last inference: ${telemetry.timestamp_utc||'unknown'} · ${telemetry.status||'unknown'}`));
  const usage=telemetry.usage?.completion_tokens;
  if(Number.isSafeInteger(usage)&&usage>=0){body.push(note(`Measured completion usage: ${usage} / 4096 tokens`));const meter=el('progress',undefined,'meter');meter.max=4096;meter.value=usage;meter.setAttribute('aria-label','Completion token usage');body.push(meter);if(usage>4096)body.push(note('Token limit exceeded in reported telemetry.','bad'));}
  else body.push(note('Completion tokens: unknown / 4096 · adapter reports estimates only.'));
  if(data.repair_bound_breach)body.push(note('REPAIR BOUND BREACH — expected at most two attempts.','bad'));
  for(const attempt of telemetry.attempts.slice(0,2)){const node=el('div',undefined,'attempt');node.append(el('b',`Attempt ${attempt.attempt} ${attempt.attempt===2?'· bounded repair':''}`),note(attempt.outcome||'No outcome'),note(`Estimated input + output tokens: ${attempt.estimated_tokens??'unknown'}`));if(attempt.error)node.append(details('Validation / endpoint log',attempt.error));body.push(node);}
  if(telemetry.attempts.length<2)body.push(note('Attempt 2: not used. One repair is the maximum.'));
  root.replaceChildren(...body);
});}
