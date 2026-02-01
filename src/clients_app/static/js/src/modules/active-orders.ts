// Active orders, tabs, and "Pedir cuenta" flow for client app
// Extracted from legacy inline script in base.html and converted to a module.

import { getSessionId } from './session-manager';

// Simple view name type
export type ViewName = 'menu' | 'orders' | 'details';

interface ActiveOrdersResponse {
  orders?: any[];
  session?: any & { status?: string };
}

function escape(str: any): string {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function sanitizeHtml(html: string): string {
  const div = document.createElement('div');
  div.textContent = html;
  return div.innerHTML;
}

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

const normalizeWorkflowStatus = (status?: string, legacy?: string): string => {
  if (legacy) return legacy;
  if (status && status in CANONICAL_TO_LEGACY) return CANONICAL_TO_LEGACY[status];
  return status || 'requested';
};

const getWorkflowStatus = (order: any): string =>
  normalizeWorkflowStatus(order?.workflow_status || order?.status, order?.workflow_status_legacy);

let currentView: ViewName = 'menu';
let activeOrdersData: ActiveOrdersResponse | null = null;
let ordersRefreshInterval: number | null = null;
let sessionValidationInterval: number | null = null;
let sessionValidationIntervalMinutes = 15; // Default value, will be loaded from config

type NormalizedOrderItem = {
  quantity: number;
  name: string;
  total_price: number;
  modifiers?: Array<{ name: string }>;
};

type NormalizedOrder = {
  order_id: number;
  created_at: string;
  total: number;
  workflow_status: string;
  status: string;
  table_number?: string | null;
  customer_notes?: string;
  items: NormalizedOrderItem[];
  session_id?: number;
};

// Public initializer, called from entrypoints/base.ts
export function initActiveOrders(): void {
  const viewTabs = document.getElementById('view-tabs');
  // If the layout does not include view tabs, skip initialization
  if (!viewTabs) return;

  const tabMenu = document.getElementById('tab-menu') as HTMLButtonElement | null;
  const tabOrders = document.getElementById('tab-orders') as HTMLButtonElement | null;
  const tabDetails = document.getElementById('tab-details') as HTMLButtonElement | null;
  const tabRequestCheck = document.getElementById('tab-request-check') as HTMLButtonElement | null;
  const requestCheckBtn = document.getElementById('request-check-btn') as HTMLButtonElement | null;

  tabMenu?.addEventListener('click', () => switchView('menu'));
  tabOrders?.addEventListener('click', () => switchView('orders'));
  tabDetails?.addEventListener('click', () => switchView('details'));
  tabRequestCheck?.addEventListener('click', () => void requestCheck());
  requestCheckBtn?.addEventListener('click', () => void requestCheck());

  // Wire up outside-hours modal continue button
  const outsideHoursContinueBtn = document.getElementById('outside-hours-continue-btn');
  outsideHoursContinueBtn?.addEventListener('click', closeOutsideHoursModal);

  // Wire up footer business hours button
  const footerHoursBtn = document.getElementById('footer-hours-btn');
  footerHoursBtn?.addEventListener('click', toggleBusinessHoursDisplay);

  // Ensure menu is visible on initial load
  const mainContent = document.querySelector('main') as HTMLElement | null;
  const ordersSection = document.getElementById('active-orders-section') as HTMLElement | null;
  const checkoutSection = document.getElementById('checkout-section') as HTMLElement | null;

  if (mainContent) mainContent.style.display = 'block';
  if (ordersSection) ordersSection.style.display = 'none';
  if (checkoutSection) checkoutSection.style.display = 'none';

  // Start auto-refresh and load business hours
  startOrdersAutoRefresh();
  startSessionValidation();
  void loadBusinessHours();
  attachDetailModalHandlers();

  // Check URL params for initial view
  const params = new URLSearchParams(window.location.search);
  const initialView = params.get('view') || params.get('tab');
  if (initialView === 'orders') {
    switchView('orders');
    // Clean URL without reloading
    const url = new URL(window.location.href);
    url.searchParams.delete('tab');
    url.searchParams.delete('view');
    window.history.replaceState({}, '', url.toString());
  } else if (initialView === 'details' || initialView === 'checkout') {
    switchView('details');
  }

  // Re-check view state on load to ensure it wasn't overridden
  const enforceViewState = () => {
    const p = new URLSearchParams(window.location.search);
    const v = p.get('view') || p.get('tab');
    if (v === 'details' || v === 'checkout') {
      console.log('[ActiveOrders] Enforcing details view on load');
      switchView('details');
    }
  };

  window.addEventListener('load', enforceViewState);
  // Backup check in case load already fired or scripts ran late
  setTimeout(enforceViewState, 100);
  setTimeout(enforceViewState, 500);
}

// Expose API immediately to avoid race conditions
(window as any).switchView = switchView;
(window as any).openAccountSummary = openAccountSummary;
(window as any).refreshActiveOrders = refreshActiveOrders;
(window as any).closeOutsideHoursModal = closeOutsideHoursModal;

function switchView(view: ViewName): void {
  currentView = view;

  const tabMenu = document.getElementById('tab-menu');
  const tabOrders = document.getElementById('tab-orders');
  const tabDetails = document.getElementById('tab-details');
  const requestCheckTab = document.getElementById('tab-request-check');

  tabMenu?.classList.toggle('active', view === 'menu');
  tabOrders?.classList.toggle('active', view === 'orders');
  tabDetails?.classList.toggle('active', view === 'details');
  requestCheckTab?.classList.remove('active');

  const mainContent = document.querySelector('main') as HTMLElement | null;
  const ordersSection = document.getElementById('active-orders-section') as HTMLElement | null;
  const checkoutSection = document.getElementById('checkout-section') as HTMLElement | null;
  const footer = document.querySelector('.footer') as HTMLElement | null;

  if (!mainContent) return;

  // Reset all displays
  mainContent.style.display = 'none';
  if (ordersSection) ordersSection.style.display = 'none';
  if (checkoutSection) checkoutSection.style.display = 'none';

  // Update footer visibility default
  if (footer) footer.classList.remove('hide-on-checkout');

  if (view === 'menu') {
    mainContent.style.display = 'block';
  } else if (view === 'orders') {
    if (ordersSection) ordersSection.style.display = 'block';
    if (footer) footer.classList.add('hide-on-checkout');
    void refreshActiveOrders();
  } else if (view === 'details') {
    if (checkoutSection) {
      checkoutSection.style.display = 'block';
      checkoutSection.classList.add('active');
    }
    if (footer) footer.classList.add('hide-on-checkout');

    // Refresh orders to populate history, but don't show full loading screen if we have cached data?
    // actually, better to just refresh.
    refreshActiveOrders(false).then(() => {
      renderCheckoutHistory();
    });

    // Manage Customer Info Accordion State
    updateCustomerAccordionState();
  }

  if (view !== 'details' && checkoutSection) {
    checkoutSection.classList.remove('active');
  }
}

async function refreshActiveOrders(showLoading: boolean = true): Promise<void> {
  const ordersSection = document.getElementById('active-orders-section') as HTMLElement | null;
  const singleTracker = document.getElementById('single-order-tracker') as HTMLElement | null;
  const multipleView = document.getElementById('multiple-orders-view') as HTMLElement | null;

  if (showLoading && ordersSection && singleTracker) {
    singleTracker.style.display = 'block';
    if (multipleView) multipleView.style.display = 'none';
    singleTracker.innerHTML = `
            <div style="text-align: center; padding: 3rem 1rem;">
                <div style="font-size: 2.5rem; margin-bottom: 1rem;">⏳</div>
                <h3 style="color: var(--text); margin-bottom: 0.5rem;">Cargando órdenes...</h3>
                <p style="color: var(--muted);">Estamos sincronizando tu pedido.</p>
            </div>
        `;
  }

  const sessionId = await resolveSessionId();

  if (!sessionId) {
    // Show message in orders section instead of hiding
    if (ordersSection && singleTracker) {
      singleTracker.style.display = 'block';
      if (multipleView) multipleView.style.display = 'none';
      safeSetHTML(
        singleTracker,
        `
                <div style="text-align: center; padding:3rem 1rem;">
                    <p style="font-size:3rem; margin-bottom: 1rem;">🍽️</p>
                    <h3 style="color: var(--text); margin-bottom: 0.5rem;">No hay pedidos activos</h3>
                    <p style="color: var(--muted);">Realiza un pedido desde el menú para ver su estado aquí.</p>
                </div>
            `
      );
    }
    return;
  }

  try {
    const response = await fetch(`/api/session/${sessionId}/orders`);
    if (!response.ok) {
      // If session not found (404), clear the stale session ID
      if (response.status === 404) {
        console.warn('[ActiveOrders] Session not found, clearing stale session ID');
        localStorage.removeItem('pronto-session-id');
        // Show message instead of hiding
        if (ordersSection && singleTracker) {
          singleTracker.style.display = 'block';
          if (multipleView) multipleView.style.display = 'none';
          singleTracker.innerHTML = `
                        <div style="text-align: center; padding: 3rem 1rem;">
                            <p style="font-size: 3rem; margin-bottom: 1rem;">⚠️</p>
                            <h3 style="color: var(--text); margin-bottom: 0.5rem;">Sesión cerrada</h3>
                            <p style="color: var(--muted); margin-bottom: 1.5rem;">Tu sesión fue cerrada. Puedes hacer un nuevo pedido desde el menú.</p>
                            <button
                                onclick="window.location.href = '/'"
                                style="padding: 0.75rem 1.5rem; background: var(--primary); color: white; border: none; border-radius: 8px; font-size: 1rem; cursor: pointer;">
                                Volver al Menú
                            </button>
                        </div>
                    `;
        }
      } else {
        hideViewTabs();
      }
      return;
    }

    const data = (await response.json()) as ActiveOrdersResponse;
    const normalized = normalizeOrders(data.orders || []);
    const visibleOrders = normalized.filter((order) => !isCancelledOrder(order));
    activeOrdersData = { ...data, orders: visibleOrders };

    console.debug('[ActiveOrders] response', {
      status: response.status,
      orders_count: visibleOrders.length,
      session: data.session,
    });

    const orders = visibleOrders;
    const session = data.session || {};
    const sessionStatus = session.status || 'open';
    const finishedStatuses = ['closed', 'paid', 'billed', 'cancelled'];
    const isSessionFinished = finishedStatuses.includes(sessionStatus);

    if (visibleOrders.length > 0 && !isSessionFinished) {
      showViewTabs(visibleOrders.length);
      displayActiveOrders(visibleOrders, session);
    } else if (visibleOrders.length === 0 && !isSessionFinished) {
      // No orders yet
      showViewTabs(0);
      displayActiveOrders([], session);
    } else if (isSessionFinished) {
      // Session is finished (closed/paid/cancelled)
      console.warn('[ActiveOrders] Session is finished:', sessionStatus);
      localStorage.removeItem('pronto-session-id');
      // Show message to user
      if (ordersSection && singleTracker) {
        singleTracker.style.display = 'block';
        if (multipleView) multipleView.style.display = 'none';
        const statusMessages: Record<string, string> = {
          closed: 'cerrada',
          paid: 'pagada',
          billed: 'facturada',
          cancelled: 'cancelada',
        };
        const statusText = statusMessages[sessionStatus] || 'cerrada';
        singleTracker.innerHTML = `
                    <div style="text-align: center; padding: 3rem 1rem;">
                        <p style="font-size: 3rem; margin-bottom: 1rem;">✅</p>
                        <h3 style="color: var(--text); margin-bottom: 0.5rem;">Sesión ${escape(statusText)}</h3>
                        <p style="color: var(--muted); margin-bottom: 1.5rem;">Tu sesión ha sido ${escape(statusText)}. Puedes hacer un nuevo pedido desde el menú.</p>
                        <button
                            onclick="window.location.href = '/'"
                            style="padding: 0.75rem 1.5rem; background: var(--primary); color: white; border: none; border-radius: 8px; font-size: 1rem; cursor: pointer;">
                            Volver al Menú
                        </button>
                    </div>
                `;
      }
      // Auto redirect after 3 seconds
      setTimeout(() => {
        window.location.href = '/';
      }, 3000);
    }
  } catch (error) {
    console.error('[ActiveOrders] Error loading active orders:', error);
    if (ordersSection && singleTracker) {
      singleTracker.style.display = 'block';
      if (multipleView) multipleView.style.display = 'none';
      singleTracker.innerHTML = `
                <div style="text-align: center; padding: 3rem 1rem;">
                    <p style="font-size: 3rem; margin-bottom: 1rem;">⚠️</p>
                    <h3 style="color: var(--text); margin-bottom: 0.5rem;">Error al cargar</h3>
                    <p style="color: var(--muted);">No se pudieron cargar las órdenes. Intenta recargar la página.</p>
                </div>
            `;
    }
  }
}

function resolveSessionId(): Promise<number | null> {
  return Promise.resolve(getSessionId());
}

function showViewTabs(ordersCount: number): void {
  const ordersBadge = document.getElementById('orders-badge');
  const requestCheckTab = document.getElementById('tab-request-check') as HTMLButtonElement | null;

  if (ordersBadge) {
    ordersBadge.textContent = String(ordersCount);
    ordersBadge.style.display = ordersCount > 0 ? 'flex' : 'none';
  }

  updateRequestCheckButton();
  if (requestCheckTab && requestCheckTab.disabled) {
    requestCheckTab.classList.remove('active');
  }
}

// --- Checkout Accordion Helpers ---

function updateCustomerAccordionState(): void {
  const customerAccordion = document.getElementById('accordion-customer');
  const nameInput = document.getElementById('customer-name') as HTMLInputElement;
  const badge = document.getElementById('customer-status-badge');

  if (customerAccordion && nameInput) {
    // Check if fields have value
    const hasData = nameInput.value.trim().length > 0;

    if (hasData) {
      customerAccordion.classList.add('collapsed');
      if (badge) {
        badge.textContent = 'Completado';
        badge.classList.add('confirmed');
        badge.style.background = '#dcfce7';
        badge.style.color = '#166534';
      }
    } else {
      customerAccordion.classList.remove('collapsed');
      if (badge) {
        badge.textContent = 'Requerido';
        badge.classList.remove('confirmed');
        badge.style.background = '#f3f4f6';
        badge.style.color = '#4b5563';
      }
    }
  }
}

function renderCheckoutHistory(): void {
  const container = document.getElementById('checkout-history-container');
  if (!container) return;

  // Clear current history
  container.innerHTML = '';

  if (!activeOrdersData || !activeOrdersData.orders || activeOrdersData.orders.length === 0) {
    return;
  }

  // Iterate orders and create accordions
  activeOrdersData.orders.forEach((order: any) => {
    const el = document.createElement('div');

    // "Nuevas ordenes no confirmadas aun estan desplegadas"
    // "Orden que ya este realizada... comprimida"
    // Status 'requested' = Unconfirmed? 'pending'?
    // Assumption: 'requested' or 'pending' are unconfirmed. 'confirmed', 'preparing', 'ready', 'delivered' are confirmed.
    const isUnconfirmed = ['requested', 'pending', 'payment_pending'].includes(
      order.status || 'requested'
    );
    const collapsedClass = isUnconfirmed ? '' : 'collapsed';

    el.className = `checkout-accordion ${collapsedClass}`;

    const statusLabel = translateStatus(order.status || 'pending');
    const itemsHtml = (order.items || [])
      .map(
        (item: any) => `
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem; font-size: 0.95rem;">
           <span><b style="margin-right:0.5rem;">${escape(item.quantity)}x</b> ${escape(item.name)}</span>
           <span>$${escape((item.total_price || 0).toFixed(2))}</span>
        </div>
      `
      )
      .join('');

    const totalAmount = order.total || order.total_amount || 0;

    // Check if order can be marked as received (delivered status)
    const canMarkReceived = getWorkflowStatus(order) === 'ready' || order.status === 'ready';
    const sessionId = order.session_id || activeOrdersData?.session?.id;

    el.innerHTML = `
        <div class="checkout-accordion-header" onclick="this.parentElement.classList.toggle('collapsed')">
           <div class="accordion-title">
              <span class="accordion-icon">🧾</span>
              <span>Orden #${escape(order.order_id)}</span>
           </div>
           <div style="display: flex; align-items: center; gap: 0.5rem;">
              <span class="header-status ${isUnconfirmed ? 'new' : 'confirmed'}">${escape(statusLabel)}</span>
              <span class="accordion-chevron">▼</span>
           </div>
        </div>
        <div class="accordion-content">
           <div class="checkout-summary__items">
              ${itemsHtml}
           </div>
           <div class="checkout-summary__divider" style="height: 1px; background: #eee; margin: 0.5rem 0;"></div>
           <div class="checkout-summary__total" style="display: flex; justify-content: space-between; font-weight: bold;">
               <span>Total Orden</span>
               <span>$${escape(Number(totalAmount).toFixed(2))}</span>
           </div>
           <div class="order-actions" style="display: flex; gap: 0.5rem; margin-top: 1rem; justify-content: flex-end;">
              ${
                sessionId
                  ? `<button class="btn btn--secondary btn--small" onclick="downloadOrderPDF(${escape(sessionId)})" title="Descargar PDF">
                  📄 PDF
               </button>`
                  : ''
              }
              ${
                canMarkReceived
                  ? `<button class="btn btn--primary btn--small" onclick="markOrderReceived(${escape(order.order_id)})" title="Marcar como recibida">
                  ✅ Recibida
               </button>`
                  : ''
              }
           </div>
        </div>
      `;
    container.appendChild(el);
  });
}

function translateStatus(status: string): string {
  const map: Record<string, string> = {
    requested: 'Solicitado',
    pending: 'Pendiente',
    payment_pending: 'Confirma Pago',
    confirmed: 'Confirmado',
    preparing: 'Preparando',
    ready: 'Listo',
    delivered: 'Entregado',
    paid: 'Pagado',
    completed: 'Completado',
    cancelled: 'Cancelado',
  };
  return map[status] || status;
}

function hideViewTabs(): void {
  const ordersBadge = document.getElementById('orders-badge');
  const mainContent = document.querySelector('main') as HTMLElement | null;
  const ordersSection = document.getElementById('active-orders-section') as HTMLElement | null;
  const detailsSection = document.getElementById('account-details-section') as HTMLElement | null;
  const trackerTab = document.getElementById('tab-tracker') as HTMLButtonElement | null;
  const requestCheckTab = document.getElementById('tab-request-check') as HTMLButtonElement | null;

  if (ordersBadge) {
    ordersBadge.textContent = '0';
    ordersBadge.style.display = 'none';
  }
  if (trackerTab) {
    trackerTab.disabled = true;
    trackerTab.classList.remove('active');
  }
  if (requestCheckTab) {
    requestCheckTab.disabled = true;
    requestCheckTab.classList.remove('active');
  }

  if (mainContent) mainContent.style.display = 'block';
  if (ordersSection) ordersSection.style.display = 'none';
  if (detailsSection) detailsSection.style.display = 'none';
  currentView = 'menu';

  document.getElementById('tab-menu')?.classList.add('active');
  document.getElementById('tab-orders')?.classList.remove('active');
}

function normalizeOrders(rawOrders: any[]): NormalizedOrder[] {
  return (rawOrders || []).map((order: any) => {
    const workflow = getWorkflowStatus(order);
    const createdAt = order.created_at || order.createdAt || new Date().toISOString();
    const totalAmountRaw =
      order.total_amount ??
      order.total ??
      order.session?.total_amount ??
      order.session?.totals?.total_amount ??
      0;
    const totalAmountNum = Number(totalAmountRaw);
    const totalAmount = Number.isFinite(totalAmountNum) ? totalAmountNum : 0;
    const items: NormalizedOrderItem[] = (order.items || []).map((item: any) => {
      const unitPriceNum = Number(item.unit_price ?? item.price ?? 0);
      const unitPrice = Number.isFinite(unitPriceNum) ? unitPriceNum : 0;
      const qtyNum = Number(item.quantity ?? 1);
      const qty = Number.isFinite(qtyNum) && qtyNum > 0 ? qtyNum : 1;
      return {
        quantity: qty,
        name: item.name || 'Producto',
        total_price: Number.isFinite(unitPrice * qty) ? unitPrice * qty : 0,
        modifiers: item.modifiers || [],
      };
    });

    return {
      order_id: order.id || order.order_id || order.orderId || 0,
      created_at: createdAt,
      total: totalAmount,
      total_amount: totalAmount,
      workflow_status: workflow,
      status: workflow,
      table_number:
        order.table_number ||
        order.session?.table_number ||
        order.session?.table?.table_number ||
        null,
      customer_notes: order.customer_notes || order.notes || order.session?.notes,
      items,
    };
  });
}

function isCancelledOrder(order: NormalizedOrder): boolean {
  const status = getWorkflowStatus(order).toLowerCase();
  return status === 'cancelled' || status === 'canceled';
}

function updateRequestCheckButton(): void {
  if (!activeOrdersData || !activeOrdersData.orders) return;

  // Enable "Pedir cuenta" when order is ready_for_delivery (70% progress) or delivered
  const hasReadyOrDeliveredOrder = activeOrdersData.orders.some((order: any) => {
    const status = getWorkflowStatus(order);
    return status === 'ready_for_delivery' || status === 'delivered';
  });
  const tabButton = document.getElementById('tab-request-check') as HTMLButtonElement | null;
  const detailsButton = document.getElementById('request-check-btn') as HTMLButtonElement | null;

  if (tabButton) {
    tabButton.disabled = !hasReadyOrDeliveredOrder;
    tabButton.style.opacity = hasReadyOrDeliveredOrder ? '1' : '0.5';
    tabButton.style.cursor = hasReadyOrDeliveredOrder ? 'pointer' : 'not-allowed';
  }
  if (detailsButton) {
    detailsButton.disabled = !hasReadyOrDeliveredOrder;
    detailsButton.style.opacity = hasReadyOrDeliveredOrder ? '1' : '0.5';
    detailsButton.style.cursor = hasReadyOrDeliveredOrder ? 'pointer' : 'not-allowed';
  }
}

async function requestOrderCheck(orderId: number): Promise<void> {
  const notify = (window as any).showNotification as
    | ((message: string, type?: 'success' | 'warning' | 'error' | 'info') => void)
    | undefined;

  try {
    const response = await fetch(`/api/orders/${orderId}/request-check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'No se pudo solicitar la cuenta para esta orden');
    }

    notify?.(
      `✅ Cuenta solicitada para orden #${orderId}. El mesero te atenderá pronto`,
      'success'
    );

    // Refresh active orders to show updated status
    await refreshActiveOrders();
  } catch (error: any) {
    notify?.(`Error: ${error.message}`, 'error');
  }
}

async function requestCheck(): Promise<void> {
  const sessionId = localStorage.getItem('pronto-session-id');
  const notify = (window as any).showNotification as
    | ((message: string, type?: 'success' | 'warning' | 'error' | 'info') => void)
    | undefined;

  if (!sessionId) {
    notify?.('No hay una sesión activa', 'warning');
    return;
  }
  if (!activeOrdersData || !activeOrdersData.orders) {
    notify?.('Espera a que se entregue tu pedido', 'warning');
    return;
  }

  // Allow requesting check when order is ready_for_delivery or delivered
  const hasReadyOrDeliveredOrder = activeOrdersData.orders.some((order: any) => {
    const status = getWorkflowStatus(order);
    return status === 'ready_for_delivery' || status === 'delivered';
  });
  if (!hasReadyOrDeliveredOrder) {
    notify?.('Espera a que tu pedido esté listo para pedir la cuenta', 'warning');
    return;
  }

  const tabButton = document.getElementById('tab-request-check') as HTMLButtonElement | null;
  const detailsButton = document.getElementById('request-check-btn') as HTMLButtonElement | null;

  if (tabButton) {
    tabButton.focus();
    tabButton.classList.add('active');
    tabButton.disabled = true;
  }
  if (detailsButton) detailsButton.disabled = true;

  try {
    // Usar el endpoint checkout que cambia el estado de la sesión a awaiting_tip
    const response = await fetch(`/api/sessions/${sessionId}/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'No se pudo solicitar la cuenta');
    }

    notify?.('✅ Cuenta solicitada. El mesero te atenderá pronto', 'success');

    // Redirect to summary/thank you page instead of staying on order view
    openAccountSummary();

    if (tabButton) {
      tabButton.classList.add('active');
    }
    const trackerTab = document.getElementById('tab-tracker');
    trackerTab?.classList.remove('active');
  } catch (error: any) {
    notify?.(`Error: ${error.message}`, 'error');
    if (tabButton) {
      tabButton.classList.remove('active');
    }
    updateRequestCheckButton();
  }
}

function openAccountSummary(): void {
  const sessionId = localStorage.getItem('pronto-session-id');
  const notify = (window as any).showNotification as
    | ((message: string, type?: 'success' | 'warning' | 'error' | 'info') => void)
    | undefined;

  if (!sessionId) {
    notify?.('Primero realiza un pedido para ver tu cuenta.', 'warning');
    return;
  }
  window.location.href = `/gracias?session_id=${sessionId}`;
}

async function loadAccountDetails(): Promise<void> {
  const sessionId = localStorage.getItem('pronto-session-id');
  const container = document.getElementById('account-details-content');
  if (!container) return;

  if (!sessionId) {
    container.innerHTML =
      '<p style="text-align: center; color: var(--muted); padding: 2rem;">Primero realiza un pedido para ver tu cuenta.</p>';
    return;
  }

  container.innerHTML =
    '<p style="text-align: center; color: var(--muted); padding: 2rem;">Cargando...</p>';

  try {
    const response = await fetch(`/api/session/${sessionId}/orders`);
    if (!response.ok) {
      // If session not found (404), clear the stale session ID
      if (response.status === 404) {
        console.warn('[ActiveOrders] Session not found, clearing stale session ID');
        localStorage.removeItem('pronto-session-id');
        container.innerHTML =
          '<p style="text-align: center; color: var(--muted); padding: 2rem;">No hay sesión activa. Realiza un pedido para comenzar.</p>';
        hideViewTabs();
      } else {
        console.error('[ActiveOrders] Error response:', response.status, response.statusText);
        // Try to get error details
        try {
          const errorData = await response.json();
          console.error('[ActiveOrders] Error details:', errorData);
        } catch (e) {
          // Ignore JSON parse errors
        }
        container.innerHTML =
          '<p style="text-align: center; color: var(--error); padding: 2rem;">Error al cargar los detalles de la cuenta. Intenta recargar la página.</p>';
      }
      return;
    }
    const data = await response.json();
    const orders = normalizeOrders(data.orders || []);
    const session = data.session || {};
    const sessionStatus = session.status || 'open';
    const finishedStatuses = ['closed', 'paid', 'billed', 'cancelled'];
    const isSessionFinished = finishedStatuses.includes(sessionStatus);

    console.debug('[ActiveOrders] account details response', {
      status: response.status,
      orders_count: orders.length,
      session,
    });

    if (orders.length === 0) {
      container.innerHTML =
        '<p style="text-align: center; color: var(--muted); padding: 2rem;">No hay órdenes en esta sesión.</p>';
      return;
    }

    if (isSessionFinished) {
      // Session is finished, clear sessionId and show message
      localStorage.removeItem('pronto-session-id');
      container.innerHTML = `
                <div style="text-align: center; padding: 2rem;">
                    <p style="font-size: 2rem; margin-bottom: 1rem;">✅</p>
                    <h3 style="color: var(--text); margin-bottom: 0.5rem;">Sesión completada</h3>
                    <p style="color: var(--muted);">Tu sesión ha sido cerrada. ¡Gracias por tu visita!</p>
                </div>
            `;
      return;
    }

    displayAccountDetails({ ...data, orders });
  } catch (error) {
    console.error('[ActiveOrders] Error loading account details:', error);
    container.innerHTML =
      '<p style="text-align: center; color: var(--error); padding: 2rem;">Error al cargar los detalles de la cuenta.</p>';
  }
}

function displayAccountDetails(data: any): void {
  const container = document.getElementById('account-details-content');
  if (!container) return;

  const orders = data.orders || [];
  const session = data.session || {};

  const formatCurrency = (amount: number): string =>
    new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(amount);

  const html = `
        <div style="background: #f8fafc; border-radius: 12px; padding: 1.5rem; margin-bottom: 2rem;">
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
                <div>
                    <p style="margin: 0; font-size: 0.875rem; color: var(--muted);">Mesa</p>
                    <p style="margin: 0.25rem 0 0 0; font-size: 1.25rem; font-weight: 600; color: var(--text);">${
                      session.table_number || 'N/A'
                    }</p>
                </div>
                <div>
                    <p style="margin: 0; font-size: 0.875rem; color: var(--muted);">Total de órdenes</p>
                    <p style="margin: 0.25rem 0 0 0; font-size: 1.25rem; font-weight: 600; color: var(--text);">${
                      orders.length
                    }</p>
                </div>
                <div>
                    <p style="margin: 0; font-size: 0.875rem; color: var(--muted);">Total a pagar</p>
                    <p style="margin: 0.25rem 0 0 0; font-size: 1.25rem; font-weight: 600; color: var(--primary);">${formatCurrency(
                      session.total_amount || 0
                    )}</p>
                </div>
            </div>
        </div>

        <h3 style="margin: 0 0 1rem 0; color: var(--text);">Historial de Pedidos</h3>
        <div style="display: grid; gap: 1rem;">
            ${orders
              .map(
                (order: any) => `
                <div style="background: white; border: 2px solid var(--border); border-radius: 12px; padding: 1.5rem;">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 1rem;">
                        <div>
                            <h4 style="margin: 0; font-size: 1.125rem; color: var(--text);">Pedido #${order.order_id}</h4>
                            <p style="margin: 0.25rem 0 0 0; font-size: 0.875rem; color: var(--muted);">Cliente</p>
                        </div>
                        <span style="padding: 0.5rem 1rem; background: var(--primary); color: white; border-radius: 20px; font-size: 0.875rem; font-weight: 600;">
        ${formatWorkflowStatus(getWorkflowStatus(order))}
                        </span>
                    </div>
                    <div style="margin: 1rem 0;">
                        ${(order.items || [])
                          .map(
                            (item: any) => `
                            <div style="padding: 0.5rem 0; border-bottom: 1px solid var(--border);">
                                <div style="display: flex; justify-content: space-between;">
                                    <span>${item.quantity}x ${item.name}</span>
                                    <span style="font-weight: 600;">${formatCurrency(item.total_price)}</span>
                                </div>
                                ${
                                  item.modifiers && item.modifiers.length > 0
                                    ? item.modifiers
                                        .map(
                                          (m: any) => `
                                <div style="display: flex; justify-content: space-between; font-size: 0.875rem; color: var(--muted); padding-left: 1.5rem; margin-top: 0.25rem;">
                                    <span>+ ${m.name}</span>
                                    <span>${m.price ? formatCurrency(m.price) : formatCurrency(0)}</span>
                                </div>`
                                        )
                                        .join('')
                                    : ''
                                }
                            </div>`
                          )
                          .join('')}
                    </div>
                    <div style="display: flex; justify-content: space-between; padding-top: 1rem; border-top: 2px solid var(--border); font-size: 1.125rem; font-weight: 700;">
                        <span>Total:</span>
                        <span style="color: var(--primary);">${formatCurrency(order.total)}</span>
                    </div>
                </div>`
              )
              .join('')}
        </div>
    `;

  container.innerHTML = html;
}

function displayActiveOrders(orders: any[], session: any): void {
  const singleTracker = document.getElementById('single-order-tracker') as HTMLElement | null;
  const multipleView = document.getElementById('multiple-orders-view') as HTMLElement | null;
  const list = document.getElementById('active-orders-list') as HTMLElement | null;

  console.debug('[ActiveOrders] displayActiveOrders called', {
    orders_count: orders.length,
    singleTracker_exists: !!singleTracker,
    multipleView_exists: !!multipleView,
    list_exists: !!list,
  });

  if (!singleTracker || !multipleView || !list) {
    console.error('[ActiveOrders] Missing containers!', {
      singleTracker: !!singleTracker,
      multipleView: !!multipleView,
      list: !!list,
    });
    return;
  }

  const formattedOrders = orders.map((o) => ({
    ...o,
    status_label: formatWorkflowStatus(getWorkflowStatus(o)),
  }));

  console.debug('[ActiveOrders] Formatted orders:', formattedOrders);

  multipleView.style.display = 'block';
  singleTracker.style.display = 'none';

  if (formattedOrders.length === 0) {
    list.innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 3rem 1rem;">
                <p style="font-size: 3rem; margin-bottom: 1rem;">🍽️</p>
                <h3 style="color: var(--text); margin-bottom: 0.5rem;">No hay pedidos activos</h3>
                <p style="color: var(--muted);">Realiza un pedido desde el menú para ver su estado aquí.</p>
            </div>
        `;
    return;
  }

  console.debug(
    '[ActiveOrders] Showing cards view (multi-order layout), count:',
    formattedOrders.length
  );
  displayMultipleOrders(formattedOrders);
}

function formatWorkflowStatus(status: string | undefined): string {
  const map: Record<string, string> = {
    requested: 'Orden abierta sin asignar a mesero',
    open_order: 'Orden abierta sin asignar a mesero',
    waiter_accepted: 'Mesero asignado',
    kitchen_in_progress: 'Cocinando',
    ready_for_delivery: 'Listo para entregar',
    delivered: 'Entregado',
    billed: 'Pagado',
    paid: 'Pagado',
  };
  return map[status || ''] || status || 'En progreso';
}

function displaySingleOrderTracker(order: any, targetContainer?: HTMLElement | null): void {
  const container = targetContainer || document.getElementById('single-order-tracker');
  if (!container) return;

  const statusMessages: Record<string, { icon: string; title: string; description: string }> = {
    requested: {
      icon: '✓',
      title: 'Orden recibida',
      description: 'Recibimos tu orden, la estamos preparando 🍳',
    },
    waiter_accepted: {
      icon: '👨‍🍳',
      title: 'En preparación',
      description: 'Nuestro chef está cocinando tu pedido',
    },
    kitchen_in_progress: {
      icon: '🔥',
      title: 'Cocinando',
      description: 'Tu comida está en el fuego',
    },
    ready_for_delivery: {
      icon: '🔔',
      title: 'Lista para servir',
      description: 'Tu orden está lista, el mesero la llevará pronto',
    },
    delivered: {
      icon: '✨',
      title: 'Entregada',
      description: '¡Que la disfrutes!',
    },
  };

  const statusSteps = [
    { key: 'requested', ...statusMessages['requested'] },
    { key: 'waiter_accepted', ...statusMessages['waiter_accepted'] },
    { key: 'kitchen_in_progress', ...statusMessages['kitchen_in_progress'] },
    { key: 'ready_for_delivery', ...statusMessages['ready_for_delivery'] },
    { key: 'delivered', ...statusMessages['delivered'] },
  ];

  const currentIndex = statusSteps.findIndex((s) => s.key === getWorkflowStatus(order));

  container.innerHTML = `
        <div class="tracking-page">
            <!-- Order Number (Gigante) -->
            <div class="tracking-header">
                <h1 class="tracking-header__number">#${order.order_id}</h1>
                <p class="tracking-header__label">Estado de tu orden <span style="font-size: 0.8em; opacity: 0.8">(Cuenta #${localStorage.getItem('pronto-session-id') || '?'})</span></p>
            </div>

            <!-- Timeline -->
            <div class="tracking-timeline">
                ${statusSteps
                  .map(
                    (step, index) => `
                    <div class="timeline-step ${index < currentIndex ? 'completed' : ''} ${index === currentIndex ? 'active' : ''}">
                        <div class="timeline-step__icon">${step.icon}</div>
                        <div class="timeline-step__content">
                            <h3 class="timeline-step__title">${step.title}</h3>
                            <p class="timeline-step__description">${step.description}</p>
                        </div>
                    </div>`
                  )
                  .join('')}
            </div>

            <div style="background: var(--background); padding: 1.5rem; border-radius: 12px; margin-top: 2rem;">
                <h3 style="margin: 0 0 1rem 0;">Productos</h3>
                ${order.items
                  .map(
                    (item: any) => `
                    <div style="padding: 0.5rem 0; border-bottom: 1px solid var(--border);">
                        <div style="display: flex; justify-content: space-between;">
                            <span>${item.quantity}x ${item.name}</span>
                            <strong>$${item.total_price.toFixed(2)}</strong>
                        </div>
                        ${
                          item.modifiers && item.modifiers.length > 0
                            ? item.modifiers
                                .map(
                                  (m: any) => `
                        <div style="display: flex; justify-content: space-between; font-size: 0.875rem; color: var(--muted); padding-left: 1.5rem; margin-top: 0.25rem;">
                            <span>+ ${m.name}</span>
                            <span>$${m.price ? m.price.toFixed(2) : '0.00'}</span>
                        </div>`
                                )
                                .join('')
                            : ''
                        }
                    </div>`
                  )
                  .join('')}
                <div style="display: flex; justify-content: space-between; margin-top: 1rem; padding-top: 1rem; border-top: 2px solid var(--border); font-size: 1.2rem; font-weight: 700; color: var(--primary);">
                    <span>Total</span>
                    <span>$${order.total.toFixed(2)}</span>
                </div>
            </div>

            <div style="margin-top: 1.5rem; padding: 1rem; background: var(--background); border-radius: 8px; text-align: center; color: var(--muted); font-size: 0.9rem;">
                <span>⏱️ Se actualiza automáticamente cada 10 segundos</span>
            </div>
        </div>
    `;
}

function displayMultipleOrders(orders: any[]): void {
  const container = document.getElementById('active-orders-list');
  const highlightIdRaw = sessionStorage.getItem('pronto-highlight-order');
  const highlightOrderId = highlightIdRaw ? Number(highlightIdRaw) : null;
  const hiddenCancelled = getHiddenCancelledOrders();

  console.debug('[ActiveOrders] displayMultipleOrders called', {
    orders_count: orders.length,
    container_exists: !!container,
    orders,
  });

  if (!container) {
    console.error('[ActiveOrders] active-orders-list container not found!');
    return;
  }

  const timeline = (status: string) => renderStatusTimeline(status);
  const statusEmojis: Record<string, string> = {
    requested: '🆕',
    open_order: '🆕',
    waiter_accepted: '🍽️',
    kitchen_in_progress: '🔥',
    ready_for_delivery: '✅',
    delivered: '🎉',
    paid: '🧾',
    billed: '🧾',
    cancelled: '❌',
  };

  const statusTexts: Record<string, string> = {
    requested: 'Solicitada',
    open_order: 'Solicitada',
    waiter_accepted: 'Aceptada por mesero',
    kitchen_in_progress: 'En preparación',
    ready_for_delivery: 'Lista para entrega',
    delivered: 'Entregada',
    paid: 'Pagada',
    billed: 'Pagada',
    cancelled: 'Cancelada',
  };

  const normalizeStatus = (s: string) => {
    if (s === 'billed') return 'paid';
    if (s === 'open_order') return 'requested';
    return s;
  };
  const isCancellable = (status: string) => {
    const normalized = normalizeStatus(status);
    return normalized === 'requested' || normalized === 'waiter_accepted';
  };

  const filteredOrders = orders.filter((order: any) => {
    const oid = Number(order.order_id || order.id || order.orderId);
    const status = getWorkflowStatus(order);
    const isCancelled = status === 'cancelled';
    if (!isCancelled && hiddenCancelled.has(oid)) {
      hiddenCancelled.delete(oid);
      saveHiddenCancelledOrders(hiddenCancelled);
    }
    if (isCancelled && hiddenCancelled.has(oid)) {
      return false;
    }
    return true;
  });

  const cardsHtml = filteredOrders
    .map((order: any) => {
      const orderId = Number(order.order_id || order.id || order.orderId);
      const createdAt = order.created_at
        ? new Date(order.created_at).toLocaleTimeString('es-ES', {
            hour: '2-digit',
            minute: '2-digit',
          })
        : '';
      const normalizedStatus = getWorkflowStatus(order);
      const statusEmoji = statusEmojis[normalizedStatus] || '📦';
      const statusText = statusTexts[normalizedStatus] || 'En progreso';
      const itemCount = (order.items || []).reduce(
        (sum: number, item: any) => sum + (item.quantity || 1),
        0
      );
      const tableLabel =
        order.table_number ||
        order.session?.table_number ||
        order.session?.table?.table_number ||
        'N/A';
      const isCancelled = normalizedStatus === 'cancelled';
      const paymentStatus = order.payment_status || 'unpaid';
      const isAwaitingPayment = paymentStatus === 'awaiting_payment';
      const isPaid = paymentStatus === 'paid';

      // Determine status badge color and text
      const workflowStatus = normalizedStatus;
      const statusBadgeConfig: Record<string, { bg: string; color: string; text: string }> = {
        requested: { bg: '#dbeafe', color: '#1e40af', text: 'Recibida' },
        open_order: { bg: '#dbeafe', color: '#1e40af', text: 'Recibida' },
        waiter_accepted: { bg: '#fef3c7', color: '#92400e', text: 'En proceso' },
        kitchen_in_progress: { bg: '#fed7aa', color: '#9a3412', text: 'Preparando' },
        ready_for_delivery: { bg: '#d1fae5', color: '#065f46', text: 'Listo' },
        delivered: { bg: '#bfdbfe', color: '#1e3a8a', text: 'Entregado' },
        paid: { bg: '#e5e7eb', color: '#374151', text: 'Pagado' },
        billed: { bg: '#e5e7eb', color: '#374151', text: 'Pagado' },
        cancelled: { bg: '#fee2e2', color: '#991b1b', text: 'Cancelada' },
      };
      const statusBadge = statusBadgeConfig[workflowStatus] || {
        bg: '#f3f4f6',
        color: '#6b7280',
        text: 'En progreso',
      };

      return `
            <div class="kanban-card ${highlightOrderId === orderId ? 'active-order-card--highlight' : ''}" data-order-id="${orderId}">
                <div class="kanban-card__header">
                    <div>
                            <p class="kanban-card__label">Orden #${orderId}</p>
                            <p class="kanban-card__number">
                                <span>${statusEmoji}</span>
                                <span>${statusText}</span>
                            </p>
                            <p style="margin: 4px 0 0; padding: 4px 10px; background: ${statusBadge.bg}; color: ${statusBadge.color}; font-size: 0.8rem; font-weight: 600; border-radius: 6px; display: inline-block;">
                                ${statusBadge.text}
                            </p>
                            ${
                              isAwaitingPayment
                                ? `
                                <p style="margin: 4px 0 0; padding: 2px 8px; background: #fef3c7; color: #92400e; font-size: 0.75rem; font-weight: 600; border-radius: 4px; display: inline-block;">
                                    💳 Cuenta solicitada
                                </p>
                            `
                                : ''
                            }
                            ${
                              isPaid
                                ? `
                                <p style="margin: 4px 0 0; padding: 2px 8px; background: #d1fae5; color: #065f46; font-size: 0.75rem; font-weight: 600; border-radius: 4px; display: inline-block;">
                                    ✅ Pagada
                                </p>
                            `
                                : ''
                            }
                            <p style="margin: 2px 0 0; color: #64748b; font-size: 0.85rem;">Mesa ${tableLabel}</p>
                            <p class="kanban-card__time">${createdAt} · ${itemCount} ${itemCount === 1 ? 'item' : 'items'}</p>
                        </div>
                        <div class="active-order-total">
                            <span>Total</span>
                            <span>$${order.total?.toFixed(2) ?? '0.00'}</span>
                        </div>
                    </div>

                    <div class="active-order-items">
                        ${(order.items || [])
                          .map(
                            (item: any) => `
                            <div class="active-order-item">
                                <span>${item.quantity}x ${item.name}</span>
                                <span>$${item.total_price?.toFixed(2) ?? '0.00'}</span>
                            </div>
                            ${
                              item.modifiers && item.modifiers.length > 0
                                ? item.modifiers
                                    .map(
                                      (m: any) => `
                                <div style="display: flex; justify-content: space-between; font-size: 0.6875rem; color: #94a3b8; padding-left: 0.875rem; margin-top: 0.2rem;">
                                    <span>+ ${m.name}</span>
                                    <span>$${m.price ? m.price.toFixed(2) : '0.00'}</span>
                                </div>`
                                    )
                                    .join('')
                                : ''
                            }
                        `
                          )
                          .join('')}
                    </div>

                    <div class="active-order-actions">
                        ${
                          isCancelled
                            ? `
                            <button class="btn-cancel-order" data-clear-cancelled="${orderId}" title="Quitar de la vista">
                                <span>🧹</span>
                                <span>Quitar</span>
                            </button>
                        `
                            : `
                            <button class="btn-request-check-order" data-order-id="${orderId}"
                                ${(workflowStatus === 'ready_for_delivery' || workflowStatus === 'delivered') && !isAwaitingPayment && !isPaid ? '' : 'disabled'}
                                style="${(workflowStatus === 'ready_for_delivery' || workflowStatus === 'delivered') && !isAwaitingPayment && !isPaid ? '' : 'opacity: 0.5; cursor: not-allowed;'}"
                                title="${isAwaitingPayment ? 'Cuenta ya solicitada' : isPaid ? 'Orden ya pagada' : workflowStatus === 'requested' || workflowStatus === 'waiter_accepted' || workflowStatus === 'kitchen_in_progress' ? 'Disponible cuando tu orden esté lista' : 'Disponible cuando la orden esté lista'}">
                                <span>💳</span>
                                <span>${isAwaitingPayment ? 'Cuenta solicitada' : 'Pedir cuenta'}</span>
                            </button>
                            <button class="btn-cancel-order" data-cancel-order="${orderId}" ${isCancellable(workflowStatus) ? '' : 'disabled'}>
                                <span>✕</span>
                                <span>Cancelar</span>
                            </button>
                        `
                        }
                    </div>
                </div>
            `;
    })
    .join('');

  container.innerHTML = cardsHtml;

  // Request check handlers (per order)
  container.querySelectorAll<HTMLButtonElement>('.btn-request-check-order').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const orderId = Number(btn.dataset.orderId);
      if (!orderId) return;

      const order = filteredOrders.find((o) => o.order_id === orderId);
      if (!order) return;

      // Request check for this specific order
      await requestOrderCheck(orderId);
    });
  });

  // Cancel handlers
  container.querySelectorAll<HTMLButtonElement>('[data-cancel-order]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const orderId = Number(btn.dataset.cancelOrder);
      if (!orderId) return;

      const reason = await openCancelReasonModal(orderId);
      if (!reason) return;

      const shouldStoreReason = await shouldStoreCancelReason();
      const sessionId = localStorage.getItem('pronto-session-id');

      btn.disabled = true;
      btn.textContent = 'Cancelando...';

      try {
        const body: Record<string, any> = {};
        if (sessionId) body.session_id = sessionId;
        if (shouldStoreReason) body.reason = reason;

        const res = await fetch(`/api/orders/${orderId}/cancel`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          window.showNotification?.(err.error || 'No se pudo cancelar la orden', 'error');
          btn.disabled = false;
          btn.textContent = '✕ Cancelar';
          return;
        }
        window.showNotification?.('Orden cancelada', 'success');
        void refreshActiveOrders();
      } catch (error) {
        console.error('[ActiveOrders] cancel error', error);
        window.showNotification?.('No se pudo cancelar la orden', 'error');
        btn.disabled = false;
        btn.textContent = '✕ Cancelar';
      }
    });
  });

  // Clear cancelled handlers
  container.querySelectorAll<HTMLButtonElement>('[data-clear-cancelled]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const orderId = Number(btn.dataset.clearCancelled);
      if (!orderId) return;
      const hidden = getHiddenCancelledOrders();
      hidden.add(orderId);
      saveHiddenCancelledOrders(hidden);
      const card = container.querySelector<HTMLElement>(`.kanban-card[data-order-id="${orderId}"]`);
      card?.remove();
    });
  });

  if (highlightOrderId) {
    const targetCard = container.querySelector<HTMLElement>(
      `[data-order-id="${highlightOrderId}"]`
    );
    if (targetCard) {
      targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
      targetCard.classList.add('active-order-card--highlight');
      window.setTimeout(() => targetCard.classList.remove('active-order-card--highlight'), 1500);
    }
    sessionStorage.removeItem('pronto-highlight-order');
  }
}

