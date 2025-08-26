(function () {
  const ID = 'depth-iframe';

  // ---- platform detection ----
  const ua = navigator.userAgent || '';
  const isIOS = /iP(ad|hone|od)/.test(ua);
  const isWebkit = /WebKit/.test(ua) && !/CriOS|FxiOS|OPiOS|EdgiOS/.test(ua);
  const isIOSSafari = isIOS && isWebkit;
  const isAndroid = /Android/i.test(ua);

  // ---- query param / JS flag override ----
  const urlParams = new URLSearchParams(location.search);
  const noZoom = urlParams.has('nozoom') || window.PELAGICA_NO_ZOOM_LOCK;

  if (isIOSSafari || isAndroid || noZoom) {
    console.log("Zoom lock disabled on this device.");
    return;
  }

  // ---- normal zoom lock below ----
  const dpr = () => window.devicePixelRatio || 1;
  const vw  = () => document.documentElement.clientWidth  || window.innerWidth  || 0;
  const vh  = () => document.documentElement.clientHeight || window.innerHeight || 0;

  let last = { Z: 0, W: 0, H: 0 };

  function apply(el) {
    const Z = dpr(), W = vw(), H = vh();
    if (Math.abs(Z - last.Z) < 1e-3 && W === last.W && H === last.H) return;

    last = { Z, W, H };
    if (Z === 1) {
      el.style.transform = '';
      el.style.width = '';
      el.style.height = '';
      return;
    }

    el.style.position        = 'fixed';
    el.style.top             = '0';
    el.style.left            = '0';
    el.style.width           = (W * Z) + 'px';
    el.style.height          = (H * Z) + 'px';
    el.style.transformOrigin = 'top left';
    el.style.transform       = 'scale(' + (1 / Z) + ')';
    el.style.border          = 'none';
    el.style.pointerEvents   = 'none';
    el.style.willChange      = 'transform';
  }

  function waitForIframe(cb) {
    const el = document.getElementById(ID);
    if (el) return cb(el);
    const obs = new MutationObserver(() => {
      const el = document.getElementById(ID);
      if (el) { obs.disconnect(); cb(el); }
    });
    if (document.body) obs.observe(document.body, { childList: true, subtree: true });
  }

  function boot(el) {
    [0, 50, 200].forEach(ms => setTimeout(() => apply(el), ms));
    let pending = false;
    const rerun = () => {
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => { pending = false; apply(el); });
    };
    addEventListener('resize', rerun, { passive: true });
    addEventListener('orientationchange', rerun, { passive: true });
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', rerun, { passive: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => waitForIframe(boot));
  } else {
    waitForIframe(boot);
  }
})();

