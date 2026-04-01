let pollInterval, evolutionChart, lastGen = 0;

function initEvolutionChart() {
  if (evolutionChart) evolutionChart.destroy();
  evolutionChart = new Chart(document.getElementById('evolutionChart'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'f₁ 硬冲突数', data: [], borderColor: '#f5365c', backgroundColor: 'rgba(245,54,92,.08)', yAxisID: 'y', tension: 0.4, fill: true, pointRadius: 0, borderWidth: 2 },
        { label: 'f₂ 教师负载方差', data: [], borderColor: '#2dce89', backgroundColor: 'rgba(45,206,137,.08)', yAxisID: 'y1', tension: 0.4, fill: false, pointRadius: 0, borderWidth: 1.5, borderDash: [4,3] },
        { label: 'f₃ 时间分布方差', data: [], borderColor: '#fb6340', backgroundColor: 'rgba(251,99,64,.08)', yAxisID: 'y1', tension: 0.4, fill: false, pointRadius: 0, borderWidth: 1.5, borderDash: [2,3] }
      ]
    },
    options: {
      responsive: true, animation: { duration: 0 },
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { font: { size: 10 }, boxWidth: 20 } } },
      scales: {
        x: { display: true, grid: { display: false } },
        y:  { type: 'linear', position: 'left',  beginAtZero: true, title: { display: true, text: '硬冲突', font: { size: 10 } }, grid: { borderDash: [4,4] } },
        y1: { type: 'linear', position: 'right', beginAtZero: true, title: { display: true, text: '方差', font: { size: 10 } }, grid: { drawOnChartArea: false } }
      }
    }
  });
}

function handleFileSelect(input) {
  if (input.files[0]) uploadFile(input.files[0]);
}

const dropZone = document.getElementById('dropZone');
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]);
});

function uploadFile(file) {
  document.getElementById('uploadText').innerHTML = '<i class="bi bi-arrow-repeat fs-2 text-primary spin"></i><p class="mb-0 mt-1 small">上传中...</p>';
  const fd = new FormData();
  fd.append('file', file);
  fetch('/api/upload', { method: 'POST', body: fd })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        showToast(data.error, 'danger');
        document.getElementById('uploadText').innerHTML = '<i class="bi bi-cloud-upload fs-2 text-primary"></i><p class="mb-0 mt-1 small fw-600">点击上传 XML 文件</p>';
      } else {
        document.getElementById('uploadText').classList.add('d-none');
        document.getElementById('fileInfo').classList.remove('d-none');
        document.getElementById('fileName').textContent = data.filename;
        document.getElementById('startBtn').disabled = false;
      }
    });
}

function getParams() {
  return {
    init_strategy:   document.getElementById('initStrategy').value,
    population_size: +document.getElementById('popSize').value,
    generations:     +document.getElementById('generations').value,
    crossover_rate:  +document.getElementById('crossoverRate').value,
    mutation_rate:   +document.getElementById('mutationRate').value,
    elite_size:      +document.getElementById('eliteSize').value
  };
}

function startOptimization(isContinue = false) {
  const params = getParams();
  if (isContinue) {
    params.continue_optimization = true;
    params.generations = 100;
    document.getElementById('continueBtn').classList.add('d-none');
  } else {
    document.getElementById('successMessage').classList.add('d-none');
    document.getElementById('continueBtn').classList.add('d-none');
    initEvolutionChart();
    lastGen = 0;
  }
  document.getElementById('startBtn').classList.add('d-none');
  document.getElementById('stopBtn').classList.remove('d-none');
  document.getElementById('statusBadge').className = 'badge bg-primary';
  document.getElementById('statusBadge').textContent = '进化中';

  fetch('/api/start_optimization', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params)
  }).then(r => r.json()).then(data => {
    if (data.status === 'started') pollInterval = setInterval(pollProgress, 600);
  });
}

function continueOptimization() { startOptimization(true); }

function stopOptimization() {
  fetch('/api/stop', { method: 'POST' });
}

function pollProgress() {
  fetch('/api/progress').then(r => r.json()).then(data => {
    const bar = document.getElementById('progressBar');
    bar.style.width = data.progress_percent + '%';
    bar.textContent = data.progress_percent + '%';
    document.getElementById('genCount').textContent = data.generation;
    document.getElementById('hardCount').textContent = data.hard_conflicts;
    document.getElementById('softScore').textContent = parseFloat(data.f2 || 0).toFixed(2);

    const statusLabels = { 'RUNNING':'进化中', 'COMPLETED':'已收敛', 'STOPPED':'已停止', 'IDLE':'待机' };
    document.getElementById('statusBadge').textContent = statusLabels[data.status] || data.status;

    if (data.history && evolutionChart) {
      evolutionChart.data.labels = data.history.map(h => h.gen);
      evolutionChart.data.datasets[0].data = data.history.map(h => h.hard);
      evolutionChart.data.datasets[1].data = data.history.map(h => h.f2 || 0);
      evolutionChart.data.datasets[2].data = data.history.map(h => h.f3 || 0);
      evolutionChart.update();
    }

    if (data.status === 'COMPLETED' || data.status === 'STOPPED') {
      clearInterval(pollInterval);
      document.getElementById('startBtn').classList.remove('d-none');
      document.getElementById('stopBtn').classList.add('d-none');
      document.getElementById('statusBadge').className = data.status === 'COMPLETED' ? 'badge bg-success' : 'badge bg-secondary';
      document.getElementById('statusBadge').textContent = data.status === 'COMPLETED' ? '已收敛' : '已停止';
      if (data.status === 'COMPLETED') {
        document.getElementById('successMessage').classList.remove('d-none');
        document.getElementById('continueBtn').classList.remove('d-none');
      }
    }
  });
}