function renderStatusTimeline(current: string): string {
  const steps = [
    { key: 'requested', label: 'Recibida', icon: '🆕' },
    { key: 'waiter_accepted', label: 'Asignada', icon: '🍽️' },
    { key: 'kitchen_in_progress', label: 'Cocinando', icon: '🔥' },
    { key: 'ready_for_delivery', label: 'Lista', icon: '🔔' },
    { key: 'delivered', label: 'Entregada', icon: '✅' },
    { key: 'paid', label: 'Pagada', icon: '🧾' },
  ];
  const normalized = current === 'billed' ? 'paid' : current;
  const currentIndex = steps.findIndex((s) => s.key === normalized);
  return `
        <div class="timeline timeline--compact">
            ${steps
              .map((step, index) => {
                const state = (() => {
                  if (currentIndex === -1) return 'upcoming';
                  if (index === currentIndex) return 'current';
                  if (index < currentIndex) return 'previous';
                  return 'upcoming';
                })();
                return `
                        <div class="timeline__step ${state}">
                            <div class="timeline__icon">${step.icon}</div>
                            <div class="timeline__label">${step.label}</div>
                        </div>
                    `;
              })
              .join('')}
        </div>
    `;
}

let storeCancelReasonCache: boolean | null = null;

async function shouldStoreCancelReason(): Promise<boolean> {
  if (storeCancelReasonCache !== null) return storeCancelReasonCache;
  try {
    const res = await fetch('/api/config/store_cancel_reason');
    if (!res.ok) throw new Error('config missing');
    const data = await res.json().catch(() => ({}));
    const raw = data?.value ?? data?.config_value ?? data?.configValue;
    storeCancelReasonCache = String(raw ?? 'true').toLowerCase() !== 'false';
  } catch (_error) {
    storeCancelReasonCache = true;
  }
  return storeCancelReasonCache;
}

