import { getCapabilitiesForRole, type RoleCapabilities } from './role-context';
import { isValidEmailFormat, normalizeCustomerEmail } from './email-utils';

// Pagination config with localStorage
const ITEMS_PER_PAGE_OPTIONS = [10, 20, 50, 100];
const STORAGE_KEY = 'pronto_items_per_page_sessions';

function getSavedItemsPerPage(): number {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const value = parseInt(saved, 10);
      if (ITEMS_PER_PAGE_OPTIONS.includes(value)) return value;
    }
    const global = localStorage.getItem('pronto_items_per_page');
    if (global) {
      const value = parseInt(global, 10);
      if (ITEMS_PER_PAGE_OPTIONS.includes(value)) return value;
    }
  } catch (e) {
    /* ignore */
  }
  return 20;
}

function saveItemsPerPage(value: number): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(value));
    localStorage.setItem('pronto_items_per_page', String(value));
  } catch (e) {
    /* ignore */
  }
}

interface PendingSession {
  id: number;
  table_number?: string | null;
  customer_name?: string | null;
  orders_count?: number;
  delivered_orders_count?: number;
  status: string;
  check_requested_at?: string | null;
  subtotal?: number;
  tax_amount?: number;
  tip_amount?: number;
  total_amount?: number;
}

interface ClosedSession {
  id: number;
  table_number?: string | null;
  customer_name?: string | null;
  customer_email?: string | null;
  payment_method?: string | null;
  payment_reference?: string | null;
  orders_count?: number;
  subtotal?: number;
  tax_amount?: number;
  tip_amount?: number;
  total_amount?: number;
  closed_at: string;
}

type SessionResponse<T> = {
  status: string;
  message?: string;
  sessions?: T[];
  closed_sessions?: T[];
  data?: T[];
};

export function initSessionsManager(): void {
  document.addEventListener('DOMContentLoaded', () => {
    const cashierRoot = document.querySelector<HTMLElement>('[data-cashier-root]');
    const closedRoot = document.querySelector<HTMLElement>('[data-closed-sessions-root]');
    if (!cashierRoot && !closedRoot) return;
    const manager = new SessionsManager(cashierRoot, closedRoot);
    manager.initialize();
    window.ProntoSessions = manager;

    // Expose refresh function globally for HTML button
    (window as any).refreshCashierData = () => manager.refresh();
  });
}

declare global {
  interface Window {
    openEmployeePaymentModal?: (sessionId: string | number, method: string) => void;
    printTicket?: (sessionId: string | number) => Promise<void>;
    ProntoSessions?: SessionsManager;
  }
}

class SessionsManager {
  private cashierRoot: HTMLElement | null;
  private closedRoot: HTMLElement | null;
  private capabilities: RoleCapabilities;

  private pendingList: HTMLElement | null;

  private closedList: HTMLElement | null;
  private closedPagination: HTMLElement | null;
  private closedSearchInput: HTMLInputElement | null;
  private closedPageSizeSelect: HTMLSelectElement | null;
  private quickFilters: HTMLElement | null;
  private quickFilterButtons: NodeListOf<HTMLButtonElement> | null;
  private dateRangeWrapper: HTMLElement | null;
  private rangeStartInput: HTMLInputElement | null;
  private rangeEndInput: HTMLInputElement | null;

  private resendModal: HTMLElement | null;
  private resendForm: HTMLFormElement | null;
  private resendSessionLabel: HTMLElement | null;
  private resendEmailInput: HTMLInputElement | null;
  private closeResendBtn: HTMLElement | null;
  private cancelResendBtn: HTMLElement | null;

  private closedData: ClosedSession[] = [];
  private closedState = {
    filter: 'today',
    search: '',
    page: 1,
    pageSize: getSavedItemsPerPage(),
    rangeStart: null as string | null,
    rangeEnd: null as string | null,
  };

