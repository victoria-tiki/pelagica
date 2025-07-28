/* ───────── Pelagica ⇆ Depth-Viewer Bridge – final v4 ───────── */
(function () {
  let diveInProgress = false;                   // guards the show step

  /* Dash ➜ viewer  ********************************************/
  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    bridge: {
      sendDepth: function (depth, instantArr) {
        const frame  = document.getElementById("depth-iframe");
        if (!frame || depth == null) return window.dash_clientside.no_update;

        /* 1 · hide the species panel while we “dive” */
        const panel = document.getElementById("main-content");
        if (panel) panel.style.display = "none";
        diveInProgress = true;

        /* 2 · tell the viewer what to do */
        const instant = (instantArr || []).includes("instant");
        frame.contentWindow.postMessage({ type: instant ? "pauseAll" : "resumeAll" }, "*");
        
        const unitsToggle = document.getElementById("units-toggle");
        const isImperial = unitsToggle && unitsToggle.checked;
        frame.contentWindow.postMessage({
          type: "startAnimation",
          depth,
          units: isImperial ? "imperial" : "metric"
        }, "*");


        return window.dash_clientside.no_update;     // dummy output
      }
    }
  });

  /* viewer ➜ Dash  ********************************************/
  window.addEventListener("message", (e) => {
    if (e.data?.type !== "animationDone" || !diveInProgress) return;

    /* show the panel as soon as the tween ends */
    const panel = document.getElementById("main-content");
    if (panel) panel.style.display = "block";
    diveInProgress = false;
  });
})();

