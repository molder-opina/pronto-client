/* QA FIXES INJECTION */
(function () {
  function applyFixes() {
    // Force button to be visible
    const btnSelector = [
      'button#checkout-submit-btn',
      '.checkout-submit-btn',
      'button[form="checkout-form"]',
    ];
    for (const sel of btnSelector) {
      const btn = document.querySelector(sel);
      if (btn) {
        btn.style.cssText = `
          width: 100% !important;
          height: 3rem !important;
          min-height: 3rem !important;
          display: inline-flex !important;
          opacity: 1 !important;
          visibility: visible !important;
          pointer-events: auto !important;
          cursor: pointer !important;
          flex-direction: row !important;
          align-items: center !important;
          justify-content: center !important;
          padding: 1rem !important;
          margin-top: 1rem !important;
          box-sizing: border-box !important;
          position: relative !important;
          float: none !important;
        `;
      }
    }

    // Force accordion content visible
    document.querySelectorAll('.accordion-content').forEach((el) => {
      el.style.cssText = `
        opacity: 1 !important;
        visibility: visible !important;
        pointer-events: auto !important;
        display: block !important;
        width: 100% !important;
      `;
    });
  }

  applyFixes();
  document.addEventListener('DOMContentLoaded', applyFixes);
  window.addEventListener('load', applyFixes);

  // Re-run every 100ms for first 10 seconds
  let count = 0;
  const fixInterval = setInterval(() => {
    applyFixes();
    count++;
    if (count >= 100) clearInterval(fixInterval);
  }, 100);
})();

/* Force hide broken modals */
(function () {
  const hideModals = () => {
    const selectors = [
      '#keyboard-shortcuts-modal',
      '#shortcuts-modal',
      '#business-hours-modal',
      '#business-hours-display',
      '.shortcuts-modal',
      '.business-hours-display',
      '.business-hours-title',
    ];

    selectors.forEach((selector) => {
      const elements = document.querySelectorAll(selector);
      elements.forEach((el) => {
        if (el) {
          el.style.setProperty('display', 'none', 'important');
          el.style.setProperty('visibility', 'hidden', 'important');
          el.style.setProperty('opacity', '0', 'important');
          el.style.setProperty('pointer-events', 'none', 'important');
          el.style.setProperty('height', '0', 'important');
          el.style.setProperty('overflow', 'hidden', 'important');
        }
      });
    });
  };

  // Run immediately
  hideModals();

  // Run after DOM is fully loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hideModals);
  }

  // Run after a short delay to catch dynamically added elements
  setTimeout(hideModals, 500);
  setTimeout(hideModals, 1000);
  setTimeout(hideModals, 2000);
})();
