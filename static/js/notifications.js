// 通用通知页面逻辑（教师/学生共用，通过 BASE_URL 区分）
function toggleNotif(id, el) {
  const content = document.getElementById('content-' + id);
  const preview = document.getElementById('preview-' + id);
  const isOpen = content.style.display !== 'none';
  content.style.display = isOpen ? 'none' : 'block';
  preview.style.display = isOpen ? 'block' : 'none';
  const dot = el.querySelector('.notification-dot');
  if (dot) {
    fetch(`${BASE_URL}/notifications/${id}/read`, { method: 'POST' })
      .then(r => r.json())
      .then(() => {
        dot.remove();
        el.classList.remove('bg-light');
        el.querySelector('.fw-semibold')?.classList.remove('text-primary');
      });
  }
}

function markAllRead() {
  fetch(`${BASE_URL}/notifications/read-all`, { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      showToast(data.message, 'success');
      document.querySelectorAll('.notification-dot').forEach(d => d.remove());
      document.querySelectorAll('.notif-item').forEach(el => {
        el.classList.remove('bg-light');
        el.querySelector('.fw-semibold')?.classList.remove('text-primary');
      });
    });
}

function deleteNotif(id) {
  fetch(`${BASE_URL}/notifications/${id}`, { method: 'DELETE' })
    .then(r => r.json())
    .then(data => {
      if (data.code === 0) {
        const el = document.getElementById('notif-' + id);
        el.style.transition = 'opacity .3s';
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 300);
        showToast('已删除', 'success');
      }
    });
}
