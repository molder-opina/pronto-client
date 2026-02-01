interface SocketIO {
    (...args: any[]): any;
}

interface WaiterCallPayload {
    id?: number;
    call_id?: number;
    table_number?: string;
    session_id?: number;
    status?: string;
    created_at?: string;
    timestamp?: string;
    notes?: string;
    call_type?: string;
    order_numbers?: Array<number | string>;
    waiter_id?: number;
    waiter_name?: string;
}

interface NormalizedRequest {
    id: number;
    table_number: string;
    session_id: number | null;
    status: string;
    created_at: string;
    notes: string;
    order_numbers: number[];
    waiter_id: number | null;
    waiter_name: string | null;
}

declare global {
    interface Window {
        io?: SocketIO;
        confirmClientRequest?: (requestId: number) => void;
        WaiterPanel?: any;
        APP_DATA?: any;
        showToast?: (message: string, type?: string, title?: string) => void;
        ToastManager?: any;
    }
}

export function initEmployeeEvents(): void {
    document.addEventListener('DOMContentLoaded', () => {
        const root = document.querySelector<HTMLElement>('[data-client-requests-root]');
        const manager = new EmployeeEventsManager(root);
        manager.initialize();
    });
}

class EmployeeEventsManager {
    private clientRequests: NormalizedRequest[] = [];
    private socket: any = null;
    private isConnected = false;
    private requestsContainer: HTMLElement | null;
    private root: HTMLElement | null;
    private lastEventId = '0-0';
    private pollingInterval: number | null = null;
    private processedEvents: Set<string> = new Set();
    private static STORAGE_KEY = 'pronto_last_event_id';

    constructor(root: HTMLElement | null) {
        this.root = root;
        this.requestsContainer = document.getElementById('client-requests-list');
        // Restore last event ID from sessionStorage to avoid showing old notifications on page reload
        this.restoreLastEventId();
    }

    private restoreLastEventId(): void {
        try {
            const stored = sessionStorage.getItem(EmployeeEventsManager.STORAGE_KEY);
            const storedTimestamp = sessionStorage.getItem(EmployeeEventsManager.STORAGE_KEY + '_ts');
            const now = Date.now();

            // If we have a stored ID and it's not too old (less than 5 minutes), use it
            if (stored && stored !== '0-0' && storedTimestamp) {
                const age = now - parseInt(storedTimestamp, 10);
                if (age < 5 * 60 * 1000) { // 5 minutes
                    this.lastEventId = stored;
                    return;
                }
            }
            // Fresh session or stale data: mark that we need to skip initial events
            this.skipInitialEvents = true;
            this.sessionStartTime = now;
        } catch {
            // sessionStorage not available, start fresh
            this.skipInitialEvents = true;
            this.sessionStartTime = Date.now();
        }
    }

    private skipInitialEvents = false;
    private sessionStartTime = Date.now();

    private persistLastEventId(): void {
        try {
            sessionStorage.setItem(EmployeeEventsManager.STORAGE_KEY, this.lastEventId);
            sessionStorage.setItem(EmployeeEventsManager.STORAGE_KEY + '_ts', String(Date.now()));
        } catch {
            // sessionStorage not available
        }
    }

    initialize(): void {
        window.confirmClientRequest = (requestId: number) => {
            void this.confirmClientRequest(requestId);
        };
        document.addEventListener('employee:waiter-calls:updated', (event: Event) => {
            const calls = (event as CustomEvent<{ calls: WaiterCallPayload[] }>).detail?.calls;
            if (!Array.isArray(calls)) return;
            const normalized = calls.map((call) => this.normalizeRequest(call)).filter(Boolean) as NormalizedRequest[];
            this.renderClientRequests(normalized);
        });
        this.initializeClientRequests();
        // SocketIO disabled in favor of Redis polling
        // void this.initializeSocket();
        // Start polling Redis stream for realtime events
        this.startRealtimePolling();
    }

    private startRealtimePolling(): void {
        // Poll every 3 seconds for new events
        this.pollingInterval = window.setInterval(() => {
            void this.pollRealtimeEvents();
        }, 3000);
        // Initial poll
        void this.pollRealtimeEvents();
    }

