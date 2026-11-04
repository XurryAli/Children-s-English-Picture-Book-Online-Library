function decryptBooks(src, key){
              const bin = atob(src);
              const u8 = new Uint8Array(bin.length);
              for(let n=0;n<bin.length;n++) u8[n] = bin.charCodeAt(n);
              const kb = new TextEncoder().encode(key);
              const S = new Uint8Array(256);
              for(let n=0;n<256;n++) S[n] = n;
              let j = 0;
              for(let n=0;n<256;n++){ j=(j+S[n]+kb[n%kb.length])&255; const t=S[n]; S[n]=S[j]; S[j]=t; }
              const out = new Uint8Array(u8.length);
              let a = 0; j = 0;
              for(let n=0;n<u8.length;n++){ a=(a+1)&255; j=(j+S[a])&255; const t=S[a]; S[a]=S[j]; S[j]=t; out[n]=u8[n]^S[(S[a]+S[j])&255]; }
              return new TextDecoder('utf-8').decode(out);
            }
            const BOOKS = BOOKS_DATA.cipher
              ? JSON.parse(decryptBooks(BOOKS_DATA.cipher, BOOKS_DATA.key))
              : BOOKS_DATA.books;
            // 每本书的 i 与其数组下标一致（新增条目按 lv 插入后会整体重排编号），页面统一按 i 查书
            const BOOK_BY_ID = new Map(BOOKS.map(b => [b.i, b]));
    const LEVELS = [
  {key:'桥梁书', en:'1. Bridging Books', color:'#2f8f83', soft:'#e6f3f1'},
  {key:'初章书', en:'2. Early Chapter Books', color:'#3a78c2', soft:'#e9f1fb'},
  {key:'中章书', en:'3. Intermediate Chapter Books', color:'#6a5cad', soft:'#efecf7'},
  {key:'高章书', en:'4. Advanced Chapter Books', color:'#a8504a', soft:'#f8eceb'},
];
const LMAP = Object.fromEntries(LEVELS.map(l=>[l.key,l]));
const LX_BANDS = [
  {key:'0-199',   label:'0–199L',    test:m=>m!=null&&m<200},
  {key:'200-399', label:'200–399L',  test:m=>m!=null&&m>=200&&m<400},
  {key:'400-599', label:'400–599L',  test:m=>m!=null&&m>=400&&m<600},
  {key:'600-799', label:'600–799L',  test:m=>m!=null&&m>=600&&m<800},
  {key:'800+',    label:'800L 以上', test:m=>m!=null&&m>=800},
  {key:'none',    label:'未收录',    test:m=>m==null},
];

function lxmOf(b){return b.lxm==null?null:(+b.lxm);}

function renderLxSelect(){
  const opts=[{key:'全部',label:'全部蓝思'},...LX_BANDS];
  const sel=$('#lx');
  sel.innerHTML=opts.map(o=>{
    const n=BOOKS.filter(b=>o.key==='全部'?true:o.test(lxmOf(b))).length;
    return `<option value="${esc(o.key)}">${esc(o.label)} · ${n}</option>`;
  }).join('');
  sel.value=state.lxb;
  sel.classList.toggle('active',state.lxb!=='全部');
}
const state = {level:'全部', query:'', lxb:'全部', src:'全部'};
const $ = s => document.querySelector(s);
const grid = $('#grid'), overlay = $('#overlay'), modal = $('#modal');
const esc = s => String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// 有效源判据：数据条目的 u 字段包含 https://pan
const isPan = b => String(b.u||'').includes('https://pan');

// 分级占位封面（按页面注释中的 SVG 矢量图设计）：分级渐变色底 + 书脊暗条 + 封面压条 + 首字 + 中文名 + 英文名 + 分级英文
function coverSVG(b, L, prefix){
  const main = b.zh || b.en || b.t || '书';
  const initial = (String(main).trim()[0]||'书').toUpperCase();
  const gid = prefix + b.i;
  return `<svg aria-label="占位封面" height="100%" preserveAspectRatio="xMidYMid slice" role="img" viewBox="0 0 150 200" width="100%">
    <defs><linearGradient id="${gid}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="${L.color}"/><stop offset="1" stop-color="${L.color}cc"/>
    </linearGradient></defs>
    <rect width="150" height="200" fill="url(#${gid})"/>
    <rect x="0" y="0" width="12" height="200" fill="#000" opacity=".14"/>
    <rect x="16" y="22" width="26" height="2" rx="1" fill="#fff" opacity=".55"/>
    <text x="16" y="104" font-family="Georgia,serif" font-size="46" font-weight="700" fill="#fff" opacity=".92">${esc(initial)}</text>
    ${b.zh||b.en?`<text x="16" y="150" font-size="13" font-weight="600" fill="#fff" opacity=".95">${esc(String(b.zh||b.en).slice(0,13))}</text>`:''}
    ${b.zh&&b.en?`<text x="16" y="170" font-family="Georgia,serif" font-size="9.5" fill="#fff" opacity=".7">${esc(String(b.en).slice(0,26))}</text>`:''}
    <text x="16" y="190" font-size="9" fill="#fff" opacity=".6">${esc(L.en)}</text>
  </svg>`;
}

