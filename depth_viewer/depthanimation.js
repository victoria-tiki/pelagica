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
    position:'fixed',bottom:'4px',left:'6px',font:'12px/1.2 monospace',
    background:'rgba(0,0,0,.5)',color:'#fff',padding:'4px 6px',
    zIndex:9999,borderRadius:'4px',pointerEvents:'none'
  });
  box.textContent='init…';
  document.addEventListener('DOMContentLoaded',()=>document.body.appendChild(box));
})();

/* Hide the control overlay when the page is running inside Pelagica */
if (window.self !== window.top) {        // we are inside an <iframe>
  window.addEventListener('DOMContentLoaded', () => {
    const ui = document.getElementById('ui');
    if (ui) ui.style.display = 'none';
  });
}


/* ── depth → pixel mapping (your original) ── */
const depthCache = new Map();
function depthToPixelMemo(d){ if(!depthCache.has(d)) depthCache.set(d, depthToPixel(d)); return depthCache.get(d);}

/*function depthToPixel(m){
  if(m < 0)      return 2000 - m * (1000 / 20);  
  if(m <= 200)   return 1000 + m * (2500 / 200);
  if(m <= 1000)  return 3500 + (m - 200) * (4000 / 800);
  if(m <= 4000)  return 7500 + (m - 1000) * (8000 / 3000);
  if(m <= 6000)  return 15500 + (m - 4000) * (5000 / 2000);
  if(m <= 11000) return 20500 + (m - 6000) * (5000 / 5000);
  return 25500 + (m - 11000) * 1;  // arbitrary extension
}*/

function depthToPixel(m) {
  if (m < 0) {
    return 2000 - m * (1000 / 20);
  } else if (m <= 200) {
    return 1000 + m * (2500 / 200);
  } else if (m <= 1000) {
    return 3500 + (m - 200) * (4000 / 800);
  } else if (m <= 4000) {
    return 7500 + (m - 1000) * (8000 / 3000);
  } else if (m <= 6000) {
    return 15500 + (m - 4000) * (6000 / 2000);  
  } else if (m <= 11000) {
    return 21500 + (m - 6000) * (10000 / 5000); 
  } else {
    return 31500 + (m - 11000) * 1; 
  }
}



let lastRenderedDepth = null;
/* put near your other globals */
let introTween   = null;   // {baseFrom, baseTo, start, dur}
let pendingDepth = null;   // the depth the user really asked for
let frozenTime = null;   // null while live, a Number while paused




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
const WAVE_LAYERS=['front','layer6','layer7','layer8','layer9','underwater', 'ruler'];
const SWAY_LAYER='layer5';
const BASE={ wave:{ampX:4,ampY:20,ampSX:0.02,freq:0.15}, boat:{ampX:4,ampY:5,freq:1.2/5} };
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
waveParams.underwater = waveParams.front;
waveParams.ruler=waveParams.front;

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

/* ───── user‑controlled pause / resume ───── */

function applyGlobalFreeze(freeze){
  document.body.classList.toggle('paused', freeze);     // toggles the CSS rule above
  // also pause / resume any element that was animated purely via JS timers
  if (freeze){
    clearInterval(birdInterval);            // stop new birds
    activeBirds.forEach(({interval, flapTimer, destroyTimer, el})=>{
      clearInterval(interval);
      clearInterval(flapTimer);
      clearTimeout (destroyTimer);
      el.style.animationPlayState = 'paused';
    });
  }else{
    spawnBirdFlock();                       // restart flock
    birdInterval = setInterval(spawnBirdFlock, 25000 + Math.random()*5000);
    activeBirds.forEach(({el})=> el.style.animationPlayState='running');
  }
}

/* ——— user‑controlled pause / resume ——— */
let animPausedByUser = false;

function pauseAllMotion () {
  if (animPausedByUser) return;
  animPausedByUser = true;

  /* ── if a depth tween is running, finish one eased step and stop it ── */
  if (depthMode) {
    const now   = performance.now();
    const frac  = Math.min(1, (now - moveStart) / moveDur);
    const eased = easeTriPhase(frac);

    const y0    = depthToBaseY(startDepth);
    const y1    = depthToBaseY(targetDepth);
    const baseY = y0 + (y1 - y0) * eased;

    currentDepth = baseYToDepth(baseY);   // lock camera here
    depthMode    = false;                 // cancel tween
  }

  frozenTime = performance.now();         // remember this moment
  applyGlobalFreeze(true);                // stop CSS keyframes + JS timers
}

