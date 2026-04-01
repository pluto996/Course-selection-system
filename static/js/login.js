const form = document.getElementById('loginForm');
const usernameInput = document.getElementById('username');
const passwordInput = document.getElementById('password');

function validateField(input) {
  if (!input.value.trim()) {
    input.classList.add('is-invalid');
    input.classList.remove('is-valid');
    return false;
  }
  input.classList.remove('is-invalid');
  input.classList.add('is-valid');
  return true;
}

usernameInput.addEventListener('blur', () => validateField(usernameInput));
passwordInput.addEventListener('blur', () => validateField(passwordInput));

form.addEventListener('submit', function(e) {
  const v1 = validateField(usernameInput);
  const v2 = validateField(passwordInput);
  if (!v1 || !v2) { e.preventDefault(); form.classList.add('was-validated'); }
});

document.getElementById('togglePwd').addEventListener('click', function() {
  const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
  passwordInput.setAttribute('type', type);
  document.getElementById('eyeIcon').className = type === 'password' ? 'bi bi-eye' : 'bi bi-eye-slash';
});
