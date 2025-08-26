
/* ─────────────────────────────────────────────
   Deep-Sea Viewer 
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
if (window.self === window.top) {  // only show debug overlay when *not* in an iframe
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
}


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


/* ─────────────────────────────────────────────
   messages 
   ───────────────────────────────────────────── */
   /* ───────── Simple caption system ───────── */
let depthBuckets = [];

fetch("messages.json")
  .then(r => r.json())
  .then(data => depthBuckets = data)
  .catch(e => console.error("Could not load messages.json", e));



let   messageBox, hideTimer;
let units = "metric";  

function formatDepth(val){
  if (units === "imperial") {
    const ft = val * 3.28084;
    return `${Math.round(ft)} ft`;
  }
  return `${Math.round(val)} m`;
}


function showMessage(txt, ms){
  if(!messageBox){
    messageBox = document.getElementById('message-box');
  }
  clearTimeout(hideTimer);
  messageBox.innerHTML = txt.replace(/\n/g,'<br>');
  messageBox.style.opacity = 1;
  if (Number.isFinite(ms) && ms>0){
    hideTimer = setTimeout(()=>messageBox.style.opacity = 0, ms);
  }
}

let lastShownMsg = null;

function randomDepthMsg(depth, direction) {
  // grab only buckets that contain at least one valid string for THIS direction
  const candidates = depthBuckets.filter(b =>
    depth >= b.min && depth <= b.max && (
      (direction === "ascend"  && b.ascend) ||
      (direction === "descend" && b.descend) ||
      b.msg
    )
  );

  // flatten all message arrays that match the direction
  const pool = candidates.flatMap(b =>
    (direction === "ascend"  && b.ascend)  ||
    (direction === "descend" && b.descend) ||
    b.msg || []
  );

  if (!pool.length) return null;        // nothing suitable found

  // don’t repeat last caption if we have >1 option
  let msg;
  do {
    msg = pool[Math.floor(Math.random() * pool.length)];
  } while (pool.length > 1 && msg === lastShownMsg);

  lastShownMsg = msg;

  // optional prefix
  const verb = direction === "ascend" ? "Ascending to"
             : direction === "descend" ? "Descending to"
             : "Traveling to";

  return `${verb} ${formatDepth(depth)}\n${msg}`;
}





/* greet on first load */
window.addEventListener('load', ()=>
  showMessage('Welcome to Pelagica!\nChoose one of 69,000 species to get started', Infinity)
);

   
   
   
   
   
   
   
   
   
   
   
   
   
   
   
   
   
   
   
   
   
   
   
   
   
   
   
   
   


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
const WAVE_LAYERS=['front','layer6','layer7','layer8','layer9','underwater', 'ruler', 'layer9p5'];
const SWAY_LAYER='layer5';
const BASE={ wave:{ampX:5,ampY:15,ampSX:0.02,freq:0.2}, boat:{ampX:4,ampY:5,freq:1.2/5} };
const waveParams={};
const orderedWaveLayers=['front','layer9p5','layer9','layer8','layer7','layer6'];
const AMP_DECAY=.9, FREQ_DECAY=.9;
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
waveParams.underwater = waveParams.layer6;
waveParams.ruler=waveParams.front;
//waveParams.layer9p5=waveParams.front;

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





















