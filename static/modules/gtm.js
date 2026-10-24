import {el,poll,note,request} from '../core.js';
function render(root,data){
  const body=[note(data.notice)]; const pending=data.drafts.filter(d=>d.effective_status==='needs_review');
  body.push(el('p',`${pending.length} awaiting your review`,'state'));
  const list=el('div',undefined,'scroll');
  for(const draft of data.drafts){const card=el('article',undefined,'draft');const row=el('div',undefined,'row');row.append(el('h3',draft.company_name||draft.recipient_ref||'Untitled draft'),el('span',draft.effective_status,'badge '+(draft.effective_status==='needs_review'?'amber':'')));card.append(row,note(`To: ${draft.recipient_ref||'not specified'}`),el('p',draft.subject||'(No subject)','subject'),el('div',draft.body||'(No body)','body'));
    if(draft.effective_status==='needs_review'){const actions=el('div',undefined,'actions');for(const [label,decision] of [['Approve','approved'],['Reject','rejected']]){const button=el('button',label,decision==='rejected'?'secondary':'');button.type='button';button.addEventListener('click',async()=>{actions.querySelectorAll('button').forEach(b=>b.disabled=true);try{render(root,await request('/api/gtm-queue',{id:draft.id,revision:data.revision,decision}));}catch(error){card.append(note(error.message,'note bad'));actions.querySelectorAll('button').forEach(b=>b.disabled=false);}});actions.append(button);}card.append(actions);}
    list.append(card);
  }
  if(!data.drafts.length)list.append(el('div','No staged outreach. New drafts will appear here for review.','empty'));
  body.push(list);root.replaceChildren(...body);
}
export function start(){poll('gtm','/api/gtm-queue',render);}
