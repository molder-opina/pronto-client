import { normalizeCustomerEmail } from './email-utils';

declare var window: Window &
  typeof globalThis & {
    CASHIER_ORDERS_DATA: any;
    APP_DATA: any;
    refreshCashierOrders?: () => Promise<void>;
    EmployeePayments?: {
      openModal?: (sessionId: number, method?: string) => void;
    };
    openEmployeePaymentModal?: (sessionId: string | number, method: string) => void;
  };

type LegacyWorkflowStatus =
  | 'requested'
  | 'waiter_accepted'
  | 'kitchen_in_progress'
  | 'ready_for_delivery'
  | 'delivered'
  | 'cancelled'
  | 'wait_for_payment'
  | 'payed';

type CanonicalWorkflowStatus =
  | 'new'
  | 'queued'
  | 'preparing'
  | 'ready'
  | 'delivered'
  | 'awaiting_payment'
  | 'paid'
  | 'cancelled';

type WorkflowStatus = LegacyWorkflowStatus | CanonicalWorkflowStatus;
type SessionStatus =
  | 'awaiting_tip'
  | 'awaiting_payment'
  | 'awaiting_payment_confirmation'
  | 'closed'
  | 'paid'
  | string;

interface OrderInfo {
  id: number;
  session_id: number;
  workflow_status: WorkflowStatus;
  workflow_status_legacy?: LegacyWorkflowStatus;
  created_at?: string;
  session?: {
    table_number?: string | null;
    notes?: string | null;
    status?: SessionStatus;
    opened_at?: string;
    closed_at?: string | null;
  };
  customer?: {
    id?: number;
    name?: string | null;
    email?: string | null;
    phone?: string | null;
  };
  waiter_id?: number | null;
  waiter_name?: string | null;
  total_amount?: number;
}

interface ClosedSession {
  id: number;
  table_number?: string | null;
  customer_name?: string | null;
  customer_email?: string | null;
  customer_phone?: string | null;
  total_amount?: number;
  orders_count?: number;
  order_ids?: number[];
  payment_method?: string | null;
  closed_at?: string | null;
}

const PAYMENT_PENDING_STATUSES = new Set<SessionStatus>([
  'awaiting_tip',
  'awaiting_payment',
  'awaiting_payment_confirmation',
]);

const CANONICAL_TO_LEGACY: Record<CanonicalWorkflowStatus, LegacyWorkflowStatus> = {
  new: 'requested',
  queued: 'waiter_accepted',
  preparing: 'kitchen_in_progress',
  ready: 'ready_for_delivery',
  awaiting_payment: 'wait_for_payment',
  paid: 'payed',
  delivered: 'delivered',
  cancelled: 'cancelled',
};

const normalizeWorkflowStatus = (
  status: WorkflowStatus,
  legacy?: LegacyWorkflowStatus
): LegacyWorkflowStatus => {
  if (legacy) return legacy;
  if (status in CANONICAL_TO_LEGACY) {
    return CANONICAL_TO_LEGACY[status as CanonicalWorkflowStatus];
  }
  return status as LegacyWorkflowStatus;
};

class CashierBoard {
  private root: HTMLElement;
  private ordersTable: HTMLTableSectionElement | null;
  private trackingOrdersTable: HTMLTableSectionElement | null;
  private paidSessionsTable: HTMLTableSectionElement | null;
  private cancelledOrdersTable: HTMLTableSectionElement | null;
  private feedback: HTMLElement | null;
  private paidFeedback: HTMLElement | null;
  private searchInput: HTMLInputElement | null;
  private searchCount: HTMLElement | null;

  private activeTab: 'active' | 'tracking' | 'paid' | 'cancelled' = 'active';
  private starredOrders: Set<number> = new Set();

  private sessionStatusFilters: Set<string> = new Set([
    'awaiting_tip',
    'awaiting_payment',
    'awaiting_payment_confirmation',
  ]);
  private workflowStatusFilters: Set<string> = new Set(['delivered']);
  private dateFilter: 'today' | 'last7' | 'custom' | 'all' = 'today';
  private customDateDays: number = 7;
  private searchTerm: string = '';
  private isCompactView: boolean = false;

  private paidSessionsInterval?: number;

  constructor(root: HTMLElement) {
    this.root = root;
    this.ordersTable = root.querySelector<HTMLTableSectionElement>('#cashier-orders');
    this.trackingOrdersTable = root.querySelector<HTMLTableSectionElement>(
      '#cashier-tracking-orders'
    );
    this.paidSessionsTable = root.querySelector<HTMLTableSectionElement>('#cashier-paid-sessions');
    this.cancelledOrdersTable = root.querySelector<HTMLTableSectionElement>(
      '#cashier-cancelled-orders'
    );
    this.feedback = root.querySelector<HTMLElement>('#cashier-feedback');
    this.paidFeedback = root.querySelector<HTMLElement>('#cashier-paid-feedback');
    this.searchInput = root.querySelector<HTMLInputElement>('#cashier-search-input');
    this.searchCount = root.querySelector<HTMLElement>('#cashier-search-count');
  }