    private async pollRealtimeEvents(): Promise<void> {
        try {
            const response = await fetch(`/api/realtime/events?after_id=${this.lastEventId}&limit=50`);
            if (!response.ok) return;

            const data = await response.json();
            const events = data.events || [];

            if (data.last_id) {
                this.lastEventId = data.last_id;
                // Persist to sessionStorage so notifications don't repeat on page reload
                this.persistLastEventId();
            }

            // On fresh session, skip showing notifications for existing events
            // Just save the position and wait for new events
            if (this.skipInitialEvents) {
                this.skipInitialEvents = false;
                return;
            }

            for (const event of events) {
                // Avoid processing duplicates
                const eventKey = `${event.type}-${event.timestamp}`;
                if (this.processedEvents.has(eventKey)) continue;
                this.processedEvents.add(eventKey);

                // Limit processed events cache size
                if (this.processedEvents.size > 500) {
                    const arr = Array.from(this.processedEvents);
                    this.processedEvents = new Set(arr.slice(-250));
                }

                // Handle different event types
                this.handleRealtimeEvent(event);
            }
        } catch (error) {
            // Silent fail - polling will retry
        }
    }

    private handleRealtimeEvent(event: any): void {
        const eventType = event.type || '';
        const eventData = event.payload || event.data || event;

        switch (eventType) {
            case 'staff.admin_call':
                this.handleAdminCallNotification(eventData);
                break;
            case 'staff.supervisor_call':
                this.handleSupervisorCallNotification(eventData);
                break;
            case 'staff.waiter_call':
                this.handleWaiterCallNotification(eventData);
                this.upsertClientRequestFromSocket(eventData);
                break;
            case 'orders.new':
                this.handleNewOrderNotification(eventData);
                break;
            case 'orders.status_changed':
                this.handleOrderStatusNotification(eventData);
                break;
        }
    }

    private async initializeSocket(): Promise<void> {
        await this.ensureSocketIO();
        if (this.isConnected || typeof window.io === 'undefined') return;
        try {
            this.socket = window.io({
                transports: ['websocket', 'polling'],
                reconnection: true,
                reconnectionAttempts: 5,
                reconnectionDelay: 1000
            });
            this.socket.on('connect', () => {
                this.isConnected = true;
                this.socket.emit('join_employees');
            });
            this.socket.on('disconnect', () => {
                this.isConnected = false;
            });
            this.socket.on('new_order', (data: any) => this.handleNewOrderNotification(data));
            this.socket.on('order_status_changed', (data: any) => this.handleOrderStatusNotification(data));
            this.socket.on('waiter_call', (data: WaiterCallPayload) => {
                this.handleWaiterCallNotification(data);
                this.upsertClientRequestFromSocket(data);
            });
            this.socket.on('supervisor_call', (data: any) => this.handleSupervisorCallNotification(data));
        } catch (error) {
            console.error('[EmployeeEvents] socket error', error);
        }
    }

