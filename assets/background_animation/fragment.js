div id="back-view" class="layer-view">
  <picture>
    <source srcset="back.webp" type="image/webp" fetchpriority="high">
  <img id="back-img"
       class="layer-img parallax-layer"
       src="back.png"
       data-depth="0.0"
       data-layer="back"
       decoding="async"
       fetchpriority="high">   
  </picture>
</div>


<div id="layer3-view" class="layer-view">
  <picture>
    <!--<source srcset="layer3.avif" type="image/avif">-->
    <source srcset="layer3.webp" type="image/webp">
    <img id="layer3"
         class="layer-img parallax-layer"
         src="layer3.png"
         data-depth="0.0"
         data-layer="layer3"
         loading="lazy"
         decoding="async">
  </picture>
</div>

<div id="birds-view" class="layer-view"></div>

<div id="layer4-view" class="layer-view">
  <picture>
    <!--<source srcset="layer4.avif" type="image/avif">-->
    <source srcset="layer4.webp" type="image/webp">
    <img id="layer4"
         class="layer-img parallax-layer"
         src="layer4.png"
         data-depth="0.1"
         data-layer="layer4"
         decoding="async"
         fetchpriority="high">
  </picture>
</div>

<div id="layer5-view" class="layer-view">
  <picture>
    <!--<source srcset="layer5.avif" type="image/avif">-->
    <source srcset="layer5.webp" type="image/webp">
    <img id="layer5"
         class="layer-img parallax-layer"
         src="layer5.png"
         data-depth="0.2"
         data-layer="layer5"
         loading="lazy"
         decoding="async">
  </picture>
</div>

<div id="layer6-view" class="layer-view">
  <picture>
    <!--<source srcset="layer6.avif" type="image/avif">-->
    <source srcset="layer6.webp" type="image/webp">
    <img id="layer6"
         class="layer-img parallax-layer"
         src="layer6.png"
         data-depth="0.4"
         data-layer="layer6"
         loading="lazy"
         decoding="async">
  </picture>
</div>

<div id="layer7-view" class="layer-view">
   <img id="layer7"
       class="layer-img parallax-layer progressive"
       src="layer7_top.webp"          
       data-full-src="layer7.png"     
       data-depth="0.6"
       data-layer="layer7"
       decoding="async"
       fetchpriority="high">          
</div>

<div id="layer8-view" class="layer-view">
   <img id="layer8"
       class="layer-img parallax-layer progressive"
       src="layer8_top.webp"          
       data-full-src="layer8.png"     
       data-depth="0.6"
       data-layer="layer8"
       decoding="async"
       fetchpriority="high">          
</div>

<div id="layer9-view" class="layer-view">
   <img id="layer9"
       class="layer-img parallax-layer progressive"
       src="layer9_top.webp"          
       data-full-src="layer9.png"     
       data-depth="0.6"
       data-layer="layer9"
       decoding="async"
       fetchpriority="high">          
</div>

<div id="view" class="layer-view">
   <img id="front-img"
       class="layer-img parallax-layer progressive"
       src="front_top.webp"          
       data-full-src="front.png"     
       data-depth="0.6"
       data-layer="front"
       decoding="async"
       fetchpriority="high">          
</div>












/* ─────────────────────────────────────────────
   Deep-Sea Viewer  –  single consolidated JS
   ───────────────────────────────────────────── */
const TILE_H     = 1000;   // must stay in sync with Python script
let   tileLayers = [];     // filled later by setupLazyTiles()


if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js')   // supply the correct path
           .catch(console.error);
}







const depthCache = new Map();
function depthToPixelMemo(d){
  if(!depthCache.has(d)) depthCache.set(d, depthToPixel(d));
  return depthCache.get(d);
}

/* — full original depthToPixel formula — */
function depthToPixel(m){
  if(m<0)      return 1000 - m*(1000/20);
  if(m<=200)   return 1000 + m*(2500/200);
  if(m<=1000)  return 3500 + (m-200)*(4000/800);
  if(m<=4000)  return 7500 + (m-1000)*(8000/3000);
  if(m<=6000)  return15500 + (m-4000)*(5000/2000);
  if(m<=11000) return20500 + (m-6000)*(11000/5000);
  alert("Depth out of range!"); return 0;
}


// Optional animations for layers
const behaviorHooks = {};

/*  ────────────────────────────────────────────────────────────
    CONTINUOUS SIDE‑SCROLL FOR LAYER‑3
    (drop this right where the old `behaviorHooks.layer3` sat)
   ──────────────────────────────────────────────────────────── */
