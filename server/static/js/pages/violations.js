import { $, can, download, empty, esc, fdt, get, icon, modal, num, options, plateHtml, put, sevBadge, state, toast } from '../core.js';
import { bindQuick, pager, rangeFilter, readRange } from './events.js';

export async function render(el) {
  const cams = await get('/api/cameras');
  const m = state.meta;
  el.innerHTML = `<div class="card"><form class="filters" id="flt">
    <label class="f">پلاک<input class="input" name="plate" style="width:160px"></label>
    <label class="f">نوع تخلف<select class="input" name="type">${options(m.violation_types, '', 'همه')}</select></label>
    <label class="f">وضعیت<select class="input" name="status">${options({ pending: 'در انتظار بررسی', confirmed: 'تایید شده', rejected: 'رد شده' }, '', 'همه')}</select></label>
    <label class="f">شدت<select class="input" name="severity">${options({ critical: 'بحرانی', high: 'زیاد', medium: 'متوسط', low: 'کم' }, '', 'همه')}</select></label>
    <label class="f">دوربین<select class="input" name="camera_id">${options(Object.fromEntries(cams.map(c => [c.id, c.name])), '', 'همه')}</select></label>
    ${rangeFilter()}
    <div style="display:flex;gap:8px;margin-right:auto"><button class="btn primary">${icon('search')} جستجو</button>
    ${can('operator') ? `<button type="button" class="btn" id="csv">${icon('download')} خروجی</button>` : ''}</div></form></div>
    <div class="card flush" style="margin-top:16px"><div id="tbl"></div></div>`;
  let page = 1;
  const form = $('#flt', el);
  const params = () => { const p = {}; for (const [k, v] of new FormData(form).entries()) if (v && !['start', 'end'].includes(k)) p[k] = v; return readRange(form, p); };
  async function load() {
    let p; try { p = params(); } catch (e) { return toast(e.message, 'bad'); }
    const r = await get('/api/violations?' + new URLSearchParams({ ...p, page, size: 30 }));
    const box = $('#tbl', el);
    if (!r.items.length) { box.innerHTML = empty('تخلفی یافت نشد'); return; }
    box.innerHTML = `<div class="table-wrap"><table class="t"><thead><tr><th>تصویر</th><th>پلاک</th><th>تخلف</th><th>زمان</th><th>دوربین</th><th>شدت</th><th>وضعیت</th><th></th></tr></thead><tbody>
      ${r.items.map(v => `<tr data-id="${v.id}"><td>${v.vehicle_image ? `<img class="thumb" src="/media/${v.vehicle_image}" loading="lazy" alt="">` : '<div class="thumb"></div>'}</td>
        <td>${plateHtml(v.plate)}</td><td><b>${esc(v.type_label)}</b><div class="small muted">${esc(v.title)}</div></td><td class="num nowrap">${fdt(v.ts)}</td>
        <td>${esc(v.camera_name || '—')}</td><td>${sevBadge(v.severity, v.severity_label)}</td>
        <td><span class="badge ${v.status === 'confirmed' ? 'ok' : v.status === 'rejected' ? '' : 'warn'}">${esc(v.status_label)}</span></td>
        <td class="nowrap"><button class="btn sm" data-open>${icon('eye')} بررسی</button></td></tr>`).join('')}</tbody></table></div>`;
    box.appendChild(pager(r.total, r.page, r.size, (p2) => { page = p2; load(); }));
    box.querySelectorAll('[data-open]').forEach(b => b.onclick = () => review(r.items.find(x => x.id === +b.closest('tr').dataset.id), load));
  }
  form.onsubmit = (e) => { e.preventDefault(); page = 1; load(); };
  bindQuick(form, () => { page = 1; load(); });
  const csv = $('#csv', el);
  if (csv) csv.onclick = () => download('/api/violations/export?' + new URLSearchParams(params()), 'violations.csv');
  await load();
}

function review(v, reload) {
  const editable = can('operator');
  const m = modal({ title: 'بررسی تخلف', wide: true, body: `<div class="gallery">
      <div>${v.image ? `<img src="/media/${v.image}" alt="">` : empty('بدون تصویر')}</div>
      <div class="side"><div style="text-align:center">${plateHtml(v.plate, 'lg')}</div>
        ${v.plate_image ? `<img src="/media/${v.plate_image}" style="max-height:90px;object-fit:contain" alt="">` : ''}
        ${v.vehicle_image ? `<img src="/media/${v.vehicle_image}" style="max-height:200px;object-fit:contain" alt="">` : ''}</div></div>
    <dl class="kv" style="margin-top:16px"><dt>نوع تخلف</dt><dd>${esc(v.type_label)}</dd><dt>شرح</dt><dd>${esc(v.title)}</dd>
      <dt>زمان</dt><dd class="num">${fdt(v.ts)}</dd><dt>دوربین</dt><dd>${esc(v.camera_name || '—')}</dd><dt>شدت</dt><dd>${sevBadge(v.severity, v.severity_label)}</dd>
      <dt>وضعیت</dt><dd>${esc(v.status_label)}${v.reviewed_by ? ` <span class="muted small">(${esc(v.reviewed_by)})</span>` : ''}</dd></dl>
    ${editable ? `<div class="form-grid" style="margin-top:16px"><label class="f">اصلاح پلاک (در صورت خطای پلاک‌خوان)<input class="input" id="pl" placeholder="۱۲ ب ۳۴۵ ۶۷"></label>
      <label class="f">یادداشت<input class="input" id="nt" value="${esc(v.note || '')}"></label></div>` : ''}`,
    footer: editable ? `<button class="btn ok" data-s="confirmed">${icon('check')} تایید تخلف</button><button class="btn danger" data-s="rejected">${icon('x')} رد تخلف</button><button class="btn" data-s="">ذخیره یادداشت</button>` : '' });
  m.$$('[data-s]').forEach(b => b.onclick = async () => {
    try {
      await put('/api/violations/' + v.id, { status: b.dataset.s || undefined, note: m.$('#nt').value, plate: m.$('#pl').value || undefined });
      toast('ثبت شد', 'ok'); m.close(); reload();
    } catch (e) { toast(e.message, 'bad'); }
  });
}
