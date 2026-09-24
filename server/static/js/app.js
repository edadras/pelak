import { $, $$, ago, api, can, esc, fa, flong, get, icon, logout, modal, post, state, toast, empty, plateHtml } from './core.js';

const ROUTES = [
  { path: '', title: 'داشبورد', sub: 'نمای کلی وضعیت تردد شهر', icon: 'dashboard', mod: 'dashboard', group: 'پایش' },
  { path: 'live', title: 'پایش زنده', sub: 'تصاویر زنده دوربین‌ها با تحلیل هوشمند', icon: 'grid', mod: 'live', group: 'پایش' },
  { path: 'map', title: 'نقشه شهر', sub: 'موقعیت دوربین‌ها و محدوده‌های ترافیکی', icon: 'map', mod: 'map', group: 'پایش' },
  { path: 'events', title: 'ترددها', sub: 'جستجو در ترددهای ثبت‌شده', icon: 'car', mod: 'events', group: 'داده‌ها' },
  { path: 'violations', title: 'تخلفات', sub: 'بررسی و تایید تخلفات', icon: 'alert', mod: 'violations', group: 'داده‌ها', badge: 'pending' },
  { path: 'parking', title: 'پارک حاشیه‌ای', sub: 'خودروهای پارک‌شده و دوبل', icon: 'parking', mod: 'parking', group: 'داده‌ها' },
  { path: 'reports', title: 'گزارش‌ها', sub: 'آمار و تحلیل تردد', icon: 'chart', mod: 'reports', group: 'داده‌ها' },
  { path: 'vehicle', title: 'پرونده خودرو', sub: 'سوابق تردد یک پلاک', icon: 'plate', mod: 'vehicle', hidden: true },
  { path: 'cameras', title: 'دوربین‌ها', sub: 'تعریف و پیکربندی دوربین‌ها', icon: 'camera', mod: 'cameras', group: 'مدیریت' },
  { path: 'districts', title: 'مناطق شهر', sub: 'محدوده‌ها و مناطق', icon: 'zone', mod: 'districts', group: 'مدیریت' },
  { path: 'rules', title: 'قوانین تردد', sub: 'محدودیت‌های زمانی، مکانی و نوع خودرو', icon: 'rules', mod: 'rules', group: 'مدیریت' },
  { path: 'lists', title: 'مجوزها و فهرست‌ها', sub: 'مجوز طرح و خودروهای تحت پیگیری', icon: 'list', mod: 'lists', group: 'مدیریت' },
  { path: 'users', title: 'کاربران', sub: 'مدیریت دسترسی کاربران', icon: 'users', mod: 'users', group: 'سیستم', role: 'admin' },
  { path: 'settings', title: 'تنظیمات و وضعیت', sub: 'پیکربندی و سلامت سرویس‌ها', icon: 'settings', mod: 'settings', group: 'سیستم' },
];

let cleanup = null;
let ws = null;
let navToken = 0;

async function boot() {
  if (!state.token) return renderLogin();
  try {
    state.user = await get('/api/auth/me');
    state.meta = await get('/api/meta');
  } catch (e) { return renderLogin(); }
  renderShell();
  connectWs();
  window.addEventListener('hashchange', route);
  route();
  refreshCounters();
  setInterval(refreshCounters, 30000);
}

// ---------------------------------------------------------------- login
function renderLogin() {
  document.title = 'ورود | پایش تردد شهری';
  const feats = [['plate', 'پلاک‌خوانی خودکار ملی و مناطق آزاد'], ['car', 'تشخیص نوع، رنگ و بار خودرو'], ['speed', 'سنجش سرعت و ثبت تخلف'],
    ['parking', 'تشخیص پارک حاشیه‌ای و دوبل'], ['rules', 'قوانین زمانی و مکانی تردد'], ['camera', 'اتصال نامحدود دوربین (Axis، ONVIF و ...)']];
  $('#app').innerHTML = `<div class="login">
    <div class="hero"><img src="/static/img/logo.svg" width="64" alt="">
      <h1>سامانه هوشمند<br>پایش تردد شهری</h1>
      <p>پایش لحظه‌ای ترددها، پلاک‌خوانی، کنترل محدوده‌های ترافیکی و شناسایی تخلفات با بینایی ماشین — روی زیرساخت خودتان.</p>
      <div class="feat">${feats.map(([i, t]) => `<div>${icon(i)}<span>${t}</span></div>`).join('')}</div></div>
    <form id="lf" autocomplete="on">
      <div><h2>ورود به سامانه</h2><p class="muted" style="margin:6px 0 0">نام کاربری و رمز عبور خود را وارد کنید</p></div>
      <label class="f">نام کاربری<input class="input" name="username" autocomplete="username" required autofocus></label>
      <label class="f">رمز عبور<input class="input" name="password" type="password" autocomplete="current-password" required></label>
      <button class="btn primary" style="justify-content:center;padding:12px">ورود</button>
      <div id="lerr" class="small" style="color:var(--bad);min-height:18px"></div>
    </form></div>`;
  $('#lf').onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      const r = await post('/api/auth/login', { username: f.get('username'), password: f.get('password') });
      state.token = r.token;
      try { localStorage.setItem('token', r.token); } catch (err) {}
      location.hash = '#/';
      boot();
    } catch (err) { $('#lerr').textContent = err.message; }
  };
}

