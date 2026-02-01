import { requestJSON } from '../core/http';
import { getCapabilitiesForRole, normalizeBackendCapabilities } from './role-context';
import { showToastGlobal } from '../core/toast';

declare var window: Window &
  typeof globalThis & {
    KITCHEN_ORDERS_DATA: any;
    APP_DATA: any;
    webkitAudioContext: any;
    refreshKitchenOrders?: () => Promise<void>;
  };

// Removed top-level constants to avoid race conditions

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

interface OrderInfo {
  id: number;
  session_id: number;
  workflow_status: WorkflowStatus;
  workflow_status_legacy?: WorkflowStatus;
  created_at?: string;
  session?: {
    table_number?: string | null;
    notes?: string | null;
    status?: string;
    opened_at?: string;
    closed_at?: string | null;
  };
  customer?: {
    id?: number;
    name?: string | null;
    email?: string | null;
    phone?: string | null;
  };
  items?: Array<{
    name: string;
    quantity: number;
  }>;
  total_amount?: number;
  chef_id?: number | null;
  waiter_id?: number | null;
  waiter_name?: string | null;
}

interface SessionInfo {
  id: number;
  table_number: string | null;
  customer_name: string;
  total: number;
  orders_count: number;
  closed_at: string;
}

const ACTIONS: Partial<
  Record<CanonicalWorkflowStatus, { label: string; endpoint: (id: number) => string }[]>
> = {
  new: [{ label: 'Iniciar preparación', endpoint: (id) => `/api/orders/${id}/kitchen/start` }],
  queued: [{ label: 'Iniciar', endpoint: (id) => `/api/orders/${id}/kitchen/start` }],
  preparing: [
    { label: 'Listo para entregar', endpoint: (id) => `/api/orders/${id}/kitchen/ready` },
  ],
  ready: [{ label: 'Entregado', endpoint: (id) => `/api/orders/${id}/deliver` }],
};

const STATUS_HINTS: Partial<Record<CanonicalWorkflowStatus, string>> = {
  new: 'Esperando mesero',
  queued: 'Enviando a cocina',
  preparing: 'En cocina',
  ready: 'Listo entrega',
  delivered: 'Entregado',
  awaiting_payment: 'Esperando pago',
  paid: 'Pagada',
  cancelled: 'Cancelada',
};

const LEGACY_TO_CANONICAL: Record<string, CanonicalWorkflowStatus> = {
  requested: 'new',
  waiter_accepted: 'queued',
  kitchen_in_progress: 'preparing',
  ready_for_delivery: 'ready',
  wait_for_payment: 'awaiting_payment',
  payed: 'paid',
  delivered: 'delivered',
  cancelled: 'cancelled',
};

const normalizeWorkflowStatus = (status: string, legacy?: string): CanonicalWorkflowStatus => {
  if (legacy && legacy in LEGACY_TO_CANONICAL) {
    return LEGACY_TO_CANONICAL[legacy];
  }
  if (status in LEGACY_TO_CANONICAL) {
    return LEGACY_TO_CANONICAL[status];
  }
  return status as CanonicalWorkflowStatus;
};

const POLL_INTERVAL_MS = 5000; // Poll every 5 seconds

class KitchenBoard {
  private root: HTMLElement;
  private ordersTable: HTMLTableSectionElement | null;
  private trackingOrdersTable: HTMLTableSectionElement | null;
  private paidSessionsTable: HTMLTableSectionElement | null;
  private cancelledOrdersTable: HTMLTableSectionElement | null;
  private feedback: HTMLElement | null;
  private paidFeedback: HTMLElement | null;
  private searchInput: HTMLInputElement | null;
  private searchCount: HTMLElement | null;

  // Tab management
  private activeTab: 'active' | 'tracking' | 'paid' | 'cancelled' = 'active';

  // Starred orders
  private starredOrders: Set<number> = new Set();

  // Filter state
  private showMyOrders: boolean = true;
  private showAllOrders: boolean = true;
  private workflowStatusFilters: Set<string> = new Set([
    'new',
    'queued',
    'preparing',
    'ready',
    'delivered',
  ]);
  private dateFilter: 'today' | 'last7' | 'custom' | 'all' = 'today';
  private customDateDays: number = 7;
  private searchTerm: string = '';

  // View mode
  private isCompactView: boolean = false;

  // Polling
  private paidSessionsInterval?: number;

  // Permissions
  private canAdvanceKitchen: boolean = false;

