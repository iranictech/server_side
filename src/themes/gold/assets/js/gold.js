(function () {
  const toggle   = document.getElementById('menuToggle');
  const drawer   = document.getElementById('mobileDrawer');
  const overlay  = document.getElementById('drawerOverlay');
  const closeBtn = document.getElementById('drawerClose');

  if (!toggle || !drawer || !overlay) return;

  function openDrawer() {
    drawer.classList.add('is_open');
    overlay.classList.add('is_open');
    toggle.classList.add('is_active');
    toggle.setAttribute('aria-expanded', 'true');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('no_scroll');
  }

  function closeDrawer() {
    drawer.classList.remove('is_open');
    overlay.classList.remove('is_open');
    toggle.classList.remove('is_active');
    toggle.setAttribute('aria-expanded', 'false');
    overlay.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('no_scroll');
  }

  toggle.addEventListener('click', function () {
    drawer.classList.contains('is_open') ? closeDrawer() : openDrawer();
  });

  if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
  overlay.addEventListener('click', closeDrawer);

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeDrawer();
  });
})();

/* GOLD JOURNAL FINDER V1.1 — no manuscript storage, no external API */
(() => {
  'use strict';
  document.querySelectorAll('[data-gold-finder-form]').forEach((form) => {
    if (form.dataset.goldFinderInitialized === '1') return;
    form.dataset.goldFinderInitialized = '1';
    const section = form.closest('.journal-finder');
    const result = section?.querySelector('[data-gold-finder-result]');
    const textarea = form.querySelector('[name="manuscript_text"]');
    const button = form.querySelector('button[type="submit"]');
    if (!result || !textarea) return;

    const resize = () => {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(220, Math.max(72, textarea.scrollHeight))}px`;
    };
    if (textarea.tagName === 'TEXTAREA') {
      textarea.addEventListener('input', resize);
      resize();
    }

    const message = (str) => {
      result.hidden = false;
      result.replaceChildren();
      result.textContent = str;
    };
    const line = (label, content) => {
      if (!content) return;
      const p = document.createElement('p');
      p.className = 'gold-jf-result-evidence';
      const heading = document.createElement('strong');
      heading.textContent = label;
      p.appendChild(heading);
      p.appendChild(document.createTextNode(` ${content}`));
      result.appendChild(p);
    };

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const text = textarea.value.trim();
      if (text.length < 3 || text.length > 8000) {
        message('Enter between 3 and 8000 characters.');
        return;
      }
      if (button) button.disabled = true;
      message('Checking topic and scope evidence…');
      try {
        const response = await fetch(form.action, {
          method: 'POST',
          body: new FormData(form),
          credentials: 'same-origin',
          headers: { 'Accept': 'application/json' },
          cache: 'no-store'
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Unable to check journal fit.');
        result.replaceChildren();
        const title = document.createElement('strong');
        title.className = 'gold-jf-result-title';
        title.textContent = data.label || 'Scope screening';
        result.appendChild(title);
        const explanation = document.createElement('p');
        explanation.textContent = data.explanation || '';
        result.appendChild(explanation);

        const matched = Array.isArray(data.matched_topics) ? data.matched_topics : [];
        const exact = matched.filter((m) => m.evidence === 'exact_phrase').map((m) => m.topic);
        const other = matched.filter((m) => m.evidence !== 'exact_phrase').map((m) => m.topic);
        line('Exact topic phrases:', exact.join(' / '));
        line('Other lexical overlap (weaker evidence):', other.join(' / '));
        line('Independent scope words:', (data.scope_support_terms || []).join(' / '));
        if (data.semantic) {
          line('Optional local semantic similarity:', `${data.semantic.similarity_band} (uncalibrated supplementary evidence)`);
        }
      } catch (error) {
        message(error?.message || 'Unable to check journal fit.');
      } finally {
        if (button) button.disabled = false;
      }
    });
  });
})();

/* GOLD REFERENCE SEARCH POPUP INTEGRATION */
document.addEventListener("DOMContentLoaded", function () {
  const searchButtons = document.querySelectorAll(
    ".head_search_icon .icon_btn, .mobile_drawer__title.icon_btn"
  );

  const searchPopup = document.getElementById("searchPopup");
  const closeButton = document.getElementById("searchPopupClose");
  const searchForm = document.getElementById("searchForm");
  const searchInput = document.getElementById("searchInput");

  if (!searchPopup) return;

  function openSearchPopup(event) {
    event.preventDefault();

    // Close the reference mobile drawer before opening search.
    const drawer = document.getElementById("mobileDrawer");
    const toggle = document.getElementById("menuToggle");

    if (
      drawer &&
      toggle &&
      drawer.classList.contains("is_open")
    ) {
      toggle.click();
    }

    searchPopup.classList.add("is-open");
    document.body.style.overflow = "hidden";

    if (searchInput) {
      setTimeout(function () {
        searchInput.focus();
      }, 350);
    }
  }

  function closeSearchPopup() {
    searchPopup.classList.remove("is-open");
    document.body.style.overflow = "";
  }

  searchButtons.forEach(function (button) {
    button.addEventListener("click", openSearchPopup);
  });

  if (closeButton) {
    closeButton.addEventListener("click", closeSearchPopup);
  }

  searchPopup.addEventListener("click", function (event) {
    if (event.target === searchPopup) {
      closeSearchPopup();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeSearchPopup();
    }
  });

  // Do not prevent native GET form submission.
  // Janeway reads article_search and sort.
  if (searchForm && searchInput) {
    searchForm.addEventListener("submit", function (event) {
      if (!searchInput.value.trim()) {
        event.preventDefault();
        searchInput.focus();
      }
    });
  }
});

/* GOLD ACCOUNT MENU INTEGRATION */
document.addEventListener("DOMContentLoaded", function () {
  const button = document.querySelector(
    "[data-gold-account-toggle]"
  );

  const menu = document.getElementById("goldAccountLinks");

  if (!button || !menu) return;

  function setOpen(open) {
    menu.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
  }

  setOpen(false);

  button.addEventListener("click", function () {
    setOpen(menu.hidden);
  });

  document.addEventListener("click", function (event) {
    if (
      !menu.hidden &&
      !button.contains(event.target) &&
      !menu.contains(event.target)
    ) {
      setOpen(false);
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !menu.hidden) {
      setOpen(false);
      button.focus();
    }
  });
});


/* GOLD TOAST AUTO DISMISS */
(function () {
    function initGoldToasts() {
        document.querySelectorAll('.gold-toast').forEach(function (toast) {
            window.setTimeout(function () {
                if (!toast.isConnected) return;

                toast.style.transition = 'opacity 300ms ease';
                toast.style.opacity = '0';

                window.setTimeout(function () {
                    toast.remove();
                }, 300);
            }, 5000);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener(
            'DOMContentLoaded',
            initGoldToasts,
            { once: true }
        );
    } else {
        initGoldToasts();
    }
})();
