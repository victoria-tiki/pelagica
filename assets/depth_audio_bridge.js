// assets/z_depth_audio_bridge.js
(function () {
  // ---------- CONFIG ----------
  const SURFACE_MAX   = 20;    // meters
  const MID_MAX       = 2000;  // meters
  const LOOP_FADE_MS  = 3000;  // per-stem seamless loop crossfade

  // two <audio> per stem in your Dash layout
  const AUDIO_IDS = [
    "snd-surface-a","snd-surface-b",
    "snd-epi2meso-a","snd-epi2meso-b",
    "snd-abyss2hadal-a","snd-abyss2hadal-b"
  ];

  // ---------- small helpers ----------
  const clamp01 = x => x < 0 ? 0 : x > 1 ? 1 : x;
  const lerp = (a, b, t) => a + (b - a) * t;
  const bandFor = d => (d >= MID_MAX ? "deep" : (d >= SURFACE_MAX ? "mid" : "surf"));
  const weightsForBand = b => (
    b === "deep" ? { surf: 0, mid: 0, deep: 1 } :
    b === "mid"  ? { surf: 0, mid: 1, deep: 0 } :
                   { surf: 1, mid: 0, deep: 0 }
  );

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
      surf: new Stem("snd-surface-a","snd-surface-b"),
      mid:  new Stem("snd-epi2meso-a","snd-epi2meso-b"),
      deep: new Stem("snd-abyss2hadal-a","snd-abyss2hadal-b"),
    };

    // current animation plan; used to finalize correctly
    let plan = null; // {startAt, endAt, toBand}

    function setBandImmediate(depthOrBand){
      const band = typeof depthOrBand === "string" ? depthOrBand : bandFor(depthOrBand);
      const w = weightsForBand(band);
      stems.surf.snapTo(w.surf);
      stems.mid .snapTo(w.mid);
      stems.deep.snapTo(w.deep);
    }

    function scheduleMidToEndRamp(toDepth, durationMs){
      const now = performance.now();
      const toBand = bandFor(toDepth);
      const startAt = now + durationMs / 2;  // midpoint
      const endAt   = now + durationMs;      // end of animation
      const w = weightsForBand(toBand);

      stems.surf.scheduleExtRamp(w.surf, startAt, endAt);
      stems.mid .scheduleExtRamp(w.mid,  startAt, endAt);
      stems.deep.scheduleExtRamp(w.deep, startAt, endAt);

      plan = { startAt, endAt, toBand };     // remember final band decisively
    }

    // RAF: keep players alive & apply ramps
    (function loop(){
      const now = performance.now();
      const on = !!window.pelagicaSoundOn;
      stems.surf.ensurePlay(on);
      stems.mid .ensurePlay(on);
      stems.deep.ensurePlay(on);
      stems.surf.tick(now);
      stems.mid .tick(now);
      stems.deep.tick(now);
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