// 列表卡片模板：DOM 结构与样式与原有写死卡片一致，内容全部来自数据；c 为空时使用占位封面
function cardHTML(b){
  const L = LMAP[b.lv] || {key:b.lv, en:b.lv, color:'#2f8f83'};
  const name = b.zh || b.en || b.t || '';
  const m = lxmOf(b);
  const cover = b.c
    ? `<img alt="${esc(name)}" loading="lazy" src="${esc(b.c)}">`
    : coverSVG(b, L, 'pg');
  return `<article aria-label="${esc(name)}" class="book-card" data-id="${b.i}" role="button" tabindex="0">
                    <div class="book-wrap">
                        <div class="book">
                            ${cover}
                            <div class="spine" style="background:${L.color}"></div>
                        </div>
                        <div class="shelf-base">
                            <div class="ledge"></div>
                            <div class="shadow"></div>
                        </div>
                    </div>
                    <div class="card-meta">
                        <div class="card-title">${esc(b.zh || b.en || b.t || '')}</div>
                        ${b.zh?`<div class="card-sub">${esc(b.en||'')}</div>`:''}
                        <div class="card-lx">
                            <span class="lx-chip${m==null?' none':''}">蓝思 ${m==null?'未收录':esc(b.lx)}</span>
                        </div>
                        <div class="chips">
                            <span class="chip level-dot">
                                <span class="dot" style="background:${L.color}"></span>
                                ${esc(b.lv)}
                            </span>
                            <span class="chip">${esc(b.n || '册数见目录')}</span>
                        </div>
                    </div>
                </article>`;
}

// 依据数据渲染 #grid（页面不再写死卡片）
function buildGrid(){
  grid.innerHTML = BOOKS.map(cardHTML).join('\n                ');
}

function matches(b){
  if(state.level!=='全部' && b.lv!==state.level) return false;
  if(state.src==='有效源' && !isPan(b)) return false;
  if(state.lxb!=='全部'){
    const band=LX_BANDS.find(x=>x.key===state.lxb);
    if(!band || !band.test(lxmOf(b))) return false;
  }
  const q = state.query.trim().toLowerCase();
  if(!q) return true;
  const hay=[b.t,b.en,b.zh,b.f,b.lv,b.db?b.db[0]:'',b.db?b.db[1]:''].join(' ').toLowerCase();
  return hay.includes(q);
}

function renderTabs(){
  const counts = {'全部':BOOKS.length};
  LEVELS.forEach(l=>counts[l.key]=BOOKS.filter(b=>b.lv===l.key).length);
  const panCount = BOOKS.filter(isPan).length;
  const tabs = [{key:'全部',en:'All Levels',color:'#1c2530'},...LEVELS];
  $('#tabs').innerHTML = tabs.map(t=>`
    <button class="tab ${state.level===t.key?'active':''}" data-level="${esc(t.key)}">
      <span class="dot" style="background:${t.color}"></span>${t.key}
      <span class="cnt">${counts[t.key]}</span>
    </button>`).join('') + `
    <span class="tab-sep" aria-hidden="true"></span>
    <button class="tab ${state.src==='有效源'?'active':''}" data-src="有效源" aria-pressed="${state.src==='有效源'}" title="含网盘资源链接（u 字段包含 https://pan）的书目">
      <span class="dot" style="background:#0b8f5e"></span>有效源
      <span class="cnt">${panCount}</span>
    </button>`;
  document.querySelectorAll('.tab[data-level]').forEach(btn=>{
    btn.addEventListener('click',()=>{state.level=btn.dataset.level;render();});
  });
  document.querySelectorAll('.tab[data-src]').forEach(btn=>{
    btn.addEventListener('click',()=>{state.src = state.src==='有效源' ? '全部' : '有效源'; render();});
  });
}

function render(){
  renderTabs();
  renderLxSelect();
  const list = BOOKS.filter(matches);
  const titles = {'全部':'全部馆藏'};
  LEVELS.forEach(l=>titles[l.key]=l.en);
  $('#result-title').textContent = titles[state.level] + (state.src==='有效源' ? ' · 有效源' : '');
  $('#result-count').textContent = `共 ${list.length} 套`;
  const visible = new Set(list.map(b=>b.i));
  grid.querySelectorAll('.book-card').forEach(card=>{
    card.style.display = visible.has(+card.dataset.id) ? '' : 'none';
  });
  $('#empty').style.display = list.length ? 'none' : 'block';
}

function infoRow(label, value){return `<dt>${esc(label)}</dt><dd>${value||'—'}</dd>`;}

