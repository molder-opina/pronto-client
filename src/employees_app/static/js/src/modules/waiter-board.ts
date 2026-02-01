import { requestJSON } from '../core/http';
import { isValidEmailFormat, normalizeCustomerEmail } from './email-utils';
import {
  getCapabilitiesForRole,
  normalizeBackendCapabilities,
  type RoleCapabilities,
} from './role-context';
import type {
  OrderItem,
  WorkflowStatus,
  SessionData,
  CustomerData,
  WaiterOrder,
  WaiterCall,
  ActionDescriptor,
  StatusInfo,
} from './waiter/types';
import {
  STATUS_INFO,
  CHECKOUT_SESSION_STATES,
  CHECKOUT_CALL_NOTE,
  WAITERS_ROOM,
  EMPLOYEES_ROOM,
  POLL_INTERVAL_MS,
  formatStatus,
} from './waiter/constants';
import { WaiterSoundManager } from './waiter/sounds';
import {
  showFeedback,
  showNewOrderNotification,
  notifyAction,
  getTimeAgo,
  showModal,
  showOrderSelectionModal,
} from './waiter/ui-utils';

interface Window {
  APP_DATA: any;
  EmployeePayments: any;
  SESSIONS_STATE: any;
  EmployeeBell: any;
  io: any;
  webkitAudioContext: any;
  WaiterPanel: any;
  WAITER_ORDERS_DATA: any;
  ProntoRealtime: any;
  GlobalLoading?: { start: () => void; stop: () => void };
  EmployeeLoading?: { start: () => void; stop: () => void };
  showToast?: (message: string, type?: 'success' | 'error' | 'warning' | 'info') => void;
}

declare var window: Window & typeof globalThis;

export function initWaiterBoard(root: HTMLElement): void {
  const board = new WaiterBoard(root);
  board.initialize();

  // Expose refreshOrders globally for HTML button
  (window as any).refreshWaiterOrders = () => board.refreshOrders();
}

class WaiterBoard {
  private static readonly ICON_EYE = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"></path>
            <circle cx="12" cy="12" r="3"></circle>
        </svg>
    `;

  private static readonly ICON_CHECK = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M20 6 9 17l-5-5"></path>
        </svg>
    `;

  private static readonly ICON_TICKET = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 9V7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4Z"></path>
            <path d="M13 5v14"></path>
            <path d="M17 9h.01"></path>
            <path d="M17 15h.01"></path>
        </svg>
    `;

  private static readonly ICON_CLOCK = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9"></circle>
            <path d="M12 7v6l3 2"></path>
        </svg>
    `;

  private getDisplayStatus(order: WaiterOrder, sessionStatus?: string): string {
    if (sessionStatus === 'paid') return 'Pagada';
    const status = order.workflow_status;
    const map = {
      new: 'Esperando mesero',
      queued: 'Enviando a cocina',
      preparing: 'En cocina',
      ready: 'Listo entrega',
      delivered: 'Entregado',
      awaiting_payment: 'Esperando pago',
      paid: 'Pagada',
      cancelled: 'Cancelada',
    };
    return map[status as keyof typeof map] || formatStatus(status);
  }

  private root: HTMLElement;
  private ordersTable: HTMLTableElement | null = null;
  private feedbackEl: HTMLElement | null = null;
  private notificationsPanel: HTMLElement | null = null;
  private notificationsContent: HTMLElement | null = null;
  private capabilities: RoleCapabilities;
  private noteSaveTimers: Map<number, number> = new Map();
  private ordersData: WaiterOrder[] = [];
  private pendingCalls: WaiterCall[] = [];
  private currentEmployeeId: number | null = null;
  private socket: any = null;
  private orders: Map<number, WaiterOrder> = new Map();
  private pendingCallsInterval?: number;
  private ordersPollingInterval?: number;
  private realtimeUnsubscribe?: () => void;
  private realtimeRefreshTimer?: number;
  private soundManager: WaiterSoundManager = new WaiterSoundManager();

  // New properties for tabs and tracking (starred orders)
  private activeTab: 'active' | 'tracking' | 'paid' | 'cancelled' = 'active';
  private starredOrders: Set<number> = new Set();
  private isCompactView: boolean = false;
  private showMyOrders: boolean = true; // Filter to show my orders
  private showUnassignedOrders: boolean = true; // Filter to show unassigned orders
  private dateFilter: 'today' | 'last7' | 'custom' | 'all' = 'today';
  private customDateDays: number = 7;
  private sessionStatusFilters: Set<string> = new Set([
    'open',
    'awaiting_tip',
    'awaiting_payment',
    'awaiting_payment_confirmation',
  ]);
  private workflowStatusFilters: Set<string> = new Set([
    'new',
    'queued',
    'preparing',
    'ready',
    'delivered',
  ]);
  private paidSessionsInterval?: number;
  private paidSessionsTable: HTMLTableElement | null = null;
  private paidFeedbackEl: HTMLElement | null = null;
  private trackingOrdersTable: HTMLElement | null = null;
  private trackingFeedbackEl: HTMLElement | null = null;
  private cancelledOrdersTable: HTMLElement | null = null;
  private cancelledFeedbackEl: HTMLElement | null = null;
  private resendModal: HTMLElement | null = null;
  private resendForm: HTMLFormElement | null = null;
  private resendSessionLabel: HTMLElement | null = null;
  private resendEmailInput: HTMLInputElement | null = null;
  private closeResendBtn: HTMLElement | null = null;
  private cancelResendBtn: HTMLElement | null = null;
  private resendModalInitialized: boolean = false;

  // Partial delivery modal
  private partialDeliveryModal: HTMLElement | null = null;
  private partialDeliveryOrderId: number | null = null;
  private partialDeliverySelectedItems: Set<number> = new Set();

  // Search functionality
  private searchTerm: string = '';
  private searchInput: HTMLInputElement | null = null;
  private searchCountEl: HTMLElement | null = null;

  constructor(root: HTMLElement) {
    console.log('[WAITER] Constructor called');
    this.root = root;
    this.capabilities =
      normalizeBackendCapabilities(window.APP_DATA?.role_capabilities) ||
      window.APP_DATA?.role_capabilities ||
      getCapabilitiesForRole(window.APP_DATA?.employee_role);
    console.log('[WAITER] Employee role:', window.APP_DATA?.employee_role);
    console.log('[WAITER] Capabilities initialized:', this.capabilities);
    this.loadStarredOrders();
  }

  initialize(): void {
    console.log('[WAITER] Initialize called');
    this.ordersData = Array.isArray(window.WAITER_ORDERS_DATA)
      ? (window.WAITER_ORDERS_DATA as WaiterOrder[]).map((order) => {
          const normalized = normalizeWorkflowStatus(
            order.workflow_status,
            order.workflow_status_legacy
          );
          return {
            ...order,
            workflow_status: normalized,
            workflow_status_legacy: normalized,
          };
        })
      : [];
    this.ordersData.forEach((order) => this.orders.set(order.id, order)); // Populate the new Map

    console.log('[WAITER] window.APP_DATA:', window.APP_DATA);
    this.currentEmployeeId = window.APP_DATA?.employee_id ?? null;
    console.log('[WAITER] currentEmployeeId:', this.currentEmployeeId);

    this.ordersTable = this.root.querySelector<HTMLTableElement>('#waiter-orders');
    this.feedbackEl = this.root.querySelector<HTMLElement>('#waiter-feedback');
    this.paidSessionsTable = document.getElementById('paid-sessions') as HTMLTableElement | null;
    this.paidFeedbackEl = document.getElementById('paid-feedback');
    this.trackingOrdersTable = document.getElementById('tracking-orders');
    this.trackingFeedbackEl = document.getElementById('tracking-feedback');
    this.cancelledOrdersTable = document.getElementById('cancelled-orders');
    this.cancelledFeedbackEl = document.getElementById('cancelled-feedback');
    this.notificationsPanel = document.getElementById('notifications-panel');
    this.notificationsContent = document.getElementById('notifications-content');
    this.resendModal = document.getElementById('resend-ticket-modal');
    this.resendForm = document.getElementById('resend-ticket-form') as HTMLFormElement | null;
    this.resendSessionLabel = document.getElementById('resend-ticket-session-label');
    this.resendEmailInput = document.getElementById(
      'resend-ticket-email'
    ) as HTMLInputElement | null;
    this.closeResendBtn = document.getElementById('close-resend-ticket');
    this.cancelResendBtn = document.getElementById('cancel-resend-ticket');
    this.partialDeliveryModal = document.getElementById('partial-delivery-modal');
    this.searchInput = document.getElementById('order-search-input') as HTMLInputElement | null;
    this.searchCountEl = document.getElementById('order-search-count');

    // Este modal se usa en el tab "Pagadas", incluso si no hay órdenes activas renderizadas.
    this.initializeResendModal();

    if (!this.ordersTable) {
      console.warn('[WAITER] Tabla de órdenes no encontrada; se inicializan solo notificaciones');
    } else {
      console.log('[WAITER] Initializing with', this.orders.size, 'orders');

      try {
        this.renderExistingRows();
        this.attachEventHandlers();
        this.initializeTabs();
        this.initializeStarButtons();
        this.initializeFilters(); // Initialize filters
        this.setupSearch(); // Initialize search
        this.initializeHeaderTableChips();
        this.sortOrders();
        this.applyFilters(); // Apply filters after sorting
        this.renderExistingRows(); // Re-render after filters to ensure buttons show
        this.updateTrackingBadge(); // Update tracking count badge
        this.renderCancelledOrders();
        this.initializeViewToggle();
      } catch (error) {
        console.error('[WAITER] Error inicializando panel de órdenes', error);
      }
    }

    console.log('[WAITER] Initialization complete');
    void this.soundManager.loadSoundSettings();
    this.loadPendingCalls();
    // if (this.capabilities.canViewPaid) {
    void this.loadPaidSessions();
    // }
    this.pendingCallsInterval = window.setInterval(
      () => this.loadPendingCalls(),
      30000
    ) as unknown as number;
    this.initializeWebSocket();
    this.initializeRealtimeEvents();
    this.initializeOrdersPolling();
    this.initializePartialDeliveryModal();
    this.initializeCancelOrderModal();

    document.addEventListener('employee:session:closed', (event) => {
      const session = ((event as CustomEvent).detail?.session || null) as SessionData | null;
      if (session) {
        // Actualizar el status de las órdenes en memoria para que se oculten de la tabla
        this.orders.forEach((order) => {
          if (order.session_id === session.id) {
            order.session = { ...order.session, status: session.status } as SessionData;
          }
        });
        this.updateSharedSessionState(session);
        this.refreshRowsForSession(session.id);
        void this.loadPaidSessions();
      }
    });
    document.addEventListener('employee:session:updated', (event) => {
      const session = ((event as CustomEvent).detail?.session || null) as SessionData | null;
      if (session) {
        // Actualizar el status de las órdenes en memoria para reflejar el cambio
        this.orders.forEach((order) => {
          if (order.session_id === session.id) {
            order.session = { ...order.session, status: session.status } as SessionData;
          }
        });
        this.updateSharedSessionState(session);
        this.refreshRowsForSession(session.id);
        if (session.status === 'paid' || session.status === 'paid') {
          void this.loadPaidSessions();
        }
      }
    });

    document.addEventListener('employee:notifications:toggle', () =>
      this.toggleNotificationsPanel()
    );

    window.WaiterPanel = {
      confirmWaiterCall: (callId: number) => this.confirmWaiterCall(callId),
      toggleNotificationsPanel: () => this.toggleNotificationsPanel(),
      clearPendingCalls: () => this.clearPendingCalls(),
      getPendingCalls: () => [...this.pendingCalls],
      printPaidSession: (sessionId: number) => this.printPaidSession(sessionId),
    } as any;
  }

  private renderExistingRows(): void {
    const rows = this.ordersTable?.querySelectorAll<HTMLTableRowElement>('tr[data-order-id]');
    console.log('[WAITER] renderExistingRows called, found', rows?.length || 0, 'rows');

    rows?.forEach((row) => {
      // If the row is already marked as cancelled, remove from active table immediately
      if ((row.dataset.status || '').toLowerCase() === 'cancelled') {
        row.remove();
        return;
      }

      const id = Number(row.dataset.orderId);
      let order = this.orders.get(id);

      // If order not in Map, try to get it from ordersData array
      if (!order) {
        order = this.ordersData.find((o) => o.id === id);
      }

      // If still not found, create a minimal order object from HTML data attributes
      if (!order) {
        console.log('[WAITER] Order', id, 'not found in data, creating from HTML');
        const normalizedStatus = normalizeWorkflowStatus(
          (row.dataset.status as WorkflowStatus) || 'requested'
        );
        order = {
          id: id,
          workflow_status: normalizedStatus,
          workflow_status_legacy: normalizedStatus,
          session_id: Number(row.dataset.sessionId) || 0,
          session: {
            id: Number(row.dataset.sessionId) || 0,
            status: row.dataset.sessionStatus || 'open',
          },
        } as WaiterOrder;
        this.orders.set(id, order);
      }

      // Skip cancelled orders from active table; they live in their own tab
      if (order.workflow_status === 'cancelled') {
        row.remove();
        return;
      }

      console.log('[WAITER] Rendering row', id, 'status:', order.workflow_status);
      this.renderRow(row, order);
    });

    this.pruneCancelledActiveRows();
  }

  private pruneCancelledActiveRows(): void {
    if (!this.ordersTable) return;
    this.ordersTable.querySelectorAll<HTMLTableRowElement>('tr[data-order-id]').forEach((row) => {
      const status = row.dataset.status || '';
      if (status === 'cancelled') {
        row.remove();
      }
    });
  }

  private attachEventHandlers(): void {
    this.ordersTable?.addEventListener('click', (event) => this.handleTableClick(event));
    this.trackingOrdersTable?.addEventListener('click', (event) => this.handleTableClick(event));
    this.cancelledOrdersTable?.addEventListener('click', (event) => this.handleTableClick(event));
    this.initializeSupervisorCallButton();
    this.initializeNotificationsPanelEvents();

    // Add listener for kitchen actions (if rendered due to role capabilities)
    this.ordersTable?.addEventListener('click', (event) => {
      const target = (event.target as HTMLElement).closest<HTMLButtonElement>('.kitchen-action');
      if (target && !target.disabled) {
        void this.processKitchenAction(target);
      }
    });
  }

  private initializeNotificationsPanelEvents(): void {
    // Use event delegation for notifications panel to handle dynamic content
    this.notificationsContent?.addEventListener('click', (event) => {
      const target = event.target as HTMLElement;
      const btn = target.closest<HTMLButtonElement>('[data-call-action="confirm"]');
      if (btn) {
        const callId = Number(btn.dataset.callId);
        if (callId) {
          console.log('[WAITER] Confirming call via delegation:', callId);
          void this.confirmWaiterCall(callId);
        }
      }
    });
  }

  private async processKitchenAction(button: HTMLButtonElement): Promise<void> {
    const endpoint = button.dataset.endpoint;
    if (!endpoint) return;

    const row = button.closest('tr');
    if (!row) return;

    // Prevent double clicks
    button.disabled = true;
    const originalNodes = Array.from(button.childNodes).map((node) => node.cloneNode(true));
    button.replaceChildren(createFragment('<span class="spin">↻</span>'));

    try {
      await requestJSON(endpoint, { method: 'POST' });
      // The socket update will handle the UI refresh via order_status_changed event
      notifyAction(this.feedbackEl, 'Acción de cocina procesada');
    } catch (error) {
      console.error('[WAITER] Kitchen action error:', error);
      const msg = (error as Error).message || 'Error procesando acción';
      showFeedback(this.feedbackEl, msg, true);
      window.showToast?.(msg, 'error');

      // Restore button state on error (using DOM nodes instead of innerHTML)
      button.disabled = false;
      button.replaceChildren(...originalNodes);
    }
  }

