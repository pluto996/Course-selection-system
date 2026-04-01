// 通用个人中心逻辑（管理员/教师/学生共用，通过 PROFILE_URL 区分）
function saveDisplayName() {
  const name = document.getElementById('displayNameInput').value.trim();
  if (name.length < 2 || name.length > 50) {
    showToast('显示名称长度需在2-50字符之间', 'warning');
    return;
  }
  fetch(PROFILE_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_name: name })
  }).then(r => r.json()).then(data => {
    showToast(data.message, data.code === 0 ? 'success' : 'danger');
  });
}

const avatarInput = document.getElementById('avatarInput');
if (avatarInput) {
  avatarInput.addEventListener('change', function() {
    if (!this.files[0]) return;
    const spinner = document.getElementById('avatarSpinner');
    if (spinner) spinner.classList.remove('d-none');
    const fd = new FormData();
    fd.append('avatar', this.files[0]);
    fetch(PROFILE_URL + '/avatar', { method: 'POST', body: fd })
      .then(r => r.json())
      .then(data => {
        if (spinner) spinner.classList.add('d-none');
        if (data.code === 0) {
          showToast('头像上传成功', 'success');
          setTimeout(() => location.reload(), 800);
        } else {
          showToast(data.message, 'danger');
        }
      });
  });
}