  constructor(cashierRoot: HTMLElement | null, closedRoot: HTMLElement | null) {
    this.cashierRoot = cashierRoot;
    this.closedRoot = closedRoot;
    this.pendingList = cashierRoot?.querySelector('#cashier-sessions-list') || null;
    this.capabilities =
      window.APP_DATA?.role_capabilities || getCapabilitiesForRole(window.APP_DATA?.employee_role);

    this.closedList = closedRoot?.querySelector('#closed-sessions-list') || null;
    this.closedPagination = closedRoot?.querySelector('#closed-sessions-pagination') || null;
    this.closedSearchInput = closedRoot?.querySelector('#closed-sessions-search') || null;
    this.closedPageSizeSelect = closedRoot?.querySelector('#closed-sessions-page-size') || null;
    this.quickFilters = closedRoot?.querySelector('#closed-sessions-quick-filters') || null;
    this.quickFilterButtons =
      this.quickFilters?.querySelectorAll<HTMLButtonElement>('.quick-filter-btn') || null;
    this.dateRangeWrapper = closedRoot?.querySelector('#closed-date-range') || null;
    this.rangeStartInput = closedRoot?.querySelector('#closed-range-start') || null;
    this.rangeEndInput = closedRoot?.querySelector('#closed-range-end') || null;

    this.resendModal = document.getElementById('resend-ticket-modal');
    this.resendForm = document.getElementById('resend-ticket-form') as HTMLFormElement | null;
    this.resendSessionLabel = document.getElementById('resend-ticket-session-label');
    this.resendEmailInput = document.getElementById(
      'resend-ticket-email'
    ) as HTMLInputElement | null;
    this.closeResendBtn = document.getElementById('close-resend-ticket');
    this.cancelResendBtn = document.getElementById('cancel-resend-ticket');
  }

  initialize(): void {
    if (this.cashierRoot && this.capabilities.canViewActive) {
      void this.loadPendingSessions();
    }
    if (this.closedRoot) {
      if (!this.capabilities.canViewPaid) {
        this.closedRoot.style.display = 'none';
      } else {
        this.attachClosedEventListeners();
        void this.loadClosedSessions();
      }
    }

    document.addEventListener('employee:session:closed', () => {
      if (this.cashierRoot && this.capabilities.canViewActive) void this.loadPendingSessions();
      if (this.closedRoot && this.capabilities.canViewPaid) void this.loadClosedSessions();
    });
    document.addEventListener('employee:session:updated', () => {
      if (this.cashierRoot && this.capabilities.canViewActive) void this.loadPendingSessions();
    });
  }

  public refresh(): void {
    console.log('[CASHIER] Refreshing data manually...');
    if (this.cashierRoot && this.capabilities.canViewActive) {
      void this.loadPendingSessions();
    }
    if (this.closedRoot && this.capabilities.canViewPaid) {
      void this.loadClosedSessions();
    }
  }

