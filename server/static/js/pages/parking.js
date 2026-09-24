import { $, duration, empty, esc, fa, fdt, get, kindBadge, num, plateHtml } from '../core.js';
import { showEvent } from './events.js';

export async function render(el) {
  el.innerHTML = `<div class="section-title"><div class="seg" id="win"><button data-m="30" class="on">۳۰ دقیقه اخیر</button><button data-m="120">۲ ساعت</button><button data-m="1440">۲۴ ساعت</button></div>
    <div class="actions"><span class="small muted">برای تشخیص پارک، در تنظیمات هر دوربین ناحیه‌های «پارک حاشیه‌ای»، «توقف ممنوع» و «مسیر عبور» را رسم کنید.</span></div></div>
    <div class="grid g4" id="k"></div>
    <div class="grid g-1-2" style="margin-top:16px"><div class="card flush"><div class="card-h"><h3>به تفکیک دوربین</h3></div><div id="pc" style="margin-top:10px"></div></div>
      <div class="card flush"><div class="card-h"><h3>خودروهای متوقف</h3></div><div id="pl" style="margin-top:10px"></div></div></div>`;
  let minutes = 30;
  el.querySelectorAll('#win button').forEach(b => b.onclick = () => { el.querySelectorAll('#win button').forEach(x => x.classList.toggle('on', x === b)); minutes = +b.dataset.m; load(); });
  async function load() {
    const d = await get('/api/parking/current?minutes=' + minutes);
    const count = (k) => d.items.filter(x => x.kind === k).length;
    $('#k', el).innerHTML = [['پارک حاشیه‌ای', count('parking'), 'ok'], ['پارک دوبل', count('double_parking'), 'bad'], ['توقف در محل ممنوع', count('no_parking'), 'bad'], ['توقف در مسیر', count('stopped'), 'warn']]
      .map(([l, n, t]) => `<div class="card stat tone-${t}"><div class="label">${l}</div><div class="value num">${num(n)}</div></div>`).join('');
    $('#pc', el).innerHTML = d.cameras.length ? `<table class="t"><thead><tr><th>دوربین</th><th>حاشیه</th><th>دوبل</th><th>ممنوع</th></tr></thead><tbody>${d.cameras.map(c =>
      `<tr><td>${esc(c.camera_name)}</td><td class="num">${num(c.parking || 0)}</td><td class="num">${num(c.double_parking || 0)}</td><td class="num">${num((c.no_parking || 0) + (c.stopped || 0))}</td></tr>`).join('')}</tbody></table>` : empty();
    $('#pl', el).innerHTML = d.items.length ? `<div class="table-wrap"><table class="t"><tbody>${d.items.map(e => `<tr class="click" data-id="${e.id}">
      <td>${e.vehicle_image ? `<img class="thumb" src="/media/${e.vehicle_image}" loading="lazy" alt="">` : ''}</td><td>${plateHtml(e.plate)}</td><td>${kindBadge(e.kind, e.kind_label)}</td>
      <td>${esc(e.vehicle_type_label)}</td><td>${esc(e.camera_name || '')}<div class="small muted">${esc(e.zone || '')}</div></td><td class="small">${duration(e.dwell_seconds)}</td><td class="num small nowrap">${fdt(e.ts)}</td></tr>`).join('')}</tbody></table></div>` : empty('خودروی متوقفی در این بازه ثبت نشده');
    el.querySelectorAll('tr[data-id]').forEach(tr => tr.onclick = () => showEvent(+tr.dataset.id));
  }
  await load();
  const t = setInterval(load, 20000);
  return () => clearInterval(t);
}
