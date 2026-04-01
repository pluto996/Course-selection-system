fetch('/api/viz/capacity')
  .then(r => r.json())
  .then(data => {
    if (!data || data.length === 0) {
      document.getElementById('noDataMsg').classList.remove('d-none');
      document.getElementById('capacityChart').style.display = 'none';
      return;
    }

    const labels = data.map(d => d.room_id);
    const bgColors = data.map(d => d.over_capacity ? 'rgba(220,53,69,0.8)' : 'rgba(25,135,84,0.7)');

    new Chart(document.getElementById('capacityChart'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: '额定容量', data: data.map(d => d.capacity), backgroundColor: 'rgba(13,110,253,0.6)', borderColor: '#0d6efd', borderWidth: 1, borderRadius: 4 },
          { label: '实际使用人数', data: data.map(d => d.actual), backgroundColor: bgColors, borderColor: data.map(d => d.over_capacity ? '#dc3545' : '#198754'), borderWidth: 1, borderRadius: 4 }
        ]
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: 'top' },
          tooltip: { callbacks: { afterBody: (items) => data[items[0].dataIndex].over_capacity ? ['⚠️ 超出容量！'] : [] } }
        },
        scales: { x: { grid: { display: false }, ticks: { maxRotation: 45 } }, y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,.05)' } } }
      }
    });

    const overItems = data.filter(d => d.over_capacity);
    if (overItems.length > 0) {
      document.getElementById('overCapacityCard').style.display = '';
      const tbody = document.getElementById('overCapacityBody');
      overItems.forEach(d => {
        tbody.insertAdjacentHTML('beforeend', `<tr><td><code>${d.room_id}</code></td><td>${d.capacity}</td><td class="text-danger fw-bold">${d.actual}</td><td><span class="badge bg-danger">+${d.actual - d.capacity}</span></td></tr>`);
      });
    }
  })
  .catch(() => {
    document.getElementById('noDataMsg').classList.remove('d-none');
    document.getElementById('capacityChart').style.display = 'none';
  });
