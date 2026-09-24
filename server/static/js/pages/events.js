import { $, can, colorBadge, debounce, download, empty, esc, fa, fdt, get, icon, kindBadge, loadedBadge, localIso, modal, num, options, parseJalali, plateHtml, sevBadge, state, duration } from '../core.js';

export function rangeFilter(prefix = '') {
  return `<label class="f">از تاریخ<input class="input" name="${prefix}start" placeholder="۱۴۰۵/۰۷/۰۱ ۰۸:۰۰" style="width:160px"></label>
    <label class="f">تا تاریخ<input class="input" name="${prefix}end" placeholder="۱۴۰۵/۰۷/۰۲" style="width:160px"></label>
    <div class="f"><span class="small muted" style="font-weight:600">بازه سریع</span><div class="seg" data-quick>
      <button type="button" data-h="1">۱ ساعت</button><button type="button" data-h="24">۲۴ ساعت</button><button type="button" data-h="168">۷ روز</button><button type="button" data-h="0" class="on">همه</button></div></div>`;
}

export function readRange(root, params) {
  const q = root.querySelector('[data-quick] .on');
  const h = q ? +q.dataset.h : 0;
  const s = root.querySelector('[name=start]').value.trim(), e = root.querySelector('[name=end]').value.trim();
  if (s || e) {
    const ps = parseJalali(s), pe = parseJalali(e);
    if (s && !ps) throw new Error('تاریخ شروع نامعتبر است (نمونه: ۱۴۰۵/۰۷/۰۱ ۰۸:۰۰)');
    if (e && !pe) throw new Error('تاریخ پایان نامعتبر است');
    if (ps) params.start = ps;
    if (pe) params.end = e.includes(':') ? pe : pe.replace('T00:00:00', 'T23:59:59');
  } else if (h) params.start = localIso(new Date(Date.now() - h * 3600e3));
  return params;
}

export function bindQuick(root, onChange) {
  root.querySelectorAll('[data-quick] button').forEach(b => b.onclick = () => {
    root.querySelectorAll('[data-quick] button').forEach(x => x.classList.toggle('on', x === b));
    root.querySelector('[name=start]').value = ''; root.querySelector('[name=end]').value = '';
    onChange();
  });
}

export function pager(total, page, size, onPage) {
  const pages = Math.max(1, Math.ceil(total / size));
  const div = document.createElement('div');
  div.className = 'pager';
  div.innerHTML = `<span>${num(total)} مورد · صفحه ${fa(page)} از ${fa(pages)}</span><div style="display:flex;gap:6px">
    <button class="btn sm" data-p="${page - 1}" ${page <= 1 ? 'disabled' : ''}>قبلی</button><button class="btn sm" data-p="${page + 1}" ${page >= pages ? 'disabled' : ''}>بعدی</button></div>`;
  div.querySelectorAll('[data-p]').forEach(b => b.onclick = () => onPage(+b.dataset.p));
  return div;
}

export async function render(el) {
  const cams = await get('/api/cameras');
  const dists = await get('/api/districts');
  const m = state.meta;
  el.innerHTML = `<div class="card"><form class="filters" id="flt">
      <label class="f">پلاک<input class="input" name="plate" placeholder="بخشی از پلاک" style="width:170px"></label>
      <label class="f">دوربین<select class="input" name="camera_id">${options(Object.fromEntries(cams.map(c => [c.id, c.name])), '', 'همه')}</select></label>
      <label class="f">منطقه<select class="input" name="district_id">${options(Object.fromEntries(dists.map(d => [d.id, d.name])), '', 'همه')}</select></label>
      <label class="f">نوع خودرو<select class="input" name="vehicle_type">${options(m.vehicle_types, '', 'همه')}</select></label>
      <label class="f">رنگ<select class="input" name="color">${options(Object.fromEntries(Object.entries(m.colors).map(([k, v]) => [k, v.label])), '', 'همه')}</select></label>
      <label class="f">رویداد<select class="input" name="kind">${options(m.event_kinds, '', 'همه')}</select></label>
      <label class="f">بار<select class="input" name="loaded">${options({ loaded: 'باردار', empty: 'بدون بار' }, '', 'همه')}</select></label>
      <label class="f">حداقل سرعت<input class="input" name="min_speed" type="number" style="width:100px"></label>
      ${rangeFilter()}
      <label class="check"><input type="checkbox" name="heavy"> فقط سنگین</label>
      <label class="check"><input type="checkbox" name="has_plate"> دارای پلاک</label>
      <div style="display:flex;gap:8px;margin-right:auto"><button class="btn primary">${icon('search')} جستجو</button>
      ${can('operator') ? `<button type="button" class="btn" id="csv">${icon('download')} خروجی اکسل</button>` : ''}</div>
    </form></div>
    <div class="card flush" style="margin-top:16px"><div id="tbl">${'<div class="loading"><span class="spinner"></span></div>'}</div></div>`;

  let page = 1;
  const form = $('#flt', el);
  const params = () => {
    const f = new FormData(form);
    const p = {};
    for (const [k, v] of f.entries()) if (v && !['start', 'end'].includes(k)) p[k] = k === 'heavy' || k === 'has_plate' ? '1' : v;
    return readRange(form, p);
  };
  async function load() {
    let p;
    try { p = params(); } catch (e) { return import('../core.js').then(c => c.toast(e.message, 'bad')); }
    const qs = new URLSearchParams({ ...p, page, size: 30 });
    const r = await get('/api/events?' + qs);
    const box = $('#tbl', el);
    if (!r.items.length) { box.innerHTML = empty('ترددی با این مشخصات یافت نشد'); return; }
    box.innerHTML = `<div class="table-wrap"><table class="t"><thead><tr><th>تصویر</th><th>پلاک</th><th>زمان</th><th>دوربین</th><th>رویداد</th><th>خودرو</th><th>رنگ</th><th>سرعت</th></tr></thead><tbody>
      ${r.items.map(e => `<tr class="click" data-id="${e.id}">
        <td>${e.vehicle_image ? `<img class="thumb" src="/media/${e.vehicle_image}" loading="lazy" alt="">` : '<div class="thumb"></div>'}</td>
        <td>${plateHtml(e.plate)}</td><td class="num nowrap">${fdt(e.ts)}</td><td>${esc(e.camera_name || '—')}</td><td>${kindBadge(e.kind, e.kind_label)}</td>
        <td>${esc(e.vehicle_type_label)} ${e.is_heavy ? '<span class="badge warn">سنگین</span>' : ''} ${loadedBadge(e.loaded)}</td>
        <td>${colorBadge(e.color, e.color_label, e.color_hex)}</td><td class="num">${e.speed_kmh ? num(e.speed_kmh) + ' km/h' : '—'}</td></tr>`).join('')}</tbody></table></div>`;
    box.appendChild(pager(r.total, r.page, r.size, (p2) => { page = p2; load(); }));
    box.querySelectorAll('tr[data-id]').forEach(tr => tr.onclick = () => showEvent(+tr.dataset.id));
  }
  form.onsubmit = (e) => { e.preventDefault(); page = 1; load(); };
  bindQuick(form, () => { page = 1; load(); });
  const csv = $('#csv', el);
  if (csv) csv.onclick = () => { try { download('/api/events/export?' + new URLSearchParams(params()), 'events.csv'); } catch (e) {} };
  const onEvent = debounce(() => { if (page === 1 && !form.plate.value) load(); }, 2000);
  window.addEventListener('pelak:event', onEvent);
  await load();
  return () => window.removeEventListener('pelak:event', onEvent);
}