function getHiddenCancelledOrders(): Set<number> {
  const raw = localStorage.getItem('pronto-hidden-cancelled-orders');
  if (!raw) return new Set();
  try {
    const arr = JSON.parse(raw);
    if (Array.isArray(arr)) {
      return new Set(arr.map((n) => Number(n)).filter((n) => Number.isFinite(n)));
    }
  } catch (_e) {
    /* ignore */
  }
  return new Set();
}

function saveHiddenCancelledOrders(set: Set<number>): void {
  localStorage.setItem('pronto-hidden-cancelled-orders', JSON.stringify([...set]));
}

function openOrderDetail(order: any): void {
  const modal = document.getElementById('order-detail-modal') as HTMLElement | null;
  const body = document.getElementById('order-detail-body') as HTMLElement | null;
  const tracker = document.getElementById('single-order-tracker') as HTMLElement | null;
  if (!modal || !body || !tracker) return;

  displaySingleOrderTracker(order, tracker);
  body.innerHTML = tracker.innerHTML;
  modal.style.display = 'flex';
}

function openCancelReasonModal(orderId: number): Promise<string | null> {
  return new Promise((resolve) => {
    const existing = document.getElementById('cancel-reason-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'cancel-reason-overlay';
    Object.assign(overlay.style, {
      position: 'fixed',
      inset: '0',
      background: 'rgba(0,0,0,0.45)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: '20000',
      padding: '1rem',
    });

    const modal = document.createElement('div');
    Object.assign(modal.style, {
      background: 'white',
      borderRadius: '14px',
      maxWidth: '420px',
      width: '100%',
      boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
      padding: '1.25rem',
      display: 'flex',
      flexDirection: 'column',
      gap: '0.75rem',
    });

    safeSetHTML(
      modal,
      `
            <div style="display:flex; justify-content: space-between; align-items: center; gap: 0.75rem;">
                <h3 style="margin:0; font-size:1.15rem; color:#0f172a;">Cancelar orden #${escape(orderId)}</h3>
                <button type="button" id="cancel-reason-close" style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:999px; width:34px; height:34px; display:flex; align-items:center; justify-content:center; cursor:pointer;">✕</button>
            </div>
            <p style="margin:0; color:#475569; font-size:0.95rem;">Indica el motivo de cancelación (obligatorio).</p>
            <textarea id="cancel-reason-input" rows="3" placeholder="Ej. Cliente se equivocó, duplicado, etc."
                style="width:100%; padding:0.75rem; border:1px solid #e2e8f0; border-radius:10px; font-size:0.95rem; resize: vertical;"></textarea>
            <div id="cancel-reason-error" style="color:#dc2626; font-size:0.9rem; display:none;">Debes indicar un motivo</div>
            <div style="display:flex; justify-content:flex-end; gap:0.5rem; margin-top:0.25rem;">
                <button type="button" id="cancel-reason-cancel" style="padding:0.65rem 1rem; border:1px solid #e2e8f0; border-radius:10px; background:#f8fafc; cursor:pointer;">Cerrar</button>
                <button type="button" id="cancel-reason-submit" style="padding:0.65rem 1rem; border:none; border-radius:10px; background:#ef4444; color:white; cursor:pointer;">Cancelar orden</button>
            </div>
        `
    );

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    const textarea = modal.querySelector<HTMLTextAreaElement>('#cancel-reason-input');
    const errorEl = modal.querySelector<HTMLElement>('#cancel-reason-error');
    const closeModal = (result: string | null) => {
      overlay.remove();
      document.removeEventListener('keydown', onKey);
      resolve(result);
    };

    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') {
        ev.preventDefault();
        closeModal(null);
      }
    };

    modal.querySelector('#cancel-reason-close')?.addEventListener('click', () => closeModal(null));
    modal.querySelector('#cancel-reason-cancel')?.addEventListener('click', () => closeModal(null));
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeModal(null);
    });
    modal.querySelector('#cancel-reason-submit')?.addEventListener('click', () => {
      const val = textarea?.value.trim() || '';
      if (!val) {
        if (errorEl) errorEl.style.display = 'block';
        textarea?.focus();
        return;
      }
      closeModal(val);
    });
    textarea?.focus();
    document.addEventListener('keydown', onKey);
  });
}

