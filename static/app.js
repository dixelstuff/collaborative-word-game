const $ = id => document.getElementById(id);
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const colours = ['#6573b8','#bd8834','#ba7586'];
let state, token, count = 2, busy = false, exposed = false, debug;

function saveSession() {
  try { sessionStorage.setItem('common-ground.v1',JSON.stringify({token,exposed,count})); } catch {}
}

async function api(action, data = {}) {
  const response = await fetch(`/api/${action}`, {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify({token,...data})});
  const result = await response.json();
  if (!response.ok) throw Error(result.error || 'The request failed. Please try again.');
  return result;
}

function lock(value) {
  busy = value;
  for (const button of document.querySelectorAll('button')) button.disabled = value;
  $('word').disabled = value || !state || state.won;
  $('suspect').disabled = value || !state;
  $('export').disabled = value || !debug;
  if (!value) {
    for (const b of document.querySelectorAll('[data-owner]')) b.disabled = state.won || Number(b.dataset.owner)!==state.active;
    $('play-form').querySelector('button').disabled = !state || state.won;
  }
}

function banner(text, error=false) {
  $('banner').textContent = text;
  $('banner').classList.toggle('error',error);
}

async function run(operation) {
  if (busy) return;
  lock(true);
  try { await operation(); }
  catch(error) { banner(error.message,true); }
  finally { lock(false); }
}

async function newGame(options={}) {
  banner('Finding fair starting words and different routes to the same mystery…');
  const result = await api('new',{players:count,...options});
  token = result.token; state = result.state;
  exposed = Boolean(options.target || options.starts); debug = null;
  saveSession();
  $('debug-target').textContent = '';
  $('diagnostics').textContent = ''; $('diagnostics').hidden = true;
  $('word').value = ''; $('suspect').value = '';
  $('feedback').textContent = 'Only landed words reveal how close they are. Keep comparing clues.';
  $('feedback').className = 'feedback';
  render();
  banner(exposed ? 'Test mystery · custom setup. Developer overrides bypass the balance checks.' : 'Mystery ready. Compare your starting clues, then follow a connection.');
}

function render() {
  $('word-count').textContent = state.words;
  $('rose-key').hidden = state.players.length!==3;
  const player = state.players[state.active];
  $('turn-label').textContent = state.won ? 'MYSTERY SOLVED' : `${player.name.toUpperCase()}’S TURN`;
  $('turn-label').style.color = colours[state.active];
  $('launch-label').innerHTML = state.won ? 'You found your common ground.' : `Launching from <strong>${esc(player.launch.toUpperCase())}</strong>`;
  $('turn-strip').querySelector('.turn-icon').style.color = colours[state.active];
  $('word').placeholder = state.won ? 'A mystery, solved together.' : `A word connected to ${player.launch.toUpperCase()}…`;
  $('collections').classList.toggle('three',state.players.length===3);
  $('collections').style.gridTemplateColumns = `repeat(${state.players.length},minmax(0,1fr))`;
  $('collections').innerHTML = state.players.map((p,i)=>`<article class="collection" style="--color:${colours[i]}"><div class="collection-heading"><h3><i class="dot" style="background:${colours[i]}"></i>${p.name}${!state.won && i===state.active?' <span>· your turn</span>':''}</h3><small>${p.words.length} launch ${p.words.length===1?'word':'words'}</small></div><div class="words">${p.words.map(w=>`<button class="word-chip ${w.word===p.launch?'selected':''}" data-owner="${i}" data-launch="${esc(w.word)}" aria-pressed="${w.word===p.launch}" ${state.won || i!==state.active?'disabled':''}>${esc(w.word.toUpperCase())}</button>`).join('')}</div></article>`).join('');
  renderMap(); renderSuspects(); renderResult();
}

