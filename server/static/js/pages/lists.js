import { $, api, bindChips, can, chipSelect, chipValues, confirmBox, del, empty, esc, fa, fdate, formData, get, icon, localIso, modal, options, parseJalali, plateHtml, post, put, toast } from '../core.js';
import { PERMITS } from './rules.js';

const REASONS = { stolen: 'سرقتی', wanted: 'تحت تعقیب قضایی', suspicious: 'مشکوک', unpaid: 'بدهی / توقیف', vip: 'ویژه', other: 'سایر' };
let tab = 'permits';

export async function render(el) {
  el.innerHTML = `<div class="tabs"><button data-t="permits" class="${tab === 'permits' ? 'on' : ''}">مجوزهای تردد</button><button data-t="watch" class="${tab === 'watch' ? 'on' : ''}">خودروهای تحت پیگیری</button></div><div id="body"></div>`;
  el.querySelectorAll('.tabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; render(el); });
  return tab === 'permits' ? permits($('#body', el)) : watch($('#body', el));
}

async function permits(el) {
  const [list, dists] = await Promise.all([get('/api/permits'), get('/api/districts')]);
  const dn = Object.fromEntries(dists.map(d => [d.id, d.name]));
  const now = new Date();
  el.innerHTML = `<div class="section-title"><div class="small muted">خودروهای دارای مجوز از قوانین مرتبط (طرح ترافیک، زوج و فرد، تردد سنگین) معاف می‌شوند.</div>
    <div class="actions">${can('operator') ? `<label class="btn">${icon('upload')} ورود از CSV<input type="file" id="imp" accept=".csv" hidden></label><button class="btn primary" id="add">${icon('plus')} مجوز جدید</button>` : ''}</div></div>
    <div class="card flush">${list.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>پلاک</th><th>نوع مجوز</th><th>محدوده</th><th>اعتبار</th><th>مالک</th><th></th></tr></thead><tbody>
    ${list.map(p => { const expired = p.valid_to && new Date(p.valid_to) < now; return `<tr data-id="${p.id}"><td>${plateHtml(p.plate)}</td><td>${esc(PERMITS[p.permit_type] || p.permit_type)}</td>
      <td>${p.district_ids?.length ? p.district_ids.map(i => esc(dn[i] || '?')).join('، ') : 'همه'}</td>
      <td class="num small">${p.valid_from ? fdate(p.valid_from) : '—'} تا ${p.valid_to ? fdate(p.valid_to) : 'نامحدود'} ${expired ? '<span class="badge bad">منقضی</span>' : '<span class="badge ok">معتبر</span>'}</td>
      <td>${esc(p.owner)}</td><td class="nowrap">${can('operator') ? `<button class="btn sm" data-edit>${icon('edit')}</button> <button class="btn sm danger" data-del>${icon('trash')}</button>` : ''}</td></tr>`; }).join('')}</tbody></table></div>` : empty('مجوزی ثبت نشده')}</div>
    <p class="small muted">قالب CSV: <span class="ltr">plate,permit_type,valid_from,valid_to,owner</span> — پلاک مانند «۱۲ ب ۳۴۵ ۶۷» یا «12B34567»، تاریخ میلادی ISO.</p>`;
  const reload = () => permits(el);
  $('#add', el)?.addEventListener('click', () => editPermit({ permit_type: 'traffic_plan', district_ids: [] }, dists, reload));
  el.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => editPermit(list.find(p => p.id === +b.closest('tr').dataset.id), dists, reload));
  el.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => { if (await confirmBox('مجوز حذف شود؟')) { await del('/api/permits/' + b.closest('tr').dataset.id); reload(); } });
  const imp = $('#imp', el);
  if (imp) imp.onchange = async () => {
    const fd = new FormData(); fd.append('file', imp.files[0]);
    try { const r = await api('/api/permits/import', { method: 'POST', body: fd }); toast(`${fa(r.added)} مجوز اضافه شد${r.errors.length ? ' — ' + r.errors.slice(0, 3).join('؛ ') : ''}`, r.errors.length ? 'warn' : 'ok'); reload(); }
    catch (e) { toast(e.message, 'bad'); }
  };
}

const toJ = (iso) => iso ? fdate(iso).replace(/[\u200e\u200f]/g, '') : '';
function editPermit(p, dists, done) {
  const m = modal({ title: p.id ? 'ویرایش مجوز' : 'مجوز جدید', body: `<div class="form-grid" id="f">
    <label class="f">پلاک<input class="input" name="plate" value="${esc(p.plate_fa || '')}" placeholder="۱۲ ب ۳۴۵ ۶۷"></label>
    <label class="f">نوع مجوز<select class="input" name="permit_type">${options(PERMITS, p.permit_type)}</select></label>
    <label class="f">از تاریخ (شمسی)<input class="input" name="vf" value="${toJ(p.valid_from)}" placeholder="۱۴۰۵/۰۱/۰۱"></label>
    <label class="f">تا تاریخ (شمسی)<input class="input" name="vt" value="${toJ(p.valid_to)}" placeholder="۱۴۰۵/۱۲/۲۹"></label>
    <label class="f full">مالک / توضیح<input class="input" name="owner" value="${esc(p.owner || '')}"></label>
    <div class="f full">محدوده‌های معتبر (خالی = همه)${chipSelect('district_ids', Object.fromEntries(dists.map(d => [d.id, d.name])), p.district_ids || [], true)}</div></div>`,
    footer: `<button class="btn primary" id="sv">ذخیره</button><button class="btn" data-close>انصراف</button>` });
  bindChips(m.el);
  m.$('#sv').onclick = async () => {
    const f = formData(m.$('#f'));
    const vf = f.vf ? parseJalali(f.vf) : null, vt = f.vt ? parseJalali(f.vt) : null;
    if ((f.vf && !vf) || (f.vt && !vt)) return toast('تاریخ را به شکل ۱۴۰۵/۰۱/۰۱ وارد کنید', 'bad');
    const data = { plate: f.plate, permit_type: f.permit_type, owner: f.owner, valid_from: vf, valid_to: vt ? vt.replace('T00:00:00', 'T23:59:59') : null, district_ids: chipValues(m.el, 'district_ids') };
    try { p.id ? await put('/api/permits/' + p.id, data) : await post('/api/permits', data); toast('ذخیره شد', 'ok'); m.close(); done(); }
    catch (e) { toast(e.message, 'bad'); }
  };
}

async function watch(el) {
  const list = await get('/api/watchlist');
  el.innerHTML = `<div class="section-title"><div class="small muted">با مشاهده این پلاک‌ها در هر دوربین، هشدار فوری برای همه اپراتورها ارسال می‌شود.</div>
    <div class="actions">${can('operator') ? `<button class="btn primary" id="add">${icon('plus')} افزودن پلاک</button>` : ''}</div></div>
    <div class="card flush">${list.length ? `<table class="t"><thead><tr><th>پلاک</th><th>علت</th><th>اولویت</th><th>توضیح</th><th>وضعیت</th><th></th></tr></thead><tbody>${list.map(w => `<tr data-id="${w.id}">
      <td>${plateHtml(w.plate)}</td><td>${esc(REASONS[w.reason] || w.reason)}</td><td>${w.priority === 'high' ? '<span class="badge bad">فوری</span>' : '<span class="badge">عادی</span>'}</td>
      <td>${esc(w.note)}</td><td>${w.active ? '<span class="badge ok">فعال</span>' : '<span class="badge">غیرفعال</span>'}</td>
      <td class="nowrap"><a class="btn sm" href="#/vehicle/${encodeURIComponent(w.plate)}">${icon('eye')}</a> ${can('operator') ? `<button class="btn sm" data-edit>${icon('edit')}</button> <button class="btn sm danger" data-del>${icon('trash')}</button>` : ''}</td></tr>`).join('')}</tbody></table>` : empty('پلاکی در فهرست نیست')}</div>`;
  const reload = () => watch(el);
  const edit = (w) => {
    const m = modal({ title: w.id ? 'ویرایش' : 'افزودن به فهرست پیگیری', body: `<div class="form-grid" id="f">
      <label class="f">پلاک<input class="input" name="plate" value="${esc(w.plate_fa || '')}" placeholder="۱۲ ب ۳۴۵ ۶۷"></label>
      <label class="f">علت<select class="input" name="reason">${options(REASONS, w.reason)}</select></label>
      <label class="f">اولویت<select class="input" name="priority">${options({ high: 'فوری', normal: 'عادی' }, w.priority)}</select></label>
      <label class="check"><input type="checkbox" name="active" ${w.active !== false ? 'checked' : ''}> فعال</label>
      <label class="f full">توضیح<textarea class="input" name="note">${esc(w.note || '')}</textarea></label></div>`,
      footer: `<button class="btn primary" id="sv">ذخیره</button><button class="btn" data-close>انصراف</button>` });
    m.$('#sv').onclick = async () => {
      const data = formData(m.$('#f'));
      try { w.id ? await put('/api/watchlist/' + w.id, data) : await post('/api/watchlist', data); toast('ذخیره شد', 'ok'); m.close(); reload(); }
      catch (e) { toast(e.message, 'bad'); }
    };
  };
  $('#add', el)?.addEventListener('click', () => edit({ reason: 'wanted', priority: 'high', active: true }));
  el.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => edit(list.find(w => w.id === +b.closest('tr').dataset.id)));
  el.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => { if (await confirmBox('از فهرست حذف شود؟')) { await del('/api/watchlist/' + b.closest('tr').dataset.id); reload(); } });
}