/* ─── World-anchored glitter: depths −150 m … 0 m ─────────────── */
(() => {
  const RANGE_MIN = 5, RANGE_MAX = 200;

  function buildWorldGlitter(layerId, opts){
    const layer = document.getElementById(layerId);
    if (!layer) return null;

    const {
      count   = 160,
      sizeMin = 2.0,  // tweak per layer
      sizeMax = 2.6,
      opacity = 0.55  // steady opacity (no depth gating needed)
    } = opts || {};

    const rng = (a,b)=>Math.random()*(b-a)+a;
    const frag = document.createDocumentFragment();

    for (let i=0;i<count;i++){
      const d  = rng(RANGE_MIN, RANGE_MAX);  // fixed world depth
      const x  = rng(0, 100);                // spread across width
      const yP = depthToPixelMemo(d);        // world Y (px)

      const s = document.createElement('span');
      s.className = 'sparkle';
      s.style.left = x.toFixed(2) + 'vw';
      s.style.top  = yP.toFixed(1) + 'px';   // ← world-anchored
      s.style.setProperty('--size',      rng(sizeMin, sizeMax).toFixed(2) + 'px');
      s.style.setProperty('--delay',     rng(0, 4).toFixed(2) + 's');
      s.style.setProperty('--twinkleDur',rng(2.4, 3.8).toFixed(2) + 's');
      s.style.setProperty('--driftDur',  rng(9, 14).toFixed(2) + 's');
      frag.appendChild(s);
    }

    layer.appendChild(frag);
    layer.style.pointerEvents = 'none';
    layer.style.opacity = String(opacity);

    return layer;
  }

  // Build subtle + strong using your existing IDs
  buildWorldGlitter('glitter-layer', {
    count: 160, sizeMin: 2.0, sizeMax: 2.6, opacity: 0.55
  });
  buildWorldGlitter('glitter-layer-strong', {
    count: 90,  sizeMin: 3.5, sizeMax: 4.6, opacity: 0.80
  });

  // Move with the world camera via behavior hooks (picked up in raf())
  behaviorHooks.glitterWorldA = (el, _depth, yLayer) => {
    el.style.transform = `translate3d(-50%, ${-yLayer}px, 0)`;
  };
  behaviorHooks.glitterWorldB = (el, _depth, yLayer) => {
    el.style.transform = `translate3d(-50%, ${-yLayer}px, 0)`;
  };

  // Keep old calls harmless if they still exist
  window.updateGlitterForDepth = window.updateGlitterForDepth || function(){};
})();


/* ─── Bioluminescence layer: depths 200 m … 3000 m ────────────── */
(() => {
  const RANGE_MIN = 200, RANGE_MAX = 3000;
  const COUNT = 300;                 // ~half as many as the shallow glitter
  const SIZE_MIN = 2.5, SIZE_MAX = 6.2;
  const OPACITY = 0.60;              // subtle but visible in the dark

  const layer = document.getElementById('glitter-bio');
  if (!layer) return;

  const rng = (a,b)=>Math.random()*(b-a)+a;
  const frag = document.createDocumentFragment();

  for (let i = 0; i < COUNT; i++) {
    const d   = rng(RANGE_MIN, RANGE_MAX);     // fixed world depth
    const xvw = rng(0, 100);                   // spread across width
    const yPx = depthToPixelMemo(d);           // world Y in px

    // pick a hue between green→teal→blue (approx 160°–220°)
    const h   = rng(160, 220);
    const c1  = `hsla(${h}, 100%, 65%, 0.95)`;  // bright core
    const c2  = `hsla(${h}, 100%, 50%, 0.25)`;  // colored halo

    const s = document.createElement('span');
    s.className = 'sparkle';
    s.style.left = xvw.toFixed(2) + 'vw';
    s.style.top  = yPx.toFixed(1) + 'px';

    // per-particle look
    s.style.setProperty('--size', rng(SIZE_MIN, SIZE_MAX).toFixed(2) + 'px');
    s.style.setProperty('--delay',      rng(0, 4).toFixed(2) + 's');
    s.style.setProperty('--twinkleDur', rng(2.6, 4.0).toFixed(2) + 's');
    s.style.setProperty('--driftDur',   rng(10, 16).toFixed(2) + 's');

    // green→blue glow (overrides default white)
    s.style.background = `radial-gradient(circle, ${c1} 0%, ${c2} 70%, rgba(0,0,0,0) 100%)`;
    s.style.filter     = `drop-shadow(0 0 3px ${c1})`;

    frag.appendChild(s);
  }

  layer.appendChild(frag);
  layer.style.pointerEvents = 'none';
  layer.style.opacity = String(OPACITY);

  // Move with the world camera (same pattern as your other world-anchored layers)
  behaviorHooks.glitterBio = (el, _depth, yLayer) => {
    el.style.transform = `translate3d(-50%, ${-yLayer}px, 0)`;
  };
})();



































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
    const eased = smoothest(frac);

    const y0    = depthToBaseY(startDepth);
    const y1    = depthToBaseY(targetDepth);
    const baseY = y0 + (y1 - y0) * eased;

    currentDepth = baseYToDepth(baseY);   // lock camera here
    updateGlitterForDepth(currentDepth);
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


