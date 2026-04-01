function showCourseDetail(courses) {
  let html = '';
  courses.forEach(c => {
    html += `
      <div class="mb-3 p-3 bg-light rounded">
        <div class="fw-bold fs-6 mb-2">${c.course_name}</div>
        <div class="row g-2">
          <div class="col-6"><small class="text-muted">教室</small><div>${c.room}</div></div>
          <div class="col-6"><small class="text-muted">班级人数</small><div>${c.class_size} 人</div></div>
        </div>
      </div>`;
  });
  document.getElementById('courseDetailBody').innerHTML = html;
}
