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
const WAVE_LAYERS=['front','layer6','layer7','layer8','layer9','underwater'];
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
// make the overlay use *exactly* the same phases & amps as 'front'
waveParams.underwater = waveParams.layer9;

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
let underwaterImg;
let underwaterHeightPx = 0;



function updateUnderwater(depth){
  if (!underwaterImg) return;

  const minH = 0;      // px when overlay is “off”
  const maxH = 900;   // px at full stretch
  const dMax = 100;    // how many metres it takes to reach maxH

  const START = 10;                 // overlay shouldn’t grow before 20 m
  if (depth == null || depth < START){ underwaterImg.style.height = `${minH}px`; return; }


  const d = Math.min(depth - START, dMax);   // 0 → dMax once we’ve passed 20 m
  const h = minH + (maxH - minH) * (d / dMax);
  underwaterImg.style.height = `${h}px`;
}

/*
function updateUnderwater(depth){
  if (!underwaterImg) return;

  const START   = 10;
  const GROW    = 100;
  const minH    =   0;
  const maxH    = 900;

  if (depth == null || depth < START) {
    var targetH = minH;
  } else {
    const dClamped = Math.min(depth, START + GROW);
    const baseY0   = depthToPixelMemo(START);
    const baseYc   = depthToPixelMemo(dClamped);
    const moved    = baseYc - baseY0;
    const fullMove = depthToPixelMemo(START + GROW) - baseY0;
    const t        = Math.max(0, Math.min(moved / fullMove, 1));
    var targetH = minH + t * (maxH - minH);
  }

  // Ease underwaterHeightPx toward targetH
  const speed = 0.2;  // smaller = slower (e.g. 0.05 = very slow)
  underwaterHeightPx += (targetH - underwaterHeightPx) * speed;

  underwaterImg.style.height = `${underwaterHeightPx}px`;
}*/





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
  moveDur = T * 1000/2;
  depthMode = true;
}


window.goToDepth=goToDepth;


/*function tileExists (prefix, n) {
  const key = prefix + '_' + n;
  if (tileExists.cache[key] !== undefined) return tileExists.cache[key];
  const img = new Image();
  img.src = `${prefix}_${n}.webp`;
  tileExists.cache[key] = true;     // assume it will succeed
  img.onerror = () => tileExists.cache[key] = false;
  return true;
}
tileExists.cache = Object.create(null);*/



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



function raf(ts){
  if (pausedDoc){ requestAnimationFrame(raf); return; }

  const doingDepthAnimation = depthMode || typeof currentDepth === 'number';

  if (depthMode){
    const e = ts - moveStart, t = Math.min(1, e / moveDur);
    const s = 3*t*t - 2*t*t*t;
    currentDepth = (e >= moveDur)
        ? targetDepth
        : startDepth + (targetDepth - startDepth) * s;
    if (e >= moveDur) depthMode = false;
  }

  const hasDepth = typeof currentDepth === 'number';
  if (hasDepth) updateDepthDependentAssets(currentDepth);
  const baseY = hasDepth ? depthToPixelMemo(currentDepth) - innerHeight / 2 : 0;
  updateUnderwater(hasDepth ? currentDepth : null);

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







/*function swapSlice(L,n){
  L.img.src = `${L.prefix}_${n}.webp`;
  L.loaded = n;
}*/

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

/* Tile layer list 
function setupLazyTiles(){
tileLayers = [];
document.querySelectorAll('.layer-view').forEach(view=>{
  const img = view.querySelector('img[data-prefix]');
  if (!img) return;                 // skip non‑tiled wrappers
  tileLayers.push({
    img,
    prefix : img.dataset.prefix,
    total  : +img.dataset.tiles,
    depthF : +view.dataset.depth,
    loaded : -1
  });
});
}*/

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






/* Single startup path */
window.addEventListener('DOMContentLoaded', () => {
  wireUpButtons();
  underwaterImg = document.getElementById('underwater-img');


  // ✅ Create preload zone first
  const preloadZone = document.createElement('div');
  preloadZone.id = 'preload-zone';
  preloadZone.style.cssText = 'position:fixed; left:-9999px; top:-9999px; width:1px; height:1px; overflow:hidden;';
  document.body.appendChild(preloadZone);
  
    const uwPre = new Image();
    uwPre.src = underwaterImg.src;
    preloadZone.appendChild(uwPre);


  layers = Array.from(document.querySelectorAll('.parallax-layer')).map(el => {
    const img = el.querySelector('img');

    if (!img) {
      // Skip layers like birds-view that don't use tiled images
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

    const prefix = img.dataset.prefix;
    const total  = +img.dataset.tiles;
    const cache  = {};

    // Preload first few tiles
    for (let k = 0; k <= 10 && k < total; k++) {
      preloadTile(prefix, k, cache);
    }


    return {
      el,
      id: el.dataset.layer,
      depthFactor: +el.dataset.depth,
      total,
      prefix,
      cache,
      // ✅ Fix: Register existing slice 0 image to prevent duplication
      imgNodes: { 0: img }
    };
    
    
    
    
    
    
    
    
    
    
  });

  document.body.classList.add('ready');
  requestAnimationFrame(raf);

  spawnBirdFlock();
  birdInterval = setInterval(spawnBirdFlock, 25000 + Math.random() * 5000);
});




/* ─── bubble strip, world‑Y 900‑1500, aligned every frame ─── 
(function bubbleStrip(){

  const WORLD_TOP    = 900;          // world px where strip starts
  const STRIP_H      = 600;          // → 1500
  const SPAWN_MS     = 350;          // spawn cadence (lower = more)
  const BUBBLES_PT   = 5;            // bubbles each tick
  const MIN_SIZE     = 22;           // px
  const MAX_SIZE     = 48;           // px
  const DUR_MIN      = 5;            // s
  const DUR_MAX      = 8;            // s


  const strip = document.body.appendChild(document.createElement('div'));
  strip.id = 'bubble-layer';


  function spawn(){
    const s = MIN_SIZE + Math.random()*(MAX_SIZE - MIN_SIZE);
    const b = document.createElement('div');
    b.className = 'bubble';
    b.style.width  = b.style.height = s + 'px';
    b.style.left   = Math.random()*innerWidth + 'px';
    b.style.setProperty('--dur',
      (DUR_MIN + Math.random()*(DUR_MAX-DUR_MIN)) + 's');
    strip.appendChild(b);
    b.addEventListener('animationend', () => b.remove());
  }


  setInterval(() => { for(let i=0;i<BUBBLES_PT;i++) spawn(); }, SPAWN_MS);


  const orig = window.updateDepthDependentAssets;
  window.updateDepthDependentAssets = function(depth){
    orig.apply(this, arguments);

    if(typeof depth === 'number'){
      const baseWorldTop = depthToPixelMemo(depth) - innerHeight/2;
      strip.style.top = (WORLD_TOP - baseWorldTop) + 'px';
    }
  };

  console.log('[bubbles] strip aligned & running');
})();*/

