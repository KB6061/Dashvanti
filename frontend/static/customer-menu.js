(() => {
 const button = document.querySelector('[data-customer-menu-toggle]');
 const items = document.querySelector('#customer-menu-items');
 const sidebar = document.querySelector('.customer-sidebar');
 if (!button || !items || !sidebar) return;
 const setOpen = open => {
  items.hidden = !open;
  button.setAttribute('aria-expanded', String(open));
  document.body.classList.toggle('customer-menu-open', open);
 };
 button.addEventListener('click', () => setOpen(items.hidden));
 document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !items.hidden) {
   setOpen(false);
   button.focus();
  }
 });
 document.addEventListener('click', event => {
  if (!sidebar.contains(event.target) && !button.contains(event.target)) setOpen(false);
 });
 items.addEventListener('click', event => {
  if (event.target.closest('a, [data-account-open], [data-logout-open]')) setOpen(false);
 });
})();