  initialize(): void {
    if (!this.ordersTable) {
      console.warn('[CASHIER] Tabla de órdenes no encontrada');
      return;
    }

    this.loadStarredOrders();
    this.initializeTabs();
    this.initializeFilters();
    this.initializeSearch();
    this.initializeStarButtons();
    this.initializeViewToggle();
    this.initializeOrderActions();

    const ordersData: OrderInfo[] = Array.isArray(window.CASHIER_ORDERS_DATA)
      ? window.CASHIER_ORDERS_DATA.map((order: OrderInfo) => {
          const normalizedStatus = normalizeWorkflowStatus(
            order.workflow_status,
            order.workflow_status_legacy
          );
          return {
            ...order,
            workflow_status: normalizedStatus,
            workflow_status_legacy: normalizedStatus,
          };
        })
      : [];
    this.ordersTable.querySelectorAll<HTMLTableRowElement>('tr[data-order-id]').forEach((row) => {
      const id = Number(row.dataset.orderId);
      const order = ordersData.find((o) => o.id === id);
      if (order) {
        this.renderRowActions(row, order);
      }
    });

    this.updateStarButtonStates();
    this.updateTrackingBadge();
    this.applyFilters();

    window.refreshCashierOrders = async () => {
      await this.refreshOrders();
    };
  }