/* ── continuous side‑scroll for layer‑3 ───────────────────────── */
behaviorHooks.layer3 = (() => {
  let prevT   = null;   // previous timestamp
  let offset  = 0;      // running X‑offset (px, negative = left)
  let imgW    = null;   // pixel width of layer‑3 sprite
  let clone   = null;   // trailing copy
  const SPEED = 15;     // px / s  – tweak to taste

  /* one‑time setup */
  function setup(el) {
    if (imgW !== null) return;              // already done
    imgW = el.naturalWidth || el.width;

    /* kill CSS transitions so wraps are truly instant */
    el.style.transition = "none";

    clone = el.cloneNode(false);
    clone.id = "layer3-clone";
    clone.dataset.layer = "layer3";
    clone.style.transition = "none";
    el.parentElement.appendChild(clone);
  }

  return (el, _depth, baseY, t) => {
    setup(el);

    if (prevT === null) prevT = t;
    const dt = (t - prevT) / 1000;  // seconds since last frame
    prevT = t;

    /* advance, then wrap with modulo for a perfect loop */
    offset = (offset - SPEED * dt) % imgW;

    const yPx = -baseY;  // your existing vertical parallax shift

    /* keep the built‑in –50 % centring *and* add our offset */
    el.style.transform    = `translate(calc(-50% + ${offset}px), ${yPx}px)`;
    clone.style.transform = `translate(calc(-50% + ${offset + imgW}px), ${yPx}px)`;
  };
})();



/* ────────────────────────────────────────────────────────────────
   RANDOM SURFACE DISTORTIONS 2.0
   ─ layer front, layer6‑9  : translate  +  scaleX pulsation
   ─ layer layer5  (boat)   : figure‑8 drift (unchanged)
   ──────────────────────────────────────────────────────────────── */

const WAVE_LAYERS = ['front', 'layer6', 'layer7', 'layer8', 'layer9'];
const SWAY_LAYER  = 'layer5';

/* base magnitudes (we’ll randomise per layer) */
const BASE = {
  wave: { ampX: 3, ampY: 25,  ampSX: 0.02, freq: 0.2 },   // ampSX = ±5 % width
  boat: { ampX: 4,  ampY: 5,  freq: 1.2/5 }
};

/* one‑time random params so layers are independent */
/* ─────────────────────────────────────────────────────────────
   Per‑layer random params WITH depth‑aware fall‑off
   front  > layer9 > layer8 > layer7 > layer6   (largest ⟶ smallest)
   ──────────────────────────────────────────────────────────── */

const waveParams = {};
const orderedWaveLayers = ['front', 'layer9', 'layer8', 'layer7', 'layer6'];

/* How much should each successive layer shrink? */
const AMP_DECAY = 0.80;   // amplitude multiplier per step (0.75 ⇒ 25 % smaller)
const FREQ_DECAY = 0.9;  // frequency multiplier per step (0.85 ⇒ 15 % slower)

orderedWaveLayers.forEach((name, idx) => {
  const ampMult  = Math.pow(AMP_DECAY, idx);   // front = 1, next = 0.75, …
  const freqMult = Math.pow(FREQ_DECAY, idx);

  waveParams[name] = {
    /* Random phase keeps layers unsynchronised                          */
    phaseTX : Math.random() * 2 * Math.PI,
    phaseTY : Math.random() * 2 * Math.PI,
    phaseSX : Math.random() * 2 * Math.PI,

    /* Frequencies & amplitudes taper with depth, then random‑jitter */
    freqTX  : BASE.wave.freq * freqMult * (0.9 + Math.random()*0.2),
    freqTY  : BASE.wave.freq * freqMult * (0.9 + Math.random()*0.2),
    freqSX  : BASE.wave.freq * freqMult * (0.9 + Math.random()*0.2),

    ampTX   : BASE.wave.ampX  * ampMult  * (0.9 + Math.random()*0.2),
    ampTY   : BASE.wave.ampY  * ampMult  * (0.9 + Math.random()*0.2),
    ampSX   : BASE.wave.ampSX * ampMult  * (0.9 + Math.random()*0.2)
  };
});


const boatParam = {
  phase : Math.random() * 2 * Math.PI,
  ampX  : BASE.boat.ampX,
  ampY  : BASE.boat.ampY,
  freq  : BASE.boat.freq
};

