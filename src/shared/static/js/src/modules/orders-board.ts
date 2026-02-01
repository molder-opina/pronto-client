import { requestJSON } from '../core/http';
import { getCapabilitiesForRole, type RoleCapabilities } from './role-context';
import { normalizeCustomerEmail } from './email-utils';

type LegacyWorkflowStatus =
  | 'requested'
  | 'waiter_accepted'
  | 'kitchen_in_progress'
  | 'ready_for_delivery'
  | 'delivered'
  | 'wait_for_payment'
  | 'payed'
  | 'cancelled';

type CanonicalWorkflowStatus =
  | 'new'
  | 'queued'
  | 'preparing'
  | 'ready'
  | 'awaiting_payment'
  | 'paid'
  | 'delivered'
  | 'cancelled';

type WorkflowStatus = LegacyWorkflowStatus | CanonicalWorkflowStatus;

type CheckoutState = 'awaiting_tip' | 'awaiting_payment' | 'open' | 'paid' | string;

interface SessionInfo {
  id: number;
  status: CheckoutState;
  table_number?: string | null;
  notes?: string | null;
}

interface CustomerInfo {
  name?: string | null;
  email?: string | null;
}

interface OrderData {
  id: number;
  session_id: number;
  workflow_status: WorkflowStatus;
  workflow_status_legacy?: LegacyWorkflowStatus;
  status_display?: string;
  session?: SessionInfo;
  customer?: CustomerInfo;
  waiter_name?: string | null;
  waiter_notes?: string | null;
  total_amount?: number;
}

interface ApiOrderResponse extends OrderData {
  session: SessionInfo;
  customer: CustomerInfo;
}

interface ActionDescriptor {
  label: string;
  endpoint: (id: number) => string;
  method?: string;
  className?: string;
  capability?: keyof RoleCapabilities;
}

const STATUS_LABELS: Record<LegacyWorkflowStatus, string> = {
  requested: 'Esperando mesero',
  waiter_accepted: 'Enviando a cocina',
  kitchen_in_progress: 'En cocina',
  ready_for_delivery: 'Listo entrega',
  delivered: 'Entregado',
  wait_for_payment: 'Esperando pago',
  payed: 'Pagada',
  cancelled: 'Cancelada',
};

const WORKFLOW_ACTIONS: Partial<Record<LegacyWorkflowStatus, ActionDescriptor[]>> = {
  requested: [
    {
      label: 'Aceptar orden',
      endpoint: (id) => `/api/orders/${id}/accept`,
      className: 'btn--primary',
      capability: 'canCommandItems',
    },
  ],
  waiter_accepted: [
    {
      label: 'Enviar a cocina',
      endpoint: (id) => `/api/orders/${id}/kitchen/start`,
      className: 'btn--primary',
      capability: 'canCommandItems',
    },
  ],
  kitchen_in_progress: [
    {
      label: 'Marcar como lista',
      endpoint: (id) => `/api/orders/${id}/kitchen/ready`,
      className: 'btn--primary',
      capability: 'canAdvanceKitchen',
    },
  ],
  ready_for_delivery: [
    {
      label: 'Entregar al cliente',
      endpoint: (id) => `/api/orders/${id}/deliver`,
      className: 'btn--success',
      capability: 'canCommandItems',
    },
  ],
};

const TIMELINE_STEPS: LegacyWorkflowStatus[] = [
  'requested',
  'waiter_accepted',
  'kitchen_in_progress',
  'ready_for_delivery',
  'delivered',
];

const CHECKOUT_STATES: CheckoutState[] = ['awaiting_tip', 'awaiting_payment'];
const ROLE_CAPABILITIES: RoleCapabilities =
  typeof window !== 'undefined' && window.APP_DATA?.role_capabilities
    ? (window.APP_DATA.role_capabilities as RoleCapabilities)
    : getCapabilitiesForRole(window.APP_DATA?.employee_role);