function attachDetailModalHandlers(): void {
  const modal = document.getElementById('order-detail-modal') as HTMLElement | null;
  const closeBtn = document.getElementById('close-order-detail') as HTMLElement | null;
  if (!modal || !closeBtn) return;

  const closeModal = () => {
    modal.style.display = 'none';
  };
  closeBtn.addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.style.display === 'flex') {
      closeModal();
    }
  });
}

function startOrdersAutoRefresh(): void {
  if (ordersRefreshInterval) {
    clearInterval(ordersRefreshInterval);
  }

  void refreshActiveOrders();

  ordersRefreshInterval = window.setInterval(() => {
    if (currentView === 'orders') {
      void refreshActiveOrders(false);
    } else if (currentView === 'details') {
      // Refresh account details view to update order statuses
      void loadAccountDetails();
      // Also update tabs badge
      void resolveSessionId().then((sessionId) => {
        if (!sessionId) return;
        fetch(`/api/session/${sessionId}/orders`)
          .then((res) => res.json())
          .then((data: ActiveOrdersResponse) => {
            if (
              data.orders &&
              data.orders.length > 0 &&
              data.session &&
              data.session.status !== 'closed'
            ) {
              showViewTabs(data.orders.length);
            } else {
              hideViewTabs();
            }
          })
          .catch(() => {
            /* ignore */
          });
      });
    } else {
      void resolveSessionId().then((sessionId) => {
        if (!sessionId) return;
        fetch(`/api/session/${sessionId}/orders`)
          .then((res) => res.json())
          .then((data: ActiveOrdersResponse) => {
            if (
              data.orders &&
              data.orders.length > 0 &&
              data.session &&
              data.session.status !== 'closed'
            ) {
              showViewTabs(data.orders.length);
            } else {
              hideViewTabs();
            }
          })
          .catch(() => {
            /* ignore */
          });
      });
    }
  }, 10000);
}

