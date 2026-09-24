import { $, PALETTE, chartColors, empty, esc, fa, get, num } from '../core.js';
import { chartOpts } from './dashboard.js';

export async function render(el) {
  el.innerHTML = `<div class="section-title"><div class="seg" id="rg"><button data-d="1">امروز</button><button data-d="7" class="on">۷ روز</button><button data-d="30">۳۰ روز</button><button data-d="90">۹۰ روز</button></div>
    <div class="actions"><a class="btn" href="#/events">خروجی جزئی ترددها</a><a class="btn" href="#/violations">خروجی تخلفات</a></div></div>
    <div class="grid g2"><div class="card"><div class="card-h"><h3>روند تردد و تخلف</h3></div><div class="chart-box"><canvas id="c1"></canvas></div></div>
      <div class="card"><div class="card-h"><h3>تخلفات به تفکیک نوع</h3></div><div class="chart-box"><canvas id="c2"></canvas></div></div></div>
    <div class="grid g3" style="margin-top:16px">
      <div class="card"><div class="card-h"><h3>نوع خودرو</h3></div><div class="chart-box sm"><canvas id="c3"></canvas></div></div>
      <div class="card"><div class="card-h"><h3>رنگ خودرو</h3></div><div class="chart-box sm"><canvas id="c4"></canvas></div></div>
      <div class="card"><div class="card-h"><h3>نوع پلاک</h3></div><div class="chart-box sm"><canvas id="c5"></canvas></div></div></div>
    <div class="grid g3" style="margin-top:16px">
      <div class="card"><div class="card-h"><h3>توزیع سرعت (km/h)</h3></div><div class="chart-box sm"><canvas id="c6"></canvas></div></div>
      <div class="card"><div class="card-h"><h3>پرترددترین دوربین‌ها</h3></div><div class="bar-list" id="bc"></div></div>
      <div class="card"><div class="card-h"><h3>تردد مناطق</h3></div><div class="bar-list" id="bd"></div></div></div>`;
  const charts = [];
  async function load(days) {
    charts.forEach(c => c.destroy()); charts.length = 0;
    const [ts, b] = await Promise.all([get('/api/stats/timeseries?days=' + days), get('/api/stats/breakdown?days=' + days)]);
    const c = chartColors();
    charts.push(new Chart($('#c1', el), { type: 'bar', data: { labels: ts.labels.map(fa), datasets: [
      { label: 'تردد', data: ts.events, backgroundColor: c.accent, borderRadius: 6 }, { label: 'تخلف', data: ts.violations, backgroundColor: c.bad, borderRadius: 6 }] }, options: chartOpts(c) }));
    const hbar = (id, obj, colors) => {
      const e = Object.entries(obj).sort((a, b) => b[1] - a[1]);
      const o = chartOpts(c); o.indexAxis = 'y'; o.plugins.legend.display = false;
      o.scales.x.ticks.callback = (v) => fa(v); o.scales.y.ticks.callback = function (v) { return this.getLabelForValue(v); };
      charts.push(new Chart($(id, el), { type: 'bar', data: { labels: e.map(x => x[0]), datasets: [{ data: e.map(x => x[1]), backgroundColor: colors || PALETTE, borderRadius: 6 }] }, options: o }));
    };
    const pie = (id, labels, data, colors) => charts.push(new Chart($(id, el), { type: 'doughnut', data: { labels, datasets: [{ data, backgroundColor: colors || PALETTE, borderWidth: 0 }] },
      options: { maintainAspectRatio: false, cutout: '62%', plugins: { legend: { position: 'left', labels: { color: c.text, font: { family: 'Vazirmatn' }, boxWidth: 12 } } } } }));
    hbar('#c2', b.violations);
    pie('#c3', Object.keys(b.vehicle_types), Object.values(b.vehicle_types));
    const colors = Object.values(b.colors).sort((a, b) => b.count - a.count);
    pie('#c4', colors.map(x => x.label), colors.map(x => x.count), colors.map(x => x.hex));
    pie('#c5', Object.keys(b.plate_categories), Object.values(b.plate_categories));
    const o6 = chartOpts(c); o6.plugins.legend.display = false;
    charts.push(new Chart($('#c6', el), { type: 'bar', data: { labels: Object.keys(b.speed_histogram).map(fa), datasets: [{ data: Object.values(b.speed_histogram), backgroundColor: c.accent2, borderRadius: 5 }] }, options: o6 }));
    const bars = (sel, items) => { const max = Math.max(1, ...items.map(x => x.count)); $(sel, el).innerHTML = items.length ? items.map(x => `<div class="it"><span>${esc(x.name)}</span><div class="track"><i style="width:${x.count / max * 100}%"></i></div><b class="num">${num(x.count)}</b></div>`).join('') : empty(); };
    bars('#bc', b.cameras); bars('#bd', b.districts);
  }
  el.querySelectorAll('#rg button').forEach(b => b.onclick = () => { el.querySelectorAll('#rg button').forEach(x => x.classList.toggle('on', x === b)); load(+b.dataset.d); });
  await load(7);
  return () => charts.forEach(c => c.destroy());
}
