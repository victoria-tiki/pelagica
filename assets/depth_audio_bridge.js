(function(){
  // ids you already created
  const getTracks = () => ([
    document.getElementById("snd-surface"),
    document.getElementById("snd-epi2meso"),
    document.getElementById("snd-bathy2abyss"),
    document.getElementById("snd-abyss2hadal"),
  ]);
  
  document.addEventListener("DOMContentLoaded", () => {
  const tracks = getTracks();
  tracks.forEach(t => { if (t) t.volume = 0; });});


  // same BLEND logic as before, but stateless
  function gainsForDepth(d){
    const BLEND = 20, half = BLEND/2;
    let gS=0,gE=0,gB=0,gH=0;
    if (d <= 50 - half) { gS=1; }
    else if (d < 50 + half) { const t=(d-(50-half))/BLEND; gS=1-t; gE=t; }
    else if (d <= 200 - half) { gE=1; }
    else if (d < 200 + half) { const t=(d-(200-half))/BLEND; gE=1-t; gB=t; }
    else if (d <= 3000 - half) { gB=1; }
    else if (d < 3000 + half) { const t=(d-(3000-half))/BLEND; gB=1-t; gH=t; }
    else { gH=1; }
    return [gS,gE,gB,gH];
  }

  // tiny ramp to avoid zipper noise
  function rampVolumes(tracks, targets, durMs){
    const start = tracks.map(t => t ? t.volume : 0);
    const t0 = performance.now();
    function step(now){
      const k = Math.min(1, (now - t0)/durMs);
      for (let i=0;i<tracks.length;i++){
        const t = tracks[i]; if (!t) continue;
        t.volume = start[i] + (targets[i] - start[i]) * k;
      }
      if (k < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  // observe Dash's sound toggle store (optional; works even if store isn't present)
  const on = !!window.pelagicaSoundOn;

  // ensure playback state matches toggle
  function ensurePlayState(tracks, on){
    tracks.forEach(t => {
      if (!t) return;
      if (on) { if (t.paused) t.play().catch(()=>{}); }
      else { if (!t.paused) t.pause(); }
    });
  }

  window.addEventListener("message", (ev) => {
      const data = ev?.data;
      if (!data || (data.type !== "depthProgress" && data.type !== "animationDone")) return;

      const tracks = getTracks();
      if (!tracks.every(Boolean)) return;

      const on = !!window.pelagicaSoundOn;     // <-- read the global flag
      window.pelagicaLastDepth = data.depth ?? window.pelagicaLastDepth; // cache
      ensurePlayState(tracks, on);
      if (!on) return;

      if (data.type === "depthProgress" && typeof data.depth === "number") {
        const targets = gainsForDepth(data.depth);     // blend DURING the tween
        rampVolumes(tracks, targets, 120);
      }

      if (data.type === "animationDone") {
        // After the tween, SNAP to the single active band (no lingering partial mix)
        const d = window.pelagicaLastDepth;
        if (typeof d === "number") {
          const idx = (d >= 3000) ? 3 : (d >= 200) ? 2 : (d >= 50) ? 1 : 0;
          tracks.forEach((t,i) => { if (t) t.volume = (i === idx) ? 1 : 0; });
        }
      }
    }, false);

})();