function renderMap() {
  // Word Golf's .55 display curve is already applied by the rules module.
  // The fixed shared domain includes backward travel; vertical rows only avoid collisions.
  const x = position => 38 + Math.max(0,Math.min(1,(position-.43)/.57))*790;
  const layout = [], laneBottoms = [];
  let top = 42;
  for (let owner=0;owner<state.players.length;owner++) {
    const player = state.players[owner], rows = [], points = new Map();
    const words = [...player.words].sort((a,b)=>a.position-b.position);
    for (const item of words) {
      const px = x(item.position), width = Math.max(48,item.word.length*9+16);
      let row = rows.findIndex(end=>end < px-width/2-12);
      if (row<0) {row=rows.length;rows.push(0);}
      rows[row]=px+width/2;
      points.set(item.word,{x:px,y:top+row*45+27});
    }
    layout.push({owner,points});
    top += Math.max(100,rows.length*45+44);
    laneBottoms.push(top-20);
  }
  const height=top+10;
  let content = `<defs><radialGradient id="mystery-glow"><stop stop-color="#e5eadb" stop-opacity=".8"/><stop offset="1" stop-color="#e5eadb" stop-opacity="0"/></radialGradient></defs><ellipse cx="842" cy="${height/2}" rx="140" ry="${height/2}" fill="url(#mystery-glow)"/>`;
  for (const xx of [360,550,705,830]) content += `<path d="M ${xx} 20 Q ${xx-40} ${height/2} ${xx} ${height-10}" fill="none" stroke="#e1e6d8" stroke-dasharray="3 7"/>`;
  for (const lane of layout) {
    const p=state.players[lane.owner], colour=colours[lane.owner];
    for(const event of state.history.filter(h=>h.player===lane.owner)) {
      const a=lane.points.get(event.origin),b=lane.points.get(event.word);
      content += `<path d="M${a.x} ${a.y} C${(a.x+b.x)/2} ${a.y},${(a.x+b.x)/2} ${b.y},${b.x} ${b.y}" stroke="${colour}" stroke-opacity=".3" stroke-width="1.5" fill="none"/>`;
    }
    for (const item of p.words) {
      const point=lane.points.get(item.word), active=!state.won && lane.owner===state.active;
      const selected=item.word===p.launch;
      content += `<g class="map-node ${selected?'selected':''} ${active?'':'inactive'}" transform="translate(${point.x},${point.y})" style="color:${colour}" ${active?`role="button" tabindex="0" data-launch="${esc(item.word)}" aria-label="Launch from ${esc(item.word)}" aria-pressed="${selected}"`:`aria-label="${p.name}: ${esc(item.word)}"`}><circle class="node-ring" r="${selected?9:6}"/><circle class="node-core" r="${selected?2.5:2}"/><text class="map-label" x="0" y="-17" text-anchor="middle">${esc(item.word.toUpperCase())}</text></g>`;
    }
    if (lane.owner<state.players.length-1) content+=`<line x1="20" x2="850" y1="${laneBottoms[lane.owner]}" y2="${laneBottoms[lane.owner]}" stroke="#e5e8dc"/>`;
  }
  content += `<circle cx="843" cy="${height/2}" r="28" fill="#eff1e7" stroke="#bdc7af" stroke-dasharray="3 4"/><text x="843" y="${height/2+10}" text-anchor="middle" font-size="32" font-family="Georgia" fill="#6e8063">${state.won?'✓':'?'}</text><text x="843" y="${height/2+48}" text-anchor="middle" font-size="8" letter-spacing="1.6" fill="#859278">${state.won?'SOLVED':'MYSTERY'}</text>`;
  $('landscape').innerHTML=`<svg viewBox="0 0 900 ${height}" role="group" aria-label="Word proximity map. Farther right is closer to the mystery.">${content}</svg>`;
}

function renderSuspects() {
  $('empty-board').hidden=state.suspects.length>0;
  $('suspects-list').innerHTML=state.suspects.map(s=>`<li class="${s.eliminated?'eliminated':''}"><span class="suspect-word">${esc(s.word.toUpperCase())}</span><button data-action="favourite" data-word="${esc(s.word)}" class="${s.favourite?'favourite':''}" aria-pressed="${s.favourite}" aria-label="Favourite ${esc(s.word)}">${s.favourite?'★':'☆'}</button><button data-action="eliminated" data-word="${esc(s.word)}" aria-pressed="${s.eliminated}" aria-label="${s.eliminated?'Restore':'Eliminate'} ${esc(s.word)}">⊘</button><button data-action="remove" data-word="${esc(s.word)}" aria-label="Remove ${esc(s.word)}">×</button></li>`).join('');
}

function renderResult() {
  $('result').hidden=!state.won;
  if (!state.won) { $('result').innerHTML=''; return; }
  $('result').innerHTML=`<p class="eyebrow">YOU FOUND YOUR COMMON GROUND ${exposed?'<span class="spoiled">DEVELOPER TEST ROUND</span>':''}</p><h2>The mystery was <em>${esc(state.target.toUpperCase())}.</em></h2><p>Your team solved it in <strong>${state.words} ${state.words===1?'word':'words'}</strong>. Different journeys. One discovery.</p><div class="awards">${state.awards.map(a=>`<div class="award"><strong>${a.title}</strong><span style="color:${colours[a.player]}">${state.players[a.player].name}</span> · ${esc(a.origin.toUpperCase())} → ${esc(a.word.toUpperCase())}</div>`).join('')}</div><p class="board-note" style="padding:0;margin-bottom:0">Accolades are experimental: cleverness rewards useful progress through a less obvious connection; One Hit Wonder recognises the largest advance.</p>`;
}

