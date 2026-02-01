const SESSION_STORAGE_KEY = 'pronto-session-id';
const SESSION_TIMESTAMP_KEY = 'pronto-session-timestamp';
const ANONYMOUS_CLIENT_ID_KEY = 'pronto-anonymous-client-id';

// Maximum session age in milliseconds (24 hours)
const MAX_SESSION_AGE_MS = 24 * 60 * 60 * 1000;

type NotificationType = 'success' | 'error' | 'warning' | 'info';

interface NotificationPayload {
  message: string;
  type: NotificationType;
}

let activeNotification: HTMLDivElement | null = null;
const notificationQueue: NotificationPayload[] = [];
let fetchWrapped = false;

function safeSetHTML(element: HTMLElement, html: string): void {
  // Simple sanitization using textContent approach for maximum safety
  const tempDiv = document.createElement('div');
  tempDiv.innerHTML = html;

  // Remove all script tags and dangerous attributes
  const scripts = tempDiv.querySelectorAll('script');
  scripts.forEach((script) => script.remove());

  // Remove all event handlers from elements
  const allElements = tempDiv.querySelectorAll('*');
  allElements.forEach((el) => {
    const attributes = Array.from(el.attributes);
    attributes.forEach((attr) => {
      if (attr.name.startsWith('on')) {
        el.removeAttribute(attr.name);
      }
    });
  });

  element.innerHTML = tempDiv.innerHTML;
}

export function initClientBase(): void {
  ensureAnimations();
  setupGlobalLoading();
  attachWaiterButton();
  exposeGlobals();
  initStickyCartBar();
  const sessionId = getSessionId();
  if (sessionId) {
    void validateAndCleanSession().then(() => {
      window.setTimeout(() => void checkActiveOrdersGlobal(), 500);
    });
  } else {
    window.setTimeout(() => void checkActiveOrdersGlobal(), 500);
  }
}

let storeCancelReasonClientCache: boolean | null = null;
async function shouldStoreCancelReason(): Promise<boolean> {
  if (storeCancelReasonClientCache !== null) return storeCancelReasonClientCache;
  try {
    const res = await fetch('/api/config/store_cancel_reason');
    if (!res.ok) throw new Error('config missing');
    const data = await res.json().catch(() => ({}));
    const raw = data?.value ?? data?.config_value ?? data?.configValue;
    storeCancelReasonClientCache = String(raw ?? 'true').toLowerCase() !== 'false';
  } catch (_error) {
    storeCancelReasonClientCache = true;
  }
  return storeCancelReasonClientCache;
}

function exposeGlobals(): void {
  window.showNotification = showNotification;
  window.callWaiter = callWaiter;
  window.formatCurrency = formatCurrency;
  window.getSessionId = getSessionId;
  window.setSessionId = setSessionId;
  window.clearSessionId = clearSessionId;
  window.getAnonymousClientId = getAnonymousClientId;
  window.ensureAnonymousClientId = getOrCreateAnonymousClientId;
  window.getOrCreateAnonymousClientId = getOrCreateAnonymousClientId;
  window.createConfetti = createConfetti;
  window.viewFullTracker = viewFullTracker;
  window.requestCheckoutFromTracker = requestCheckoutFromTracker;
  window.cancelPendingOrder = cancelPendingOrder;
  window.refreshMiniTracker = () => void checkActiveOrdersGlobal();
}

function setupGlobalLoading(): void {
  const overlay = document.getElementById('global-loading');
  if (!overlay || fetchWrapped) return;

  let pending = 0;
  const start = (): void => {
    pending += 1;
    overlay.classList.add('visible');
  };
  const stop = (): void => {
    pending = Math.max(0, pending - 1);
    if (pending === 0) overlay.classList.remove('visible');
  };

  window.GlobalLoading = { start, stop };

  if (typeof window.fetch === 'function') {
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      start();
      try {
        const response = await originalFetch(...args);
        stop();
        return response;
      } catch (error) {
        stop();
        throw error;
      }
    };
  }

  fetchWrapped = true;
}

function attachWaiterButton(): void {
  const bind = (): void => {
    const button =
      document.querySelector<HTMLButtonElement>('.waiter-btn') ||
      document.querySelector<HTMLButtonElement>('.call-waiter-btn');
    if (button && !button.onclick) {
      button.addEventListener('click', () => callWaiter());
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind, { once: true });
  } else {
    bind();
  }
}