function openModal(id){
  const b = BOOK_BY_ID.get(id); if(!b) return; const L = LMAP[b.lv], db = b.db;
  const name = b.zh || b.en || b.t;
  const sub = b.zh ? b.en : b.zh;
  const cover = b.c
    ? `<img src="${esc(b.c)}" alt="${esc(name)}" style="width:100%;height:100%;object-fit:cover;display:block">`
    : coverSVG(b, L, 'mg');
  modal.innerHTML = `
  <button class="modal-close" id="modal-close" aria-label="关闭">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
  </button>
  <div class="modal-cover">
    <div class="book" style="box-shadow:var(--shadow-book-hover)">${cover}<div class="spine" style="background:${L.color}"></div></div>
  </div>
  <div class="modal-body">
    <span class="level-badge" style="background:${L.soft};color:${L.color}">
      <span class="dot" style="background:${L.color}"></span>${esc(b.lv)} · ${esc(L.en)}
    </span>
    <h3 id="modal-title">${esc(name)}</h3>
    ${b.en?`<div class="modal-en">${esc(b.en)}</div>`:''}
    <div class="info-grid">
      ${infoRow('原始目录名', esc(b.t))}
      ${infoRow('册数', b.n || '未标注，见目录内资源')}
      ${infoRow('蓝思值', lxmOf(b)!=null?esc(b.lx):'未收录（Lexile 官方库暂未收录）')}
      ${infoRow('资源格式', esc(b.f))}
      ${infoRow('收录日期', esc(b.d))}
      ${infoRow('网盘路径', `<div class="dir-path">${esc(b.dir)}</div>`)}
    </div>
    ${db?`
    <div class="db-panel">
      <h4><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 5h16v14H4z"/><path d="M4 9h16M9 5v14"/></svg>豆瓣匹配书目</h4>
      <div class="db-title">${esc(db[0])}</div>
      <div class="db-meta">${esc([db[1],db[2]].filter(Boolean).join(' · '))}</div>
    </div>`:`
    <div class="db-panel">
      <h4>封面说明</h4>
      <p class="db-note">豆瓣图书库未检索到可靠对应书目，当前为按分级生成的系统占位封面；如需核对请打开网盘目录查看原始资源。</p>
    </div>`}
    <div class="actions">
      <a class="btn btn-primary" href="${esc(b.u)}" target="_blank" rel="noopener noreferrer">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
        打开网盘目录
      </a>
      ${db&&db[3]?`<a class="btn btn-ghost" href="${esc(db[3])}" target="_blank" rel="noopener noreferrer">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M20 4L10 14"/><path d="M20 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h5"/></svg>
        查看豆瓣书目
      </a>`:`<button class="btn btn-ghost disabled" disabled>暂无豆瓣链接</button>`}
    </div>
  </div>`;
  overlay.classList.add('open');
  document.body.style.overflow = 'hidden';
  $('#modal-close').addEventListener('click', closeModal);
}

function closeModal(){overlay.classList.remove('open');document.body.style.overflow='';}
overlay.addEventListener('click',e=>{if(e.target===overlay) closeModal();});
document.addEventListener('keydown',e=>{if(e.key==='Escape') closeModal();});
grid.addEventListener('click',e=>{
  const card = e.target.closest('.book-card');
  if(card) openModal(+card.dataset.id);
});
grid.addEventListener('keydown',e=>{
  const card = e.target.closest('.book-card');
  if(card && (e.key==='Enter'||e.key===' ')){e.preventDefault();openModal(+card.dataset.id);}
});
$('#search').addEventListener('input',e=>{state.query=e.target.value;render();});
$('#lx').addEventListener('change',e=>{state.lxb=e.target.value;render();});

// 固定页头阴影 + 返回顶部按钮
const siteHead = document.querySelector('header.top');
const toTop = $('#to-top');
function onScroll(){
  const y = window.scrollY || document.documentElement.scrollTop || 0;
  siteHead.classList.toggle('scrolled', y > 4);
  toTop.classList.toggle('show', y > 360);
}
window.addEventListener('scroll', onScroll, {passive:true});
window.addEventListener('resize', onScroll);
toTop.addEventListener('click',()=>{
  const y = window.scrollY || document.documentElement.scrollTop || 0;
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  window.scrollTo({top:0, behavior: reduce ? 'auto' : 'smooth'});
  if(y > 0) setTimeout(()=>{
    if((window.scrollY || document.documentElement.scrollTop || 0) >= y) window.scrollTo(0,0);
  }, 600);
});
onScroll();

// 含网盘资源（u 字段为 https://pan.* 链接）的书籍，在卡片底部 shelf-base 上按分级颜色高亮
function applyPanHighlight(){
  const hit = new Set(BOOKS.filter(isPan).map(b=>b.i));
  grid.querySelectorAll('.book-card').forEach(card=>{
    const id = +card.dataset.id;
    if(!hit.has(id)) return;
    const b = BOOK_BY_ID.get(id), base = card.querySelector('.shelf-base');
    if(!b || !base) return;
    const color = (LMAP[b.lv] && LMAP[b.lv].color) || '#2f8f83';
    base.classList.add('pan-hl');
    base.style.setProperty('--hl', color);
    base.setAttribute('title', '含网盘资源链接');
    card.dataset.pan = '1';
  });
  return hit.size;
}

$('#stat-total').textContent = BOOKS.length;
$('#stat-match').textContent = BOOKS.filter(b=>b.c).length;
$('#stat-ph').textContent = BOOKS.filter(b=>!b.c).length;
buildGrid();
applyPanHighlight();
render();