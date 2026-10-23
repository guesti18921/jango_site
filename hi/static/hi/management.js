(() => {
  const form = document.querySelector('#bulk-form');
  if (form) {
    const all = form.querySelector('[data-select-all]');
    const items = [...form.querySelectorAll('input[name="selected"]')];
    const output = form.querySelector('[data-selected-count]');
    const update = () => {
      const count = items.filter(item => item.checked).length;
      if (all) { all.checked = count > 0 && count === items.length; all.indeterminate = count > 0 && count < items.length; }
      if (output) output.textContent = String(count);
      items.forEach(item => item.closest('tr').classList.toggle('is-selected', item.checked));
    };
    all?.addEventListener('change', () => { items.forEach(item => item.checked = all.checked); update(); });
    items.forEach(item => item.addEventListener('change', update));
    update();
  }
})();