  private async requestJSON<T = unknown>(url: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = (data && (data.message || data.error)) || 'Error de conexión';
      throw new Error(message);
    }
    if (data && data.error) {
      throw new Error(data.error || 'Error de conexión');
    }
    return data as T;
  }

  private unwrapResponse<T = unknown>(data: any): T {
    return (data && data.data ? data.data : data) as T;
  }

  // Pending sessions
  private async loadPendingSessions(): Promise<void> {
    if (!this.pendingList) return;
    this.pendingList.replaceChildren(
      createFragment('<p class="loading">Cargando sesiones pendientes...</p>')
    );
    try {
      const data = await this.requestJSON<SessionResponse<PendingSession>>(
        '/api/sessions/awaiting-payment'
      );
      const payload = this.unwrapResponse<SessionResponse<PendingSession>>(data);
      const sessions = payload.sessions || [];
      this.renderPendingSessions(sessions);
    } catch (error) {
      console.error('[Sessions] pending', error);
      this.pendingList.replaceChildren(
        createFragment('<p style="color:#ef4444;">Error al cargar sesiones pendientes</p>')
      );
    }
  }

  private renderPendingSessions(sessions: PendingSession[]): void {
    if (!this.pendingList) return;
    if (!sessions.length) {
      this.pendingList.replaceChildren(
        createFragment('<p>No hay sesiones pendientes de pago.</p>')
      );
      return;
    }
    const canProcess = Boolean(window.APP_DATA?.can_process_payments);
    const chargeableStatuses = new Set(['awaiting_tip', 'awaiting_payment']);
    const allowCharge = this.capabilities.canCharge && canProcess;
    const pendingHtml = sessions
      .map((session) => {
        const requestedDate = session.check_requested_at
          ? new Date(session.check_requested_at)
          : null;
        const formatted = requestedDate
          ? requestedDate.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })
          : 'N/A';
        const canCharge = allowCharge && chargeableStatuses.has(session.status);
        const sessionId = escapeHtml(String(session.id));
        const tableNumber = escapeHtml(session.table_number || 'N/A');
        const customerName = escapeHtml(session.customer_name || 'N/A');
        const ordersCount = escapeHtml(String(session.orders_count || 0));
        const deliveredCount = escapeHtml(String(session.delivered_orders_count || 0));
        const statusLabel = escapeHtml(session.status);
        const formattedTime = escapeHtml(formatted);
        return `
                <article class="session-card session-card--pending" data-session-id="${sessionId}">
                    <div class="session-card__flag session-card__flag--warning">Pendiente</div>
                    <header>
                        <h3>Cuenta #${sessionId} · Mesa ${tableNumber}</h3>
                        <span class="session-status session-status--warning">⏰ Esperando mesero: ${formattedTime}</span>
                    </header>
                    <div class="session-card__info">
                        <p><strong>Cliente:</strong> ${customerName}</p>
                        <p><strong>Órdenes:</strong> ${ordersCount} (${deliveredCount} entregadas)</p>
                        <p><strong>Estado:</strong> ${statusLabel}</p>
                    </div>
                    <div class="session-card__totals">
                        <span>Subtotal: ${escapeHtml(this.formatCurrency(session.subtotal))}</span>
                        <span>IVA: ${escapeHtml(this.formatCurrency(session.tax_amount))}</span>
                        <span>Propina: ${escapeHtml(this.formatCurrency(session.tip_amount))}</span>
                        <strong>Total: ${escapeHtml(this.formatCurrency(session.total_amount))}</strong>
                    </div>
                    ${
                      canCharge
                        ? `<div class="session-card__actions">
                                <button type="button" class="btn btn--primary" data-pay-cash="${sessionId}">💵 Cobrar en efectivo</button>
                                <button type="button" class="btn btn--primary" data-pay-clip="${sessionId}">💳 Cobrar con terminal</button>
                            </div>`
                        : ''
                    }
                </article>`;
      })
      .join('');
    this.pendingList.replaceChildren(createFragment(pendingHtml));
    if (allowCharge) {
      this.pendingList.querySelectorAll<HTMLButtonElement>('[data-pay-cash]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const id = btn.dataset.payCash;
          if (id) window.openEmployeePaymentModal?.(id, 'cash');
        });
      });
      this.pendingList.querySelectorAll<HTMLButtonElement>('[data-pay-clip]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const id = btn.dataset.payClip;
          if (id) window.openEmployeePaymentModal?.(id, 'clip');
        });
      });
    }
  }

  // Closed sessions
  private attachClosedEventListeners(): void {
    this.closedSearchInput?.addEventListener('input', () => {
      this.closedState.search = this.closedSearchInput?.value.trim().toLowerCase() || '';
      this.closedState.page = 1;
      this.renderClosedSessions();
    });
    this.closedPageSizeSelect?.addEventListener('change', () => {
      const newValue = Number(this.closedPageSizeSelect?.value) || 20;
      this.closedState.pageSize = newValue;
      saveItemsPerPage(newValue);
      this.closedState.page = 1;
      this.renderClosedSessions();
    });
    this.rangeStartInput?.addEventListener('change', () => {
      this.closedState.rangeStart = this.rangeStartInput?.value || null;
      if (this.closedState.filter !== 'range') {
        this.closedState.filter = 'range';
        this.updateQuickFilterButtons();
      }
      this.closedState.page = 1;
      this.renderClosedSessions();
    });
    this.rangeEndInput?.addEventListener('change', () => {
      this.closedState.rangeEnd = this.rangeEndInput?.value || null;
      if (this.closedState.filter !== 'range') {
        this.closedState.filter = 'range';
        this.updateQuickFilterButtons();
      }
      this.closedState.page = 1;
      this.renderClosedSessions();
    });
    this.quickFilterButtons?.forEach((btn) => {
      btn.addEventListener('click', () => {
        const period = btn.dataset.period || 'all';
        this.closedState.filter = period;
        this.closedState.page = 1;
        this.updateQuickFilterButtons();
        this.toggleRangeVisibility();
        this.renderClosedSessions();
      });
    });
    this.closeResendBtn?.addEventListener('click', () => this.closeResendModal());
    this.cancelResendBtn?.addEventListener('click', () => this.closeResendModal());
    this.resendModal?.addEventListener('click', (event) => {
      if (event.target === this.resendModal) this.closeResendModal();
    });
    this.resendForm?.addEventListener('submit', (event) => void this.handleResendSubmit(event));
  }

  private async loadClosedSessions(): Promise<void> {
    if (!this.closedList) return;
    this.closedList.replaceChildren(
      createFragment('<p class="loading">Cargando órdenes cerradas...</p>')
    );
    try {
      const normalizedRole =
        window.APP_DATA?.normalized_role || window.APP_DATA?.employee_role || '';
      const isCashier = normalizedRole === 'cashier';
      const isAdmin = normalizedRole === 'super_admin' || normalizedRole === 'admin_roles';
      const endpoint = isCashier || isAdmin ? '/api/sessions/closed' : '/api/sessions/paid-recent';
      const data = await this.requestJSON<SessionResponse<ClosedSession>>(endpoint);
      const payload = this.unwrapResponse<SessionResponse<ClosedSession>>(data);
      this.closedData = payload.closed_sessions || payload.sessions || [];
      this.closedState.page = 1;
      this.renderClosedSessions();
    } catch (error) {
      console.error('[Sessions] closed', error);
      this.closedList.replaceChildren(
        createFragment('<p style="color:#ef4444;">Error al cargar órdenes cerradas</p>')
      );
    }
  }

  private renderClosedSessions(): void {
    if (!this.closedList) return;
    const filtered = this.getClosedFiltered();
    const totalPages = Math.max(1, Math.ceil(filtered.length / this.closedState.pageSize));
    this.closedState.page = Math.min(this.closedState.page, totalPages);
    if (!filtered.length) {
      this.closedList.replaceChildren(
        createFragment(`
                <tr>
                    <td colspan="7" style="text-align:center; padding: 1.25rem; color:#94a3b8;">
                        No hay órdenes cerradas para este filtro.
                    </td>
                </tr>`)
      );
      if (this.closedPagination) this.closedPagination.replaceChildren();
      return;
    }
    const start = (this.closedState.page - 1) * this.closedState.pageSize;
    const pageItems = filtered.slice(start, start + this.closedState.pageSize);
    this.closedList.replaceChildren(
      createFragment(pageItems.map((session) => this.buildClosedRow(session)).join(''))
    );
    if (this.capabilities.canReprint) {
      this.closedList.querySelectorAll<HTMLButtonElement>('button[data-reprint]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const id = btn.dataset.reprint;
          if (id) void this.reprintTicket(id);
        });
      });
      this.closedList.querySelectorAll<HTMLButtonElement>('button[data-resend]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const id = btn.dataset.resend;
          const email = normalizeCustomerEmail(btn.dataset.email);
          this.openResendModal(id, email);
        });
      });
    }
    this.renderClosedPagination(filtered.length);
  }

  private renderClosedPagination(totalItems: number): void {
    if (!this.closedPagination) return;
    const totalPages = Math.max(1, Math.ceil(totalItems / this.closedState.pageSize));
    if (totalPages <= 1) {
      this.closedPagination.replaceChildren();
      return;
    }
    let pagesHtml = '';
    for (let i = 1; i <= totalPages; i += 1) {
      pagesHtml += `<button class="pagination__page ${
        i === this.closedState.page ? 'active' : ''
      }" data-page="${i}">${i}</button>`;
    }
    this.closedPagination.replaceChildren(
      createFragment(`
            <div class="pagination">
                <button class="pagination__btn ${this.closedState.page === 1 ? 'disabled' : ''}" data-page="${
                  this.closedState.page - 1
                }" ${this.closedState.page === 1 ? 'disabled' : ''}>← Anterior</button>
                <div class="pagination__pages">${pagesHtml}</div>
                <button class="pagination__btn ${this.closedState.page === totalPages ? 'disabled' : ''}" data-page="${
                  this.closedState.page + 1
                }" ${this.closedState.page === totalPages ? 'disabled' : ''}>Siguiente →</button>
                <div class="pagination__info">Mostrando ${(this.closedState.page - 1) * this.closedState.pageSize + 1}-${Math.min(
                  this.closedState.page * this.closedState.pageSize,
                  totalItems
                )} de ${totalItems} órdenes</div>
            </div>`)
    );
    this.closedPagination
      .querySelectorAll<HTMLButtonElement>('button[data-page]')
      .forEach((btn) => {
        btn.addEventListener('click', () => {
          const page = Number(btn.dataset.page);
          if (
            !Number.isNaN(page) &&
            page >= 1 &&
            page <= totalPages &&
            page !== this.closedState.page
          ) {
            this.closedState.page = page;
            this.renderClosedSessions();
          }
        });
      });
  }

  private getClosedFiltered(): ClosedSession[] {
    const search = this.closedState.search;
    const startOfToday = new Date();
    startOfToday.setHours(0, 0, 0, 0);
    const startOfWeek = new Date(startOfToday);
    startOfWeek.setDate(startOfWeek.getDate() - startOfWeek.getDay() + 1);
    const startOfMonth = new Date(startOfToday.getFullYear(), startOfToday.getMonth(), 1);
    const rangeStart = this.closedState.rangeStart ? new Date(this.closedState.rangeStart) : null;
    const rangeEnd = this.closedState.rangeEnd ? new Date(this.closedState.rangeEnd) : null;
    if (rangeEnd) rangeEnd.setHours(23, 59, 59, 999);
    return this.closedData.filter((session) => {
      const closedAt = new Date(session.closed_at);
      let matchesPeriod = true;
      switch (this.closedState.filter) {
        case 'today':
          matchesPeriod = closedAt >= startOfToday;
          break;
        case 'week':
          matchesPeriod = closedAt >= startOfWeek;
          break;
        case 'month':
          matchesPeriod = closedAt >= startOfMonth;
          break;
        case 'range':
          if (rangeStart && rangeEnd) {
            matchesPeriod = closedAt >= rangeStart && closedAt <= rangeEnd;
          }
          break;
        default:
          matchesPeriod = true;
      }
      if (!matchesPeriod) return false;
      if (search) {
        const haystack = [
          session.id,
          session.table_number,
          session.customer_name,
          normalizeCustomerEmail(session.customer_email),
          session.payment_method,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      return true;
    });
  }

  private buildClosedRow(session: ClosedSession): string {
    const closedDate = new Date(session.closed_at);
    const formatted = closedDate.toLocaleDateString('es-MX', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
    const paymentMethod =
      session.payment_method === 'cash'
        ? 'Efectivo'
        : session.payment_method === 'card'
          ? 'Tarjeta'
          : session.payment_method === 'clip'
            ? 'Terminal'
            : session.payment_method || 'N/A';
    const showReprint = this.capabilities.canReprint;
    const sessionId = escapeHtml(String(session.id));
    const tableNumber = escapeHtml(session.table_number || 'N/A');
    const customerName = escapeHtml(session.customer_name || 'Cliente');
    const paymentLabel = escapeHtml(paymentMethod);
    const totalDisplay = escapeHtml(this.formatCurrency(session.total_amount));
    const formattedDate = escapeHtml(formatted);
    const email = escapeHtml(normalizeCustomerEmail(session.customer_email) || '');
    return `
            <tr>
                <td>#${sessionId}</td>
                <td>${tableNumber}</td>
                <td>${customerName}</td>
                <td>${paymentLabel}</td>
                <td>${totalDisplay}</td>
                <td>${formattedDate}</td>
                <td>
                    <div class="waiter-payment-group">
                        ${
                          showReprint
                            ? `<button type="button" class="btn btn--small btn--secondary" data-reprint="${sessionId}">
                                        🖨️ Reimprimir
                                   </button>
                                   <button type="button" class="btn btn--small btn--outline" data-resend="${sessionId}" data-email="${email}">
                                        ✉️ Reenviar
                                   </button>`
                            : '<span style="color:#94a3b8;">Sin acciones disponibles</span>'
                        }
                    </div>
                </td>
            </tr>`;
  }

  private async reprintTicket(sessionId: string): Promise<void> {
    if (!this.capabilities.canReprint) {
      window.showToast?.('No tienes permisos para reimprimir', 'warning');
      return;
    }
    try {
      await this.requestJSON(`/api/sessions/${sessionId}/reprint`, { method: 'POST' });
      await window.printTicket?.(sessionId);
      window.showToast?.('Ticket generado para impresión', 'success');
    } catch (error) {
      window.showToast?.((error as Error).message || 'Error al reimprimir ticket', 'error');
    }
  }

  private openResendModal(sessionId: string, email: string): void {
    if (!this.capabilities.canReprint) {
      window.showToast?.('No tienes permisos para reenviar tickets', 'warning');
      return;
    }
    if (!this.resendModal || !this.resendForm || !this.resendEmailInput) return;
    if (this.resendSessionLabel) this.resendSessionLabel.textContent = `#${sessionId}`;
    this.resendForm.dataset.sessionId = sessionId;
    const normalizedEmail = normalizeCustomerEmail(email);
    this.resendEmailInput.value = normalizedEmail;
    if (normalizedEmail) {
      this.resendEmailInput.readOnly = true;
      this.resendEmailInput.style.backgroundColor = '#f1f5f9';
    } else {
      this.resendEmailInput.readOnly = false;
      this.resendEmailInput.style.backgroundColor = '';
    }
    this.resendModal.classList.add('active');
  }

  private closeResendModal(): void {
    if (!this.resendModal || !this.resendEmailInput) return;
    this.resendModal.classList.remove('active');
    this.resendEmailInput.value = '';
    this.resendEmailInput.readOnly = false;
    this.resendEmailInput.style.backgroundColor = '';
  }

  private async handleResendSubmit(event: Event): Promise<void> {
    event.preventDefault();
    if (!this.capabilities.canReprint) {
      window.showToast?.('No tienes permisos para reenviar tickets', 'warning');
      return;
    }
    if (!this.resendForm || !this.resendEmailInput) return;
    const sessionId = this.resendForm.dataset.sessionId;
    const email = this.resendEmailInput.value.trim();
    if (!email) {
      window.showToast?.('Ingresa un correo electrónico válido', 'warning');
      return;
    }
    if (!isValidEmailFormat(email)) {
      window.showToast?.('Ingresa un correo electrónico válido', 'warning');
      return;
    }
    try {
      const response = await this.requestJSON<{ message?: string }>(
        `/api/sessions/${sessionId}/resend`,
        {
          method: 'POST',
          body: JSON.stringify({ email }),
        }
      );
      window.showToast?.(response.message || 'Ticket reenviado exitosamente', 'success');
      this.closeResendModal();
    } catch (error) {
      window.showToast?.((error as Error).message || 'Error al reenviar ticket', 'error');
    }
  }

  private updateQuickFilterButtons(): void {
    if (!this.quickFilterButtons) return;
    this.quickFilterButtons.forEach((btn) => {
      const isActive = btn.dataset.period === this.closedState.filter;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
  }

  private toggleRangeVisibility(): void {
    if (!this.dateRangeWrapper) return;
    const showRange = this.closedState.filter === 'range';
    this.dateRangeWrapper.classList.toggle('hidden', !showRange);
  }

  private formatCurrency(value?: number): string {
    const symbol = window.APP_SETTINGS?.currency_symbol || '$';
    const amount = Number(value) || 0;
    return `${symbol}${amount.toFixed(2)}`;
  }
}

const createFragment = (html: string): DocumentFragment =>
  document.createRange().createContextualFragment(html);

const escapeHtml = (value: string): string => {
  const div = document.createElement('div');
  div.textContent = value;
  return div.innerHTML;
};
