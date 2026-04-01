function showDetail(el) {
  const statusMap = { pending: '待审核', approved: '已通过', rejected: '已拒绝' };
  const statusColor = { pending: 'warning', approved: 'success', rejected: 'danger' };
  const status = el.dataset.status;
  document.getElementById('appDetailBody').innerHTML = `
    <div class="row g-2">
      <div class="col-6"><small class="text-muted">课程</small><div class="fw-bold">${el.dataset.course}</div></div>
      <div class="col-6"><small class="text-muted">状态</small>
        <div><span class="badge bg-${statusColor[status]}">${statusMap[status]}</span></div>
      </div>
      <div class="col-6"><small class="text-muted">申请时间</small><div>${el.dataset.applied || '-'}</div></div>
      <div class="col-6"><small class="text-muted">审批时间</small><div>${el.dataset.reviewed || '-'}</div></div>
      <div class="col-12"><small class="text-muted">审批意见</small>
        <div>${el.dataset.comment || '无'}</div>
      </div>
    </div>`;
}
