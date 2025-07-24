/* ─────────────────────────────────────────────
   Deep-Sea Viewer – consolidated JS (NO BIRDS)
   ───────────────────────────────────────────── */
const TILE_H = 1000;          // must match tiler
//let tileLayers = [];          // filled in setupLazyTiles()

/* (Optional) service worker – harmless if sw.js missing */
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js').catch(()=>{});
}

/* Debug: first error catcher (so silent errors don't freeze unnoticed) */
window.addEventListener('error', e => {
  console.error('✗ Runtime error:', e.message, e.filename+':'+e.lineno);
});

/* Tiny on-screen FPS / depth debug */
(function makeDebugOverlay(){
  const box = document.createElement('div');
  box.id = 'debugBox';
  Object.assign(box.style,{
    position:'fixed',top:'4px',right:'6px',font:'12px/1.2 monospace',
    background:'rgba(0,0,0,.5)',color:'#fff',padding:'4px 6px',
    zIndex:9999,borderRadius:'4px',pointerEvents:'none'
  });
  box.textContent='init…';
  document.addEventListener('DOMContentLoaded',()=>document.body.appendChild(box));
})();

/* ── depth → pixel mapping (your original) ── */
const depthCache = new Map();
function depthToPixelMemo(d){ if(!depthCache.has(d)) depthCache.set(d, depthToPixel(d)); return depthCache.get(d);}
function depthToPixel(m){
  if(m < 0)      return 2000 - m * (1000 / 20);  
  if(m <= 200)   return 1000 + m * (2500 / 200);
  if(m <= 1000)  return 3500 + (m - 200) * (4000 / 800);
  if(m <= 4000)  return 7500 + (m - 1000) * (8000 / 3000);
  if(m <= 6000)  return 15500 + (m - 4000) * (5000 / 2000);
  if(m <= 11000) return 20500 + (m - 6000) * (5000 / 5000);
  return 25500 + (m - 11000) * 1;  // arbitrary extension
}

let lastRenderedDepth = null;


/* ── Layer behaviour hooks (kept) ── */
const behaviorHooks = {};

behaviorHooks.layer3 = (() => {
  let prevT = null, offset = 0, imgW = null, clone = null, imgEl = null;
  const SPEED = 15;

  function setup(el){
    if (imgW !== null) return;
    imgEl = el.querySelector('img');
    if (!imgEl) return;

    imgW = imgEl.naturalWidth || imgEl.width;
    imgEl.style.transition = 'none';
    clone = imgEl.cloneNode(false);
    clone.id = 'layer3-clone';
    clone.style.transition = 'none';
    el.appendChild(clone);
  }

  return (el, _depth, baseY, t) => {
    setup(el);
    if (!imgEl) return;
    if (prevT === null) prevT = t;

    const dt = (t - prevT) / 1000;
    prevT = t;
    offset = (offset - SPEED * dt) % imgW;

    const yPx = -baseY;
    imgEl.style.transform = `translate(calc(-50% + ${offset}px), ${yPx}px)`;
    clone.style.transform = `translate(calc(-50% + ${offset + imgW}px), ${yPx}px)`;
  };
})();


/* Wave / boat overlay hooks (retained) */
const WAVE_LAYERS=['front','layer6','layer7','layer8','layer9'];
const SWAY_LAYER='layer5';
const BASE={ wave:{ampX:4,ampY:15,ampSX:0.02,freq:0.15}, boat:{ampX:4,ampY:5,freq:1.2/5} };
const waveParams={};
const orderedWaveLayers=['front','layer9','layer8','layer7','layer6'];
const AMP_DECAY=.7, FREQ_DECAY=.99;
orderedWaveLayers.forEach((name,i)=>{
  const ampMult = AMP_DECAY**i, freqMult = FREQ_DECAY**i;
  waveParams[name]={
    phaseTX:Math.random()*2*Math.PI,
    phaseTY:Math.random()*2*Math.PI,
    phaseSX:Math.random()*2*Math.PI,
    freqTX:BASE.wave.freq*freqMult*(0.9+Math.random()*0.2),
    freqTY:BASE.wave.freq*freqMult*(0.9+Math.random()*0.2),
    freqSX:BASE.wave.freq*freqMult*(0.9+Math.random()*0.2),
    ampTX: BASE.wave.ampX *ampMult*(0.9+Math.random()*0.2),
    ampTY: BASE.wave.ampY *ampMult*(0.9+Math.random()*0.2),
    ampSX: BASE.wave.ampSX*ampMult*(0.9+Math.random()*0.2)
  };
});


const boatParam={ phase:Math.random()*2*Math.PI, ampX:BASE.boat.ampX, ampY:BASE.boat.ampY, freq:BASE.boat.freq };

