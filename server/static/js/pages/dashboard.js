import { PALETTE, chartColors, colorBadge, empty, esc, fa, ftime, get, icon, kindBadge, loadedBadge, num, plateHtml, state, statusBadge } from '../core.js';
import { showEvent } from './events.js';

const charts = [];

export async function render(el) {
  el.innerHTML = `
  <div class="grid g4" id="kpis"></div>
  <div class="grid g-2-1" style="margin-top:16px">
    <div class="card"><div class="card-h"><h3>روند تردد و تخلفات</h3><div class="actions"><div class="seg" id="range">
      <button data-d="1" class="on">امروز</button><button data-d="7">۷ روز</button><button data-d="30">۳۰ روز</button></div></div></div>
      <div class="chart-box"><canvas id="c-ts"></canvas></div></div>
    <div class="card flush"><div class="card-h"><h3>ترددهای لحظه‌ای</h3><div class="actions"><span class="live-dot">زنده</span></div></div>
      <div class="feed" id="feed" style="margin-top:12px;max-height:330px">${empty('در انتظار ترددهای جدید…')}</div></div>
  </div>
  <div class="grid g3" style="margin-top:16px">
    <div class="card"><div class="card-h"><h3>ترکیب خودروها (امروز)</h3></div><div class="chart-box sm"><canvas id="c-types"></canvas></div></div>
    <div class="card"><div class="card-h"><h3>تخلفات امروز</h3><div class="actions"><a class="btn sm ghost" href="#/violations">همه</a></div></div><div class="bar-list" id="vio"></div></div>
    <div class="card flush"><div class="card-h"><h3>وضعیت دوربین‌ها</h3><div class="actions"><a class="btn sm ghost" href="#/cameras">مدیریت</a></div></div>
      <div id="cams" style="max-height:260px;overflow:auto;margin-top:10px"></div></div>
  </div>`;

  let stopped = false;  // requests may resolve after the user navigated away
  const $ = (sel) => (!stopped && el.querySelector(sel)) || document.createElement('div');
  let days = 1;
  el.querySelectorAll('#range button').forEach(b => b.onclick = () => {
    el.querySelectorAll('#range button').forEach(x => x.classList.toggle('on', x === b));
    days = +b.dataset.d; loadSeries();
  });

  async function loadKpis() {
    const o = await get('/api/stats/overview');
    const diff = o.events_yesterday ? Math.round((o.events_today - o.events_yesterday) / o.events_yesterday * 100) : null;
    const tiles = [
      ['تردد امروز', num(o.events_today), 'car', 'accent', diff == null ? 'دیروز: ' + num(o.events_yesterday) : `<span class="${diff >= 0 ? 'up' : 'down'}">${diff >= 0 ? '▲' : '▼'} ${fa(Math.abs(diff))}٪</span> نسبت به دیروز`],
      ['پلاک‌های یکتا', num(o.unique_plates_today), 'plate', 'info', 'خودروی شناسایی‌شده امروز'],
      ['تخلفات امروز', num(o.violations_today), 'alert', 'bad', `${num(o.violations_pending)} مورد در انتظار بررسی`],
      ['دوربین‌های فعال', `${num(o.cameras_online)}<span class="muted" style="font-size:18px"> / ${num(o.cameras_total)}</span>`, 'camera', o.cameras_error ? 'warn' : 'ok', o.cameras_error ? `${num(o.cameras_error)} دوربین قطع یا دارای خطا` : 'همه دوربین‌ها سالم'],
      ['خودروهای سنگین', num(o.heavy_today), 'truck', 'warn', 'کامیون، تریلی، اتوبوس'],
      ['پارک حاشیه‌ای', num(o.parked_recent), 'parking', 'ok', '۳۰ دقیقه اخیر'],
      ['پارک دوبل', num(o.double_parked_recent), 'parking', 'bad', '۳۰ دقیقه اخیر'],
      ['میانگین سرعت', o.avg_speed_today ? num(o.avg_speed_today) + '<span class="muted" style="font-size:14px"> km/h</span>' : '—', 'speed', 'info', 'امروز، دوربین‌های کالیبره'],
    ];
    $('#kpis').innerHTML = tiles.map(([l, v, i, t, s]) => `<div class="card stat tone-${t}"><div class="ico">${icon(i)}</div>
      <div class="label">${l}</div><div class="value num">${v}</div><div class="trend muted">${s}</div></div>`).join('');
  }

  async function loadSeries() {
    const d = await get('/api/stats/timeseries?days=' + days);
    const c = chartColors();
    if (stopped) return;
    charts[0]?.destroy();
    const ctx = $('#c-ts').getContext('2d');
    const grad = ctx.createLinearGradient(0, 0, 0, 280);
    grad.addColorStop(0, c.accent + '55'); grad.addColorStop(1, c.accent + '00');
    charts[0] = new Chart(ctx, {
      type: 'line',
      data: { labels: d.labels.map(fa), datasets: [
        { label: 'تردد', data: d.events, borderColor: c.accent, backgroundColor: grad, fill: true, tension: .35, pointRadius: 0, borderWidth: 2.5 },
        { label: 'تخلف', data: d.violations, borderColor: c.bad, backgroundColor: c.bad, tension: .35, pointRadius: 0, borderWidth: 2, yAxisID: 'y1' }] },
      options: chartOpts(c, true),
    });
  }

  async function loadBreakdown() {
    const b = await get('/api/stats/breakdown?days=1');
    if (stopped) return;
    const c = chartColors();
    charts[1]?.destroy();
    const entries = Object.entries(b.vehicle_types).sort((a, b) => b[1] - a[1]);
    charts[1] = new Chart($('#c-types'), {
      type: 'doughnut',
      data: { labels: entries.map(e => e[0]), datasets: [{ data: entries.map(e => e[1]), backgroundColor: PALETTE, borderWidth: 0 }] },
      options: { maintainAspectRatio: false, cutout: '68%', plugins: { legend: { position: 'left', labels: { color: c.text, font: { family: 'Vazirmatn' }, boxWidth: 12, padding: 10 } } } },
    });
    const v = Object.entries(b.violations).sort((a, b) => b[1] - a[1]);
    const max = Math.max(1, ...v.map(x => x[1]));
    $('#vio').innerHTML = v.length ? v.map(([k, n]) => `<div class="it"><span>${esc(k)}</span><div class="track"><i style="width:${n / max * 100}%"></i></div><b class="num">${num(n)}</b></div>`).join('') : empty('تخلفی ثبت نشده');
  }

  async function loadCams() {
    const cams = await get('/api/cameras');
    $('#cams').innerHTML = cams.length ? `<table class="t"><tbody>${cams.map(c => `<tr><td><b>${esc(c.name)}</b><div class="small muted">${esc(c.district_name || c.address || '')}</div></td>
      <td>${statusBadge(c.status)}</td><td class="small muted num">${c.status === 'online' ? fa(c.fps) + ' fps' : ''}</td></tr>`).join('')}</tbody></table>` : empty('هنوز دوربینی تعریف نشده');
  }

  async function loadFeed() {
    const r = await get('/api/events?size=12');
    if (r.items.length) $('#feed').innerHTML = r.items.map(feedItem).join('');
  }

  const onEvent = (e) => {
    const feed = $('#feed');
    if (!feed) return;
    if (feed.querySelector('.empty')) feed.innerHTML = '';
    feed.insertAdjacentHTML('afterbegin', feedItem(e.detail));
    while (feed.children.length > 40) feed.lastElementChild.remove();
  };
  el.addEventListener('click', (e) => { const it = e.target.closest('[data-ev]'); if (it) showEvent(+it.dataset.ev); });
  window.addEventListener('pelak:event', onEvent);

  await Promise.all([loadKpis(), loadSeries(), loadBreakdown(), loadCams(), loadFeed()]).catch(err => console.error(err));
  const timer = setInterval(() => { loadKpis(); loadCams(); }, 15000);
  const slow = setInterval(() => { loadSeries(); loadBreakdown(); }, 60000);
  return () => { stopped = true; window.removeEventListener('pelak:event', onEvent); clearInterval(timer); clearInterval(slow); charts.forEach(c => c?.destroy()); charts.length = 0; };
}