// ---------------------------------------------------------------- shell
function renderShell() {
  const groups = {};
  ROUTES.filter(r => !r.hidden && (!r.role || can(r.role))).forEach(r => (groups[r.group] ||= []).push(r));
  const initials = (state.user.full_name || state.user.username).trim()[0] || '؟';
  $('#app').innerHTML = `<div class="shell">
    <aside class="sidebar" id="sb">
      <div class="brand"><img src="/static/img/logo.svg" alt=""><div><b>پایش تردد شهری</b><span>پلاک‌خوانی و کنترل هوشمند</span></div></div>
      ${Object.entries(groups).map(([g, rs]) => `<div class="nav-group">${g}</div><nav class="nav">${rs.map(r =>
        `<a href="#/${r.path}" data-path="${r.path}">${icon(r.icon)}<span>${r.title}</span>${r.badge ? `<span class="count hidden" data-badge="${r.badge}"></span>` : ''}</a>`).join('')}</nav>`).join('')}
      <div class="side-foot">نسخه ۱٫۰ — ${esc(state.meta.app_name)}</div>
    </aside>
    <div class="main">
      <header class="topbar">
        <button class="icon-btn menu-btn" id="menu" aria-label="منو">${icon('menu')}</button>
        <div><h1 id="pt"></h1><div class="sub" id="ps"></div></div>
        <div class="spacer"></div>
        <form class="search" id="gs"><input placeholder="جستجوی پلاک… مثلا ۱۲ ب ۳۴۵" aria-label="جستجوی پلاک">${icon('search')}</form>
        <div class="clock"><b class="num" id="clk"></b><div id="dte"></div></div>
        <button class="icon-btn" id="theme" aria-label="تغییر پوسته">${icon(document.documentElement.dataset.theme === 'light' ? 'moon' : 'sun')}</button>
        <button class="icon-btn" id="bell" aria-label="هشدارها">${icon('bell')}<span class="dot hidden" id="bdot"></span></button>
        <div class="user-chip" id="uc"><div class="nm"><div style="font-weight:600;font-size:13px">${esc(state.user.full_name || state.user.username)}</div>
          <div class="small muted">${({ admin: 'مدیر سیستم', operator: 'اپراتور', viewer: 'ناظر' })[state.user.role]}</div></div><div class="avatar">${esc(initials)}</div></div>
      </header>
      <main class="content" id="page"></main>
    </div></div>`;
  $('#menu').onclick = () => $('#sb').classList.toggle('open');
  $('#gs').onsubmit = (e) => { e.preventDefault(); const v = e.target.querySelector('input').value.trim(); if (v) location.hash = '#/vehicle/' + encodeURIComponent(v); };
  $('#theme').onclick = () => {
    const t = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem('theme', t); } catch (e) {}
    $('#theme').innerHTML = icon(t === 'light' ? 'moon' : 'sun');
    route();
  };
  $('#bell').onclick = showAlerts;
  $('#uc').onclick = userMenu;
  const tick = () => {
    const now = new Date();
    $('#clk').textContent = new Intl.DateTimeFormat('fa-IR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: 'Asia/Tehran' }).format(now);
    $('#dte').textContent = flong(now);
  };
  tick(); setInterval(tick, 1000);
}

