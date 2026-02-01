import type { WorkflowStatus, StatusInfo, ActionDescriptor } from './types';

export const STATUS_INFO: Record<WorkflowStatus, StatusInfo> = {
  new: {
    title: 'Esperando mesero',
    hint: 'Sin asignar',
    actions: [
      {
        label: 'Aceptar orden',
        icon: '✅',
        endpoint: (id) => `/api/orders/${id}/accept`,
        variant: 'success',
        capability: 'canCommandItems',
      },
    ],
  },
  queued: {
    title: 'Enviando a cocina',
    hint: 'En cola',
    actions: [
      {
        label: 'Imprimir',
        icon: '🖨️',
        endpoint: (id) => `/api/orders/${id}/print`,
        capability: 'canReprint',
      },
      // Allow chefs/admins to start prep from main board
      {
        label: 'Iniciar cocina',
        icon: '🍳',
        endpoint: (id) => `/api/orders/${id}/kitchen/start`,
        variant: 'success',
        capability: 'canCommandItems',
      },
    ],
  },
  preparing: {
    title: 'En cocina',
    hint: 'Preparando',
    actions: [
      // Allow chefs/admins to mark ready
      {
        label: 'Marcar lista',
        icon: '✅',
        endpoint: (id) => `/api/orders/${id}/kitchen/ready`,
        variant: 'success',
        capability: 'canCommandItems',
      },
      // Waiter view: Disabled deliver button until ready
      {
        label: 'Entregar',
        icon: '📦',
        endpoint: (id) => `/api/orders/${id}/deliver`,
        variant: 'disabled',
        capability: 'canCommandItems',
        disabled: true,
      },
    ],
  },
  ready: {
    title: 'Listo entrega',
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
    title: 'Entregado',
    hint: 'Cobrar',
    actions: [],
  },
  awaiting_payment: {
    title: 'Esperando pago',
    hint: 'En caja',
    actions: [],
  },
  paid: {
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

export const CHECKOUT_SESSION_STATES = new Set([
  'awaiting_tip',
  'awaiting_payment',
  'awaiting_payment_confirmation',
]);
export const CHECKOUT_CALL_NOTE = 'checkout_request';
export const WAITERS_ROOM = 'join_waiters';
export const EMPLOYEES_ROOM = 'join_employees';
export const POLL_INTERVAL_MS = 2000; // Poll every 2 seconds for faster order updates

export function formatStatus(status: WorkflowStatus): string {
  const map: Partial<Record<WorkflowStatus, string>> = {
    new: 'Esperando mesero',
    queued: 'Enviando a cocina',
    preparing: 'En cocina',
    ready: 'Listo entrega',
    awaiting_payment: 'Esperando pago',
    paid: 'Pagada',
    delivered: 'Entregado',
    cancelled: 'Cancelada',
  };
  return map[status] || status;
}