  private initializeSupervisorCallButton(): void {
    const btn = document.getElementById('call-supervisor-btn');
    const statusEl = document.getElementById('supervisor-call-status');
    const statusDetails = document.getElementById('supervisor-call-status-details');

    if (!btn) return;

    btn.addEventListener('click', async () => {
      // Prevent double-click
      if (btn.classList.contains('loading')) return;

      btn.classList.add('loading');
      const originalNodes = Array.from(btn.childNodes).map((node) => node.cloneNode(true));
      btn.replaceChildren(
        createFragment(`
                <svg class="spin" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10" stroke-dasharray="31.4" stroke-dashoffset="10"></circle>
                </svg>
                Llamando...
            `)
      );

      try {
        const response = await fetch('/api/waiter-calls/supervisor/call', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            table_number: null, // Optional: could get from selected order
            order_id: null,
            reason: 'Asistencia requerida',
          }),
        });

        const result = await response.json().catch(() => ({}) as any);

        if (response.ok && (result.status === 'success' || !result.status)) {
          // Show success feedback
          btn.replaceChildren(
            createFragment(`
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M20 6L9 17l-5-5"></path>
                        </svg>
                        ¡Supervisor notificado!
                    `)
          );
          btn.classList.remove('btn--primary');
          btn.classList.add('btn--success');

          // Update status display
          if (statusEl && statusDetails) {
            statusEl.style.display = 'block';
            const now = new Date();
            statusDetails.textContent = `Solicitado a las ${now.toLocaleTimeString()}`;
          }

          // Reset button after 5 seconds
          setTimeout(() => {
            btn.replaceChildren(...originalNodes);
            btn.classList.remove('btn--success');
            btn.classList.add('btn--primary');
          }, 5000);
        } else {
          throw new Error(result.message || result.error || 'Error al llamar supervisor');
        }
      } catch (error) {
        console.error('[WAITER] Error calling supervisor:', error);
        // Fallback optimista: informamos al usuario y dejamos botón listo
        btn.replaceChildren(
          createFragment(`
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M20 6L9 17l-5-5"></path>
                    </svg>
                    Supervisor notificado (fallback)
                `)
        );
        btn.classList.remove('btn--primary', 'btn--danger');
        btn.classList.add('btn--success');
        setTimeout(() => {
          btn.replaceChildren(...originalNodes);
          btn.classList.remove('btn--success');
          btn.classList.add('btn--primary');
        }, 3000);
      } finally {
        btn.classList.remove('loading');
      }
    });
  }

  private handleTableClick(event: Event): void {
    const target = event.target as HTMLElement;
    if (!this.ordersTable) return;

    console.log(
      '[CLICK] Target:',
      target.tagName,
      target.className,
      target.textContent?.substring(0, 20)
    );

    const paymentButton = target.closest<HTMLElement>(
      '[data-session-action],[data-payment-method],[data-open-payment-modal]'
    );
    if (paymentButton) {
      console.log('[CLICK] Payment button detected');
      void this.handlePaymentButton(paymentButton);
      return;
    }

    const partialDeliveryButton = target.closest<HTMLButtonElement>('.partial-delivery-btn');
    if (partialDeliveryButton) {
      console.log('[CLICK] Partial delivery button detected');
      const orderId = Number(partialDeliveryButton.dataset.orderId);
      if (orderId) {
        void this.openPartialDeliveryModal(orderId);
      }
      return;
    }

    // Cancel button is now handled inside the order detail panel, not in the table
    // The cancel button click is handled by the confirmCancelOrder function in the HTML template

    const workflowButton = target.closest<HTMLButtonElement>('.waiter-action');
    if (workflowButton) {
      console.log('[CLICK] Workflow button detected:', workflowButton.dataset.endpoint);
      void this.processWorkflowAction(workflowButton);
    } else {
      console.log('[CLICK] No button detected');
    }
  }

  private async handlePaymentButton(button: HTMLElement): Promise<void> {
    console.log('[PAYMENT] handlePaymentButton called, button:', button);
    if (!this.ordersTable) return;
    const row = button.closest<HTMLTableRowElement>('tr[data-order-id]');
    const sessionId = Number(row?.dataset.sessionId ?? '');
    console.log('[PAYMENT] Session ID:', sessionId, 'Row:', row);
    if (!sessionId) {
      showFeedback(this.feedbackEl, 'Esta orden no tiene cuenta activa', true);
      return;
    }

    // Check if this is the new single "Cobrar" button
    if (button.dataset.openPaymentModal === 'true') {
      console.log('[PAYMENT] Opening payment modal for session:', sessionId);
      // Extract Order ID and Email from row for better UX
      const orderId = Number(row?.dataset.orderId ?? 0);
      const customerEmail = normalizeCustomerEmail(row?.dataset.customerEmail);

      const opened = this.openPaymentModule(sessionId, undefined, orderId, customerEmail);
      console.log('[PAYMENT] Payment module opened:', opened);
      if (!opened) {
        showFeedback(this.feedbackEl, 'No se pudo abrir el módulo de cobro', true);
      }
      return;
    }

    // Legacy support for old payment method buttons (if any remain)
    if (button.dataset.paymentMethod) {
      const opened = this.openPaymentModule(sessionId, button.dataset.paymentMethod);
      if (!opened) {
        showFeedback(this.feedbackEl, 'No se pudo abrir el módulo de cobro', true);
      }
      return;
    }

    if (button.dataset.sessionAction) {
      button.setAttribute('disabled', 'true');
      await this.handleSessionAction(sessionId, button.dataset.sessionAction);
      button.removeAttribute('disabled');
    }
  }

  private async handleSessionAction(sessionId: number, action: string): Promise<void> {
    try {
      showFeedback(this.feedbackEl, 'Procesando cuenta...');
      if (action === 'ticket') {
        await this.handleTicketPrint(sessionId);
        return;
      }
      if (action === 'checkout') {
        const data = await requestJSON<SessionData>(`/api/sessions/${sessionId}/checkout`, {
          method: 'POST',
        });
        this.updateSharedSessionState(data);
        showFeedback(this.feedbackEl, 'Propina solicitada');
        return;
      }
      if (action === 'tip') {
        const input = prompt('Propina (usa números)', '0');
        if (input === null) return;
        const parsed = parseFloat(input);
        if (Number.isNaN(parsed) || parsed < 0) {
          throw new Error('Ingresa un monto válido');
        }
        const data = await requestJSON<SessionData>(`/api/sessions/${sessionId}/tip`, {
          method: 'POST',
          body: { tip_amount: parsed },
        });
        this.updateSharedSessionState(data);
        showFeedback(this.feedbackEl, 'Cuenta actualizada');
        return;
      }
      if (action === 'print-ticket-and-confirm' || action === 'confirm-payment') {
        // Show payment type selection modal
        const paymentType = await showModal({
          title: '¿Cómo desea cobrar?',
          message:
            'Seleccione si desea cobrar esta orden individualmente o seleccionar múltiples órdenes de la mesa:',
          buttons: [
            { text: 'Cancelar', value: 'cancel' },
            { text: 'Solo esta orden', value: 'individual', primary: true },
            { text: 'Seleccionar órdenes', value: 'together' },
          ],
        });

        if (paymentType === 'cancel') {
          showFeedback(this.feedbackEl, 'Pago cancelado');
          return;
        }

        let orderIds: number[] | undefined;

        if (paymentType === 'individual') {
          // Get the current order ID from the row
          const row = this.ordersTable?.querySelector<HTMLTableRowElement>(
            `tr[data-session-id="${sessionId}"]`
          );
          const orderId = Number(row?.dataset.orderId ?? '');
          if (!orderId) {
            showFeedback(this.feedbackEl, 'No se pudo identificar la orden', true);
            return;
          }
          orderIds = [orderId];
        } else if (paymentType === 'together') {
          // Fetch all orders from the session
          showFeedback(this.feedbackEl, 'Cargando órdenes...');
          const sessionOrders = await requestJSON<{
            session_id: number;
            table_number: string;
            orders: Array<{
              id: number;
              customer_name: string;
              total_amount: number;
              items_count: number;
              payment_status: string;
            }>;
          }>(`/api/sessions/${sessionId}/orders`);

          if (!sessionOrders.orders || sessionOrders.orders.length === 0) {
            showFeedback(this.feedbackEl, 'No hay órdenes en esta sesión', true);
            return;
          }

          // Show order selection modal
          const selectedOrderIds = await showOrderSelectionModal(sessionOrders.orders);

          if (selectedOrderIds === null) {
            showFeedback(this.feedbackEl, 'Pago cancelado');
            return;
          }

          orderIds = selectedOrderIds;
        }

        // Process payment with selected order IDs
        showFeedback(this.feedbackEl, 'Confirmando pago...');
        const data = await requestJSON<SessionData>(`/api/sessions/${sessionId}/confirm-payment`, {
          method: 'POST',
          body: orderIds ? { order_ids: orderIds } : undefined,
        });

        this.updateSharedSessionState(data);

        // Update the row UI immediately without page reload
        this.updateRowAfterPayment(sessionId);

        // Sync local session status for any cached orders
        this.orders.forEach((order) => {
          if (order.session_id === sessionId) {
            if (orderIds && orderIds.includes(order.id)) {
              order.payment_status = 'paid';
            }
            // Only update session status to paid if all orders are paid
            if (data.status === 'paid') {
              order.session = {
                ...order.session,
                id: sessionId,
                status: 'paid',
              } as SessionData;
            }
          }
        });

        // Apply filters to hide paid orders from active tab
        this.applyFilters();
        // Refresh paid sessions table to show the newly paid order
        void this.loadPaidSessions();

        const isPrintTicketAction = action === 'print-ticket-and-confirm';
        const isFullPayment = data.status === 'paid';

        if (isFullPayment) {
          showFeedback(this.feedbackEl, 'Pago confirmado, cuenta cerrada');
        } else {
          showFeedback(
            this.feedbackEl,
            `Pago parcial confirmado (${orderIds?.length || 0} ${orderIds?.length === 1 ? 'orden' : 'órdenes'})`
          );
        }

        // Handle ticket printing if requested
        if (isPrintTicketAction) {
          if (window.EmployeePayments?.openTicketModal) {
            window.EmployeePayments.openTicketModal(sessionId);
          } else if (window.EmployeePayments?.printTicket) {
            window.EmployeePayments.printTicket(sessionId);
          } else {
            await this.handleTicketPrint(sessionId);
          }
        }

        return;
      }
      if (action === 'archive') {
        // Archive paid order (hide it from active panel)
        const rows = this.ordersTable?.querySelectorAll<HTMLTableRowElement>(
          `tr[data-session-id="${sessionId}"]`
        );
        rows?.forEach((row) => {
          row.style.display = 'none';
          row.dataset.archived = 'true';
        });
        showFeedback(this.feedbackEl, 'Orden archivada');
        return;
      }
    } catch (error) {
      showFeedback(this.feedbackEl, (error as Error).message, true);
    }
  }

  private async handleTicketPrint(sessionId: number): Promise<void> {
    // Try to use the ticket modal from payments-flow first
    if (window.EmployeePayments?.openTicketModal) {
      window.EmployeePayments.openTicketModal(sessionId);
      showFeedback(this.feedbackEl, 'Abriendo ticket...');
      return;
    }

    // Fallback to direct print if modal not available
    if (window.EmployeePayments?.printTicket) {
      window.EmployeePayments.printTicket(sessionId);
      showFeedback(this.feedbackEl, 'Imprimiendo ticket...');
      return;
    }

    // Final fallback: direct PDF download/view
    const pdfUrl = `/api/sessions/${sessionId}/ticket.pdf`;
    showFeedback(this.feedbackEl, 'Imprimiendo ticket PDF...');

    const ticketWindow = window.open(pdfUrl, '_blank');

    if (!ticketWindow) {
      showFeedback(
        this.feedbackEl,
        'Por favor permite ventanas emergentes para imprimir el ticket',
        true
      );
      return;
    }
  }

  private openPaymentModule(
    sessionId: number,
    method?: string,
    orderId?: number,
    customerEmail?: string
  ): boolean {
    console.log(
      '[PAYMENT] openPaymentModule called, sessionId:',
      sessionId,
      'method:',
      method,
      'orderId:',
      orderId
    );
    if (!sessionId) {
      console.warn('[PAYMENT] No session ID provided');
      return false;
    }
    console.log('[PAYMENT] window.EmployeePayments:', window.EmployeePayments);
    if (window.EmployeePayments?.openModal) {
      console.log('[PAYMENT] Calling EmployeePayments.openModal');
      // Pass orderId and email to the modal
      window.EmployeePayments.openModal(sessionId, method || 'cash', orderId, customerEmail);
      return true;
    }
    console.log('[PAYMENT] EmployeePayments not available, dispatching event');
    document.dispatchEvent(
      new CustomEvent('employee:payments:open', {
        detail: { sessionId, method, orderId, customerEmail },
      })
    );
    return true;
  }

  private scheduleNoteSave(noteField: HTMLTextAreaElement): void {
    const orderId = Number(noteField.dataset.orderNote);
    if (!orderId || noteField.disabled) return;
    if (this.noteSaveTimers.has(orderId)) {
      window.clearTimeout(this.noteSaveTimers.get(orderId));
    }
    const timer = window.setTimeout(() => {
      void this.saveOrderNoteField(noteField, orderId);
    }, 800) as unknown as number;
    this.noteSaveTimers.set(orderId, timer);
  }

  private async saveOrderNoteField(noteField: HTMLTextAreaElement, orderId: number): Promise<void> {
    this.noteSaveTimers.delete(orderId);
    const row = noteField.closest<HTMLTableRowElement>('tr[data-order-id]');
    const sessionStatus = row?.dataset.sessionStatus || 'open';
    const finishedStatuses = new Set(['paid', 'paid', 'closed', 'cancelled']);
    if (finishedStatuses.has(sessionStatus)) {
      showFeedback(this.feedbackEl, 'Solo puedes anotar órdenes activas', true);
      return;
    }
    noteField.dataset.saving = 'true';
    showFeedback(this.feedbackEl, 'Guardando nota...');
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(`/api/orders/${orderId}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ notes: noteField.value }),
        signal: controller.signal,
      });
      window.clearTimeout(timeout);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || 'No se pudo guardar la nota.');
      }
      const data = await response.json();
      noteField.value = data.waiter_notes || '';
      if (row) {
        row.dataset.waiterNotes = data.waiter_notes || '';
      }
      document.dispatchEvent(new CustomEvent('orders:changed'));
      showFeedback(this.feedbackEl, 'Nota actualizada');
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        showFeedback(this.feedbackEl, 'Tiempo de espera agotado. Intenta de nuevo.', true);
      } else {
        showFeedback(this.feedbackEl, (error as Error).message, true);
      }
    } finally {
      noteField.dataset.saving = '';
    }
  }

  private async processWorkflowAction(button: HTMLButtonElement): Promise<void> {
    if (!this.ordersTable) return;
    const row = button.closest<HTMLTableRowElement>('tr[data-order-id]');
    if (!row) return;
    const orderId = Number(row.dataset.orderId);
    const endpoint = button.dataset.endpoint;
    if (!endpoint) return;
    const employeeId = this.currentEmployeeId;

    console.log(
      '[WORKFLOW] Processing action:',
      endpoint,
      'for order:',
      orderId,
      'employee:',
      employeeId
    );

    if (!employeeId) {
      showFeedback(this.feedbackEl, 'Error: No hay empleado activo en esta sesión', true);
      return;
    }

    // Prevent double-clicks by checking if button is already disabled
    if (button.disabled) {
      console.log('[WORKFLOW] Button already disabled, ignoring click');
      return;
    }

    // Prevent double-clicks by checking if button is already disabled
    if (button.disabled) {
      console.log('[WORKFLOW] Button already disabled, ignoring click');
      return;
    }

    button.disabled = true;
    showFeedback(this.feedbackEl, 'Procesando...');
    try {
      console.log('[WORKFLOW] Calling API:', endpoint);
      const data = await requestJSON<WaiterOrder>(endpoint, {
        method: 'POST',
        body: { employee_id: employeeId },
      });
      console.log('[WORKFLOW] API response:', data);
      const normalizedStatus = normalizeWorkflowStatus(
        data.workflow_status,
        data.workflow_status_legacy
      );
      const normalizedOrder = {
        ...data,
        workflow_status: normalizedStatus,
        workflow_status_legacy: normalizedStatus,
      } as WaiterOrder;
      this.orders.set(orderId, normalizedOrder); // Update the order in the Map
      if (normalizedStatus === 'cancelled') {
        row.remove();
        this.orders.delete(orderId); // Remove from Map
      } else {
        row.dataset.status = normalizedStatus;
        const statusEl = row.querySelector<HTMLElement>('.status');
        if (statusEl) {
          const displayStatus = this.getDisplayStatus(
            normalizedOrder,
            normalizedOrder.session?.status || row.dataset.sessionStatus
          );
          statusEl.textContent = displayStatus;
          statusEl.className = `status status--${normalizedStatus}`;
        }
        row.dataset.waiterNotes = normalizedOrder.waiter_notes || '';
        row.dataset.waiterName = normalizedOrder.waiter_name || row.dataset.waiterName || '';
        row.dataset.sessionStatus = normalizedOrder.session?.status || '';
        row.dataset.tableNumber = normalizedOrder.session?.table_number || '';
        this.renderRow(row, normalizedOrder);

        // Visual feedback: highlight the updated row
        row.style.transition = 'background-color 0.3s ease';
        row.style.backgroundColor = '#d4edda'; // Light green
        setTimeout(() => {
          row.style.backgroundColor = '';
        }, 1500);
      }
      // Prepare custom notification message based on action
      let notificationMessage = `Orden #${orderId} → ${this.getDisplayStatus(
        normalizedOrder,
        normalizedOrder.session?.status || row.dataset.sessionStatus
      )}`;
      const tableNumber =
        normalizedOrder.session?.table_number || row.dataset.tableNumber || '#' + orderId;

      if (normalizedStatus === 'queued') {
        row.dataset.waiterId = String(employeeId);
        row.dataset.waiterName = window.APP_DATA?.employee_name ?? '';
        const waiterCell = row.querySelector<HTMLElement>('.waiter-badge');
        if (waiterCell) {
          waiterCell.textContent = `👤 ${window.APP_DATA?.employee_name ?? 'Asignado'}`;
          waiterCell.classList.remove('waiter-badge--unassigned');
        } else {
          console.warn('[WORKFLOW] Waiter cell not found for order', orderId);
        }
        // Custom message for accepted order
        notificationMessage = `✅ Mesa ${tableNumber} aceptada`;

        // Refresh assigned tables display in case auto-assignment occurred
        // Use setTimeout to ensure the backend has finished processing the assignment
        setTimeout(() => {
          const tableManager = (window as any).tableAssignmentManager;
          if (tableManager?.refreshAssignedTablesDisplay) {
            console.log('[WORKFLOW] Refreshing assigned tables after order acceptance');
            tableManager.refreshAssignedTablesDisplay();
          } else {
            console.warn('[WORKFLOW] Table assignment manager not available');
          }
        }, 500);
      } else if (normalizedStatus === 'ready') {
        // Check if this was just accepted (quick delivery items)
        const previousStatus = row.dataset.status;
        if (previousStatus === 'new') {
          // Quick delivery: orden accepted and ready immediately
          notificationMessage = `✅ Mesa ${tableNumber} aceptada - Lista para entregar`;
        } else {
          // Kitchen completed the order
          notificationMessage = `✓ Orden #${orderId} lista para servir`;
        }
      } else if (normalizedStatus === 'delivered') {
        // Custom message for delivered order
        notificationMessage = `✅ Orden #${orderId} entregada`;
      } else if (normalizedStatus === 'preparing') {
        notificationMessage = `🍳 Orden #${orderId} enviada a cocina`;
      }

      if (data.session) {
        this.updateSharedSessionState(data.session);
      }
      document.dispatchEvent(new CustomEvent('orders:changed'));
      notifyAction(this.feedbackEl, notificationMessage);
      this.sortOrders(); // Re-sort after status change
      this.applyFilters(); // Re-apply filters
    } catch (error) {
      console.error('[WORKFLOW] Error:', error);
      const errorMessage = (error as Error).message || String(error);

      // Si la orden ya fue tomada, recargar la orden desde el servidor para mostrar el estado actual
      if (
        errorMessage.includes('ya fue tomada') ||
        errorMessage.includes('already') ||
        errorMessage.includes('taken')
      ) {
        console.log('[WORKFLOW] Order already taken, refreshing order state from server');
        try {
          // Recargar la orden desde el servidor
          await this.refreshOrders();
          // Buscar la orden actualizada en la tabla
          const updatedRow = this.ordersTable?.querySelector<HTMLTableRowElement>(
            `tr[data-order-id="${orderId}"]`
          );
          if (updatedRow) {
            const updatedStatus = updatedRow.dataset.status;
            const updatedWaiterName = updatedRow.dataset.waiterName;
            if (updatedWaiterName) {
              showFeedback(
                this.feedbackEl,
                `La orden ya fue asignada a ${updatedWaiterName}`,
                false
              );
            } else {
              showFeedback(this.feedbackEl, 'La orden ya fue tomada. Estado actualizado.', false);
            }
          } else {
            showFeedback(this.feedbackEl, 'La orden ya fue tomada', true);
          }
        } catch (refreshError) {
          console.error('[WORKFLOW] Error refreshing order:', refreshError);
          showFeedback(this.feedbackEl, errorMessage, true);
        }
      } else {
        showFeedback(this.feedbackEl, errorMessage, true);
      }
    } finally {
      button.disabled = false;
    }
  }

  private async handleCancelOrder(orderId: number): Promise<void> {
    if (!this.ordersTable) return;

    const order = this.orders.get(orderId);
    if (!order) {
      showFeedback(this.feedbackEl, 'Orden no encontrada', true);
      return;
    }

    // Open cancel modal
    this.openCancelOrderModal(orderId);
  }

  private openCancelOrderModal(orderId: number): void {
    const modal = document.getElementById('cancel-order-modal');
    const orderNumberSpan = document.getElementById('cancel-order-number');
    const reasonTextarea = document.getElementById('cancel-order-reason') as HTMLTextAreaElement;

    if (!modal || !orderNumberSpan || !reasonTextarea) return;

    // Set order number
    orderNumberSpan.textContent = String(orderId);
    reasonTextarea.value = '';

    // Show modal
    modal.style.display = 'flex';

    // Store orderId for later use
    modal.dataset.orderId = String(orderId);
  }

  private closeCancelOrderModal(): void {
    const modal = document.getElementById('cancel-order-modal');
    const reasonTextarea = document.getElementById('cancel-order-reason') as HTMLTextAreaElement;

    if (modal) {
      modal.style.display = 'none';
      delete modal.dataset.orderId;
    }
    if (reasonTextarea) {
      reasonTextarea.value = '';
    }
  }

  private async confirmCancelOrder(): Promise<void> {
    const modal = document.getElementById('cancel-order-modal');
    const reasonTextarea = document.getElementById('cancel-order-reason') as HTMLTextAreaElement;
    const confirmBtn = document.getElementById('confirm-cancel-order') as HTMLButtonElement | null;

    if (!modal || !reasonTextarea) return;

    const orderId = Number(modal.dataset.orderId);
    const reason = reasonTextarea.value.trim();

    if (!reason) {
      showFeedback(this.feedbackEl, 'Por favor indica el motivo de la cancelación', true);
      return;
    }

    if (!Number.isFinite(orderId) || !orderId) {
      showFeedback(this.feedbackEl, 'Orden no válida para cancelar', true);
      return;
    }

    // UI feedback
    this.closeCancelOrderModal();
    if (confirmBtn) {
      confirmBtn.disabled = true;
      confirmBtn.textContent = 'Cancelando...';
    }
    showFeedback(this.feedbackEl, 'Cancelando orden...');

    try {
      const storeReason = await this.shouldStoreCancelReason();
      const data = await requestJSON<WaiterOrder>(`/api/orders/${orderId}/cancel`, {
        method: 'POST',
        body: {
          employee_id: this.currentEmployeeId,
          ...(storeReason ? { cancellation_reason: reason } : {}),
        },
      });

      console.log('[CANCEL] Order cancelled:', data);

      // Remove the order row from active table, keep it in Map for cancelled tab
      const row = this.ordersTable?.querySelector<HTMLTableRowElement>(
        `tr[data-order-id="${orderId}"]`
      );
      if (row) {
        row.remove();
      }
      this.orders.set(orderId, data);

      // Also remove from tracking if present
      const trackingRow = this.trackingOrdersTable?.querySelector<HTMLTableRowElement>(
        `tr[data-order-id="${orderId}"]`
      );
      if (trackingRow) {
        trackingRow.remove();
      }

      document.dispatchEvent(new CustomEvent('orders:changed'));
      notifyAction(this.feedbackEl, `Orden #${orderId} cancelada`);
      this.sortOrders();
      this.applyFilters();
      this.renderCancelledOrders();
    } catch (error) {
      console.error('[CANCEL] Error:', error);
      showFeedback(this.feedbackEl, (error as Error).message, true);
    } finally {
      if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = '❌ Confirmar Cancelación';
      }
    }
  }

  private renderRow(row: HTMLTableRowElement, order: WaiterOrder): void {
    const cell = row.querySelector<HTMLTableCellElement>('.actions');
    if (!cell) return;

    console.log(
      '[DEBUG renderRow] Order:',
      order.id,
      'Status:',
      order.workflow_status,
      'Session:',
      order.session?.status
    );

    row.dataset.sessionStatus = order.session?.status || '';
    row.classList.toggle(
      'waiter-row--checkout',
      Boolean(order.session && CHECKOUT_SESSION_STATES.has(order.session.status))
    );

    const sessionStatus = order.session?.status || row?.dataset.sessionStatus || 'open';
    const statusInfo = STATUS_INFO[order.workflow_status];
    // Create container structure similar to notes column
    let actionsContainer = cell.querySelector('.waiter-actions-container');
    if (!actionsContainer) {
      actionsContainer = document.createElement('div');
      actionsContainer.className = 'waiter-actions-container flex flex-col gap-2';
      cell.appendChild(actionsContainer);
    } else {
      // Clear existing content but keep the container
      actionsContainer.replaceChildren();
    }

    const actionLabelText =
      this.getDisplayStatus(order, sessionStatus) || statusInfo?.title || 'Acciones';

    const ensureActionLabel = (text?: string) => {
      const existingLabel = actionsContainer.querySelector('.waiter-action-label');
      if (existingLabel) return existingLabel;
      const label = document.createElement('p');
      label.className = 'waiter-action-label';
      label.textContent = text || actionLabelText;
      actionsContainer.insertBefore(label, actionsContainer.firstChild);
      return label;
    };

    if (
      (order.session?.status === 'paid' || order.session?.status === 'closed') &&
      !row.dataset.paidAt
    ) {
      const closedAt = (order.session as any).closed_at;
      row.dataset.paidAt = closedAt ? String(closedAt) : new Date().toISOString();
    }

    // Persist creation time for date filters
    const created = (order as any).created_at || (order as any).createdAt || row.dataset.createdAt;
    if (created) {
      row.dataset.createdAt = String(created);
    }

    let allowedActions =
      statusInfo?.actions.filter(
        (action) => !action.capability || this.capabilities[action.capability]
      ) || [];

    if (allowedActions.length === 0 && order.workflow_status === ('queued' as WorkflowStatus)) {
      allowedActions = [
        {
          label: 'En Cocina',
          icon: '🍳',
          endpoint: (_id: number) => '',
          variant: 'disabled',
          disabled: true,
        },
      ];
    }
    if (allowedActions.length === 0 && order.workflow_status === ('new' as WorkflowStatus)) {
      allowedActions = [
        {
          label: 'Aceptar',
          icon: '✅',
          endpoint: (id) => `/api/orders/${id}/accept`,
          variant: 'success',
        },
      ];
    }

    console.log(
      '[DEBUG renderRow] Order:',
      order.id,
      'Status:',
      order.workflow_status,
      'StatusInfo:',
      statusInfo,
      'AllowedActions:',
      allowedActions,
      'Capabilities:',
      this.capabilities
    );

    // Update status text with friendly label
    const statusEl = row.querySelector<HTMLElement>('.status');
    if (statusEl) {
      const friendlyStatus = this.getDisplayStatus(order, sessionStatus);

      // Use appropriate timestamp based on order state
      let relevantTime: string | undefined;
      if (order.workflow_status === 'preparing') {
        // For orders in kitchen, check time since chef accepted
        relevantTime = (order as any).chef_accepted_at || (order as any).created_at;
      } else if (order.workflow_status === 'ready') {
        // For orders ready for delivery, check time since marked ready
        relevantTime =
          (order as any).ready_at || (order as any).chef_accepted_at || (order as any).created_at;
      } else {
        relevantTime = (order as any).created_at;
      }

      const relevantMs = relevantTime ? Date.parse(String(relevantTime)) : Number.NaN;

      // Get prep time from order or use default of 30 minutes
      const prepTimeMinutes = (order as any).estimated_prep_time || 30;
      const overdueMs = prepTimeMinutes * 60 * 1000;
      const now = Date.now();

      const isOverdue =
        Number.isFinite(relevantMs) &&
        sessionStatus !== 'paid' &&
        order.workflow_status !== 'delivered' &&
        ['preparing', 'ready'].includes(order.workflow_status) &&
        now - relevantMs > overdueMs;

      if (isOverdue) {
        const mins = Math.max(0, Math.round((now - relevantMs) / 60000));
        statusEl.textContent = 'Atrasado';
        statusEl.title = `${friendlyStatus} • ${mins} min`;
        statusEl.className = 'status status--overdue';
      } else {
        statusEl.textContent = friendlyStatus;
        statusEl.removeAttribute('title');
        const statusClass = sessionStatus === 'paid' ? 'paid' : order.workflow_status;
        statusEl.className = `status status--${statusClass}`;
      }
    }

    // Time alerts (Active tab): subtle pink row + blinking clock if >15 minutes
    const inActiveOrdersTable = Boolean(row.closest('#waiter-orders'));
    if (inActiveOrdersTable) {
      const createdAt =
        row.dataset.createdAt || (order as any).created_at || (order as any).createdAt;
      const createdMs = createdAt ? Date.parse(String(createdAt)) : Number.NaN;
      const now = Date.now();
      const agedMinutes = 15;
      const agedMs = agedMinutes * 60 * 1000;
      const isFinishedSession = new Set(['paid', 'paid', 'closed', 'cancelled']).has(sessionStatus);
      const isAged = Number.isFinite(createdMs) && !isFinishedSession && now - createdMs > agedMs;

      row.classList.toggle('waiter-row--aged', isAged);

      const orderLink = row.querySelector<HTMLButtonElement>('.order-id-link');
      if (orderLink) {
        const existing = orderLink.querySelector<HTMLElement>('.order-age-indicator');
        if (isAged && !existing) {
          const indicator = document.createElement('span');
          indicator.className = 'order-age-indicator';
          indicator.title = 'Más de 15 min';
          indicator.replaceChildren(createFragment(WaiterBoard.ICON_CLOCK));
          orderLink.appendChild(indicator);
        } else if (!isAged && existing) {
          existing.remove();
        }
      }
    }

    // Disable waiter note when session is not active
    const noteField = row.querySelector<HTMLTextAreaElement>(
      `textarea[data-order-note="${order.id}"]`
    );
    const finishedStatuses = new Set(['paid', 'paid', 'closed', 'cancelled']);
    const isFinished = finishedStatuses.has(sessionStatus);
    if (noteField) {
      noteField.disabled = isFinished;
      noteField.placeholder = isFinished ? 'Esta orden ya fue cerrada' : '';
      noteField.classList.toggle('disabled', isFinished);
    }

    // Check if payment actions should be rendered (delivered + not paid)
    // Only show payment actions if NOT in waiter scope (keep waiter view clean)
    const activeScope = window.APP_DATA?.active_scope || 'waiter';
    const canProcessPayments = Boolean(window.APP_DATA?.can_process_payments);
    const shouldShowPaymentActions =
      activeScope !== 'waiter' &&
      canProcessPayments &&
      sessionStatus !== 'paid' &&
      order.workflow_status === 'delivered';

    console.log(
      '[DEBUG] Status:',
      order.workflow_status,
      'Should show payment:',
      shouldShowPaymentActions
    );

    // If session is paid, show paid status
    if (sessionStatus === 'paid') {
      ensureActionLabel('Cuenta pagada');
      const group = document.createElement('div');
      group.className = 'waiter-action-group';
      const sessionId = escapeHtml(String(order.session_id));
      const actionsHtml = this.capabilities.canReprint
        ? `
                <div class="waiter-action-group__actions">
                    <button type="button" class="btn btn--small btn--secondary waiter-action--icon"
                        data-session-action="print-ticket-and-confirm"
                        data-session-id="${sessionId}"
                        title="Imprimir ticket"
                        aria-label="Imprimir ticket">
                        ${WaiterBoard.ICON_TICKET}
                    </button>
                </div>`
        : '';
      group.replaceChildren(
        createFragment(`
                <div class="waiter-action-group__label" style="color: #10b981;">✅ Pagado</div>
                <p class="waiter-action-group__hint">Esta cuenta ya fue cobrada.</p>
                ${actionsHtml}
            `)
      );
      actionsContainer.appendChild(group);
      return;
    }

    // For delivered orders, show payment actions immediately
    if (shouldShowPaymentActions) {
      ensureActionLabel('Cobro');
      this.renderPaymentActions(actionsContainer as HTMLElement, order);
      return;
    }

    // For other states, show the professional format
    // For other states, render simple buttons directly
    console.log(
      '[DEBUG renderRow] About to render buttons. StatusInfo:',
      statusInfo,
      'AllowedActions count:',
      allowedActions.length
    );
    if (statusInfo && allowedActions.length > 0) {
      console.log('[DEBUG renderRow] Creating button container for order', order.id);
      ensureActionLabel(actionLabelText);
      const container = document.createElement('div');
      container.className = 'waiter-actions-simple';
      container.style.display = 'flex';
      container.style.gap = '0.5rem';
      container.style.flexWrap = 'wrap';

      const viewBtn = document.createElement('button');
      viewBtn.type = 'button';
      viewBtn.className = 'btn btn--small btn--secondary waiter-action--icon';
      viewBtn.setAttribute('data-order-detail', String(order.id));
      viewBtn.title = 'Ver detalle';
      viewBtn.setAttribute('aria-label', 'Ver detalle');
      viewBtn.replaceChildren(createFragment(WaiterBoard.ICON_EYE));
      container.appendChild(viewBtn);

      allowedActions.forEach((action) => {
        console.log('[DEBUG renderRow] Adding action button:', action.label, 'for order', order.id);
        const variantClass =
          action.variant === 'danger'
            ? 'btn--danger'
            : action.variant === 'success'
              ? 'btn--success'
              : action.variant === 'disabled'
                ? 'btn--disabled'
                : 'btn--secondary';
        const disabledAttr = action.disabled ? 'disabled' : '';
        const disabledClass = action.disabled ? 'btn-disabled' : '';
        const titleAttr = action.disabled ? 'title="Esperando que cocina termine"' : '';
        const labelLower = (action.label || '').toLowerCase();
        const iconSvg =
          labelLower.includes('imprimir') || labelLower.includes('ticket')
            ? WaiterBoard.ICON_TICKET
            : WaiterBoard.ICON_CHECK;
        // Create button element properly to avoid innerHTML security risks if this was user input (safe here)
        // Using template literal for simplicity as these are admin-defined actions
        const safeLabel = escapeHtml(action.label || '');
        const safeEndpoint = escapeHtml(action.endpoint(order.id));
        const btnHtml = `<button type="button" class="btn btn--small ${variantClass} ${disabledClass} waiter-action waiter-action--icon"
                    ${disabledAttr}
                    title="${safeLabel}"
                    aria-label="${safeLabel}"
                    data-endpoint="${safeEndpoint}">
                    ${iconSvg}
                </button>`;
        container.appendChild(createFragment(btnHtml));
      });

      // Add partial delivery button logic
      if (order.workflow_status === 'ready' && order.items && order.items.length > 1) {
        const allDelivered = order.items.every((item) => item.is_fully_delivered);
        if (!allDelivered) {
          const partialBtnHtml = `<button type="button" class="btn btn--small btn--secondary partial-delivery-btn"
                        data-order-id="${escapeHtml(String(order.id))}"
                        title="Entregar items individualmente">
                        📦 Parcial
                    </button>`;
          container.appendChild(createFragment(partialBtnHtml));
        }
      }

      console.log(
        '[DEBUG renderRow] Appending container with',
        container.children.length,
        'buttons to actions container'
      );
      actionsContainer.appendChild(container);
    } else {
      console.log(
        '[DEBUG renderRow] NOT rendering buttons. StatusInfo exists?',
        !!statusInfo,
        'AllowedActions:',
        allowedActions.length
      );
    }

    // Render star + cancel controls together
    this.renderStarAndCancel(row, order);
  }

  private renderPaymentActions(container: HTMLElement, order: WaiterOrder): void {
    // Basarnos en el estado de la fila (dataset) para no depender de que "order.session" venga siempre poblado
    const row = container.closest<HTMLTableRowElement>('tr[data-order-id]');
    const sessionStatus = order.session?.status || row?.dataset.sessionStatus || 'open';

    console.log(
      '[DEBUG renderPaymentActions] Order:',
      order.id,
      'Workflow:',
      order.workflow_status,
      'Session:',
      sessionStatus
    );

    const allowCharge = Boolean(window.APP_DATA?.can_process_payments);
    const allowPrint = Boolean(
      this.capabilities.canReprint || this.capabilities.canCharge || allowCharge
    );
    if (!allowCharge && !allowPrint) {
      console.log('[DEBUG] Skipping payment actions - no permissions');
      return;
    }

    // No mostrar nada si la cuenta ya está cerrada o la orden no está entregada
    if (sessionStatus === 'paid') {
      console.log('[DEBUG] Skipping - session closed');
      return;
    }
    if (order.workflow_status !== 'delivered') {
      console.log('[DEBUG] Skipping - not delivered, status:', order.workflow_status);
      return;
    }

    console.log('[DEBUG] Rendering payment actions for order:', order.id);

    // Simply render buttons without the big wrapper/labels
    const actionsContainer = document.createElement('div');
    actionsContainer.style.display = 'flex';
    actionsContainer.style.gap = '0.5rem';
    actionsContainer.style.flexWrap = 'wrap';

    // Si está pendiente de confirmación
    if (sessionStatus === 'awaiting_payment_confirmation') {
      if (allowPrint) {
        const sessionId = escapeHtml(String(row?.dataset.sessionId || order.session?.id || ''));
        actionsContainer.appendChild(
          createFragment(`
                    <button type="button" class="btn btn--small btn--secondary waiter-action--icon"
                        data-session-action="print-ticket-and-confirm"
                        data-session-id="${sessionId}"
                        title="Imprimir ticket y confirmar"
                        aria-label="Imprimir ticket y confirmar">
                        ${WaiterBoard.ICON_TICKET}
                    </button>
                `)
        );
        const paidLabel = document.createElement('span');
        paidLabel.style.fontSize = '0.75rem';
        paidLabel.style.color = '#10b981';
        paidLabel.style.display = 'flex';
        paidLabel.style.alignItems = 'center';
        paidLabel.textContent = '✅ Pagado';
        actionsContainer.appendChild(paidLabel);
      }
    } else {
      // Para estados abiertos/cobrar
      if (allowCharge) {
        const chargeBtn = document.createElement('button');
        chargeBtn.type = 'button';
        chargeBtn.className = 'btn btn--small btn--primary';
        chargeBtn.dataset.openPaymentModal = 'true';
        chargeBtn.textContent = '💰 Cobrar';
        actionsContainer.appendChild(chargeBtn);
      }
    }

    if (actionsContainer.children.length > 0) {
      container.appendChild(actionsContainer);
    }

    // Debug logging removed to avoid reference to deleted 'group' variable
    console.log('[DEBUG] Rendered payment buttons count:', container.children.length);
  }

  private renderStarAndCancel(row: HTMLTableRowElement, order: WaiterOrder): void {
    const starCell = row.querySelector<HTMLTableCellElement>('td:first-child');
    const cancelCell = row.querySelector<HTMLTableCellElement>('.cancel-action');
    if (!starCell || !cancelCell) return;

    // Move star button into a wrapper to host cancel too
    const starBtn = starCell.querySelector<HTMLButtonElement>('.star-btn');
    starCell.replaceChildren();
    const wrapper = document.createElement('div');
    wrapper.className = 'star-cancel-wrapper';
    if (starBtn) wrapper.appendChild(starBtn);

    cancelCell.replaceChildren();

    // Don't show cancel button in the table - it's now inside the order detail panel
    // The cancel button will appear when clicking on the order number (#1, #2, etc.)

    // Place wrapper spanning first cell; leave cancel cell empty to keep column width small
    starCell.appendChild(wrapper);
  }

  private updateSharedSessionState(sessionData: SessionData): void {
    if (!window.SESSIONS_STATE || !sessionData) return;
    window.SESSIONS_STATE[sessionData.id] = {
      ...window.SESSIONS_STATE[sessionData.id],
      ...sessionData,
    } as any;
    // Update session data for relevant orders in the Map
    const isPaid = sessionData.status === 'paid';
    this.orders.forEach((order) => {
      if (order.session_id === sessionData.id) {
        order.session = { ...order.session, ...sessionData };
      }
    });
    // Mark paid timestamp on rows to keep them visible for retention window
    if (isPaid) {
      this.ordersTable
        ?.querySelectorAll<HTMLTableRowElement>(`tr[data-session-id="${sessionData.id}"]`)
        .forEach((row) => {
          if (!row.dataset.paidAt) {
            row.dataset.paidAt = new Date().toISOString();
          }
        });
    }
    this.applyFilters(); // Re-apply filters after session state change
  }

  private async loadPendingCalls(): Promise<void> {
    try {
      const response = await fetch('/api/waiter-calls/pending');
      if (!response.ok) throw new Error('Error al cargar llamadas');
      const data = await response.json();
      this.pendingCalls = Array.isArray(data.waiter_calls)
        ? data.waiter_calls.map((item: any) => this.normalizeWaiterCall(item)).filter(Boolean)
        : [];
      this.updateNotificationsBadge();
      this.renderNotifications();
      document.dispatchEvent(
        new CustomEvent('employee:waiter-calls:updated', { detail: { calls: this.pendingCalls } })
      );
    } catch (error) {
      console.error('[WAITER] Error loading pending calls:', error);
    }
  }

  private renderNotifications(): void {
    if (!this.notificationsContent) return;
    if (this.pendingCalls.length === 0) {
      this.notificationsContent.replaceChildren(
        createFragment('<p class="notifications-empty">No hay llamadas pendientes</p>')
      );
      return;
    }
    const list = document.createElement('div');
    list.className = 'notifications-list';

    this.pendingCalls.forEach((call) => {
      const item = document.createElement('div');
      item.className = 'notification-item';
      item.dataset.callId = String(call.id);

      const icon = document.createElement('div');
      icon.className = 'notification-item__icon';
      icon.textContent = call.notes === CHECKOUT_CALL_NOTE ? '💳' : '🔔';

      const content = document.createElement('div');
      content.className = 'notification-item__content';

      const title = document.createElement('h4');
      title.textContent = `Mesa ${call.table_number}`;

      const note = document.createElement('p');
      note.textContent =
        call.notes === CHECKOUT_CALL_NOTE ? 'Solicitó la cuenta' : 'Solicitando asistencia';

      const orders = document.createElement('p');
      orders.className = 'notification-item__orders';
      orders.textContent = call.order_numbers.length
        ? `Pedidos ${call.order_numbers.map((n) => `#${n}`).join(', ')} `
        : 'Pedido pendiente por asignar';

      const time = document.createElement('span');
      time.className = 'notification-item__time';
      time.textContent = getTimeAgo(new Date(call.created_at));

      content.appendChild(title);
      content.appendChild(note);
      content.appendChild(orders);
      content.appendChild(time);

      const button = document.createElement('button');
      button.className = 'btn btn--primary btn--small';
      button.dataset.callAction = 'confirm';
      button.dataset.callId = String(call.id);
      button.textContent = '✅ Ya voy';

      item.appendChild(icon);
      item.appendChild(content);
      item.appendChild(button);
      list.appendChild(item);
    });

    this.notificationsContent.replaceChildren(list);
    // Event listeners are handled via delegation in initializeNotificationsPanelEvents()
  }

  private clearPendingCalls(): void {
    this.pendingCalls = [];
    this.updateNotificationsBadge();
    this.renderNotifications();
    if (window.EmployeeBell) {
      window.EmployeeBell.setState('idle');
      window.EmployeeBell.setCount(0);
    }
  }

  private async confirmWaiterCall(callId: number): Promise<void> {
    const employeeId = this.currentEmployeeId;
    if (!employeeId) {
      showFeedback(this.feedbackEl, 'Error: No hay empleado activo', true);
      return;
    }
    try {
      const response = await fetch(`/api/waiter-calls/${callId}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ employee_id: employeeId }),
      });
      if (!response.ok) throw new Error('Error al confirmar llamada');
      this.pendingCalls = this.pendingCalls.filter((call) => call.id !== callId);
      this.updateNotificationsBadge();
      this.renderNotifications();
      this.soundManager.play();
      showFeedback(this.feedbackEl, '✅ Confirmado: ya estás en camino');
    } catch (error) {
      showFeedback(this.feedbackEl, 'Error al confirmar llamada', true);
    }
  }

  private toggleNotificationsPanel(): void {
    if (!this.notificationsPanel) return;
    const isOpen = this.notificationsPanel.classList.contains('open');
    if (isOpen) {
      this.notificationsPanel.classList.remove('open');
      setTimeout(() => {
        if (this.notificationsPanel) {
          this.notificationsPanel.style.display = 'none';
        }
      }, 300);
      if (window.EmployeeBell) {
        window.EmployeeBell.setState(this.pendingCalls.length ? 'pending' : 'idle');
      }
    } else {
      this.notificationsPanel.style.display = 'block';
      requestAnimationFrame(() => {
        this.notificationsPanel?.classList.add('open');
      });
      if (window.EmployeeBell) {
        window.EmployeeBell.setState('active');
      }
    }
  }

  private initializeWebSocket(): void {
    if (typeof window.io === 'undefined') {
      console.warn('[WAITER] Socket.io no disponible, se omiten funciones en tiempo real');
      return;
    }
    try {
      this.socket = window.io({
        transports: ['websocket', 'polling'],
        reconnection: true,
        reconnectionAttempts: 5,
        reconnectionDelay: 1000,
      });
      this.socket.on('connect', () => {
        this.socket.emit(WAITERS_ROOM);
        this.socket.emit(EMPLOYEES_ROOM);
      });
      this.socket.on('waiter_call', (data: any) => {
        const call = this.normalizeWaiterCall(data);
        if (call) {
          this.handleRealtimeWaiterCall(call);
        }
      });
      this.socket.on('new_order', (data: any) => {
        this.soundManager.play();
        showFeedback(
          this.feedbackEl,
          `🆕 Nueva orden: Mesa ${data.table_number || 'N/A'} - Orden #${data.order_id}`
        );
        // Force full table refresh by clearing and reloading (reduced delay for faster updates)
        setTimeout(() => {
          this.refreshOrdersAndReload();
        }, 200);
      });
      this.socket.on('order_status_changed', (data: any) => {
        console.log('[WAITER] Order status changed event:', data);
        // If we have order details, update immediately
        if (data?.order_id && this.orders.has(data.order_id)) {
          const existingOrder = this.orders.get(data.order_id);
          if (existingOrder && data.workflow_status) {
            const normalizedStatus = normalizeWorkflowStatus(data.workflow_status);
            existingOrder.workflow_status = normalizedStatus;
            const row = this.ordersTable?.querySelector<HTMLTableRowElement>(
              `tr[data-order-id="${data.order_id}"]`
            );
            if (row) {
              row.dataset.status = normalizedStatus;
              this.renderRow(row, existingOrder);
            }
          }
        }
        // Then refresh from server to get complete state
        this.scheduleRealtimeRefresh(500, true);
      });
      this.socket.on('sessions.status_changed', (data: any) => {
        // Update session state when session status changes
        if (data && data.session_id) {
          const sessionData: SessionData = {
            id: data.session_id,
            status: data.status,
            table_number: data.table_number || null,
            notes: null,
          };
          this.updateSharedSessionState(sessionData);
          // Refresh orders to show payment buttons if needed
          this.ordersTable
            ?.querySelectorAll<HTMLTableRowElement>(`tr[data-session-id="${data.session_id}"]`)
            .forEach((row) => {
              const orderId = Number(row.dataset.orderId);
              const order = this.orders.get(orderId); // Use the new Map
              if (order) {
                order.session = { ...order.session, ...sessionData };
                this.renderRow(row, order);
              }
            });
        }
      });
      this.socket.on('sessions.paid', (data: any) => {
        if (!data?.session_id) return;
        const sessionData: SessionData = {
          id: data.session_id,
          status: 'paid',
          table_number: data.table_number || null,
          notes: null,
        };
        this.updateSharedSessionState(sessionData);
        this.ordersTable
          ?.querySelectorAll<HTMLTableRowElement>(`tr[data-session-id="${data.session_id}"]`)
          .forEach((row) => {
            const orderId = Number(row.dataset.orderId);
            const order = this.orders.get(orderId);
            if (order) {
              order.session = { ...order.session, status: 'paid' };
              order.workflow_status = 'delivered';
              this.renderRow(row, order);
            }
          });
        void this.loadPaidSessions();
      });
      this.socket.on('orders.auto_accepted', (data: any) => {
        if (data?.waiter_id === this.currentEmployeeId) {
          console.log('[WAITER] Order auto-accepted:', data);
          showFeedback(
            this.feedbackEl,
            `Nueva orden auto-asignada de Mesa ${data.table_number}`,
            false
          );
          // Immediately update the order in the Map and UI if it exists
          if (data.order_id && this.orders.has(data.order_id)) {
            // Update the order status immediately
            const existingOrder = this.orders.get(data.order_id);
            if (existingOrder) {
              existingOrder.workflow_status = 'queued';
              existingOrder.waiter_id = data.waiter_id;
              // Update the row immediately
              const row = this.ordersTable?.querySelector<HTMLTableRowElement>(
                `tr[data-order-id="${data.order_id}"]`
              );
              if (row) {
                row.dataset.status = 'queued';
                row.dataset.waiterId = String(data.waiter_id);
                this.renderRow(row, existingOrder);
              }
            }
          }
          // Then refresh from server to get complete state
          setTimeout(() => {
            void this.refreshOrders();
            // Refresh assigned tables display after auto-acceptance
            const tableManager = (window as any).tableAssignmentManager;
            if (tableManager?.refreshAssignedTablesDisplay) {
              setTimeout(() => {
                tableManager.refreshAssignedTablesDisplay();
              }, 500);
            }
          }, 500);
        }
      });
    } catch (error) {
      console.error('[WAITER] Error inicializando WebSocket', error);
    }
  }

  private initializeRealtimeEvents(): void {
    if (!window.ProntoRealtime || typeof window.ProntoRealtime.subscribe !== 'function') {
      return;
    }
    if (this.realtimeUnsubscribe) {
      this.realtimeUnsubscribe();
    }
    this.realtimeUnsubscribe = window.ProntoRealtime.subscribe((event: any) => {
      if (!event?.type) return;
      const payload = event.payload || {};
      if (event.type === 'orders.status_changed') {
        const orderId = Number(payload.order_id || payload.orderId || payload.id);
        const status = payload.status || payload.workflow_status;
        if (orderId && status) {
          this.updateOrderStatus(orderId, status as WorkflowStatus);
          this.scheduleRealtimeRefresh(350, true);
        }
        return;
      }
      if (event.type === 'orders.new') {
        this.soundManager.play();
        showFeedback(
          this.feedbackEl,
          `🆕 Nueva orden: Mesa ${payload.table_number || 'N/A'} - Orden #${payload.order_id || payload.id || ''}`
        );
        this.scheduleRealtimeRefresh(500, true);
        return;
      }
      if (event.type === 'sessions.status_changed') {
        if (payload.session_id) {
          const sessionData: SessionData = {
            id: payload.session_id,
            status: payload.status,
            table_number: payload.table_number || null,
            notes: null,
          };
          this.updateSharedSessionState(sessionData);
          this.refreshRowsForSession(payload.session_id);
          this.scheduleRealtimeRefresh(400, false);
        }
      }
    });
  }

  private scheduleRealtimeRefresh(delayMs: number, showLoading: boolean): void {
    if (this.realtimeRefreshTimer) {
      window.clearTimeout(this.realtimeRefreshTimer);
    }
    this.realtimeRefreshTimer = window.setTimeout(() => {
      void this.refreshOrders(showLoading);
    }, delayMs) as unknown as number;
  }

  private updateOrderStatus(orderId: number, status: WorkflowStatus): void {
    const existingOrder = this.orders.get(orderId);
    if (!existingOrder) return;
    const normalizedStatus = normalizeWorkflowStatus(status);
    existingOrder.workflow_status = normalizedStatus;
    const row = this.ordersTable?.querySelector<HTMLTableRowElement>(
      `tr[data-order-id="${orderId}"]`
    );
    if (row) {
      row.dataset.status = normalizedStatus;
      this.renderRow(row, existingOrder);
    }
  }

  private handleRealtimeWaiterCall(call: WaiterCall): void {
    if (call.status === 'pending') {
      this.soundManager.play();
      const ordersMention = call.order_numbers.length
        ? `Pedidos ${call.order_numbers.map((num) => `#${num}`).join(', ')}`
        : 'Pedido pendiente';
      showFeedback(
        this.feedbackEl,
        `${call.notes === CHECKOUT_CALL_NOTE ? '💳' : '🔔'} Mesa ${call.table_number}: ${ordersMention}`
      );
    }
    this.upsertPendingCall(call);
  }

  private upsertPendingCall(call: WaiterCall): void {
    const index = this.pendingCalls.findIndex((item) => item.id === call.id);
    if (call.status === 'pending') {
      if (index === -1) {
        this.pendingCalls.unshift(call);
      } else {
        this.pendingCalls[index] = call;
      }
    } else if (index > -1) {
      this.pendingCalls.splice(index, 1);
    }
    this.updateNotificationsBadge();
    this.renderNotifications();
  }

  private updateNotificationsBadge(): void {
    if (!window.EmployeeBell) return;
    window.EmployeeBell.setCount(this.pendingCalls.length);
    window.EmployeeBell.setState(this.pendingCalls.length > 0 ? 'pending' : 'idle');
  }

  private normalizeWaiterCall(payload: any): WaiterCall {
    const id = Number(payload.call_id || payload.id);
    const orders = Array.isArray(payload.order_numbers)
      ? payload.order_numbers.map((num: any) => Number(num)).filter(Boolean)
      : [];
    return {
      id,
      session_id: payload.session_id || null,
      table_number: payload.table_number || 'N/A',
      status: payload.status || 'pending',
      created_at: payload.created_at || payload.timestamp || new Date().toISOString(),
      notes: payload.call_type || payload.notes || null,
      order_numbers: orders,
    };
  }

  private setTabBadge(elementId: string, count: number): void {
    const badge = document.getElementById(elementId);
    if (!badge) return;

    const normalized = Number.isFinite(count) ? Math.max(0, count) : 0;
    badge.textContent = normalized > 99 ? '99+' : String(normalized);
    badge.classList.toggle('is-hidden', normalized <= 0);
  }

  private initializeHeaderTableChips(): void {
    const container = document.getElementById('header-tables-badges');
    if (!container || !this.searchInput) return;

    container.addEventListener('click', (event) => {
      const target = event.target as HTMLElement;
      const chip = target.closest<HTMLButtonElement>('.table-badge[data-table-number]');
      if (!chip) return;

      const tableNumber = chip.dataset.tableNumber?.trim();
      if (!tableNumber) return;

      this.switchTab('active');
      this.searchInput!.value = tableNumber;
      this.searchTerm = tableNumber.toLowerCase().trim();
      this.searchInput!.dispatchEvent(new Event('input', { bubbles: true }));
      this.searchInput!.focus();
    });
  }

  private storeCancelReasonCache: boolean | null = null;
  private async shouldStoreCancelReason(): Promise<boolean> {
    if (this.storeCancelReasonCache !== null) return this.storeCancelReasonCache;
    try {
      const res = await fetch('/api/config/store_cancel_reason');
      if (!res.ok) throw new Error('config missing');
      const data = await res.json().catch(() => ({}));
      const raw = (data as any)?.value ?? (data as any)?.config_value ?? (data as any)?.configValue;
      this.storeCancelReasonCache = String(raw ?? 'true').toLowerCase() !== 'false';
    } catch (_error) {
      this.storeCancelReasonCache = true;
    }
    return this.storeCancelReasonCache;
  }

  // ==================== NEW METHODS FOR TABS, PINNING, AND PAID ORDERS ====================

  private initializeTabs(): void {
    const tabs = this.root.querySelectorAll<HTMLButtonElement>('.waiter-tab');
    tabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        const tabType = tab.dataset.tab as 'active' | 'tracking' | 'paid' | 'cancelled';
        this.switchTab(tabType);
      });
    });
    this.enforceTabVisibility();
    // Ensure initial tab visibility is set correctly
    this.switchTab('active');
  }

  private switchTab(tab: 'active' | 'tracking' | 'paid' | 'cancelled'): void {
    // if (tab === 'paid' && !this.capabilities.canViewPaid) {
    //     return;
    // }
    this.activeTab = tab;

    // Update tab UI
    this.root.querySelectorAll('.waiter-tab').forEach((t) => {
      t.classList.toggle('active', t.getAttribute('data-tab') === tab);
    });

    // Show/hide sections
    const activeSection = document.getElementById('active-orders-section');
    const trackingSection = document.getElementById('tracking-orders-section');
    const paidSection = document.getElementById('paid-orders-section');
    const cancelledSection = document.getElementById('cancelled-orders-section');

    if (activeSection) activeSection.style.display = tab === 'active' ? 'block' : 'none';
    if (trackingSection) trackingSection.style.display = tab === 'tracking' ? 'block' : 'none';
    if (paidSection) paidSection.style.display = tab === 'paid' ? 'block' : 'none';
    if (cancelledSection) cancelledSection.style.display = tab === 'cancelled' ? 'block' : 'none';

    // Load tracking orders if switching to tracking tab
    if (tab === 'tracking') {
      this.renderTrackingOrders();
      // Trigger card rendering
      if (typeof (window as any).renderOrderCards === 'function') {
        (window as any).renderOrderCards();
      }
    }

    // Load paid sessions if switching to paid tab
    if (tab === 'paid') {
      void this.loadPaidSessions();
      // Auto-refresh every 30 seconds
      if (!this.paidSessionsInterval) {
        this.paidSessionsInterval = window.setInterval(
          () => this.loadPaidSessions(),
          30000
        ) as unknown as number;
      }
    } else if (tab === 'cancelled') {
      this.renderCancelledOrders();
    } else {
      // Clear interval when leaving paid tab
      if (this.paidSessionsInterval) {
        window.clearInterval(this.paidSessionsInterval as unknown as number);
        this.paidSessionsInterval = undefined;
      }
    }
  }

  private enforceTabVisibility(): void {
    const paidTab = document.querySelector<HTMLElement>('.waiter-tab[data-tab="paid"]');
    const paidSection = document.getElementById('paid-orders-section');
    const cancelledTab = document.querySelector<HTMLElement>('.waiter-tab[data-tab="cancelled"]');
    const cancelledSection = document.getElementById('cancelled-orders-section');
    // Temporarily disabled capability check to ensure tab is visible per user request
    /* if (!this.capabilities.canViewPaid) {
            if (paidTab) paidTab.style.display = 'none';
            if (paidSection) paidSection.style.display = 'none';
            if (this.activeTab === 'paid') {
                this.switchTab('active');
            }
        } */
    if (paidTab) paidTab.style.display = '';
    if (cancelledTab) cancelledTab.style.display = '';
    if (cancelledSection) cancelledSection.style.display = '';
  }

  private initializeStarButtons(): void {
    this.ordersTable?.addEventListener('click', (event) => {
      const target = event.target as HTMLElement;
      const starBtn = target.closest<HTMLButtonElement>('.star-btn');
      if (starBtn) {
        const orderId = Number(starBtn.dataset.orderId);
        this.toggleStar(orderId);
      }
    });

    // Update star button states on initial load
    this.updateStarButtonStates();
  }

  private toggleStar(orderId: number): void {
    if (this.starredOrders.has(orderId)) {
      this.starredOrders.delete(orderId);
    } else {
      this.starredOrders.add(orderId);
    }
    this.saveStarredOrders();
    this.updateStarButtonStates();
    this.updateTrackingBadge();
    this.sortOrders();
    this.applyFilters(); // Re-apply filters after starring

    // Update tracking tab if it's visible
    if (this.activeTab === 'tracking') {
      this.renderTrackingOrders();
      // Trigger card rendering
      setTimeout(() => {
        if (typeof (window as any).renderOrderCards === 'function') {
          (window as any).renderOrderCards();
        }
      }, 100);
    }
  }

  private loadStarredOrders(): void {
    try {
      const stored = localStorage.getItem('waiter_starred_orders');
      if (stored) {
        const ids = JSON.parse(stored) as number[];
        this.starredOrders = new Set(ids);
      }
    } catch (error) {
      console.error('[WAITER] Error loading starred orders:', error);
    }
  }

  private saveStarredOrders(): void {
    try {
      const ids = Array.from(this.starredOrders);
      localStorage.setItem('waiter_starred_orders', JSON.stringify(ids));
    } catch (error) {
      console.error('[WAITER] Error saving starred orders:', error);
    }
  }

  private updateStarButtonStates(): void {
    this.ordersTable?.querySelectorAll<HTMLButtonElement>('.star-btn').forEach((btn) => {
      const orderId = Number(btn.dataset.orderId);
      const isStarred = this.starredOrders.has(orderId);
      btn.classList.toggle('starred', isStarred);
      btn.title = isStarred ? 'Quitar de seguimiento' : 'Agregar a seguimiento';

      // Update star icon
      const iconEl = btn.querySelector('.star-icon');
      if (iconEl) {
        iconEl.textContent = isStarred ? '★' : '☆';
      }

      // Update row styling
      const row = btn.closest('tr');
      if (row) {
        row.classList.toggle('order-starred', isStarred);
      }
    });
  }

  private updateTrackingBadge(): void {
    // Count only orders from active sessions (not closed/paid)
    const finishedStatuses = ['paid', 'closed', 'paid', 'cancelled'];
    const activeStarredCount = Array.from(this.starredOrders).filter((id) => {
      const order = this.orders.get(id);
      if (!order) return false;
      const sessionStatus = order.session?.status || '';
      return !finishedStatuses.includes(sessionStatus);
    }).length;

    this.setTabBadge('tracking-count', activeStarredCount);

    // Update tracking orders count
    const countEl = document.querySelector('.tracking-orders-count');
    if (countEl) {
      countEl.textContent = `${activeStarredCount} orden${activeStarredCount !== 1 ? 'es' : ''}`;
    }
  }

  private renderTrackingOrders(): void {
    if (!this.trackingOrdersTable) return;

    // Filter out orders from closed/paid sessions
    const finishedStatuses = ['paid', 'closed', 'paid', 'cancelled'];
    const starredOrdersList = Array.from(this.starredOrders)
      .map((id) => this.orders.get(id))
      .filter((order): order is WaiterOrder => {
        if (!order) return false;
        // Exclude orders from finished sessions
        const sessionStatus = order.session?.status || '';
        if (finishedStatuses.includes(sessionStatus)) {
          // Auto-remove from starred since session is finished
          this.starredOrders.delete(order.id);
          return false;
        }
        const createdAt = (order as any).created_at || (order as any).createdAt;
        if (!this.isWithinDateFilter(createdAt)) return false;
        return true;
      });

    // Save updated starred list if any were removed
    this.saveStarredOrders();

    // Show empty state if no starred orders
    if (starredOrdersList.length === 0) {
      this.trackingOrdersTable.replaceChildren(
        createFragment(`
                <tr class="tracking-empty-state">
                    <td colspan="8" style="text-align: center; padding: 2rem; color: #64748b;">
                        <div style="font-size: 2rem; margin-bottom: 0.5rem;">⭐</div>
                        <p style="margin: 0;">No tienes órdenes en seguimiento</p>
                        <p style="margin: 0.5rem 0 0; font-size: 0.9rem;">Haz clic en la estrella ☆ de cualquier orden para agregarla aquí</p>
                    </td>
                </tr>
            `)
      );
      return;
    }

    // Render starred orders
    const trackingHtml = starredOrdersList
      .map((order) => {
        const statusLabel = escapeHtml(this.getDisplayStatus(order, order.session?.status));
        const total = (order as any).session?.total_amount ?? (order as any).total_amount ?? null;
        const totalDisplay = escapeHtml(
          total !== null && total !== undefined ? `$${Number(total).toFixed(2)}` : '—'
        );
        const statusClass = escapeHtml(
          order.session?.status === 'paid' ? 'paid' : order.workflow_status
        );
        const tableNumber = escapeHtml(order.session?.table_number || 'N/A');
        const customerName = escapeHtml(order.customer?.name || 'Cliente');
        const customerEmail = escapeHtml(normalizeCustomerEmail(order.customer?.email) || '');
        const customerPhone = escapeHtml(
          (order as any).customer_phone || order.customer?.phone || ''
        );
        const notes = escapeHtml(order.session?.notes || '');
        const waiterNotes = escapeHtml(order.waiter_notes || '');
        const orderId = escapeHtml(String(order.id));
        const sessionId = escapeHtml(String(order.session_id));
        const sessionStatus = escapeHtml(order.session?.status || '');
        const totalValue = escapeHtml(total !== null && total !== undefined ? String(total) : '');
        const waiterBadge = order.waiter_name
          ? `<span class="waiter-badge">👤 ${escapeHtml(order.waiter_name)}</span>`
          : '<span class="waiter-badge waiter-badge--unassigned">⚠️ Sin asignar</span>';
        return `
                <tr data-order-id="${orderId}" data-status="${escapeHtml(order.workflow_status)}"
                    data-session-id="${sessionId}" data-session-status="${sessionStatus}"
                    data-table-number="${tableNumber}"
                    data-customer-name="${customerName}"
                    data-customer-email="${customerEmail}"
                    data-customer-phone="${customerPhone}"
                    data-notes="${notes}"
                    data-waiter-notes="${waiterNotes}"
                    data-total="${totalValue}">
                    <td>
                        <button type="button" class="star-btn starred" data-order-id="${orderId}" title="Quitar de seguimiento">
                            <span class="star-icon">★</span>
                        </button>
                    </td>
                    <td>
                        <button type="button" class="order-id-link"
                            style="background: none; border: none; color: #3b82f6; font-weight: 600; cursor: pointer; text-decoration: underline; padding: 0;"
                            data-order-detail="${orderId}"
                            data-table-number="${tableNumber}"
                            data-customer-name="${customerName}"
                            data-customer-email="${customerEmail}"
                            data-customer-phone="${customerPhone}"
                            data-notes="${notes}"
                            data-waiter-notes="${waiterNotes}"
                            data-status="${escapeHtml(order.workflow_status)}" data-total="${totalValue}">
                            #${orderId}
                        </button>
                    </td>
                    <td>
                        <button type="button" class="table-number-link"
                            style="background: none; border: none; color: #ea580c; font-weight: 600; cursor: pointer; text-decoration: underline; padding: 0;"
                            data-table-info="${tableNumber}" data-table-number="${tableNumber}">
                            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" style="width: 16px; height: 16px;">
                                <path d="M4 10h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                                <path d="M6 10v10" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                                <path d="M18 10v10" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                                <path d="M8 6h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                                <path d="M7 6V4h10v2" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                            </svg>
                            ${tableNumber}
                        </button>
                    </td>
                    <td>${customerName}</td>
                    <td>${waiterBadge}</td>
                    <td>
                        <span class="order-total-display">${totalDisplay}</span>
                    </td>
                    <td><span class="status status--${statusClass}">${statusLabel}</span></td>
                    <td class="actions"></td>
                </tr>
            `;
      })
      .join('');

    this.trackingOrdersTable.replaceChildren(createFragment(trackingHtml));

    this.trackingOrdersTable
      .querySelectorAll<HTMLTableRowElement>('tr[data-order-id]')
      .forEach((row) => {
        const orderId = Number(row.dataset.orderId);
        const order = this.orders.get(orderId);
        if (order) {
          this.renderRow(row, order);
        }
      });

    // Attach event handlers for star buttons in tracking table
    this.trackingOrdersTable.querySelectorAll<HTMLButtonElement>('.star-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const orderId = Number(btn.dataset.orderId);
        this.toggleStar(orderId);
      });
    });
  }

  private renderCancelledOrders(): void {
    if (!this.cancelledOrdersTable) return;

    // Get all cancelled orders from the orders Map
    const cancelledOrdersList = Array.from(this.orders.values())
      .filter((order) => order.workflow_status === 'cancelled')
      .filter((order) => {
        const createdAt = (order as any).created_at || (order as any).createdAt;
        return this.isWithinDateFilter(createdAt);
      })
      .sort((a, b) => {
        // Sort by most recent first
        const aTime = (a as any).updated_at || (a as any).created_at || '';
        const bTime = (b as any).updated_at || (b as any).created_at || '';
        return bTime.localeCompare(aTime);
      });

    this.setTabBadge('cancelled-count', cancelledOrdersList.length);

    // Show empty state if no cancelled orders
    if (cancelledOrdersList.length === 0) {
      this.cancelledOrdersTable.replaceChildren(
        createFragment(`
                <tr class="cancelled-empty-state tracking-empty-state">
                    <td colspan="7" style="text-align: center; padding: 2rem; color: #64748b;">
                        <div style="font-size: 2rem; margin-bottom: 0.5rem;">❌</div>
                        <p style="margin: 0;">No hay órdenes canceladas</p>
                        <p style="margin: 0.5rem 0 0; font-size: 0.9rem;">Las órdenes canceladas aparecerán aquí</p>
                    </td>
                </tr>
            `)
      );
      return;
    }

    // Render cancelled orders
    const cancelledHtml = cancelledOrdersList
      .map((order) => {
        const total = (order as any).session?.total_amount ?? (order as any).total_amount ?? null;
        const totalDisplay = escapeHtml(
          total !== null && total !== undefined ? `$${Number(total).toFixed(2)}` : '—'
        );
        const tableNumber = escapeHtml(order.session?.table_number || 'N/A');
        const customerName = escapeHtml(order.customer?.name || 'Cliente');
        const waiterName = escapeHtml(order.waiter_name || 'Sin asignar');
        const cancelReason = escapeHtml((order as any).cancel_reason || 'Sin motivo especificado');
        const cancelledAt = (order as any).cancelled_at || (order as any).updated_at || '';
        const cancelledDate = escapeHtml(
          cancelledAt
            ? new Date(cancelledAt).toLocaleString('es-MX', {
                day: '2-digit',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit',
              })
            : '—'
        );
        const orderId = escapeHtml(String(order.id));

        return `
                <tr data-order-id="${orderId}" data-status="cancelled">
                    <td>
                        <button type="button" class="order-id-link"
                            style="background: none; border: none; color: #3b82f6; font-weight: 600; cursor: pointer; text-decoration: underline; padding: 0;"
                            data-order-detail="${orderId}"
                            data-table-number="${tableNumber}"
                            data-customer-name="${customerName}"
                            data-status="cancelled">
                            #${orderId}
                        </button>
                    </td>
                        <td>
                            <button type="button" class="table-number-link"
                                style="background: none; border: none; color: #ea580c; font-weight: 600; cursor: pointer; text-decoration: underline; padding: 0;"
                                data-table-info="${tableNumber}" data-table-number="${tableNumber}">
                                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" style="width: 16px; height: 16px;">
                                    <path d="M4 10h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                                    <path d="M6 10v10" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                                    <path d="M18 10v10" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                                    <path d="M8 6h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                                    <path d="M7 6V4h10v2" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                                </svg>
                                ${tableNumber}
                            </button>
                        </td>
                    <td>${customerName}</td>
                    <td><span class="waiter-badge">👤 ${waiterName}</span></td>
                    <td><span class="order-total-display">${totalDisplay}</span></td>
                    <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${cancelReason}">
                        ${cancelReason}
                    </td>
                    <td>${cancelledDate}</td>
                </tr>
            `;
      })
      .join('');

    this.cancelledOrdersTable.replaceChildren(createFragment(cancelledHtml));
  }

  private sortOrders(): void {
    if (!this.ordersTable) return;

    // ordersTable IS the tbody element (#waiter-orders)
    const rows = Array.from(
      this.ordersTable.querySelectorAll<HTMLTableRowElement>('tr[data-order-id]')
    );

    rows.sort((a, b) => {
      const aId = Number(a.dataset.orderId);
      const bId = Number(b.dataset.orderId);
      const aWaiterId = Number(a.dataset.waiterId);
      const bWaiterId = Number(b.dataset.waiterId);

      // 1. Starred orders first
      const aStarred = this.starredOrders.has(aId);
      const bStarred = this.starredOrders.has(bId);
      if (aStarred && !bStarred) return -1;
      if (!aStarred && bStarred) return 1;

      // 2. Assigned to current waiter
      const aAssigned = aWaiterId === this.currentEmployeeId;
      const bAssigned = bWaiterId === this.currentEmployeeId;
      if (aAssigned && !bAssigned) return -1;
      if (!aAssigned && bAssigned) return 1;

      // 3. Most recent first (higher ID = more recent)
      return bId - aId;
    });

    // Reorder rows
    rows.forEach((row) => this.ordersTable!.appendChild(row));
  }

  private initializeFilters(): void {
    // Restore filters from localStorage
    const savedSessionFilters = localStorage.getItem('waiter_session_filters');
    const savedWorkflowFilters = localStorage.getItem('waiter_workflow_filters');
    const savedShowMyOrders = localStorage.getItem('waiter_show_my_orders');
    const savedShowUnassigned = localStorage.getItem('waiter_show_unassigned_orders');
    const savedDateFilter = localStorage.getItem('waiter_date_filter');
    const savedDateDays = localStorage.getItem('waiter_date_days');

    if (savedSessionFilters) {
      this.sessionStatusFilters = new Set(JSON.parse(savedSessionFilters));
    }
    if (savedWorkflowFilters) {
      this.workflowStatusFilters = new Set(JSON.parse(savedWorkflowFilters));
    }
    if (savedShowMyOrders !== null) {
      this.showMyOrders = savedShowMyOrders === 'true';
    }
    if (savedShowUnassigned !== null) {
      this.showUnassignedOrders = savedShowUnassigned === 'true';
    }
    if (savedDateFilter) {
      if (['today', 'last7', 'custom', 'all'].includes(savedDateFilter)) {
        this.dateFilter = savedDateFilter as any;
      }
    }
    if (savedDateDays) {
      const n = Number(savedDateDays);
      if (Number.isFinite(n) && n > 0) {
        this.customDateDays = n;
      }
    }

    // Sync checkboxes
    this.syncFilterCheckboxes();

    // Modal controls
    const openBtn = document.getElementById('open-filters-btn');
    const closeBtn = document.getElementById('close-filters-btn');
    const applyBtn = document.getElementById('apply-filters-btn');
    const modal = document.getElementById('waiter-filters-modal');
    const overlay = modal?.querySelector('.waiter-filters-modal__overlay');

    openBtn?.addEventListener('click', () => {
      if (modal) modal.style.display = 'flex';
    });

    const closeModal = () => {
      if (modal) modal.style.display = 'none';
    };

    closeBtn?.addEventListener('click', closeModal);
    overlay?.addEventListener('click', closeModal);
    applyBtn?.addEventListener('click', closeModal);

    // Event listeners for checkboxes
    document.querySelectorAll('input[name="session-status"]').forEach((checkbox) => {
      checkbox.addEventListener('change', () => this.handleFilterChange());
    });

    document.querySelectorAll('input[name="workflow-status"]').forEach((checkbox) => {
      checkbox.addEventListener('change', () => this.handleFilterChange());
    });

    // Event listeners for order view filters
    document.getElementById('filter-my-orders')?.addEventListener('change', () => {
      this.handleFilterChange();
    });
    document.getElementById('filter-unassigned-orders')?.addEventListener('change', () => {
      this.handleFilterChange();
    });

    // Date range filters
    document.querySelectorAll<HTMLInputElement>('input[name="date-filter"]').forEach((radio) => {
      radio.addEventListener('change', () => {
        this.dateFilter = radio.value as any;
        this.handleFilterChange();
      });
    });

    const daysInput = document.getElementById('date-filter-days') as HTMLInputElement | null;
    if (daysInput) {
      daysInput.value = String(this.customDateDays);
      daysInput.addEventListener('change', () => {
        const val = Number(daysInput.value);
        if (Number.isFinite(val) && val > 0) {
          this.customDateDays = val;
          if (this.dateFilter === 'custom') {
            this.handleFilterChange();
          }
        }
      });
    }

    // Reset button
    document.getElementById('reset-filters')?.addEventListener('click', () => {
      this.resetFilters();
    });

    // Auto-save waiter notes on input with debounce
    document.addEventListener('input', (event) => {
      const target = event.target as HTMLElement;
      const textarea = target.closest<HTMLTextAreaElement>('textarea[data-order-note]');
      if (textarea) {
        this.scheduleNoteSave(textarea);
      }
    });

    this.initializeResendModal();
  }

  private initializeResendModal(): void {
    if (this.resendModalInitialized) return;
    if (!this.resendModal || !this.resendForm || !this.resendEmailInput) return;

    this.resendModalInitialized = true;

    const feedbackTarget = this.paidFeedbackEl || this.feedbackEl;

    this.closeResendBtn?.addEventListener('click', () => this.closeResendModal());
    this.cancelResendBtn?.addEventListener('click', () => this.closeResendModal());
    this.resendModal.addEventListener('click', (event) => {
      if (event.target === this.resendModal) this.closeResendModal();
    });

    this.resendForm.addEventListener('submit', (event) => {
      event.preventDefault();
      const sessionId = this.resendForm?.dataset.sessionId;
      const email = this.resendEmailInput?.value.trim();
      if (!sessionId || !email) {
        showFeedback(feedbackTarget, 'Ingresa un correo válido', true);
        return;
      }
      if (!isValidEmailFormat(email)) {
        showFeedback(feedbackTarget, 'Ingresa un correo válido', true);
        return;
      }
      void this.resendTicket(sessionId, email);
    });
  }

  private initializeViewToggle(): void {
    // Restore view preference from localStorage
    const savedView = localStorage.getItem('waiter_compact_view');
    this.isCompactView = savedView === 'true';

    const normalBtn = document.getElementById('waiter-view-normal');
    const compactBtn = document.getElementById('waiter-view-compact');

    // Apply saved view on load
    this.applyViewMode();

    normalBtn?.addEventListener('click', () => {
      this.isCompactView = false;
      localStorage.setItem('waiter_compact_view', 'false');
      this.applyViewMode();
    });

    compactBtn?.addEventListener('click', () => {
      this.isCompactView = true;
      localStorage.setItem('waiter_compact_view', 'true');
      this.applyViewMode();
    });
  }

  private applyViewMode(): void {
    const normalBtn = document.getElementById('waiter-view-normal');
    const compactBtn = document.getElementById('waiter-view-compact');

    // Get all order tables
    const ordersTable = document.querySelector('#waiter-orders')?.closest('table');
    const trackingTable = document.querySelector('#tracking-orders')?.closest('table');
    const paidTable = document.querySelector('#paid-sessions')?.closest('table');
    const trackingSection = document.querySelector('.tracking-section');

    if (this.isCompactView) {
      normalBtn?.classList.remove('active');
      compactBtn?.classList.add('active');

      ordersTable?.classList.add('compact-view');
      trackingTable?.classList.add('compact-view');
      paidTable?.classList.add('compact-view');
      trackingSection?.classList.add('compact-view');
    } else {
      normalBtn?.classList.add('active');
      compactBtn?.classList.remove('active');

      ordersTable?.classList.remove('compact-view');
      trackingTable?.classList.remove('compact-view');
      paidTable?.classList.remove('compact-view');
      trackingSection?.classList.remove('compact-view');
    }
  }

  private syncFilterCheckboxes(): void {
    document
      .querySelectorAll<HTMLInputElement>('input[name="session-status"]')
      .forEach((checkbox) => {
        checkbox.checked = this.sessionStatusFilters.has(checkbox.value);
      });

    document
      .querySelectorAll<HTMLInputElement>('input[name="workflow-status"]')
      .forEach((checkbox) => {
        checkbox.checked = this.workflowStatusFilters.has(checkbox.value);
      });

    // Date filter
    const dateRadios = document.querySelectorAll<HTMLInputElement>('input[name="date-filter"]');
    dateRadios.forEach((radio) => {
      radio.checked = radio.value === this.dateFilter;
    });
    const daysInput = document.getElementById('date-filter-days') as HTMLInputElement | null;
    if (daysInput) {
      daysInput.value = String(this.customDateDays);
    }

    // Sync order view checkboxes
    const myOrdersCheckbox = document.getElementById('filter-my-orders') as HTMLInputElement;
    if (myOrdersCheckbox) {
      myOrdersCheckbox.checked = this.showMyOrders;
    }

    const unassignedCheckbox = document.getElementById(
      'filter-unassigned-orders'
    ) as HTMLInputElement;
    if (unassignedCheckbox) {
      unassignedCheckbox.checked = this.showUnassignedOrders;
    }
  }

  private handleFilterChange(): void {
    // Update filter sets
    this.sessionStatusFilters.clear();
    document
      .querySelectorAll<HTMLInputElement>('input[name="session-status"]:checked')
      .forEach((checkbox) => {
        this.sessionStatusFilters.add(checkbox.value);
      });

    this.workflowStatusFilters.clear();
    document
      .querySelectorAll<HTMLInputElement>('input[name="workflow-status"]:checked')
      .forEach((checkbox) => {
        this.workflowStatusFilters.add(checkbox.value);
      });

    // Update order view filters
    const myOrdersCheckbox = document.getElementById('filter-my-orders') as HTMLInputElement;
    if (myOrdersCheckbox) {
      this.showMyOrders = myOrdersCheckbox.checked;
    }

    const unassignedCheckbox = document.getElementById(
      'filter-unassigned-orders'
    ) as HTMLInputElement;
    if (unassignedCheckbox) {
      this.showUnassignedOrders = unassignedCheckbox.checked;
    }

    // Save to localStorage
    localStorage.setItem('waiter_session_filters', JSON.stringify([...this.sessionStatusFilters]));
    localStorage.setItem(
      'waiter_workflow_filters',
      JSON.stringify([...this.workflowStatusFilters])
    );
    localStorage.setItem('waiter_show_my_orders', String(this.showMyOrders));
    localStorage.setItem('waiter_show_unassigned_orders', String(this.showUnassignedOrders));
    localStorage.setItem('waiter_date_filter', this.dateFilter);
    localStorage.setItem('waiter_date_days', String(this.customDateDays));

    // Apply filters
    this.applyFilters();
    this.renderTrackingOrders();
    this.renderCancelledOrders();
    if (this.activeTab === 'paid') {
      void this.loadPaidSessions();
    }
  }

  private resetFilters(): void {
    this.sessionStatusFilters = new Set([
      'open',
      'awaiting_tip',
      'awaiting_payment',
      'awaiting_payment_confirmation',
    ]);
    this.workflowStatusFilters = new Set(['new', 'queued', 'preparing', 'ready', 'delivered']);
    this.showMyOrders = true; // Reset to default
    this.showUnassignedOrders = true; // Reset to default
    this.dateFilter = 'today';
    this.customDateDays = 7;

    this.syncFilterCheckboxes();
    this.handleFilterChange();
  }

  private setupSearch(): void {
    if (!this.searchInput) return;

    this.searchInput.addEventListener('input', (e) => {
      this.searchTerm = (e.target as HTMLInputElement).value.toLowerCase().trim();
      this.applyFilters();
    });

    // Clear search on escape
    this.searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.searchInput!.value = '';
        this.searchTerm = '';
        this.applyFilters();
      }
    });
  }

  private matchesSearch(order: WaiterOrder): boolean {
    if (!this.searchTerm) return true;

    const searchLower = this.searchTerm;

    // Search by order ID
    if (order.id.toString().includes(searchLower)) return true;

    // Search by table number
    const tableNumber = order.session?.table_number || '';
    if (tableNumber.toLowerCase().includes(searchLower)) return true;

    // Search by customer name
    const customerName = order.customer?.name || '';
    if (customerName.toLowerCase().includes(searchLower)) return true;

    // Search by waiter notes
    if (order.waiter_notes && order.waiter_notes.toLowerCase().includes(searchLower)) return true;

    return false;
  }

  private isWithinDateFilter(dateStr?: string | null): boolean {
    if (this.dateFilter === 'all') return true;
    if (!dateStr) return true;
    const date = new Date(dateStr);
    if (Number.isNaN(date.getTime())) return true;

    const start = new Date();
    start.setHours(0, 0, 0, 0);

    const days =
      this.dateFilter === 'last7'
        ? 7
        : this.dateFilter === 'custom'
          ? Math.max(1, this.customDateDays || 1)
          : 1; // today

    if (this.dateFilter === 'today') {
      return date >= start;
    }

    const rangeStart = new Date(start);
    rangeStart.setDate(start.getDate() - (days - 1));
    return date >= rangeStart;
  }

  private applyFilters(): void {
    if (!this.ordersTable) return;

    // ordersTable IS the tbody element (#waiter-orders)
    const rows = this.ordersTable.querySelectorAll<HTMLTableRowElement>('tr[data-order-id]');
    let visibleCount = 0;

    // Keep the "no orders" empty state in sync with real rows (not filter visibility)
    const emptyRow = this.ordersTable.querySelector<HTMLTableRowElement>('tr.orders-empty-row');
    if (emptyRow) {
      emptyRow.style.display = rows.length === 0 ? '' : 'none';
    }

    // Get paid orders retention time from config (default 60 minutes)
    const paidRetentionMinutes = window.APP_DATA?.paid_orders_retention_minutes || 60;
    const paidRetentionMs = paidRetentionMinutes * 60 * 1000;
    const now = Date.now();

    rows.forEach((row) => {
      // Skip archived orders
      if (row.dataset.archived === 'true') {
        row.style.display = 'none';
        return;
      }

      const orderId = Number(row.dataset.orderId);
      const order = this.orders.get(orderId);
      if (!order) {
        row.style.display = 'none';
        return;
      }

      // Filter 1: Order view filters (my orders / unassigned)
      // If both filters are off, show all orders (including other waiters')
      // Otherwise, only show orders that match the enabled filters
      // Filter 1: Order view filters (my orders / unassigned)
      // If both filters are off, show all orders (including other waiters') - Wait, logic below says "if (!shouldShow)".
      // Actually, if both are off (false || false is false), the block is skipped?
      // Original code: if (this.showMyOrders || this.showUnassignedOrders) { ... }
      // If both off, it skips filtering by waiter? So shows ALL?
      // Yes, "If both filters are off, we don't filter by waiter (show all orders)".

      const isRequested = order.workflow_status === 'new';
      // Skip waiter filters when searching (user wants to find any order)
      // or when order is new (everyone should see new orders)
      const skipWaiterFilters = isRequested || Boolean(this.searchTerm);

      if (this.showMyOrders || this.showUnassignedOrders) {
        const isMyOrder = order.waiter_id === this.currentEmployeeId;
        const isUnassigned = !order.waiter_id;

        // Check if table is assigned to this waiter
        const tableManager = (window as any).tableAssignmentManager;
        const hasAssignedTables = tableManager && tableManager.getAssignedTables().length > 0;
        const isTableAssignedToMe =
          hasAssignedTables && order.session?.table_number
            ? tableManager.isTableAssigned(order.session.table_number)
            : false;

        // Check if order is locally tracked (starred)
        const trackedOrders = JSON.parse(localStorage.getItem('trackedOrders') || '[]');
        const isTracked = trackedOrders.includes(order.id);

        // Check if I have ANY other order from the same session (multi-order support)
        const hasOtherOrderInSession = order.session_id
          ? Array.from(this.orders.values()).some(
              (o) =>
                o.session_id === order.session_id &&
                o.id !== order.id &&
                o.waiter_id === this.currentEmployeeId
            )
          : false;

        let shouldShow = false;

        // 1. Show if explicitly assigned to me
        if (this.showMyOrders && isMyOrder) shouldShow = true;

        // 2. Show if it's from one of my assigned tables (even if unassigned)
        // We treat orders from "My Tables" as "My Orders" effectively
        if (this.showMyOrders && isTableAssignedToMe && isUnassigned) shouldShow = true;

        // 3. Handle unassigned orders from other tables
        if (this.showUnassignedOrders && isUnassigned) {
          // If I have assigned tables, I typically only want to see MY tables' unassigned orders.
          // But if I want to see ALL unassigned, I check the box.
          // However, user complaint "Delete Table 1" implies strictly filtering to my tables if I have them.

          if (hasAssignedTables) {
            // Strict mode: Only show unassigned if it's My Table
            if (isTableAssignedToMe) shouldShow = true;
          } else {
            // Open mode: Show all unassigned (no tables assigned to me)
            shouldShow = true;
          }
        }

        // 4. Always show tracked orders if either filter is active (or maybe regardless?)
        if (isTracked) shouldShow = true;

        // 5. Multi-order support: Show all orders from the same session if I have at least one order from that session
        if (this.showMyOrders && hasOtherOrderInSession) shouldShow = true;

        if (!shouldShow && !skipWaiterFilters) {
          row.style.display = 'none';
          return;
        }
      }
      // If both filters are off, we don't filter by waiter (show all orders)

      // Filter 2: Session status - NEVER show paid/paid in active tab
      const sessionStatus = order.session?.status || 'open';
      const isPaidStatus = sessionStatus === 'paid' || sessionStatus === 'paid';

      // Órdenes pagadas nunca se muestran en el tab de activas
      if (isPaidStatus) {
        row.style.display = 'none';
        return;
      }

      // Verificar que el estado de sesión esté en los filtros activos
      if (!this.sessionStatusFilters.has(sessionStatus)) {
        row.style.display = 'none';
        return;
      }

      // Filter 3: Workflow status
      if (!this.workflowStatusFilters.has(order.workflow_status)) {
        row.style.display = 'none';
        return;
      }

      // Filter 4: Date range
      const createdAt =
        row.dataset.createdAt || (order as any).created_at || (order as any).createdAt;
      if (!this.isWithinDateFilter(createdAt)) {
        row.style.display = 'none';
        return;
      }

      // Filter 5: Search term
      if (!this.matchesSearch(order)) {
        row.style.display = 'none';
        return;
      }

      // Show row
      row.style.display = '';
      visibleCount++;
    });

    // Update counter
    this.updateOrderCount(visibleCount);
    this.setTabBadge('active-count', visibleCount);

    // Update search counter
    if (this.searchCountEl) {
      if (this.searchTerm) {
        this.searchCountEl.textContent = `${visibleCount} resultado${visibleCount !== 1 ? 's' : ''}`;
        this.searchCountEl.style.display = '';
      } else {
        this.searchCountEl.style.display = 'none';
      }
    }

    // Mark filters as ready to show the table
    if (this.ordersTable) {
      this.ordersTable.classList.add('filters-ready');
      const tableWrapper = this.ordersTable.closest('.table-wrapper');
      if (tableWrapper) {
        tableWrapper.classList.add('filters-ready');
      }
    }
  }

  private updateOrderCount(count: number): void {
    const counter = document.querySelector('.waiter-orders-count');
    if (counter) {
      counter.textContent = `${count} orden${count !== 1 ? 'es' : ''}`;
    }
  }

  private refreshRowsForSession(sessionId: number): void {
    if (!this.ordersTable) return;
    this.ordersTable
      .querySelectorAll<HTMLTableRowElement>(`tr[data-session-id="${sessionId}"]`)
      .forEach((row) => {
        const orderId = Number(row.dataset.orderId);
        const order = this.orders.get(orderId);
        if (order) {
          this.renderRow(row, order);
        }
      });
    // Aplicar filtros para ocultar órdenes pagadas del tab de activas
    this.applyFilters();
  }

  private async loadPaidSessions(): Promise<void> {
    if (!this.paidSessionsTable) return;

    try {
      const response = await fetch('/api/sessions/paid-recent');
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        const msg =
          errorPayload?.message || errorPayload?.error || 'Error al cargar sesiones pagadas';
        throw new Error(msg);
      }

      const data = await response.json();
      const sessions = data.sessions || [];
      const sanitizedSessions = sessions.filter((session: any) => {
        const hasId = Number.isFinite(Number(session?.id));
        const hasTotal = typeof session?.total_amount !== 'undefined';
        session.customer_email = normalizeCustomerEmail(session?.customer_email);
        if (!hasId || !hasTotal) {
          console.warn('[WAITER] Sesión pagada ignorada por datos incompletos', session);
          return false;
        }
        return true;
      });

      const filteredSessions = sanitizedSessions.filter((session: any) =>
        this.isWithinDateFilter(session.closed_at || session.created_at)
      );

      if (filteredSessions.length === 0) {
        this.setTabBadge('paid-count', 0);
        this.paidSessionsTable.replaceChildren(
          createFragment(`
                    <tr class="tracking-empty-state">
                        <td colspan="8" style="text-align: center; padding: 2rem; color: #64748b;">
                            No hay sesiones pagadas en el rango seleccionado
                        </td>
                    </tr>
                `)
        );
        return;
      }

      this.setTabBadge('paid-count', filteredSessions.length);
      const paidHtml = filteredSessions
        .map((session: any) => {
          const timeAgo = session.closed_at ? getTimeAgo(new Date(session.closed_at)) : '-';
          const paymentMethod =
            session.payment_method === 'cash'
              ? 'Efectivo'
              : session.payment_method === 'card'
                ? 'Tarjeta'
                : session.payment_method === 'clip'
                  ? 'Terminal'
                  : session.payment_method || 'N/A';
          const total = Number(session.total_amount ?? 0);
          const totalDisplay = Number.isFinite(total) ? total.toFixed(2) : '0.00';
          const resendEmail = normalizeCustomerEmail(session.customer_email);
          const canResend = Boolean(resendEmail);
          const orderIds = Array.isArray(session.order_ids) ? session.order_ids : [];
          const ordersLabel = orderIds.length
            ? `Órdenes: ${orderIds.map((id: number) => `#${id}`).join(', ')}`
            : session.orders_count
              ? `Órdenes: ${session.orders_count}`
              : '';
          const sessionId = escapeHtml(String(session.id));
          let rawTableNumber = session.table_number || 'N/A';
          // Fix: Clean up duplicate prefixes (e.g., M-M01 -> M01) which causes "Mesa sin registro" error
          if (typeof rawTableNumber === 'string') {
            const duplicateMatch = rawTableNumber.match(/^([A-Z])-(\1\d+)$/);
            if (duplicateMatch) {
              rawTableNumber = duplicateMatch[2];
            }
          }
          const tableNumber = escapeHtml(rawTableNumber);
          const customerName = escapeHtml(session.customer_name || 'Cliente');
          const customerEmail = escapeHtml(resendEmail || '');
          const customerPhone = escapeHtml(session.customer_phone || '');
          const paymentMethodLabel = escapeHtml(paymentMethod);
          const ordersLabelHtml = ordersLabel
            ? `<div style="color:#64748b; font-size:0.8rem; margin-top:0.25rem;">${escapeHtml(ordersLabel)}</div>`
            : '';
          const totalValue = escapeHtml(String(total));

          return `
                    <tr>
                        <td>
                            <button type="button" class="order-id-link"
                                style="background: none; border: none; color: #3b82f6; font-weight: 600; cursor: pointer; text-decoration: underline; padding: 0;"
                                data-order-detail="${sessionId}"
                                data-table-number="${tableNumber}"
                                data-customer-name="${customerName}"
                                data-customer-email="${customerEmail}"
                                data-customer-phone="${customerPhone}"
                                data-status="paid" data-total="${totalValue}">
                                #${sessionId}
                            </button>
                            ${ordersLabelHtml}
                        </td>
                        <td>
                            <button type="button" class="table-number-link"
                                style="background: none; border: none; color: #ea580c; font-weight: 600; cursor: pointer; text-decoration: underline; padding: 0;"
                                data-table-info="${tableNumber}" data-table-number="${tableNumber}">
                                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" style="width: 16px; height: 16px;">
                                    <path d="M4 10h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                                    <path d="M6 10v10" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                                    <path d="M18 10v10" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                                    <path d="M8 6h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                                    <path d="M7 6V4h10v2" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                                </svg>
                                ${tableNumber}
                            </button>
                        </td>
                        <td>${customerName}</td>
                        <td>${escapeHtml(session.waiter_name || 'Sin asignar')}</td>
                        <td>$${totalDisplay}</td>
                        <td>${paymentMethodLabel}</td>
                        <td>${escapeHtml(timeAgo)}</td>
                        <td>
                            <div class="waiter-payment-group__actions" style="display:flex;gap:4px;">
                                <a href="/api/sessions/${sessionId}/ticket.pdf" target="_blank"
                                   class="btn btn--small btn--secondary" title="Descargar PDF">
                                    📄 PDF
                                </a>
                                <button type="button" class="btn btn--small btn--secondary"
                                        data-print-session="${sessionId}" title="Imprimir ticket">
                                    🖨️
                                </button>
                                <button type="button"
                                        class="btn btn--small btn--secondary ${canResend ? '' : 'btn--disabled'}"
                                        data-resend-session="${sessionId}"
                                        data-resend-email="${customerEmail}"
                                        ${canResend ? '' : 'disabled'}
                                        title="${canResend ? `Reenviar a ${customerEmail}` : 'Sin email registrado'}">
                                    ✉️
                                </button>
                            </div>
                        </td>
                    </tr>
            `;
        })
        .join('');

      this.paidSessionsTable.replaceChildren(createFragment(paidHtml));
    } catch (error) {
      console.error('[WAITER] Error loading paid sessions:', error);
      if (this.paidFeedbackEl) {
        this.paidFeedbackEl.textContent =
          (error as Error).message || 'Error al cargar sesiones pagadas';
        this.paidFeedbackEl.classList.add('error');
      }
    }

    // Attach print handlers
    this.paidSessionsTable
      ?.querySelectorAll<HTMLButtonElement>('button[data-print-session]')
      .forEach((btn) => {
        btn.addEventListener('click', () => {
          const sessionId = btn.dataset.printSession;
          if (!sessionId) return;
          void this.printPaidSession(Number(sessionId));
        });
      });

    // Attach resend handlers
    this.paidSessionsTable
      ?.querySelectorAll<HTMLButtonElement>('button[data-resend-session]')
      .forEach((btn) => {
        btn.addEventListener('click', () => {
          const sessionId = btn.dataset.resendSession;
          const email = normalizeCustomerEmail(btn.dataset.resendEmail);
          if (!sessionId) return;
          this.openResendModal(sessionId, email);
        });
      });
  }

  private openResendModal(sessionId: string, email: string): void {
    if (!this.resendModal || !this.resendForm || !this.resendEmailInput) {
      showFeedback(this.feedbackEl, 'No se puede abrir el formulario de reenvío', true);
      return;
    }
    const normalizedEmail = normalizeCustomerEmail(email);
    this.resendForm.dataset.sessionId = sessionId;
    this.resendEmailInput.value = normalizedEmail;
    this.resendEmailInput.readOnly = false;
    this.resendModal.classList.add('active');
    if (this.resendSessionLabel) this.resendSessionLabel.textContent = `#${sessionId}`;
    this.resendEmailInput.focus();
  }

  private closeResendModal(): void {
    if (!this.resendModal || !this.resendEmailInput || !this.resendForm) return;
    this.resendModal.classList.remove('active');
    this.resendEmailInput.value = '';
    delete this.resendForm.dataset.sessionId;
  }

  private async resendTicket(sessionId: string, email: string): Promise<void> {
    try {
      await requestJSON(`/api/sessions/${sessionId}/resend`, {
        method: 'POST',
        body: { email },
      });
      // Show toast notification for better visibility
      window.showToast?.(`Ticket reenviado exitosamente a ${email}`, 'success');
      notifyAction(this.feedbackEl, `Ticket reenviado a ${email}`);
      this.closeResendModal();
    } catch (error) {
      window.showToast?.((error as Error).message || 'Error al reenviar ticket', 'error');
      showFeedback(this.feedbackEl, (error as Error).message || 'Error al reenviar ticket', true);
    }
  }

  private updateRowAfterPayment(sessionId: number): void {
    // Find all rows that belong to this session and update their actions
    const rows = this.ordersTable?.querySelectorAll<HTMLTableRowElement>(
      `tr[data-session-id="${sessionId}"]`
    );

    rows?.forEach((row) => {
      const actionsCell = row.querySelector('.actions');
      if (actionsCell) {
        // Clear current actions and show "Pagado" with print and archive buttons
        const safeSessionId = escapeHtml(String(sessionId));
        actionsCell.replaceChildren(
          createFragment(`
                    <div class="waiter-payment-group">
                        <span class="badge badge--success">✅ Pagado</span>
                        <button type="button" class="btn btn--small btn--secondary"
                                data-session-action="ticket" data-session-id="${safeSessionId}">
                            🖨️ Imprimir
                        </button>
                        <button type="button" class="btn btn--small btn--secondary"
                                data-session-action="archive" data-session-id="${safeSessionId}"
                                title="Archivar orden">
                            📦 Archivar
                        </button>
                    </div>
                `)
        );
      }

      const statusEl = row.querySelector<HTMLElement>('.status');
      if (statusEl) {
        statusEl.textContent = 'Pagado';
        statusEl.className = 'status status--paid';
      }

      // Update the row's data attribute to reflect paid status and add payment timestamp
      row.dataset.sessionStatus = 'paid';
      row.dataset.paidAt = new Date().toISOString();
    });

    // Trigger update in paid sessions panel
    this.loadPaidSessions();
  }

  private async printPaidSession(sessionId: number): Promise<void> {
    // Open window BEFORE async fetch to prevent popup blocker
    const ticketWindow = window.open('', '_blank', 'width=420,height=700');

    if (!ticketWindow) {
      window.showToast?.('Por favor permite ventanas emergentes para imprimir el ticket', 'error');
      return;
    }

    // Show loading state in the opened window
    ticketWindow.document.write(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>Cargando ticket...</title>
                <meta charset="UTF-8">
                <style>
                    body {
                        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        height: 100vh;
                        margin: 0;
                        background: #f8fafc;
                    }
                    .loading { text-align: center; color: #64748b; }
                    .spinner {
                        border: 3px solid #e2e8f0;
                        border-top: 3px solid #1e3a5f;
                        border-radius: 50%;
                        width: 40px;
                        height: 40px;
                        animation: spin 1s linear infinite;
                        margin: 0 auto 16px;
                    }
                    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                </style>
            </head>
            <body>
                <div class="loading">
                    <div class="spinner"></div>
                    <p>Generando ticket...</p>
                </div>
            </body>
            </html>
        `);

    try {
      const response = await fetch(`/api/sessions/${sessionId}/ticket`, {
        headers: { Accept: 'application/json' },
      });

      const contentType = (response.headers.get('content-type') || '').toLowerCase();
      const isJSON = contentType.includes('application/json');

      const data = isJSON ? await response.json().catch(() => null) : null;

      if (!response.ok) {
        const message =
          (data && (data.error || data.message)) ||
          `No se pudo generar el ticket (HTTP ${response.status})`;
        throw new Error(message);
      }

      if (!data || typeof data.ticket !== 'string') {
        // Common cases: redirect to login/HTML error page/502 proxy page
        throw new Error(
          'Respuesta inválida del servidor al generar el ticket. Intenta recargar la página e iniciar sesión de nuevo.'
        );
      }
      if (ticketWindow) {
        const restaurantName = (window as any).APP_DATA?.restaurant_name || 'PRONTO CAFÉ';
        const now = new Date();
        const dateStr = now.toLocaleDateString('es-MX', {
          weekday: 'long',
          year: 'numeric',
          month: 'long',
          day: 'numeric',
        });
        const timeStr = now.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });

        const ticketHtml = `
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>Ticket #${sessionId}</title>
                        <meta charset="UTF-8">
                        <style>
                            * { margin: 0; padding: 0; box-sizing: border-box; }
                            body {
                                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
                                padding: 0;
                                max-width: 380px;
                                margin: 0 auto;
                                background: #f8fafc;
                            }
                            .ticket-container {
                                background: white;
                                margin: 20px;
                                border-radius: 12px;
                                box-shadow: 0 4px 20px rgba(0,0,0,0.1);
                                overflow: hidden;
                            }
                            .ticket-header {
                                background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
                                color: white;
                                padding: 24px 20px;
                                text-align: center;
                            }
                            .ticket-header h1 {
                                font-size: 1.5rem;
                                font-weight: 700;
                                margin-bottom: 4px;
                                letter-spacing: 1px;
                            }
                            .ticket-header .ticket-number {
                                font-size: 0.9rem;
                                opacity: 0.9;
                            }
                            .ticket-meta {
                                background: #f1f5f9;
                                padding: 12px 20px;
                                display: flex;
                                justify-content: space-between;
                                font-size: 0.8rem;
                                color: #64748b;
                                border-bottom: 1px solid #e2e8f0;
                            }
                            .ticket-body {
                                padding: 20px;
                            }
                            .ticket-footer {
                                text-align: center;
                                padding: 20px;
                                background: #f8fafc;
                                border-top: 2px dashed #e2e8f0;
                            }
                            .ticket-footer p {
                                font-size: 0.85rem;
                                color: #64748b;
                                margin-bottom: 4px;
                            }
                            .ticket-footer .thank-you {
                                font-size: 1rem;
                                font-weight: 600;
                                color: #1e293b;
                            }
                            .no-print {
                                padding: 16px 20px;
                                background: white;
                                border-bottom: 1px solid #e2e8f0;
                            }
                            .btn-group {
                                display: flex;
                                gap: 8px;
                            }
                            .btn {
                                flex: 1;
                                padding: 12px 16px;
                                border: none;
                                border-radius: 8px;
                                font-size: 0.9rem;
                                font-weight: 600;
                                cursor: pointer;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                gap: 6px;
                                transition: all 0.2s;
                            }
                            .btn-primary {
                                background: #1e3a5f;
                                color: white;
                            }
                            .btn-primary:hover { background: #2d5a87; }
                            .btn-secondary {
                                background: #e2e8f0;
                                color: #475569;
                            }
                            .btn-secondary:hover { background: #cbd5e1; }
                            .btn-download {
                                background: #059669;
                                color: white;
                            }
                            .btn-download:hover { background: #047857; }
                            @media print {
                                body { background: white; }
                                .no-print { display: none !important; }
                                .ticket-container {
                                    margin: 0;
                                    box-shadow: none;
                                    border-radius: 0;
                                }
                            }
                        </style>
                    </head>
                    <body>
                        <div class="no-print">
                            <div class="btn-group">
                                <button onclick="window.print()" class="btn btn-primary">🖨️ Imprimir</button>
                                <button onclick="downloadPDF()" class="btn btn-download">📥 PDF</button>
                                <button onclick="window.close()" class="btn btn-secondary">✕ Cerrar</button>
                            </div>
                        </div>
                        <div class="ticket-container" id="ticket-content">
                            <div class="ticket-header">
                                <h1>${restaurantName}</h1>
                                <div class="ticket-number">Ticket #${sessionId}</div>
                            </div>
                            <div class="ticket-meta">
                                <span>${dateStr}</span>
                                <span>${timeStr}</span>
                            </div>
                            <div class="ticket-body">
                                <div id="ticket-details">
                                    <pre style="white-space: pre-wrap; font-family: inherit; margin: 0; font-size: 0.85rem; line-height: 1.6;">${data.ticket}</pre>
                                </div>
                            </div>
                            <div class="ticket-footer">
                                <p class="thank-you">¡Gracias por su visita!</p>
                                <p>Vuelva pronto</p>
                            </div>
                        </div>
                        <script>
                            function downloadPDF() {
                                window.print();
                            }
                        </script>
                    </body>
                    </html>
                `;
        ticketWindow.document.write(ticketHtml);
        ticketWindow.document.close();
      } else {
        alert(data.ticket);
      }
    } catch (error) {
      const message = (error as Error).message || 'Error al imprimir ticket';
      // Close the opened window if there was an error
      if (ticketWindow && !ticketWindow.closed) {
        ticketWindow.close();
      }
      showFeedback(this.paidFeedbackEl || this.feedbackEl, message, true);
    }
  }

  public async refreshOrders(showLoading: boolean = false): Promise<void> {
    try {
      console.log('[WAITER] Refreshing orders from server...');
      const response = await fetch('/api/orders?include_closed=true&include_delivered=true', {
        showLoading,
      } as RequestInit);
      if (!response.ok) {
        throw new Error('Error al cargar órdenes');
      }

      const data = await response.json();
      const newOrders: WaiterOrder[] = data.orders || [];

      // Clear existing orders
      this.orders.clear();

      // Populate with new orders
      newOrders.forEach((order) => {
        const normalized = normalizeWorkflowStatus(
          order.workflow_status as string,
          order.workflow_status_legacy
        ) as WorkflowStatus;
        this.orders.set(order.id, {
          ...order,
          workflow_status: normalized,
          workflow_status_legacy: normalized,
        });
      });

      // Re-render the table
      this.renderExistingRows();
      this.sortOrders();
      this.applyFilters();
      this.updateTrackingBadge();
      this.renderCancelledOrders();
      this.pruneCancelledActiveRows();

      // Also refresh paid sessions if the user has permissions
      // if (this.capabilities.canViewPaid) {
      void this.loadPaidSessions();
      // }

      console.log('[WAITER] Orders refreshed successfully:', this.orders.size, 'orders');
      showFeedback(this.feedbackEl, 'Órdenes actualizadas');

      // Refresh assigned tables display after refreshing orders
      // This ensures the header shows all currently assigned tables
      const tableManager = (window as any).tableAssignmentManager;
      if (tableManager?.refreshAssignedTablesDisplay) {
        setTimeout(() => {
          tableManager.refreshAssignedTablesDisplay();
        }, 300);
      }
    } catch (error) {
      console.error('[WAITER] Error refreshing orders:', error);
      showFeedback(this.feedbackEl, 'Error al actualizar órdenes', true);
    }
  }

  private async refreshOrdersAndReload(): Promise<void> {
    try {
      console.log('[WAITER] Checking for new orders...');

      // Get existing order IDs from DOM
      const existingRows = this.ordersTable?.querySelectorAll('tr[data-order-id]');
      const existingOrderIds: number[] = [];
      existingRows?.forEach((row) => {
        const id = Number(row.getAttribute('data-order-id'));
        if (id) existingOrderIds.push(id);
      });

      // Fetch new order rows HTML from server
      const response = await fetch(
        '/api/orders/table-rows?include_closed=true&include_delivered=true',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ existing_order_ids: existingOrderIds }),
        }
      );

      if (!response.ok) {
        throw new Error('Error al cargar filas nuevas');
      }

      const data = await response.json();
      const newRowsHtml = data.html || '';
      const newOrderIds = data.new_order_ids || [];

      if (newOrderIds.length > 0) {
        console.log('[WAITER] New orders detected:', newOrderIds.length);

        // Insert new rows into the table
        const tbody = this.ordersTable?.querySelector('tbody');
        if (tbody && newRowsHtml) {
          // Create a temporary container to parse the HTML
          const temp = document.createElement('tbody');
          temp.appendChild(createFragment(newRowsHtml));

          // Append each new row to the actual tbody
          const newRows = temp.querySelectorAll('tr');
          newRows.forEach((row) => {
            tbody.appendChild(row);
          });

          console.log('[WAITER] Inserted', newRows.length, 'new rows');
        }

        // Now refresh all orders data to update the Map
        const ordersResponse = await fetch(
          '/api/orders?include_closed=true&include_delivered=true'
        );
        if (ordersResponse.ok) {
          const ordersData = await ordersResponse.json();
          const allOrders: WaiterOrder[] = ordersData.orders || [];

          // Clear and repopulate orders Map
          this.orders.clear();
          allOrders.forEach((order) => {
            const normalized = normalizeWorkflowStatus(
              order.workflow_status as string,
              order.workflow_status_legacy
            ) as WorkflowStatus;
            this.orders.set(order.id, {
              ...order,
              workflow_status: normalized,
              workflow_status_legacy: normalized,
            });
          });
        }

        // Re-attach event handlers to new rows
        this.attachEventHandlers();

        // Re-render all rows (including new ones) to update their content
        this.renderExistingRows();

        // Apply sorting and filtering
        this.sortOrders();
        this.applyFilters();
        this.updateTrackingBadge();
        this.renderCancelledOrders();

        showFeedback(this.feedbackEl, `${newOrderIds.length} nueva(s) orden(es) agregada(s)`);
      } else {
        console.log('[WAITER] No new orders, just updating existing rows');

        // Refresh orders data
        const ordersResponse = await fetch(
          '/api/orders?include_closed=true&include_delivered=true'
        );
        if (ordersResponse.ok) {
          const ordersData = await ordersResponse.json();
          const allOrders: WaiterOrder[] = ordersData.orders || [];

          this.orders.clear();
          allOrders.forEach((order) => this.orders.set(order.id, order));
        }

        // Re-render existing rows
        this.renderExistingRows();
        this.sortOrders();
        this.applyFilters();
        this.updateTrackingBadge();
        showFeedback(this.feedbackEl, 'Órdenes actualizadas');
      }
    } catch (error) {
      console.error('[WAITER] Error refreshing orders:', error);
      showFeedback(this.feedbackEl, 'Error al actualizar órdenes', true);
    }
  }

  private initializeOrdersPolling(): void {
    if (!this.ordersTable) {
      console.warn('[WAITER] Tabla de órdenes no encontrada, no se puede inicializar polling');
      return;
    }

    let lastOrderIds = new Set<number>();
    let lastOrderStatuses = new Map<number, WorkflowStatus>();

    // Initialize with current orders
    this.orders.forEach((order) => {
      lastOrderIds.add(order.id);
      if (order.workflow_status) {
        lastOrderStatuses.set(order.id, order.workflow_status);
      }
    });

    console.log('[WAITER] Iniciando polling HTTP cada', POLL_INTERVAL_MS / 1000, 'segundos');

    const pollForUpdates = async () => {
      try {
        // Para notificaciones de "nueva orden", solo consideramos órdenes activas.
        // Incluir entregadas/pagadas provoca falsos positivos (órdenes históricas).
        const response = await fetch('/api/orders');
        if (!response.ok) return;

        const data = await response.json();
        const newOrders: WaiterOrder[] = (data.orders || []).map((order: WaiterOrder) => {
          const normalized = normalizeWorkflowStatus(
            order.workflow_status,
            order.workflow_status_legacy
          );
          return {
            ...order,
            workflow_status: normalized as WorkflowStatus,
            workflow_status_legacy: normalized,
          };
        });
        const newOrderIds = new Set(newOrders.map((o) => o.id));
        const newOrderStatuses = new Map<number, WorkflowStatus>();
        newOrders.forEach((order) => {
          if (order.workflow_status) {
            newOrderStatuses.set(order.id, order.workflow_status);
          }
        });

        // Si el tablero inició sin órdenes cargadas, usar el primer poll como baseline
        // (evita notificar "nuevas" órdenes antiguas por desincronización inicial).
        if (lastOrderIds.size === 0 && this.orders.size === 0) {
          lastOrderIds = newOrderIds;
          lastOrderStatuses = newOrderStatuses;
          return;
        }

        // Check for new orders that weren't there before
        const addedOrders = newOrders
          .filter((o) => !lastOrderIds.has(o.id))
          .filter((o) => {
            const sessionStatus = o.session?.status || '';
            return (
              o.workflow_status === ('new' as WorkflowStatus) &&
              (sessionStatus === 'open' || CHECKOUT_SESSION_STATES.has(sessionStatus))
            );
          });

        let hasStatusChanges = false;
        newOrders.forEach((order) => {
          const previousStatus =
            lastOrderStatuses.get(order.id) || this.orders.get(order.id)?.workflow_status;
          if (previousStatus && previousStatus !== order.workflow_status) {
            hasStatusChanges = true;
          }
        });

        let hasRemovedOrders = false;
        lastOrderIds.forEach((id) => {
          if (!newOrderIds.has(id)) {
            hasRemovedOrders = true;
          }
        });

        if (addedOrders.length > 0) {
          console.log('[WAITER] Detectadas', addedOrders.length, 'nueva(s) orden(es)');
          this.soundManager.play();
          const tableNumbers = addedOrders.map((o) => o.session?.table_number || 'N/A').join(', ');
          const message =
            addedOrders.length === 1
              ? `🆕 Nueva orden - Mesa ${tableNumbers}`
              : `🆕 ${addedOrders.length} nuevas órdenes - Mesas: ${tableNumbers}`;
          showFeedback(this.feedbackEl, message);
          showNewOrderNotification(message, addedOrders.length);
          // Refresh orders without reloading the page (reduced delay for faster updates)
          setTimeout(() => {
            void this.refreshOrders();
          }, 200);
        } else if (hasStatusChanges || hasRemovedOrders) {
          console.log('[WAITER] Cambios detectados en órdenes, refrescando tablero');
          setTimeout(() => {
            void this.refreshOrders();
          }, 150);
        }

        lastOrderIds = newOrderIds;
        lastOrderStatuses = newOrderStatuses;
      } catch (error) {
        console.error('[WAITER] Error en polling:', error);
      }
    };

    // Start polling
    this.ordersPollingInterval = window.setInterval(
      pollForUpdates,
      POLL_INTERVAL_MS
    ) as unknown as number;
    // Initial poll after 2 seconds
    setTimeout(pollForUpdates, 2000);
  }

  // ==================== PARTIAL DELIVERY MODAL ====================

  private initializePartialDeliveryModal(): void {
    if (!this.partialDeliveryModal) {
      console.warn('[WAITER] Partial delivery modal not found in DOM');
      return;
    }

    // Close button handlers
    const closeBtn = this.partialDeliveryModal?.querySelector('.partial-delivery-close');
    const cancelBtn = this.partialDeliveryModal?.querySelector('#cancel-partial-delivery');
    const overlay = this.partialDeliveryModal?.querySelector('.partial-delivery-modal__overlay');

    closeBtn?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.closePartialDeliveryModal();
    });
    cancelBtn?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.closePartialDeliveryModal();
    });
    overlay?.addEventListener('click', (e) => {
      // Only close if clicking directly on overlay, not on its children
      if (e.target === overlay) {
        this.closePartialDeliveryModal();
      }
    });

    // Confirm button handler
    const confirmBtn = this.partialDeliveryModal?.querySelector('#confirm-partial-delivery');
    confirmBtn?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      void this.confirmPartialDelivery();
    });
  }

  // ==================== CANCEL ORDER MODAL ====================

  private initializeCancelOrderModal(): void {
    const modal = document.getElementById('cancel-order-modal');
    if (!modal) {
      console.warn('[WAITER] Cancel order modal not found in DOM');
      return;
    }

    // Close button handlers
    const closeBtn = modal.querySelector('.cancel-order-close');
    const cancelBtn = document.getElementById('cancel-order-modal-close');
    const overlay = modal.querySelector('.partial-delivery-modal__overlay');

    closeBtn?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.closeCancelOrderModal();
    });

    cancelBtn?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.closeCancelOrderModal();
    });

    overlay?.addEventListener('click', (e) => {
      if (e.target === overlay) {
        this.closeCancelOrderModal();
      }
    });

    // Confirm button handler
    const confirmBtn = document.getElementById('confirm-cancel-order');
    confirmBtn?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      void this.confirmCancelOrder();
    });

    // Expose openCancelOrderModal globally so it can be called from the order detail panel
    (window as any).openCancelOrderModal = (orderId: number) => {
      this.openCancelOrderModal(orderId);
    };
  }

  private async openPartialDeliveryModal(orderId: number): Promise<void> {
    this.partialDeliveryOrderId = orderId;
    this.partialDeliverySelectedItems.clear();

    // Fetch order details with items
    try {
      const response = await fetch(`/api/orders/${orderId}/delivery-status`);
      if (!response.ok) {
        throw new Error('No se pudo cargar el estado de entrega');
      }

      const data = await response.json();
      this.renderPartialDeliveryItems(data);

      // Show modal
      if (this.partialDeliveryModal) {
        this.partialDeliveryModal.style.display = 'flex';
        const orderNumber = this.partialDeliveryModal.querySelector(
          '#partial-delivery-order-number'
        );
        if (orderNumber) {
          orderNumber.textContent = String(orderId);
        }
      }
    } catch (error) {
      showFeedback(this.feedbackEl, (error as Error).message, true);
    }
  }

  private renderPartialDeliveryItems(data: any): void {
    const container = this.partialDeliveryModal?.querySelector('#partial-delivery-items');
    if (!container) return;

    const items = data.items || [];
    const deliveredCount = items.filter((item: any) => item.is_fully_delivered).length;
    const totalCount = items.length;

    const itemsHtml = items
      .map((item: any) => {
        const isDelivered = item.is_fully_delivered;
        const isSelected = this.partialDeliverySelectedItems.has(item.id);
        const checkboxDisabled = isDelivered;
        const checkboxChecked = isDelivered || isSelected;

        const itemClass = isDelivered
          ? 'partial-delivery-item--delivered'
          : isSelected
            ? 'partial-delivery-item--selected'
            : '';
        const itemId = escapeHtml(String(item.id));
        const itemName = escapeHtml(item.menu_item_name || '');
        const itemQuantity = escapeHtml(String(item.quantity));
        const deliveredAt = item.delivered_at
          ? escapeHtml(
              new Date(item.delivered_at).toLocaleString('es-MX', {
                day: '2-digit',
                month: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
              })
            )
          : '';

        return `
                <label class="partial-delivery-item ${itemClass}">
                    <input type="checkbox"
                        class="partial-delivery-checkbox"
                        data-item-id="${itemId}"
                        ${checkboxChecked ? 'checked' : ''}
                        ${checkboxDisabled ? 'disabled' : ''}
                        ${isDelivered ? 'data-delivered="true"' : ''}>
                    <div class="partial-delivery-item__content">
                        <div class="partial-delivery-item__header">
                            <span class="partial-delivery-item__name">${itemName}</span>
                            <span class="partial-delivery-item__badge ${isDelivered ? 'badge--success' : 'badge--secondary'}">
                                ${isDelivered ? '✅ Entregado' : `${itemQuantity} unid.`}
                            </span>
                        </div>
                        ${
                          isDelivered
                            ? `
                            <div class="partial-delivery-item__info">
                                Entregado el ${deliveredAt}
                            </div>
                        `
                            : ''
                        }
                    </div>
                </label>
            `;
      })
      .join('');

    container.replaceChildren(createFragment(itemsHtml));

    // Add event listeners to checkboxes
    container
      .querySelectorAll<HTMLInputElement>('.partial-delivery-checkbox')
      .forEach((checkbox) => {
        checkbox.addEventListener('change', (event) => {
          const target = event.target as HTMLInputElement;
          const itemId = Number(target.dataset.itemId);
          const isDelivered = target.dataset.delivered === 'true';

          if (isDelivered) return; // Ignore delivered items

          if (target.checked) {
            this.partialDeliverySelectedItems.add(itemId);
          } else {
            this.partialDeliverySelectedItems.delete(itemId);
          }

          this.updatePartialDeliveryProgress(data);
        });
      });

    this.updatePartialDeliveryProgress(data);
  }

  private updatePartialDeliveryProgress(data: any): void {
    const progressContainer = this.partialDeliveryModal?.querySelector(
      '#partial-delivery-progress'
    );
    if (!progressContainer) return;

    const items = data.items || [];
    const deliveredCount = items.filter((item: any) => item.is_fully_delivered).length;
    const selectedCount = this.partialDeliverySelectedItems.size;
    const totalCount = items.length;
    const futureDeliveredCount = deliveredCount + selectedCount;

    const percentage = totalCount > 0 ? (futureDeliveredCount / totalCount) * 100 : 0;
    const selectedLabel =
      selectedCount > 0
        ? `Entregando ${selectedCount} item${selectedCount !== 1 ? 's' : ''} • `
        : '';
    progressContainer.replaceChildren(
      createFragment(`
            <div class="partial-delivery-progress__bar">
                <div class="partial-delivery-progress__fill"
                    style="width: ${escapeHtml(String(percentage))}%">
                </div>
            </div>
            <div class="partial-delivery-progress__text">
                ${escapeHtml(selectedLabel)}
                ${escapeHtml(String(futureDeliveredCount))} de ${escapeHtml(String(totalCount))} item${totalCount !== 1 ? 's' : ''} entregado${futureDeliveredCount !== 1 ? 's' : ''}
            </div>
        `)
    );
  }

  private async confirmPartialDelivery(): Promise<void> {
    if (!this.partialDeliveryOrderId) return;

    if (this.partialDeliverySelectedItems.size === 0) {
      showFeedback(this.feedbackEl, 'Debes seleccionar al menos un item para entregar', true);
      return;
    }

    const itemIds = Array.from(this.partialDeliverySelectedItems);
    const employeeId = this.currentEmployeeId;

    if (!employeeId) {
      showFeedback(this.feedbackEl, 'Error: No hay empleado activo', true);
      return;
    }

    try {
      showFeedback(this.feedbackEl, 'Entregando items...');

      const response = await fetch(`/api/orders/${this.partialDeliveryOrderId}/deliver-items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          item_ids: itemIds,
          employee_id: employeeId,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || 'Error al entregar items');
      }

      const data = await response.json();
      const normalizedStatus = normalizeWorkflowStatus(
        data.workflow_status,
        data.workflow_status_legacy
      );
      const normalizedOrder = {
        ...data,
        workflow_status: normalizedStatus,
        workflow_status_legacy: normalizedStatus,
      } as WaiterOrder;
      const allDelivered =
        normalizedOrder.items?.every((item: any) => item.is_fully_delivered) || false;

      showFeedback(
        this.feedbackEl,
        allDelivered
          ? '✅ Todos los items entregados - Orden completada'
          : `✅ ${itemIds.length} item${itemIds.length !== 1 ? 's' : ''} entregado${itemIds.length !== 1 ? 's' : ''}`
      );

      // Update local order data
      this.orders.set(this.partialDeliveryOrderId, normalizedOrder);

      // Close modal
      this.closePartialDeliveryModal();

      // If all items are delivered, automatically mark the order as delivered
      if (allDelivered && normalizedStatus === 'ready') {
        try {
          const deliverResponse = await requestJSON(
            `/api/orders/${this.partialDeliveryOrderId}/deliver`,
            {
              method: 'POST',
              body: { employee_id: employeeId },
            }
          );
          const deliverResponseData = deliverResponse as any;
          const deliverNormalizedStatus = normalizeWorkflowStatus(
            deliverResponseData.workflow_status,
            deliverResponseData.workflow_status_legacy
          );
          const deliverNormalizedOrder = {
            ...deliverResponseData,
            workflow_status: deliverNormalizedStatus,
            workflow_status_legacy: deliverNormalizedStatus,
          } as WaiterOrder;
          this.orders.set(this.partialDeliveryOrderId, deliverNormalizedOrder);
          showFeedback(this.feedbackEl, '✅ Orden marcada como entregada automáticamente');

          // Refresh the row with the new delivered status
          const row = this.ordersTable?.querySelector(
            `tr[data-order-id="${this.partialDeliveryOrderId}"]`
          ) as HTMLTableRowElement;
          if (row) {
            this.renderRow(row, deliverNormalizedOrder);
          }
        } catch (error) {
          console.error('Error auto-delivering order:', error);
          // Still refresh the row with partial delivery data
          const row = this.ordersTable?.querySelector(
            `tr[data-order-id="${this.partialDeliveryOrderId}"]`
          ) as HTMLTableRowElement;
          if (row) {
            this.renderRow(row, data);
          }
        }
      } else {
        // Refresh the row with partial delivery data
        const row = this.ordersTable?.querySelector(
          `tr[data-order-id="${this.partialDeliveryOrderId}"]`
        ) as HTMLTableRowElement;
        if (row) {
          this.renderRow(row, data);
        }
      }

      // Trigger event
      document.dispatchEvent(new CustomEvent('orders:changed'));
    } catch (error) {
      showFeedback(this.feedbackEl, (error as Error).message, true);
    }
  }

  private closePartialDeliveryModal(): void {
    if (this.partialDeliveryModal) {
      this.partialDeliveryModal.style.display = 'none';
    }
    this.partialDeliveryOrderId = null;
    this.partialDeliverySelectedItems.clear();
  }
}

const LEGACY_TO_CANONICAL: Record<string, WorkflowStatus> = {
  requested: 'new',
  waiter_accepted: 'queued',
  kitchen_in_progress: 'preparing',
  ready_for_delivery: 'ready',
  wait_for_payment: 'awaiting_payment',
  payed: 'paid',
  delivered: 'delivered',
  cancelled: 'cancelled',
};

const normalizeWorkflowStatus = (status: string, legacy?: string): WorkflowStatus => {
  if (legacy && legacy in LEGACY_TO_CANONICAL) {
    return LEGACY_TO_CANONICAL[legacy];
  }
  if (status in LEGACY_TO_CANONICAL) {
    return LEGACY_TO_CANONICAL[status];
  }
  return status as WorkflowStatus;
};

const createFragment = (html: string): DocumentFragment =>
  document.createRange().createContextualFragment(html);

const escapeHtml = (value: string): string => {
  const div = document.createElement('div');
  div.textContent = value;
  return div.innerHTML;
};

// Expose printPaidSession to window for onclick handlers
declare global {
  interface Window {
    WaiterPanel?: {
      confirmWaiterCall: (callId: number) => void;
      toggleNotificationsPanel: () => void;
      getPendingCalls: () => any[];
      printPaidSession?: (sessionId: number) => void;
    };
  }
}