async function route() {
  const hash = location.hash.replace(/^#\/?/, '');
  const [path, ...rest] = hash.split('/');
  const r = ROUTES.find(x => x.path === path) || ROUTES[0];
  if (r.role && !can(r.role)) { location.hash = '#/'; return; }
  $$('.nav a').forEach(a => a.classList.toggle('active', a.dataset.path === r.path));
  $('#sb')?.classList.remove('open');
  $('#pt').textContent = r.title; $('#ps').textContent = r.sub;
  document.title = r.title + ' | پایش تردد شهری';
  if (cleanup) { try { cleanup(); } catch (e) {} cleanup = null; }
  const host = $('#page');
  const token = ++navToken;
  // Each render gets its own container: a slow, superseded page then writes into a detached node.
  const el = document.createElement('div');
  el.innerHTML = '<div class="loading"><span class="spinner"></span></div>';
  host.replaceChildren(el);
  try {
    const mod = await import(`./pages/${r.mod}.js`);
    const done = await mod.render(el, rest.map(decodeURIComponent)) || null;
    if (token === navToken) cleanup = done;
    else if (done) done();  // user already navigated elsewhere
  } catch (e) {
    console.error(e);
    if (token !== navToken) return;
    el.innerHTML = `<div class="card">${empty('خطا در بارگذاری صفحه: ' + esc(e.message))}</div>`;
  }
}

// ---------------------------------------------------------------- realtime
function connectWs() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(state.token)}`);
  ws.onmessage = (m) => {
    let msg; try { msg = JSON.parse(m.data); } catch (e) { return; }
    window.dispatchEvent(new CustomEvent('pelak:' + msg.type, { detail: msg.data }));
    if (msg.type === 'alert') {
      toast(msg.data.body, 'bad', msg.data.title);
      $('#bdot')?.classList.remove('hidden');
    }
    if (msg.type === 'event' && msg.data.violations?.length) {
      const v = msg.data.violations[0];
      if (v.severity === 'critical' || v.severity === 'high') toast(`${msg.data.plate_fa || 'بدون پلاک'} — ${msg.data.camera_name || ''}`, 'warn', v.title);
    }
  };
  ws.onclose = () => setTimeout(connectWs, 3000);
}

async function refreshCounters() {
  try {
    const o = await get('/api/stats/overview');
    const b = $('[data-badge="pending"]');
    if (b) { b.textContent = fa(o.violations_pending > 999 ? '999+' : o.violations_pending); b.classList.toggle('hidden', !o.violations_pending); }
    $('#bdot')?.classList.toggle('hidden', !o.open_alerts);
  } catch (e) {}
}

async function showAlerts() {
  const m = modal({ title: 'هشدارها', body: '<div class="loading"><span class="spinner"></span></div>',
    footer: can('operator') ? `<button class="btn" id="ackall">${icon('check')} علامت‌گذاری همه به‌عنوان خوانده‌شده</button>` : '' });
  const items = await get('/api/alerts');
  m.$('.modal-b').innerHTML = items.length ? `<div class="feed" style="max-height:60vh">${items.map(a => `
    <div class="feed-item" data-ev="${a.event_id || ''}" style="opacity:${a.acknowledged ? .55 : 1}">
      <span class="badge ${a.level === 'critical' ? 'bad' : a.level === 'warning' ? 'warn' : 'info'}">${a.kind === 'watchlist' ? 'تحت پیگیری' : a.kind === 'camera' ? 'دوربین' : 'تخلف'}</span>
      <div class="meta"><b>${esc(a.title)}</b><span class="small muted">${esc(a.body)}</span></div>
      <span class="small faint nowrap">${ago(a.ts)}</span></div>`).join('')}</div>` : empty('هشداری وجود ندارد');
  m.$$('[data-ev]').forEach(x => x.onclick = () => { if (x.dataset.ev) { m.close(); import('./pages/events.js').then(p => p.showEvent(+x.dataset.ev)); } });
  const ack = m.$('#ackall');
  if (ack) ack.onclick = async () => { await post('/api/alerts/ack', {}); m.close(); refreshCounters(); };
}

function userMenu() {
  const m = modal({ title: 'حساب کاربری', body: `
    <div class="kv"><dt>نام کاربری</dt><dd>${esc(state.user.username)}</dd><dt>نقش</dt><dd>${esc(state.user.role)}</dd></div>
    <h4>تغییر رمز عبور</h4>
    <div class="form-grid"><label class="f">رمز فعلی<input class="input" type="password" id="pc"></label>
    <label class="f">رمز جدید<input class="input" type="password" id="pn"></label></div>`,
    footer: `<button class="btn primary" id="chp">ذخیره رمز</button><button class="btn danger" id="lo">${icon('logout')} خروج</button>` });
  m.$('#lo').onclick = () => logout();
  m.$('#chp').onclick = async () => {
    try { await post('/api/auth/password', { current: m.$('#pc').value, new: m.$('#pn').value }); toast('رمز عبور تغییر کرد', 'ok'); m.close(); }
    catch (e) { toast(e.message, 'bad'); }
  };
}

boot();
