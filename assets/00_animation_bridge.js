/* ───────── Pelagica ⇆ Depth-Viewer Bridge – v5 ───────── */
(function () {
  let diveInProgress = false;                    // guards the show step

  /* Dash ➜ viewer  ********************************************/
  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    bridge: {
      /**
       * @param {number}  depth   – target depth in metres
       * @param {boolean} skip    – true  = jump instantly
       *                          – false = play descent animation
       */
      sendDepth: function (depth, skip) {
        const frame = document.getElementById("depth-iframe");
        if (!frame || depth == null) {
          return window.dash_clientside.no_update;
        }

        /* 1 · hide the species panel while we “dive” */
        const panel = document.getElementById("main-content");
        if (panel) panel.style.display = "none";
        diveInProgress = true;

        /* 2 · tell the viewer to pause / resume animation timeline */
        frame.contentWindow.postMessage(
          { type: skip ? "pauseAll" : "resumeAll" },
          "*"
        );

        /* 3 · launch the actual depth transition */
        const unitsToggle = document.getElementById("units-toggle");
        const isImperial = unitsToggle && unitsToggle.checked;
        frame.contentWindow.postMessage(
          {
            type: "startAnimation",
            depth,
            units: isImperial ? "imperial" : "metric",
          },
          "*"
        );

        return window.dash_clientside.no_update; // dummy output
      },
    },
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


/* ── Brief loading overlay while the species image downloads ── */
(function () {
  const msg  = document.getElementById("load-message");
  const img  = document.getElementById("species-img");

  if (!msg || !img) return;                        // safety on hot-reloads

  /* When Dash tells us a NEW species is coming… */
  window.showSpeciesLoading = function (gs) {
    msg.textContent = `Searching for ${gs}…`;
    msg.style.display   = "block";
    img.style.visibility = "hidden";
  };

  /* …hide the overlay again the moment the <img> finishes */
  img.addEventListener("load", () => {
    msg.style.display   = "none";
    img.style.visibility = "visible";
  });
})();