// global state
let overlayState = 'none';        // 'none' | 'mid' | 'deep'
let lastOverlayChange = 0;
let overlayShown = false;
let deepShown    = false;   // NEW


function updateBackOverlay(depth) {
  const backImg = document.getElementById('back-img');
  const back    = document.getElementById('back-view');
  if (!backImg || !back) return;

  const hide = depth >= 43;              // keep your original cutoff
  const deep = depth > 150;              // NEW: deep starts after 100 m

  // ─── Image swap (base ↔ mid ↔ deep) ───
  if (deep) {
    if (!deepShown) {
      backImg.src = 'back_overlay_deeper.webp';  // ← use your *_deeper.webp filename
      deepShown = true;
      overlayShown = true;
    }
  } else if (hide) {
    if (deepShown || !overlayShown) {
      backImg.src = 'back_overlay.webp';
      deepShown = false;
      overlayShown = true;
    }
  } else {
    if (overlayShown || deepShown) {
      backImg.src = 'tiles/back_0.webp';
      overlayShown = false;
      deepShown = false;
    }
  }

  // keep your existing z-index behavior exactly as-is
  back.style.zIndex = hide ? '5' : '0';
}




/* persistent across frames */
/*let currentH = 50;                

function updateUnderwaterEased(depth){
  const targetH = updateUnderwater(depth);  
  const SPEED   = 0.05;                      

  currentH += (targetH - currentH) * SPEED;  
  underwaterImg.style.height = currentH + 'px';
}*/



function updateUnderwater(depthMeters) {
  if (!underwaterImg || typeof depthMeters !== 'number') return;
  
  const d = Math.max(0, depthMeters);

  const depthPx = depthToPixelMemo(d); // meters → px
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
    units = e.data?.units || "metric";
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
  if (messageBox){
   clearTimeout(hideTimer);          
    messageBox.style.opacity = 0;     
  }
  
  let v = parseFloat(document.getElementById('depth-input').value);
  if (Number.isNaN(v)) return;

  // 🔒 Clamp the value to within acceptable bounds
  if (v > 11000) v = 11000;
  if (v < -20)   v = -20;

    if (animPausedByUser) {
      /* no tween – just teleport */
      depthMode    = false;
      currentDepth = v;      
      updateGlitterForDepth(currentDepth);
      window.parent.postMessage({ type: "animationDone" }, "*");
      return;
    }


  /* ——— first ever jump (currentDepth is still undefined) ——— */
  if (typeof currentDepth !== 'number'){
    introTween = {
      baseFrom : 0,                                          // default view
      baseTo   : depthToPixelMemo(0) - innerHeight/2,        // where 0 m lives
      start    : performance.now(),
      dur      : 2200                                         // ms – tweak to taste
    };
    pendingDepth = v;        // remember the user’s real request
    updateGlitterForDepth(0);

    return;                  // <- normal depth tween waits
  }

  /* ——— all subsequent jumps use your existing code ——— */
  const prev = currentDepth;
  const dz = Math.abs(v - prev);      // metres to travel

  // decide which way we’re moving
    let direction = null;
    if (typeof currentDepth === "number") {
      direction = v < currentDepth ? "ascend"
                : v > currentDepth ? "descend"
                : null;                    
    }

  const MIN_T = 1.5;                  // never shorter than 1.5 s
  const MAX_T = 7;                    // keep your long‑dive ceiling
  let T = Math.min(MAX_T,MIN_T + 1.25 * Math.pow(dz / 800, 0.75));
  if (dz < 50) T = Math.max(0.5, T * 0.33);


  startDepth = prev;
  targetDepth = v;
  moveStart = performance.now();
  moveDur   = T * 1000 * 2.2;
  depthMode = true;
  
  window.parent.postMessage({
  type: "animationStart",
  fromDepth: startDepth,
  toDepth:   targetDepth,
  duration:  moveDur  }, "*");


    if (moveDur >= 2000 && direction) {
      const caption = randomDepthMsg(v, direction);
      if (caption) showMessage(caption, moveDur);
    }




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


function easeInOutCubic(t){
  return t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t+2, 3)/2;
}
function easeInOutQuint(t){
  return t < 0.5 ? 16*t*t*t*t*t : 1 - Math.pow(-2*t+2, 5)/2;
}