function showNotification(message: string, type: NotificationType = 'info'): void {
  if (activeNotification) {
    notificationQueue.push({ message, type });
    return;
  }
  const notification = document.createElement('div');
  notification.className = `pronto-notification pronto-notification--${type}`;
  notification.textContent = message;
  Object.assign(notification.style, {
    position: 'fixed',
    top: '100px',
    right: '20px',
    padding: '0.875rem 1.25rem',
    borderRadius: '8px',
    color: '#fff',
    fontSize: '14px',
    fontWeight: '500',
    zIndex: '9999',
    opacity: '0',
    transform: 'translateX(100%)',
    transition: 'all 0.2s ease',
  });
  notification.style.background = {
    success: '#22c55e',
    error: '#ef4444',
    warning: '#f97316',
    info: '#3b82f6',
  }[type];
  document.body.appendChild(notification);
  requestAnimationFrame(() => {
    notification.style.opacity = '1';
    notification.style.transform = 'translateX(0)';
  });
  activeNotification = notification;
  window.setTimeout(() => hideNotification(notification), 2500);
}

function hideNotification(notification: HTMLDivElement): void {
  requestAnimationFrame(() => {
    notification.style.opacity = '0';
    notification.style.transform = 'translateX(100%)';
    window.setTimeout(() => {
      notification.remove();
      activeNotification = null;
      const next = notificationQueue.shift();
      if (next) showNotification(next.message, next.type);
    }, 200);
  });
}

/**
 * Play the configured waiter bell sound
 */
function playWaiterBellSound(): void {
  try {
    // Get configured sound from APP_SETTINGS, default to bell1.mp3
    const soundFile = (window as any).APP_SETTINGS?.waiter_call_sound || 'bell1.mp3';
    const audio = new Audio(`/static/audio/${soundFile}`);

    // Set volume to 70% to avoid being too loud
    audio.volume = 0.7;

    // Play the sound (catch errors silently in case autoplay is blocked)
    audio.play().catch((error) => {
      console.log('Audio playback blocked or failed:', error);
    });
  } catch (error) {
    console.log('Error playing waiter bell sound:', error);
  }
}

function callWaiter(): void {
  const button =
    document.querySelector<HTMLButtonElement>('.waiter-btn') ||
    document.querySelector('.call-waiter-btn');

  // Throttling: prevent multiple calls while pending or confirmed
  if (button?.classList.contains('pending') || button?.classList.contains('confirmed')) {
    showNotification('Ya hay una solicitud activa. Por favor espera.', 'info');
    return;
  }

  const sessionId = getSessionId();
  const tableField = document.getElementById('table-number') as HTMLInputElement | null;
  const tableNumber = tableField?.value || 'N/A';

  button?.classList.add('ringing');
  window.setTimeout(() => button?.classList.remove('ringing'), 600);

  fetch('/api/call-waiter', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, table_number: tableNumber }),
  })
    .then((response) => response.json())
    .then((data) => {
      button?.classList.add('pending');
      showNotification('Mesero llamado. ¡Te atenderemos pronto!', 'success');

      // Play the configured bell sound
      playWaiterBellSound();

      if (data.call_id) checkWaiterCallStatus(data.call_id, button);
    })
    .catch(() => {
      button?.classList.remove('pending');
      showNotification('Error al llamar al mesero. Intenta de nuevo.', 'error');
    });
}

function checkWaiterCallStatus(callId: number, button?: HTMLElement | null): void {
  // Get cooldown from settings (default 10 seconds)
  const cooldownSeconds = (window as any).APP_SETTINGS?.waiter_call_cooldown_seconds || 10;
  const cooldownMs = cooldownSeconds * 1000;

  // Set up SSE listener for immediate notification
  const notificationManager = (window as any).notificationManager;
  let sseUnsubscribe: (() => void) | null = null;

  if (notificationManager) {
    const handleConfirmation = (data: any) => {
      if (data.call_id === callId && data.status === 'confirmed') {
        if (sseUnsubscribe) sseUnsubscribe();
        if (interval) window.clearInterval(interval);
        button?.classList.remove('pending');
        button?.classList.add('confirmed');
        showNotification('¡El mesero va en camino! 🎉', 'success');
        window.setTimeout(() => button?.classList.remove('confirmed'), cooldownMs);
      }
    };

    notificationManager.on('customers.waiter_call', handleConfirmation);
    sseUnsubscribe = () => notificationManager.off('customers.waiter_call', handleConfirmation);
  }

  // Fallback polling (reduced to 2 seconds for faster response if SSE fails)
  let attempts = 0;
  const interval = window.setInterval(async () => {
    attempts += 1;
    try {
      const response = await fetch(`/api/waiter-calls/${callId}/status`);
      const data = await response.json();
      if (data.status === 'confirmed') {
        if (sseUnsubscribe) sseUnsubscribe();
        window.clearInterval(interval);
        button?.classList.remove('pending');
        button?.classList.add('confirmed');
        showNotification('¡El mesero va en camino! 🎉', 'success');
        window.setTimeout(() => button?.classList.remove('confirmed'), cooldownMs);
      } else if (attempts >= 30) {
        if (sseUnsubscribe) sseUnsubscribe();
        window.clearInterval(interval);
        button?.classList.remove('pending');
        showNotification('La solicitud sigue pendiente', 'info');
      }
    } catch {
      if (sseUnsubscribe) sseUnsubscribe();
      window.clearInterval(interval);
      button?.classList.remove('pending');
    }
  }, 2000);
}