  private initializeTabs(): void {
    const tabs = this.root.querySelectorAll<HTMLButtonElement>('.waiter-tab[data-tab]');
    tabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        const tabType = tab.dataset.tab as 'active' | 'tracking' | 'paid' | 'cancelled';
        this.switchTab(tabType);
      });
    });
    this.switchTab('active');
  }

  private switchTab(tab: 'active' | 'tracking' | 'paid' | 'cancelled'): void {
    this.activeTab = tab;

    this.root.querySelectorAll('.waiter-tab').forEach((t) => {
      t.classList.toggle('active', t.getAttribute('data-tab') === tab);
    });

    const activeSection = this.root.querySelector<HTMLElement>('#cashier-active-orders-section');
    const trackingSection = this.root.querySelector<HTMLElement>(
      '#cashier-tracking-orders-section'
    );
    const paidSection = this.root.querySelector<HTMLElement>('#cashier-paid-orders-section');
    const cancelledSection = this.root.querySelector<HTMLElement>(
      '#cashier-cancelled-orders-section'
    );

    if (activeSection) activeSection.style.display = tab === 'active' ? 'block' : 'none';
    if (trackingSection) trackingSection.style.display = tab === 'tracking' ? 'block' : 'none';
    if (paidSection) paidSection.style.display = tab === 'paid' ? 'block' : 'none';
    if (cancelledSection) cancelledSection.style.display = tab === 'cancelled' ? 'block' : 'none';

    if (tab === 'tracking') {
      this.renderTrackingOrders();
    }

    if (tab === 'paid') {
      void this.loadPaidSessions();
      if (!this.paidSessionsInterval) {
        this.paidSessionsInterval = window.setInterval(() => this.loadPaidSessions(), 30000);
      }
    } else if (tab === 'cancelled') {
      this.renderCancelledOrders();
    } else {
      if (this.paidSessionsInterval) {
        window.clearInterval(this.paidSessionsInterval);
        this.paidSessionsInterval = undefined;
      }
    }
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
    this.applyFilters();

    if (this.activeTab === 'tracking') {
      this.renderTrackingOrders();
    }
  }

  private loadStarredOrders(): void {
    try {
      const stored = localStorage.getItem('cashier_starred_orders');
      if (stored) {
        const ids = JSON.parse(stored) as number[];
        this.starredOrders = new Set(ids);
      }
    } catch (error) {
      console.error('[CASHIER] Error loading starred orders:', error);
    }
  }

  private saveStarredOrders(): void {
    try {
      const ids = Array.from(this.starredOrders);
      localStorage.setItem('cashier_starred_orders', JSON.stringify(ids));
    } catch (error) {
      console.error('[CASHIER] Error saving starred orders:', error);
    }
  }

  private updateStarButtonStates(): void {
    this.ordersTable?.querySelectorAll<HTMLButtonElement>('.star-btn').forEach((btn) => {
      const orderId = Number(btn.dataset.orderId);
      const isStarred = this.starredOrders.has(orderId);
      const icon = btn.querySelector('.star-icon');
      if (icon) {
        icon.textContent = isStarred ? '★' : '☆';
        btn.classList.toggle('starred', isStarred);
      }
    });
  }

  private updateTrackingBadge(): void {
    const badge = this.root.querySelector<HTMLElement>('#cashier-tracking-count');
    if (badge) {
      const count = this.starredOrders.size;
      badge.textContent = String(count);
      badge.classList.toggle('is-hidden', count === 0);
    }
  }

  private sortOrders(): void {
    if (!this.ordersTable) return;
    const rows = Array.from(
      this.ordersTable.querySelectorAll<HTMLTableRowElement>('tr[data-order-id]')
    );

    rows.sort((a, b) => {
      const aId = Number(a.dataset.orderId);
      const bId = Number(b.dataset.orderId);
      const aStarred = this.starredOrders.has(aId);
      const bStarred = this.starredOrders.has(bId);

      if (aStarred && !bStarred) return -1;
      if (!aStarred && bStarred) return 1;
      return bId - aId;
    });

    rows.forEach((row) => this.ordersTable!.appendChild(row));
  }

  private renderTrackingOrders(): void {
    if (!this.trackingOrdersTable || !this.ordersTable) return;

    const allRows = this.ordersTable.querySelectorAll<HTMLTableRowElement>('tr[data-order-id]');
    const starredRows: HTMLTableRowElement[] = [];

    allRows.forEach((row) => {
      const orderId = Number(row.dataset.orderId);
      if (this.starredOrders.has(orderId)) {
        const clone = row.cloneNode(true) as HTMLTableRowElement;
        starredRows.push(clone);
      }
    });

    this.trackingOrdersTable.replaceChildren();

    if (starredRows.length === 0) {
      this.trackingOrdersTable.replaceChildren(
        createFragment(`
                <tr class="tracking-empty-state">
                    <td colspan="8" style="text-align: center; padding: 2rem; color: #64748b;">
                        Haz clic en la ⭐ estrella de una orden para agregarla a seguimiento.
                    </td>
                </tr>
            `)
      );
    } else {
      starredRows.forEach((row) => {
        this.trackingOrdersTable!.appendChild(row);
        const orderId = Number(row.dataset.orderId);
        const ordersData: OrderInfo[] = Array.isArray(window.CASHIER_ORDERS_DATA)
          ? window.CASHIER_ORDERS_DATA.map((order: OrderInfo) => {
              const normalizedStatus = normalizeWorkflowStatus(
                order.workflow_status,
                order.workflow_status_legacy
              );
              return {
                ...order,
                workflow_status: normalizedStatus,
                workflow_status_legacy: normalizedStatus,
              };
            })
          : [];
        const order = ordersData.find((o) => o.id === orderId);
        if (order) {
          this.renderRowActions(row, order);
        }
      });
    }

    this.trackingOrdersTable.addEventListener('click', (event) => {
      const target = event.target as HTMLElement;
      const starBtn = target.closest<HTMLButtonElement>('.star-btn');
      if (starBtn) {
        const orderId = Number(starBtn.dataset.orderId);
        this.toggleStar(orderId);
      }

      const paymentBtn = target.closest<HTMLButtonElement>('[data-open-payment-modal]');
      if (paymentBtn) {
        void this.handlePaymentButton(paymentBtn);
      }
    });
  }

  private initializeFilters(): void {
    const savedSessionFilters = localStorage.getItem('cashier_session_filters');
    const savedWorkflowFilters = localStorage.getItem('cashier_workflow_filters');
    const savedDateFilter = localStorage.getItem('cashier_date_filter');
    const savedDateDays = localStorage.getItem('cashier_date_days');

    if (savedSessionFilters) {
      this.sessionStatusFilters = new Set(JSON.parse(savedSessionFilters));
    }
    if (savedWorkflowFilters) {
      this.workflowStatusFilters = new Set(JSON.parse(savedWorkflowFilters));
    }
    if (savedDateFilter && ['today', 'last7', 'custom', 'all'].includes(savedDateFilter)) {
      this.dateFilter = savedDateFilter as any;
    }
    if (savedDateDays) {
      const n = Number(savedDateDays);
      if (Number.isFinite(n) && n > 0) {
        this.customDateDays = n;
      }
    }

    this.syncFilterCheckboxes();

    const openBtn = this.root.querySelector<HTMLButtonElement>('#cashier-open-filters-btn');
    const closeBtn = this.root.querySelector<HTMLButtonElement>('#cashier-close-filters-btn');
    const applyBtn = this.root.querySelector<HTMLButtonElement>('#cashier-apply-filters-btn');
    const modal = this.root.querySelector<HTMLElement>('#cashier-filters-modal');
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

    this.root.querySelectorAll('input[name="cashier-session-status"]').forEach((checkbox) => {
      checkbox.addEventListener('change', () => this.handleFilterChange());
    });

    this.root.querySelectorAll('input[name="cashier-workflow-status"]').forEach((checkbox) => {
      checkbox.addEventListener('change', () => this.handleFilterChange());
    });

    this.root
      .querySelectorAll<HTMLInputElement>('input[name="cashier-date-filter"]')
      .forEach((radio) => {
        radio.addEventListener('change', () => {
          this.dateFilter = radio.value as any;
          this.handleFilterChange();
        });
      });

    const daysInput = this.root.querySelector<HTMLInputElement>('#cashier-date-filter-days');
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

    this.root.querySelector('#cashier-reset-filters')?.addEventListener('click', () => {
      this.resetFilters();
    });
  }

  private syncFilterCheckboxes(): void {
    this.root
      .querySelectorAll<HTMLInputElement>('input[name="cashier-session-status"]')
      .forEach((checkbox) => {
        checkbox.checked = this.sessionStatusFilters.has(checkbox.value);
      });

    this.root
      .querySelectorAll<HTMLInputElement>('input[name="cashier-workflow-status"]')
      .forEach((checkbox) => {
        checkbox.checked = this.workflowStatusFilters.has(checkbox.value);
      });

    this.root
      .querySelectorAll<HTMLInputElement>('input[name="cashier-date-filter"]')
      .forEach((radio) => {
        radio.checked = radio.value === this.dateFilter;
      });
  }

  private handleFilterChange(): void {
    this.sessionStatusFilters.clear();
    this.root
      .querySelectorAll<HTMLInputElement>('input[name="cashier-session-status"]:checked')
      .forEach((checkbox) => {
        this.sessionStatusFilters.add(checkbox.value);
      });

    this.workflowStatusFilters.clear();
    this.root
      .querySelectorAll<HTMLInputElement>('input[name="cashier-workflow-status"]:checked')
      .forEach((checkbox) => {
        this.workflowStatusFilters.add(checkbox.value);
      });

    localStorage.setItem(
      'cashier_session_filters',
      JSON.stringify(Array.from(this.sessionStatusFilters))
    );
    localStorage.setItem(
      'cashier_workflow_filters',
      JSON.stringify(Array.from(this.workflowStatusFilters))
    );
    localStorage.setItem('cashier_date_filter', this.dateFilter);
    localStorage.setItem('cashier_date_days', String(this.customDateDays));

    this.applyFilters();
  }

  private resetFilters(): void {
    this.sessionStatusFilters = new Set([
      'awaiting_tip',
      'awaiting_payment',
      'awaiting_payment_confirmation',
    ]);
    this.workflowStatusFilters = new Set(['delivered']);
    this.dateFilter = 'today';
    this.customDateDays = 7;

    this.syncFilterCheckboxes();
    this.handleFilterChange();
  }

  private initializeSearch(): void {
    this.searchInput?.addEventListener('input', () => {
      this.searchTerm = (this.searchInput?.value || '').trim().toLowerCase();
      this.applyFilters();
    });

    this.searchInput?.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && this.searchInput) {
        this.searchInput.value = '';
        this.searchTerm = '';
        this.applyFilters();
      }
    });
  }

  private applyFilters(): void {
    if (!this.ordersTable) return;

    let visible = 0;
    const rows = Array.from(
      this.ordersTable.querySelectorAll<HTMLTableRowElement>('tr[data-order-id]')
    );

    rows.forEach((row) => {
      const status = row.dataset.status || '';
      const sessionStatus = row.dataset.sessionStatus || '';
      const createdAt = row.dataset.createdAt || '';

      const matchesWorkflow = this.workflowStatusFilters.has(status);
      const matchesSession =
        this.sessionStatusFilters.has(sessionStatus) && PAYMENT_PENDING_STATUSES.has(sessionStatus);

      let matchesDate = true;
      if (this.dateFilter !== 'all' && createdAt) {
        const orderDate = new Date(createdAt);
        const now = new Date();
        const diffDays = Math.floor((now.getTime() - orderDate.getTime()) / (1000 * 60 * 60 * 24));

        if (this.dateFilter === 'today') {
          matchesDate = diffDays === 0;
        } else if (this.dateFilter === 'last7') {
          matchesDate = diffDays <= 7;
        } else if (this.dateFilter === 'custom') {
          matchesDate = diffDays <= this.customDateDays;
        }
      }

      const haystack = [
        row.dataset.orderId || '',
        row.dataset.tableNumber || '',
        row.dataset.customerName || '',
        row.dataset.notes || '',
        row.textContent || '',
      ]
        .join(' ')
        .toLowerCase();
      const matchesSearch = !this.searchTerm || haystack.includes(this.searchTerm);

      const show = matchesWorkflow && matchesSession && matchesDate && matchesSearch;
      row.style.display = show ? '' : 'none';
      if (show) visible += 1;
    });

    const emptyRow = this.ordersTable.querySelector<HTMLTableRowElement>(
      'tr.orders-filter-empty[data-filter-empty-for="cashier"]'
    );
    if (emptyRow) {
      emptyRow.style.display = rows.length > 0 && visible === 0 ? '' : 'none';
    }

    if (this.searchCount) {
      if (this.searchTerm) {
        this.searchCount.textContent = `${visible}`;
        this.searchCount.style.display = '';
      } else {
        this.searchCount.style.display = 'none';
      }
    }

    const ordersCount = this.root.querySelector<HTMLElement>('#cashier-orders-count');
    if (ordersCount) {
      ordersCount.textContent = `${visible} órdenes`;
    }

    const activeBadge = this.root.querySelector<HTMLElement>('#cashier-active-count');
    if (activeBadge) {
      activeBadge.textContent = String(visible);
      activeBadge.classList.toggle('is-hidden', visible === 0);
    }
  }

  private initializeViewToggle(): void {
    const savedView = localStorage.getItem('cashier_compact_view');
    this.isCompactView = savedView === 'true';

    const normalBtn = this.root.querySelector<HTMLButtonElement>('#cashier-view-normal');
    const compactBtn = this.root.querySelector<HTMLButtonElement>('#cashier-view-compact');

    this.applyViewMode();

    normalBtn?.addEventListener('click', () => {
      this.isCompactView = false;
      localStorage.setItem('cashier_compact_view', 'false');
      this.applyViewMode();
    });

    compactBtn?.addEventListener('click', () => {
      this.isCompactView = true;
      localStorage.setItem('cashier_compact_view', 'true');
      this.applyViewMode();
    });
  }

  private applyViewMode(): void {
    const normalBtn = this.root.querySelector('#cashier-view-normal');
    const compactBtn = this.root.querySelector('#cashier-view-compact');

    const ordersTable = this.ordersTable?.closest('table');
    const trackingTable = this.trackingOrdersTable?.closest('table');
    const paidTable = this.paidSessionsTable?.closest('table');

    if (this.isCompactView) {
      normalBtn?.classList.remove('active');
      compactBtn?.classList.add('active');
      ordersTable?.classList.add('compact-view');
      trackingTable?.classList.add('compact-view');
      paidTable?.classList.add('compact-view');
    } else {
      normalBtn?.classList.add('active');
      compactBtn?.classList.remove('active');
      ordersTable?.classList.remove('compact-view');
      trackingTable?.classList.remove('compact-view');
      paidTable?.classList.remove('compact-view');
    }
  }

  private initializeOrderActions(): void {
    this.ordersTable?.addEventListener('click', (event) => {
      const button = (event.target as HTMLElement).closest<HTMLButtonElement>(
        '[data-open-payment-modal]'
      );
      if (!button) return;
      void this.handlePaymentButton(button);
    });
  }

  private async handlePaymentButton(button: HTMLButtonElement): Promise<void> {
    const row = button.closest<HTMLTableRowElement>('tr[data-order-id]');
    const sessionId = Number(row?.dataset.sessionId ?? '');
    if (!sessionId) {
      this.showFeedback('Esta orden no tiene cuenta activa', true);
      return;
    }

    const opened = this.openPaymentModule(sessionId);
    if (!opened) {
      this.showFeedback('No se pudo abrir el módulo de cobro', true);
    }
  }

  private openPaymentModule(sessionId: number, method?: string): boolean {
    if (!sessionId) return false;
    if (window.EmployeePayments?.openModal) {
      window.EmployeePayments.openModal(sessionId, method || 'cash');
      return true;
    }
    if (window.openEmployeePaymentModal) {
      window.openEmployeePaymentModal(sessionId, method || 'cash');
      return true;
    }
    document.dispatchEvent(
      new CustomEvent('employee:payments:open', { detail: { sessionId, method } })
    );
    return true;
  }

  private renderRowActions(row: HTMLTableRowElement, order: OrderInfo): void {
    const cell = row.querySelector<HTMLTableCellElement>('.actions');
    if (!cell) return;
    cell.replaceChildren();

    const normalizedStatus = normalizeWorkflowStatus(
      order.workflow_status,
      order.workflow_status_legacy
    );
    const sessionStatus = order.session?.status || row.dataset.sessionStatus || '';
    const canCharge = Boolean(window.APP_DATA?.can_process_payments);

    if (normalizedStatus !== 'delivered') {
      const label = document.createElement('span');
      label.className = 'status-text';
      label.textContent = 'Esperando entrega';
      cell.appendChild(label);
      return;
    }

    if (!PAYMENT_PENDING_STATUSES.has(sessionStatus)) {
      const label = document.createElement('span');
      label.className = 'status-text';
      label.textContent =
        sessionStatus === 'paid' || sessionStatus === 'closed' ? 'Cuenta cerrada' : 'Sin cobro';
      cell.appendChild(label);
      return;
    }

    if (!canCharge) {
      const label = document.createElement('span');
      label.className = 'status-text';
      label.textContent = 'Sin permiso para cobrar';
      cell.appendChild(label);
      return;
    }

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn--small btn--primary';
    button.dataset.openPaymentModal = 'true';
    button.textContent = '💰 Cobrar';
    cell.appendChild(button);
  }

  private async loadPaidSessions(): Promise<void> {
    if (!this.paidSessionsTable) return;

    try {
      const response = await fetch('/api/sessions/closed');
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        const msg =
          errorPayload?.message || errorPayload?.error || 'Error al cargar sesiones cerradas';
        throw new Error(msg);
      }

      const data = await response.json();
      const sessions: ClosedSession[] = data.closed_sessions || data.sessions || [];
      const filteredSessions = sessions.filter((session) =>
        this.isWithinDateFilter(session.closed_at || '')
      );

      if (filteredSessions.length === 0) {
        this.setTabBadge('cashier-paid-count', 0);
        this.paidSessionsTable.replaceChildren(
          createFragment(`
                    <tr>
                        <td colspan="7" style="text-align: center; padding: 2rem; color: #64748b;">
                            No hay sesiones cerradas en el rango seleccionado
                        </td>
                    </tr>
                `)
        );
        return;
      }

      this.setTabBadge('cashier-paid-count', filteredSessions.length);
      const paidHtml = filteredSessions
        .map((session) => {
          const timeAgo = session.closed_at ? this.getTimeAgo(new Date(session.closed_at)) : '-';
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
          const ordersCount = session.orders_count ?? '-';
          const orderIds = Array.isArray(session.order_ids) ? session.order_ids : [];
          const ordersLabel = orderIds.length
            ? `Órdenes: ${orderIds.map((id: number) => `#${id}`).join(', ')}`
            : '';
          const sessionId = escapeHtml(String(session.id));
          const tableNumber = escapeHtml(session.table_number || 'N/A');
          const customerName = escapeHtml(session.customer_name || 'Cliente');
          const customerEmail = escapeHtml(normalizeCustomerEmail(session.customer_email) || '');
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
                        <td>$${totalDisplay}</td>
                        <td>${escapeHtml(String(ordersCount))}</td>
                        <td>${paymentMethodLabel}</td>
                        <td>${escapeHtml(timeAgo)}</td>
                        <td>
                            <div class="paid-session-actions" style="display: flex; gap: 0.5rem; align-items: center;">
                                <button type="button" class="btn btn--small btn--secondary"
                                    data-action="send-email"
                                    data-session-id="${sessionId}"
                                    data-customer-email="${customerEmail}"
                                    data-customer-name="${customerName}"
                                    title="Enviar ticket por email">
                                    📧
                                </button>
                                <button type="button" class="btn btn--small btn--secondary"
                                    data-action="download-pdf"
                                    data-session-id="${sessionId}"
                                    data-customer-name="${customerName}"
                                    title="Descargar PDF del ticket">
                                    📄
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
        })
        .join('');

      // Add event listeners for paid session actions
      this.paidSessionsTable.addEventListener('click', (e) =>
        this.handlePaidSessionAction(e as Event)
      );
      this.paidSessionsTable.replaceChildren(createFragment(paidHtml));
    } catch (error) {
      console.error('[CASHIER] Error loading paid sessions:', error);
      if (this.paidFeedback) {
        this.paidFeedback.textContent =
          (error as Error).message || 'Error al cargar sesiones cerradas';
        this.paidFeedback.classList.add('error');
      }
    }
  }

  private renderCancelledOrders(): void {
    if (!this.cancelledOrdersTable || !this.ordersTable) return;
    const cancelledRows = Array.from(
      this.ordersTable.querySelectorAll<HTMLTableRowElement>('tr[data-order-id]')
    ).filter((row) => (row.dataset.status || '').toLowerCase() === 'cancelled');

    this.cancelledOrdersTable.replaceChildren();

    if (cancelledRows.length === 0) {
      this.cancelledOrdersTable.replaceChildren(
        createFragment(`
                <tr class="cancelled-empty-state">
                    <td colspan="6" style="text-align: center; padding: 2rem; color: #64748b;">
                        No hay órdenes canceladas.
                    </td>
                </tr>
            `)
      );
    } else {
      cancelledRows.forEach((row) => {
        const orderId = row.dataset.orderId || '';
        const tableNumber = row.dataset.tableNumber || 'N/A';
        const customerName = row.dataset.customerName || 'Cliente';
        const totalRaw =
          row.dataset.total ||
          row.querySelector('.order-total-display')?.textContent?.replace(/[^0-9.]/g, '') ||
          '';
        const cancelledAt = row.dataset.paidAt || '';
        const cancelledDate = cancelledAt
          ? new Date(cancelledAt).toLocaleString('es-MX', {
              year: 'numeric',
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })
          : '-';

        const rowEl = document.createElement('tr');
        const safeOrderId = escapeHtml(orderId);
        const safeTableNumber = escapeHtml(tableNumber);
        const safeCustomerName = escapeHtml(customerName);
        const totalDisplay = totalRaw ? `$${Number(totalRaw).toFixed(2)}` : '-';
        rowEl.replaceChildren(
          createFragment(`
                    <td>#${safeOrderId}</td>
                    <td>${safeTableNumber}</td>
                    <td>${safeCustomerName}</td>
                    <td>${escapeHtml(totalDisplay)}</td>
                    <td>cancelled</td>
                    <td>${escapeHtml(cancelledDate)}</td>
                `)
        );
        this.cancelledOrdersTable!.appendChild(rowEl);
      });
    }

    const badge = this.root.querySelector<HTMLElement>('#cashier-cancelled-count');
    if (badge) {
      badge.textContent = String(cancelledRows.length);
      badge.classList.toggle('is-hidden', cancelledRows.length === 0);
    }
  }

  private async refreshOrders(): Promise<void> {
    this.showFeedback('Actualizando...');
    try {
      const response = await fetch('/api/orders?include_closed=true&include_delivered=true');
      if (!response.ok) throw new Error('Error al cargar órdenes');

      const data = await response.json();
      const newOrders: OrderInfo[] = (data.orders || []).map((order: OrderInfo) => {
        const normalizedStatus = normalizeWorkflowStatus(
          order.workflow_status,
          order.workflow_status_legacy
        );
        return {
          ...order,
          workflow_status: normalizedStatus,
          workflow_status_legacy: normalizedStatus,
        };
      });
      window.CASHIER_ORDERS_DATA = newOrders;

      if (this.ordersTable) {
        this.ordersTable.replaceChildren();

        if (newOrders.length === 0) {
          this.ordersTable.replaceChildren(
            createFragment(`
                        <tr class="orders-empty-row">
                            <td colspan="9">
                                <div class="orders-empty orders-empty--center" role="status" aria-live="polite">
                                    <div class="orders-empty__illustration" aria-hidden="true">
                                        <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2"
                                            stroke-linecap="round" stroke-linejoin="round">
                                            <circle cx="32" cy="32" r="26" opacity="0.25"></circle>
                                            <path d="M20 36a12 12 0 0 1 24 0"></path>
                                            <path d="M18 40h28"></path>
                                            <path d="M24 24c0-2.2 1.8-4 4-4"></path>
                                            <path d="M36 20c2.2 0 4 1.8 4 4"></path>
                                            <path d="M30 18h4"></path>
                                            <path d="M12 44h40"></path>
                                        </svg>
                                    </div>
                                    <div class="orders-empty__title">¡Todo al día!</div>
                                    <div class="orders-empty__text">No hay órdenes pendientes de pago.</div>
                                </div>
                            </td>
                        </tr>
                        <tr class="orders-filter-empty" data-filter-empty-for="cashier" style="display: none;">
                            <td colspan="9">No encontramos órdenes que coincidan con tu búsqueda.</td>
                        </tr>
                    `)
          );
        } else {
          newOrders.forEach((order) => {
            const row = this.createOrderRow(order);
            this.ordersTable!.appendChild(row);
          });
          const empty = document.createElement('tr');
          empty.className = 'orders-filter-empty';
          empty.dataset.filterEmptyFor = 'cashier';
          empty.style.display = 'none';
          empty.replaceChildren(
            createFragment(
              '<td colspan="9">No encontramos órdenes que coincidan con tu búsqueda.</td>'
            )
          );
          this.ordersTable.appendChild(empty);
        }

        this.updateStarButtonStates();
        this.sortOrders();
        this.applyFilters();
      }

      this.showFeedback('Ordenes actualizadas');
    } catch (error) {
      console.error('[CASHIER] Error refreshing:', error);
      this.showFeedback('Error al actualizar', true);
    }
  }

  private createOrderRow(order: OrderInfo): HTMLTableRowElement {
    const row = document.createElement('tr');
    row.dataset.orderId = String(order.id);
    const normalizedStatus = normalizeWorkflowStatus(
      order.workflow_status,
      order.workflow_status_legacy
    );
    row.dataset.status = normalizedStatus;
    row.dataset.sessionId = String(order.session_id);
    row.dataset.sessionStatus = order.session?.status || '';
    row.dataset.paidAt = order.session?.closed_at || '';
    row.dataset.createdAt = order.created_at || '';
    row.dataset.sessionOpened = order.session?.opened_at || '';
    row.dataset.tableNumber = order.session?.table_number || '';
    row.dataset.customerName = order.customer?.name || '';
    row.dataset.customerEmail = normalizeCustomerEmail(order.customer?.email);
    row.dataset.customerId = order.customer?.id ? String(order.customer.id) : '';
    row.dataset.waiterName = order.waiter_name || '';
    row.dataset.waiterId = order.waiter_id ? String(order.waiter_id) : '';
    row.dataset.notes = order.session?.notes || '';
    row.dataset.total = order.total_amount ? String(order.total_amount) : '';

    const orderId = escapeHtml(String(order.id));
    const tableNumber = escapeHtml(order.session?.table_number || '');
    const customerName = escapeHtml(order.customer?.name || 'Cliente');
    const customerEmail = escapeHtml(order.customer?.email || '');
    const customerPhone = escapeHtml(order.customer?.phone || '');
    const notes = escapeHtml(order.session?.notes || '');
    const workflowStatus = escapeHtml(normalizedStatus);
    const totalValue = escapeHtml(String(order.total_amount || 0));
    const waiterBadge = order.waiter_name
      ? `<span class="waiter-badge">👤 ${escapeHtml(order.waiter_name)}</span>`
      : '<span class="waiter-badge waiter-badge--unassigned">⚠️ Sin asignar</span>';
    const totalDisplay = escapeHtml(`$${Number(order.total_amount || 0).toFixed(2)}`);
    const sessionStatus = escapeHtml(order.session?.status || '');
    const notesHtml = order.session?.notes
      ? `
                    <div class="waiter-note-pill text-xs text-gray-600 bg-gray-50 px-2 py-1 rounded border border-gray-100 flex items-center gap-1"
                        title="${notes}">
                        <span class="select-none">👤</span>
                        <span class="truncate max-w-[150px]">${notes}</span>
                    </div>`
      : '';

    row.replaceChildren(
      createFragment(`
            <td>
                <button type="button" class="star-btn" data-order-id="${orderId}" title="Agregar a seguimiento">
                    <span class="star-icon">☆</span>
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
                    data-status="${workflowStatus}" data-total="${totalValue}">
                    #${orderId}
                </button>
            </td>
            <td>
                <button type="button" class="table-number-link"
                    style="background: none; border: none; color: #ea580c; font-weight: 600; cursor: pointer; text-decoration: underline; padding: 0;"
                    data-table-info="${tableNumber}"
                    data-table-number="${tableNumber}">
                    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" style="width: 16px; height: 16px;">
                        <path d="M4 10h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                        <path d="M6 10v10" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                        <path d="M18 10v10" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                        <path d="M8 6h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                        <path d="M7 6V4h10v2" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                    </svg>
                    ${tableNumber || 'N/A'}
                </button>
            </td>
            <td>${customerName}</td>
            <td>
                ${waiterBadge}
            </td>
            <td>
                <span class="order-total-display">${totalDisplay}</span>
            </td>
            <td><span class="status status--${sessionStatus}">${sessionStatus}</span></td>
            <td class="order-notes">
                <div class="waiter-note-inline flex items-center gap-2 flex-wrap">
                    ${notesHtml}
                </div>
            </td>
            <td class="actions"></td>
        `)
    );

    this.renderRowActions(row, order);
    return row;
  }

  private setTabBadge(id: string, count: number): void {
    const badge = this.root.querySelector<HTMLElement>(`#${id}`);
    if (badge) {
      badge.textContent = String(count);
      badge.classList.toggle('is-hidden', count === 0);
    }
  }

  private isWithinDateFilter(dateStr: string): boolean {
    if (!dateStr || this.dateFilter === 'all') return true;
    const date = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

    if (this.dateFilter === 'today') return diffDays === 0;
    if (this.dateFilter === 'last7') return diffDays <= 7;
    if (this.dateFilter === 'custom') return diffDays <= this.customDateDays;
    return true;
  }

  private getTimeAgo(date: Date): string {
    const diffMs = Date.now() - date.getTime();
    const diffMinutes = Math.floor(diffMs / (1000 * 60));
    if (diffMinutes < 1) return 'Ahora';
    if (diffMinutes < 60) return `${diffMinutes} min`;
    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours} h`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays} d`;
  }

  private showFeedback(message: string, isError = false): void {
    if (!this.feedback) return;
    this.feedback.textContent = message;
    this.feedback.classList.toggle('error', isError);
  }

  private async handlePaidSessionAction(event: Event): Promise<void> {
    const target = event.target as HTMLElement;
    const button = target.closest<HTMLButtonElement>('[data-action]');
    if (!button) return;

    const action = button.dataset.action;
    const sessionId = button.dataset.sessionId;
    const customerEmail = button.dataset.customerEmail;
    const customerName = button.dataset.customerName;

    if (!sessionId) return;

    const sessionNum = escapeHtml(String(sessionId));

    if (action === 'send-email') {
      await this.handleSendEmail(sessionNum, customerEmail, customerName);
    } else if (action === 'download-pdf') {
      await this.handleDownloadPdf(sessionNum, customerName);
    }
  }

  private async handleSendEmail(
    sessionId: string,
    customerEmail: string | undefined,
    customerName: string | undefined
  ): Promise<void> {
    if (!customerEmail) {
      this.showFeedback('El cliente no proporcionó email', true);
      return;
    }

    try {
      const response = await fetch(`/api/sessions/${sessionId}/send-ticket-email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || error.error || 'Error al enviar email');
      }

      const result = await response.json();
      this.showFeedback(`✅ Ticket enviado a ${escapeHtml(customerEmail)}`);
      this.showToast('Email enviado', `Ticket enviado a ${escapeHtml(customerEmail)}`, 'success');
    } catch (error) {
      console.error('[CASHIER] Error sending email:', error);
      this.showFeedback(`Error: ${(error as Error).message}`, true);
      this.showToast('Error', `No se pudo enviar el email: ${(error as Error).message}`, 'error');
    }
  }

  private async handleDownloadPdf(
    sessionId: string,
    customerName: string | undefined
  ): Promise<void> {
    try {
      const response = await fetch(`/api/sessions/${sessionId}/ticket.pdf`, {
        method: 'GET',
      });

      if (!response.ok) {
        throw new Error('Error al descargar ticket');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ticket-sesion-${sessionId}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

      this.showFeedback(`✅ Ticket descargado: Sesión #${sessionId}`);
      this.showToast('PDF descargado', `Ticket de la sesión #${sessionId} descargado`, 'success');
    } catch (error) {
      console.error('[CASHIER] Error downloading PDF:', error);
      this.showFeedback(`Error: ${(error as Error).message}`, true);
      this.showToast('Error', `No se pudo descargar el PDF: ${(error as Error).message}`, 'error');
    }
  }

  private showToast(title: string, message: string, type: 'success' | 'error'): void {
    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.innerHTML = `
            <div style="display: flex; align-items: flex-start; gap: 12px;">
                <span style="flex: 1;">
                    <strong>${escapeHtml(title)}</strong><br/>
                    <span style="opacity: 0.9;">${escapeHtml(message)}</span>
                </span>
                <button class="toast-close" style="background: none; border: none; color: white; opacity: 0.8; cursor: pointer; font-size: 1.2rem; line-height: 1; padding: 0;">&times;</button>
            </div>
        `;
    toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 16px;
            border-radius: 8px;
            color: white;
            font-weight: 500;
            z-index: 10000;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            min-width: 300px;
            max-width: 400px;
        `;
    toast.style.backgroundColor = type === 'success' ? '#10b981' : '#ef4444';

    document.body.appendChild(toast);

    const closeBtn = toast.querySelector('.toast-close');
    closeBtn?.addEventListener('click', () => toast.remove());

    setTimeout(() => toast.remove(), 5000);
  }
}

const createFragment = (html: string): DocumentFragment =>
  document.createRange().createContextualFragment(html);

const escapeHtml = (value: string): string => {
  const div = document.createElement('div');
  div.textContent = value;
  return div.innerHTML;
};

export function initCashierBoard(root: HTMLElement): void {
  const board = new CashierBoard(root);
  board.initialize();
}
