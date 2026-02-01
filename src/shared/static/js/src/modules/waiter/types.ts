import type { RoleCapabilities } from '../role-context';

export interface OrderItem {
  id: number;
  name: string;
  quantity: number;
  price: number;
  status: string;
  notes?: string;
  delivered_quantity: number;
  is_fully_delivered: boolean;
  delivered_at: string | null;
  delivered_by_employee_id: number | null;
  is_quick_serve?: boolean;
}

export type LegacyWorkflowStatus =
  | 'requested'
  | 'waiter_accepted'
  | 'kitchen_in_progress'
  | 'ready_for_delivery'
  | 'delivered'
  | 'cancelled'
  | 'wait_for_payment'
  | 'payed';

export type CanonicalWorkflowStatus =
  | 'new'
  | 'queued'
  | 'preparing'
  | 'ready'
  | 'delivered'
  | 'awaiting_payment'
  | 'paid'
  | 'cancelled';

export type WorkflowStatus = LegacyWorkflowStatus | CanonicalWorkflowStatus;

export interface SessionData {
  id: number;
  status: string;
  table_number?: string | null;
  notes?: string | null;
}

export interface CustomerData {
  name?: string | null;
  email?: string | null;
}

export interface WaiterOrder {
  id: number;
  session_id: number;
  workflow_status: WorkflowStatus;
  workflow_status_legacy?: LegacyWorkflowStatus;
  status_display?: string;
  session?: SessionData;
  customer?: CustomerData;
  waiter_name?: string | null;
  waiter_id?: number | null;
  waiter_notes?: string | null;
  items?: OrderItem[];
  created_at?: string;
  updated_at?: string;
}

export interface WaiterCall {
  id: number;
  session_id: number | null;
  table_number: string;
  status: string;
  created_at: string;
  notes: string | null;
  order_numbers: number[];
}

export interface ActionDescriptor {
  label: string;
  icon: string;
  endpoint: (id: number) => string;
  variant?: 'danger' | 'success' | 'warning' | 'disabled';
  capability?: keyof RoleCapabilities;
  disabled?: boolean;
}

export interface StatusInfo {
  title: string;
  hint: string;
  actions: ActionDescriptor[];
}