function formatCurrency(
  value: number,
  options: { locale?: string; currency?: string } = {}
): string {
  const locale = options.locale || window.APP_SETTINGS?.currency_locale || 'es-MX';
  const currency =
    options.currency ||
    window.APP_SETTINGS?.currency_code ||
    window.APP_CONFIG.currency_code ||
    'MXN';
  try {
    return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(value || 0);
  } catch {
    const symbol = window.APP_SETTINGS?.currency_symbol || window.APP_CONFIG.currency_symbol || '$';
    return `${symbol}${(value || 0).toFixed(2)}`;
  }
}

function getSessionId(): number | null {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;

    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) {
      clearSessionId();
      return null;
    }

    const tsRaw = localStorage.getItem(SESSION_TIMESTAMP_KEY);
    const ts = tsRaw ? Number(tsRaw) : null;
    if (ts && Number.isFinite(ts) && Date.now() - ts > MAX_SESSION_AGE_MS) {
      clearSessionId();
      return null;
    }

    return parsed;
  } catch (err) {
    console.warn('[ClientBase] Could not read session id:', err);
    return null;
  }
}

function setSessionId(sessionId: number): void {
  try {
    if (!Number.isFinite(sessionId)) return;
    localStorage.setItem(SESSION_STORAGE_KEY, String(sessionId));
    localStorage.setItem(SESSION_TIMESTAMP_KEY, String(Date.now()));
  } catch (err) {
    console.warn('[ClientBase] Could not persist session id:', err);
  }
}

function clearSessionId(): void {
  try {
    localStorage.removeItem(SESSION_STORAGE_KEY);
    localStorage.removeItem(SESSION_TIMESTAMP_KEY);
  } catch (err) {
    console.warn('[ClientBase] Error clearing session id:', err);
  }
}

function getAnonymousClientId(): string | null {
  // Server generates and tracks anonymous IDs
  console.warn('[DEPRECATED] getAnonymousClientId() - Server manages anonymous IDs');
  return null;
}

function setAnonymousClientId(id: string): void {
  // No-op: Server handles anonymous ID generation
  console.warn('[DEPRECATED] setAnonymousClientId() - Server manages anonymous IDs');
}

function ensureAnonymousClientId(): string {
  // Generate a client-side ID only for the current page load (not persisted)
  // This is used only as a fallback identifier in the request payload
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `anon-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function getOrCreateAnonymousClientId(): string {
  return ensureAnonymousClientId();
}

function regenerateAnonymousClientId(reason?: string): string {
  const generated =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `anon-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
  try {
    localStorage.setItem(ANONYMOUS_CLIENT_ID_KEY, generated);
  } catch (err) {
    console.warn('[ClientBase] Error storing anonymous client id:', err);
  }
  console.log('[ClientBase] Regenerated anonymous client id', reason || '');
  return generated;
}

/**
 * Validates the current session with the server.
 * All session validation logic is now server-side.
 * The server manages session expiration, ownership, and cleanup.
 */