function smootherstep(t){ return t*t*t*(t*(6*t-15)+10); }
function smoothest(t){ const s = smootherstep(t); return smootherstep(s); }

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

  let img;
  try {
    img = await preloadTile(layer.prefix, slice, layer.cache);
  } catch (err) {
    // transient decode failure – cache entry was evicted; RAF will try again next frame
    return;
  }

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
    const eased  = t*t*t*(t*(6*t-15)+10);//0.5 * (1 - Math.cos(Math.PI * t));
    const baseY  = baseFrom + (baseTo - baseFrom) * eased;
    
    updateUnderwater(0);

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
      updateGlitterForDepth(0);        
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
      updateGlitterForDepth(0);        
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
  
  if (hasDepth && currentDepth !== lastFrameDepth) {
  updateGlitterForDepth(currentDepth);
  lastFrameDepth = currentDepth;}

  if (hasDepth) {
    updateDepthDependentAssets(currentDepth);
    updateBackOverlay(currentDepth);
  } else {
    updateUnderwater(0);
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
const MAX_IN_FLIGHT = 4;
const q = [];
let inFlight = 0;

function pump() {
  if (inFlight >= MAX_IN_FLIGHT || q.length === 0) return;
  const { url, resolve, reject } = q.shift();
  inFlight++;
  const img = new Image();
  img.decoding = 'async';
  img.loading  = 'eager';
  img.src = url;
  let done;
  if ('decode' in img) {
    done = img.decode().catch((err) => {
      // Fallback: if it ended up loaded anyway, accept it; else wait onload/.onerror
      if (img.complete && img.naturalWidth && img.naturalHeight) return;
      return new Promise((res, rej) => { img.onload = () => res(); img.onerror = rej; });
    });
  } else {
    done = new Promise((res, rej) => { img.onload = () => res(); img.onerror = rej; });
  }
  done.then(() => resolve(img))
      .catch((err) => reject(err))
      .finally(() => { inFlight--; pump(); });
}

 function queuedDecode(url) {
   const hit = decodeCache.get(url);
   if (hit) return hit;
   const p = new Promise((resolve, reject) => { q.push({ url, resolve, reject }); pump(); });
   // Important: do not permanently cache a failure
   const wrapped = p.then(img => img)
                    .catch(err => { decodeCache.delete(url); throw err; });
   decodeCache.set(url, wrapped);
   return wrapped;
 }

function preloadTile(prefix, n, cache) {
  const url = `${prefix}_${n}.webp`;
  const p = queuedDecode(url);
  cache[n] = p;    // keep your per-layer cache behavior
  return p;
}








/* Single startup path */
window.addEventListener('DOMContentLoaded', () => {
  wireUpButtons();
  underwaterImg = document.getElementById('underwater-img');
  if (underwaterImg) updateUnderwater(0);


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

    const preloadDeep = new Image();
    preloadDeep.src = 'back_overlay_deeper.webp'; 
    preloadZone.appendChild(preloadDeep);



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
    for (let k = 0; k <= 2 && k < total; k++) {
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
  
  // ✅ Warm-attach exactly one extra tile (slice 1) after layers exist
    const schedule = window.requestIdleCallback || window.requestAnimationFrame;
    schedule(() => {
      layers.forEach(layer => {
        if (layer.total > 1 && !layer.imgNodes[1]) {
          // async; don't await to keep startup snappy
          ensureSlice(layer, 1);
        }
      });
    });

  document.body.classList.add('ready');
  requestAnimationFrame(raf);

  spawnBirdFlock();
  birdInterval = setInterval(spawnBirdFlock, 25000 + Math.random() * 5000);
});