function resumeAllMotion () {
  if (!animPausedByUser) return;
  animPausedByUser = false;

  frozenTime = null;                      // hooks get live time again
  applyGlobalFreeze(false);
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
  back.style.zIndex = hide ? '5' : '0';  // layer8 is z=7
}



/* persistent across frames */
let currentH = 100;                 // matches the 100 px CSS default

/* wrapper that eases height but leaves your mapping untouched */
function updateUnderwaterEased(depth){
  const targetH = updateUnderwater(depth);   // the height your logic already returns
  const SPEED   = 0.05;                      // 0.1 = very slow, 0.3 = snappier

  currentH += (targetH - currentH) * SPEED;  // one‑line lerp
  underwaterImg.style.height = currentH + 'px';
}



function updateUnderwater(depthMeters) {
  if (!underwaterImg || typeof depthMeters !== 'number') return;

  const depthPx = depthToPixelMemo(depthMeters); // meters → px
  const baseY = depthPx - innerHeight / 2;

  const topY = 1150;
  const bottomY = 800 + depthPx * 0.4;//777 + depthPx * 0.4;

  let h = bottomY - topY;

  // Clamp h between 77 and 477
  //h = Math.max(100, Math.min(h, 520));

  underwaterImg.style.height = `${h}px`;
  //return h;

  // Debug
  //console.log(`depth=${depthMeters}m → baseY=${baseY}px → clamped height=${h}px`);
}









/* 4‑a  start animation when we get a message */
window.addEventListener("message", (e) => {
  const t = e.data?.type;
  if (t === "startAnimation") {
    const d = Number(e.data.depth) || 0;
    document.getElementById("depth-input").value = d;
    goToDepth();
  } else if (t === "pauseAll") {
    pauseAllMotion();
  } else if (t === "resumeAll") {
    resumeAllMotion();
  }
});


/* Go button */
function goToDepth(){
  let v = parseFloat(document.getElementById('depth-input').value);
  if (Number.isNaN(v)) return;

  // 🔒 Clamp the value to within acceptable bounds
  if (v > 11000) v = 11000;
  if (v < -20)   v = -20;

    if (animPausedByUser) {
      /* no tween – just teleport */
      depthMode    = false;
      currentDepth = v;          
      window.parent.postMessage({ type: "animationDone" }, "*");
      return;
    }


  /* ——— first ever jump (currentDepth is still undefined) ——— */
  if (typeof currentDepth !== 'number'){
    introTween = {
      baseFrom : 0,                                          // default view
      baseTo   : depthToPixelMemo(0) - innerHeight/2,        // where 0 m lives
      start    : performance.now(),
      dur      : 900                                         // ms – tweak to taste
    };
    pendingDepth = v;        // remember the user’s real request
    return;                  // <- normal depth tween waits
  }

  /* ——— all subsequent jumps use your existing code ——— */
  const prev = currentDepth;
  const dz = Math.abs(v - prev);      // metres to travel
  const MIN_T = 1.5;                  // never shorter than 1.5 s
  const MAX_T = 7;                    // keep your long‑dive ceiling
  const T = Math.min(MAX_T,MIN_T + 1.25 * Math.pow(dz / 800, 0.75));


  startDepth = prev;
  targetDepth = v;
  moveStart = performance.now();
  moveDur   = T * 1000 * 2;
  depthMode = true;

}





window.goToDepth=goToDepth;


/* helper: pixel position (top of viewport) for any depth */
function depthToBaseY(d){
  return depthToPixelMemo(d) - innerHeight / 2;
}

/* inverse helper – returns metres for a given baseY */
function baseYToDepth(y){
  const p = y + innerHeight/2;   /* surface & air */
  if (p < 1000)                    return -(p - 2000) * (20 / 1000);/* 0‑200 m  */
  if (p < 3500)                    return (p - 1000) * (200  / 2500);/* 200‑1000 m ( 5   px / m) */
  if (p < 7500)                    return 200  + (p - 3500) * (800  / 4000);/* 1‑4 km    ( 8/3 px / m) */
  if (p < 15500)                   return 1000 + (p - 7500) * (3000 / 8000);/* 4‑6 km    ( 3   px / m) */
  if (p < 21500)                   return 4000 + (p - 15500) * (2000 / 6000);/* 6‑11 km   ( 2   px / m) */
  if (p < 31500)                   return 6000 + (p - 21500) * (5000 / 10000);/* tail      ( 1   px / m) */
  return 11000 + (p - 31500);
}