function stopOrdersAutoRefresh(): void {
  if (ordersRefreshInterval) {
    clearInterval(ordersRefreshInterval);
    ordersRefreshInterval = null;
  }
}

/**
 * Load session validation interval from backend config
 */
async function loadSessionValidationConfig(): Promise<void> {
  try {
    const response = await fetch('/api/config/client_session_validation_interval_minutes');
    if (response.ok) {
      const data = await response.json();
      const value = parseInt(data?.value ?? data?.config_value ?? '15', 10);
      if (value > 0) {
        sessionValidationIntervalMinutes = value;
        console.log(
          `[SessionValidation] Loaded interval: ${sessionValidationIntervalMinutes} minutes`
        );
      }
    }
  } catch (error) {
    console.warn('[SessionValidation] Could not load config, using default 15 minutes:', error);
  }
}

/**
 * Validate that the current session still exists in the backend
 */
async function validateSession(): Promise<void> {
  const sessionId = localStorage.getItem('pronto-session-id');

  if (!sessionId) {
    // No session to validate
    return;
  }

  try {
    const response = await fetch(`/api/session/${sessionId}/orders`);

    if (response.status === 404) {
      // Session no longer exists in backend
      console.warn('[SessionValidation] Session not found in backend, cleaning up localStorage');
      localStorage.removeItem('pronto-session-id');

      // Show notification to user
      const notify = (window as any).showNotification as
        | ((message: string, type?: 'success' | 'warning' | 'error' | 'info') => void)
        | undefined;
      notify?.('Tu sesión expiró. Por favor realiza un nuevo pedido.', 'warning');

      // Refresh the view to show "no orders" state
      if (currentView === 'orders') {
        void refreshActiveOrders();
      }
    } else if (response.ok) {
      const data = await response.json();
      const sessionStatus = data.session?.status;
      const finishedStatuses = ['closed', 'paid', 'billed', 'cancelled'];

      if (finishedStatuses.includes(sessionStatus)) {
        // Session is finished, clean up
        console.warn('[SessionValidation] Session is finished:', sessionStatus);
        localStorage.removeItem('pronto-session-id');

        // Refresh the view to show "no orders" state
        if (currentView === 'orders') {
          void refreshActiveOrders();
        }
      }
    }
  } catch (error) {
    console.error('[SessionValidation] Error validating session:', error);
    // Don't clean up on network errors - keep session for retry
  }
}

