const $=s=>document.querySelector(s);
const fmt=x=>x==null?'—':Number(x).toLocaleString('uk-UA');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const apiCache=new Map();
let stoneNames={},itemNames={},allCharacters=[],sortKey='name',sortDescending=false,currentWid=null;
fetch('/stone_names.json').then(r=>r.json()).then(x=>stoneNames=x).catch(()=>{});
fetch('/item_names.json').then(r=>r.json()).then(x=>itemNames=x).catch(()=>{});
async function api(u,opts){let p=fetch(u,opts).then(r=>{if(!r.ok)throw Error(r.status);return r.json()});return await p}
function statusLabel(state,count,fullBuff=false){if(fullBuff)return 'Повний баф';if(state==='WITH_BUFFS')return `З бафом${count!=null?' ('+count+')':''}`;if(state==='NO_REPORTED_STATUSES')return 'Без бафів';return 'Статус невідомий'}
function renderCharacters(){
 const q=$('#search').value.trim().toLocaleLowerCase('uk-UA'),cl=$('#classFilter').value;
 let arr=allCharacters.filter(x=>(!q||(x.name||'').toLocaleLowerCase('uk-UA').includes(q))&&(!cl||x.class_name===cl));
 arr.sort((a,b)=>{let av=a[sortKey],bv=b[sortKey];if(sortKey==='name'||sortKey==='class_name'){av=(av||'').toLocaleLowerCase('uk-UA');bv=(bv||'').toLocaleLowerCase('uk-UA');return (av<bv?-1:av>bv?1:0)*(sortDescending?-1:1)}av=Number(av??-Infinity);bv=Number(bv??-Infinity);return (av-bv)*(sortDescending?-1:1)});
 $('#count').textContent=`Всього ${allCharacters.length}`;
 $('#characters').innerHTML=arr.map(x=>`<tr tabindex="0" role="link" onclick="show(${x.wid})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();show(${x.wid})}"><td class="char-name">${esc(x.name)}</td><td>${esc(x.class_name||'—')}</td><td>${x.level??'—'}</td><td class="num">${fmt(x.max_hp)}</td><td class="num">${fmt(x.damage_rating)}</td><td class="num">${fmt(x.hp_rating)}</td></tr>`).join('')||'<tr><td colspan="6" class="empty">Нічого не знайдено</td></tr>';
 document.querySelectorAll('.directory th[data-sort]').forEach(th=>{const active=th.dataset.sort===sortKey;th.classList.toggle('sorted',active);th.querySelector('.sort-mark').textContent=active?(sortDescending?'▼':'▲'):''});
}
async function load(){allCharacters=await api('/api/characters');const classes=[...new Set(allCharacters.map(x=>x.class_name).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'uk'));$('#classFilter').innerHTML='<option value="">Усі класи</option>'+classes.map(c=>`<option>${esc(c)}</option>`).join('');renderCharacters()}
const S=(n,v)=>`<div class="stat"><span>${n}</span><b>${v??'—'}</b></div>`;
function slotMap(){return {2:[1,2],3:[2,2],18:[3,2],8:[1,3],5:[2,3],9:[1,4],10:[2,4],1:[6,1],4:[6,2],6:[6,3],0:[7,3],7:[6,4]}}
function itemName(i){return i.pwdb_name||itemNames[String(i.template_id)]||`ID ${i.template_id}`}
function slotHtml(i){
 const pos=slotMap()[Number(i.slot)];if(!pos)return '';
 const sockets=(i.sockets||[]).filter(v=>Number(v)>0);
 const socketHtml=sockets.map(id=>`<span class="stone" data-stone="${Number(id)}"><img src="/icon/${Number(id)}.png" alt="" onload="this.parentElement.classList.add('has-icon')" onerror="this.parentElement.classList.add('no-icon')"><i>◆</i></span>`).join('');
 return `<div class="gear-slot" style="grid-column:${pos[0]};grid-row:${pos[1]}" data-slot="${i.slot}" data-template="${i.template_id}">
 <span class="slot-no">${i.slot}</span><img class="gear-icon" src="/icon/${i.template_id}.png" alt="" onerror="this.src='/slot.svg'">
 <div class="gear-name" id="n${i.slot}">${esc(itemName(i))}</div><div class="gear-ref">${i.refine!=null?'+'+i.refine:''}</div>
 <div class="stones">${socketHtml}</div></div>`;
}
let tipTimer=0,activeStone=null;
function hideTip(){clearTimeout(tipTimer);$('#hoverTip').classList.add('hidden');activeStone=null}
async function showStoneTip(id,anchor){
 clearTimeout(tipTimer);activeStone=String(id);const tip=$('#hoverTip');
 const known=stoneNames[String(id)]||itemNames[String(id)];tip.innerHTML=`<div class="stone-tip"><img src="/icon/${id}.png" alt="" onerror="this.style.display='none'"><b>${esc(known||'Завантаження назви…')}</b></div>`;tip.classList.remove('hidden');
 const place=()=>{const r=anchor.getBoundingClientRect();tip.style.left=Math.max(10,Math.min(window.innerWidth-tip.offsetWidth-10,r.left-20))+'px';tip.style.top=Math.max(10,Math.min(window.innerHeight-tip.offsetHeight-10,r.bottom+6))+'px'};place();
 if(!known){try{const meta=await api('/api/pwdb-name/'+id);if(activeStone!==String(id))return;const name=meta.name||'Камінь';stoneNames[String(id)]=name;tip.innerHTML=`<div class="stone-tip"><img src="/icon/${id}.png" alt="" onerror="this.style.display='none'"><b>${esc(name)}</b></div>`;place()}catch{if(activeStone===String(id))tip.innerHTML='<div class="stone-tip"><b>Камінь</b></div>'}}
}
function bindStoneTips(){document.querySelectorAll('.stone').forEach(el=>{const id=el.dataset.stone;el.addEventListener('mouseenter',()=>{tipTimer=setTimeout(()=>showStoneTip(id,el),80)});el.addEventListener('mouseleave',()=>{clearTimeout(tipTimer);hideTip()})});if(!$('#hoverTip').dataset.bound){$('#hoverTip').addEventListener('mouseleave',hideTip);$('#hoverTip').dataset.bound='1'}}
async function setDefaultScan(wid,scanId){
 try{await api('/api/default-scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wid,scan_id:scanId})});
  const x=await api('/api/character/'+wid+'?scan_id='+scanId);renderProfile(x);
 }catch(e){alert('Не вдалося зберегти скан за замовчуванням: '+e.message)}
}
function renderProfile(x){
 const s=x.stats;currentWid=x.wid;$('#home').classList.add('hidden');$('#profile').classList.remove('hidden');
 window.currentGear=(x.equipment||[]).filter(i=>Object.prototype.hasOwnProperty.call(slotMap(),Number(i.slot)));const eqHtml=window.currentGear.map(slotHtml).join('');
 const hist=x.history.map(h=>{const active=Number(h.id)===Number(x.selected_scan_id),isDefault=!!h.is_default;return `<tr class="history-row ${active?'selected':''}" onclick="show(${x.wid},${h.id})"><td>${esc((h.captured_at||'').replace('T',' '))}</td><td>${statusLabel(h.status_state,h.status_count,h.full_buff)}</td><td>${fmt(h.damage_rating)}</td><td>${fmt(h.hp_rating)}</td><td>${fmt(h.max_hp)}</td><td><button type="button" class="star-btn ${isDefault?'is-default':''}" title="Зробити сканом за замовчуванням" onclick="event.stopPropagation();setDefaultScan(${x.wid},${h.id})">${isDefault?'★':'☆'}</button></td></tr>`}).join('');
 const avgMagicDefense=Math.round((Number(s.resist_metal||0)+Number(s.resist_wood||0)+Number(s.resist_water||0)+Number(s.resist_fire||0)+Number(s.resist_earth||0))/5);
 const date=(x.captured_at||'').replace('T',' ');
 $('#profileBody').innerHTML=`<div class="profileHead"><div><h1>${esc(x.name)}</h1><div class="sub profile-meta">${esc(x.class_name)} • ${s.level??'—'} рівень • ${esc(date)} <span class="meta-status ${x.full_buff?'buffed':x.status_state==='NO_REPORTED_STATUSES'?'clean':x.status_state==='WITH_BUFFS'?'buffed':'unknown'}">${statusLabel(x.status_state,x.status_count,x.full_buff)}</span></div></div></div>
 <div class="profileGrid"><div class="panel stats-panel"><h2>Характеристики</h2>
 <div class="statgrid top-vitals">${S('Макс. HP',fmt(s.max_hp))}${S('Макс. MP',fmt(s.max_mp))}</div><div class="statgrid">
 ${S('Фіз. атака',`${fmt(s.physical_attack_min)}–${fmt(s.physical_attack_max)}`)}${S('Фіз. захист',fmt(s.physical_defense))}
 ${S('Маг. атака',`${fmt(s.magic_attack_min)}–${fmt(s.magic_attack_max)}`)}${S('Маг. захист',fmt(avgMagicDefense))}
 ${S('Шанс крит. удару',`${s.critical??'—'}%`)}${S('Крит. шкода',`${s.crit_power??200}%`)}
 ${S('Атак/сек',s.attack_rate?.toFixed?.(2))}${S('Швидкість руху',s.move_speed==null?'—':Number(s.move_speed).toFixed(2)+' м/сек')}
 ${S('Точність',fmt(s.accuracy))}${S('Ухилення',fmt(s.evasion))}
 ${S('Фіз. зменшення',s.physical_reduction==null?'—':s.physical_reduction+'%')}${S('Маг. зменшення',s.magical_reduction==null?'—':s.magical_reduction+'%')}
 ${S('Показник атаки',s.attack_level)}${S('Показник захисту',s.defense_level)}
 ${S('Damage Rating',fmt(s.damage_rating))}${S('HP Rating',fmt(s.hp_rating))}</div></div>
 <div class="panel equipment-panel"><h2>Екіпіровка</h2><div class="gear-layout">${eqHtml}</div></div></div>
 <div class="panel history"><h2>Історія сканів</h2><div class="history-note">Натисни рядок, щоб переглянути скан. ★ — скан за замовчуванням.</div><div class="history-wrap"><table><thead><tr><th>Дата</th><th>Статус</th><th>Damage</th><th>HP Rating</th><th>HP</th><th></th></tr></thead><tbody>${hist}</tbody></table></div></div>`;
 bindStoneTips();window.currentGear.forEach(i=>{if(i.pwdb_name||itemNames[String(i.template_id)])return;api('/api/pwdb-name/'+i.template_id).then(m=>{const el=document.querySelector('#n'+i.slot);if(el&&m.name){el.textContent=m.name;i.pwdb_name=m.name}}).catch(()=>{})});
}
async function show(wid,scanId=null){try{const url='/api/character/'+wid+(scanId!=null?'?scan_id='+scanId:'');const x=await api(url);renderProfile(x)}catch(e){alert('Не вдалося відкрити персонажа: '+e.message)}}
$('#back').onclick=()=>{$('#profile').classList.add('hidden');$('#home').classList.remove('hidden');hideTip()};
let t;$('#search').oninput=()=>{clearTimeout(t);t=setTimeout(renderCharacters,120)};
$('#classFilter').addEventListener('change',renderCharacters);
document.querySelectorAll('.directory th[data-sort]').forEach(th=>th.addEventListener('click',()=>{const k=th.dataset.sort;if(sortKey===k)sortDescending=!sortDescending;else{sortKey=k;sortDescending=(k!=='name'&&k!=='class_name')}renderCharacters()}));
load();