const GENERIC_CUSTOMER_NAMES = new Set([
  'INVITADO',
  'CLIENTE ANONIMO',
  'CLIENTE ANÓNIMO',
  'ANONIMO',
  'ANÓNIMO',
  'CLIENTE',
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

function resolveCustomerDisplayName(customer?: CustomerInfo): string {
  if (!customer) return '';
  const name = (customer.name || '').trim();
  const email = (customer.email || '').trim();
  if (!name && email) return email;
  if (email && GENERIC_CUSTOMER_NAMES.has(name.toUpperCase())) return email;
  return name || email;
}

function parseNumber(value?: string | null): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeWorkflowStatus(
  status: WorkflowStatus | string,
  legacy?: LegacyWorkflowStatus
): LegacyWorkflowStatus {
  if (legacy) return legacy;
  if (status in CANONICAL_TO_LEGACY) {
    return CANONICAL_TO_LEGACY[status as CanonicalWorkflowStatus];
  }
  return status as LegacyWorkflowStatus;
}

function resolveStatusLabel(order: OrderData, normalizedStatus: LegacyWorkflowStatus): string {
  const display = order.status_display?.trim();
  if (display) return display;
  return STATUS_LABELS[normalizedStatus] || normalizedStatus;
}

function hydrateOrderFromCard(card: HTMLElement): OrderData {
  const dataset = card.dataset;
  return {
    id: Number(dataset.orderId),
    session_id: Number(dataset.sessionId),
    workflow_status: (dataset.status || 'requested') as WorkflowStatus,
    workflow_status_legacy: dataset.status ? (dataset.status as LegacyWorkflowStatus) : undefined,
    status_display: dataset.statusDisplay || undefined,
    session: {
      id: Number(dataset.sessionId),
      status: (dataset.sessionStatus || 'open') as CheckoutState,
      table_number: dataset.tableNumber || null,
      notes: dataset.notes || null,
    },
    customer: {
      name: dataset.customerName || '',
      email: normalizeCustomerEmail(dataset.customerEmail),
    },
    waiter_name: dataset.waiterName || '',
    waiter_notes: dataset.waiterNotes || '',
  };
}

function updateCardDataset(card: HTMLElement, order: OrderData): void {
  const displayName = resolveCustomerDisplayName(order.customer);
  const normalizedStatus = normalizeWorkflowStatus(
    order.workflow_status,
    order.workflow_status_legacy
  );
  card.dataset.status = normalizedStatus;
  if (order.status_display) {
    card.dataset.statusDisplay = order.status_display;
  }
  card.dataset.sessionStatus = order.session?.status || '';
  card.dataset.tableNumber = order.session?.table_number || '';
  card.dataset.customerName = displayName;
  card.dataset.customerEmail = normalizeCustomerEmail(order.customer?.email);
  card.dataset.waiterName = order.waiter_name || '';
  card.dataset.waiterNotes = order.waiter_notes || '';
}

function renderStatusBadge(card: HTMLElement, order: OrderData): void {
  const badge = card.querySelector<HTMLElement>('.status-badge');
  if (!badge) return;
  const normalizedStatus = normalizeWorkflowStatus(
    order.workflow_status,
    order.workflow_status_legacy
  );
  const label = resolveStatusLabel(order, normalizedStatus);
  TIMELINE_STEPS.forEach((status) => {
    badge.classList.toggle(`status-badge--${status}`, status === normalizedStatus);
  });
  badge.textContent = label;
}

function renderTimeline(card: HTMLElement, order: OrderData): void {
  const steps = card.querySelectorAll<HTMLElement>('.timeline-step');
  steps.forEach((step, index) => {
    const status = TIMELINE_STEPS[index];
    const normalizedStatus = normalizeWorkflowStatus(
      order.workflow_status,
      order.workflow_status_legacy
    );
    const normalizedIndex = TIMELINE_STEPS.indexOf(normalizedStatus);
    const isActive = normalizedIndex >= 0 && normalizedIndex >= index;
    step.classList.toggle('active', isActive && Boolean(status));
  });
}

function shouldShowCheckoutAlert(order: OrderData): boolean {
  const sessionStatus = order.session?.status || 'open';
  const normalizedStatus = normalizeWorkflowStatus(
    order.workflow_status,
    order.workflow_status_legacy
  );
  return (
    CHECKOUT_STATES.includes(sessionStatus) &&
    ['delivered', 'wait_for_payment', 'payed'].includes(normalizedStatus)
  );
}

function renderCheckoutAlert(card: HTMLElement, order: OrderData): void {
  const alert = card.querySelector<HTMLElement>('.admin-order-card__alert');
  if (!alert) return;
  alert.style.display = shouldShowCheckoutAlert(order) ? 'block' : 'none';
}

function renderActions(cell: HTMLElement, order: OrderData): void {
  cell.innerHTML = '';
  const normalizedStatus = normalizeWorkflowStatus(
    order.workflow_status,
    order.workflow_status_legacy
  );
  const actions = (WORKFLOW_ACTIONS[normalizedStatus] || []).filter(
    (action) => !action.capability || ROLE_CAPABILITIES[action.capability]
  );

  if (actions.length === 0) {
    const span = document.createElement('span');
    span.className = 'status-text';
    span.textContent = resolveStatusLabel(order, normalizedStatus);
    cell.appendChild(span);
    return;
  }

  actions.forEach((action) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className =
      `btn btn--small btn--secondary workflow-action ${action.className || ''}`.trim();
    button.dataset.orderAction = 'workflow';
    button.dataset.endpoint = action.endpoint(order.id);
    button.dataset.method = action.method || 'POST';
    button.textContent = action.label;
    cell.appendChild(button);
  });
}

function renderCard(card: HTMLElement, order: OrderData): void {
  const actionsCell = card.querySelector<HTMLElement>('.actions-cell');
  if (!actionsCell) return;
  renderActions(actionsCell, order);
  renderStatusBadge(card, order);
  renderTimeline(card, order);
  renderCheckoutAlert(card, order);
}

function updateSessionsState(order: OrderData): void {
  if (!window.SESSIONS_STATE || !order.session) return;
  const session = order.session;
  if (session.status === 'paid') {
    delete window.SESSIONS_STATE[session.id];
  } else {
    window.SESSIONS_STATE[session.id] = {
      ...(window.SESSIONS_STATE[session.id] || {}),
      ...session,
    };
  }
}

function dispatchSessionEvents(session?: SessionInfo): void {
  if (!session) return;
  document.dispatchEvent(new CustomEvent('employee:session:updated', { detail: { session } }));
  if (session.status === 'paid') {
    document.dispatchEvent(new CustomEvent('employee:session:closed', { detail: { session } }));
  }
}

function showFeedback(feedbackEl: HTMLElement | null, message: string, isError = false): void {
  if (!feedbackEl) return;
  feedbackEl.textContent = message;
  feedbackEl.classList.toggle('error', isError);
}

function removeCard(card: HTMLElement): void {
  card.classList.add('admin-order-card--removed');
  setTimeout(() => {
    card.remove();
  }, 200);
}

async function handleActionButton(
  button: HTMLButtonElement,
  card: HTMLElement,
  order: OrderData,
  feedbackEl: HTMLElement | null
): Promise<void> {
  const endpoint = button.dataset.endpoint;
  if (!endpoint) return;
  const method = button.dataset.method || 'POST';
  const employeeId = window.APP_DATA?.employee_id;

  // No validar en el DOM, confiar completamente en el backend
  button.disabled = true;
  showFeedback(feedbackEl, 'Procesando...');
  try {
    const payload = method === 'POST' ? { employee_id: employeeId } : undefined;
    const data = await requestJSON<ApiOrderResponse>(endpoint, { method, body: payload });

    // El backend puede devolver cualquier estado (waiter_accepted, ready_for_delivery, etc.)
    // dependiendo de si la orden requiere cocina o no, o si hubo auto-asignación
    const normalizedStatus = normalizeWorkflowStatus(
      data.workflow_status,
      data.workflow_status_legacy
    );
    const updatedOrder: OrderData = {
      ...order,
      ...data,
      workflow_status: normalizedStatus,
      workflow_status_legacy: normalizedStatus,
      status_display: data.status_display,
      session: data.session,
      customer: data.customer,
    };

    updateSessionsState(updatedOrder);
    dispatchSessionEvents(updatedOrder.session);
    updateCardDataset(card, updatedOrder);
    renderCard(card, updatedOrder);

    if (updatedOrder.session?.status === 'paid') {
      removeCard(card);
    }

    // Mostrar mensaje apropiado según el estado devuelto
    let message = 'Orden actualizada';
    if (endpoint.includes('/accept')) {
      const responseStatus = normalizeWorkflowStatus(
        data.workflow_status,
        data.workflow_status_legacy
      );
      if (responseStatus === 'ready_for_delivery') {
        message = 'Orden aceptada - Lista para entregar';
      } else if (responseStatus === 'waiter_accepted') {
        message = 'Orden aceptada';
      }
    }

    showFeedback(feedbackEl, message);
    if (typeof window.showToast === 'function') {
      window.showToast(message, 'success');
    }

    // Si se aceptó una orden, actualizar las mesas asignadas (auto-assign puede haber ocurrido)
    if (endpoint.includes('/accept')) {
      setTimeout(() => {
        const tableManager = (window as any).tableAssignmentManager;
        if (tableManager?.refreshAssignedTablesDisplay) {
          tableManager.refreshAssignedTablesDisplay();
        }
      }, 500);
    }
  } catch (error) {
    const errorMessage = (error as Error).message;
    showFeedback(feedbackEl, errorMessage, true);

    // Si hay un error, recargar los datos del servidor para actualizar la UI
    try {
      const response = await fetch('/api/orders?include_closed=true&include_delivered=true');
      if (response.ok) {
        const data = (await response.json()) as { orders: ApiOrderResponse[] };
        const updatedOrderData = data.orders.find((o) => o.id === order.id);
        if (updatedOrderData) {
          const normalizedStatus = normalizeWorkflowStatus(
            updatedOrderData.workflow_status,
            updatedOrderData.workflow_status_legacy
          );
          const updatedOrder: OrderData = {
            ...order,
            ...updatedOrderData,
            workflow_status: normalizedStatus,
            workflow_status_legacy: normalizedStatus,
            status_display: updatedOrderData.status_display,
            session: updatedOrderData.session,
            customer: updatedOrderData.customer,
          };
          updateCardDataset(card, updatedOrder);
          renderCard(card, updatedOrder);
          if (typeof window.showToast === 'function') {
            window.showToast('La orden fue actualizada', 'warning');
          }
        }
      }
    } catch (refreshError) {
      console.error('[orders-board] Error al actualizar orden:', refreshError);
    }
  } finally {
    button.disabled = false;
  }
}

function setupViewToggle(root: HTMLElement, list: HTMLElement): void {
  const toolbar = root.querySelector<HTMLElement>('[data-orders-view-toggle]');
  if (!toolbar) return;

  const tableView = root.querySelector<HTMLElement>('[data-orders-table-view]');
  const buttons = Array.from(
    toolbar.querySelectorAll<HTMLButtonElement>('.orders-view-toggle__btn')
  );

  buttons.forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.classList.contains('active')) return;
      buttons.forEach((peer) => peer.classList.remove('active'));
      btn.classList.add('active');
      const mode = btn.dataset.view;

      if (mode === 'table') {
        // Show table view, hide card views
        if (tableView) tableView.style.display = 'block';
        list.style.display = 'none';
        list.classList.remove('admin-orders-view--compact');
      } else {
        // Show card views, hide table
        if (tableView) tableView.style.display = 'none';
        list.style.display = 'grid';
        list.classList.toggle('admin-orders-view--compact', mode === 'compact');
      }
    });
  });
}

