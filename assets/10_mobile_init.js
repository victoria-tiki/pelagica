/* collapse the search drawer on first load (≤ 768 px) */
(function () {
  const BREAK = 768;

  function collapse() {
    if (window.innerWidth > BREAK) return;          // desktop – leave open
    const panel  = document.getElementById('search-panel');
    const handle = document.getElementById('search-handle');
    if (panel)  panel.classList.remove('open');
    if (handle) handle.classList.add('collapsed');
  }

  /* Run once the component tree is in the DOM */
  new MutationObserver((_, obs) => {
    if (document.getElementById('search-panel')) {
      collapse();
      obs.disconnect();                            // done
    }
  }).observe(document.body, {childList: true, subtree: true});
})();

