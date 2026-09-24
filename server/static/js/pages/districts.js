import { $, can, confirmBox, del, empty, esc, fa, formData, get, icon, modal, options, post, put, toast } from '../core.js';
import { baseMap, polygonEditor } from './map.js';

const KINDS = { district: 'منطقه شهرداری', traffic_zone: 'محدوده طرح ترافیک', low_emission: 'محدوده کنترل آلودگی', other: 'سایر' };

export async function render(el) {
  const dists = await get('/api/districts');
  el.innerHTML = `<div class="section-title"><div class="small muted">محدوده‌ها روی نقشه رسم می‌شوند و قوانین تردد به آن‌ها متصل می‌شوند. هر دوربین به یک منطقه تعلق دارد.</div>
    <div class="actions">${can('admin') ? `<button class="btn primary" id="add">${icon('plus')} منطقه جدید</button>` : ''}</div></div>
    <div class="grid g-1-2"><div class="card flush">${dists.length ? `<table class="t"><tbody>${dists.map(d => `<tr data-id="${d.id}">
      <td><span class="swatch" style="background:${d.color}"></span></td><td><b>${esc(d.name)}</b><div class="small muted">${esc(KINDS[d.kind] || d.kind)} ${d.code ? '· ' + esc(d.code) : ''}</div></td>
      <td class="small">${fa(d.camera_count)} دوربین${d.speed_limit ? `<div class="muted">سرعت ${fa(d.speed_limit)}</div>` : ''}</td>
      <td class="nowrap">${can('admin') ? `<button class="btn sm" data-edit>${icon('edit')}</button> <button class="btn sm danger" data-del>${icon('trash')}</button>` : ''}</td></tr>`).join('')}</tbody></table>` : empty('منطقه‌ای تعریف نشده')}</div>
    <div class="card flush" style="min-height:480px"><div id="m" class="map" style="height:100%;border-radius:0"></div></div></div>`;
  const map = baseMap($('#m', el));
  const all = [];
  dists.forEach(d => { if (d.polygon?.length > 2) { L.polygon(d.polygon, { color: d.color, weight: 2, fillOpacity: .15 }).addTo(map).bindTooltip(esc(d.name)); all.push(...d.polygon); } });
  if (all.length) map.fitBounds(all, { padding: [20, 20] });
  const reload = () => render(el);
  $('#add', el)?.addEventListener('click', () => edit({ kind: 'district', color: '#3b82f6', polygon: [] }, reload));
  el.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => edit(dists.find(d => d.id === +b.closest('tr').dataset.id), reload));
  el.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => {
    if (!await confirmBox('این منطقه حذف شود؟ دوربین‌های آن بدون منطقه می‌شوند.')) return;
    await del('/api/districts/' + b.closest('tr').dataset.id); reload();
  });
  return () => map.remove();
}

function edit(d, done) {
  let polygon = d.polygon || [];
  const m = modal({ title: d.id ? 'ویرایش منطقه' : 'منطقه جدید', wide: true, body: `<div class="grid g-1-2">
    <div class="form-grid" id="f" style="align-content:start">
      <label class="f full">نام<input class="input" name="name" value="${esc(d.name || '')}"></label>
      <label class="f">نوع<select class="input" name="kind">${options(KINDS, d.kind)}</select></label>
      <label class="f">کد<input class="input" name="code" value="${esc(d.code || '')}"></label>
      <label class="f">رنگ<input class="input" name="color" type="color" value="${d.color || '#3b82f6'}" style="height:40px;padding:4px"></label>
      <label class="f">حداکثر سرعت (km/h)<input class="input" name="speed_limit" type="number" value="${d.speed_limit ?? ''}"></label>
      <label class="f full">توضیحات<textarea class="input" name="description">${esc(d.description || '')}</textarea></label>
      <p class="small muted full" style="line-height:1.9">روی نقشه کلیک کنید تا رئوس محدوده اضافه شود. رئوس قابل جابه‌جایی هستند و با کلیک راست حذف می‌شوند.</p>
      <button class="btn sm" id="clr">${icon('trash')} پاک کردن محدوده</button></div>
    <div id="mm" class="map" style="height:460px"></div></div>`,
    footer: `<button class="btn primary" id="sv">ذخیره</button><button class="btn" data-close>انصراف</button>` });
  const map = baseMap(m.$('#mm'));
  const ed = polygonEditor(map, polygon, d.color || '#3b82f6', (p) => { polygon = p; });
  m.$('#clr').onclick = () => ed.clear();
  m.$('#sv').onclick = async () => {
    const data = { ...formData(m.$('#f')), polygon };
    if (!data.name) return toast('نام را وارد کنید', 'bad');
    try { d.id ? await put('/api/districts/' + d.id, data) : await post('/api/districts', data); toast('ذخیره شد', 'ok'); m.close(); map.remove(); done(); }
    catch (e) { toast(e.message, 'bad'); }
  };
}