function hydrateOrderFromTableRow(row: HTMLElement): OrderData {
  const dataset = row.dataset;
  return {
    id: Number(dataset.orderId),
    session_id: Number(dataset.sessionId),
    workflow_status: (dataset.status || 'requested') as WorkflowStatus,
    workflow_status_legacy: dataset.status ? (dataset.status as LegacyWorkflowStatus) : undefined,
    status_display: dataset.statusDisplay || undefined,
    session: {
      id: Number(dataset.sessionId),
      status: (dataset.sessionStatus || 'open') as CheckoutState,
      table_number: dataset.tableNumber || null,
      notes: dataset.notes || null,
    },
    customer: {
      name: dataset.customerName || '',
      email: normalizeCustomerEmail(dataset.customerEmail),
    },
    waiter_name: dataset.waiterName || '',
    waiter_notes: dataset.waiterNotes || '',
  };
}

function renderTableRow(row: HTMLElement, order: OrderData): void {
  const actionsCell = row.querySelector<HTMLElement>('.actions-cell');
  if (actionsCell) {
    renderActions(actionsCell, order);
  }

  // Update status badge
  const statusBadge = row.querySelector<HTMLElement>('.table-status-badge');
  if (statusBadge) {
    const normalizedStatus = normalizeWorkflowStatus(
      order.workflow_status,
      order.workflow_status_legacy
    );
    const label = resolveStatusLabel(order, normalizedStatus);
    TIMELINE_STEPS.forEach((status) => {
      statusBadge.classList.toggle(`table-status-badge--${status}`, status === normalizedStatus);
    });
    statusBadge.textContent = label;
  }
}

