document.getElementById('selectAll').addEventListener('change', function() {
  document.querySelectorAll('.app-checkbox').forEach(cb => cb.checked = this.checked);
});
