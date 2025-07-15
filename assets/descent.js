window.addEventListener("DOMContentLoaded", () => {
  const wrapper = document.getElementById("ocean-layers");

  // Listen for Dash's dcc.Store change
  const observer = new MutationObserver(() => {
    const store = document.querySelector('[data-dash-is-loading="false"][id="target-depth"]');
    if (store && store.textContent) {
      const depth = parseFloat(store.textContent);
      if (isNaN(depth)) return;

      // Translate downward: 1100m → 100vh
      const vh = Math.min((depth / 11000) * 1000, 1000); // clamp to 1000vh
      wrapper.style.transform = `translateY(-${vh}vh)`;
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
});

