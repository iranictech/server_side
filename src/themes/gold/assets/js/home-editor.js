/* Gold Editor's Choice: progressive page navigation of FeaturedArticle records.
   Reference DOM/classes preserved. Single article => no pagination. */
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.section_editor_container[data-gold-home-element="featured"]').forEach(function (root) {
    const pages = Array.from(root.querySelectorAll('.section_editor_article_page'));
    const buttons = Array.from(root.querySelectorAll('[data-editor-page]'));
    const prev = root.querySelector('[data-editor-prev]');
    const next = root.querySelector('[data-editor-next]');
    if (pages.length < 2) return;
    let current = 0;
    function show(index) {
      current = Math.max(0, Math.min(pages.length - 1, index));
      pages.forEach((page, i) => { page.hidden = (i !== current); });
      buttons.forEach((button, i) => {
        const active = (i === current);
        button.classList.toggle('section_editor_active', active);
        button.setAttribute('aria-current', active ? 'page' : 'false');
      });
      if (prev) prev.disabled = current === 0;
      if (next) next.disabled = current === pages.length - 1;
    }
    buttons.forEach((button, i) => button.addEventListener('click', () => show(i)));
    if (prev) prev.addEventListener('click', () => show(current - 1));
    if (next) next.addEventListener('click', () => show(current + 1));
    show(0);
  });
});
