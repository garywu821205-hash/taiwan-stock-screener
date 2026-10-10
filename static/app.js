const $ = id => document.getElementById(id);
const STOCK_STORE = 'tw-stock-demo-watchlist-v3';
const PRESET_STORE = 'tw-stock-demo-presets-v1';
const BOOL_RULES = ['maOrder','maRising','kd60','kdDay','kdMonth','macd','rsi','dmi'];
const RANGE_RULES = ['maRiseBars','kd60Lookback','kdDayLookback','kdMonthLookback','macdLookback','rsiMax','dmiLookback'];
let stocks=[], defaults=[], defaultRules={}, presets={}, selectedCategories=new Set(), data=[], screeningMode='strict', hasScanned=false;
let dataMode='local', staticPayload=null, statusInfo={};

init();
async function init(){
  let status;
  try{status=await fetchJson('/api/status')}catch{status=await fetchJson('data/status.json')}
  statusInfo=status;dataMode=status.mode||'local';
  defaults=status.defaultStocks;defaultRules=status.defaultRules;stocks=readJson(STOCK_STORE)||clone(defaults);presets=readJson(PRESET_STORE)||{};
  updateUniverse();renderPresets();applyRules(defaultRules);bindEvents();updateDataStatus();
}
async function fetchJson(url){const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw new Error(`读取失败：${response.status}`);const type=response.headers.get('content-type')||'';if(!type.includes('json'))throw new Error('返回内容不是资料文件');return response.json()}
function clone(v){return JSON.parse(JSON.stringify(v))}
function readJson(key){try{return JSON.parse(localStorage.getItem(key))}catch{return null}}
function saveStocks(){localStorage.setItem(STOCK_STORE,JSON.stringify(stocks));updateUniverse()}
function categories(){return [...new Set(stocks.map(s=>s.category))].sort((a,b)=>a.localeCompare(b,'zh-CN'))}
function updateUniverse(){
  const cats=categories();selectedCategories=new Set([...selectedCategories].filter(x=>cats.includes(x)));if(!selectedCategories.size)cats.forEach(x=>selectedCategories.add(x));
  $('categoryChips').innerHTML=cats.map(c=>`<button class="chip ${selectedCategories.has(c)?'active':''}" data-category="${escapeHtml(c)}">${escapeHtml(c)}<small>${stocks.filter(s=>s.category===c).length}</small></button>`).join('');
  document.querySelectorAll('[data-category]').forEach(b=>b.onclick=()=>{const c=b.dataset.category;selectedCategories.has(c)?selectedCategories.delete(c):selectedCategories.add(c);b.classList.toggle('active');updateCount()});
  $('listCount').textContent=`${stocks.length}档`;renderStockList();updateCount();
}
function updateCount(){const n=stocks.filter(s=>selectedCategories.has(s.category)).length;$('total').textContent=n;const radar=$('status').querySelector('.radar span');if(radar)radar.textContent=n}
function updateDataStatus(){
  const isStatic=dataMode==='static';
  $('runtimeLabel').textContent=isStatic?'免费网页':'本机运行';
  $('runtimeDetail').textContent=isStatic?'每日盘后自动更新':'可即时读取行情';
  $('sourceNote').textContent=isStatic?`目前可筛选 ${statusInfo.availableCount||stocks.length} 档；调整规则会立即重新筛选，不会重复下载行情。`:'本机扫描最多100档；免费网页版本会在盘后预先计算全市场。';
  if(statusInfo.generatedAt)$('timestamp').textContent='资料更新：'+new Date(statusInfo.generatedAt).toLocaleString('zh-CN');
}

