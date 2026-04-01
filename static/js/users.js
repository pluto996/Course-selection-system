// 密码强度（复用 change_password.js 中的逻辑）
function _pwdStrength(value, fillEl, textEl) {
  let score = 0;
  if (value.length >= 8) score++;
  if (/[a-zA-Z]/.test(value)) score++;
  if (/\d/.test(value)) score++;
  if (/[^a-zA-Z0-9]/.test(value)) score++;
  const colors = ['#dc3545', '#fd7e14', '#0dcaf0', '#198754'];
  const labels = ['弱', '中', '强', '很强'];
  fillEl.style.width = (score * 25) + '%';
  fillEl.style.background = colors[score - 1] || '#dee2e6';
  textEl.textContent = score > 0 ? '强度：' + labels[score - 1] : '';
}

// 新建用户 - 角色切换
document.getElementById('roleSelect').addEventListener('change', function() {
  document.getElementById('teacherSelectGroup').style.display = this.value === 'teacher' ? '' : 'none';
});

// 新建用户 - 密码强度
document.getElementById('newPassword').addEventListener('input', function() {
  _pwdStrength(this.value,
    document.getElementById('pwdStrengthFill'),
    document.getElementById('pwdStrengthText'));
});

// 修改密码 Modal - 密码强度
document.getElementById('adminNewPwd').addEventListener('input', function() {
  _pwdStrength(this.value,
    document.getElementById('adminPwdBar'),
    document.getElementById('adminPwdText'));
});

// ── 用户操作 ──────────────────────────────────────────────────

let _changePwdUserId = null;

function openChangePwd(userId, username) {
  _changePwdUserId = userId;
  document.getElementById('changePwdUsername').textContent = username;
  document.getElementById('adminNewPwd').value = '';
  document.getElementById('adminConfirmPwd').value = '';
  document.getElementById('adminPwdBar').style.width = '0';
  document.getElementById('adminPwdText').textContent = '';
  document.getElementById('adminConfirmPwd').classList.remove('is-invalid', 'is-valid');
  new bootstrap.Modal(document.getElementById('changePwdModal')).show();
}

function submitChangePwd() {
  const pwd = document.getElementById('adminNewPwd').value;
  const confirm = document.getElementById('adminConfirmPwd').value;
  const confirmEl = document.getElementById('adminConfirmPwd');

  if (pwd !== confirm) {
    confirmEl.classList.add('is-invalid');
    return;
  }
  confirmEl.classList.remove('is-invalid');

  fetch(`/admin/users/${_changePwdUserId}/change-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: pwd })
  }).then(r => r.json()).then(data => {
    if (data.code === 0) {
      bootstrap.Modal.getInstance(document.getElementById('changePwdModal')).hide();
      showToast(data.message, 'success');
    } else {
      showToast(data.message, 'danger');
    }
  });
}

function toggleUser(userId, username) {
  confirmAction(`确定要切换用户 "${username}" 的状态吗？`, function() {
    fetch(`/admin/users/${userId}/toggle`, { method: 'POST' })
      .then(r => r.json())
      .then(data => {
        if (data.code === 0) {
          const badge = document.getElementById('status-badge-' + userId);
          const icon = document.getElementById('toggle-icon-' + userId);
          badge.textContent = data.is_active ? '启用' : '停用';
          badge.className = 'badge ' + (data.is_active ? 'bg-success' : 'bg-secondary');
          icon.className = 'bi bi-' + (data.is_active ? 'pause-circle' : 'play-circle');
          showToast(data.message, 'success');
        } else {
          showToast(data.message, 'danger');
        }
      });
  });
}

function deleteUser(userId, username) {
  confirmAction(`确定要永久删除用户 "${username}" 吗？此操作不可撤销。`, function() {
    fetch(`/admin/users/${userId}/delete`, { method: 'POST' })
      .then(r => r.json())
      .then(data => {
        if (data.code === 0) {
          showToast(data.message, 'success');
          document.getElementById('user-row-' + userId)?.remove();
        } else {
          showToast(data.message, 'danger');
        }
      });
  }, '确认删除用户');
}
