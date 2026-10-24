import {el,poll,note,details,request} from '../core.js';
function render(root,data){
  const body=[el('p',data.armed?'Dispatcher armed':'SMTP not configured',`state ${data.armed?'good':'amber'}`),note(data.armed?'TLS enabled. Delivery is confirmed only after SMTP acceptance.':'Set SMTP environment variables and restart. Events remain in the local outbox.'),note(`Last confirmed send: ${data.last_sent_at||'none'}`),note(`Pending: ${data.counts.pending||'0'} · Sent: ${data.counts.sent||'0'} · Failed: ${data.counts.failed||'0'} · Uncertain: ${data.counts.uncertain||'0'}`)];
  const test=el('button','Queue test alert');test.type='button';test.disabled=!data.armed;test.addEventListener('click',async()=>{test.disabled=true;try{render(root,await request('/api/alerts',{action:'test'}));}catch(error){root.append(note(error.message,'bad'));test.disabled=false;}});body.push(test,note('Recipient comes only from SMTP configuration. No client data leaves through alerts.'));
  const logs=el('div',undefined,'scroll');
  for(const item of data.logs){const line=el('div',undefined,'alert-line');line.append(el('b',`${item.event_state} · ${item.delivery_state}`),note(`${item.reference} · ${item.sent_at||item.recorded_at}`));if(item.error)line.append(note(item.error,'note amber'));
    if(['failed','uncertain'].includes(item.delivery_state)){const retry=el('button','Retry after mailbox check','secondary');retry.addEventListener('click',async()=>{if(item.delivery_state==='uncertain'&&!confirm('SMTP delivery is uncertain. Verify your mailbox first; retrying can produce a duplicate. Continue?'))return;retry.disabled=true;try{render(root,await request('/api/alerts',{action:'retry',event_id:item.event_id}));}catch(error){line.append(note(error.message,'bad'));retry.disabled=false;}});line.append(retry);}logs.append(line);}
  if(!data.logs.length)logs.append(el('div','No alert events observed yet.','empty'));
  body.push(logs,details('Source watcher health',data.sources),note(data.notice));root.replaceChildren(...body);
}
export function start(){poll('alerts','/api/alerts',render);}