export function feedItem(e) {
  const vio = (e.violations || []).map(v => `<span class="badge bad">${esc(v.title.split(':')[0])}</span>`).join('');
  return `<div class="feed-item" data-ev="${e.id}">
    ${e.vehicle_image ? `<img class="thumb sm" src="/media/${e.vehicle_image}" loading="lazy" alt="">` : `<div class="thumb sm"></div>`}
    <div class="meta"><div class="row">${plateHtml(e.plate)}</div>
      <div class="row small muted">${esc(e.vehicle_type_label)} · ${colorBadge(e.color, e.color_label, e.color_hex)}${e.speed_kmh ? ' · ' + num(e.speed_kmh) + ' km/h' : ''} ${loadedBadge(e.loaded)} ${e.kind !== 'passage' ? kindBadge(e.kind, e.kind_label) : ''} ${vio}</div></div>
    <div class="small faint" style="text-align:left"><div class="num">${ftime(e.ts)}</div><div>${esc(e.camera_name || '')}</div></div></div>`;
}

export function chartOpts(c, dual = false) {
  return {
    maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
    plugins: { legend: { labels: { color: c.text, font: { family: 'Vazirmatn' }, boxWidth: 12 } }, tooltip: { rtl: true, bodyFont: { family: 'Vazirmatn' }, titleFont: { family: 'Vazirmatn' } } },
    scales: {
      x: { ticks: { color: c.text, font: { family: 'Vazirmatn' }, maxRotation: 0, autoSkipPadding: 12 }, grid: { display: false } },
      y: { beginAtZero: true, ticks: { color: c.text, font: { family: 'Vazirmatn' }, callback: (v) => fa(v) }, grid: { color: c.grid } },
      ...(dual ? { y1: { beginAtZero: true, position: 'right', ticks: { color: c.bad, callback: (v) => fa(v) }, grid: { display: false } } } : {}),
    },
  };
}