function updateTableRowDataset(row: HTMLElement, order: OrderData): void {
  const displayName = resolveCustomerDisplayName(order.customer);
  const normalizedStatus = normalizeWorkflowStatus(
    order.workflow_status,
    order.workflow_status_legacy
  );
  row.dataset.status = normalizedStatus;
  if (order.status_display) {
    row.dataset.statusDisplay = order.status_display;
  }
  row.dataset.sessionStatus = order.session?.status || '';
  row.dataset.tableNumber = order.session?.table_number || '';
  row.dataset.customerName = displayName;
  row.dataset.customerEmail = normalizeCustomerEmail(order.customer?.email);
  row.dataset.waiterName = order.waiter_name || '';
  row.dataset.waiterNotes = order.waiter_notes || '';
}

function removeTableRow(row: HTMLElement): void {
  row.style.opacity = '0';
  setTimeout(() => {
    row.remove();
  }, 200);
}

async function handleTableActionButton(
  button: HTMLButtonElement,
  row: HTMLElement,
  order: OrderData,
  feedbackEl: HTMLElement | null
): Promise<void> {
  const endpoint = button.dataset.endpoint;
  if (!endpoint) return;
  const method = button.dataset.method || 'POST';
  const employeeId = window.APP_DATA?.employee_id;

  // No validar en el DOM, confiar completamente en el backend
  button.disabled = true;
  showFeedback(feedbackEl, 'Procesando...');
  try {
    const payload = method === 'POST' ? { employee_id: employeeId } : undefined;
    const data = await requestJSON<ApiOrderResponse>(endpoint, { method, body: payload });

    // El backend puede devolver cualquier estado (waiter_accepted, ready_for_delivery, etc.)
    // dependiendo de si la orden requiere cocina o no, o si hubo auto-asignación
    const normalizedStatus = normalizeWorkflowStatus(
      data.workflow_status,
      data.workflow_status_legacy
    );
    const updatedOrder: OrderData = {
      ...order,
      ...data,
      workflow_status: normalizedStatus,
      workflow_status_legacy: normalizedStatus,
      status_display: data.status_display,
      session: data.session,
      customer: data.customer,
    };

    updateSessionsState(updatedOrder);
    dispatchSessionEvents(updatedOrder.session);
    updateTableRowDataset(row, updatedOrder);
    renderTableRow(row, updatedOrder);

    if (updatedOrder.session?.status === 'paid') {
      removeTableRow(row);
    }

    // Mostrar mensaje apropiado según el estado devuelto
    let message = 'Orden actualizada';
    if (endpoint.includes('/accept')) {
      const responseStatus = normalizeWorkflowStatus(
        data.workflow_status,
        data.workflow_status_legacy
      );
      if (responseStatus === 'ready_for_delivery') {
        message = 'Orden aceptada - Lista para entregar';
      } else if (responseStatus === 'waiter_accepted') {
        message = 'Orden aceptada';
      }
    }

    showFeedback(feedbackEl, message);
    if (typeof window.showToast === 'function') {
      window.showToast(message, 'success');
    }

    // Si se aceptó una orden, actualizar las mesas asignadas (auto-assign puede haber ocurrido)
    if (endpoint.includes('/accept')) {
      setTimeout(() => {
        const tableManager = (window as any).tableAssignmentManager;
        if (tableManager?.refreshAssignedTablesDisplay) {
          tableManager.refreshAssignedTablesDisplay();
        }
      }, 500);
    }
  } catch (error) {
    const errorMessage = (error as Error).message;
    showFeedback(feedbackEl, errorMessage, true);

    // Si hay un error, recargar los datos del servidor para actualizar la UI
    try {
      const response = await fetch('/api/orders?include_closed=true&include_delivered=true');
      if (response.ok) {
        const data = (await response.json()) as { orders: ApiOrderResponse[] };
        const updatedOrderData = data.orders.find((o) => o.id === order.id);
        if (updatedOrderData) {
          const normalizedStatus = normalizeWorkflowStatus(
            updatedOrderData.workflow_status,
            updatedOrderData.workflow_status_legacy
          );
          const updatedOrder: OrderData = {
            ...order,
            ...updatedOrderData,
            workflow_status: normalizedStatus,
            workflow_status_legacy: normalizedStatus,
            status_display: updatedOrderData.status_display,
            session: updatedOrderData.session,
            customer: updatedOrderData.customer,
          };
          updateTableRowDataset(row, updatedOrder);
          renderTableRow(row, updatedOrder);
          if (typeof window.showToast === 'function') {
            window.showToast('La orden fue actualizada', 'warning');
          }
        }
      }
    } catch (refreshError) {
      console.error('[orders-board] Error al actualizar orden:', refreshError);
    }
  } finally {
    button.disabled = false;
  }
}

