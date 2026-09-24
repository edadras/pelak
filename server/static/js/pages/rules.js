import { $, bindChips, can, chipSelect, chipValues, confirmBox, del, empty, esc, fa, formData, get, icon, modal, options, post, put, sevBadge, state, toast } from '../core.js';

const KINDS = { ban: 'ممنوعیت تردد', permit_required: 'نیازمند مجوز (طرح ترافیک)', odd_even: 'طرح زوج و فرد' };
const PERMITS = { traffic_plan: 'مجوز طرح ترافیک', odd_even: 'مجوز زوج و فرد', heavy: 'مجوز تردد سنگین', resident: 'ساکن محدوده', emergency: 'امدادی', other: 'سایر' };
export { PERMITS };

export async function render(el) {
  const [rules, dists] = await Promise.all([get('/api/rules'), get('/api/districts')]);
  const dn = Object.fromEntries(dists.map(d => [d.id, d.name]));
  const wd = state.meta.weekdays;
  el.innerHTML = `<div class="section-title"><div class="small muted">قوانین به صورت خودکار روی همه ترددها بررسی می‌شوند و تخلفات ثبت می‌گردد.</div>
    <div class="actions">${can('admin') ? `<button class="btn primary" id="add">${icon('plus')} قانون جدید</button>` : ''}</div></div>
    <div class="grid g2">${rules.length ? rules.map(r => `<div class="card" data-id="${r.id}" style="${r.enabled ? '' : 'opacity:.6'}">
      <div class="card-h"><h3>${esc(r.name)}</h3><div class="actions">${r.enabled ? '<span class="badge ok">فعال</span>' : '<span class="badge">غیرفعال</span>'}${sevBadge(r.severity, ({ critical: 'بحرانی', high: 'زیاد', medium: 'متوسط', low: 'کم' })[r.severity])}</div></div>
      <dl class="kv"><dt>نوع</dt><dd>${KINDS[r.kind]}</dd>
        <dt>محدوده</dt><dd>${r.district_ids?.length ? r.district_ids.map(i => esc(dn[i] || '?')).join('، ') : 'کل شهر'}</dd>
        <dt>خودروها</dt><dd>${r.vehicle_types?.length ? r.vehicle_types.map(t => esc(state.meta.vehicle_types[t])).join('، ') : 'همه'}${r.heavy_only ? ' (فقط سنگین)' : ''}${r.loaded === 'loaded' ? ' — باردار' : r.loaded === 'empty' ? ' — بدون بار' : ''}</dd>
        <dt>روزها</dt><dd>${r.weekdays?.length ? r.weekdays.map(d => wd[d]).join('، ') : 'همه روزها'}</dd>
        <dt>ساعات</dt><dd class="num">${r.time_windows?.length ? r.time_windows.map(w => fa(w.start) + ' تا ' + fa(w.end)).join(' ، ') : 'شبانه‌روزی'}</dd>
        ${r.exempt_categories?.length ? `<dt>معاف</dt><dd>${r.exempt_categories.map(c => esc(state.meta.plate_categories[c])).join('، ')}</dd>` : ''}
        ${r.kind === 'odd_even' ? `<dt>روزهای زوج</dt><dd>${(r.even_weekdays || []).map(d => wd[d]).join('، ')}</dd>` : ''}</dl>
      ${can('admin') ? `<div style="display:flex;gap:8px;margin-top:14px"><button class="btn sm" data-edit>${icon('edit')} ویرایش</button><button class="btn sm danger" data-del>${icon('trash')}</button></div>` : ''}</div>`).join('')
      : `<div class="card">${empty('قانونی تعریف نشده')}</div>`}</div>`;
  const reload = () => render(el);
  $('#add', el)?.addEventListener('click', () => edit({ kind: 'ban', enabled: true, severity: 'medium', loaded: 'any', time_windows: [{ start: '06:00', end: '20:00' }], even_weekdays: [0, 2, 4] }, dists, reload));
  el.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => edit(rules.find(r => r.id === +b.closest('[data-id]').dataset.id), dists, reload));
  el.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => { if (await confirmBox('این قانون حذف شود؟')) { await del('/api/rules/' + b.closest('[data-id]').dataset.id); reload(); } });
}

