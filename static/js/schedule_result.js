function applyFilters() {
  const tv = document.getElementById('teacherFilter').value;
  const rv = document.getElementById('roomFilter').value;
  document.querySelectorAll('.course-card').forEach(card => {
    const show = (!tv || card.dataset.teacher === tv) && (!rv || card.dataset.room === rv);
    card.style.display = show ? '' : 'none';
  });
}

function showCourseDetails(name, teacher, room, time) {
  document.getElementById('detailName').textContent = name;
  document.getElementById('detailTeacher').textContent = teacher;
  document.getElementById('detailRoom').textContent = room;
  document.getElementById('detailTime').textContent = time;
  new bootstrap.Modal(document.getElementById('courseDetailModal')).show();
}

document.getElementById('analysisModal').addEventListener('shown.bs.modal', function () {
  const roomUsageMap = {}, dayDistMap = {};
  scheduleData.forEach(item => {
    roomUsageMap[item.room] = (roomUsageMap[item.room] || 0) + 1;
    const dn = dayNamesMap[item.day] || item.day;
    dayDistMap[dn] = (dayDistMap[dn] || 0) + 1;
  });

  const baseOpts = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: { y: { beginAtZero: true, ticks: { precision: 0 }, grid: { borderDash: [5,5] } },
               x: { grid: { display: false } } }
  };

  const ctxRoom = document.getElementById('roomUtilChart');
  if (ctxRoom && !Chart.getChart(ctxRoom)) {
    const keys = Object.keys(roomUsageMap).sort();
    new Chart(ctxRoom, { type: 'bar', data: {
      labels: keys,
      datasets: [{ label: '占用节次', data: keys.map(k => roomUsageMap[k]), backgroundColor: '#11cdef', borderRadius: 4 }]
    }, options: baseOpts });
  }

  const ctxDay = document.getElementById('dayDistChart');
  if (ctxDay && !Chart.getChart(ctxDay)) {
    const order = ['星期一','星期二','星期三','星期四','星期五'];
    new Chart(ctxDay, { type: 'bar', data: {
      labels: order,
      datasets: [{ label: '课程总数', data: order.map(d => dayDistMap[d]||0), backgroundColor: '#fb6340', borderRadius: 6, barThickness: 40 }]
    }, options: baseOpts });
  }
});
