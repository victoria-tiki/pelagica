// --- keep ambient <audio> out of Dash re-renders ---
(function () {
  function hoistAmbient() {
    // 🔎 Make sure this matches the ids you render in app.py
    const ids = [
      "snd-surface-a","snd-surface-b",
      "snd-epi2meso-a","snd-epi2meso-b",
      "snd-meso2bath-a","snd-meso2bath-b",
      "snd-bath2abyss-a","snd-bath2abyss-b",
      "snd-abyss2hadal-a","snd-abyss2hadal-b" // if you use these
    ];

    // Create a static host outside Dash layouts
    let host = document.getElementById("ambient-audio-host");
    if (!host) {
      host = document.createElement("div");
      host.id = "ambient-audio-host";
      host.style.position = "fixed";
      host.style.left = "-9999px"; // off-screen but in the DOM
      host.style.top = "0";
      document.body.appendChild(host);
    }

    ids.forEach(id => {
      const el = document.getElementById(id);
      if (el && el.parentElement !== host) {
        host.appendChild(el);  // re-parent the existing node (don’t clone)
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hoistAmbient, { once: true });
  } else {
    hoistAmbient();
  }
})();


// assets/z_depth_audio_bridge.js
(function () {
  // ---------- CONFIG ----------
  const CUT1 = 20;    // default view → 20 m
  const CUT2 = 100;   // 20 → 200 m
  const CUT3 = 1500;  // 200 → 1500 m
  const CUT4 = 6000;  // 1500 → 6000 m
  const LOOP_FADE_MS  = 3000;  // per-stem seamless loop crossfade

  // two <audio> per stem in your Dash layout
  // (Add the new ids you created in app.py)
  const AUDIO_IDS = [
    "snd-surface-a","snd-surface-b",         // default view → 20 m (reuse)
    "snd-epi2meso-a","snd-epi2meso-b",       // 20 → 200 m (reuse)
    "snd-meso2bath-a","snd-meso2bath-b",     // 200 → 1500 m (new)
    "snd-bath2abyss-a","snd-bath2abyss-b",   // 1500 → 6000 m (new)
    "snd-abyss2hadal-a","snd-abyss2hadal-b"  // 6000 m → end (reuse)
  ];

  // ---------- small helpers ----------
  const clamp01 = x => x < 0 ? 0 : x > 1 ? 1 : x;
  const lerp = (a, b, t) => a + (b - a) * t;

  // 5-band classifier
  // returns one of: "surf", "mid1", "mid2", "mid3", "deep"
  const bandFor = (d) => {
    if (d >= CUT4) return "deep";   // 6000 → end
    if (d >= CUT3) return "mid3";   // 1500 → 6000
    if (d >= CUT2) return "mid2";   // 200 → 1500
    if (d >= CUT1) return "mid1";   // 20 → 200
    return "surf";                  // default → 20
  };

  // a simple one-hot weight for each band
  const ALL_BANDS = ["surf","mid1","mid2","mid3","deep"];
  const weightsForBand = (b) => {
    const w = { surf:0, mid1:0, mid2:0, mid3:0, deep:0 };
    if (w.hasOwnProperty(b)) w[b] = 1;
    return w;
  };

  function waitForEls(ids, cb){
    function check(){
      const els = ids.map(id => document.getElementById(id));
      if (els.every(Boolean)) cb(); else requestAnimationFrame(check);
    }
    check();
  }

  // ---------- Stem: dual players + loop crossfade + scheduled external ramp ----------
  class Stem {
    constructor(aId, bId){
      this.a = document.getElementById(aId);
      this.b = document.getElementById(bId);

      // active/inactive for internal loop crossfade
      this.active = this.a;
      this.inactive = this.b;
      this.intStart = null;
      this.intEnd = null;

      // external mix ramp
      this.cur = 0;            // current gain 0..1
      this.rampStart = 0;      // ms (performance.now)
      this.rampEnd = 0;        // ms
      this.rampFrom = 0;       // value at rampStart
      this.rampTo = 0;         // target

      [this.a, this.b].forEach(el => { if (el) el.volume = 0; });

      const onTimeUpdate = el => {
        const dur = el.duration || 0;
        if (!dur || this.active !== el) return;
        const remain = dur - el.currentTime;
        if (remain > 0 && remain * 1000 < LOOP_FADE_MS) this._startInternalXfade();
      };
      const onEnded = el => { if (this.active === el) this._startInternalXfade(true); };

      [this.a, this.b].forEach(el => {
        if (!el) return;
        el.addEventListener("timeupdate", () => onTimeUpdate(el));
        el.addEventListener("ended",      () => onEnded(el));
      });
    }

    ensurePlay(on){
      [this.a, this.b].forEach(el => {
        if (!el) return;
        if (on) { if (el.paused) el.play().catch(()=>{}); }
        else    { if (!el.paused) el.pause(); }
      });
    }

    // schedule a linear ramp from the *current* value to target, starting at startAt and ending at endAt
    scheduleExtRamp(target, startAt, endAt){
      const now = performance.now();
      const current = this._currentExt(now);
      this.rampFrom = current;
      this.rampTo   = clamp01(target);
      this.rampStart = startAt;
      this.rampEnd   = Math.max(startAt + 1, endAt);
    }

    // snap immediately to a target value
    snapTo(target){
      this.cur = clamp01(target);
      this.rampStart = this.rampEnd = performance.now();
      this.rampFrom = this.rampTo = this.cur;
      this._applyVolumes(1, 0); // will be corrected on next tick
    }

    // internal (A/B) crossfade for seamless looping
    _startInternalXfade(immediate=false){
      const now = performance.now();
      try { this.inactive.currentTime = 0; } catch(_) {}
      this.inactive.play().catch(()=>{});
      this.intStart = now;
      this.intEnd   = now + (immediate ? 1 : LOOP_FADE_MS);
    }
    _swapIfDone(now){
      if (this.intEnd && now > this.intEnd){
        const old = this.active;
        this.active = this.inactive;
        this.inactive = old;
        this.intStart = this.intEnd = null;
      }
    }

    _currentExt(now){
      if (now <= this.rampStart) return this.cur;
      if (now >= this.rampEnd)   return this.rampTo;
      const t = clamp01((now - this.rampStart) / (this.rampEnd - this.rampStart));
      return lerp(this.rampFrom, this.rampTo, t);
    }

    _applyVolumes(wA, wB){
      if (this.a) this.a.volume = this.cur * wA;
      if (this.b) this.b.volume = this.cur * wB;
    }

    tick(now){
      // external
      this.cur = this._currentExt(now);

      // internal crossfade weights
      let wA = 1, wB = 0;
      if (this.intEnd && now <= this.intEnd){
        const t = clamp01((now - this.intStart) / (this.intEnd - this.intStart));
        const aIsActive = (this.active === this.a);
        wA = aIsActive ? (1 - t) : t;
        wB = aIsActive ? t : (1 - t);
      } else {
        wA = (this.active === this.a) ? 1 : 0;
        wB = (this.active === this.b) ? 1 : 0;
      }

      this._applyVolumes(wA, wB);
      this._swapIfDone(now);
    }
  }

  // ---------- Init once audio tags exist ----------
  waitForEls(AUDIO_IDS, init);

  function init(){
    const stems = {
      // keep original ids for reused ranges
      surf: new Stem("snd-surface-a","snd-surface-b"),          // default → 20
      mid1: new Stem("snd-epi2meso-a","snd-epi2meso-b"),        // 20 → 200
      mid2: new Stem("snd-meso2bath-a","snd-meso2bath-b"),      // 200 → 1500 (NEW)
      mid3: new Stem("snd-bath2abyss-a","snd-bath2abyss-b"),    // 1500 → 6000 (NEW)
      deep: new Stem("snd-abyss2hadal-a","snd-abyss2hadal-b"),  // 6000 → end
    };

    const stemList = Object.values(stems);

    // current animation plan; used to finalize correctly
    let plan = null; // {startAt, endAt, toBand}

    function setBandImmediate(depthOrBand){
      const band = typeof depthOrBand === "string" ? depthOrBand : bandFor(depthOrBand);
      const w = weightsForBand(band);
      for (const k of ALL_BANDS) stems[k].snapTo(w[k] || 0);
    }

    function scheduleMidToEndRamp(toDepth, durationMs){
      const now = performance.now();
      const toBand = bandFor(toDepth);
      const startAt = now + durationMs / 2;  // midpoint
      const endAt   = now + durationMs;      // end of animation
      const w = weightsForBand(toBand);

      for (const k of ALL_BANDS) stems[k].scheduleExtRamp(w[k] || 0, startAt, endAt);

      plan = { startAt, endAt, toBand };     // remember final band decisively
    }

    // RAF: keep players alive & apply ramps
    (function loop(){
      const now = performance.now();
      const on = !!window.pelagicaSoundOn;
      for (const s of stemList) {
        s.ensurePlay(on);
        s.tick(now);
      }
      requestAnimationFrame(loop);
    })();

    // initial state (no ramp)
    const initialDepth = (typeof window.pelagicaLastDepth === "number") ? window.pelagicaLastDepth : 0;
    setBandImmediate(initialDepth);

    // ---- messages from viewer ----
    window.addEventListener("message", (ev) => {
      const d = ev && ev.data;
      if (!d) return;

      if (d.type === "animationStart"
          && typeof d.fromDepth === "number"
          && typeof d.toDepth   === "number"
          && typeof d.duration  === "number") {

        window.pelagicaAnimating = true;
        window.pelagicaLastDepth = d.fromDepth;

        const fromBand = bandFor(d.fromDepth);
        const toBand   = bandFor(d.toDepth);

        // If band doesn't change, just note the plan; we'll snap at end.
        if (fromBand === toBand) {
          plan = { startAt: performance.now(), endAt: performance.now() + Math.max(200, d.duration|0), toBand };
          return;
        }

        // Single, deterministic ramp: midpoint -> end, to the final band
        scheduleMidToEndRamp(d.toDepth, Math.max(200, d.duration|0));
      }

      else if (d.type === "depthProgress" && typeof d.depth === "number") {
        // record only (do NOT retarget during tween)
        window.pelagicaLastDepth = d.depth;
      }

      else if (d.type === "animationDone") {
        // finalize to planned final band if we had a plan; otherwise use last known depth
        const finalBand = plan ? plan.toBand
                               : bandFor((typeof window.pelagicaLastDepth === "number") ? window.pelagicaLastDepth : 0);
        setBandImmediate(finalBand);
        plan = null;
        window.pelagicaAnimating = false;
      }
    }, false);

    // tiny API to avoid breaking older calls; intentionally a no-op for targeting
    window.pelagicaAudio = {
      preFadeToward: function(_){ /* no-op by design */ },
      bandOf: bandFor
    };
  }
})();