async function validateAndCleanSession(): Promise<void> {
  const currentSessionId = getSessionId();
  if (!currentSessionId) {
    return;
  }

  // Server-side validation via API endpoint
  // The server will check:
  // 1. Session exists in database
  // 2. Session belongs to the current user (via Flask session cookie)
  // 3. Session is not expired
  // 4. Session status is valid
  try {
    // Call server validation endpoint
    // The server will validate against Flask session (HTTP-only cookie)
    // and return current session state
    const response = await fetch('/api/session/validate', {
      method: 'GET',
      credentials: 'same-origin', // Include cookies
      headers: {
        Accept: 'application/json',
      },
    });

    if (!response.ok) {
      // Session validation failed (404, 410, or 500)
      // The server already cleared the Flask session
      console.warn('[ClientBase] Session validation failed:', response.status);

      // For 404 (not found) and 410 (gone/finished), clear local state
      if (response.status === 404 || response.status === 410) {
        regenerateAnonymousClientId(`validate_failed_${response.status}`);
        clearSessionId();
      }
      return;
    }

    const data = await response.json();
    console.log('[ClientBase] Session validated:', data);

    // Response format: {session: {id, status, table_number, total_amount}, anonymous_client_id}
    if (data.session?.id) {
      setSessionId(Number(data.session.id));
    }
  } catch (error) {
    // Network error - log and clear session
    console.warn('[ClientBase] Error validating session:', error);
    clearSessionId();
  }
}

function createConfetti(): void {
  const colors = [
    '#667eea',
    '#764ba2',
    '#f093fb',
    '#f5576c',
    '#4facfe',
    '#00f2fe',
    '#FF6B35',
    '#FF8C42',
  ];
  for (let i = 0; i < 40; i += 1) {
    window.setTimeout(() => {
      const piece = document.createElement('div');
      piece.className = 'confetti';
      piece.style.left = `${Math.random() * 100}%`;
      piece.style.background = colors[Math.floor(Math.random() * colors.length)];
      piece.style.animationDelay = `${Math.random() * 1.5}s`;
      document.body.appendChild(piece);
      window.setTimeout(() => piece.remove(), 4000);
    }, i * 30);
  }
}

function ensureAnimations(): void {
  if (document.getElementById('pronto-animations')) return;
  const style = document.createElement('style');
  style.id = 'pronto-animations';
  style.textContent = `
        .confetti {
            position: fixed;
            width: 10px;
            height: 10px;
            top: -10px;
            z-index: 9999;
            animation: confetti-fall 3s linear forwards;
        }
        @keyframes confetti-fall {
            to { transform: translateY(100vh) rotate(360deg); opacity: 0; }
        }
        .ringing {
            animation: ring 0.5s ease-in-out;
        }
        @keyframes ring {
            0%, 100% { transform: rotate(0deg); }
            25% { transform: rotate(10deg); }
            75% { transform: rotate(-10deg); }
        }
    `;
  document.head.appendChild(style);
}

// ============================================================================
// Mini-Tracker Global Functions (for showing order status on all pages)
// ============================================================================

let miniTrackerInterval: number | null = null;
let miniTrackerOrders: any[] = [];
const TRACKER_STATUS_WEIGHTS: Record<string, number> = {
  requested: 0,
  waiter_accepted: 20,
  kitchen_in_progress: 40,
  ready_for_delivery: 70,
  delivered: 100,
};
const CANONICAL_TO_LEGACY: Record<string, string> = {
  new: 'requested',
  queued: 'waiter_accepted',
  preparing: 'kitchen_in_progress',
  ready: 'ready_for_delivery',
  awaiting_payment: 'wait_for_payment',
  paid: 'payed',
  delivered: 'delivered',
  cancelled: 'cancelled',
};
const TRACKER_STATUS_LABELS: Record<string, string> = {
  requested: 'Pedido recibido',
  waiter_accepted: 'Mesero asignado',
  kitchen_in_progress: 'En preparación',
  ready_for_delivery: 'Listo para entregar',
  delivered: 'Entregado',
};

const getTrackerOrderId = (order: any): number => {
  const raw = order?.id ?? order?.order_id ?? order?.orderId;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : 0;
};

const getTrackerStatus = (order: any): string => {
  const legacy = order?.workflow_status_legacy;
  if (legacy) return legacy;
  const status = order?.workflow_status || order?.status || 'requested';
  return CANONICAL_TO_LEGACY[status] || status;
};

const formatTrackerStatus = (status: string): string =>
  TRACKER_STATUS_LABELS[status] || status || 'Preparando...';

const isOrderCancellable = (order: any): boolean => {
  const status = getTrackerStatus(order);
  return status === 'requested' || status === 'waiter_accepted';
};

