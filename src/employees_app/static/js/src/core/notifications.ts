export class NotificationManager {
    private streamUrl: string;
    private eventSource: EventSource | null = null;
    private eventListeners: Record<string, Array<(data: any) => void>> = {};
    private reconnectDelay = 3000;
    private maxReconnectDelay = 30000;
    private reconnectAttempts = 0;
    private isConnected = false;

    constructor(streamUrl: string) {
        this.streamUrl = streamUrl;
    }

    connect(): void {
        if (this.eventSource) {
            console.log('[NotificationManager] Already connected');
            return;
        }
        try {
            this.eventSource = new EventSource(this.streamUrl);
            this.eventSource.onopen = () => {
                console.log('[NotificationManager] Connection established');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.reconnectDelay = 3000;
            };
            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleEvent(data);
                } catch (error) {
                    console.error('[NotificationManager] Error parsing message:', error);
                }
            };
            this.eventSource.onerror = (error) => {
                console.error('[NotificationManager] Connection error:', error);
                this.isConnected = false;
                if (this.eventSource) {
                    this.eventSource.close();
                    this.eventSource = null;
                }
                this.reconnect();
            };
        } catch (error) {
            console.error('[NotificationManager] Failed to create EventSource:', error);
            this.reconnect();
        }
    }

    disconnect(): void {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        this.isConnected = false;
        this.eventListeners = {};
    }

    connected(): boolean {
        return this.isConnected && this.eventSource !== null;
    }

    on(eventType: string, callback: (data: any) => void): void {
        if (!this.eventListeners[eventType]) {
            this.eventListeners[eventType] = [];
        }
        this.eventListeners[eventType].push(callback);
    }

    off(eventType: string, callback: (data: any) => void): void {
        if (!this.eventListeners[eventType]) return;
        this.eventListeners[eventType] = this.eventListeners[eventType].filter((cb) => cb !== callback);
    }

    private reconnect(): void {
        this.reconnectAttempts += 1;
        const delay = Math.min(
            this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1),
            this.maxReconnectDelay
        );
        console.log(`[NotificationManager] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})...`);
        window.setTimeout(() => this.connect(), delay);
    }

    private handleEvent(data: any): void {
        const eventType = data.type || data.event || 'notification';
        this.emit(eventType, data);
        this.emit('all', data);
        if (data.message) {
            this.showUINotification(data);
        }
    }

    private emit(eventType: string, data: any): void {
        const listeners = this.eventListeners[eventType];
        if (!listeners || listeners.length === 0) return;
        listeners.forEach((callback) => {
            try {
                callback(data);
            } catch (error) {
                console.error(`[NotificationManager] Error in event handler for ${eventType}:`, error);
            }
        });
    }

    private showUINotification(data: any): void {
        const container = document.getElementById('notification-container');
        if (!container) {
            return;
        }
        const notification = document.createElement('div');
        notification.className = 'notification-item notification-slide-in';
        const notificationType = data.priority || data.type || 'info';
        notification.classList.add(`notification-${notificationType}`);
        const icons: Record<string, string> = {
            order_status_update: '📦',
            order_ready: '✅',
            order_delivered: '🎉',
            waiter_accepted: '👍',
            info: 'ℹ️',
            success: '✅',
            warning: '⚠️',
            error: '❌'
        };
        const icon = icons[data.type] || icons[notificationType] || '🔔';
        notification.innerHTML = `
            <div class="notification-icon">${icon}</div>
            <div class="notification-content">
                <div class="notification-title">${data.title || 'Notificación'}</div>
                <div class="notification-message">${data.message}</div>
            </div>
            <button class="notification-close" onclick="this.parentElement.remove()">×</button>
        `;
        container.appendChild(notification);
        window.setTimeout(() => {
            notification.classList.add('notification-slide-out');
            window.setTimeout(() => notification.remove(), 300);
        }, 5000);
    }
}

export function exposeNotificationManager(): void {
    window.NotificationManager = NotificationManager;
}