    private ensureSocketIO(): Promise<void> {
        if (typeof window.io !== 'undefined') {
            return Promise.resolve();
        }
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://cdn.socket.io/4.5.4/socket.io.min.js';
            script.onload = () => resolve();
            script.onerror = () => reject(new Error('No se pudo cargar Socket.IO'));
            document.head.appendChild(script);
        });
    }

    private initializeClientRequests(): void {
        if (window.WaiterPanel && typeof window.WaiterPanel.getPendingCalls === 'function') {
            const calls = window.WaiterPanel.getPendingCalls();
            if (Array.isArray(calls) && calls.length) {
                const normalized = calls.map((call) => this.normalizeRequest(call)).filter(Boolean) as NormalizedRequest[];
                this.renderClientRequests(normalized);
            }
        }
        void this.loadClientRequests();
    }

    private async loadClientRequests(): Promise<void> {
        if (!this.requestsContainer) return;
        try {
            const response = await fetch('/api/waiter-calls/pending');
            const data = await response.json();
            const calls = Array.isArray(data.waiter_calls) ? data.waiter_calls : [];
            const normalized = calls.map((call: WaiterCallPayload) => this.normalizeRequest(call)).filter(Boolean) as NormalizedRequest[];
            this.renderClientRequests(normalized);
        } catch (error) {
            console.error('[EmployeeEvents] load requests', error);
            this.requestsContainer.innerHTML = '<p class="no-requests">Error al cargar solicitudes</p>';
        }
    }

    private normalizeRequest(payload: WaiterCallPayload): NormalizedRequest | null {
        if (!payload) return null;
        const id = Number(payload.call_id || payload.id);
        if (!id) return null;
        const orders = Array.isArray(payload.order_numbers)
            ? payload.order_numbers.map((num) => Number(num)).filter((value) => !Number.isNaN(value))
            : [];
        const createdAt = payload.created_at || payload.timestamp || new Date().toISOString();
        return {
            id,
            table_number: payload.table_number || 'N/A',
            session_id: payload.session_id ?? null,
            status: payload.status || 'pending',
            created_at: createdAt,
            notes: payload.call_type || payload.notes || '',
            order_numbers: orders,
            waiter_id: payload.waiter_id ?? null,
            waiter_name: payload.waiter_name ?? null
        };
    }

    private renderClientRequests(requests: NormalizedRequest[]): void {
        if (!this.requestsContainer) return;
        this.clientRequests = requests;
        if (!requests.length) {
            this.requestsContainer.innerHTML = '<p class="no-requests">Sin solicitudes pendientes</p>';
            return;
        }
        this.requestsContainer.innerHTML = requests
            .map((request) => {
                const createdAt = new Date(request.created_at);
                const minutesAgo = Math.floor((Date.now() - createdAt.getTime()) / 60000);
                const timeText =
                    minutesAgo < 1 ? 'Ahora mismo' : minutesAgo === 1 ? 'Hace 1 minuto' : `Hace ${minutesAgo} minutos`;
                const isUrgent = minutesAgo >= 5;
                const notes = (request.notes || '').toLowerCase();
                let typeIcon = '👋';
                let typeText = 'Llamar mesero';
                if (notes.includes('cuenta') || notes.includes('pagar') || notes === 'checkout_request') {
                    typeIcon = '💳';
                    typeText = 'Solicitud de cuenta';
                } else if (notes.includes('ayuda')) {
                    typeIcon = '🆘';
                    typeText = 'Necesita ayuda';
                }
                const waiterLabel = request.waiter_name ? `👤 ${request.waiter_name}` : '⚠️ Sin asignar';
                return `
                    <div class="request-card ${isUrgent ? 'request-card--urgent' : ''}" data-request-id="${request.id
                    }">
                        <div class="request-card__icon">${typeIcon}</div>
                        <div class="request-card__content">
                            <p class="request-card__table">Mesa ${request.table_number}</p>
                            <p class="request-card__type">${typeText}</p>
                            <p class="request-card__meta">${waiterLabel}</p>
                            <p class="request-card__time">${timeText}</p>
                        </div>
                        <div class="request-card__action">
                            <button data-confirm-request="${request.id}">Atender</button>
                        </div>
                    </div>`;
            })
            .join('');
        this.requestsContainer
            .querySelectorAll('[data-confirm-request]')
            .forEach((btn) =>
                btn.addEventListener('click', () => {
                    const id = Number((btn as HTMLElement).getAttribute('data-confirm-request'));
                    void this.confirmClientRequest(id);
                })
            );
    }

    private upsertClientRequestFromSocket(payload: WaiterCallPayload): void {
        const request = this.normalizeRequest(payload);
        if (!request) return;
        const index = this.clientRequests.findIndex((item) => item.id === request.id);
        const isPending = request.status === 'pending';
        if (!isPending) {
            if (index !== -1) {
                this.clientRequests.splice(index, 1);
                this.renderClientRequests(this.clientRequests);
            }
            return;
        }
        if (index === -1) {
            this.clientRequests.unshift(request);
        } else {
            this.clientRequests[index] = { ...this.clientRequests[index], ...request };
        }
        this.renderClientRequests(this.clientRequests);
    }

    private async confirmClientRequest(requestId: number): Promise<void> {
        if (!requestId) return;
        try {
            const response = await fetch(`/api/waiter-calls/${requestId}/confirm`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ employee_id: window.APP_DATA?.employee_id || null })
            });
            if (!response.ok) throw new Error('No se pudo confirmar la solicitud');
            this.clientRequests = this.clientRequests.filter((request) => request.id !== requestId);
            this.renderClientRequests(this.clientRequests);
            window.showToast?.('Solicitud atendida correctamente', 'info');
        } catch (error) {
            console.error('[EmployeeEvents] confirm', error);
            window.showToast?.('Error al confirmar la solicitud', 'warning');
        }
    }

    private async handleNewOrderNotification(data: any): Promise<void> {
        const { order_id, table_number } = data;

        // Validate the order exists before showing notification
        if (order_id) {
            try {
                const response = await fetch(`/api/orders/${order_id}`, {
                    method: 'HEAD',
                    credentials: 'include'
                });
                if (!response.ok) {
                    console.log(`[EmployeeEvents] Order #${order_id} no longer exists, skipping notification`);
                    return;
                }
            } catch {
                // If we can't verify, still show the notification but refresh orders
                console.log(`[EmployeeEvents] Could not verify order #${order_id}, proceeding with notification`);
            }
        }

        this.showDesktopNotification('Nuevo Pedido', `Mesa ${table_number || 'desconocida'} - Pedido #${order_id}`, 'new_order');
        this.playNotificationSound();
        window.showToast?.(`🔔 Nuevo pedido #${order_id} - Mesa ${table_number || 'N/A'}`, 'info');
        setTimeout(() => {
            if (typeof (window as any).refreshOrders === 'function') {
                (window as any).refreshOrders();
            }
        }, 1000);
    }

    private handleOrderStatusNotification(data: any): void {
        const labels: Record<string, string> = {
            pending: 'Pendiente',
            confirmed: 'Confirmado',
            in_kitchen: 'En cocina',
            ready: 'Listo',
            delivered: 'Entregado',
            cancelled: 'Cancelado',
            requested: 'Solicitada',
            waiter_accepted: 'Aceptada',
            kitchen_in_progress: 'En cocina',
            ready_for_delivery: 'Lista para entregar'
        };
        const statusLabel = labels[data.status] || data.status || 'Actualizado';
        window.showToast?.(`📋 Pedido #${data.order_id}: ${statusLabel}`, 'info');

        // Actualizar inmediatamente el estado de la orden en el DOM si existe
        if (data.order_id && data.status) {
            void this.updateOrderStatusInDOM(data.order_id, data.status);
        }

        setTimeout(() => {
            if (typeof (window as any).refreshOrders === 'function') {
                (window as any).refreshOrders();
            }
        }, 500);
    }

    private updateOrderStatusInDOM(orderId: number, newStatus: string): void {
        // Usar la función global de orders-board si está disponible
        if (typeof (window as any).updateOrderStatusFromEvent === 'function') {
            (window as any).updateOrderStatusFromEvent(orderId, newStatus);
        } else {
            // Fallback: actualizar directamente el dataset
            const card = document.querySelector(`[data-order-id="${orderId}"], [data-orderid="${orderId}"]`) as HTMLElement;
            if (card) {
                card.dataset.status = newStatus;
            }
            const row = document.querySelector(`tr[data-order-id="${orderId}"], tr[data-orderid="${orderId}"]`) as HTMLElement;
            if (row) {
                row.dataset.status = newStatus;
            }
        }
    }

    private handleWaiterCallNotification(data: WaiterCallPayload): void {
        const notes = (data.call_type || data.notes || '').toLowerCase();
        const isCheckout = notes.includes('cuenta') || notes.includes('pagar') || notes === 'checkout_request';
        const message = isCheckout
            ? `La mesa ${data.table_number} solicitó la cuenta`
            : `La mesa ${data.table_number} solicita atención`;
        this.showDesktopNotification(isCheckout ? 'Solicitud de cuenta' : 'Llamada de mesa', message, 'waiter_call');
        this.playNotificationSound(true);
        window.showToast?.(`${isCheckout ? '💳' : '🔔'} ${message}`, isCheckout ? 'info' : 'warning');
    }

    private handleAdminCallNotification(data: any): void {
        const role = window.APP_DATA?.employee_role || 'staff';
        // Only admins/system should see these notifications
        const allowed = ['system', 'admin'];
        if (!allowed.includes(role)) return;

        let message = `${data.sender_name || 'Alguien'} (${data.sender_role || 'Staff'}) solicita ayuda`;
        if (data.message) message = `${data.sender_name}: ${data.message}`;

        this.showDesktopNotification('🚨 Llamada Administrativa', message, 'admin_call');
        this.playNotificationSound(true);
        window.showToast?.(message, 'error', 'LLAMADA ADMIN');

        // Visual feedback on the bell
        const bellIcon = document.querySelector('.notification-bell');
        bellIcon?.classList.add('ringing');
        setTimeout(() => bellIcon?.classList.remove('ringing'), 4000);
    }

    private handleSupervisorCallNotification(data: any): void {
        const role = window.APP_DATA?.employee_role || 'staff';
        const allowed = ['super_admin', 'admin_roles', 'supervisor'];
        if (!allowed.includes(role)) return;
        let message = `${data.waiter_name || 'Un mesero'} solicita ayuda`;
        if (data.table_number) message += ` (Mesa ${data.table_number})`;
        if (data.order_id) message += ` - Pedido #${data.order_id}`;
        this.showDesktopNotification('🔔 Llamada de Supervisor', message, 'supervisor_call');
        this.playNotificationSound(true);
        window.showToast?.(`🚨 ${message}`, 'warning');
        const bellIcon = document.querySelector('.notification-bell');
        bellIcon?.classList.add('ringing');
        setTimeout(() => bellIcon?.classList.remove('ringing'), 3000);
    }

    private static audioContext: AudioContext | null = null;
    private static initAudioContext(): AudioContext | null {
        try {
            if (this.audioContext) return this.audioContext;

            const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
            if (!AudioContextClass) {
                console.warn('[EmployeeEvents] AudioContext not supported');
                return null;
            }

            this.audioContext = new AudioContextClass();
            return this.audioContext;
        } catch (error) {
            console.warn('[EmployeeEvents] Failed to create AudioContext:', error);
            return null;
        }
    }

    private audioContextInstance: AudioContext | null = null;

    private initAudioContext(): AudioContext | null {
        try {
            if (this.audioContextInstance) return this.audioContextInstance;

            const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
            if (!AudioContextClass) {
                console.warn('[EmployeeEvents] AudioContext not supported');
                return null;
            }

            this.audioContextInstance = new AudioContextClass();
            return this.audioContextInstance;
        } catch (error) {
            console.warn('[EmployeeEvents] Failed to create AudioContext:', error);
            return null;
        }
    }

    private playNotificationSound(urgent = false): void {
        try {
            const audioContext = this.initAudioContext();
            if (!audioContext) {
                console.warn('[EmployeeEvents] Cannot play sound - AudioContext not available');
                return;
            }
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            if (urgent) {
                oscillator.frequency.value = 1000;
                gainNode.gain.setValueAtTime(0.4, audioContext.currentTime);
                gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.2);
                oscillator.start(audioContext.currentTime);
                oscillator.stop(audioContext.currentTime + 0.2);
                const osc2 = audioContext.createOscillator();
                const gain2 = audioContext.createGain();
                osc2.connect(gain2);
                gain2.connect(audioContext.destination);
                osc2.frequency.value = 1200;
                gain2.gain.setValueAtTime(0.4, audioContext.currentTime + 0.3);
                gain2.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);
                osc2.start(audioContext.currentTime + 0.3);
                osc2.stop(audioContext.currentTime + 0.5);
            } else {
                oscillator.frequency.value = 800;
                oscillator.type = 'sine';
                gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
                gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);
                oscillator.start(audioContext.currentTime);
                oscillator.stop(audioContext.currentTime + 0.5);
            }
        } catch (error) {
            console.log('[EmployeeEvents] audio error', error);
        }
    }

    private showDesktopNotification(title: string, body: string, tag: string): void {
        if (!('Notification' in window)) return;
        const show = () => {
            try {
                const notification = new Notification(title, {
                    body,
                    icon: '/static/favicon.ico',
                    badge: '/static/favicon.ico',
                    tag
                });
                notification.onclick = () => {
                    window.focus();
                    notification.close();
                };
            } catch (error) {
                console.warn('[EmployeeEvents] notification error', error);
            }
        };
        if (Notification.permission === 'granted') {
            show();
            return;
        }
        if (Notification.permission !== 'denied') {
            Notification.requestPermission().then((permission) => {
                if (permission === 'granted') show();
            });
        }
    }

    public static async callAdmin(message: string = ''): Promise<void> {
        try {
            const response = await fetch('/api/notifications/call-admin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            });

            if (response.ok) {
                window.showToast?.('Administrador notificado', 'success');
            } else {
                throw new Error('Error al notificar al administrador');
            }
        } catch (error) {
            console.error('[EmployeeEvents] callAdmin error', error);
            window.showToast?.('No se pudo llamar al administrador', 'error');
        }
    }
}

// Global utility export
(window as any).callAdmin = (message: string = '') => {
    return EmployeeEventsManager.callAdmin(message);
};