const getSelectedMiniTrackerOrderId = (): number | null => {
  const select = document.getElementById('mini-tracker-order-select') as HTMLSelectElement | null;
  if (select && select.value) {
    const parsed = Number(select.value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  if (miniTrackerOrders.length === 1) {
    return getTrackerOrderId(miniTrackerOrders[0]);
  }
  return null;
};

function renderMiniTrackerControls(orders: any[]): void {
  const statusEl = document.getElementById('mini-tracker-status');
  const progressEl = document.getElementById('mini-tracker-progress');
  const percentageEl = document.getElementById('mini-tracker-percentage');
  const checkoutBtn = document.getElementById('request-checkout-btn') as HTMLButtonElement | null;
  const cancelBtn = document.getElementById('cancel-order-button') as HTMLButtonElement | null;
  const selectWrapper = document.getElementById('mini-tracker-order-select-wrapper');
  const selectEl = document.getElementById('mini-tracker-order-select') as HTMLSelectElement | null;

  const normalized = (orders || []).map((order: any) => ({
    id: getTrackerOrderId(order),
    status: getTrackerStatus(order),
  }));

  if (selectWrapper && selectEl) {
    if (normalized.length > 1) {
      const previous = selectEl.value;
      selectWrapper.style.display = 'flex';
      safeSetHTML(
        selectEl,
        normalized
          .map(
            (order) =>
              `<option value="${order.id}">
                            Orden #${order.id} · ${formatTrackerStatus(order.status)}
                        </option>`
          )
          .join('')
      );
      const hasPrevious = previous && normalized.some((order) => String(order.id) === previous);
      selectEl.value = hasPrevious ? previous : String(normalized[0].id);
    } else {
      selectWrapper.style.display = 'none';
      selectEl.innerHTML = '';
    }
  }

  const selectedId =
    (selectEl && selectEl.value ? Number(selectEl.value) : null) ??
    (normalized[0] ? normalized[0].id : null);
  const selectedOrder =
    normalized.find((order) => order.id === selectedId) ||
    (normalized.length ? normalized[0] : null);

  const selectedStatus = selectedOrder ? selectedOrder.status : 'requested';
  const statusLabel = formatTrackerStatus(selectedStatus);
  if (statusEl) {
    statusEl.textContent =
      normalized.length > 1 && selectedOrder
        ? `Orden #${selectedOrder.id} · ${statusLabel}`
        : statusLabel;
  }

  const progress = TRACKER_STATUS_WEIGHTS[selectedStatus] ?? 0;
  if (progressEl) progressEl.style.width = `${progress}%`;
  if (percentageEl) percentageEl.textContent = `${progress}%`;

  const allDelivered =
    normalized.length > 0 && normalized.every((order) => order.status === 'delivered');
  if (checkoutBtn) {
    checkoutBtn.style.display = allDelivered ? 'inline-flex' : 'none';
  }

  const hasCancellable = normalized.some((order) => isOrderCancellable(order));
  const selectedIsCancellable = selectedOrder ? isOrderCancellable(selectedOrder) : false;
  if (cancelBtn) {
    cancelBtn.style.display = hasCancellable ? 'inline-flex' : 'none';
    cancelBtn.disabled = !selectedIsCancellable;
    cancelBtn.title = selectedIsCancellable
      ? 'Cancelar la orden seleccionada'
      : 'Selecciona una orden que aún se pueda cancelar';
  }
}

function resetClientSession(reason?: string): void {
  try {
    localStorage.removeItem('pronto-cart');
    localStorage.removeItem(SESSION_STORAGE_KEY);
    localStorage.removeItem(SESSION_TIMESTAMP_KEY);
    localStorage.removeItem(ANONYMOUS_CLIENT_ID_KEY);
  } catch (err) {
    console.warn('[ClientBase] Error clearing localStorage:', err);
  }
  console.log('[ClientBase] Resetting client session', reason || '');
  window.location.href = '/';
}

async function checkActiveOrdersGlobal(): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId) return;

  try {
    const response = await fetch(`/api/session/${sessionId}/orders`);
    if (!response.ok) {
      // If session not found (404), clear the stale session ID
      if (response.status === 404) {
        console.warn('[ClientBase] Session not found, clearing stale session ID');
        regenerateAnonymousClientId('orders_404');
        clearSessionId();
      }
      return;
    }

    const data = await response.json();
    const orders = data.orders || [];
    const session = data.session || {};

    // Session statuses that indicate the session is finished
    const finishedStatuses = ['closed', 'paid', 'billed', 'cancelled'];
    const isSessionFinished = finishedStatuses.includes(session.status);

    // Check if all orders are paid
    const allOrdersPaid =
      orders.length > 0 && orders.every((o: any) => o.payment_status === 'paid');

    // Only show if there are unpaid orders and session is not finished
    if (orders.length > 0 && !isSessionFinished && !allOrdersPaid) {
      miniTrackerOrders = orders;
      showMiniTrackerGlobal(orders);
      startMiniTrackerUpdates();
    } else {
      // Reset client session entirely and go back to start
      resetClientSession(isSessionFinished ? 'session_finished' : 'orders_paid');
    }
  } catch (error) {
    console.warn('[ClientBase] Error checking active orders:', error);
  }
}