function updateOrderTimes(): void {
  const timeIndicators = document.querySelectorAll<HTMLElement>('.time-indicator');
  timeIndicators.forEach((indicator) => {
    const createdAt = indicator.dataset.createdAt;
    if (!createdAt) return;

    const createdDate = new Date(createdAt);
    const now = new Date();
    const diffMs = now.getTime() - createdDate.getTime();
    const minutes = Math.floor(diffMs / 60000);

    const timeText = indicator.querySelector('.time-text');
    if (timeText) {
      timeText.textContent = `${minutes} min`;
    }

    // Update color based on time
    indicator.classList.remove('time-indicator--warning', 'time-indicator--danger');
    if (minutes >= 20) {
      indicator.classList.add('time-indicator--danger');
    } else if (minutes >= 15) {
      indicator.classList.add('time-indicator--warning');
    }
  });
}

function setupTableDensityToggle(root: HTMLElement): void {
  const container = root.querySelector<HTMLElement>('[data-orders-table-view]');
  if (!container) return;

  const buttons = Array.from(container.querySelectorAll<HTMLButtonElement>('.table-density-btn'));

  buttons.forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.classList.contains('active')) return;
      buttons.forEach((peer) => peer.classList.remove('active'));
      btn.classList.add('active');

      const density = btn.dataset.density;
      container.classList.toggle('admin-orders-table-container--compact', density === 'compact');
    });
  });
}

