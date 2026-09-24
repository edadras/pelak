import { $, confirmBox, del, esc, fdt, formData, get, icon, modal, options, post, put, state, toast } from '../core.js';

const ROLES = { admin: 'مدیر سیستم', operator: 'اپراتور', viewer: 'ناظر (فقط مشاهده)' };

export async function render(el) {
  const users = await get('/api/users');
  el.innerHTML = `<div class="section-title"><div class="small muted">مدیر: دسترسی کامل · اپراتور: بررسی تخلفات، مجوزها و فهرست پیگیری · ناظر: فقط مشاهده</div>
    <div class="actions"><button class="btn primary" id="add">${icon('plus')} کاربر جدید</button></div></div>
    <div class="card flush"><table class="t"><thead><tr><th>نام کاربری</th><th>نام</th><th>نقش</th><th>وضعیت</th><th>آخرین ورود</th><th></th></tr></thead><tbody>
    ${users.map(u => `<tr data-id="${u.id}"><td class="ltr">${esc(u.username)}</td><td>${esc(u.full_name)}</td><td>${ROLES[u.role]}</td>
      <td>${u.is_active ? '<span class="badge ok">فعال</span>' : '<span class="badge">غیرفعال</span>'}</td><td class="num small">${fdt(u.last_login)}</td>
      <td class="nowrap"><button class="btn sm" data-edit>${icon('edit')}</button> ${u.id !== state.user.id ? `<button class="btn sm danger" data-del>${icon('trash')}</button>` : ''}</td></tr>`).join('')}</tbody></table></div>`;
  const reload = () => render(el);
  const edit = (u) => {
    const m = modal({ title: u.id ? 'ویرایش کاربر' : 'کاربر جدید', body: `<div class="form-grid" id="f">
      <label class="f">نام کاربری<input class="input ltr" name="username" value="${esc(u.username || '')}" ${u.id ? 'disabled' : ''}></label>
      <label class="f">نام و نام خانوادگی<input class="input" name="full_name" value="${esc(u.full_name || '')}"></label>
      <label class="f">نقش<select class="input" name="role">${options(ROLES, u.role)}</select></label>
      <label class="f">${u.id ? 'رمز جدید (اختیاری)' : 'رمز عبور'}<input class="input" type="password" name="password" autocomplete="new-password"></label>
      <label class="check"><input type="checkbox" name="is_active" ${u.is_active !== false ? 'checked' : ''}> فعال</label></div>`,
      footer: `<button class="btn primary" id="sv">ذخیره</button><button class="btn" data-close>انصراف</button>` });
    m.$('#sv').onclick = async () => {
      const d = formData(m.$('#f'));
      try { u.id ? await put('/api/users/' + u.id, d) : await post('/api/users', d); toast('ذخیره شد', 'ok'); m.close(); reload(); } catch (e) { toast(e.message, 'bad'); }
    };
  };
  $('#add', el).onclick = () => edit({ role: 'operator' });
  el.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => edit(users.find(u => u.id === +b.closest('tr').dataset.id)));
  el.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => { if (await confirmBox('کاربر حذف شود؟')) { await del('/api/users/' + b.closest('tr').dataset.id); reload(); } });
}