  constructor(root: HTMLElement) {
    this.root = root;
    this.ordersTable = root.querySelector<HTMLTableSectionElement>('#kitchen-orders');
    this.trackingOrdersTable = root.querySelector<HTMLTableSectionElement>(
      '#kitchen-tracking-orders'
    );
    this.paidSessionsTable = root.querySelector<HTMLTableSectionElement>('#kitchen-paid-sessions');
    this.cancelledOrdersTable = root.querySelector<HTMLTableSectionElement>(
      '#kitchen-cancelled-orders'
    );
    this.feedback = root.querySelector<HTMLElement>('#kitchen-feedback');
    this.paidFeedback = root.querySelector<HTMLElement>('#kitchen-paid-feedback');
    this.searchInput = root.querySelector<HTMLInputElement>('#kitchen-search-input');
    this.searchCount = root.querySelector<HTMLElement>('#kitchen-search-count');
  }

  initialize(): void {
    if (!this.ordersTable) {
      console.warn('[KITCHEN] Tabla de órdenes no encontrada');
      return;
    }

    // Load starred orders from localStorage
    this.loadStarredOrders();

    // Initialize permissions with robust fallback
    const roleCapabilities = window.APP_DATA?.role_capabilities;
    const employeeRole = window.APP_DATA?.employee_role;

    console.log('[KITCHEN] Raw backend capabilities:', JSON.stringify(roleCapabilities));
    console.log('[KITCHEN] Employee role:', employeeRole);

    const caps =
      normalizeBackendCapabilities(roleCapabilities) || getCapabilitiesForRole(employeeRole);

    // CRITICAL FIX: Ensure chef role ALWAYS has kitchen advance permission
    // This is a defensive fallback in case backend capabilities fail to load
    const isChefRole =
      employeeRole &&
      ['chef', 'cook', 'admin', 'admin_roles', 'super_admin'].includes(employeeRole.toLowerCase());
    this.canAdvanceKitchen = Boolean(caps?.canAdvanceKitchen) || isChefRole;

    console.log('[KITCHEN] Permissions initialized:', {
      canAdvance: this.canAdvanceKitchen,
      role: employeeRole,
      isChefRole: isChefRole,
      capsFromBackend: caps?.canAdvanceKitchen,
      finalDecision: this.canAdvanceKitchen,
    });

    // Initialize components
    this.initializeTabs();
    this.initializeFilters();
    this.initializeSearch();
    this.initializeStarButtons();
    this.initializeViewToggle();
    this.initializeOrderActions();
    this.initializePolling();

    // Render initial actions for orders
    const ordersData: OrderInfo[] = Array.isArray(window.KITCHEN_ORDERS_DATA)
      ? window.KITCHEN_ORDERS_DATA.map((order: OrderInfo) => {
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

    // Update star button states
    this.updateStarButtonStates();
    this.updateTrackingBadge();

    // Apply initial filters
    this.applyFilters();

    // Expose refresh function globally
    window.refreshKitchenOrders = async () => {
      await this.refreshOrders();
    };
  }

  // ==================== TAB MANAGEMENT ====================

  private initializeTabs(): void {
    const tabs = this.root.querySelectorAll<HTMLButtonElement>('.waiter-tab[data-tab]');
    tabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        const tabType = tab.dataset.tab as 'active' | 'tracking' | 'paid' | 'cancelled';
        this.switchTab(tabType);
      });
    });
    // Set initial tab
    this.switchTab('active');
  }

  private switchTab(tab: 'active' | 'tracking' | 'paid' | 'cancelled'): void {
    this.activeTab = tab;

    // Update tab UI
    this.root.querySelectorAll('.waiter-tab').forEach((t) => {
      t.classList.toggle('active', t.getAttribute('data-tab') === tab);
    });

    // Show/hide sections
    const activeSection = this.root.querySelector<HTMLElement>('#kitchen-active-orders-section');
    const trackingSection = this.root.querySelector<HTMLElement>(
      '#kitchen-tracking-orders-section'
    );
    const paidSection = this.root.querySelector<HTMLElement>('#kitchen-paid-orders-section');
    const cancelledSection = this.root.querySelector<HTMLElement>(
      '#kitchen-cancelled-orders-section'
    );

    if (activeSection) activeSection.style.display = tab === 'active' ? 'block' : 'none';
    if (trackingSection) trackingSection.style.display = tab === 'tracking' ? 'block' : 'none';
    if (paidSection) paidSection.style.display = tab === 'paid' ? 'block' : 'none';
    if (cancelledSection) cancelledSection.style.display = tab === 'cancelled' ? 'block' : 'none';

    // Load tracking orders if switching to tracking tab
    if (tab === 'tracking') {
      this.renderTrackingOrders();
    }

    // Load paid sessions if switching to paid tab
    if (tab === 'paid') {
      void this.loadPaidSessions();
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
        window.clearInterval(this.paidSessionsInterval);
        this.paidSessionsInterval = undefined;
      }
    }
  }

  // ==================== STARRED ORDERS ====================

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

    // Update tracking tab if visible
    if (this.activeTab === 'tracking') {
      this.renderTrackingOrders();
    }
  }

  private loadStarredOrders(): void {
    try {
      const stored = localStorage.getItem('kitchen_starred_orders');
      if (stored) {
        const ids = JSON.parse(stored) as number[];
        this.starredOrders = new Set(ids);
      }
    } catch (error) {
      console.error('[KITCHEN] Error loading starred orders:', error);
    }
  }

  private saveStarredOrders(): void {
    try {
      const ids = Array.from(this.starredOrders);
      localStorage.setItem('kitchen_starred_orders', JSON.stringify(ids));
    } catch (error) {
      console.error('[KITCHEN] Error saving starred orders:', error);
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
    const badge = this.root.querySelector<HTMLElement>('#kitchen-tracking-count');
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
      return bId - aId; // Newest first
    });

    rows.forEach((row) => this.ordersTable!.appendChild(row));
  }

  private renderTrackingOrders(): void {
    if (!this.trackingOrdersTable) return;

    // Get all starred orders from the main table
    const allRows =
      this.ordersTable?.querySelectorAll<HTMLTableRowElement>('tr[data-order-id]') || [];
    const starredRows: HTMLTableRowElement[] = [];

    allRows.forEach((row) => {
      const orderId = Number(row.dataset.orderId);
      if (this.starredOrders.has(orderId)) {
        const clone = row.cloneNode(true) as HTMLTableRowElement;
        starredRows.push(clone);
      }
    });

    // Clear table
    this.trackingOrdersTable.replaceChildren();

    if (starredRows.length === 0) {
      this.trackingOrdersTable.replaceChildren(
        createFragment(`
                <tr class="tracking-empty-state">
                    <td colspan="7" style="text-align: center; padding: 2rem; color: #64748b;">
                        Haz clic en la ⭐ estrella de una orden para agregarla a seguimiento.
                    </td>
                </tr>
            `)
      );
    } else {
      starredRows.forEach((row) => {
        this.trackingOrdersTable!.appendChild(row);
        // Re-render actions for cloned row
        const orderId = Number(row.dataset.orderId);
        const ordersData: OrderInfo[] = Array.isArray(window.KITCHEN_ORDERS_DATA)
          ? window.KITCHEN_ORDERS_DATA
          : [];
        const order = ordersData.find((o) => o.id === orderId);
        if (order) {
          this.renderRowActions(row, order);
        }
      });
    }

    // Re-attach event listeners for tracking table
    this.trackingOrdersTable.addEventListener('click', (event) => {
      const target = event.target as HTMLElement;
      const starBtn = target.closest<HTMLButtonElement>('.star-btn');
      if (starBtn) {
        const orderId = Number(starBtn.dataset.orderId);
        this.toggleStar(orderId);
      }

      const actionBtn = target.closest<HTMLButtonElement>('.kitchen-action');
      if (actionBtn) {
        const row = actionBtn.closest<HTMLTableRowElement>('tr[data-order-id]');
        if (row) {
          const orderId = Number(row.dataset.orderId);
          void this.processAction(actionBtn, row, orderId, this.feedback);
        }
      }
    });
  }

  // ==================== FILTERS ====================

  private initializeFilters(): void {
    // Restore filters from localStorage
    const savedWorkflowFilters = localStorage.getItem('kitchen_workflow_filters');
    const savedShowMyOrders = localStorage.getItem('kitchen_show_my_orders');
    const savedShowAllOrders = localStorage.getItem('kitchen_show_all_orders');
    const savedDateFilter = localStorage.getItem('kitchen_date_filter');
    const savedDateDays = localStorage.getItem('kitchen_date_days');

    if (savedWorkflowFilters) {
      this.workflowStatusFilters = new Set(JSON.parse(savedWorkflowFilters));
    }
    this.workflowStatusFilters.add('new');
    if (savedShowMyOrders !== null) {
      this.showMyOrders = savedShowMyOrders === 'true';
    }
    if (savedShowAllOrders !== null) {
      this.showAllOrders = savedShowAllOrders === 'true';
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

    // Sync checkboxes
    this.syncFilterCheckboxes();

    // Modal controls
    const openBtn = this.root.querySelector<HTMLButtonElement>('#kitchen-open-filters-btn');
    const closeBtn = this.root.querySelector<HTMLButtonElement>('#kitchen-close-filters-btn');
    const applyBtn = this.root.querySelector<HTMLButtonElement>('#kitchen-apply-filters-btn');
    const modal = this.root.querySelector<HTMLElement>('#kitchen-filters-modal');
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
    this.root.querySelectorAll('input[name="kitchen-workflow-status"]').forEach((checkbox) => {
      checkbox.addEventListener('change', () => this.handleFilterChange());
    });

    this.root.querySelector('#kitchen-filter-my-orders')?.addEventListener('change', () => {
      this.handleFilterChange();
    });
    this.root.querySelector('#kitchen-filter-all-orders')?.addEventListener('change', () => {
      this.handleFilterChange();
    });

    // Date range filters
    this.root
      .querySelectorAll<HTMLInputElement>('input[name="kitchen-date-filter"]')
      .forEach((radio) => {
        radio.addEventListener('change', () => {
          this.dateFilter = radio.value as any;
          this.handleFilterChange();
        });
      });

    const daysInput = this.root.querySelector<HTMLInputElement>('#kitchen-date-filter-days');
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
    this.root.querySelector('#kitchen-reset-filters')?.addEventListener('click', () => {
      this.resetFilters();
    });
  }

  private syncFilterCheckboxes(): void {
    this.root
      .querySelectorAll<HTMLInputElement>('input[name="kitchen-workflow-status"]')
      .forEach((checkbox) => {
        checkbox.checked = this.workflowStatusFilters.has(checkbox.value);
      });

    const myOrdersCheckbox = this.root.querySelector<HTMLInputElement>('#kitchen-filter-my-orders');
    if (myOrdersCheckbox) myOrdersCheckbox.checked = this.showMyOrders;

    const allOrdersCheckbox = this.root.querySelector<HTMLInputElement>(
      '#kitchen-filter-all-orders'
    );
    if (allOrdersCheckbox) allOrdersCheckbox.checked = this.showAllOrders;

    this.root
      .querySelectorAll<HTMLInputElement>('input[name="kitchen-date-filter"]')
      .forEach((radio) => {
        radio.checked = radio.value === this.dateFilter;
      });
  }

  private handleFilterChange(): void {
    // Update workflow status filters
    this.workflowStatusFilters.clear();
    this.root
      .querySelectorAll<HTMLInputElement>('input[name="kitchen-workflow-status"]:checked')
      .forEach((checkbox) => {
        this.workflowStatusFilters.add(checkbox.value);
      });

    // Update order view filters
    const myOrdersCheckbox = this.root.querySelector<HTMLInputElement>('#kitchen-filter-my-orders');
    const allOrdersCheckbox = this.root.querySelector<HTMLInputElement>(
      '#kitchen-filter-all-orders'
    );
    if (myOrdersCheckbox) this.showMyOrders = myOrdersCheckbox.checked;
    if (allOrdersCheckbox) this.showAllOrders = allOrdersCheckbox.checked;

    // Save to localStorage
    localStorage.setItem(
      'kitchen_workflow_filters',
      JSON.stringify(Array.from(this.workflowStatusFilters))
    );
    localStorage.setItem('kitchen_show_my_orders', String(this.showMyOrders));
    localStorage.setItem('kitchen_show_all_orders', String(this.showAllOrders));
    localStorage.setItem('kitchen_date_filter', this.dateFilter);
    localStorage.setItem('kitchen_date_days', String(this.customDateDays));

    // Apply filters
    this.applyFilters();
  }

  private resetFilters(): void {
    this.workflowStatusFilters = new Set(['new', 'queued', 'preparing', 'ready', 'delivered']);
    this.showMyOrders = true;
    this.showAllOrders = true;
    this.dateFilter = 'today';
    this.customDateDays = 7;

    this.syncFilterCheckboxes();
    this.handleFilterChange();
  }

  // ==================== SEARCH ====================

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

  // ==================== APPLY FILTERS ====================

  private applyFilters(): void {
    if (!this.ordersTable) return;

    const myChefId = String(window.APP_DATA?.employee_id ?? '');
    let visible = 0;
    const rows = Array.from(
      this.ordersTable.querySelectorAll<HTMLTableRowElement>('tr[data-order-id]')
    );

    rows.forEach((row) => {
      const status = row.dataset.status || '';
      const chefId = row.dataset.chefId || '';
      const createdAt = row.dataset.createdAt || '';

      // Filter by workflow status
      const matchesStatus = this.workflowStatusFilters.has(status);

      // Filter by ownership (my orders or all orders)
      let matchesOwnership = false;
      const isMyOrder = myChefId && chefId && chefId === myChefId;
      if (this.showMyOrders && isMyOrder) matchesOwnership = true;
      if (this.showAllOrders && !isMyOrder) matchesOwnership = true;

      // Filter by date
      let matchesDate = true;
      if (this.dateFilter !== 'all' && createdAt) {
        const orderDate = new Date(createdAt);
        const now = new Date();

        // Normalize to start of day for accurate day comparison regardless of time
        const orderDay = new Date(
          orderDate.getFullYear(),
          orderDate.getMonth(),
          orderDate.getDate()
        );
        const currentDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());

        const diffTime = currentDay.getTime() - orderDay.getTime();
        const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

        if (this.dateFilter === 'today') {
          // Accept today (0) and future dates (negative diff) which might happen due to timezone mess
          matchesDate = diffDays <= 0;
        } else if (this.dateFilter === 'last7') {
          matchesDate = diffDays <= 7;
        } else if (this.dateFilter === 'custom') {
          matchesDate = diffDays <= this.customDateDays;
        }
      }

      // Filter by search term
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

      // When searching, show all matching results regardless of status filters
      // This ensures orders don't "disappear" from search when marked as ready/delivered
      const show = this.searchTerm
        ? matchesSearch && matchesDate
        : matchesStatus && matchesOwnership && matchesDate && matchesSearch;
      row.style.display = show ? '' : 'none';
      if (show) visible += 1;
    });

    // Update empty row visibility
    const emptyRow = this.ordersTable.querySelector<HTMLTableRowElement>(
      'tr.orders-filter-empty[data-filter-empty-for="kitchen"]'
    );
    if (emptyRow) {
      emptyRow.style.display = rows.length > 0 && visible === 0 ? '' : 'none';
    }

    // Update search count
    if (this.searchCount) {
      if (this.searchTerm) {
        this.searchCount.textContent = `${visible}`;
        this.searchCount.style.display = '';
      } else {
        this.searchCount.style.display = 'none';
      }
    }

    // Update orders count
    const ordersCount = this.root.querySelector<HTMLElement>('#kitchen-orders-count');
    if (ordersCount) {
      ordersCount.textContent = `${visible} órdenes`;
    }

    // Update badge count
    const activeBadge = this.root.querySelector<HTMLElement>('#kitchen-active-count');
    if (activeBadge) {
      activeBadge.textContent = String(visible);
      activeBadge.classList.toggle('is-hidden', visible === 0);
    }
  }

  // ==================== VIEW TOGGLE ====================

  private initializeViewToggle(): void {
    const savedView = localStorage.getItem('kitchen_compact_view');
    this.isCompactView = savedView === 'true';

    const normalBtn = this.root.querySelector<HTMLButtonElement>('#kitchen-view-normal');
    const compactBtn = this.root.querySelector<HTMLButtonElement>('#kitchen-view-compact');

    this.applyViewMode();

    normalBtn?.addEventListener('click', () => {
      this.isCompactView = false;
      localStorage.setItem('kitchen_compact_view', 'false');
      this.applyViewMode();
    });

    compactBtn?.addEventListener('click', () => {
      this.isCompactView = true;
      localStorage.setItem('kitchen_compact_view', 'true');
      this.applyViewMode();
    });
  }

  private applyViewMode(): void {
    const normalBtn = this.root.querySelector('#kitchen-view-normal');
    const compactBtn = this.root.querySelector('#kitchen-view-compact');

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

  // ==================== ORDER ACTIONS ====================

  private initializeOrderActions(): void {
    this.ordersTable?.addEventListener('click', (event) => {
      const button = (event.target as HTMLElement).closest<HTMLButtonElement>('.kitchen-action');
      if (!button) return;
      const row = button.closest<HTMLTableRowElement>('tr[data-order-id]');
      if (!row) return;
      const orderId = Number(row.dataset.orderId);
      void this.processAction(button, row, orderId, this.feedback);
    });
  }

  private getDisplayStatus(status: string, legacy?: string): string {
    const normalized = normalizeWorkflowStatus(status, legacy);
    const map: Partial<Record<CanonicalWorkflowStatus, string>> = {
      new: 'Esperando mesero',
      queued: 'Enviando a cocina',
      preparing: 'En cocina',
      ready: 'Listo entrega',
      delivered: 'Entregado',
      awaiting_payment: 'Esperando pago',
      paid: 'Pagada',
      cancelled: 'Cancelada',
    };
    return map[normalized] || normalized;
  }

  private renderRowActions(row: HTMLTableRowElement, order: OrderInfo): void {
    const cell = row.querySelector<HTMLTableCellElement>('.actions');

    const normalizedStatus = normalizeWorkflowStatus(
      order.workflow_status,
      order.workflow_status_legacy
    );
    // Update status text with friendly name
    const statusEl = row.querySelector<HTMLElement>('.status');
    if (statusEl) {
      statusEl.textContent = this.getDisplayStatus(normalizedStatus);
      // Keep the class for styling
      statusEl.className = `status status--${normalizedStatus}`;
    }

    if (!cell) return;
    cell.replaceChildren();
    const actions = this.canAdvanceKitchen
      ? ACTIONS[normalizedStatus as CanonicalWorkflowStatus] || []
      : [];
    if (actions.length === 0) {
      const label = document.createElement('span');
      label.className = 'status-text';
      label.textContent =
        STATUS_HINTS[normalizedStatus as CanonicalWorkflowStatus] ||
        this.getDisplayStatus(normalizedStatus);
      label.style.fontSize = '0.875rem';
      label.style.color = '#64748b';
      label.style.fontStyle = 'italic';
      cell.appendChild(label);
      return;
    }
    actions.forEach((action) => {
      const button = document.createElement('button');
      button.className = 'btn btn--small btn--secondary kitchen-action';
      button.dataset.endpoint = action.endpoint(order.id);
      button.textContent = action.label;
      cell.appendChild(button);
    });
  }

  private async processAction(
    button: HTMLButtonElement,
    row: HTMLTableRowElement,
    orderId: number,
    feedback: HTMLElement | null
  ): Promise<void> {
    if (!this.canAdvanceKitchen) {
      showFeedback(feedback, 'Sin permisos para avanzar estatus', true);
      return;
    }
    const endpoint = button.dataset.endpoint;
    if (!endpoint) return;
    const employeeId = window.APP_DATA?.employee_id;
    if (!employeeId) {
      showFeedback(feedback, 'Error: No hay empleado activo en esta sesión', true);
      return;
    }
    button.disabled = true;
    showFeedback(feedback, 'Procesando...');
    try {
      const data = await requestJSON<OrderInfo>(endpoint, {
        method: 'POST',
        body: { employee_id: employeeId },
      });
      const normalizedStatus = normalizeWorkflowStatus(
        data.workflow_status,
        data.workflow_status_legacy
      );
      const normalizedOrder = {
        ...data,
        workflow_status: normalizedStatus,
        workflow_status_legacy: normalizedStatus,
      } as OrderInfo;
      row.dataset.status = normalizedStatus;

      // Update status and actions
      this.renderRowActions(row, normalizedOrder);

      showFeedback(feedback, 'Actualizado');
    } catch (error) {
      showFeedback(feedback, (error as Error).message, true);
    } finally {
      button.disabled = false;
    }
  }

  // ==================== PAID SESSIONS ====================

  private async loadPaidSessions(): Promise<void> {
    if (!this.paidSessionsTable) return;

    try {
      showFeedback(this.paidFeedback, 'Cargando...');
      const response = await fetch('/api/sessions/paid');
      if (!response.ok) throw new Error('Error al cargar sesiones pagadas');

      const data = await response.json();
      const sessions: SessionInfo[] = data.sessions || [];

      this.paidSessionsTable.replaceChildren();

      if (sessions.length === 0) {
        this.paidSessionsTable.replaceChildren(
          createFragment(`
                    <tr>
                        <td colspan="6" style="text-align: center; padding: 2rem; color: #64748b;">
                            No hay sesiones pagadas recientes.
                        </td>
                    </tr>
                `)
        );
      } else {
        sessions.forEach((session) => {
          const row = document.createElement('tr');
          const closedDate = new Date(session.closed_at);
          const sessionId = escapeHtml(String(session.id));
          const tableNumber = escapeHtml(session.table_number || 'N/A');
          const customerName = escapeHtml(session.customer_name || 'Cliente');
          const totalDisplay = escapeHtml(`$${session.total.toFixed(2)}`);
          const ordersCount = escapeHtml(String(session.orders_count));
          const closedAt = escapeHtml(
            closedDate.toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' })
          );
          row.replaceChildren(
            createFragment(`
                        <td>#${sessionId}</td>
                        <td>${tableNumber}</td>
                        <td>${customerName}</td>
                        <td>${totalDisplay}</td>
                        <td>${ordersCount}</td>
                        <td>${closedAt}</td>
                        <td>
                            <a href="/api/sessions/${sessionId}/ticket.pdf" target="_blank"
                               class="btn btn--small btn--secondary" title="Descargar PDF">
                                📄 PDF
                            </a>
                        </td>
                    `)
          );
          this.paidSessionsTable!.appendChild(row);
        });
      }

      showFeedback(this.paidFeedback, '');
    } catch (error) {
      console.error('[KITCHEN] Error loading paid sessions:', error);
      this.paidSessionsTable.replaceChildren(
        createFragment(`
                <tr>
                    <td colspan="6" style="text-align: center; padding: 2rem; color: #ef4444;">
                        Error al cargar sesiones pagadas.
                    </td>
                </tr>
            `)
      );
      showFeedback(this.paidFeedback, (error as Error).message, true);
    }
  }

  // ==================== CANCELLED ORDERS ====================

  private renderCancelledOrders(): void {
    if (!this.cancelledOrdersTable) return;

    // Filter cancelled orders from main orders
    const allRows =
      this.ordersTable?.querySelectorAll<HTMLTableRowElement>('tr[data-order-id]') || [];
    const cancelledRows: HTMLTableRowElement[] = [];

    allRows.forEach((row) => {
      if (row.dataset.status === 'cancelled') {
        const clone = row.cloneNode(true) as HTMLTableRowElement;
        cancelledRows.push(clone);
      }
    });

    this.cancelledOrdersTable.replaceChildren();

    if (cancelledRows.length === 0) {
      this.cancelledOrdersTable.replaceChildren(
        createFragment(`
                <tr>
                    <td colspan="6" style="text-align: center; padding: 2rem; color: #64748b;">
                        No hay órdenes canceladas.
                    </td>
                </tr>
            `)
      );
    } else {
      cancelledRows.forEach((row) => {
        // Remove star column
        const starCell = row.querySelector('td:first-child');
        if (starCell) starCell.remove();

        // Remove actions column
        const actionsCell = row.querySelector('.actions');
        if (actionsCell?.parentElement) actionsCell.parentElement.remove();

        this.cancelledOrdersTable!.appendChild(row);
      });
    }

    // Update badge
    const badge = this.root.querySelector<HTMLElement>('#kitchen-cancelled-count');
    if (badge) {
      badge.textContent = String(cancelledRows.length);
      badge.classList.toggle('is-hidden', cancelledRows.length === 0);
    }
  }

  // ==================== REFRESH ORDERS ====================

  private async refreshOrders(): Promise<void> {
    console.log('[KITCHEN] Refreshing orders manually...');
    showFeedback(this.feedback, 'Actualizando...');
    try {
      const response = await fetch('/api/orders/kitchen/pending');
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

      // Update global data
      window.KITCHEN_ORDERS_DATA = newOrders;

      // Update category counts (#7)
      this.updateCategoryCounts(newOrders);

      // Clear existing rows
      if (this.ordersTable) {
        this.ordersTable.replaceChildren();

        if (newOrders.length === 0) {
          this.ordersTable.replaceChildren(
            createFragment(`
                        <tr class="orders-empty-row">
                            <td colspan="7">
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
                                    <div class="orders-empty__title">¡Todo listo!</div>
                                    <div class="orders-empty__text">No hay órdenes pendientes en cocina. Las nuevas órdenes aparecerán aquí.</div>
                                </div>
                            </td>
                        </tr>
                        <tr class="orders-filter-empty" data-filter-empty-for="kitchen" style="display: none;">
                            <td colspan="7">No encontramos órdenes que coincidan con tu búsqueda.</td>
                        </tr>
                    `)
          );
        } else {
          // Render new orders
          newOrders.forEach((order) => {
            const row = this.createOrderRow(order);
            this.ordersTable!.appendChild(row);
          });
          // Keep empty filter row for search
          const empty = document.createElement('tr');
          empty.className = 'orders-filter-empty';
          empty.dataset.filterEmptyFor = 'kitchen';
          empty.style.display = 'none';
          empty.replaceChildren(
            createFragment(
              '<td colspan="7">No encontramos órdenes que coincidan con tu búsqueda.</td>'
            )
          );
          this.ordersTable.appendChild(empty);
        }

        this.updateStarButtonStates();
        this.sortOrders();
        this.applyFilters();
      }

      showFeedback(this.feedback, 'Órdenes actualizadas');
    } catch (error) {
      console.error('[KITCHEN] Error refreshing:', error);
      showFeedback(this.feedback, 'Error al actualizar', true);
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
    row.dataset.customerEmail = order.customer?.email || '';
    row.dataset.customerId = String(order.customer?.id || '');
    row.dataset.notes = order.session?.notes || '';
    row.dataset.chefId = String(order.chef_id || '');
    row.dataset.waiterId = String(order.waiter_id || '');
    row.dataset.waiterName = order.waiter_name || '';

    // Render items list
    const itemsList =
      order.items
        ?.map((item) => `<li>${escapeHtml(String(item.quantity))} x ${escapeHtml(item.name)}</li>`)
        .join('') || '<li>Sin items</li>';

    // Render client notes if present (NO waiter notes for chef!)
    const clientNotesHtml = order.session?.notes
      ? `
            <div class="kitchen-customer-note" style="margin-top: 0.5rem; padding: 0.5rem; background-color: #fef3c7; border-left: 3px solid #f59e0b; border-radius: 4px;">
                <p style="margin: 0; font-size: 0.85rem; font-weight: 600; color: #92400e;">📝 Nota del cliente:</p>
                <p style="margin: 0.25rem 0 0; font-size: 0.9rem; color: #78350f;">${escapeHtml(order.session.notes)}</p>
            </div>
        `
      : '';

    const orderId = escapeHtml(String(order.id));
    const tableNumber = escapeHtml(order.session?.table_number || '');
    const customerName = escapeHtml(order.customer?.name || 'Cliente');
    const customerEmail = escapeHtml(order.customer?.email || '');
    const customerPhone = escapeHtml(order.customer?.phone || '');
    const notes = escapeHtml(order.session?.notes || '');
    const workflowStatus = escapeHtml(normalizedStatus);
    const totalValue = escapeHtml(String(order.total_amount || 0));

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
                    data-status="${workflowStatus}"
                    data-total="${totalValue}">
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
                <ul style="margin: 0; padding-left: 1.25rem;">
                    ${itemsList}
                </ul>
                ${clientNotesHtml}
            </td>
            <td><span class="status status--${workflowStatus}">${workflowStatus}</span></td>
            <td class="actions"></td>
        `)
    );

    this.renderRowActions(row, order);
    return row;
  }

  // ==================== CATEGORY COUNTS (#7) ====================

  private updateCategoryCounts(orders: OrderInfo[]): void {
    const counts = {
      all: orders.length,
      burger: 0,
      pizza: 0,
      taco: 0,
      drink: 0,
      dessert: 0,
      salad: 0,
      combo: 0,
    };

    orders.forEach((order) => {
      if (!order.items) return;

      order.items.forEach((item) => {
        const itemName = item.name?.toLowerCase() || '';

        if (itemName.includes('hamburguesa')) {
          counts.burger++;
        } else if (itemName.includes('pizza')) {
          counts.pizza++;
        } else if (itemName.includes('taco')) {
          counts.taco++;
        } else if (
          itemName.includes('bebida') ||
          itemName.includes('refresco') ||
          itemName.includes('agua') ||
          itemName.includes('jugo') ||
          itemName.includes('cerveza')
        ) {
          counts.drink++;
        } else if (
          itemName.includes('postre') ||
          itemName.includes('helado') ||
          itemName.includes('pastel')
        ) {
          counts.dessert++;
        } else if (itemName.includes('ensalada')) {
          counts.salad++;
        } else if (itemName.includes('combo')) {
          counts.combo++;
        }
      });
    });

    // Update display counts
    Object.keys(counts).forEach((category) => {
      const countElement = document.getElementById(`filter-count-${category}`);
      if (countElement) {
        countElement.textContent = String(counts[category as keyof typeof counts]);
      }
    });
  }

  // ==================== POLLING ====================

  private initializePolling(): void {
    let lastOrderIds = new Set<number>();

    // Initialize with current orders from DOM to avoid notifying on load
    this.ordersTable?.querySelectorAll('tr[data-order-id]').forEach((row) => {
      const id = Number((row as HTMLElement).dataset.orderId);
      if (id) lastOrderIds.add(id);
    });

    console.log('[KITCHEN] Iniciando polling HTTP cada', POLL_INTERVAL_MS / 1000, 'segundos');

    const pollForUpdates = async () => {
      try {
        const response = await fetch('/api/orders/kitchen/pending');
        if (!response.ok) return;

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
        const currentOrderIds = new Set(newOrders.map((o) => o.id));

        // Check for new orders that weren't there before
        const addedOrders = newOrders.filter((o) => !lastOrderIds.has(o.id));

        if (addedOrders.length > 0) {
          this.playNotificationSound();

          // Show specific notification for each new order
          addedOrders.forEach((order) => {
            const tableName = order.session?.table_number || 'Mesa ?';
            const message = `🔔 Nueva Orden #${order.id} - ${tableName}`;
            showToastGlobal(message, 'info');
          });

          // Refresh orders after a short delay
          setTimeout(() => {
            void this.refreshOrders();
          }, 500);
        }

        // Update tracking set to match current server state
        lastOrderIds = currentOrderIds;
      } catch (error) {
        console.error('[KITCHEN] Error en polling:', error);
      }
    };

    // Start polling
    setInterval(pollForUpdates, POLL_INTERVAL_MS);
    // Initial poll after 2 seconds
    setTimeout(pollForUpdates, 2000);
  }

  private playNotificationSound(): void {
    try {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();
      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);
      // Use a different tone than waiter panel (higher pitch)
      oscillator.frequency.value = 1000;
      oscillator.type = 'sine';
      gainNode.gain.setValueAtTime(0.4, audioContext.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.4);
      oscillator.start();
      oscillator.stop(audioContext.currentTime + 0.4);
    } catch (error) {
      console.log('[KITCHEN] No se pudo reproducir sonido:', error);
    }
  }
}

// ==================== HELPER FUNCTIONS ====================

function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function createFragment(html: string): DocumentFragment {
  return document.createRange().createContextualFragment(html);
}

function showFeedback(element: HTMLElement | null, message: string, isError = false): void {
  if (!element) return;
  element.textContent = message;
  element.classList.toggle('error', isError);
}

// ==================== INITIALIZATION ====================

export function initKitchenBoard(root: HTMLElement): void {
  const board = new KitchenBoard(root);
  board.initialize();
}