function bindEvents(){
  RANGE_RULES.forEach(id=>$(id).oninput=()=>{updateOutput($(id));syncControlStates()});
  BOOL_RULES.forEach(id=>$(id).onchange=syncControlStates);
  document.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>setScreeningMode(button.dataset.mode));
  $('search').oninput=render;$('scan').onclick=scan;
  $('manage').onclick=()=>$('stockDialog').showModal();$('closeDialog').onclick=()=>$('stockDialog').close();
  $('addStock').onsubmit=e=>{e.preventDefault();const code=$('newCode').value.trim();if(!/^\d{4,6}$/.test(code))return toast('股票代码应为4至6位数字','warn');const item={code,name:$('newName').value.trim(),market:$('newMarket').value,category:$('newCategory').value.trim()};const i=stocks.findIndex(s=>s.code===code);i>=0?stocks.splice(i,1,item):stocks.push(item);e.target.reset();saveStocks();toast(i>=0?'已更新股票':'已加入股票')};
  $('restoreDefaults').onclick=()=>{stocks=clone(defaults);localStorage.removeItem(STOCK_STORE);updateUniverse();toast(`已恢复完整名单（${defaults.length}档）`)};
  $('presetSelect').onchange=()=>{const key=$('presetSelect').value;applyRules(key==='default'?defaultRules:presets[key]);toast(`已切换至${key==='default'?'默认规则':key}`,'info')};
  $('savePreset').onclick=()=>$('presetDialog').showModal();$('closePreset').onclick=()=>$('presetDialog').close();
  $('presetForm').onsubmit=e=>{e.preventDefault();const name=$('presetName').value.trim();if(!name)return;presets[name]=getRules();localStorage.setItem(PRESET_STORE,JSON.stringify(presets));renderPresets(name);$('presetDialog').close();e.target.reset();toast(`已保存策略：${name}`)};
  $('deletePreset').onclick=()=>{const key=$('presetSelect').value;if(key==='default')return toast('默认规则不能删除','warn');delete presets[key];localStorage.setItem(PRESET_STORE,JSON.stringify(presets));renderPresets();applyRules(defaultRules);toast('已删除策略')};
}
function setScreeningMode(mode){
  screeningMode=mode==='loose'?'loose':'strict';
  document.querySelectorAll('[data-mode]').forEach(button=>{const active=button.dataset.mode===screeningMode;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active))});
  $('modeHint').textContent=screeningMode==='strict'?'严格：只显示所有已启用条件都通过的股票':'宽松：同时显示接近符合的股票（均线通过，其他条件至少通过一半）';
  if(hasScanned)refreshResults();
  toast(`已切换为${screeningMode==='strict'?'严格':'宽松'}模式`,'info');
}
function updateOutput(input){const output=input.parentElement.querySelector('output');if(output)output.value=input.value}
function getRules(){const rules={};BOOL_RULES.forEach(id=>rules[id]=$(id).checked);RANGE_RULES.forEach(id=>rules[id]=Number($(id).value));return rules}
function applyRules(rules){BOOL_RULES.forEach(id=>$(id).checked=Boolean(rules[id]));RANGE_RULES.forEach(id=>{$(id).value=rules[id];updateOutput($(id))});syncControlStates()}
function syncControlStates(){
  const links=[['maRising','maRiseBars'],['kd60','kd60Lookback'],['kdDay','kdDayLookback'],['kdMonth','kdMonthLookback'],['macd','macdLookback'],['rsi','rsiMax'],['dmi','dmiLookback']];
  links.forEach(([check,range])=>$(range).disabled=!$(check).checked);
  document.querySelectorAll('.rule-card').forEach(card=>{const checks=[...card.querySelectorAll('input[type=checkbox]')];card.classList.toggle('disabled',checks.length>0&&!checks.some(x=>x.checked))});
}
function renderPresets(selected='default'){$('presetSelect').innerHTML='<option value="default">默认规则</option>'+Object.keys(presets).map(n=>`<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join('');$('presetSelect').value=selected}
function renderStockList(){if(!$('stockList'))return;$('stockList').innerHTML=stocks.map((s,i)=>`<div><span><b>${s.code} ${escapeHtml(s.name)}</b><small>${s.market} · ${escapeHtml(s.category)}</small></span><button data-remove="${i}" aria-label="删除${escapeHtml(s.name)}">删除</button></div>`).join('');document.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{stocks.splice(Number(b.dataset.remove),1);saveStocks()})}

function ageText(age,unit='日'){return age===null||age===undefined?'范围内无交叉':age===0?'最新一根交叉':`${age}${unit}前交叉`}
function pillSignal(signal,label,detail=''){if(signal.enabled===false)return '<span class="badge">— 未启用</span>';return `<span class="badge ${signal.pass?'pass':'fail'}">${signal.pass?'✓':'×'} ${label}</span>${detail?`<div class="details">${detail}</div>`:''}`}
function money(value){return value>=1e8?`${(value/1e8).toFixed(1)}亿`:`${(value/1e4).toFixed(0)}万`}
function escapeHtml(v){return String(v).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
function kdDetail(k){return ['60分','日','月'].map(label=>{const v=k[label];return v.enabled?`${label} ${v.k}/${v.d}`:`${label}关闭`}).join(' · ')}
function signalItem(label,content){return `<div class="signal-item"><div class="signal-label">${label}</div>${content}</div>`}
function modeData(){return screeningMode==='strict'?data.filter(x=>x.qualified):data}
function refreshResults(){
  const visible=modeData();
  if(visible.length){$('status').classList.add('hidden');$('tableWrap').classList.remove('hidden');$('search').disabled=false;render();return}
  $('tableWrap').classList.add('hidden');$('status').classList.remove('hidden','loading');$('search').disabled=true;
  $('status').querySelector('h3').textContent=screeningMode==='strict'?'没有完全符合的股票':'没有符合或接近符合的股票';
  $('status').querySelector('p').textContent=screeningMode==='strict'?'可切换到宽松模式查看接近符合的股票。':'可以适当关闭条件或扩大交叉时间范围后再试。';
}
function render(){
  const q=$('search').value.trim().toLowerCase();const shown=modeData().filter(x=>!q||x.code.includes(q)||x.name.toLowerCase().includes(q));
  $('rows').innerHTML=shown.map(x=>{const s=x.signals,k=s.kd.values;const risk=x.liquidityRisk?'<em class="risk">低流动性</em>':'';return `<article class="result-card">
      <div class="result-card-head">
        <div class="stock card-stock"><strong>${x.code} ${escapeHtml(x.name)}</strong><small>${x.market} · ${escapeHtml(x.category)} · ${x.date}</small>${risk}</div>
        <div class="card-status"><span class="result-tag ${x.qualified?'full':'near'}">${x.qualified?'完全符合':'接近符合'}</span></div>
        <div class="card-price"><small>收盘价</small><strong>${x.price}</strong><span class="${x.change>=0?'up':'down'}">${x.change>=0?'+':''}${x.change}%</span><span class="details">${money(x.turnover)}</span></div>
        <div class="card-score"><small>评分</small><span class="score ${x.qualified?'full':''}">${x.score}/${x.maxScore}</span><span class="details">${x.matched}/${x.enabledCount}组</span></div>
      </div>
      <div class="signal-grid">
        ${signalItem('均线',pillSignal(s.ma,'均线',`排列${s.ma.orderEnabled?(s.ma.orderPass?'✓':'×'):'关闭'} · 向上${s.ma.risingEnabled?(s.ma.risingPass?'✓':'×'):'关闭'}`))}
        ${signalItem('三周期 KD',pillSignal(s.kd,'KD',kdDetail(k)))}
        ${signalItem('MACD',pillSignal(s.macd,'MACD',`${s.macd.previous} → ${s.macd.hist} · ${ageText(s.macd.age)}`))}
        ${signalItem('RSI',pillSignal(s.rsi,`RSI ${s.rsi.value}`,s.rsi.up?'正在向上':'没有向上'))}
        ${signalItem('DMI',pillSignal(s.dmi,'DMI',`+DI ${s.dmi.plus} / −DI ${s.dmi.minus} · ${ageText(s.dmi.age)}`))}
      </div>
    </article>`}).join('')
}

async function scan(){
  const chosen=stocks.filter(s=>selectedCategories.has(s.category));if(!chosen.length)return toast('请至少选择一个产业族群','warn');const rules=getRules();if(!BOOL_RULES.some(id=>rules[id]))return toast('请至少启用一项筛选条件','warn');
  $('scan').disabled=true;$('scan').querySelector('span').textContent=dataMode==='static'?'正在筛选…':'正在读取行情…';$('status').classList.remove('hidden');$('status').classList.add('loading');$('tableWrap').classList.add('hidden');$('status').querySelector('h3').textContent='正在扫描，请稍候';$('status').querySelector('p').textContent=`正在按当前规则计算${chosen.length}档股票`;
  try{
    if(dataMode==='static'){await scanStatic(chosen,rules);return}
    const response=await fetch('/api/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stocks,categories:[...selectedCategories],rules})});const payload=await response.json();if(!response.ok)throw new Error(payload.message||'扫描失败');
    data=payload.results;hasScanned=true;$('total').textContent=payload.scanned;$('qualified').textContent=payload.qualifiedCount;$('near').textContent=payload.nearCount;$('errors').textContent=payload.errors.length;$('timestamp').textContent='更新：'+new Date(payload.generatedAt).toLocaleString('zh-CN');
    refreshResults();
    toast(payload.qualifiedCount?`发现${payload.qualifiedCount}档完全符合、${payload.nearCount}档接近符合`:`没有完全符合，找到${payload.nearCount}档接近符合`,payload.qualifiedCount?'success':'info');
  }catch(error){$('status').classList.remove('hidden','loading');$('status').querySelector('h3').textContent='暂时无法完成扫描';$('status').querySelector('p').textContent=error.message+'。请检查网络后再试。';toast(error.message,'warn')}
  finally{$('scan').disabled=false;$('scan').querySelector('span').textContent='开始扫描'}
}

async function scanStatic(chosen,rules){
  if(!staticPayload)staticPayload=await fetchJson('data/signals.json');
  const wanted=new Set(chosen.map(s=>`${s.market}:${s.code}`));
  const evaluated=staticPayload.results.filter(item=>wanted.has(`${item.market}:${item.code}`)).map(item=>evaluateFacts(item,rules));
  const qualified=evaluated.filter(x=>x.qualified).sort((a,b)=>a.triggerAge-b.triggerAge||b.turnover-a.turnover);
  const near=evaluated.filter(x=>x.near).sort((a,b)=>b.score-a.score||a.triggerAge-b.triggerAge||b.turnover-a.turnover).slice(0,5);
  data=qualified.concat(near);hasScanned=true;
  $('total').textContent=evaluated.length;$('qualified').textContent=qualified.length;$('near').textContent=near.length;$('errors').textContent=(staticPayload.errorCount||0)+(chosen.length-evaluated.length);
  $('timestamp').textContent='资料更新：'+new Date(staticPayload.generatedAt).toLocaleString('zh-CN');
  refreshResults();toast(qualified.length?`发现${qualified.length}档完全符合、${near.length}档接近符合`:`没有完全符合，找到${near.length}档接近符合`,qualified.length?'success':'info');
}

function evaluateFacts(source,rules){
  const x=clone(source),s=x.signals;
  const maEnabled=rules.maOrder||rules.maRising;
  const streaks=s.ma.riseStreaks||{};
  const risingPass=['5','10','20','60'].every(key=>(streaks[key]||0)>=rules.maRiseBars);
  s.ma.enabled=maEnabled;s.ma.orderEnabled=rules.maOrder;s.ma.risingEnabled=rules.maRising;s.ma.riseBars=rules.maRiseBars;s.ma.risingPass=risingPass;
  s.ma.pass=(!rules.maOrder||s.ma.orderPass)&&(!rules.maRising||risingPass);
  const kdRules=[['60分','kd60','kd60Lookback'],['日','kdDay','kdDayLookback'],['月','kdMonth','kdMonthLookback']];
  const kdPasses=[];
  kdRules.forEach(([label,onKey,rangeKey])=>{const v=s.kd.values[label];v.enabled=rules[onKey];v.lookback=rules[rangeKey];v.pass=v.age!==null&&v.age<rules[rangeKey]&&v.k>v.d;if(v.enabled)kdPasses.push(v.pass)});
  s.kd.enabled=kdPasses.length>0;s.kd.pass=!s.kd.enabled||kdPasses.every(Boolean);
  s.macd.enabled=rules.macd;s.macd.lookback=rules.macdLookback;s.macd.pass=s.macd.age!==null&&s.macd.age<rules.macdLookback&&s.macd.hist>0;
  s.rsi.enabled=rules.rsi;s.rsi.max=rules.rsiMax;s.rsi.pass=s.rsi.value<rules.rsiMax&&s.rsi.up;
  s.dmi.enabled=rules.dmi;s.dmi.lookback=rules.dmiLookback;s.dmi.pass=s.dmi.age!==null&&s.dmi.age<rules.dmiLookback&&s.dmi.plus>s.dmi.minus;
  const groups=[['ma',maEnabled,s.ma.pass,30],['kd',s.kd.enabled,s.kd.pass,30],['macd',rules.macd,s.macd.pass,40/3],['rsi',rules.rsi,s.rsi.pass,40/3],['dmi',rules.dmi,s.dmi.pass,40/3]];
  const enabled=groups.filter(g=>g[1]);x.matched=enabled.filter(g=>g[2]).length;x.enabledCount=enabled.length;x.qualified=enabled.length>0&&x.matched===enabled.length;
  const others=groups.slice(1).filter(g=>g[1]);x.near=!x.qualified&&(!maEnabled||s.ma.pass)&&others.length>0&&others.filter(g=>g[2]).length>=Math.ceil(others.length/2);
  x.score=Math.round(groups.filter(g=>g[1]&&g[2]).reduce((sum,g)=>sum+g[3],0)*10)/10;x.maxScore=Math.round(enabled.reduce((sum,g)=>sum+g[3],0)*10)/10;
  const ages=[];kdRules.forEach(([label,onKey])=>{const age=s.kd.values[label].age;if(rules[onKey]&&age!==null)ages.push(age)});if(rules.macd&&s.macd.age!==null)ages.push(s.macd.age);if(rules.dmi&&s.dmi.age!==null)ages.push(s.dmi.age);x.triggerAge=ages.length?Math.max(...ages):99;
  return x;
}
function toast(message,type='success'){const el=$('toast');el.textContent=message;el.className=`toast show ${type}`;clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.className='toast',4200)}