/* ----------------------------------------------------------------
   Overlay‑hook factory
-----------------------------------------------------------------*/
const behaviorHooksOverlay = layerName => {

  /* 🌊  Surface layers */
  if (WAVE_LAYERS.includes(layerName)) {
    const p = waveParams[layerName];
    return (el, depth, baseY, t) => {

      /* only near surface (≤100 m or undefined) */
      const active = (depth === undefined || depth < 40);
      const time   = t / 1000;

      const dx  = active ? Math.sin(2*Math.PI*p.freqTX*time + p.phaseTX) * p.ampTX : 0;
      const dy  = active ? Math.cos(2*Math.PI*p.freqTY*time + p.phaseTY) * p.ampTY : 0;
      const sX  = active ? 1 + Math.sin(2*Math.PI*p.freqSX*time + p.phaseSX) * p.ampSX : 1;

      /* scale first, then translate → natural squeeze/expand */
      el.style.transform =
        `scaleX(${sX}) translate(calc(-50% + ${dx}px), ${-baseY + dy}px)`;
    };
  }

  /* ⛵  Boat layer */
  if (layerName === SWAY_LAYER) {
    const p = boatParam;
    return (el, _depth, baseY, t) => {
      const time = t / 1000;
      const dx = Math.sin(2*Math.PI*p.freq*time + p.phase)           * p.ampX;
      const dy = Math.sin(2*Math.PI*p.freq*time + p.phase + Math.PI/2)* p.ampY;
      el.style.transform =
        `translate(calc(-50% + ${dx}px), ${-baseY + dy}px)`;
    };
  }

  return null;
};


/*
let birdInterval = null;        
const activeBirds = new Set();*/








/* ── master animation switch ─────────────────────────────── */
let animPausedByUser = false;

window.pauseAllMotion = function() {
  animPausedByUser = true;

  // Stop spawning new birds
  clearInterval(birdInterval);
  birdInterval = null;

  // Stop flapping + remove from DOM
  for (const { interval } of activeBirds) {
    clearInterval(interval);
  }
  activeBirds.clear();
  document.querySelectorAll('.bird-wrapper').forEach(b => b.remove());
};





function resumeAllMotion(){
  animPausedByUser = false;

  window.spawnBirdFlock();
  birdInterval = setInterval(window.spawnBirdFlock, 25000 + Math.random() * 5000);

  activeBirds.forEach(meta => {
    const { el } = meta;
    el.style.animationPlayState = 'running';

    // Restart flapping
    const flapEvery = 3000 + Math.random() * 3000;
    const flapDuration = 150;

    meta.flapTimer = setInterval(() => {
      el.style.backgroundImage = "url('bird_down.webp')";
      setTimeout(() => {
        el.style.backgroundImage = "url('bird_up.webp')";
      }, flapDuration);
    }, flapEvery);

    // Restart auto-despawn (time remaining is approximate here)
    const remainingTime = 5000 + Math.random() * 2000; // fudge value
    meta.destroyTimer = setTimeout(() => {
      clearInterval(meta.flapTimer);
      activeBirds.delete(meta);
      el.remove();
    }, remainingTime);
  });

  // Resume CSS animations
  document.querySelectorAll('.layer-img').forEach(el =>
    el.style.animationPlayState = 'running'
  );
}





