/* three‑phase ease used *only* for pixels */
function easeTriPhase(t){
  const T1 = 0.15, T2 = 0.85;
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  const S = 1 / (0.5*T1 + (T2 - T1) + 0.5*(1 - T2));
  if (t < T1) { const a = S / T1; return 0.5 * a * t * t; }
  if (t < T2) { const y1 = 0.5 * S * T1; return y1 + S * (t - T1); }
  const y1 = 0.5 * S * T1, y2 = y1 + S * (T2 - T1);
  const dt = t - T2, d = 1 - T2, a = -S / d;
  return y2 + S * dt + 0.5 * a * dt * dt;
}





/* RAF loop */
let pausedDoc=false, frameCount=0, lastFPSStamp=0;
document.addEventListener('visibilitychange',()=>pausedDoc=document.hidden);


/* -----------------------------------------------
   Decide once: do we need a 1-px vertical overlap?
   true  = Blink (Chrome / Edge / Chromium / Opera / Brave)  OR  old WebKit
   false = Firefox OR modern Safari (WebKit 615+)
------------------------------------------------ */
const ua = navigator.userAgent;

const isBlink   = !!window.chrome || /\bEdg\//.test(ua) || /\bOPR\//.test(ua);
const isFirefox = /\bFirefox\//.test(ua);

let needsOverlap = false;

if (isBlink) {
  needsOverlap = true;                         
} else if (isFirefox) {
  needsOverlap = false;                        
} else {
  /* WebKit – decide by version */
  const m = ua.match(/AppleWebKit\/(\d+)/);
  const wk = m ? parseInt(m[1], 10) : 0;
  needsOverlap = wk && wk < 615;               
}




