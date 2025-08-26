// 02_system_dpi_lock.js — neutralize *system DPI* by scaling INSIDE the iframe.
// Pairs with 01_zoom_lock.js (page zoom). Same-origin only.
/*
(function () {
  const ID = 'depth-iframe';

  function vw() { return document.documentElement.clientWidth  || window.innerWidth  || 0; }
  function vh() { return document.documentElement.clientHeight || window.innerHeight || 0; }
  function dpr() { return window.devicePixelRatio || 1; }
  function pageZoom() {
    return (window.visualViewport && typeof window.visualViewport.scale === 'number')
      ? window.visualViewport.scale : 1; // Firefox: returns 1; then sysDPR == total DPR
  }

  // Anchor system-DPI at load (not page zoom)
  const baseSysDPR = dpr() / pageZoom();

  function canUseZoom() { try { return CSS && CSS.supports && CSS.supports('zoom','1'); } catch { return false; } }
  const useZoom = canUseZoom(); // Chromium yes; Firefox no

  function applyInner(doc) {
    const sysDPR = dpr() / pageZoom();         // isolates OS scale on Chromium; total DPR on Firefox
    const factor = baseSysDPR / sysDPR;        // what we apply inside the iframe
    const W = vw(), H = vh();

    const html = doc.documentElement;
    const body = doc.body || doc.documentElement;

    // Reset
    html.style.overflow = 'hidden';
    body.style.margin = '0';
    body.style.padding = '0';
    body.style.overflow = 'hidden';
    body.style.width = ''; body.style.height = '';
    body.style.transform = ''; body.style.transformOrigin = '';
    html.style.zoom = '';

    // Expand logical box so (logical * factor) == viewport
    const logicalW = W / factor;
    const logicalH = H / factor;

    if (useZoom) {
      html.style.zoom = String(factor);        // crisp text/canvas on Chromium
    } else {
      body.style.transformOrigin = 'top left'; // Firefox fallback
      body.style.transform = 'scale(' + factor + ')';
    }
    body.style.width  = logicalW + 'px';
    body.style.height = logicalH + 'px';
  }

  function withIframeDoc(cb) {
    const el = document.getElementById(ID);
    if (!el) return;
    const ready = () => {
      try {
        const doc = el.contentDocument || (el.contentWindow && el.contentWindow.document);
        if (doc && (doc.readyState === 'interactive' || doc.readyState === 'complete')) cb(doc);
      } catch (_) { s }
    };
    if (el.contentDocument && el.contentDocument.readyState) ready();
    el.addEventListener('load', ready);
  }

  function init() {
    const run = () => withIframeDoc(applyInner);

    run(); // first time (if already loaded)
    window.addEventListener('resize', run, { passive: true });
    window.addEventListener('orientationchange', run, { passive: true });
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', run, { passive: true });
      window.visualViewport.addEventListener('scroll',  run, { passive: true });
    }
    // Poll DPR to catch Windows per-monitor DPI swaps
    let last = dpr();
    setInterval(() => { const cur = dpr(); if (cur !== last) { last = cur; run(); } }, 300);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();*/