/*  birds.js  ─ one flock spawner you can pause / resume  */
/*
(function initBirds(){
  const container = document.getElementById('birds-view');

  const FLOCK_SIZE   = 3;
  const FLIGHT_MIN   = 35000;
  const FLIGHT_VAR   = 5000;
  const SPAWN_EVERY  = 35000;
  const SPAWN_JITTER = 2000;

  window.birdInterval = null;


  const activeBirds = new Set();

  function spawnBirdFlock(){
    if (animPausedByUser) return;

    const baseAlt = 8 + Math.random()*14;

    for (let i = 0; i < FLOCK_SIZE; i++) {
      const dur = FLIGHT_MIN + Math.random()*FLIGHT_VAR;

      const wrap = document.createElement('div');
      wrap.className = 'bird-wrapper';

      const bird = document.createElement('div');
      bird.className = 'bird';
        wrap.style.setProperty('--dur', `${dur}ms`);
        wrap.style.animation = `birdFlight var(--dur) linear forwards`;


      bird.style.backgroundImage = "url('bird_up.webp')";

      wrap.appendChild(bird);
      container.appendChild(wrap);

      const scale = 0.5 + Math.random()*0.9;
      wrap.style.left = '0';
      wrap.style.transform = `scale(${scale}) translateX(120vw)`;

      wrap.style.top = `${baseAlt + i*2}vh`;

      const waveAmp = (10 + Math.random()*80).toFixed(1) + 'px';
      wrap.style.setProperty('--wave', waveAmp);

      const flapEvery = 3000 + Math.random()*3000;
      const flapDuration = 150;

      const flapData = {
        bird,
        interval: setInterval(() => {
          if (animPausedByUser) return;  // Skip if paused
          bird.style.backgroundImage = "url('bird_down.webp')";
          setTimeout(() => {
            if (!animPausedByUser) bird.style.backgroundImage = "url('bird_up.webp')";
          }, flapDuration);
        }, flapEvery)
      };

      activeBirds.add(flapData);

      setTimeout(() => {
        clearInterval(flapData.interval);
        activeBirds.delete(flapData);
        wrap.remove();
      }, dur);
    }
  }

  window.spawnBirdFlock = spawnBirdFlock;

  function startBirds(){
    spawnBirdFlock();
    birdInterval = setInterval(spawnBirdFlock, SPAWN_EVERY + Math.random()*SPAWN_JITTER);
  }

  function stopBirds(){
    clearInterval(birdInterval);
    birdInterval = null;
  }

  function pauseBirdAnimations(){
    document.querySelectorAll('.bird').forEach(b => {
      b.style.animationPlayState = 'paused';
    });
  }

  function resumeBirdAnimations(){
    document.querySelectorAll('.bird').forEach(b => {
      b.style.animationPlayState = 'running';
    });
  }


  window.resumeAllMotion = function(){
    animPausedByUser = false;
    startBirds();
    resumeBirdAnimations();
  };

  // Start initially
  startBirds();
})();*/
















/* ② helper that hides layers / pauses animations according to depth */
function updateDepthDependentAssets (depth) {

  /* Shorthands */
  const show   = (id, on)   =>  document.getElementById(id).style.display = on ? '' : 'none';
  const pause  = (ids,on)   =>  ids.forEach(id=>{
                                const el = document.getElementById(id);
                                if (el) el.style.animationPlayState = on? 'paused':'running';
                              });

  /* a) depth < 0 m (above water) → hide layers 4 & 5 */
  const off45 = (depth !== undefined && depth < 0);
  show('layer4-view', !off45);
  show('layer5-view', !off45);

  /* b) depth ≤ 30 →  stop birds + hide layer 3 */
  const off30 =(depth !== undefined && depth >= 30);
  show('layer3-view', !off30);
  if (off30) {
    clearInterval(birdInterval);
    birdInterval = null;
    document.getElementById('birds-view').innerHTML = '';  /* scrub any birds already on screen */
      } else if (!birdInterval && !animPausedByUser) {
        /* first flock right away, then resume the usual 25 s cadence (+ jitter) */
        window.spawnBirdFlock();
        birdInterval = setInterval(
          window.spawnBirdFlock,
         25000 + Math.random() * 5000
        );
    }

  /* c) depth ≤ 50 →  hide BACK layer + freeze deeper layers */
  const off50 = (depth !== undefined && depth >= 50);
  show('back-view', !off50);
  pause(['layer6','layer7','layer8','layer9','front-img'], off50); /* freezes parallax movement */
}


/* ==========  STATE  ========================================= */

/* ------------------------------------------------------------------ */
/* 1️⃣  ORIGINAL MAP — keep this exactly as you wrote it               */
const layers = Array.from(document.querySelectorAll('.parallax-layer')).map(el => ({
  el,                            // DOM node
  id: el.dataset.layer,          // "layer5", "front", …
  depthFactor: +el.dataset.depth // numeric   0.0 … 1.0
}));

/* ------------------------------------------------------------------ */
/* 2️⃣  Build the “all images are ready” promise from that same array */
const loadPromises = layers.map(({ el }) =>
  el.complete
    ? Promise.resolve()                      // already in the cache
    : new Promise(res => el.addEventListener('load', res, { once:true }))
);



/* ------------------------------------------------------------------ */
/* 4️⃣  Optional: drop will-change again after the initial dive        */
function stopParallax() {
  layers.forEach(({ el }) => (el.style.willChange = 'auto'));
}


let currentDepth=0, targetDepth=0, depthMode=false;
let moveStart=0, moveDur=0, startDepth=0;


