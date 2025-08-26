// 01_zoom_lock.js — Cancel *browser page zoom only* by scaling the OUTER iframe.
// Uses DPR (works in all browsers) and aggressively settles during first load.

(function () {
  const ID = 'depth-iframe';

  function dpr() { return window.devicePixelRatio || 1; }
  function vw()  { return document.documentElement.clientWidth  || window.innerWidth  || 0; }
  function vh()  { return document.documentElement.clientHeight || window.innerHeight || 0; }

  function apply(el) {
    const Z = dpr();                 // page zoom reflected in DPR in all browsers
    const W = vw(), H = vh();

    // Pre-scale by Z, then scale by 1/Z ⇒ visually fills viewport at any page zoom
    el.style.position        = 'fixed';
    el.style.top             = '0';
    el.style.left            = '0';
    el.style.width           = (W * Z) + 'px';
    el.style.height          = (H * Z) + 'px';
    el.style.transformOrigin = 'top left';
    el.style.transform       = 'scale(' + (1 / Z) + ')';
    el.style.border          = 'none';
    el.style.zIndex          = '0';
    el.style.pointerEvents   = 'none';
    el.style.willChange      = 'transform';
  }

  // Wait until the iframe actually exists (Dash inserts it after assets load)
  function waitForIframe(cb, timeoutMs = 8000) {
    const now = document.getElementById(ID);
    if (now) return cb(now);

    const t0 = performance.now();
    const obs = new MutationObserver(() => {
      const el = document.getElementById(ID);
      if (el) { obs.disconnect(); cb(el); }
      else if (performance.now() - t0 > timeoutMs) { obs.disconnect(); }
    });
    if (document.body) obs.observe(document.body, { childList: true, subtree: true });
    const int = setInterval(() => {
      const el = document.getElementById(ID);
      if (el) { clearInterval(int); cb(el); }
      else if (performance.now() - t0 > timeoutMs) { clearInterval(int); }
    }, 50);
  }

  function boot(el) {
    // Aggressive settle: hit multiple frames + timed passes so initial 150% is caught
    const passes = [0, 16, 32, 64, 96, 160, 240, 400, 700, 1200];
    passes.forEach(ms => setTimeout(() => apply(el), ms));

    // Also poll DPR for the first 2 seconds; re-apply if it changes
    let last = -1, t0 = performance.now();
    const int = setInterval(() => {
      const z = dpr();
      if (Math.abs(z - last) > 1e-3) { last = z; apply(el); }
      if (performance.now() - t0 > 2000) clearInterval(int);
    }, 50);

    // Keep it glued after boot
    const rerun = () => apply(el);
    window.addEventListener('resize', rerun, { passive: true });
    window.addEventListener('orientationchange', rerun, { passive: true });
    window.addEventListener('pageshow', () => apply(el), { passive: true });
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', rerun, { passive: true });
      window.visualViewport.addEventListener('scroll',  rerun, { passive: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => waitForIframe(boot));
  } else {
    waitForIframe(boot);
  }
})();

