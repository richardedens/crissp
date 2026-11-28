(()=>{const tabs=[...document.querySelectorAll('section.stab')],links=[...document.querySelectorAll('.sub-tabs a')];
const show=()=>{const id=(location.hash||'#dashboard').slice(1);if(!tabs.some(t=>t.id==='tab-'+id))return;
tabs.forEach(t=>t.hidden=t.id!=='tab-'+id);links.forEach(a=>a.classList.toggle('on',a.hash==='#'+id));};
addEventListener('hashchange',show);show();})();