function setupTableSorting(root: HTMLElement): void {
  const tableView = root.querySelector<HTMLElement>('[data-orders-table-view]');
  if (!tableView) return;

  const table = tableView.querySelector<HTMLTableElement>('.admin-orders-table');
  if (!table) return;

  const thead = table.querySelector('thead');
  if (!thead) return;

  let currentSort: { column: string; direction: 'asc' | 'desc' } = {
    column: 'time',
    direction: 'desc',
  };

  thead.addEventListener('click', (event) => {
    const th = (event.target as HTMLElement).closest<HTMLTableHeaderCellElement>('th.sortable');
    if (!th) return;

    const column = th.dataset.sort;
    if (!column) return;

    // Update sort direction
    if (currentSort.column === column) {
      currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
      currentSort.column = column;
      currentSort.direction = 'asc';
    }

    // Update header classes and icons
    const allHeaders = thead.querySelectorAll<HTMLTableHeaderCellElement>('th.sortable');
    allHeaders.forEach((header) => {
      header.classList.remove('sorted-asc', 'sorted-desc');
      const icon = header.querySelector('.sort-icon');
      if (icon) icon.textContent = '⇅';
    });

    th.classList.add(`sorted-${currentSort.direction}`);
    const icon = th.querySelector('.sort-icon');
    if (icon) icon.textContent = currentSort.direction === 'asc' ? '↑' : '↓';

    // Sort rows
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const rows = Array.from(
      tbody.querySelectorAll<HTMLTableRowElement>('.admin-orders-table__row')
    );

    rows.sort((a, b) => {
      let aValue: string | number = '';
      let bValue: string | number = '';

      switch (column) {
        case 'id':
          aValue = Number(a.dataset.orderId) || 0;
          bValue = Number(b.dataset.orderId) || 0;
          break;
        case 'table':
          aValue = a.dataset.tableNumber || '';
          bValue = b.dataset.tableNumber || '';
          break;
        case 'customer':
          aValue = a.dataset.customerName || '';
          bValue = b.dataset.customerName || '';
          break;
        case 'status':
          aValue = a.dataset.status || '';
          bValue = b.dataset.status || '';
          break;
        case 'time':
          const aTime = a.querySelector<HTMLElement>('.time-indicator');
          const bTime = b.querySelector<HTMLElement>('.time-indicator');
          const aCreated = aTime?.dataset.createdAt
            ? new Date(aTime.dataset.createdAt).getTime()
            : 0;
          const bCreated = bTime?.dataset.createdAt
            ? new Date(bTime.dataset.createdAt).getTime()
            : 0;
          aValue = aCreated;
          bValue = bCreated;
          break;
      }

      if (typeof aValue === 'number' && typeof bValue === 'number') {
        return currentSort.direction === 'asc' ? aValue - bValue : bValue - aValue;
      }

      const aStr = String(aValue).toLowerCase();
      const bStr = String(bValue).toLowerCase();

      if (currentSort.direction === 'asc') {
        return aStr < bStr ? -1 : aStr > bStr ? 1 : 0;
      } else {
        return bStr < aStr ? -1 : bStr > aStr ? 1 : 0;
      }
    });

    // Reorder DOM
    rows.forEach((row) => tbody.appendChild(row));
  });
}

