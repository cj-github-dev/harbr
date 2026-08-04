
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
fetch('/data/experience.json',{cache:'no-store'}).then(r=>r.json()).then(d=>{
  $('#confidence-label').textContent=d.confidence.label;
  $('#story-text').textContent=d.story;
  $('#checks').innerHTML=d.checks.map(x=>`<div class="check"><span>${x[0]}</span><strong>${x[1]}</strong></div>`).join('');
  $('#archive-list').innerHTML=d.archives.map(x=>`<div class="archive"><strong>${x.split(' ')[1]}</strong><span>${x.split(' ')[0]}</span></div>`).join('');
});
$('#search').addEventListener('input',e=>{const q=e.target.value.toLowerCase();$$('#results article').forEach(a=>a.hidden=q&&!a.textContent.toLowerCase().includes(q));});
setTimeout(()=>$('#startup').classList.add('done'),2200);