/* ==========  GO BUTTON  ===================================== */
function goToDepth(){
  const v = parseFloat(document.getElementById('depth-input').value);
  if(Number.isNaN(v)) return;

  if(v<currentDepth) updateDepthDependentAssets(v);   // surfacing

  const dz=Math.abs(v-currentDepth);
  const T = Math.min(7,Math.max(3,2+1.5*Math.sqrt(dz/1000)));

  startDepth=currentDepth; targetDepth=v;
  moveStart=performance.now(); moveDur=T*1000; depthMode=true;
}
window.goToDepth=goToDepth;

/* ==========  RAF LOOP  ====================================== */
let prevDepthForStatic=null, paused=false;
document.addEventListener('visibilitychange',()=>paused=document.hidden);

function raf(ts){
  if(paused){requestAnimationFrame(raf);return;}

  /* camera easing */
  if(depthMode){
    const e=ts-moveStart;
    currentDepth = e>=moveDur ? targetDepth
                  : startDepth+(targetDepth-startDepth)*(3*(e/moveDur)**2-2*(e/moveDur)**3);
  }

  /* gate layers exactly when camera settles */
  if(!depthMode||currentDepth===targetDepth)
      updateDepthDependentAssets(depthMode?currentDepth:undefined);

  /* transforms & hooks every frame, static translate only on change */
  const baseY = depthMode ? depthToPixelMemo(currentDepth)-innerHeight/2 : 0;
  const depthArg = depthMode?currentDepth:undefined;

    for (const {el,id,depthFactor} of layers){
      const y     = baseY * depthFactor;
      const h1    = behaviorHooks[id];
      const h2    = behaviorHooksOverlay(id);

      /* base vertical parallax ALWAYS updates */
      el.style.transform = `translate(-50%, ${-y}px)`;

      /* extra motion only if user hasn’t paused */
      if (!animPausedByUser){
        if (h1) h1(el, depthArg, y, ts);
        if (h2) h2(el, depthArg, y, ts);
      }
    }

  prevDepthForStatic=currentDepth;
  
  /* ─── progressive tiling (keeps 1 slice ahead) ─────────────────── */
for (const L of tileLayers){
  const yPx   = baseY * L.depthF;                 // top edge of this view
  const slice = Math.min(L.total-1, Math.floor(yPx / TILE_H));

  if (slice   > L.loaded)                       swapSlice(L, slice);
  if (slice+1 > L.loaded && slice+1 < L.total)  swapSlice(L, slice+1);
}

function swapSlice(L, n){
  L.img.src = `${L.prefix}_${n}.webp`;
  L.loaded  = n;
}



  requestAnimationFrame(raf);
}


/* ── Progressive image swap (one copy in DOM) ───────────────────────────── */
/*const progressiveImgs = document.querySelectorAll('.progressive[data-full-src]');

const swapObserver = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (!entry.isIntersecting) return;           // not close enough yet
    const img = entry.target;
    // Swap src → full image
    img.src = img.dataset.fullSrc;
    img.removeAttribute('data-full-src');
    img.classList.remove('progressive');         // optional, for CSS hooks
    swapObserver.unobserve(img);                 // stop watching
  });
}, {
  root: null,                // viewport
  rootMargin: '1200px 0px',   // start 1.2 viewports before the layer
  threshold: 0               // fire as soon as ANY pixel is inside margin
});

progressiveImgs.forEach(img => swapObserver.observe(img));*/


function wireUpButtons () {
  const toggle = document.getElementById('anim-toggle');

  toggle.addEventListener('click', () => {
    if (animPausedByUser) {
      resumeAllMotion();
      toggle.textContent = 'Pause animation';
    } else {
      pauseAllMotion();
      toggle.textContent = 'Resume animation';
    }
  });
}


/* ─── single, unified start‑up path ─────────────────────────────────── */
window.addEventListener('DOMContentLoaded', () => {
  wireUpButtons();          // buttons clickable right away

  /* build tileLayers immediately; fall back to setTimeout if idle‑cb
     isn't available (Safari)                                        */
  (window.requestIdleCallback || function(cb){ setTimeout(cb,0); })
        (setupLazyTiles);

  /* no need to wait for every <img> → start motion now */
  document.body.classList.add('ready');
  requestAnimationFrame(raf);
});



/* ── build look‑up table but let the main RAF handle swapping ── */
function setupLazyTiles(){
  tileLayers = Array.from(document.querySelectorAll('.layer-view')).map(view=>{
      const img = view.querySelector('img');
      return {
        img,
        prefix : img.dataset.prefix,
        total  : +img.dataset.tiles,
        depthF : +view.dataset.depth,
        loaded : -1
      };
  });
}



