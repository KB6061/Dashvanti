(() => {

  const fundsPage = document.querySelector('[data-fund-section]');
  if (fundsPage) {
    const active = fundsPage.dataset.fundSection || 'revenue';
    document.querySelectorAll('[data-fund-views]').forEach((node) => {
      const views = (node.dataset.fundViews || '').split(/\s+/);
      node.classList.toggle('is-hidden', !views.includes(active));
    });
  }
  document.querySelectorAll('[data-sort-table]').forEach((table) => {
    table.querySelectorAll('th').forEach((th, index) => {
      th.tabIndex = 0;
      th.addEventListener('click', () => sort(index));
      th.addEventListener('keydown', (event) => { if (event.key === 'Enter') sort(index); });
      function sort(column) {
        const tbody = table.tBodies[0];
        const direction = th.dataset.sortDirection === 'asc' ? -1 : 1;
        table.querySelectorAll('th').forEach((node) => delete node.dataset.sortDirection);
        th.dataset.sortDirection = direction === 1 ? 'asc' : 'desc';
        [...tbody.rows].sort((a, b) => {
          const av = a.cells[column]?.textContent.trim().replace(/[$,#]/g, '') || '';
          const bv = b.cells[column]?.textContent.trim().replace(/[$,#]/g, '') || '';
          const an = Number(av), bn = Number(bv);
          return direction * (Number.isFinite(an) && Number.isFinite(bn) ? an - bn : av.localeCompare(bv));
        }).forEach((row) => tbody.append(row));
      }
    });
  });
  document.addEventListener('dblclick', (event) => {
    const row = event.target.closest('tr[data-order-url]');
    if (row) location.href = row.dataset.orderUrl;
  });
})();
