const DAYS = ['周一','周二','周三','周四','周五'];
const SECTIONS = ['第1节','第2节','第3节','第4节','第5节','第6节','第7节','第8节'];

fetch('/api/viz/heatmap')
  .then(r => r.json())
  .then(matrix => {
    if (!matrix || matrix.length === 0) {
      document.getElementById('noDataMsg').classList.remove('d-none');
      return;
    }

    const maxVal = Math.max(...matrix.flat(), 1);
    const colorScale = d3.scaleSequential(d3.interpolateReds).domain([0, maxVal]);
    const cellSize = 70, marginLeft = 60, marginTop = 40;
    const width = marginLeft + SECTIONS.length * cellSize + 20;
    const height = marginTop + DAYS.length * cellSize + 20;

    const svg = d3.create('svg').attr('width', width).attr('height', height);

    SECTIONS.forEach((sec, j) => {
      svg.append('text').attr('x', marginLeft + j * cellSize + cellSize / 2).attr('y', marginTop - 8)
        .attr('text-anchor', 'middle').style('font-size', '12px').style('fill', '#555').text(sec);
    });

    DAYS.forEach((day, i) => {
      svg.append('text').attr('x', marginLeft - 8).attr('y', marginTop + i * cellSize + cellSize / 2)
        .attr('text-anchor', 'end').attr('dominant-baseline', 'middle').style('font-size', '13px').style('fill', '#333').text(day);
    });

    matrix.forEach((row, i) => {
      row.forEach((val, j) => {
        const g = svg.append('g');
        g.append('rect')
          .attr('x', marginLeft + j * cellSize + 2).attr('y', marginTop + i * cellSize + 2)
          .attr('width', cellSize - 4).attr('height', cellSize - 4).attr('rx', 6)
          .attr('fill', val === 0 ? '#f8f9fa' : colorScale(val)).attr('stroke', '#dee2e6').attr('stroke-width', 1);
        g.append('text')
          .attr('x', marginLeft + j * cellSize + cellSize / 2).attr('y', marginTop + i * cellSize + cellSize / 2)
          .attr('text-anchor', 'middle').attr('dominant-baseline', 'middle')
          .style('font-size', '14px').style('font-weight', val > 0 ? '700' : '400')
          .style('fill', val > maxVal * 0.6 ? '#fff' : '#333').text(val);
        g.append('title').text(`${DAYS[i]} ${SECTIONS[j]}：${val} 个冲突`);
      });
    });

    document.getElementById('heatmapContainer').appendChild(svg.node());
    document.getElementById('legendRow').style.removeProperty('display');
  })
  .catch(() => document.getElementById('noDataMsg').classList.remove('d-none'));