/**
 * Start periodic session validation
 */
function startSessionValidation(): void {
  // Load config first
  void loadSessionValidationConfig().then(() => {
    // Stop any existing interval
    if (sessionValidationInterval) {
      clearInterval(sessionValidationInterval);
    }

    // Start validation interval (convert minutes to milliseconds)
    const intervalMs = sessionValidationIntervalMinutes * 60 * 1000;
    sessionValidationInterval = window.setInterval(() => {
      void validateSession();
    }, intervalMs);

    console.log(
      `[SessionValidation] Started validation every ${sessionValidationIntervalMinutes} minutes`
    );

    // Run initial validation after 30 seconds
    window.setTimeout(() => {
      void validateSession();
    }, 30000);
  });
}

/**
 * Stop periodic session validation
 */
function stopSessionValidation(): void {
  if (sessionValidationInterval) {
    clearInterval(sessionValidationInterval);
    sessionValidationInterval = null;
  }
}

// Business hours helpers (header footer + outside-hours modal)
async function loadBusinessHours(): Promise<void> {
  try {
    const response = await fetch('/api/business-info');
    const data = await response.json();
    if (response.ok && data.schedule) {
      displayBusinessHours(data.schedule, data.current_day_schedule);
      if (!data.is_currently_open) {
        showOutsideHoursModal(data.schedule, data.current_day_schedule);
      }
    }
  } catch (error) {
    console.error('[ActiveOrders] Error loading business hours:', error);
  }
}

