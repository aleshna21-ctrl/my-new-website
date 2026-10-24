export const el = (tag, text, cls) => {const node = document.createElement(tag); if (text !== undefined) node.textContent = String(text); if (cls) node.className = cls; return node;};
export function details(label, value) {const node=el('details'); node.append(el('summary',label),el('pre',typeof value==='string'?value:JSON.stringify(value,null,2))); return node;}
export function note(text, cls='note') {return el('p',text,cls);}
export async function request(path, payload) {
  const controller=new AbortController(); const timer=setTimeout(()=>controller.abort(),4000);
  try {
    const options={signal:controller.signal,cache:'no-store'};
    if(payload!==undefined){const session=await fetch('/api/session',{signal:controller.signal,cache:'no-store'}).then(r=>r.json()); Object.assign(options,{method:'POST',headers:{'Content-Type':'application/json','X-HUD-Token':session.token},body:JSON.stringify(payload)});}
    const response=await fetch(path,options); const data=await response.json();
    if(!response.ok) throw new Error(data.error||'Request failed');
    if(data.status==='unavailable') throw new Error(`${data.error}: ${data.message}`);
    return data;
  } finally {clearTimeout(timer);}
}
export function poll(id,path,render,period=5000){
  const root=document.getElementById(id); let stopped=false; let pending=false;
  const tick=async()=>{if(stopped||pending)return;pending=true;try{
    const data=await request(path);
    // Keep details open without freezing health/freshness when a panel has keyboard focus.
    const expanded=new Set([...root.querySelectorAll('details[open]')].map(n=>n.querySelector('summary')?.textContent));
    const active=document.activeElement;const focusIndex=[...root.querySelectorAll('button,summary')].indexOf(active);
    const scrolls=[...root.querySelectorAll('.scroll,.table-wrap')].map(n=>n.scrollTop);
    render(root,data);
    root.querySelectorAll('details').forEach(n=>{n.open=expanded.has(n.querySelector('summary')?.textContent);});
    root.querySelectorAll('.scroll,.table-wrap').forEach((n,i)=>{n.scrollTop=scrolls[i]||0;});
    if(focusIndex>=0)root.querySelectorAll('button,summary')[focusIndex]?.focus({preventScroll:true});
  }catch(error){root.replaceChildren(note('Unavailable','state amber'),note(error.message),note('This module will retry automatically.'));}finally{pending=false;if(!stopped)setTimeout(tick,period);}};
  tick(); return {refresh:tick,stop:()=>{stopped=true;}};
}
export function table(headers,rows){const wrap=el('div',undefined,'table-wrap'), t=el('table'), head=el('thead'),tr=el('tr');headers.forEach(v=>tr.append(el('th',v)));head.append(tr);t.append(head);const body=el('tbody');rows.forEach(values=>{const r=el('tr');values.forEach(v=>r.append(el('td',v??'—')));body.append(r);});t.append(body);wrap.append(t);return wrap;}
export function stats(values){const grid=el('div',undefined,'stat-grid');Object.entries(values).forEach(([key,value])=>{const cell=el('div',undefined,'stat');cell.append(el('small',key),el('strong',value));grid.append(cell);});return grid;}
