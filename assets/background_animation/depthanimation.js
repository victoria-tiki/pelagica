let previousTimestamp = null;
let driftOffset = 0;

// Convert depth (in meters) to vertical pixel position
function depthToPixel(depth_m) {
  if (depth_m < 0) return 1000 - depth_m * (1000 / 20);
  if (depth_m <= 200) return 1000 + depth_m * (2500 / 200);
  if (depth_m <= 1000) return 3500 + (depth_m - 200) * (4000 / 800);
  if (depth_m <= 4000) return 7500 + (depth_m - 1000) * (8000 / 3000);
  if (depth_m <= 6000) return 15500 + (depth_m - 4000) * (5000 / 2000);
  if (depth_m <= 11000) return 20500 + (depth_m - 6000) * (11000 / 5000);
  alert("Depth out of range!");
  return 0;
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
  const SPEED = 10;     // px / s  – tweak to taste

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
   SURFACE WAVE EFFECTS – subtle wiggles for top layers
   Applies to layers: front, 6, 7, 8, 9 when near surface (depth ≤ 100)
   Adds soft horizontal sway to layer 5 (the boat)
   ──────────────────────────────────────────────────────────────── */

/* ────────────────────────────────────────────────────────────────
   RANDOMISED SURFACE DISTORTIONS  ✨
   • Layers front, layer6-9 : small, unsynchronised X+Y wiggles when depth ≤ 100 m
   • Layer layer5 (boat)   : lazy figure-8 bob (side-to-side + up-down)
   ──────────────────────────────────────────────────────────────── */
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
      const active = (depth === undefined || depth <= 100);
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












/* birds.js  – asynchronous flapping + asymmetric wing‑beat  */

/* birds.js – asynchronous flapping, strong climb, gentle glide */

(function initBirds () {
  const container = document.getElementById('birds-view');

  /* ---------- tweakables ---------- */
  const FLOCK_SIZE   = 3;
  const FLAP_CYCLE   = 5000;               // ms – 0.9 s wing‑beat
  const FLIGHT_MIN   = 30000;             // 10 s
  const FLIGHT_VAR   = 4000;              // +0‑6 s random
  const SPAWN_EVERY  = 40000;              // 7 s
  const SPAWN_JITTER = 5000;              // +0‑5 s

  /* ---------- helper ---------- */
  function spawnBirdFlock () {
    for (let i = 0; i < FLOCK_SIZE; i++) {

      const bird = document.createElement('div');
      bird.className = 'bird';

      /* altitude 10‑35 vh + 2 vh offset per flock member */
      bird.style.top = `${ 10 + Math.random()*25 + i*2 }vh`;

      /* per‑bird size via CSS var so transform stays animatable */
      bird.style.setProperty('--s', (0.7 + Math.random()*0.4).toFixed(2));

      const dur   = FLIGHT_MIN + Math.random()*FLIGHT_VAR;      // flight time
      const phase = Math.random()*FLAP_CYCLE;                   // random offset

      /* --- CLIMB: flap --- */
      bird.style.animation =
        `birdFlight ${dur}ms linear forwards 0ms, ` +
        `flap ${FLAP_CYCLE}ms steps(2,end) infinite -${phase}ms`;

      container.appendChild(bird);

      /* --- GLIDE (second 60 %) --- */
      setTimeout(() => {
        bird.style.animation =
          `birdFlight ${dur}ms linear forwards 0ms, ` +
          `glide ${FLAP_CYCLE}ms linear infinite -${phase}ms`;
      }, dur * 0.40);          // 0‑40 % timeline = climb

      /* cleanup when off‑screen */
      setTimeout(() => bird.remove(), dur);
    }
  }

  /* fire first flock immediately, then at random intervals */
  spawnBirdFlock();
  setInterval(
    spawnBirdFlock,
    SPAWN_EVERY + Math.random()*SPAWN_JITTER
  );
})();










/* ─ Sparkle factory ─────────────────────────────────────────── 
const sparkleContainer = document.getElementById('sparkle-container');
const NUM_SPARKLES = 60;                    

function resetSparkle(el) {

  el.style.left = (Math.random() * 100) + 'vw';
  el.style.top  = (Math.random() * 100) + '%';

  el.style.animationDuration = (2 + Math.random() * 3) + 's';
  el.style.animationDelay    = (Math.random() * 3) + 's';
}

for (let i = 0; i < NUM_SPARKLES; i++) {
  const s = document.createElement('span');
  s.className = 'sparkle';
  resetSparkle(s);

  s.addEventListener('animationiteration', () => resetSparkle(s));
  sparkleContainer.appendChild(s);
}


function toggleSparkles(visible) {
  sparkleContainer.style.opacity = visible ? '1' : '0';
}


const originalGoToDepth = goToDepth;
goToDepth = function () {
  originalGoToDepth();
  // user pressed Go → hide glitter
  toggleSparkles(false);
};


const originalAnimationLoop = animationLoop;
animationLoop = function (ts) {
  toggleSparkles(!depthMode);   
  originalAnimationLoop(ts);
};
*/













// Load layers from HTML
const layers = Array.from(document.querySelectorAll(".parallax-layer")).map(img => ({
  el: img,
  id: img.dataset.layer,
  depthFactor: parseFloat(img.dataset.depth)
}));

// App state
let currentDepth = 0;
let depthMode = false;

// Handle user clicking "Go"
function goToDepth() {
  const input = document.getElementById("depth-input");
  const depth = parseFloat(input.value);
  if (!isNaN(depth)) {
    currentDepth = depth;
    depthMode = true;
  }
}

// Animation loop — always running
function animationLoop(timestamp) {
  const baseY = depthMode
    ? depthToPixel(currentDepth) - window.innerHeight / 2
    : 0;

  for (const { el, id, depthFactor } of layers) {
    const layerY = baseY * depthFactor;

    const baseHook = behaviorHooks[id];
    const extraHook = behaviorHooksOverlay(id);

    if (baseHook) baseHook(el, currentDepth, layerY, timestamp);
    if (extraHook) extraHook(el, currentDepth, layerY, timestamp);

    if (!baseHook && !extraHook) {
      el.style.transform = `translate(-50%, ${-layerY}px)`;
    }

  }

  requestAnimationFrame(animationLoop);
}

// Initialize
window.addEventListener("DOMContentLoaded", () => {
  // Start from top of image
  for (const { el } of layers) {
    el.style.transform = `translate(-50%, 0px)`;
  }

  document.getElementById("depth-input").value = '';
  depthMode = false;

  requestAnimationFrame(animationLoop); // always run
});

