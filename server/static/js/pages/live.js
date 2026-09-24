import { $, empty, esc, fa, get, icon, options, statusBadge } from '../core.js';
import { feedItem } from './dashboard.js';
import { showEvent } from './events.js';

let layout = 4;
try { layout = +localStorage.getItem('liveLayout') || 4; } catch (e) {}

/** Self-paced snapshot polling: avoids the browser's per-host connection limit with many tiles. */
function pollImage(img, camId, stopped, onState) {
  let busy = false;
  const next = () => {
    if (stopped() || !img.isConnected) return;
    if (busy) return;
    busy = true;
    const probe = new Image();
    probe.onload = () => { img.src = probe.src; busy = false; onState(true); setTimeout(next, 250); };
    probe.onerror = () => { busy = false; onState(false); setTimeout(next, 3000); };
    probe.src = `/api/cameras/${camId}/snapshot?cached=1&t=${Date.now()}`;
  };
  next();
}

export async function render(el) {
  const [cams, dists] = await Promise.all([get('/api/cameras'), get('/api/districts')]);
  let stopped = false;
  let page = 0;
  el.innerHTML = `<div class="section-title"><div class="seg" id="lay">${[1, 4, 9, 16].map(n => `<button data-n="${n}" class="${n === layout ? 'on' : ''}">${fa(n)} تصویر</button>`).join('')}</div>
    <select class="input" id="dist" style="width:200px">${options(Object.fromEntries(dists.map(d => [d.id, d.name])), '', 'همه مناطق')}</select>
    <div class="actions"><button class="btn sm" id="prev">قبلی</button><span class="small muted" id="pg"></span><button class="btn sm" id="next">بعدی</button></div></div>
    <div class="grid" style="grid-template-columns:1fr 340px;align-items:start" id="wrap">
      <div class="cams l${layout}" id="grid"></div>
      <div class="card flush"><div class="card-h"><h3>رویدادهای زنده</h3><div class="actions"><span class="live-dot">زنده</span></div></div>
        <div class="feed" id="feed" style="max-height:calc(100vh - 230px);margin-top:10px">${empty('در انتظار تردد…')}</div></div></div>`;
  if (innerWidth < 1100) $('#wrap', el).style.gridTemplateColumns = '1fr';

  const filtered = () => cams.filter(c => c.enabled && (!$('#dist', el).value || String(c.district_id) === $('#dist', el).value));
  function draw() {
    const list = filtered();
    const pages = Math.max(1, Math.ceil(list.length / layout));
    page = Math.min(page, pages - 1);
    $('#pg', el).textContent = `صفحه ${fa(page + 1)} از ${fa(pages)}`;
    const grid = $('#grid', el);
    grid.className = 'cams l' + layout;
    const shown = list.slice(page * layout, page * layout + layout);
    if (!shown.length) { grid.innerHTML = `<div class="card">${empty('دوربین فعالی وجود ندارد. از بخش «دوربین‌ها» دوربین اضافه کنید.')}</div>`; return; }
    grid.innerHTML = shown.map(c => `<div class="cam-tile" data-id="${c.id}">
      <img alt="${esc(c.name)}"><div class="off">${c.status === 'online' ? '<span class="spinner"></span>' : `${icon('camera')}<br>${esc(c.status_message || 'در انتظار اتصال دوربین')}`}</div>
      <div class="ov"><span>${esc(c.name)}</span>${statusBadge(c.status)}</div>
      <div class="tools"><button data-full>${icon('full')} تمام‌صفحه</button><a href="#/cameras/${c.id}"><button>تنظیمات</button></a></div></div>`).join('');
    grid.querySelectorAll('.cam-tile').forEach(t => {
      const img = t.querySelector('img'), off = t.querySelector('.off');
      pollImage(img, t.dataset.id, () => stopped, (ok) => off.classList.toggle('hidden', ok));
      t.querySelector('[data-full]').onclick = () => fullscreen(cams.find(c => c.id === +t.dataset.id));
    });
  }
  el.querySelectorAll('#lay button').forEach(b => b.onclick = () => {
    layout = +b.dataset.n; try { localStorage.setItem('liveLayout', layout); } catch (e) {}
    el.querySelectorAll('#lay button').forEach(x => x.classList.toggle('on', x === b)); page = 0; draw();
  });
  $('#dist', el).onchange = () => { page = 0; draw(); };
  $('#prev', el).onclick = () => { page = Math.max(0, page - 1); draw(); };
  $('#next', el).onclick = () => { page++; draw(); };
  draw();

  const feed = $('#feed', el);
  feed.onclick = (e) => { const it = e.target.closest('[data-ev]'); if (it) showEvent(+it.dataset.ev); };
  const onEvent = (e) => {
    if (feed.querySelector('.empty')) feed.innerHTML = '';
    feed.insertAdjacentHTML('afterbegin', feedItem(e.detail));
    while (feed.children.length > 50) feed.lastElementChild.remove();
  };
  window.addEventListener('pelak:event', onEvent);
  return () => { stopped = true; window.removeEventListener('pelak:event', onEvent); };
}

function fullscreen(cam) {
  const bg = document.createElement('div');
  bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal wide" style="width:min(1500px,100%)"><div class="modal-h"><h3>${esc(cam.name)}</h3>${statusBadge(cam.status)}
    <button class="btn ghost sm x" aria-label="بستن">${icon('x')}</button></div>
    <div style="background:#000"><img src="/api/cameras/${cam.id}/stream.mjpg" style="width:100%;max-height:78vh;object-fit:contain;display:block" alt=""></div></div>`;
  const close = () => { bg.querySelector('img').src = ''; bg.remove(); };
  bg.querySelector('.x').onclick = close;
  bg.addEventListener('mousedown', (e) => { if (e.target === bg) close(); });
  document.body.appendChild(bg);
}