/* ───── helper to create / reuse slice img ───── */
async function ensureSlice(layer, slice){
  if (slice < 0 || slice >= layer.total) return;
  if (layer.imgNodes[slice])             return;

  const img = await preloadTile(layer.prefix, slice, layer.cache);

  /* (styling block unchanged) */
  img.className = 'layer-img';
  img.style.top    = `${slice * TILE_H - (needsOverlap?1:0)}px`;
  img.style.height = `${TILE_H + (needsOverlap?1:0)}px`;
  if (layer.id === 'ruler'){
    img.style.left='auto'; img.style.right='0'; img.style.transform='translateX(0)';
  }else{
    img.style.left='50%';  img.style.transform='translateX(-50%)';
  }

  layer.el.appendChild(img);
  layer.imgNodes[slice] = img;
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

let lastFrameDepth = null;
/* one shared handle; resolved the first time we enter raf() */
let fpsBox = null;

/* helper – applies translate3d only when the offset changes */
function applyParallax(layer, offsetCssPx) {
  const dpr    = window.devicePixelRatio || 1;
  const ySnap  = Math.round(offsetCssPx * dpr) / dpr;   // ← physical‑pixel snap

  if (layer.prevOffset !== ySnap) {
    layer.el.style.transform = `translate3d(-50%, ${ySnap}px, 0)`;
    layer.prevOffset = ySnap;
  }
}



function raf(ts) {

  /* lazy‑cache the overlay node (debugBox is appended at DOMContentLoaded) */
  if (!fpsBox) fpsBox = document.getElementById('debugBox');

  /* -------- intro slide‑in (runs only once) -------- */
  if (introTween) {
    const { baseFrom, baseTo, start, dur } = introTween;
    const t      = Math.min(1, (ts - start) / dur);
    const eased  = 0.5 * (1 - Math.cos(Math.PI * t));
    const baseY  = baseFrom + (baseTo - baseFrom) * eased;

    layers.forEach(layer => {
      const yLayer = baseY * layer.depthFactor;
      const slice  = Math.floor(yLayer / TILE_H);
      const offset = -(yLayer % TILE_H);

      if (layer.total > 1) {
        /* ➜ draw slices that can actually enter the viewport within ~2 screens */
        for (let s = slice - 1; s <= slice + 4; s++) ensureSlice(layer, s);

        /* ➜ silently decode another five; they’ll be ready when we scroll down */
        //for (let s = slice + 5; s <= slice + 10; s++) preloadTile(layer.prefix, s, layer.cache);

        applyParallax(layer, offset);
      }

      const h1 = behaviorHooks[layer.id];
      const h2 = behaviorHooksOverlay(layer.id);
      if (!animPausedByUser) {
        if (h1) h1(layer.el, undefined, yLayer, ts);
        if (h2) h2(layer.el, undefined, yLayer, ts);
      }
    });

    if (t >= 1) {                      // intro finished – hand off to depth tween
      currentDepth = 0;
      introTween   = null;
      if (pendingDepth !== null) { goToDepth(pendingDepth); pendingDepth = null; }
    }

    requestAnimationFrame(raf);
    return;
  }

  /* -------- regular depth tween -------- */
  if (!animPausedByUser && depthMode) {
    const frac = (ts - moveStart) / moveDur;
    if (frac >= 1) {
      currentDepth = targetDepth;
      depthMode = false;
      
      //console.log("[viewer] tween finished – sending animationDone");
      window.parent.postMessage({ type: "animationDone" }, "*");
  
    } else {
      const y0 = depthToBaseY(startDepth);
      const y1 = depthToBaseY(targetDepth);
      const baseY = y0 + (y1 - y0) * easeTriPhase(frac);
      currentDepth = baseYToDepth(baseY);
    }
  }

  /* -------- steady‑state paint -------- */
  const hasDepth = typeof currentDepth === 'number';
  if (hasDepth) {
    updateDepthDependentAssets(currentDepth);
    updateBackOverlay(currentDepth);
  }
  const baseY = hasDepth ? depthToPixelMemo(currentDepth) - innerHeight / 2 : 0;

  for (const layer of layers) {
    const yLayer = baseY * layer.depthFactor;
    const slice  = Math.floor(yLayer / TILE_H);
    const offset = -(yLayer % TILE_H);

    if (hasDepth && layer.total > 1) {
      for (let s = slice - 1; s <= slice + 2; s++) ensureSlice(layer, s);

      /* prune off‑screen tiles (buffer ±5) */
      for (const s in layer.imgNodes) {
        if (s < slice - 5 || s > slice + 5) {
          layer.el.removeChild(layer.imgNodes[s]);
          delete layer.imgNodes[s];
        }
      }
      applyParallax(layer, offset);
    }

    const tNow = frozenTime ?? ts;
    const h1 = behaviorHooks[layer.id];
    const h2 = behaviorHooksOverlay(layer.id);
    if (h1) h1(layer.el, hasDepth ? currentDepth : undefined, yLayer, tNow);
    if (h2) h2(layer.el, hasDepth ? currentDepth : undefined, yLayer, tNow);
  }

  if (hasDepth) updateUnderwater(currentDepth);

  /* FPS overlay – only if the node exists */
  frameCount++;
  if (fpsBox && ts - lastFPSStamp > 250) {
    const fps = frameCount * 1000 / (ts - lastFPSStamp);
    fpsBox.textContent =
      `fps:${fps.toFixed(1)}  depth:${hasDepth ? currentDepth.toFixed(1) : '—'}`;
    lastFPSStamp = ts;
    frameCount   = 0;
  }

  requestAnimationFrame(raf);
}

/* initialise memoised offset once, right after you build `layers` */
layers.forEach(l => { l.prevOffset = NaN; });



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



/* keeps one promise per URL so we don’t start the same fetch twice */
const decodeCache = new Map();

function preloadTile(prefix, n, cache){
  const url = `${prefix}_${n}.webp`;
  if (decodeCache.has(url)) return decodeCache.get(url);   // reuse

  const img = new Image();
  img.src = url;

  const p = ('decode' in img)
      ? img.decode().then(()=>img)         // modern browsers
      : new Promise(res => img.onload = () => res(img));

  decodeCache.set(url, p);
  cache[n] = p;                            // your per‑layer cache still works
  return p;
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
    
    const preloadOverlay = new Image();
    preloadOverlay.src = 'back_overlay.webp';
    preloadZone.appendChild(preloadOverlay);



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
      imgNodes: { 0: img }
    };
  });

  document.body.classList.add('ready');
  requestAnimationFrame(raf);

  spawnBirdFlock();
  birdInterval = setInterval(spawnBirdFlock, 25000 + Math.random() * 5000);
});




