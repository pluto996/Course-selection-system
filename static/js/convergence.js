fetch('/api/viz/convergence')
  .then(r => r.json())
  .then(data => {
    if (!data.generations || data.generations.length === 0) {
      document.getElementById('noDataMsg').classList.remove('d-none');
      document.getElementById('convergenceChart').style.display = 'none';
      return;
    }

    document.getElementById('statGenerations').textContent = data.generations.length;
    document.getElementById('statInitial').textContent = data.conflicts[0] ?? '-';
    document.getElementById('statFinal').textContent   = data.conflicts[data.conflicts.length - 1] ?? '-';
    document.getElementById('statsRow').style.display  = '';

    const datasets = [{
      label: 'f₁ 硬冲突数', data: data.conflicts,
      borderColor: '#f5365c', backgroundColor: 'rgba(245,54,92,.1)',
      fill: true, tension: 0.3,
      pointRadius: data.generations.length > 100 ? 0 : 3,
      borderWidth: 2, yAxisID: 'y'
    }];

    if (data.f2?.length) datasets.push({ label: 'f₂ 教师负载方差', data: data.f2, borderColor: '#2dce89', fill: false, tension: 0.3, pointRadius: 0, borderWidth: 1.5, borderDash: [5,3], yAxisID: 'y1' });
    if (data.f3?.length) datasets.push({ label: 'f₃ 时间分布方差', data: data.f3, borderColor: '#fb6340', fill: false, tension: 0.3, pointRadius: 0, borderWidth: 1.5, borderDash: [2,3], yAxisID: 'y1' });

    new Chart(document.getElementById('convergenceChart'), {
      type: 'line',
      data: { labels: data.generations, datasets },
      options: {
        responsive: true,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'top' }, title: { display: true, text: 'NSGA-II 多目标进化收敛曲线', font: { size: 14 } } },
        scales: {
          x:  { title: { display: true, text: '迭代代数' }, grid: { color: 'rgba(0,0,0,.04)' } },
          y:  { title: { display: true, text: 'f₁ 硬冲突数' }, beginAtZero: true, position: 'left', grid: { color: 'rgba(0,0,0,.04)' } },
          y1: { title: { display: true, text: '方差值' }, beginAtZero: true, position: 'right', grid: { drawOnChartArea: false } }
        }
      }
    });
  })
  .catch(() => {
    document.getElementById('noDataMsg').classList.remove('d-none');
    document.getElementById('convergenceChart').style.display = 'none';
  });