const behaviorHooksOverlay = name=>{
  if(WAVE_LAYERS.includes(name)){
    const p=waveParams[name];
    return (el,depth,baseY,t)=>{
      const active = true;
      const time=t/1000;
      const dx  = active? Math.sin(2*Math.PI*p.freqTX*time + p.phaseTX)*p.ampTX:0;
      const dy  = active? Math.cos(2*Math.PI*p.freqTY*time + p.phaseTY)*p.ampTY:0;
      const sX  = active? 1+Math.sin(2*Math.PI*p.freqSX*time + p.phaseSX)*p.ampSX:1;
      el.style.transform = `scaleX(${sX}) translate(calc(-50% + ${dx}px), ${-baseY + dy}px)`;
    };
  }
  if(name===SWAY_LAYER){
    const p=boatParam;
    return (el,_d,baseY,t)=>{
      const time=t/1000;
      const dx=Math.sin(2*Math.PI*p.freq*time + p.phase)*p.ampX;
      const dy=Math.sin(2*Math.PI*p.freq*time + p.phase + Math.PI/2)*p.ampY;
      el.style.transform = `translate(calc(-50% + ${dx}px), ${-baseY + dy}px)`;
    };
  }
  return null;
};

/* Pause / resume stubs (birds removed) */
let animPausedByUser=false;

function pauseAllMotion(){
  animPausedByUser = true;

  // Stop birds
  clearInterval(birdInterval);
  birdInterval = null;
  for (const { interval } of activeBirds) {
    clearInterval(interval);
  }
  activeBirds.clear();
  document.querySelectorAll('.bird-wrapper').forEach(b => b.remove());
}

function resumeAllMotion(){
  animPausedByUser = false;
  spawnBirdFlock();
  birdInterval = setInterval(spawnBirdFlock, 25000 + Math.random() * 5000);

  activeBirds.forEach(meta => {
    const { el } = meta;
    el.style.animationPlayState = 'running';

    const flapEvery = 3000 + Math.random() * 3000;
    const flapDuration = 150;

    meta.flapTimer = setInterval(() => {
      el.style.backgroundImage = "url('bird_down.webp')";
      setTimeout(() => {
        el.style.backgroundImage = "url('bird_up.webp')";
      }, flapDuration);
    }, flapEvery);

    const remainingTime = 5000 + Math.random() * 2000;
    meta.destroyTimer = setTimeout(() => {
      clearInterval(meta.flapTimer);
      activeBirds.delete(meta);
      el.remove();
    }, remainingTime);
  });
}


let birdInterval = null;
const activeBirds = new Set();