async function select(word) {
  await run(async()=>{ const r=await api('select',{word});state=r.state;render();banner(`Launch point changed to ${word.toUpperCase()}.`); });
}

document.addEventListener('click',event=>{
  const target=event.target.closest('[data-launch]');
  if (target && !target.disabled) select(target.dataset.launch);
});
$('landscape').addEventListener('keydown',event=>{
  const target=event.target.closest('[data-launch]');
  if(target && (event.key==='Enter'||event.key===' ')){event.preventDefault();select(target.dataset.launch);}
});
$('player-count').addEventListener('click',event=>{
  const button=event.target.closest('[data-count]');if(!button || busy)return;
  count=Number(button.dataset.count);
  for(const b of $('player-count').querySelectorAll('button'))b.setAttribute('aria-pressed',String(b===button));
  banner(`${count} players selected for your next mystery. Press New mystery to begin.`);
});
$('new-game').onclick=()=>run(()=>newGame());
$('play-form').onsubmit=event=>{
  event.preventDefault();
  run(async()=>{
    const player=state.players[state.active].name;
    const result=await api('submit',{word:$('word').value});
    state=result.state;render();
    const success=result.event.success;
    $('feedback').textContent=success?`${player} landed ${result.event.word.toUpperCase()}. ${state.won?'Mystery solved together!':`${state.players[state.active].name}, follow the next clue.`}`:result.event.message;
    $('feedback').className=`feedback${success?'':' miss'}`;
    banner(state.won?'A shared mystery, solved. Start another whenever you’re ready.':exposed?'Developer test · target exposed.':'Compare your clues. Every landed word adds to the picture.');
    $('word').value='';
    if(exposed && debug)await updateDebug();
    setTimeout(()=>{if(!state.won)$('word').focus();},0);
  });
};
$('suspect-form').onsubmit=event=>{
  event.preventDefault();run(async()=>{
    const result=await api('suspect',{action:'add',word:$('suspect').value});
    state=result.state;renderSuspects();$('suspect').value='';banner('Hunch added. The board never checks a word against the mystery.');
  });
};
$('suspects-list').onclick=event=>{
  const button=event.target.closest('[data-action]');if(!button)return;
  run(async()=>{const r=await api('suspect',{action:button.dataset.action,word:button.dataset.word});state=r.state;renderSuspects();});
};
async function updateDebug() {
  debug=await api('debug');
  $('debug-target').textContent=`Mystery: ${debug.target.toUpperCase()} · test round`;
  $('diagnostics').hidden=false;$('diagnostics').textContent=JSON.stringify(debug,null,2);
}
$('reveal').onclick=()=>run(async()=>{await updateDebug();exposed=true;saveSession();renderResult();banner('Developer test · mystery revealed. This round is marked as target exposed.');});
$('export').onclick=()=>{
  if(!debug)return;
  const blob=new Blob([JSON.stringify({prototype:'Common Ground v1',state,debug},null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='common-ground-test.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
$('override-form').onsubmit=event=>{
  event.preventDefault();
  const options={},target=$('override-target').value.trim(),starts=$('override-starts').value.trim(),seed=$('override-seed').value;
  if(target)options.target=target;
  if(starts)options.starts=starts.split(',').map(s=>s.trim());
  if(seed!=='')options.seed=Number(seed);
  run(()=>newGame(options));
};
$('help').onclick=()=>$('help-dialog').showModal();
$('close-help').onclick=$('understood').onclick=()=>$('help-dialog').close();
$('help-dialog').addEventListener('click',event=>{if(event.target===$('help-dialog')){const r=$('help-dialog').getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)$('help-dialog').close();}});
fetch('/api/config').then(r=>r.json()).then(config=>{$('model-note').textContent=`${config.vocabulary.toLocaleString()} real words · GloVe 6B · Local play`;}).catch(()=>{});
run(async()=>{
  let saved;
  try {saved=JSON.parse(sessionStorage.getItem('common-ground.v1'));}catch{}
  if(saved?.token){
    token=saved.token;
    try {
      const result=await api('state');state=result.state;
      count=state.players.length;exposed=Boolean(saved.exposed);
      for(const b of $('player-count').querySelectorAll('button'))b.setAttribute('aria-pressed',String(Number(b.dataset.count)===count));
      render();banner(exposed?'Resumed developer test round.':'Your mystery is ready to continue.');return;
    }catch{}
  }
  await newGame();
});