function displayBusinessHours(schedule: any[], currentDaySchedule: any): void {
  const displayContainer = document.getElementById('business-hours-display');
  const scheduleContainer = document.getElementById('business-hours-schedule');
  const statusContainer = document.getElementById('current-status');

  if (
    !displayContainer ||
    !scheduleContainer ||
    !statusContainer ||
    !schedule ||
    schedule.length === 0
  )
    return;

  // Don't auto-expand - let toggle control visibility

  scheduleContainer.innerHTML = schedule
    .map((day: any) => {
      const isCurrent = currentDaySchedule && day.day_of_week === currentDaySchedule.day_of_week;
      return `
                <div style="padding: 0.5rem; border-radius: 6px; ${
                  isCurrent ? 'background: #dbeafe; font-weight: 600;' : ''
                }">
                    <div style="font-size: 0.9rem; color: var(--text);">${day.day_name}</div>
                    <div style="font-size: 0.85rem; color: ${
                      day.is_open ? 'var(--primary)' : '#94a3b8'
                    }; margin-top: 0.25rem;">
                        ${day.is_open ? `${day.open_time} - ${day.close_time}` : 'Cerrado'}
                    </div>
                </div>`;
    })
    .join('');

  if (currentDaySchedule) {
    if (currentDaySchedule.is_open) {
      statusContainer.style.background = '#d1fae5';
      statusContainer.style.color = '#065f46';
      statusContainer.innerHTML = `✅ Abierto ahora · Cierra a las ${currentDaySchedule.close_time}`;
    } else {
      statusContainer.style.background = '#fee2e2';
      statusContainer.style.color = '#991b1b';
      statusContainer.innerHTML = '🔒 Cerrado hoy';
    }
  }
}

