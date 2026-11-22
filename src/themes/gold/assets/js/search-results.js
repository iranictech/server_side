(() => {
  'use strict';
  const root = document.querySelector('.gold-search-page');
  if (!root) return;
  root.querySelectorAll('.achive_page_two_accordion_header').forEach((button) => {
    button.addEventListener('click', () => {
      const accordion = button.closest('.achive_page_two_accordion');
      const open = accordion.classList.toggle('achive_page_two_active');
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  });
  const sort = root.querySelector('[data-gold-sort]');
  sort?.addEventListener('change', () => {
    const url = new URL(window.location.href);
    url.searchParams.set('sort', sort.value);
    url.searchParams.delete('page');
    window.location.assign(url.toString());
  });
  // Safe title highlighting: preserve each original <a> and never inject HTML.
  const input = root.querySelector('#liveSearchInput');
  const titles = Array.from(root.querySelectorAll('.article-title-a'));
  const originals = titles.map((a) => a.textContent);
  const highlight = () => {
    const needle = input?.value.trim() || '';
    titles.forEach((anchor, idx) => {
      const value = originals[idx];
      anchor.replaceChildren();
      if (!needle) { anchor.textContent = value; return; }
      let start = 0;
      const haystack = value.toLocaleLowerCase();
      const lowerNeedle = needle.toLocaleLowerCase();
      while (start < value.length) {
        const found = haystack.indexOf(lowerNeedle, start);
        if (found < 0) { anchor.appendChild(document.createTextNode(value.slice(start))); break; }
        anchor.appendChild(document.createTextNode(value.slice(start, found)));
        const mark = document.createElement('mark');
        mark.className = 'highlight';
        mark.textContent = value.slice(found, found + needle.length);
        anchor.appendChild(mark);
        start = found + needle.length;
      }
    });
  };
  input?.addEventListener('input', highlight);
  highlight();
})();


/* GOLD SEARCH SHARE SUPPORT V2 */
/* A normal anchor is retained: sharing failures never create a dead link. */
document.addEventListener('click', async (event) => {
  const target = event.target.closest?.('.gold-search-page [data-gold-article-share]');
  if (!target) return;
  if (!navigator.share && !navigator.clipboard?.writeText) return;
  event.preventDefault();
  const url = target.href;
  const title = target.dataset.shareTitle || document.title;
  try {
    if (navigator.share) {
      await navigator.share({ title, url });
    } else {
      await navigator.clipboard.writeText(url);
      const label = target.querySelector('.gold-share-label');
      if (label) {
        const previous = label.textContent;
        label.textContent = 'Copied!';
        window.setTimeout(() => { label.textContent = previous; }, 1800);
      }
    }
  } catch (error) {
    if (error?.name !== 'AbortError') window.location.assign(url);
  }
});
