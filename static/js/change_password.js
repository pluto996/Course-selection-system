// 密码强度检测（公共函数，供 users.js 复用）
function checkPwdStrength(value, barEl, textEl) {
  let score = 0;
  if (value.length >= 8) score++;
  if (/[a-zA-Z]/.test(value)) score++;
  if (/\d/.test(value)) score++;
  if (/[^a-zA-Z0-9]/.test(value)) score++;
  const colors = ['bg-danger', 'bg-warning', 'bg-info', 'bg-success'];
  const labels = ['弱', '中', '强', '很强'];
  barEl.className = 'strength-bar ' + (colors[score - 1] || 'bg-secondary');
  barEl.style.width = (score * 25) + '%';
  textEl.textContent = score > 0 ? '密码强度：' + labels[score - 1] : '';
}

const newPwd = document.getElementById('newPwd');
const confirmPwd = document.getElementById('confirmPwd');
const bar = document.getElementById('strengthBar');
const txt = document.getElementById('strengthText');

newPwd.addEventListener('input', function() {
  checkPwdStrength(this.value, bar, txt);
});

confirmPwd.addEventListener('blur', function() {
  if (this.value !== newPwd.value) {
    this.classList.add('is-invalid');
  } else {
    this.classList.remove('is-invalid');
    this.classList.add('is-valid');
  }
});