function showOutsideHoursModal(schedule: any[], currentDaySchedule: any): void {
  const dismissed = sessionStorage.getItem('outside-hours-dismissed');
  if (dismissed) return;

  const modal = document.getElementById('outside-hours-modal');
  const scheduleContainer = document.getElementById('outside-hours-schedule');
  if (!modal || !scheduleContainer) return;

  if (schedule) {
    scheduleContainer.innerHTML = `
            <h4 style="margin: 0 0 0.75rem 0; font-size: 1rem; color: var(--text);">Nuestros Horarios:</h4>
            ${schedule
              .map(
                (day: any) => `
                <div style="display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid var(--border);">
                    <span style="font-weight: 600; color: var(--text);">${day.day_name}</span>
                    <span style="color: ${day.is_open ? 'var(--primary)' : '#94a3b8'};">
                        ${day.is_open ? `${day.open_time} - ${day.close_time}` : 'Cerrado'}
                    </span>
                </div>`
              )
              .join('')}
        `;
  }

  modal.classList.add('active');
}

function closeOutsideHoursModal(): void {
  const modal = document.getElementById('outside-hours-modal');
  if (modal) {
    modal.classList.remove('active');
    sessionStorage.setItem('outside-hours-dismissed', 'true');
  }
}

function toggleBusinessHoursDisplay(): void {
  const displayContainer = document.getElementById('business-hours-display');
  const footerHoursBtn = document.getElementById('footer-hours-btn');
  if (!displayContainer || !footerHoursBtn) return;

  const isVisible = displayContainer.style.display !== 'none';
  if (isVisible) {
    displayContainer.style.display = 'none';
    footerHoursBtn.textContent = '🕒 Ver horarios de atención';
  } else {
    displayContainer.style.display = 'block';
    footerHoursBtn.textContent = '🕒 Ocultar horarios';
    // Ensure business hours are loaded
    void loadBusinessHours();
  }
}

// PDF Download functionality
async function downloadOrderPDF(sessionId: number): Promise<void> {
  const notify = (window as any).showNotification as
    | ((message: string, type?: 'success' | 'warning' | 'error' | 'info') => void)
    | undefined;

  try {
    notify?.('Descargando PDF...', 'info');

    const response = await fetch(`/api/sessions/${sessionId}/ticket.pdf`);
    if (!response.ok) {
      throw new Error('No se pudo descargar el PDF');
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = `ticket_sesion_${sessionId}.pdf`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);

    notify?.('PDF descargado exitosamente', 'success');
  } catch (error: any) {
    console.error('Error downloading PDF:', error);
    notify?.(`Error al descargar PDF: ${error.message}`, 'error');
  }
}

// Mark order as received functionality
async function markOrderReceived(orderId: number): Promise<void> {
  const notify = (window as any).showNotification as
    | ((message: string, type?: 'success' | 'warning' | 'error' | 'info') => void)
    | undefined;

  try {
    const response = await fetch(`/api/orders/${orderId}/received`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || 'No se pudo marcar como recibida');
    }

    notify?.(`✅ Orden #${orderId} marcada como recibida`, 'success');

    // Refresh orders to show updated status
    await refreshActiveOrders();
  } catch (error: any) {
    console.error('Error marking order as received:', error);
    notify?.(`Error: ${error.message}`, 'error');
  }
}

// Expose functions globally for onclick handlers
(window as any).downloadOrderPDF = downloadOrderPDF;
(window as any).markOrderReceived = markOrderReceived;