function spawnBirdFlock(){
  if (animPausedByUser) return;

  const container = document.getElementById('birds-view');
  const baseAlt = 8 + Math.random()*14;
  const FLOCK_SIZE = 3;

  for (let i = 0; i < FLOCK_SIZE; i++) {
    const dur = 35000 + Math.random()*5000;

    const wrap = document.createElement('div');
    wrap.className = 'bird-wrapper';

    const bird = document.createElement('div');
    bird.className = 'bird';
    wrap.appendChild(bird);
    container.appendChild(wrap);

    const scale = 0.5 + Math.random()*0.9;
    wrap.style.left = '0';
    wrap.style.transform = `scale(${scale}) translateX(120vw)`;
    wrap.style.top = `${baseAlt + i*2}vh`;
    wrap.style.setProperty('--dur', `${dur}ms`);
    wrap.style.setProperty('--wave', (10 + Math.random()*80).toFixed(1) + 'px');
    wrap.style.animation = `birdFlight var(--dur) linear forwards`;

    bird.style.backgroundImage = "url('bird_up.webp')";

    const flapEvery = 3000 + Math.random()*3000;
    const flapDuration = 150;

    const flapData = {
      bird,
      interval: setInterval(() => {
        if (animPausedByUser) return;
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










/* Depth-dependent visibility (bird code removed) */
function updateDepthDependentAssets(depth){
  const show = (id, on) => {
    const n = document.getElementById(id);
    if (n) n.style.display = on ? '' : 'none';
  };

  const pause = (ids, on) => ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.animationPlayState = on ? 'paused' : 'running';
  });

  const above200 = (depth !== undefined && depth < 200);


  // Always show birds + layer3 + 4 + 5 + back-view above 200m
  show('layer3-view', above200);
  show('layer4-view', above200);
  show('layer5-view', above200);
  show('back-view', above200);

  if (above200) {
    if (!birdInterval && !animPausedByUser) {
      spawnBirdFlock();
      birdInterval = setInterval(spawnBirdFlock, 25000 + Math.random() * 5000);
    }
  } else {
    clearInterval(birdInterval);
    birdInterval = null;
    const birdsView = document.getElementById('birds-view');
    if (birdsView) birdsView.innerHTML = '';
  }
}


/* Gather parallax layers (once DOM exists) */
let layers=[];

/* State */
let currentDepth = undefined, targetDepth = 0, depthMode = false;
let moveStart=0, moveDur=0, startDepth=0;



let overlayShown = false;

function updateBackOverlay(depth) {
  const backImg  = document.getElementById('back-img');
  const back     = document.getElementById('back-view');
  //const layer3   = document.getElementById('layer3-view');
  //const birds    = document.getElementById('birds-view');

  //if (!backImg || !back || !layer3 || !birds) return;
  if (!backImg || !back) return;
  
  const hide = depth >= 40;

  // ─── Image swap ───
  if (hide && !overlayShown) {
    backImg.src = 'back_overlay.webp';
    overlayShown = true;
  } else if (!hide && overlayShown) {
    backImg.src = 'tiles/back_0.webp';
    overlayShown = false;
  }

  // ─── Show/hide birds + layer3 ───
  //layer3.style.display = hide ? 'none' : '';
  //birds.style.display  = hide ? 'none' : '';

  // ─── z-index swap ───
  back.style.zIndex = hide ? '4' : '0';  // layer8 is z=7
}














/* Go button */
function goToDepth(){
  const inp = document.getElementById('depth-input');
  if (!inp) return;
  const v = parseFloat(inp.value);
  if (Number.isNaN(v)) return;

  const prev = (typeof currentDepth === 'number') ? currentDepth : 0;
  const dz = Math.abs(v - prev);
  const T = Math.min(7, Math.max(3, 2 + 1.5 * Math.sqrt(dz / 1000)));

  startDepth = prev;           // 💡 ensure valid number
  targetDepth = v;
  moveStart = performance.now();
  moveDur = T * 1000*2;
  depthMode = true;
}


window.goToDepth=goToDepth;




/* RAF loop */
let pausedDoc=false, frameCount=0, lastFPSStamp=0;
document.addEventListener('visibilitychange',()=>pausedDoc=document.hidden);


/* ───── helper to create / reuse slice img ───── */
function ensureSlice(layer, slice){

  if (slice < 0 || slice >= layer.total) return;
  if (layer.imgNodes[slice]) return;                 // already there

  // <img> for this slice
  const img = new Image();
  img.src   = `${layer.prefix}_${slice}.webp`;
  img.className = 'layer-img';
  img.style.top  = `${slice * TILE_H}px`;
  img.style.left = '50%';
  img.style.transform = 'translateX(-50%)';
  layer.el.appendChild(img);

  // keep reference so we don't duplicate later
  layer.imgNodes[slice] = img;

  // optional: invisible preload to guarantee decode
  preloadTile(layer.prefix, slice, layer.cache);
}

/* ───── helper to prune slices far above viewport ───── */
function pruneAbove(layer, keepFrom){
  for (const s in layer.imgNodes){
    if (+s < keepFrom){
      layer.el.removeChild(layer.imgNodes[s]);
      delete layer.imgNodes[s];
    }
  }
}



const overlayEl = document.getElementById("underwater-overlay");

function updateUnderwaterOverlay(currentDepth) {
  const frontDepth = 1.00;
  const layer7Depth = 0.40;

  const frontY = depthToPixelMemo(currentDepth * frontDepth);
  const layer7Y = depthToPixelMemo(currentDepth * layer7Depth);

  const topY = frontY + 1100;
  const bottomY = layer7Y + 777;

  const height = bottomY - topY;

  overlayEl.style.top = `${topY}px`;
  overlayEl.style.height = `${height}px`;
  overlayEl.style.left = '50%';
  overlayEl.style.transform = 'translateX(-50%)';
  overlayEl.style.width = 'auto';  // Let the image define width unless you want to constrain it
}









function raf(ts){
  if (pausedDoc){ requestAnimationFrame(raf); return; }

  const doingDepthAnimation = depthMode || typeof currentDepth === 'number';

    if (depthMode){
      const e = ts - moveStart;
      const t = Math.min(1, e / moveDur);
      const s = 0.5 * (1 - Math.cos(Math.PI * t)); // new easing
      currentDepth = (e >= moveDur)
          ? targetDepth
          : startDepth + (targetDepth - startDepth) * s;
      if (e >= moveDur) depthMode = false;
    }


  const hasDepth = typeof currentDepth === 'number';
  if (hasDepth) updateDepthDependentAssets(currentDepth);
  if (hasDepth) updateBackOverlay(currentDepth);
  const baseY = hasDepth ? depthToPixelMemo(currentDepth) - innerHeight / 2 : 0;

  if (hasDepth) {
  updateUnderwaterOverlay(currentDepth);}


  for (const layer of layers){
    const {el, depthFactor} = layer;
    const yLayer = baseY * depthFactor;

    // Only apply translate if we have a defined depth
    const slice  = Math.floor(yLayer / TILE_H);
    const offset = -(yLayer % TILE_H);

    // Only load and move tiles if user entered a depth
    if (hasDepth && layer.total > 1){
      for (let s = slice - 1; s <= slice + 2; s++) {
        ensureSlice(layer, s);
      }

      // Prune unused tiles
      const buffer = 5;
      for (const s in layer.imgNodes) {
        if (s < slice - buffer || s > slice + buffer) {
          layer.el.removeChild(layer.imgNodes[s]);
          delete layer.imgNodes[s];
        }
      }

      el.style.transform = `translate(-50%, ${offset}px)`;
    }

    // Animation hooks still run even when idle
    const h1 = behaviorHooks[layer.id];
    const h2 = behaviorHooksOverlay(layer.id);
    if (!animPausedByUser){
      if (h1) h1(el, hasDepth ? currentDepth : undefined, yLayer, ts);
      if (h2) h2(el, hasDepth ? currentDepth : undefined, yLayer, ts);
    }
  }
  


  /* FPS overlay */
  frameCount++;
  if (ts - lastFPSStamp > 250){
    const fps = frameCount * 1000 / (ts - lastFPSStamp);
    const box = document.getElementById('debugBox');
    if (box) box.textContent =
      `fps:${fps.toFixed(1)}  depth:${hasDepth ? currentDepth.toFixed(1) : '—'}`;
    lastFPSStamp = ts; frameCount = 0;
  }

  requestAnimationFrame(raf);
}





/* Buttons */
function wireUpButtons(){
  const toggle=document.getElementById('anim-toggle');
  if(toggle){
    toggle.addEventListener('click',()=>{
      if(animPausedByUser){ resumeAllMotion(); toggle.textContent='Pause animation'; }
      else { pauseAllMotion(); toggle.textContent='Resume animation'; }
    });
  }
}


function preloadTile(prefix, n, cache){
  if (n in cache) return;  // already cached

  const url = `${prefix}_${n}.webp`;
  const img = new Image();
  img.src = url;

  // Force it into memory: append it to the invisible preload zone
  img.style.width = '1px';
  img.style.height = '1px';
  img.style.opacity = '0';
  img.style.pointerEvents = 'none';

  document.getElementById('preload-zone').appendChild(img);
  cache[n] = img;
}








































/* ── Single startup path ── */
window.addEventListener('DOMContentLoaded', () => {
  // 1) Wire up your pause/resume button
  wireUpButtons();


  // 3) Build an offscreen preload zone so images decode ahead of time
  const preloadZone = document.createElement('div');
  preloadZone.id = 'preload-zone';
  Object.assign(preloadZone.style, {
    position: 'fixed',
    left: '-9999px',
    top: '-9999px',
    width: '1px',
    height: '1px',
    overflow: 'hidden'
  });
  document.body.appendChild(preloadZone);

  // And the back‑overlay
  const preloadOverlay = new Image();
  preloadOverlay.src = 'back_overlay.webp';
  preloadZone.appendChild(preloadOverlay);

  // 4) Gather your parallax layers
  layers = Array.from(document.querySelectorAll('.parallax-layer'))
    .map(el => {
      const tileImg = el.querySelector('img[data-prefix]');
      if (!tileImg) {
        // non‑tiled layers (e.g. birds-view)
        return {
          el,
          id: el.dataset.layer,
          depthFactor: +el.dataset.depth,
          total: 0,
          prefix: '',
          cache: {},
          imgNodes: {}
        };
      }

      const prefix = tileImg.dataset.prefix;
      const total  = Number(tileImg.dataset.tiles);
      const cache  = {};

      // Preload first few tiles
      for (let k = 0; k < Math.min(10, total); k++) {
        preloadTile(prefix, k, cache);
      }

      return {
        el,
        id: el.dataset.layer,
        depthFactor: +el.dataset.depth,
        total,
        prefix,
        cache,
        imgNodes: { 0: tileImg }
      };
    });

  document.body.classList.add('ready');

  // 5) Only start the RAF loop once our overlay image dimensions are known
  function startLoop() {
    requestAnimationFrame(raf);
    // birds start regardless of image load
    spawnBirdFlock();
    birdInterval = setInterval(spawnBirdFlock, 25000 + Math.random() * 5000);
  }

});




