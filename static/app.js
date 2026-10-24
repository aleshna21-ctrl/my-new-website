// Independent imports: a failed renderer does not prevent sibling modules from starting.
for (const name of ['hud','hermes','ledger','gtm','alerts']) {
  import(`/static/modules/${name}.js`).then(module=>module.start()).catch(error=>{
    const target=document.getElementById(name); if(target)target.textContent=`Renderer unavailable: ${error.message}`;
  });
}