function showMiniTrackerGlobal(orders: any[]): void {
  const miniTracker = document.getElementById('mini-tracker');

  if (!miniTracker) return;

  miniTrackerOrders = orders;
  miniTracker.classList.add('visible');
  renderMiniTrackerControls(orders);

  const selectEl = document.getElementById('mini-tracker-order-select') as HTMLSelectElement | null;
  if (selectEl && !selectEl.dataset.bound) {
    selectEl.addEventListener('change', () => renderMiniTrackerControls(miniTrackerOrders));
    selectEl.dataset.bound = 'true';
  }
}

function startMiniTrackerUpdates(): void {
  if (miniTrackerInterval) {
    window.clearInterval(miniTrackerInterval);
  }

  miniTrackerInterval = window.setInterval(() => {
    void updateMiniTrackerGlobal();
  }, 5000);
}

async function updateMiniTrackerGlobal(): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId) return;

  try {
    const response = await fetch(`/api/session/${sessionId}/orders`);
    if (!response.ok) return;

    const data = await response.json();
    const orders = data.orders || [];
    const session = data.session || {};

    // Session statuses that indicate the session is finished
    const finishedStatuses = ['closed', 'paid', 'cancelled'];
    const isSessionFinished = finishedStatuses.includes(session.status);

    // Check if all orders are paid
    const allOrdersPaid =
      orders.length > 0 && orders.every((o: any) => o.payment_status === 'paid');

    if (orders.length > 0 && !isSessionFinished && !allOrdersPaid) {
      miniTrackerOrders = orders;
      showMiniTrackerGlobal(orders);
    } else {
      // Hide mini-tracker and clear session if finished or without orders
      const miniTracker = document.getElementById('mini-tracker');
      miniTracker?.classList.remove('visible');
      if (miniTrackerInterval) {
        window.clearInterval(miniTrackerInterval);
        miniTrackerInterval = null;
      }
      miniTrackerOrders = [];
      clearSessionId();
    }
  } catch (error) {
    console.warn('[ClientBase] Error updating mini-tracker:', error);
  }
}

