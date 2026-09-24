import { $, colorBadge, empty, esc, fa, fdt, get, icon, kindBadge, num, plateHtml, sevBadge, state, vt } from '../core.js';
import { showEvent } from './events.js';
import { baseMap } from './map.js';

export async function render(el, [plate]) {
  if (!plate) { el.innerHTML = `<div class="card">${empty('پلاکی برای جستجو وارد نشده')}</div>`; return; }
  const d = await get('/api/vehicles/' + encodeURIComponent(plate));
  const p = d.plate;
  if (!d.count && !d.violations.length) {
    el.innerHTML = `<div class="card" style="text-align:center;padding:40px">${plateHtml(p.raw, 'lg')}<p class="muted">هیچ ترددی برای این پلاک ثبت نشده است.</p>
      <p class="small faint">برای جستجوی بخشی از پلاک از صفحه <a href="#/events">ترددها</a> استفاده کنید.</p></div>`;
    return;
  }
  const watch = d.watchlist.filter(w => w.active);
  el.innerHTML = `
  ${watch.length ? `<div class="card" style="border-color:var(--bad);background:var(--bad-soft);margin-bottom:16px"><b style="color:var(--bad)">⚠ این خودرو در فهرست تحت پیگیری است:</b> ${esc(watch.map(w => w.note || w.reason).join('، '))}</div>` : ''}
  <div class="grid g-1-2">
    <div class="card" style="text-align:center">${plateHtml(p.raw, 'lg')}
      <div style="margin:14px 0 6px"><span class="badge accent">${esc(p.category_label)}</span> ${p.even != null ? `<span class="badge">${p.even ? 'زوج' : 'فرد'}</span>` : ''}</div>
      <dl class="kv" style="text-align:right;margin-top:16px">
        <dt>تعداد تردد</dt><dd class="num">${num(d.count)}</dd><dt>تعداد تخلف</dt><dd class="num">${num(d.violations.length)}</dd>
        <dt>نوع خودرو</dt><dd>${esc(vt(d.vehicle_type))}</dd><dt>رنگ</dt><dd>${d.color ? colorBadge(d.color) : '—'}</dd>
        <dt>اولین مشاهده</dt><dd class="num">${fdt(d.first_seen)}</dd><dt>آخرین مشاهده</dt><dd class="num">${fdt(d.last_seen)}</dd></dl></div>
    <div class="card flush" style="min-height:340px"><div class="card-h"><h3>مسیر تردد روی نقشه</h3></div><div id="m" class="map" style="height:300px;margin-top:12px;border-radius:0"></div></div>
  </div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card flush"><div class="card-h"><h3>سوابق تردد</h3></div><div class="table-wrap" style="margin-top:10px;max-height:480px">
      <table class="t"><tbody>${d.events.map(e => `<tr class="click" data-id="${e.id}"><td>${e.vehicle_image ? `<img class="thumb sm" src="/media/${e.vehicle_image}" loading="lazy" alt="">` : ''}</td>
        <td class="num nowrap">${fdt(e.ts)}</td><td>${esc(e.camera_name || '—')}</td><td>${kindBadge(e.kind, e.kind_label)}</td><td class="num">${e.speed_kmh ? num(e.speed_kmh) + ' km/h' : ''}</td></tr>`).join('')}</tbody></table></div></div>
    <div class="card flush"><div class="card-h"><h3>تخلفات</h3></div><div class="table-wrap" style="margin-top:10px;max-height:480px">
      ${d.violations.length ? `<table class="t"><tbody>${d.violations.map(v => `<tr><td><b>${esc(v.type_label)}</b><div class="small muted">${esc(v.title)}</div></td>
        <td class="num nowrap">${fdt(v.ts)}</td><td>${sevBadge(v.severity, v.severity_label)}</td><td>${esc(v.status_label)}</td></tr>`).join('')}</tbody></table>` : empty('تخلفی ثبت نشده')}</div></div>
  </div>`;
  el.querySelectorAll('tr[data-id]').forEach(tr => tr.onclick = () => showEvent(+tr.dataset.id));
  const map = baseMap($('#m', el));
  if (d.path.length) {
    const pts = d.path.map(x => [x.lat, x.lng]);
    L.polyline(pts, { color: '#22d3ee', weight: 4, opacity: .8, dashArray: '8 6' }).addTo(map);
    d.path.forEach((x, i) => L.circleMarker([x.lat, x.lng], { radius: i === d.path.length - 1 ? 9 : 6, color: '#fff', weight: 2, fillColor: i === d.path.length - 1 ? '#ef4444' : '#6366f1', fillOpacity: 1 })
      .addTo(map).bindTooltip(`${esc(x.camera)}<br>${fdt(x.ts)}`));
    map.fitBounds(pts, { padding: [40, 40], maxZoom: 16 });
  }
  return () => map.remove();
}