// Función global para actualizar el estado de una orden cuando se recibe un evento
export async function updateOrderStatusFromEvent(
  orderId: number,
  newStatus: string
): Promise<void> {
  // Obtener los datos actualizados de la orden del servidor
  try {
    const response = await fetch('/api/orders?include_closed=true&include_delivered=true');
    if (response.ok) {
      const data = (await response.json()) as { orders: ApiOrderResponse[] };
      const orderData = data.orders.find((o) => o.id === orderId);
      if (orderData) {
        const normalizedStatus = normalizeWorkflowStatus(
          orderData.workflow_status,
          orderData.workflow_status_legacy
        );
        const updatedOrder: OrderData = {
          id: orderData.id,
          session_id: orderData.session_id,
          workflow_status: normalizedStatus,
          workflow_status_legacy: normalizedStatus,
          status_display: orderData.status_display,
          session: orderData.session,
          customer: orderData.customer,
          waiter_name: orderData.waiter_name,
          waiter_notes: orderData.waiter_notes,
          total_amount: orderData.total_amount,
        };

        // Buscar y actualizar la tarjeta de la orden
        const card = document.querySelector(
          `[data-order-id="${orderId}"], [data-orderid="${orderId}"]`
        ) as HTMLElement;
        if (card) {
          updateCardDataset(card, updatedOrder);
          renderCard(card, updatedOrder);
        }

        // Buscar y actualizar la fila de la tabla de la orden
        const row = document.querySelector(
          `tr[data-order-id="${orderId}"], tr[data-orderid="${orderId}"]`
        ) as HTMLElement;
        if (row) {
          updateTableRowDataset(row, updatedOrder);
          renderTableRow(row, updatedOrder);
        }
      }
    }
  } catch (error) {
    console.error('[orders-board] Error al actualizar orden desde evento:', error);
    // Fallback: actualizar solo el estado en el dataset
    const card = document.querySelector(
      `[data-order-id="${orderId}"], [data-orderid="${orderId}"]`
    ) as HTMLElement;
    if (card) {
      const normalizedStatus = normalizeWorkflowStatus(newStatus);
      card.dataset.status = normalizedStatus;
    }
    const row = document.querySelector(
      `tr[data-order-id="${orderId}"], tr[data-orderid="${orderId}"]`
    ) as HTMLElement;
    if (row) {
      const normalizedStatus = normalizeWorkflowStatus(newStatus);
      row.dataset.status = normalizedStatus;
    }
  }
}

