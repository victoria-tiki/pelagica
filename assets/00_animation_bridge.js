/* ───────── Pelagica ⇆ Depth-Viewer Bridge – v5.3b (overlay text handled by Dash) ───────── */
(function () {
  // ---- gates/state ----------------------------------------------------
  let animGate   = false;     // opens when viewer posts animationDone
  let imgGate    = false;     // opens when the *current* image src finishes loading
  let pendingSrc = null;      // tracks the src we're waiting on (guards rapid changes)

  // ---- small DOM helpers ---------------------------------------------
  const $ = (id) => document.getElementById(id);

  function setOverlay(visible) {
    const msg = $("load-message");
    if (!msg) return;
    msg.style.display = visible ? "block" : "none";
  }

  function hidePanel(why) {
    const panel = $("main-content");
    if (panel) panel.style.display = "none";
    if (why) console.log("[Pelagica] hide main-content →", why);
  }

  function tryShowPanel() {
    if (!(animGate && imgGate)) return;   // show only when both gates are open
    const panel = $("main-content");
    if (panel) panel.style.display = "block";
    setOverlay(false);                     // overlay off when panel shows
    console.log("[Pelagica] species panel SHOWN (anim + image ready).");
  }

  // ────────────────────────────────────────────────────────────────────
  // Dash ➜ viewer: sendDepth (keep your API; just reset gates + hide)
  // ────────────────────────────────────────────────────────────────────
  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    bridge: {
      /**
       * @param {number}  depth  – metres
       * @param {boolean} skip   – true = jump instantly, false = play tween
       */
      sendDepth: function (depth, skip) {
        const frame = $("depth-iframe");
        if (!frame || depth == null) {
          return window.dash_clientside.no_update;
        }

        // Fresh request: close both gates, hide panel; keep overlay hidden during the dive
        animGate = false;
        imgGate  = false;
        setOverlay(false);
        hidePanel("startAnimation");

        // Your original viewer messages
        frame.contentWindow.postMessage({ type: skip ? "pauseAll" : "resumeAll" }, "*");
        const isImperial = !!$("units-toggle")?.checked;
        frame.contentWindow.postMessage(
          { type: "startAnimation", depth, units: isImperial ? "imperial" : "metric" },
          "*"
        );
        return window.dash_clientside.no_update; // dummy Output
      },
    },
  });

  // ────────────────────────────────────────────────────────────────────
  // viewer ➜ Dash: open the animation gate on "animationDone"
  // Show overlay *now* (not earlier) if we’re still waiting on the image.
  // ────────────────────────────────────────────────────────────────────
  window.addEventListener("message", (e) => {
    if (e?.data?.type !== "animationDone") return;
    animGate = true;
    console.log("[Pelagica] descent animation completed.");
    if (!imgGate) setOverlay(true);  // overlay text is provided by Dash
    tryShowPanel();
  });

  // ────────────────────────────────────────────────────────────────────
  // Image watcher: hide on new src; open image gate when that src loads
  // ────────────────────────────────────────────────────────────────────
  function armImageWatch() {
    const img = $("species-img");
    if (!img) return false;

    const obs = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type === "attributes" && m.attributeName === "src") {
          const newSrc = img.getAttribute("src");
          if (!newSrc || newSrc === pendingSrc) continue;

          pendingSrc = newSrc;
          imgGate = false;
          hidePanel("new image src");

          // Only show overlay after animation has completed
          if (animGate) {
            setOverlay(true);    // Dash sets the message text
          } else {
            setOverlay(false);
          }

          const onLoad = () => {
            if (img.getAttribute("src") === pendingSrc) {
              imgGate = true;
              console.log("[Pelagica] image loaded:", pendingSrc);
              tryShowPanel();
            }
          };
          const onError = () => {
            if (img.getAttribute("src") === pendingSrc) {
              imgGate = true; // fail-open so UI isn’t stuck
              console.error("[Pelagica] image failed to load; showing panel anyway.");
              tryShowPanel();
            }
          };

          img.addEventListener("load",  onLoad,  { once: true });
          img.addEventListener("error", onError, { once: true });

          // Cached fast path (image already complete for this src)
          if (img.complete && img.naturalWidth > 0) {
            queueMicrotask(onLoad);
          }
        }
      }
    });

    obs.observe(img, { attributes: true, attributeFilter: ["src"] });

    // Initial mount: if there’s already a src but it isn’t ready, wait.
    if (img.getAttribute("src") && !(img.complete && img.naturalWidth > 0)) {
      pendingSrc = img.getAttribute("src");
      imgGate = false;
      hidePanel("initial image pending");
      if (animGate) setOverlay(true);   // Dash sets the message text
      img.addEventListener("load", () => {
        if (img.getAttribute("src") === pendingSrc) {
          imgGate = true;
          tryShowPanel();
        }
      }, { once: true });
      img.addEventListener("error", () => {
        imgGate = true;
        tryShowPanel();
      }, { once: true });
    } else if (img.complete && img.naturalWidth > 0) {
      imgGate = true; // initial image already displayed
    }

    return true;
  }

  // Attach as soon as #species-img exists
  function attachWhenReady() {
    const ok = armImageWatch();
    if (!ok) {
      const t = setInterval(() => armImageWatch() && clearInterval(t), 100);
    }
  }
  if (document.readyState === "complete" || document.readyState === "interactive") {
    attachWhenReady();
  } else {
    document.addEventListener("DOMContentLoaded", attachWhenReady);
  }

  // Optional: if some other code toggles the overlay visibility later,
  // keep to showing/hiding only (no text writes here).
  const msg = $("load-message");
  if (msg) {
    new MutationObserver((mutList) => {
      for (const m of mutList) {
        if (m.type === "attributes" && m.attributeName === "style") {
          // nothing to do; Dash controls the text, we control visibility elsewhere
        }
      }
    }).observe(msg, { attributes: true, attributeFilter: ["style"] });
  }
})();

