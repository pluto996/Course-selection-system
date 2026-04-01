function showToast(message, type = 'success') {
  const icons = { success:'check-circle-fill', danger:'exclamation-circle-fill',
                  warning:'exclamation-triangle-fill', info:'info-circle-fill' };
  const id = 'toast-' + Date.now();
  document.getElementById('toast-container').insertAdjacentHTML('beforeend', `
    <div id="${id}" class="toast align-items-center text-bg-${type} border-0" role="alert">
      <div class="d-flex">
        <div class="toast-body">
          <i class="bi bi-${icons[type]||'info-circle-fill'} me-2"></i>${message}
        </div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
      </div>
    </div>`);
  const el = document.getElementById(id);
  const t = new bootstrap.Toast(el, { delay: 3000 });
  t.show();
  el.addEventListener('hidden.bs.toast', () => el.remove());
}

function confirmAction(message, callback, title = '确认操作') {
  document.getElementById('confirmModalTitle').textContent = title;
  document.getElementById('confirmModalBody').textContent = message;
  const modal = new bootstrap.Modal(document.getElementById('confirmModal'));
  const okBtn = document.getElementById('confirmModalOk');
  const handler = () => { modal.hide(); okBtn.removeEventListener('click', handler); callback(); };
  okBtn.addEventListener('click', handler);
  modal.show();
}

document.addEventListener('DOMContentLoaded', function() {
  const origFetch = window.fetch;
  window.fetch = function(...args) {
    return origFetch.apply(this, args).then(r => {
      if (r.status === 401) window.location.href = '/auth/login';
      else if (r.status === 403) showToast('权限不足，无法执行此操作', 'danger');
      else if (r.status === 500) showToast('服务器错误，请稍后重试', 'danger');
      return r;
    });
  };
});
