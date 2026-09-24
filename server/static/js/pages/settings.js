import { $, ago, can, esc, fa, formData, get, icon, num, put, toast } from '../core.js';

export async function render(el) {
  const [s, sys] = await Promise.all([get('/api/settings'), get('/api/system')]);
  el.innerHTML = `<div class="grid g2">
    <div class="card"><div class="card-h"><h3>تنظیمات تشخیص</h3></div><div class="form-grid" id="f">
      <label class="f">تلورانس سرعت (km/h)<input class="input" type="number" name="speed_tolerance" value="${s.speed_tolerance}"></label>
      <label class="f">حداقل اطمینان پلاک برای ثبت (۰ تا ۱)<input class="input" type="number" step="0.05" min="0" max="1" name="min_plate_conf" value="${s.min_plate_conf}"></label>
      <label class="f">مدت نگهداری داده‌ها (روز، ۰ = همیشه)<input class="input" type="number" name="retention_days" value="${s.retention_days}"></label></div>
      ${can('admin') ? `<button class="btn primary" id="sv" style="margin-top:16px">${icon('check')} ذخیره</button>` : ''}</div>
    <div class="card"><div class="card-h"><h3>وضعیت سامانه</h3><div class="actions"><button class="btn sm" id="rf">${icon('refresh')}</button></div></div>
      <dl class="kv"><dt>پایگاه داده</dt><dd class="ltr">${esc(sys.database)}</dd><dt>گذرگاه رویداد</dt><dd>${sys.bus === 'redis' ? 'Redis (چندسروره)' : 'داخلی (تک‌سرور)'}</dd>
        <dt>دوربین‌ها</dt><dd>${fa(sys.cameras.enabled)} فعال از ${fa(sys.cameras.total)}${sys.cameras.unassigned ? ` — <span style="color:var(--warn)">${fa(sys.cameras.unassigned)} بدون سرور پردازش</span>` : ''}</dd>
        <dt>ظرفیت پردازش</dt><dd>${fa(sys.capacity)} دوربین</dd>
        ${sys.disk ? `<dt>فضای ذخیره‌سازی</dt><dd>${num(sys.disk.free_gb, 1)} گیگابایت آزاد از ${num(sys.disk.total_gb, 1)} (${fa(sys.disk.used_percent)}٪ مصرف)</dd>` : ''}</dl></div></div>
    <div class="card flush" style="margin-top:16px"><div class="card-h"><h3>سرورهای پردازش تصویر</h3></div>
      <table class="t" style="margin-top:12px"><thead><tr><th>شناسه</th><th>میزبان</th><th>پردازنده</th><th>دوربین / ظرفیت</th><th>CPU</th><th>حافظه</th><th>آخرین گزارش</th><th>وضعیت</th></tr></thead><tbody>
      ${sys.workers.map(w => `<tr><td class="ltr">${esc(w.id)}</td><td class="ltr">${esc(w.host)}</td><td>${w.device.startsWith('cuda') ? '<span class="badge accent">GPU</span>' : '<span class="badge">CPU</span>'}</td>
        <td class="num">${fa(w.cameras)} / ${fa(w.capacity)}</td><td class="num">${num(w.cpu)}٪</td><td class="num">${num(w.memory)}٪</td><td class="small">${ago(w.last_heartbeat)}</td>
        <td>${w.alive ? '<span class="badge ok">فعال</span>' : '<span class="badge bad">قطع</span>'}</td></tr>`).join('') || '<tr><td colspan="8" class="muted">هیچ سرور پردازشی متصل نیست. سرویس worker را اجرا کنید.</td></tr>'}</tbody></table></div>
    <div class="help" style="margin-top:16px">مستندات کامل API در <a href="/api/docs" target="_blank">/api/docs</a> در دسترس است و می‌توان سامانه را به سامانه‌های دیگر (پلیس راهور، شهرداری، سامانه جریمه) متصل کرد.</div>`;
  $('#sv', el)?.addEventListener('click', async () => { try { await put('/api/settings', formData($('#f', el))); toast('ذخیره شد', 'ok'); } catch (e) { toast(e.message, 'bad'); } });
  $('#rf', el).onclick = () => render(el);
}