export async function showEvent(id) {
  const m = modal({ title: 'جزئیات تردد', body: '<div class="loading"><span class="spinner"></span></div>', wide: true });
  const e = await get('/api/events/' + id);
  const attr = e.attrs || {};
  m.$('.modal-b').innerHTML = `<div class="gallery">
    <div>${e.image ? `<img src="/media/${e.image}" alt="تصویر کامل">` : empty('تصویری ذخیره نشده')}</div>
    <div class="side">
      <div style="text-align:center;padding:10px 0">${plateHtml(e.plate, 'lg')}
        ${e.plate ? `<div class="small muted" style="margin-top:8px">${esc(e.plate_category_label)} · اطمینان ${num((e.plate_conf || 0) * 100)}٪</div>` : ''}</div>
      ${e.plate_image ? `<img src="/media/${e.plate_image}" alt="پلاک" style="max-height:90px;object-fit:contain">` : ''}
      ${e.vehicle_image ? `<img src="/media/${e.vehicle_image}" alt="خودرو" style="max-height:220px;object-fit:contain">` : ''}
    </div></div>
    <div class="grid g2" style="margin-top:16px">
      <dl class="kv">
        <dt>زمان</dt><dd class="num">${fdt(e.ts)}</dd><dt>دوربین</dt><dd>${esc(e.camera_name || '—')}</dd>
        <dt>رویداد</dt><dd>${kindBadge(e.kind, e.kind_label)}</dd><dt>نوع خودرو</dt><dd>${esc(e.vehicle_type_label)} ${e.is_heavy ? '<span class="badge warn">سنگین</span>' : ''}</dd>
        <dt>وضعیت بار</dt><dd>${loadedBadge(e.loaded) || '<span class="muted">نامشخص / غیرباری</span>'}</dd>
        <dt>رنگ</dt><dd>${colorBadge(e.color, e.color_label, e.color_hex)}</dd>
      </dl>
      <dl class="kv">
        <dt>سرعت</dt><dd class="num">${e.speed_kmh ? num(e.speed_kmh) + ' کیلومتر بر ساعت' : 'اندازه‌گیری نشده'}</dd>
        <dt>مدت حضور/توقف</dt><dd>${duration(e.dwell_seconds)}</dd><dt>ناحیه</dt><dd>${esc(e.zone || '—')}</dd>
        <dt>اطمینان تشخیص</dt><dd class="num">${num((e.confidence || 0) * 100)}٪</dd><dt>شناسه ردیابی</dt><dd class="num">${fa(attr.track_id || '—')}</dd>
      </dl></div>
    ${e.violations?.length ? `<h4>تخلفات این تردد</h4><div class="table-wrap"><table class="t"><tbody>${e.violations.map(v => `<tr><td>${esc(v.title)}</td><td>${sevBadge(v.severity, v.severity_label)}</td><td>${esc(v.status_label)}</td></tr>`).join('')}</tbody></table></div>` : ''}
    ${e.plate ? `<div style="margin-top:14px"><a class="btn" href="#/vehicle/${encodeURIComponent(e.plate)}">${icon('plate')} پرونده کامل این خودرو</a></div>` : ''}`;
  m.$$('a[href^="#/vehicle"]').forEach(a => a.addEventListener('click', () => m.close()));
}