// Exponer función globalmente para que employee-events.ts pueda usarla
(window as any).updateOrderStatusFromEvent = updateOrderStatusFromEvent;

export function initOrdersBoard(root: HTMLElement): void {
  const list = root.querySelector<HTMLElement>('[data-orders-list]');
  if (!list) {
    console.warn('[orders-board] No se encontró el contenedor de órdenes');
    return;
  }
  const feedbackEl = root.querySelector<HTMLElement>('[data-orders-feedback]');
  const tableView = root.querySelector<HTMLElement>('[data-orders-table-view]');

  // Initialize cards
  const cards = Array.from(list.querySelectorAll<HTMLElement>('.admin-order-card'));
  cards.forEach((card) => {
    const order = hydrateOrderFromCard(card);
    updateCardDataset(card, order);
    renderCard(card, order);
  });

  // Initialize table rows
  if (tableView) {
    const rows = Array.from(tableView.querySelectorAll<HTMLElement>('.admin-orders-table__row'));
    rows.forEach((row) => {
      const order = hydrateOrderFromTableRow(row);
      updateTableRowDataset(row, order);
      renderTableRow(row, order);
    });

    // Handle table row clicks
    tableView.addEventListener('click', (event) => {
      const target = (event.target as HTMLElement).closest<HTMLButtonElement>(
        '[data-order-action]'
      );
      if (!target) return;
      const row = target.closest<HTMLElement>('.admin-orders-table__row');
      if (!row) return;
      const order = hydrateOrderFromTableRow(row);
      void handleTableActionButton(target, row, order, feedbackEl);
    });
  }

  setupViewToggle(root, list);
  setupTableDensityToggle(root);
  setupTableSorting(root);

  // Handle card clicks
  list.addEventListener('click', (event) => {
    const target = (event.target as HTMLElement).closest<HTMLButtonElement>('[data-order-action]');
    if (!target) return;
    const card = target.closest<HTMLElement>('.admin-order-card');
    if (!card) return;
    const order = hydrateOrderFromCard(card);
    void handleActionButton(target, card, order, feedbackEl);
  });

  // Update times every 30 seconds
  updateOrderTimes();
  setInterval(updateOrderTimes, 30000);
}
