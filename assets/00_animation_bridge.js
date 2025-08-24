/* ───────── Pelagica ⇆ Depth-Viewer Bridge – v5.3b (overlay text handled by Dash) ───────── */
(function () {
  // ---- gates/state ----------------------------------------------------
  let animGate   = false;     // opens when viewer posts animationDone
  let imgGate    = false;     // opens when the *current* image src finishes loading
  let pendingSrc = null;      // tracks the src we're waiting on (guards rapid changes)

  // ---- small DOM helpers ---------------------------------------------
  const $ = (id) => document.getElementById(id);

  let overlayTimer = null;                     // one global timer
  let imgWatchdog = null;  // fail-safe: never wait forever for <img> events


  function setOverlay(visible) {
    const msg = document.getElementById("load-message");
    if (!msg) return;

    if (visible) {
      clearTimeout(overlayTimer);              
      overlayTimer = setTimeout(() => {
        msg.style.display = "block";
      }, 500);                                 // ← 0.5 s delay
    } else {
      clearTimeout(overlayTimer);              
      msg.style.display = "none";
    }
  }


  function hidePanel(why) {
    const panel = $("main-content");
    if (panel) panel.style.display = "none";
    //if (why) console.log("[Pelagica] hide main-content →", why);
  }

  function tryShowPanel() {
    if (!(animGate && imgGate)) return;   // show only when both gates are open
    const panel = $("main-content");
    if (panel) panel.style.display = "block";
    setOverlay(false);                     // overlay off when panel shows
    //console.log("[Pelagica] species panel SHOWN (anim + image ready).");
  }

  // ────────────────────────────────────────────────────────────────────
  // Dash ➜ viewer: sendDepth
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
    // viewer ➜ Dash: open the animation gate on "animationDone"
    window.addEventListener("message", (e) => {
      if (e?.data?.type !== "animationDone") return;
      animGate = true;
      //console.log("[Pelagica] descent animation completed.");

      // Show the overlay only if we are waiting on a NEW image to load.
      // (Do not hide it here; tryShowPanel() will hide it when both gates are open.)
      if (pendingSrc && !imgGate) {
        setOverlay(true);
      }

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
          
          clearTimeout(imgWatchdog);
          imgWatchdog = setTimeout(() => {
          // If we're still waiting on the exact same URL, proceed without the event.
          if (img.getAttribute("src") === pendingSrc && !imgGate) {
            console.warn("[Pelagica] image watchdog fired; proceeding without <img> event.");
            imgGate = true;
            tryShowPanel();    // will also hide the overlay
          }
        }, 5000); // 7s is conservative; tune if you like


          // Only show overlay after animation has completed
          if (animGate) {
            setOverlay(true);   
          } else {
            setOverlay(false);
          }

          const onLoad = () => {
            if (img.getAttribute("src") === pendingSrc) {
              imgGate = true;
              //console.log("[Pelagica] image loaded:", pendingSrc);
              tryShowPanel();
              clearTimeout(imgWatchdog);
            }
          };
          const onError = () => {
            if (img.getAttribute("src") === pendingSrc) {
              imgGate = true; 
              console.error("[Pelagica] image failed to load; showing panel anyway.");
              tryShowPanel();
              clearTimeout(imgWatchdog);
            }
          };

          img.addEventListener("load",  onLoad,  { once: true });
          img.addEventListener("error", onError, { once: true });

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
      if (animGate) setOverlay(true);  
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
      imgGate = true; 
    }

    return true;
  }

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

  //if some other code toggles the overlay visibility later, keep to showing/hiding only (no text writes here).
  const msg = $("load-message");
  if (msg) {
    new MutationObserver((mutList) => {
      for (const m of mutList) {
        if (m.type === "attributes" && m.attributeName === "style") {
        }
      }
    }).observe(msg, { attributes: true, attributeFilter: ["style"] });
  }
})();

/* ---------- Force delayed start for species image loading (hacky, but this solves some racing issues where the image would never appear if it was processed too quickly) ---------- */
(function () {
  const TARGET_ID = "species-img";
  const DELAY_MS  = 500;

  function installDelayedSrc(el) {
    if (!el || el.__delayedSrcInstalled) return;
    el.__delayedSrcInstalled = true;

    // Keep original property/behavior
    const proto = Object.getPrototypeOf(el);
    const desc  = Object.getOwnPropertyDescriptor(proto, "src");
    const origSetAttribute = el.setAttribute;

    // Intercept direct property sets:  el.src = "…"
    Object.defineProperty(el, "src", {
      configurable: true,
      enumerable: desc && desc.enumerable,
      get: function () {
        return desc ? desc.get.call(this) : this.getAttribute("src");
      },
      set: function (v) {
        const newUrl = String(v || "");
        // Cancel any pending start, coalesce rapid changes
        clearTimeout(this.__srcDelayTimer);

        // No need to schedule if it wouldn't change anything
        try {
          const current = desc ? desc.get.call(this) : this.getAttribute("src");
          if (newUrl === current) return;
        } catch (_) { /* ignore */ }

        this.__pendingSrc = newUrl;
        this.__srcDelayTimer = setTimeout(() => {
          try {
            if (desc && desc.set) {
              desc.set.call(this, this.__pendingSrc); // actual network start happens here
            } else {
              this.setAttribute("src", this.__pendingSrc);
            }
          } finally {
            this.__pendingSrc = null;
          }
        }, DELAY_MS);
      }
    });

    // Intercept attribute sets:  el.setAttribute('src', '…')
    el.setAttribute = function (name, value) {
      if (String(name).toLowerCase() === "src") {
        // Route through the delayed property setter so we always delay network start
        this.src = value;
        return;
      }
      return origSetAttribute.apply(this, arguments);
    };
  }

  function initOnce() {
    const el = document.getElementById(TARGET_ID);
    if (el) {
      installDelayedSrc(el);
      return true;
    }
    return false;
  }

  // Install now or as soon as the element exists
  if (!initOnce()) {
    const t = setInterval(() => initOnce() && clearInterval(t), 50);
    document.addEventListener("DOMContentLoaded", () => initOnce() && clearInterval(t));
  }
})();

