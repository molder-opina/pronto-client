import { createApp } from 'vue';
import CartPanel from '../components/CartPanel.vue';
import { initClientBase } from '../modules/client-base';
import { initActiveOrders } from '../modules/active-orders';
import { initClientProfile } from '../modules/client-profile';
import { initMenuShortcuts } from '../modules/menu-shortcuts';
import { initializePostPaymentFeedback } from '../modules/post-payment-feedback';
import { initDraggableModals } from '../modules/draggable-modals';
import { initMicroAnimations } from '../modules/micro-animations';
import {
  buildTableCode,
  validateTableCode,
  parseTableCode,
  deriveAreaCodeFromLabel,
} from '../shared/table-code';
import { createIcons, icons } from 'lucide/dist/umd/lucide.js';

function setupGlobalErrorHandlers(): void {
  window.addEventListener('error', (event) => {
    console.error('[Global Error]', event.error);
    if (typeof window.showNotification === 'function') {
      window.showNotification('Ocurrió un error inesperado.', 'error');
    }
  });

  window.addEventListener('unhandledrejection', (event) => {
    console.error('[Unhandled Promise Rejection]', event.reason);
    if (typeof window.showNotification === 'function') {
      window.showNotification('Error de conexión. Verifica tu internet.', 'error');
    }
    event.preventDefault();
  });
}

function initCartApp(): void {
  const panel = document.getElementById('cart-panel');
  const backdrop = document.getElementById('cart-backdrop');

  if (panel) {
    // Create a wrapper for the Vue app
    const wrapper = document.createElement('div');
    wrapper.id = 'vue-cart-root';

    // Insert wrapper where the panel was
    panel.parentNode?.insertBefore(wrapper, panel);

    // Remove the server-rendered elements as Vue will render them
    panel.remove();
    if (backdrop) backdrop.remove();

    // Mount Vue App
    try {
      const app = createApp(CartPanel);
      app.mount(wrapper);
      console.log('[CartApp] Vue Cart mounted successfully');
    } catch (error) {
      console.error('[CartApp] Failed to mount Vue Cart:', error);
    }
  } else {
    console.warn('[CartApp] #cart-panel not found, skipping Vue mount');
  }
}

function initializeBaseApp(): void {
  initClientBase();
  initActiveOrders();
  initClientProfile();
  initMenuShortcuts();
  initializePostPaymentFeedback();
  initDraggableModals();
  initMicroAnimations();
  initCartApp();
}

function exposeTableCodeHelpers(): void {
  window.ProntoTableCode = {
    buildTableCode,
    validateTableCode,
    parseTableCode,
    deriveAreaCodeFromLabel,
  };
}

// Expose Lucide
(window as any).Lucide = {
  createIcons,
  icons,
};

document.addEventListener('DOMContentLoaded', () => {
  setupGlobalErrorHandlers();
  exposeTableCodeHelpers();
  initializeBaseApp();
});
