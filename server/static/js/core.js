// Shared helpers: API client, formatting, icons, plate rendering, modal, toast.
export const state = { user: null, meta: null, token: null, cameras: [], districts: [], alerts: 0 };

try { state.token = localStorage.getItem('token'); } catch (e) { /* storage unavailable */ }

export async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (state.token) headers.Authorization = 'Bearer ' + state.token;
  let body = opts.body;
  if (body && !(body instanceof FormData) && typeof body !== 'string') { body = JSON.stringify(body); headers['Content-Type'] = 'application/json'; }
  const res = await fetch(path, { method: opts.method || (body ? 'POST' : 'GET'), headers, body, credentials: 'same-origin' });
  if (res.status === 401 && !path.includes('/auth/login')) { logout(false); throw new Error('نشست منقضی شد'); }
  const ct = res.headers.get('content-type') || '';
  const data = ct.includes('json') ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = typeof data === 'object' ? (Array.isArray(data.detail) ? data.detail.map(d => d.msg).join('، ') : data.detail) : data;
    throw new Error(msg || 'خطا در ارتباط با سرور');
  }
  return data;
}
export const get = (p) => api(p);
export const post = (p, b) => api(p, { method: 'POST', body: b || {} });
export const put = (p, b) => api(p, { method: 'PUT', body: b || {} });
export const del = (p) => api(p, { method: 'DELETE' });

export function logout(callServer = true) {
  if (callServer) fetch('/api/auth/logout', { method: 'POST' });
  state.token = null; state.user = null;
  try { localStorage.removeItem('token'); } catch (e) {}
  location.hash = '#/login';
  location.reload();
}

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const FA = '۰۱۲۳۴۵۶۷۸۹';
export const fa = (v) => String(v ?? '').replace(/[0-9]/g, d => FA[d]);
export const en = (v) => String(v ?? '').replace(/[۰-۹]/g, d => FA.indexOf(d)).replace(/[٠-٩]/g, d => '٠١٢٣٤٥٦٧٨٩'.indexOf(d));
export const num = (v, d = 0) => v == null || v === '' ? '—' : fa(Number(v).toLocaleString('en-US', { maximumFractionDigits: d }));
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const media = (p) => p ? '/media/' + p : '';
export const can = (role) => ({ viewer: 0, operator: 1, admin: 2 })[state.user?.role] >= ({ viewer: 0, operator: 1, admin: 2 })[role];