function viewFullTracker(): void {
  const selectedId = getSelectedMiniTrackerOrderId();
  if (selectedId) {
    sessionStorage.setItem('pronto-highlight-order', String(selectedId));
  }

  if (typeof (window as any).switchView === 'function') {
    (window as any).switchView('orders');
    if (selectedId) {
      window.setTimeout(() => {
        const targetCard = document.querySelector<HTMLElement>(`[data-order-id="${selectedId}"]`);
        targetCard?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 400);
    }
  } else {
    // Redirect to main page with orders view
    const highlightParam = selectedId ? `&order_id=${selectedId}` : '';
    window.location.href = `/?view=orders${highlightParam}`;
  }
}

function requestCheckoutFromTracker(): void {
  // Try to use existing checkout function
  if (typeof (window as any).requestCheck === 'function') {
    (window as any).requestCheck();
  } else if (typeof (window as any).openAccountSummary === 'function') {
    (window as any).openAccountSummary();
  } else {
    showNotification('Redirigiendo para pedir cuenta...', 'info');
    window.location.href = '/?view=details';
  }
}

function cancelPendingOrder(): void {
  const sessionId = getSessionId();
  if (!sessionId) {
    showNotification('No hay sesión activa', 'error');
    return;
  }

  (async () => {
    try {
      const response = await fetch(`/api/session/${sessionId}/orders`);
      if (!response.ok) {
        showNotification('No se pudieron cargar las órdenes activas', 'error');
        return;
      }

      const data = await response.json();
      const orders = data.orders || [];
      miniTrackerOrders = orders;
      renderMiniTrackerControls(orders);

      const cancellable = orders.filter((order: any) => isOrderCancellable(order));
      if (!cancellable.length) {
        showNotification('El pedido ya está en preparación y no puede cancelarse', 'warning');
        return;
      }

      let targetOrderId: number | null = null;
      const selectedId = getSelectedMiniTrackerOrderId();
      if (selectedId && cancellable.some((order: any) => getTrackerOrderId(order) === selectedId)) {
        targetOrderId = selectedId;
      } else if (cancellable.length === 1) {
        targetOrderId = getTrackerOrderId(cancellable[0]);
      } else {
        targetOrderId = await showCancelOrderSelector(cancellable);
      }

      if (!targetOrderId) return;

      const reason = window.prompt('¿Por qué deseas cancelar esta orden?')?.trim();
      if (!reason) {
        showNotification('Debes indicar un motivo para cancelar la orden', 'warning');
        return;
      }

      const shouldStoreReason = await shouldStoreCancelReason();

      const cancelResponse = await fetch(`/api/orders/${targetOrderId}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          ...(shouldStoreReason ? { reason } : {}),
        }),
      });

      if (!cancelResponse.ok) {
        const errorData = await cancelResponse.json().catch(() => ({}));
        showNotification(errorData.error || 'No se pudo cancelar el pedido', 'error');
        return;
      }

      showNotification('Pedido cancelado exitosamente', 'success');

      // Refresh orders to keep tracking remaining ones
      const refreshResponse = await fetch(`/api/session/${sessionId}/orders`);
      if (refreshResponse.ok) {
        const updated = await refreshResponse.json();
        miniTrackerOrders = updated.orders || [];
        if (miniTrackerOrders.length > 0) {
          showMiniTrackerGlobal(miniTrackerOrders);
          renderMiniTrackerControls(miniTrackerOrders);
          if (typeof (window as any).refreshActiveOrders === 'function') {
            (window as any).refreshActiveOrders();
          }
          return;
        }
      }

      const miniTracker = document.getElementById('mini-tracker');
      miniTracker?.classList.remove('visible');
      clearSessionId();
      window.setTimeout(() => window.location.reload(), 800);
    } catch (error) {
      console.error('[ClientBase] Error canceling order:', error);
      showNotification('Error al cancelar el pedido', 'error');
    }
  })();
}

function showCancelOrderSelector(orders: any[]): Promise<number | null> {
  return new Promise((resolve) => {
    if (orders.length === 1) {
      const orderId = getTrackerOrderId(orders[0]);
      const confirmSingle = window.confirm(`Cancelar la orden #${orderId}?`);
      resolve(confirmSingle ? orderId : null);
      return;
    }

    // Build simple modal with a select
    const overlay = document.createElement('div');
    overlay.style.position = 'fixed';
    overlay.style.inset = '0';
    overlay.style.background = 'rgba(0,0,0,0.45)';
    overlay.style.zIndex = '2000';
    overlay.style.display = 'flex';
    overlay.style.alignItems = 'center';
    overlay.style.justifyContent = 'center';

    const modal = document.createElement('div');
    modal.style.background = 'white';
    modal.style.borderRadius = '12px';
    modal.style.padding = '1.5rem';
    modal.style.width = '320px';
    modal.style.boxShadow = '0 20px 60px rgba(0,0,0,0.25)';
    safeSetHTML(
      modal,
      `
            <h3 style="margin:0 0 0.75rem 0; color:#1f2937;">Cancelar orden</h3>
            <p style="margin:0 0 0.75rem 0; color:#6b7280; font-size:0.95rem;">Solo se pueden cancelar órdenes aún no enviadas a cocina.</p>
            <label style="display:block; margin-bottom:0.75rem; color:#374151; font-size:0.95rem;">
                Selecciona la orden:
                <select id="cancel-order-select" style="width:100%; margin-top:0.35rem; padding:0.5rem; border:1px solid #e5e7eb; border-radius:8px;">
                    ${orders
                      .map(
                        (o: any) => `
                                <option value="${getTrackerOrderId(o)}">
                                    #${getTrackerOrderId(o)} · ${o.items?.length || 0} productos · ${formatTrackerStatus(getTrackerStatus(o))}
                                </option>
                            `
                      )
                      .join('')}
                </select>
            </label>
            <div style="display:flex; gap:0.5rem; justify-content:flex-end;">
                <button id="cancel-order-cancel" style="padding:0.5rem 0.9rem; border:1px solid #e5e7eb; border-radius:8px; background:#f9fafb; cursor:pointer;">Cerrar</button>
                <button id="cancel-order-confirm" style="padding:0.5rem 1rem; border:none; border-radius:8px; background:#ef4444; color:white; cursor:pointer;">Cancelar orden</button>
            </div>
        `
    );

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    const cleanup = () => {
      overlay.remove();
    };

    modal.querySelector('#cancel-order-cancel')?.addEventListener('click', () => {
      cleanup();
      resolve(null);
    });

    modal.querySelector('#cancel-order-confirm')?.addEventListener('click', () => {
      const select = modal.querySelector('#cancel-order-select') as HTMLSelectElement | null;
      const val = select?.value;
      cleanup();
      resolve(val ? Number(val) : null);
    });
  });
}

export function initStickyCartBar(): void {
  const stickyBar = document.getElementById('sticky-cart-bar');
  const undoSnackbar = document.getElementById('undo-snackbar');
  const undoBtn = document.getElementById('undo-btn');

  if (!stickyBar || !undoSnackbar || !undoBtn) return;

  undoBtn.addEventListener('click', () => {
    if (removedItemCache) {
      restoreRemovedItem();
    }
    hideUndoSnackbar();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && undoSnackbar.classList.contains('undo-snackbar--visible')) {
      hideUndoSnackbar();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
      if (removedItemCache && undoSnackbar.classList.contains('undo-snackbar--visible')) {
        restoreRemovedItem();
        hideUndoSnackbar();
      }
    }
  });

  // Listen for cart updates to sync sticky cart bar
  window.addEventListener('cart-updated', ((
    event: CustomEvent<{ count: number; total: number }>
  ) => {
    const { count, total } = event.detail || { count: 0, total: 0 };
    updateStickyCartBar(count, total);
  }) as EventListener);
}

export function showStickyCartBar(): void {
  const stickyBar = document.getElementById('sticky-cart-bar');
  if (stickyBar) {
    stickyBar.classList.add('sticky-cart-bar--visible');
  }
}

export function hideStickyCartBar(): void {
  const stickyBar = document.getElementById('sticky-cart-bar');
  if (stickyBar) {
    stickyBar.classList.remove('sticky-cart-bar--visible');
  }
}

export function updateStickyCartBar(count: number, total: number): void {
  const countEl = document.getElementById('sticky-cart-count');
  const totalEl = document.getElementById('sticky-cart-total');
  const itemsEl = document.getElementById('sticky-cart-items');

  if (countEl) countEl.textContent = count.toString();
  if (totalEl) totalEl.textContent = formatCurrency(total);
  if (itemsEl) {
    itemsEl.textContent = count === 1 ? '1 artículo' : `${count} artículos`;
  }

  if (count > 0) {
    showStickyCartBar();
  } else {
    hideStickyCartBar();
  }
}

export function showUndoSnackbar(itemName: string): void {
  const snackbar = document.getElementById('undo-snackbar');
  const messageEl = snackbar?.querySelector('.undo-snackbar__message');

  if (snackbar && messageEl) {
    messageEl.textContent = `${itemName} eliminado`;
    snackbar.classList.add('undo-snackbar--visible');

    if (undoTimeoutId) {
      clearTimeout(undoTimeoutId);
    }

    undoTimeoutId = window.setTimeout(() => {
      hideUndoSnackbar();
    }, 4000);
  }
}

export function hideUndoSnackbar(): void {
  const snackbar = document.getElementById('undo-snackbar');
  if (snackbar) {
    snackbar.classList.remove('undo-snackbar--visible');
  }
  if (undoTimeoutId) {
    clearTimeout(undoTimeoutId);
    undoTimeoutId = null;
  }
  removedItemCache = null;
}

export function setRemovedItem(item: any, index: number): void {
  removedItemCache = { item, index };
}

function restoreRemovedItem(): void {
  if (!removedItemCache) return;

  try {
    const cartPersistence = (window as any).CartPersistence;
    if (cartPersistence && typeof cartPersistence.getInstance === 'function') {
      const persistence = cartPersistence.getInstance();
      if (typeof persistence.addItem === 'function') {
        persistence.addItem(removedItemCache.item);
        console.log('[StickyCart] Item restored:', removedItemCache.item.name);
      }
    }
  } catch (error) {
    console.warn('[StickyCart] Could not restore item:', error);
  }
}

let removedItemCache: { item: any; index: number } | null = null;
let undoTimeoutId: number | null = null;
