/**
 * UX INTERACTION SCRIPTS
 * Interactive components for improved UX
 */

// === TOAST NOTIFICATIONS ===
function showToast(message, type = 'info') {
  const icons = {
    success:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>',
    error:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>',
    warning:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>',
  };

  const titles = {
    success: 'Éxito',
    error: 'Error',
    warning: 'Advertencia',
    info: 'Información',
  };

  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.setAttribute('role', 'alert');
  toast.innerHTML = `
    <span class="toast__icon">${icons[type]}</span>
    <div class="toast__content">
      <div class="toast__title">${titles[type]}</div>
      <div class="toast__message">${message}</div>
    </div>
    <button class="toast__close" aria-label="Cerrar" onclick="this.parentElement.remove()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
    </button>
  `;

  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast--exiting');
    setTimeout(() => toast.remove(), 300);
  }, 5000);
}

// === COLLAPSIBLE SECTIONS ===
function initCollapsibles() {
  document.querySelectorAll('.collapsible-section__header').forEach((header) => {
    header.addEventListener('click', () => {
      const section = header.parentElement;
      const isExpanded = section.classList.contains('collapsible-section--expanded');

      section.classList.toggle('collapsible-section--expanded');
      header.setAttribute('aria-expanded', !isExpanded);

      const content = section.querySelector('.collapsible-section__content');
      if (!isExpanded) {
        content.style.maxHeight = content.scrollHeight + 'px';
      } else {
        content.style.maxHeight = '0';
      }
    });
  });
}

// === FILTER CHIPS ===
function initFilterChips() {
  document.querySelectorAll('.filter-chip').forEach((chip) => {
    chip.addEventListener('click', (e) => {
      if (e.target.classList.contains('filter-chip__close')) return;

      chip.classList.toggle('filter-chip--active');

      const isActive = chip.classList.contains('filter-chip--active');
      announceToScreenReader(
        isActive
          ? 'Filtro activado: ' + chip.textContent.trim()
          : 'Filtro desactivado: ' + chip.textContent.trim()
      );
    });

    const closeBtn = chip.querySelector('.filter-chip__close');
    if (closeBtn) {
      closeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        chip.classList.remove('filter-chip--active');
        announceToScreenReader('Filtro removido: ' + chip.textContent.trim());
      });
    }
  });
}

// === SCREEN READER ANNOUNCEMENTS ===
function announceToScreenReader(message) {
  const announcement = document.createElement('div');
  announcement.setAttribute('role', 'status');
  announcement.setAttribute('aria-live', 'polite');
  announcement.setAttribute('aria-atomic', 'true');
  announcement.className = 'sr-only';
  announcement.textContent = message;
  document.body.appendChild(announcement);

  setTimeout(() => {
    document.body.removeChild(announcement);
  }, 1000);
}

// === PROGRESS STEPS ===
function updateProgressStep(currentStep, totalSteps) {
  const steps = document.querySelectorAll('.progress-step');
  steps.forEach((step, index) => {
    step.classList.remove('progress-step--active', 'progress-step--completed');

    if (index + 1 < currentStep) {
      step.classList.add('progress-step--completed');
    } else if (index + 1 === currentStep) {
      step.classList.add('progress-step--active');
    }
  });

  announceToScreenReader(`Paso ${currentStep} de ${totalSteps}`);
}

// === KEYBOARD NAVIGATION ===
function initKeyboardNavigation() {
  document.addEventListener('keydown', (e) => {
    // ESC key to close modals and collapsibles
    if (e.key === 'Escape') {
      const activeModal = document.querySelector('.modal-overlay--visible');
      if (activeModal) {
        const closeBtn = activeModal.querySelector('.modal-close');
        if (closeBtn) closeBtn.click();
      }

      const expandedSections = document.querySelectorAll('.collapsible-section--expanded');
      expandedSections.forEach((section) => {
        const header = section.querySelector('.collapsible-section__header');
        if (header) header.click();
      });
    }

    // Arrow keys for filter chips
    const activeChip = document.activeElement.closest('.filter-chip');
    if (activeChip && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
      e.preventDefault();
      const chips = Array.from(document.querySelectorAll('.filter-chip'));
      const currentIndex = chips.indexOf(activeChip);

      if (e.key === 'ArrowRight' && currentIndex < chips.length - 1) {
        chips[currentIndex + 1].focus();
      } else if (e.key === 'ArrowLeft' && currentIndex > 0) {
        chips[currentIndex - 1].focus();
      }
    }
  });
}

// === FOCUS TRAP FOR MODALS ===
function trapFocus(modal) {
  const focusableElements = modal.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  const firstElement = focusableElements[0];
  const lastElement = focusableElements[focusableElements.length - 1];

  modal.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          lastElement.focus();
          e.preventDefault();
        }
      } else {
        if (document.activeElement === lastElement) {
          firstElement.focus();
          e.preventDefault();
        }
      }
    }
  });
}

// === MOBILE NAVIGATION ===
function initMobileNav() {
  const mobileNav = document.querySelector('.mobile-nav');
  if (!mobileNav) return;

  const links = mobileNav.querySelectorAll('.mobile-nav__link');
  links.forEach((link) => {
    link.addEventListener('click', () => {
      links.forEach((l) => l.classList.remove('mobile-nav__link--active'));
      link.classList.add('mobile-nav__link--active');
    });
  });
}

// === ACTION BUTTONS ===
function initActionButtons() {
  document.querySelectorAll('.btn-action').forEach((button) => {
    button.addEventListener('click', () => {
      if (button.classList.contains('btn-action--loading')) return;

      button.classList.add('btn-action--loading');
      button.disabled = true;

      announceToScreenReader('Procesando solicitud');
    });
  });
}

// === INITIALIZATION ===
document.addEventListener('DOMContentLoaded', () => {
  initCollapsibles();
  initFilterChips();
  initKeyboardNavigation();
  initMobileNav();
  initActionButtons();

  console.log('UX interaction scripts initialized');
});

// === GLOBAL FUNCTIONS ===
window.uxHelpers = {
  showToast,
  initCollapsibles,
  initFilterChips,
  announceToScreenReader,
  updateProgressStep,
  trapFocus,
};
