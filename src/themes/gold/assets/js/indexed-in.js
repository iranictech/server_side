/* Gold Indexed In: show three at once; one-step autoplay. Scoped to this element. */
(function () {
  'use strict';

  function initIndexedIn(section) {
    const viewport = section.querySelector('.indexIn_marquee_container');
    const track = section.querySelector('.indexIn_marquee_track');
    const groups = track ? Array.from(track.querySelectorAll('.indexIn_logo_group')) : [];
    if (!viewport || !track || groups.length < 1) return;

    const original = Array.from(groups[0].querySelectorAll('.indexIn_logo_item'));
    const count = original.length;
    if (!count) return;

    // Original reference already contains one duplicate group for seamless looping.
    const duplicate = groups[1];
    if (!duplicate || duplicate.querySelectorAll('.indexIn_logo_item').length !== count) {
      // Never animate an incomplete loop; avoid scrolling onto empty space.
      return;
    }

    duplicate.setAttribute('aria-hidden', 'true');
    duplicate.querySelectorAll('a, button, [tabindex]').forEach(function (el) {
      el.setAttribute('tabindex', '-1');
    });

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let current = 0;
    let timer = null;
    let paused = false;
    let resetPending = false;
    let slot = 0;

    function perView() {
      if (window.innerWidth < 640) return 1;
      if (window.innerWidth < 1024) return 2;
      return 3;
    }

    function setPosition(animate) {
      track.style.transition = animate ? 'transform 650ms ease-in-out' : 'none';
      track.style.transform = 'translate3d(' + (-current * slot) + 'px, 0, 0)';
    }

    function stop() {
      if (timer !== null) {
        window.clearInterval(timer);
        timer = null;
      }
    }

    function start() {
      stop();
      if (count < 2 || reduced.matches || paused || document.hidden) return;
      timer = window.setInterval(function () {
        if (resetPending) return;
        current += 1;
        resetPending = current === count;
        setPosition(true);
      }, 3000);
    }

    function layout() {
      const n = Math.min(perView(), count);
      slot = viewport.getBoundingClientRect().width / n;
      track.style.setProperty('--indexIn-slot-width', slot + 'px');
      resetPending = false;
      current = current % count;
      setPosition(false);
      start();
    }

    track.addEventListener('transitionend', function (event) {
      if (event.target !== track || event.propertyName !== 'transform' || !resetPending) return;
      current = 0;
      resetPending = false;
      setPosition(false);
    });

    viewport.addEventListener('mouseenter', function () { paused = true; stop(); });
    viewport.addEventListener('mouseleave', function () { paused = false; start(); });
    viewport.addEventListener('focusin', function () { paused = true; stop(); });
    viewport.addEventListener('focusout', function (event) {
      if (viewport.contains(event.relatedTarget)) return;
      paused = false; start();
    });
    document.addEventListener('visibilitychange', start);
    if (typeof reduced.addEventListener === 'function') reduced.addEventListener('change', start);
    window.addEventListener('resize', layout);
    layout();
  }

  function init() {
    document.querySelectorAll('.gold-indexed-in-wrapper .indexIn_indexed_section')
      .forEach(initIndexedIn);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
