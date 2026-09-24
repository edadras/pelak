import { $, api, can, confirmBox, del, empty, esc, fa, formData, get, icon, num, options, post, put, state, statusBadge, toast } from '../core.js';
import { baseMap } from './map.js';

const ZONE_COLORS = { curb_parking: '#22c55e', no_parking: '#ef4444', traffic_lane: '#f59e0b', bus_lane: '#3b82f6', detection: '#94a3b8' };

export async function render(el, [id]) {
  if (id) return editor(el, id);
  const [cams, sys] = await Promise.all([get('/api/cameras'), get('/api/system')]);
  el.innerHTML = `<div class="section-title"><div class="small muted">ظرفیت پردازش فعلی: <b class="num">${fa(sys.capacity)}</b> دوربین روی <b>${fa(sys.workers.filter(w => w.alive).length)}</b> سرور پردازش
      ${sys.cameras.unassigned ? ` — <span style="color:var(--warn)">${fa(sys.cameras.unassigned)} دوربین منتظر سرور پردازش آزاد</span>` : ''}</div>
    <div class="actions">${can('admin') ? `<a class="btn primary" href="#/cameras/new">${icon('plus')} افزودن دوربین</a>` : ''}</div></div>
    <div class="card flush">${cams.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>نام</th><th>برند / منبع</th><th>منطقه</th><th>کاربری</th><th>وضعیت</th><th>پردازش</th><th>سرور</th><th></th></tr></thead><tbody>
      ${cams.map(c => `<tr><td><b>${esc(c.name)}</b><div class="small muted ltr">${esc(c.stream_url || '')}</div></td><td>${esc(state.meta.vendors[c.vendor] || c.vendor)}</td>
        <td>${esc(c.district_name || '—')}</td><td>${esc(({ traffic: 'تردد', parking: 'پارک', entrance: 'ورودی محدوده', mixed: 'ترکیبی' })[c.purpose] || c.purpose)}</td>
        <td>${statusBadge(c.enabled ? c.status : 'disabled')}${c.status_message ? `<div class="small muted" style="max-width:220px">${esc(c.status_message)}</div>` : ''}</td>
        <td class="num small">${c.status === 'online' ? fa(c.fps) + ' fps' : '—'}</td><td class="small muted">${esc(c.worker_id || '—')}</td>
        <td class="nowrap">${can('admin') ? `<a class="btn sm" href="#/cameras/${c.id}">${icon('edit')} ویرایش</a> <button class="btn sm danger" data-del="${c.id}">${icon('trash')}</button>` : ''}</td></tr>`).join('')}
      </tbody></table></div>` : empty('هنوز دوربینی تعریف نشده است')}</div>
    <div class="help" style="margin-top:16px"><b>اتصال تعداد نامحدود دوربین:</b> هر سرور پردازش (worker) تا سقف مشخصی دوربین را برمی‌دارد. برای افزایش ظرفیت کافی است سرور پردازش جدیدی
      به همان پایگاه داده و Redis متصل کنید؛ دوربین‌ها به صورت خودکار بین سرورها توزیع می‌شوند و در صورت خرابی یک سرور، به سرور دیگر منتقل می‌شوند.</div>`;
  el.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => {
    if (!await confirmBox('این دوربین حذف شود؟ ترددهای ثبت‌شده باقی می‌مانند.')) return;
    await del('/api/cameras/' + b.dataset.del); toast('حذف شد', 'ok'); render(el, []);
  });
}

async function editor(el, id) {
  const isNew = id === 'new';
  const dists = await get('/api/districts');
  const c = isNew ? { enabled: true, vendor: 'axis', stream: 'main', channel: 1, purpose: 'traffic', zones: [], speed_calibration: {}, analytics: {} } : await get('/api/cameras/' + id);
  const a = { detect_plates: true, plate_mode: 'vehicle', park_seconds: 60, no_parking_seconds: 30, double_parking_seconds: 45, ...(c.analytics || {}) };
  const zones = JSON.parse(JSON.stringify(c.zones || []));
  const calib = JSON.parse(JSON.stringify(c.speed_calibration || {}));
  let snapshot = null;

  el.innerHTML = `<div class="section-title"><a class="btn ghost" href="#/cameras">→ بازگشت</a><h2>${isNew ? 'دوربین جدید' : esc(c.name)}</h2>${isNew ? '' : statusBadge(c.status)}
    <div class="actions"><button class="btn" id="test">${icon('play')} تست اتصال</button><button class="btn primary" id="save">${icon('check')} ذخیره</button></div></div>
    <div class="tabs" id="tabs"><button data-t="conn" class="on">اتصال</button><button data-t="loc">موقعیت</button><button data-t="an">تحلیل و قوانین</button><button data-t="zones">نواحی و کالیبراسیون سرعت</button></div>
    <div data-p="conn" class="grid g2"><div class="card"><div class="form-grid" id="f-conn">
      <label class="f full">نام دوربین<input class="input" name="name" value="${esc(c.name || '')}" placeholder="مثلا: چهارراه ولیعصر - ورودی شمالی"></label>
      <label class="f">برند / نوع منبع<select class="input" name="vendor">${options(state.meta.vendors, c.vendor)}</select></label>
      <label class="f">جریان تصویر<select class="input" name="stream">${options({ main: 'اصلی (کیفیت بالا - توصیه‌شده برای پلاک)', sub: 'فرعی (کم‌حجم)' }, c.stream)}</select></label>
      <label class="f" data-v="net">آدرس IP / میزبان<input class="input ltr" name="host" value="${esc(c.host || '')}" placeholder="192.168.1.64"></label>
      <label class="f" data-v="net">پورت<input class="input" name="port" type="number" value="${c.port ?? ''}" placeholder="554 (ONVIF: 80)"></label>
      <label class="f" data-v="net">نام کاربری<input class="input ltr" name="username" value="${esc(c.username || '')}" autocomplete="off"></label>
      <label class="f" data-v="net">رمز عبور<input class="input ltr" name="password" type="password" placeholder="${c.has_password ? '•••• (بدون تغییر)' : ''}" autocomplete="new-password"></label>
      <label class="f" data-v="net">کانال<input class="input" name="channel" type="number" value="${c.channel ?? 1}"></label>
      <label class="f full">آدرس مستقیم استریم (اختیاری — جایگزین قالب برند)<input class="input ltr" name="url" value="${esc(c.url || '')}" placeholder="rtsp://user:pass@ip:554/... یا مسیر فایل ویدیو"></label>
      <div class="full" data-v="file"><label class="btn">${icon('upload')} بارگذاری ویدیوی آزمایشی<input type="file" id="vid" accept="video/*" hidden></label> <span class="small muted" id="vids"></span></div>
      <label class="check full"><span class="switch"><input type="checkbox" name="enabled" ${c.enabled ? 'checked' : ''}><span></span></span> دوربین فعال باشد و پردازش شود</label>
    </div></div>
    <div class="card"><div class="card-h"><h3>پیش‌نمایش</h3></div><div id="prev" class="muted small">برای مشاهده تصویر «تست اتصال» را بزنید.</div>
      <div class="help" style="margin-top:14px">قالب آدرس‌ها به صورت خودکار ساخته می‌شود: <b>Axis</b> (axis-media/media.amp)، <b>Hikvision</b>، <b>Dahua</b>، <b>Uniview</b>، <b>Hanwha</b>، <b>Bosch</b>، <b>Vivotek</b>،
        <b>Milesight</b> و <b>Tiandy</b>. برای سایر برندها <b>ONVIF</b> را انتخاب کنید تا آدرس استریم از خود دوربین دریافت شود، یا آدرس RTSP را مستقیم وارد کنید.
        برای پلاک‌خوانی دقیق، دوربین با زاویه کمتر از ۳۰ درجه و عرض پلاک حداقل ۱۲۰ پیکسل توصیه می‌شود.</div></div></div>

    <div data-p="loc" class="grid g-1-2 hidden"><div class="card"><div class="form-grid" id="f-loc">
      <label class="f full">منطقه شهر<select class="input" name="district_id">${options(Object.fromEntries(dists.map(d => [d.id, d.name])), c.district_id, '— بدون منطقه —')}</select></label>
      <label class="f full">نشانی<input class="input" name="address" value="${esc(c.address || '')}"></label>
      <label class="f">عرض جغرافیایی<input class="input ltr" name="lat" type="number" step="any" value="${c.lat ?? ''}"></label>
      <label class="f">طول جغرافیایی<input class="input ltr" name="lng" type="number" step="any" value="${c.lng ?? ''}"></label>
      <label class="f">جهت دید<input class="input" name="direction" value="${esc(c.direction || '')}" placeholder="شمال به جنوب"></label>
      <label class="f">کاربری<select class="input" name="purpose">${options({ traffic: 'پایش تردد', entrance: 'ورودی محدوده طرح', parking: 'پایش پارک حاشیه‌ای', mixed: 'ترکیبی' }, c.purpose)}</select></label>
      <p class="small muted full">روی نقشه کلیک کنید تا موقعیت دوربین ثبت شود.</p></div></div>
      <div class="card flush" style="min-height:420px"><div id="lm" class="map" style="height:100%;border-radius:0"></div></div></div>

    <div data-p="an" class="grid g2 hidden"><div class="card"><div class="form-grid" id="f-an">
      <label class="f">حداکثر سرعت مجاز (km/h)<input class="input" name="speed_limit" type="number" value="${c.speed_limit ?? ''}" placeholder="پیش‌فرض: سرعت منطقه"></label>
      <label class="f">روش پلاک‌خوانی<select class="input" name="plate_mode">${options({ vehicle: 'روی هر خودرو (دوربین شهری / دید باز)', frame: 'کل تصویر (دوربین پلاک‌خوان نزدیک)' }, a.plate_mode)}</select></label>
      <label class="f">حداقل توقف برای «پارک حاشیه‌ای» (ثانیه)<input class="input" name="park_seconds" type="number" value="${a.park_seconds}"></label>
      <label class="f">حداقل توقف در «توقف ممنوع» (ثانیه)<input class="input" name="no_parking_seconds" type="number" value="${a.no_parking_seconds}"></label>
      <label class="f">حداقل توقف برای «پارک دوبل» (ثانیه)<input class="input" name="double_parking_seconds" type="number" value="${a.double_parking_seconds}"></label>
      <label class="f">اندازه ورودی مدل<select class="input" name="imgsz">${options({ 640: '۶۴۰ (سریع)', 960: '۹۶۰ (متعادل)', 1280: '۱۲۸۰ (دقیق، خودروهای دور)' }, a.imgsz || 640)}</select></label>
      <label class="check full"><span class="switch"><input type="checkbox" name="detect_plates" ${a.detect_plates ? 'checked' : ''}><span></span></span> پلاک‌خوانی فعال باشد</label></div></div>
      <div class="help">قوانین محدودیت تردد (ساعت، روز، نوع خودرو، بار، زوج و فرد، طرح ترافیک) در صفحه <a href="#/rules">قوانین تردد</a> برای منطقه‌ها تعریف می‌شوند
        و روی همه دوربین‌های آن منطقه اعمال می‌شوند. تخلف سرعت بر اساس حداکثر سرعت همین دوربین یا منطقه آن ثبت می‌شود و نیاز به کالیبراسیون سرعت دارد.</div></div>

    <div data-p="zones" class="grid g-2-1 hidden">
      <div class="card"><div class="card-h"><h3>ترسیم روی تصویر</h3><div class="actions"><button class="btn sm" id="snap">${icon('refresh')} دریافت تصویر</button></div></div>
        <div class="editor-wrap" id="ed"><div class="empty">ابتدا «دریافت تصویر» را بزنید</div></div>
        <div class="small muted" style="margin-top:10px" id="hint">یک ابزار را از سمت چپ انتخاب کنید.</div></div>
      <div class="card"><div class="card-h"><h3>نواحی</h3></div>
        <div class="form-grid"><label class="f">نوع ناحیه<select class="input" id="zt">${options(state.meta.zone_types, 'curb_parking')}</select></label>
          <label class="f">نام<input class="input" id="zn" placeholder="مثلا حاشیه شرقی"></label></div>
        <div style="display:flex;gap:8px;margin:10px 0"><button class="btn sm primary" id="znew">${icon('plus')} رسم ناحیه جدید</button><button class="btn sm" id="zdone">پایان رسم</button></div>
        <div class="zone-list" id="zl"></div>
        <div class="card-h" style="margin-top:22px"><h3>کالیبراسیون سرعت</h3></div>
        <p class="small muted" style="line-height:1.9;margin-top:0">دو خط عرضی روی جاده رسم کنید و فاصله واقعی آن‌ها را (با متر یا خط‌کشی‌های جاده) وارد کنید. سرعت = فاصله ÷ زمان عبور بین دو خط.</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn sm" id="la" style="border-color:#facc15">خط A</button><button class="btn sm" id="lb" style="border-color:#e879f9">خط B</button>
          <button class="btn sm ghost" id="lclr">پاک کردن</button></div>
        <label class="f" style="margin-top:10px">فاصله دو خط (متر)<input class="input" type="number" step="0.1" id="dist" value="${calib.distance_m ?? ''}"></label></div></div>`;

  // tabs
  el.querySelectorAll('#tabs button').forEach(b => b.onclick = () => {
    el.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('on', x === b));
    el.querySelectorAll('[data-p]').forEach(p => p.classList.toggle('hidden', p.dataset.p !== b.dataset.t));
    if (b.dataset.t === 'loc') setTimeout(() => lmap.invalidateSize(), 50);
    if (b.dataset.t === 'zones' && !snapshot && !isNew) loadSnap();
  });
  const vendorSel = el.querySelector('[name=vendor]');
  const syncVendor = () => {
    const v = vendorSel.value;
    el.querySelectorAll('[data-v=net]').forEach(x => x.classList.toggle('hidden', ['file', 'usb', 'http_mjpeg', 'rtsp'].includes(v) && v !== 'rtsp'));
    el.querySelector('[data-v=file]').classList.toggle('hidden', v !== 'file');
  };
  vendorSel.onchange = syncVendor; syncVendor();
  el.querySelector('#vid').onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    $('#vids', el).textContent = 'در حال بارگذاری…';
    const fd = new FormData(); fd.append('file', f);
    try { const r = await api('/api/cameras/upload-video', { method: 'POST', body: fd }); el.querySelector('[name=url]').value = r.path; $('#vids', el).textContent = 'بارگذاری شد'; }
    catch (err) { $('#vids', el).textContent = err.message; }
  };

  // location map
  const lmap = baseMap($('#lm', el));
  let marker = null;
  const setMarker = (lat, lng) => { if (marker) marker.setLatLng([lat, lng]); else marker = L.marker([lat, lng]).addTo(lmap); };
  if (c.lat != null) { setMarker(c.lat, c.lng); lmap.setView([c.lat, c.lng], 15); }
  lmap.on('click', (e) => { setMarker(e.latlng.lat, e.latlng.lng); el.querySelector('[name=lat]').value = e.latlng.lat.toFixed(6); el.querySelector('[name=lng]').value = e.latlng.lng.toFixed(6); });

  // test connection
  const connPayload = () => ({ ...formData($('#f-conn', el)), id: isNew ? undefined : c.id });
  $('#test', el).onclick = async () => {
    $('#prev', el).innerHTML = '<span class="spinner"></span> در حال اتصال…';
    try {
      const r = await post('/api/cameras/test', connPayload());
      if (!r.ok) { $('#prev', el).innerHTML = `<span class="badge bad">اتصال ناموفق</span><p class="small">${esc(r.error)}</p>`; return; }
      $('#prev', el).innerHTML = `<img src="${r.image}" style="width:100%;border-radius:10px" alt=""><div class="small muted ltr" style="margin-top:6px">${esc(r.url)} — ${fa(r.width)}×${fa(r.height)}</div>`;
      snapshot = r.image; drawEditor();
    } catch (err) { $('#prev', el).innerHTML = `<span class="badge bad">${esc(err.message)}</span>`; }
  };

  // ---------------- zone editor
  let mode = null; // {type:'zone', idx} | {type:'line', key}
  let selected = -1;
  async function loadSnap() {
    $('#ed', el).innerHTML = '<div class="loading"><span class="spinner"></span></div>';
    try {
      const res = await fetch(`/api/cameras/${c.id}/snapshot?raw=1&t=${Date.now()}`, { headers: { Authorization: 'Bearer ' + state.token } });
      if (!res.ok) throw new Error((await res.json()).detail);
      snapshot = URL.createObjectURL(await res.blob());
      drawEditor();
    } catch (e) { $('#ed', el).innerHTML = `<div class="empty">${esc(e.message)}<br>از تب «اتصال» تست اتصال بگیرید.</div>`; }
  }
  $('#snap', el).onclick = () => isNew ? $('#test', el).click() : loadSnap();

  function drawEditor() {
    if (!snapshot) return;
    const wrap = $('#ed', el);
    if (!wrap.querySelector('img')) {
      wrap.innerHTML = `<div class="stage"><img alt=""><svg class="overlay"></svg></div>`;
      const img = wrap.querySelector('img');
      img.onload = () => paint();
      img.src = snapshot;
      wrap.querySelector('svg').addEventListener('click', onCanvasClick);
      wrap.querySelector('svg').addEventListener('dblclick', (e) => { e.preventDefault(); mode = null; paint(); });
    } else { wrap.querySelector('img').src = snapshot; }
    paint();
  }
  function onCanvasClick(e) {
    if (!mode) return;
    const r = e.currentTarget.getBoundingClientRect();
    const pt = [+((e.clientX - r.left) / r.width).toFixed(4), +((e.clientY - r.top) / r.height).toFixed(4)];
    if (mode.type === 'zone') zones[mode.idx].points.push(pt);
    else {
      calib[mode.key] = (calib[mode.key] || []).length >= 2 ? [pt] : [...(calib[mode.key] || []), pt];
      if (calib[mode.key].length === 2) mode = null;
    }
    paint();
  }
  function paint() {
    const svg = $('#ed svg', el), img = $('#ed img', el);
    if (!svg || !img || !img.naturalWidth) { renderZoneList(); return; }
    const W = img.naturalWidth, H = img.naturalHeight;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('preserveAspectRatio', 'none');
    const sw = W / 300;
    let s = '';
    zones.forEach((z, i) => {
      const col = ZONE_COLORS[z.type] || '#fff';
      const pts = z.points.map(p => `${p[0] * W},${p[1] * H}`).join(' ');
      s += `<polygon points="${pts}" fill="${col}" fill-opacity="${i === selected ? .35 : .2}" stroke="${col}" stroke-width="${sw}"/>`;
      z.points.forEach(p => s += `<circle cx="${p[0] * W}" cy="${p[1] * H}" r="${sw * 1.6}" fill="#fff" stroke="${col}" stroke-width="${sw * .6}"/>`);
      if (z.points.length) s += `<text x="${z.points[0][0] * W + sw * 2}" y="${z.points[0][1] * H - sw * 2}" fill="#fff" font-size="${sw * 7}" font-family="Vazirmatn" style="paint-order:stroke" stroke="#000" stroke-width="${sw}">${esc(z.name)}</text>`;
    });
    [['line_a', '#facc15', 'A'], ['line_b', '#e879f9', 'B']].forEach(([k, col, lab]) => {
      const l = calib[k] || [];
      l.forEach(p => s += `<circle cx="${p[0] * W}" cy="${p[1] * H}" r="${sw * 1.8}" fill="${col}"/>`);
      if (l.length === 2) s += `<line x1="${l[0][0] * W}" y1="${l[0][1] * H}" x2="${l[1][0] * W}" y2="${l[1][1] * H}" stroke="${col}" stroke-width="${sw * 1.2}"/><text x="${l[1][0] * W + sw * 2}" y="${l[1][1] * H}" fill="${col}" font-size="${sw * 9}" font-weight="700">${lab}</text>`;
    });
    svg.innerHTML = s;
    $('#hint', el).textContent = mode ? (mode.type === 'zone' ? 'روی تصویر کلیک کنید تا رئوس ناحیه اضافه شوند؛ برای پایان «پایان رسم» یا دوبار کلیک.' : 'دو نقطه ابتدا و انتهای خط را روی جاده کلیک کنید.') : 'یک ابزار را انتخاب کنید.';
    renderZoneList();
  }
  function renderZoneList() {
    $('#zl', el).innerHTML = zones.length ? zones.map((z, i) => `<div class="zone-row ${i === selected ? 'sel' : ''}" data-i="${i}"><span class="swatch" style="background:${ZONE_COLORS[z.type]}"></span>
      <span style="flex:1;cursor:pointer" data-sel><b>${esc(z.name)}</b> <span class="small muted">${esc(state.meta.zone_types[z.type])} · ${fa(z.points.length)} نقطه</span></span>
      <button class="btn sm ghost" data-rm>${icon('trash')}</button></div>`).join('') : '<div class="small muted">ناحیه‌ای رسم نشده است.</div>';
    el.querySelectorAll('#zl [data-rm]').forEach(b => b.onclick = () => { zones.splice(+b.closest('[data-i]').dataset.i, 1); selected = -1; mode = null; paint(); });
    el.querySelectorAll('#zl [data-sel]').forEach(b => b.onclick = () => { selected = +b.closest('[data-i]').dataset.i; paint(); });
  }
  $('#znew', el).onclick = () => {
    const type = $('#zt', el).value;
    const name = $('#zn', el).value.trim() || `${state.meta.zone_types[type]} ${fa(zones.length + 1)}`;
    if (zones.some(z => z.name === name)) return toast('نام ناحیه تکراری است', 'bad');
    zones.push({ name, type, points: [] }); selected = zones.length - 1; mode = { type: 'zone', idx: selected }; $('#zn', el).value = ''; paint();
  };
  $('#zdone', el).onclick = () => {
    if (mode?.type === 'zone' && zones[mode.idx].points.length < 3) { zones.splice(mode.idx, 1); toast('ناحیه باید حداقل ۳ نقطه داشته باشد', 'warn'); }
    mode = null; paint();
  };
  $('#la', el).onclick = () => { calib.line_a = []; mode = { type: 'line', key: 'line_a' }; paint(); };
  $('#lb', el).onclick = () => { calib.line_b = []; mode = { type: 'line', key: 'line_b' }; paint(); };
  $('#lclr', el).onclick = () => { delete calib.line_a; delete calib.line_b; paint(); };
  renderZoneList();

  // save
  $('#save', el).onclick = async () => {
    const conn = formData($('#f-conn', el));
    const loc = formData($('#f-loc', el));
    const an = formData($('#f-an', el));
    const payload = { ...conn, ...loc, speed_limit: an.speed_limit,
      district_id: loc.district_id ? +loc.district_id : null,
      zones: zones.filter(z => z.points.length >= 3),
      speed_calibration: { ...calib, distance_m: +$('#dist', el).value || null, mode: 'lines' },
      analytics: { ...a, detect_plates: an.detect_plates, plate_mode: an.plate_mode, park_seconds: an.park_seconds, no_parking_seconds: an.no_parking_seconds,
        double_parking_seconds: an.double_parking_seconds, imgsz: +an.imgsz } };
    if (!payload.name) return toast('نام دوربین را وارد کنید', 'bad');
    if (!payload.password) delete payload.password;
    try {
      const r = isNew ? await post('/api/cameras', payload) : await put('/api/cameras/' + c.id, payload);
      toast('ذخیره شد؛ پردازش با تنظیمات جدید آغاز می‌شود', 'ok');
      location.hash = '#/cameras/' + r.id;
      if (!isNew) render(el, [String(r.id)]);
    } catch (e) { toast(e.message, 'bad'); }
  };
  return () => lmap.remove();
}