// ---------- dates (Jalali)
const dtf = new Intl.DateTimeFormat('fa-IR-u-ca-persian', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'Asia/Tehran' });
const tf = new Intl.DateTimeFormat('fa-IR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: 'Asia/Tehran' });
const longf = new Intl.DateTimeFormat('fa-IR-u-ca-persian', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Tehran' });
export const fdate = (iso) => iso ? dtf.format(new Date(iso)) : '—';
export const ftime = (iso) => iso ? tf.format(new Date(iso)) : '—';
export const fdt = (iso) => iso ? `${fdate(iso)} ${ftime(iso)}` : '—';
export const flong = (d) => longf.format(d);
export function ago(iso) {
  if (!iso) return '—';
  const s = (Date.now() - new Date(iso)) / 1000;
  if (s < 60) return 'لحظاتی پیش';
  if (s < 3600) return fa(Math.floor(s / 60)) + ' دقیقه پیش';
  if (s < 86400) return fa(Math.floor(s / 3600)) + ' ساعت پیش';
  return fa(Math.floor(s / 86400)) + ' روز پیش';
}
export function duration(sec) {
  if (sec == null) return '—';
  sec = Math.round(sec);
  if (sec < 60) return fa(sec) + ' ثانیه';
  if (sec < 3600) return fa(Math.floor(sec / 60)) + ' دقیقه' + (sec % 60 ? ' و ' + fa(sec % 60) + ' ثانیه' : '');
  return fa(Math.floor(sec / 3600)) + ' ساعت و ' + fa(Math.floor((sec % 3600) / 60)) + ' دقیقه';
}
// Jalali -> Gregorian (for date filters typed as ۱۴۰۵/۰۷/۰۱)
export function jalaliToGregorian(jy, jm, jd) {
  jy += 1595;
  let days = -355668 + 365 * jy + Math.floor(jy / 33) * 8 + Math.floor(((jy % 33) + 3) / 4) + jd + (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);
  let gy = 400 * Math.floor(days / 146097); days %= 146097;
  if (days > 36524) { gy += 100 * Math.floor(--days / 36524); days %= 36524; if (days >= 365) days++; }
  gy += 4 * Math.floor(days / 1461); days %= 1461;
  if (days > 365) { gy += Math.floor((days - 1) / 365); days = (days - 1) % 365; }
  let gd = days + 1;
  const sal = [0, 31, (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0 ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let gm = 0; for (gm = 1; gm <= 12 && gd > sal[gm]; gm++) gd -= sal[gm];
  return [gy, gm, gd];
}
/** Parse "1405/07/01 08:30" (Persian or Latin digits) -> ISO string in Tehran local time (no tz), or null. */
export function parseJalali(text) {
  const t = en(text || '').replace(/[\u200e\u200f]/g, '').trim();
  const m = t.match(/^(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?$/);
  if (!m) return null;
  const [gy, gm, gd] = jalaliToGregorian(+m[1], +m[2], +m[3]);
  const p = (n) => String(n).padStart(2, '0');
  return `${gy}-${p(gm)}-${p(gd)}T${p(m[4] || 0)}:${p(m[5] || 0)}:00`;
}
export function localIso(date) { // Date -> naive Tehran time ISO
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).formatToParts(date);
  const g = (t) => parts.find(p => p.type === t).value;
  return `${g('year')}-${g('month')}-${g('day')}T${g('hour').replace('24', '00')}:${g('minute')}:${g('second')}`;
}

// ---------- plates
const LETTERS = { A: 'الف', B: 'ب', P: 'پ', Taxi: 'ت', J: 'ج', D: 'د', Sin: 'س', Sad: 'ص', T: 'ط', PuV: 'ع', Gh: 'ق', L: 'ل', M: 'م', N: 'ن', V: 'و', H: 'ه', Y: 'ی', PwD: 'ژ' };
const PLATE_CLASS = { Taxi: 'taxi', A: 'gov', P: 'police', PuV: 'public', PwD: 'disabled' };
export function plateHtml(raw, size = '') {
  if (!raw) return `<span class="plate none">بدون پلاک</span>`;
  const m = /^(\d{2})([A-Za-z]+)(\d{3})(\d{2})$/.exec(raw);
  if (m) {
    return `<span class="plate ${PLATE_CLASS[m[2]] || ''} ${size}" title="${esc(raw)}"><span class="ir"><i></i>I.R.<br>IRAN</span>` +
      `<span class="body">${fa(m[1])}<span>${esc(LETTERS[m[2]] || m[2])}</span>${fa(m[3])}</span>` +
      `<span class="reg"><small>ایران</small>${fa(m[4])}</span></span>`;
  }
  return `<span class="plate fz ${size}"><span class="body">${fa(raw)}</span><span class="reg"><small>آزاد</small>FZ</span></span>`;
}

// ---------- labels
export const vt = (k) => state.meta?.vehicle_types?.[k] || k || '—';
export const colorBadge = (key, label, hex) => `<span class="nowrap"><span class="swatch" style="background:${hex || state.meta?.colors?.[key]?.hex || '#999'}"></span> ${esc(label || state.meta?.colors?.[key]?.label || 'نامشخص')}</span>`;
export const loadedBadge = (v) => v === 'loaded' ? '<span class="badge warn">باردار</span>' : v === 'empty' ? '<span class="badge">بدون بار</span>' : '';
export const sevBadge = (s, label) => `<span class="badge ${({ critical: 'bad', high: 'bad', medium: 'warn', low: 'info' })[s] || ''}">${esc(label || s)}</span>`;
export const statusBadge = (s) => ({
  online: '<span class="badge ok"><span class="dot-s pulse"></span> آنلاین</span>',
  offline: '<span class="badge bad"><span class="dot-s"></span> قطع</span>',
  error: '<span class="badge bad"><span class="dot-s"></span> خطا</span>',
  connecting: '<span class="badge warn"><span class="dot-s"></span> در حال اتصال</span>',
  disabled: '<span class="badge"><span class="dot-s"></span> غیرفعال</span>',
})[s] || `<span class="badge">${esc(s)}</span>`;
export const kindBadge = (k, label) => `<span class="badge ${({ passage: 'info', parking: 'ok', double_parking: 'bad', no_parking: 'bad', stopped: 'warn' })[k] || ''}">${esc(label || state.meta?.event_kinds?.[k] || k)}</span>`;

// ---------- toast & modal
export function toast(msg, type = '', title = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.innerHTML = (title ? `<b>${esc(title)}</b>` : '') + esc(msg);
  const box = $('#toasts');
  box.appendChild(el);
  while (box.children.length > 4) box.firstElementChild.remove();  // bursts of events must not flood the screen
  setTimeout(() => el.remove(), type === 'bad' ? 7000 : 4500);
}
export function modal({ title, body = '', footer = '', wide = false, onClose }) {
  const bg = document.createElement('div');
  bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true"><div class="modal-h"><h3>${title}</h3>
    <button class="btn ghost sm x" data-close aria-label="بستن">${icon('x')}</button></div>
    <div class="modal-b">${body}</div>${footer ? `<div class="modal-f">${footer}</div>` : ''}</div>`;
  const close = () => { bg.remove(); document.removeEventListener('keydown', onKey); onClose && onClose(); };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  bg.addEventListener('mousedown', (e) => { if (e.target === bg) close(); });
  bg.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', close));
  document.addEventListener('keydown', onKey);
  document.body.appendChild(bg);
  return { el: bg, close, $: (s) => bg.querySelector(s), $$: (s) => [...bg.querySelectorAll(s)] };
}
export function confirmBox(text, okLabel = 'حذف', danger = true) {
  return new Promise((resolve) => {
    const m = modal({ title: 'تایید', body: `<p style="margin:0;line-height:2">${text}</p>`,
      footer: `<button class="btn ${danger ? 'danger' : 'primary'}" data-ok>${okLabel}</button><button class="btn" data-close>انصراف</button>`,
      onClose: () => resolve(false) });
    m.$('[data-ok]').onclick = () => { resolve(true); m.el.remove(); };
  });
}
export const loading = () => `<div class="loading"><span class="spinner"></span></div>`;
export const empty = (text = 'موردی یافت نشد') => `<div class="empty">${icon('inbox')}<div>${text}</div></div>`;

export function formData(root) {
  const out = {};
  root.querySelectorAll('[name]').forEach(el => {
    const k = el.name;
    if (el.type === 'checkbox') out[k] = el.checked;
    else if (el.type === 'number') out[k] = el.value === '' ? null : Number(en(el.value));
    else out[k] = el.value;
  });
  return out;
}
export function chipSelect(name, options, selected = [], numeric = false) {
  return `<div class="chips" data-chips="${name}" data-numeric="${numeric ? 1 : 0}">` + Object.entries(options).map(([k, v]) =>
    `<span class="chip-toggle ${selected.map(String).includes(String(k)) ? 'on' : ''}" data-v="${esc(k)}">${esc(v)}</span>`).join('') + '</div>';
}
export function bindChips(root) {
  root.querySelectorAll('[data-chips] .chip-toggle').forEach(c => c.onclick = () => c.classList.toggle('on'));
}
export function chipValues(root, name) {
  const box = root.querySelector(`[data-chips="${name}"]`);
  const numeric = box.dataset.numeric === '1';
  return [...box.querySelectorAll('.chip-toggle.on')].map(c => numeric ? Number(c.dataset.v) : c.dataset.v);
}
export function options(obj, selected, placeholder) {
  return (placeholder !== undefined ? `<option value="">${esc(placeholder)}</option>` : '') +
    Object.entries(obj).map(([k, v]) => `<option value="${esc(k)}" ${String(k) === String(selected ?? '') ? 'selected' : ''}>${esc(v)}</option>`).join('');
}
export function debounce(fn, ms = 300) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
export async function download(path, filename) {
  const res = await fetch(path, { headers: { Authorization: 'Bearer ' + state.token } });
  if (!res.ok) return toast('دریافت فایل ناموفق بود', 'bad');
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
export function chartColors() {
  const cs = getComputedStyle(document.documentElement);
  return { text: cs.getPropertyValue('--muted').trim(), grid: cs.getPropertyValue('--grid').trim(), accent: cs.getPropertyValue('--accent').trim(), accent2: cs.getPropertyValue('--accent2').trim(), bad: cs.getPropertyValue('--bad').trim() };
}
export const PALETTE = ['#22d3ee', '#6366f1', '#f59e0b', '#22c55e', '#ef4444', '#a855f7', '#14b8a6', '#f97316', '#3b82f6', '#ec4899', '#84cc16', '#64748b'];

// ---------- icons (inline SVG, stroke style)
const P = {
  dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  camera: '<path d="M15 10l4.55-2.28A1 1 0 0121 8.62v6.76a1 1 0 01-1.45.9L15 14"/><rect x="3" y="6" width="12" height="12" rx="2"/>',
  map: '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2z"/><path d="M9 4v14M15 6v14"/>',
  car: '<path d="M5 17h14M5 17a2 2 0 11-4 0v-5l2-5h14l2 5v5a2 2 0 11-4 0"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/><path d="M3 12h18"/>',
  alert: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/>',
  parking: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M9 17V7h4a3 3 0 010 6H9"/>',
  rules: '<path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7l8-4z"/><path d="M9 12l2 2 4-4"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  chart: '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
  users: '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 110-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 110 4h-.09a1.65 1.65 0 00-1.51 1z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/>',
  bell: '<path d="M18 8a6 6 0 00-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>',
  moon: '<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>',
  logout: '<path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', x: '<path d="M18 6L6 18M6 6l12 12"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4 12.5-12.5z"/>',
  trash: '<path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>',
  download: '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  upload: '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
  refresh: '<path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>',
  check: '<path d="M20 6L9 17l-5-5"/>', eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
  truck: '<rect x="1" y="3" width="15" height="13"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
  speed: '<path d="M12 14l4-4"/><path d="M3.34 19a10 10 0 1117.32 0"/>',
  plate: '<rect x="2" y="7" width="20" height="10" rx="2"/><path d="M6 12h3M11 10v4M14 12h4"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/>',
  grid: '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
  server: '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
  menu: '<path d="M3 12h18M3 6h18M3 18h18"/>', pin: '<path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/>',
  zone: '<path d="M3 7l6-4 6 4 6-4v14l-6 4-6-4-6 4z"/>', layers: '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>',
  full: '<path d="M8 3H5a2 2 0 00-2 2v3M21 8V5a2 2 0 00-2-2h-3M3 16v3a2 2 0 002 2h3M16 21h3a2 2 0 002-2v-3"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>', play: '<path d="M5 3l14 9-14 9V3z"/>',
};
export const icon = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[n] || ''}</svg>`;