function edit(r, dists, done) {
  const m = state.meta;
  const wdObj = Object.fromEntries(m.weekdays.map((d, i) => [i, d]));
  const cats = Object.fromEntries(Object.entries(m.plate_categories).filter(([k]) => !['unknown'].includes(k)));
  const vtypes = Object.fromEntries(Object.entries(m.vehicle_types).filter(([k]) => k !== 'unknown'));
  const windows = (r.time_windows || []).map(w => ({ ...w }));
  const md = modal({ title: r.id ? 'ویرایش قانون' : 'قانون جدید', wide: true, body: `<div class="form-grid" id="f">
    <label class="f">عنوان قانون<input class="input" name="name" value="${esc(r.name || '')}" placeholder="مثلا ممنوعیت تردد کامیون در مرکز شهر"></label>
    <label class="f">نوع قانون<select class="input" name="kind">${options(KINDS, r.kind)}</select></label>
    <div class="f full">محدوده‌ها (خالی = کل شهر)${chipSelect('district_ids', Object.fromEntries(dists.map(d => [d.id, d.name])), r.district_ids || [], true)}</div>
    <div class="f full">انواع خودرو مشمول (خالی = همه)${chipSelect('vehicle_types', vtypes, r.vehicle_types || [])}</div>
    <label class="f">وضعیت بار<select class="input" name="loaded">${options({ any: 'مهم نیست', loaded: 'فقط باردار', empty: 'فقط بدون بار' }, r.loaded)}</select></label>
    <label class="f">شدت تخلف<select class="input" name="severity">${options({ low: 'کم', medium: 'متوسط', high: 'زیاد', critical: 'بحرانی' }, r.severity)}</select></label>
    <label class="check"><input type="checkbox" name="heavy_only" ${r.heavy_only ? 'checked' : ''}> فقط خودروهای سنگین</label>
    <label class="check"><input type="checkbox" name="enabled" ${r.enabled ? 'checked' : ''}> قانون فعال است</label>
    <div class="f full">روزهای اجرا (خالی = همه روزها)${chipSelect('weekdays', wdObj, r.weekdays || [], true)}</div>
    <div class="f full">بازه‌های ساعتی (خالی = شبانه‌روزی)<div id="tw" style="display:flex;flex-direction:column;gap:8px"></div><button type="button" class="btn sm" id="addw" style="align-self:flex-start">${icon('plus')} افزودن بازه</button></div>
    <div class="f full" data-k="odd_even">روزهایی که پلاک‌های <b>زوج</b> مجاز به تردد هستند (در سایر روزهای اجرا پلاک‌های فرد مجازند)${chipSelect('even_weekdays', wdObj, r.even_weekdays || [0, 2, 4], true)}
      <span class="small muted">ملاک زوج/فرد: رقم آخر عدد سه‌رقمی پلاک</span></div>
    <div class="f full">دسته پلاک‌های معاف${chipSelect('exempt_categories', cats, r.exempt_categories || [])}</div>
    <div class="f full">مجوزهایی که از این قانون معاف می‌کنند${chipSelect('permit_types', PERMITS, r.permit_types || [])}</div>
    <label class="f full">توضیحات<textarea class="input" name="description">${esc(r.description || '')}</textarea></label></div>`,
    footer: `<button class="btn primary" id="sv">ذخیره</button><button class="btn" data-close>انصراف</button>` });
  bindChips(md.el);
  const drawW = () => {
    md.$('#tw').innerHTML = windows.map((w, i) => `<div style="display:flex;gap:8px;align-items:center" data-i="${i}">از <input class="input ltr" type="time" value="${w.start}" data-s style="width:130px">
      تا <input class="input ltr" type="time" value="${w.end}" data-e style="width:130px"><button type="button" class="btn sm ghost" data-rm>${icon('trash')}</button></div>`).join('') || '<span class="small muted">شبانه‌روزی</span>';
    md.$$('#tw [data-i]').forEach(row => {
      const i = +row.dataset.i;
      row.querySelector('[data-s]').onchange = (e) => windows[i].start = e.target.value;
      row.querySelector('[data-e]').onchange = (e) => windows[i].end = e.target.value;
      row.querySelector('[data-rm]').onclick = () => { windows.splice(i, 1); drawW(); };
    });
  };
  drawW();
  md.$('#addw').onclick = () => { windows.push({ start: '07:00', end: '09:00' }); drawW(); };
  const kindSel = md.$('[name=kind]');
  const syncKind = () => md.$('[data-k=odd_even]').classList.toggle('hidden', kindSel.value !== 'odd_even');
  kindSel.onchange = syncKind; syncKind();
  md.$('#sv').onclick = async () => {
    const f = formData(md.$('#f'));
    const data = { ...f, time_windows: windows.filter(w => w.start && w.end) };
    for (const k of ['district_ids', 'weekdays', 'even_weekdays']) data[k] = chipValues(md.el, k);
    for (const k of ['vehicle_types', 'exempt_categories', 'permit_types']) data[k] = chipValues(md.el, k);
    if (!data.name) return toast('عنوان را وارد کنید', 'bad');
    try { r.id ? await put('/api/rules/' + r.id, data) : await post('/api/rules', data); toast('ذخیره شد', 'ok'); md.close(); done(); }
    catch (e) { toast(e.message, 'bad'); }
  };
}
