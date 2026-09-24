import { $, ago, esc, fa, get, icon, num, state, statusBadge } from '../core.js';

export function baseMap(el, opts = {}) {
  const map = L.map(el, { zoomControl: true, attributionControl: true, ...opts }).setView(state.meta.map.center, 12);
  L.tileLayer(state.meta.map.tile_url, { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(map);
  setTimeout(() => map.invalidateSize(), 200);
  return map;
}

const STATUS_COLOR = { online: '#22c55e', offline: '#ef4444', error: '#ef4444', connecting: '#f59e0b', disabled: '#64748b' };
export function camIcon(status) {
  return L.divIcon({ className: '', iconSize: [30, 30], iconAnchor: [15, 15],
    html: `<div class="cam-marker" style="background:${STATUS_COLOR[status] || '#3b82f6'}">${icon('camera')}</div>` });
}

/** Editable polygon: click on the map to add a vertex, drag vertices, right-click a vertex to delete. */
export function polygonEditor(map, points, color, onChange) {
  let pts = (points || []).map(p => L.latLng(p[0], p[1]));
  const poly = L.polygon(pts, { color, weight: 2, fillOpacity: .15 }).addTo(map);
  let markers = [];
  const emit = () => onChange(pts.map(p => [+p.lat.toFixed(6), +p.lng.toFixed(6)]));
  function redraw() {
    poly.setLatLngs(pts);
    markers.forEach(m => m.remove());
    markers = pts.map((p, i) => {
      const m = L.marker(p, { draggable: true, icon: L.divIcon({ className: '', iconSize: [14, 14], iconAnchor: [7, 7],
        html: `<div style="width:14px;height:14px;border-radius:50%;background:#fff;border:3px solid ${color}"></div>` }) }).addTo(map);
      m.on('drag', (e) => { pts[i] = e.latlng; poly.setLatLngs(pts); });
      m.on('dragend', emit);
      m.on('contextmenu', () => { pts.splice(i, 1); redraw(); emit(); });
      return m;
    });
  }
  const onClick = (e) => { pts.push(e.latlng); redraw(); emit(); };
  map.on('click', onClick);
  redraw();
  if (pts.length > 2) map.fitBounds(poly.getBounds(), { padding: [30, 30] });
  return { clear() { pts = []; redraw(); emit(); }, destroy() { map.off('click', onClick); markers.forEach(m => m.remove()); poly.remove(); } };
}

export async function render(el) {
  const [cams, dists, over] = await Promise.all([get('/api/cameras'), get('/api/districts'), get('/api/stats/breakdown?days=1')]);
  el.innerHTML = `<div class="grid" style="grid-template-columns:1fr 320px;height:calc(100vh - 130px)" id="mw">
    <div class="card flush" style="min-height:500px"><div id="m" class="map" style="height:100%;border-radius:0"></div></div>
    <div class="card" style="overflow:auto"><div class="card-h"><h3>محدوده‌ها</h3></div><div id="dl" class="zone-list"></div>
      <div class="card-h" style="margin-top:20px"><h3>دوربین‌ها</h3><span class="badge">${fa(cams.length)}</span></div><div id="cl" class="zone-list"></div></div></div>`;
  if (innerWidth < 1000) { $('#mw', el).style.gridTemplateColumns = '1fr'; $('#mw', el).style.height = 'auto'; }
  const map = baseMap($('#m', el));
  const byDist = Object.fromEntries(over.districts.map(d => [d.name, d.count]));
  const layers = {};
  const bounds = [];
  dists.forEach(d => {
    if ((d.polygon || []).length < 3) return;
    const p = L.polygon(d.polygon, { color: d.color, weight: 2, fillOpacity: .12 }).addTo(map)
      .bindPopup(`<b>${esc(d.name)}</b><br>تردد امروز: ${num(byDist[d.name] || 0)}<br>دوربین: ${fa(d.camera_count)}${d.speed_limit ? `<br>حداکثر سرعت: ${fa(d.speed_limit)}` : ''}`);
    layers[d.id] = p; bounds.push(...d.polygon);
  });
  cams.forEach(c => {
    if (c.lat == null || c.lng == null) return;
    bounds.push([c.lat, c.lng]);
    L.marker([c.lat, c.lng], { icon: camIcon(c.status) }).addTo(map).bindPopup(`<div style="width:260px;font-family:Vazirmatn">
      <b>${esc(c.name)}</b> ${statusBadge(c.status)}<div class="small muted">${esc(c.address || '')}</div>
      <img src="/api/cameras/${c.id}/snapshot?cached=1" onerror="this.remove()" style="width:100%;border-radius:8px;margin-top:8px">
      <div style="margin-top:8px;display:flex;gap:6px"><a class="btn sm" href="#/live">پایش زنده</a><a class="btn sm" href="#/events">ترددها</a></div></div>`);
  });
  if (bounds.length) map.fitBounds(bounds, { padding: [30, 30] });
  $('#dl', el).innerHTML = dists.map(d => `<label class="zone-row"><input type="checkbox" checked data-d="${d.id}">
    <span class="swatch" style="background:${d.color}"></span><span style="flex:1">${esc(d.name)}</span><span class="small muted">${num(byDist[d.name] || 0)}</span></label>`).join('') || '<div class="muted small">محدوده‌ای تعریف نشده</div>';
  el.querySelectorAll('[data-d]').forEach(cb => cb.onchange = () => { const l = layers[cb.dataset.d]; if (l) cb.checked ? l.addTo(map) : l.remove(); });
  $('#cl', el).innerHTML = cams.map(c => `<div class="zone-row" data-c="${c.id}" style="cursor:pointer"><span style="flex:1">${esc(c.name)}</span>${statusBadge(c.status)}</div>`).join('');
  el.querySelectorAll('[data-c]').forEach(r => r.onclick = () => { const c = cams.find(x => x.id === +r.dataset.c); if (c?.lat) map.setView([c.lat, c.lng], 16); });
  return () => map.remove();
}
