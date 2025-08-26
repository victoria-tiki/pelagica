(function () {
  const root = document.documentElement;
  const isAndroid = /\bAndroid\b/i.test(navigator.userAgent);
  const smallish = Math.min(window.innerWidth, window.innerHeight) <= 900;
  if (!(isAndroid && smallish)) return;

  // Measure current baseline
  const remPx = parseFloat(getComputedStyle(root).fontSize) || 16;

  // === Tunables ===
  const BASE_REM = 12;   // your design baseline
  const BASE_W   = 428;  // design "normal" Android width in CSS px (try 411/414/428)
  const MIN_S    = 0.45; // allow stronger shrink if Genymotion defaults are aggressive

  // 1) Normalize text inflation so rem-based typography behaves as authored
  if (remPx > BASE_REM + 0.25) {
    root.style.fontSize = BASE_REM + 'px';
  }

  // 2) Correct for Display size (DPI) changes that narrow CSS viewport
  const widthFactor = Math.min(1, window.innerWidth / BASE_W);

  // 3) Extra guard if rem stayed bigger anyway
  const textFactor  = Math.min(1, BASE_REM / remPx);

  // 4) Respect user pinch zoom if present
  let s = Math.min(widthFactor, textFactor);
  const vv = window.visualViewport;
  if (vv && vv.scale && vv.scale > 1) s = Math.min(s, 1 / vv.scale);

  // 5) Clamp, apply, log
  s = Math.max(MIN_S, Math.min(1, +s.toFixed(3)));
  root.style.setProperty('--uiscale', s);
  console.log('[mobile-scale]', {innerWidth: window.innerWidth, remPx, widthFactor, textFactor, s});
})();



// ===== Phone-only UI tweaks (append at end of assets/mobile-scale.js) ===== 
(function () {
  // Use the same detector you already use
  const isAndroid = /\bAndroid\b/i.test(navigator.userAgent);
  const smallish  = Math.min(window.innerWidth, window.innerHeight) <= 900;
  if (!(isAndroid && smallish)) return;

  // ---- knobs you can tune ----
  const PAD_FRAC    = 0.10; // pushes the main column down (0.06–0.14)
  const MSG_TOP_FRAC= 0.72; // lowers the depth message (0.66–0.76)
  const MSG_REM     = 1.00; // message font size (0.95–1.20)
  const ROOT_REM_PX = 16;   // normalize root font in the iframe

  const getVH = () => (window.visualViewport?.height || window.innerHeight || 700);

  // 1) Main app: break vertical centering and add top padding to push content down
  function tweakParent() {
    const flex = document.getElementById('page-centre-flex');
    if (flex) {
      flex.style.justifyContent = 'flex-start';                  // was center
      flex.style.paddingTop = Math.round(getVH()*PAD_FRAC) + 'px';
    }
  }

  // 2) Viewer iframe: normalize text + shrink & lower the depth message
  function tweakIframe() {
    const ifr = document.getElementById('depth-iframe');
    if (!ifr) return;

    const apply = () => {
      const d = ifr.contentDocument;
      if (!d || d.readyState !== 'complete') return;

      const topPx = Math.round(getVH()*MSG_TOP_FRAC);

      // normalize Android text inflation inside the iframe
      d.documentElement.style.webkitTextSizeAdjust = '100%';
      d.documentElement.style.textSizeAdjust = '100%';
      d.documentElement.style.fontSize = ROOT_REM_PX + 'px';

      // hard inline overrides
      const mb = d.getElementById('message-box');
      if (mb) {
        mb.style.position = 'fixed';
        mb.style.left = '50%';
        mb.style.top = topPx + 'px';
        mb.style.transform = 'translate(-50%,-50%)';
        mb.style.fontSize = MSG_REM + 'rem';
        mb.style.fontWeight = '500';
        mb.style.lineHeight = '1.3';
        mb.style.fontFamily = 'system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif';
      }

      // belt & suspenders: a style tag with !important
      let tag = d.getElementById('phone-overrides');
      const css = `
        #message-box{
          top:${topPx}px !important;
          transform:translate(-50%,-50%) !important;
          font:500 ${MSG_REM}rem/1.3 system-ui !important;
        }`;
      if (!tag) { tag = d.createElement('style'); tag.id = 'phone-overrides'; d.head.appendChild(tag); }
      tag.textContent = css;
    };

    if (ifr.contentDocument?.readyState === 'complete') apply();
    ifr.addEventListener('load', apply);
  }

  // run now + on viewport changes (Genymotion reflows oddly)
  const reapply = () => { tweakParent(); tweakIframe(); };
  reapply();
  addEventListener('resize', reapply, { passive: true });
  addEventListener('orientationchange', reapply, { passive: true });
  if (window.visualViewport) visualViewport.addEventListener('resize', reapply, { passive: true });
})();

