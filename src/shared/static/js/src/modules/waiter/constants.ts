import type {
  CanonicalWorkflowStatus,
  LegacyWorkflowStatus,
  WorkflowStatus,
  StatusInfo,
  ActionDescriptor,
} from './types';

export const STATUS_INFO: Record<LegacyWorkflowStatus, StatusInfo> = {
  requested: {
    title: 'Abierta',
    hint: 'Sin mesero',
    actions: [
      {
        label: 'Aceptar',
        icon: '✅',
        endpoint: (id) => `/api/orders/${id}/accept`,
        variant: 'success',
        capability: 'canCommandItems',
      },
    ],
  },
  waiter_accepted: {
    title: 'Asignada',
    hint: 'En fila',
    actions: [
      {
        label: 'Imprimir',
        icon: '🖨️',
        endpoint: (id) => `/api/orders/${id}/print`,
        capability: 'canReprint',
      },
      // Allow chefs/admins to start prep from main board
      {
        label: 'Iniciar',
        icon: '🍳',
        endpoint: (id) => `/api/orders/${id}/kitchen/start`,
        variant: 'success',
        capability: 'canAdvanceKitchen',
      },
    ],
  },
  kitchen_in_progress: {
    title: 'Cocinando',
    hint: 'En cocina',
    actions: [
      // Allow chefs/admins to mark ready
      {
        label: 'Listo',
        icon: '✅',
        endpoint: (id) => `/api/orders/${id}/kitchen/ready`,
        variant: 'success',
        capability: 'canAdvanceKitchen',
      },
      // NOTE: Removed disabled "Entregar" button for waiters.
      // Waiters should not see any action button when order is in kitchen.
      // They can only act when order status changes to ready_for_delivery.
    ],
  },
  ready_for_delivery: {
    title: 'Lista',
    hint: 'Entregar ya',
    actions: [
      {
        label: 'Entregar',
        icon: '🚀',
        endpoint: (id) => `/api/orders/${id}/deliver`,
        variant: 'success',
        capability: 'canCommandItems',
      },
    ],
  },
  delivered: {
    title: 'Entregada',
    hint: 'Cobra',
    actions: [],
  },
  wait_for_payment: {
    title: 'Cuenta solicitada',
    hint: 'En caja',
    actions: [],
  },
  payed: {
    title: 'Pagada',
    hint: 'Finalizada',
    actions: [],
  },
  cancelled: {
    title: 'Cancelada',
    hint: 'Sin acción',
    actions: [],
  },
};

// Legacy ACTIONS for backward compatibility
export const ACTIONS: Record<LegacyWorkflowStatus, ActionDescriptor[]> = {
  requested: STATUS_INFO.requested.actions,
  waiter_accepted: STATUS_INFO.waiter_accepted.actions,
  kitchen_in_progress: STATUS_INFO.kitchen_in_progress.actions,
  ready_for_delivery: STATUS_INFO.ready_for_delivery.actions,
  delivered: [],
  wait_for_payment: [],
  payed: [],
  cancelled: [],
};

export const CHECKOUT_SESSION_STATES = new Set([
  'awaiting_tip',
  'awaiting_payment',
  'awaiting_payment_confirmation',
]);
export const CHECKOUT_CALL_NOTE = 'checkout_request';
export const WAITERS_ROOM = 'join_waiters';
export const EMPLOYEES_ROOM = 'join_employees';
export const POLL_INTERVAL_MS = 2000; // Poll every 2 seconds for faster order updates

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

export function normalizeWorkflowStatus(
  status: WorkflowStatus,
  legacy?: LegacyWorkflowStatus
): LegacyWorkflowStatus {
  if (legacy) return legacy;
  if (status in CANONICAL_TO_LEGACY) {
    return CANONICAL_TO_LEGACY[status as CanonicalWorkflowStatus];
  }
  return status as LegacyWorkflowStatus;
}

export function formatStatus(status: WorkflowStatus, legacy?: LegacyWorkflowStatus): string {
  const normalized = normalizeWorkflowStatus(status, legacy);
  const map: Partial<Record<LegacyWorkflowStatus, string>> = {
    requested: 'Abierta',
    waiter_accepted: 'Asignada',
    kitchen_in_progress: 'Cocinando',
    ready_for_delivery: 'Lista',
    wait_for_payment: 'Cuenta solicitada',
    payed: 'Pagada',
    delivered: 'Entregada',
    cancelled: 'Cancelada',
  };
  return map[normalized] || normalized;
}
