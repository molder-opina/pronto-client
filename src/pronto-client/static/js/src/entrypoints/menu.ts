import { bootstrapModule } from '../core/bootstrap';
import { initMenuFlow } from '../modules/menu-flow';
import { initMenuShortcuts } from '../modules/menu-shortcuts';
import { initSessionTimeoutMonitor } from '../modules/session-timeout';
import { initActiveOrders } from '../modules/active-orders';
import { CartPersistence } from '../modules/cart-persistence';
import { CheckoutHandler } from '../modules/checkout-handler';
import { initSession, getSessionId, setSessionId } from '../modules/session-manager';

console.log('[menu.ts] Script loaded, bootstrapping menu-flow...');

function getTableIdFromUrl(): number | null {
  const params = new URLSearchParams(window.location.search);
  const tableId = params.get('table');
  return tableId ? parseInt(tableId, 10) : null;
}

async function initializeApp() {
  const tableId = getTableIdFromUrl();

  if (tableId) {
    console.log('[menu.ts] Table ID from URL:', tableId);

    try {
      const sessionId = await initSession(tableId);
      console.log('[menu.ts] Session initialized:', sessionId);

      setSessionId(sessionId);
    } catch (err) {
      console.error('[menu.ts] Failed to initialize session:', err);
    }
  } else {
    console.warn('[menu.ts] No table_id found in URL, using localStorage session if available');
    const cachedSessionId = getSessionId();
    if (cachedSessionId) {
      console.log('[menu.ts] Using cached session:', cachedSessionId);
      setSessionId(cachedSessionId);
    }
  }
}

bootstrapModule(
  '[data-menu-root]',
  (root) => {
    console.log('[menu.ts] Initializing menu flow with root:', root);

    initializeApp();

    initMenuFlow(root);
    initMenuShortcuts();
    initSessionTimeoutMonitor();
    initActiveOrders();
    console.log('[menu.ts] Menu flow initialized successfully');
  },
  { name: 'menu-flow' }
);
