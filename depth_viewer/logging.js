// assets/logging.js

// 1) Log exactly when the animation completes.
// Assumes your viewer posts { type: "animationDone", species: "<name>" }.
window.addEventListener("message", (ev) => {
  const msg = ev && ev.data;
  if (msg && msg.type === "animationDone") {
    console.log("[Pelagica] descent animation completed for:", msg.species || "(unknown)");
  }
}, false);

// 2) Log when the species panel image has fully loaded.
// Wait for #species-img to exist, then watch its 'src' changes and hook a one-off 'load'.
(function watchSpeciesImage() {
  function attachObserver(img) {
    // On every src change, attach a one-time load listener
    const obs = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type === "attributes" && m.attributeName === "src" && img.src) {
          img.addEventListener("load", function onload() {
            console.log("[Pelagica] species panel fully loaded (image + details).");
            img.removeEventListener("load", onload);
          }, { once: true });
        }
      }
    });
    obs.observe(img, { attributes: true, attributeFilter: ["src"] });
  }

  // The image might be rendered later; poll until it exists, then attach.
  const interval = setInterval(() => {
    const img = document.getElementById("species-img");
    if (img) {
      clearInterval(interval);
      attachObserver(img);
    }
  }, 100);

  // As a fallback, run once when DOM is interactive/complete
  if (document.readyState === "complete" || document.readyState === "interactive") {
    const img = document.getElementById("species-img");
    if (img) {
      clearInterval(interval);
      attachObserver(img);
    }
  } else {
    document.addEventListener("DOMContentLoaded", () => {
      const img = document.getElementById("species-img");
      if (img) {
        clearInterval(interval);
        attachObserver(img);
      }
    });
  }
})();



