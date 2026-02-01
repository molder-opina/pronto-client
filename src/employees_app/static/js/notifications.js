/**
 * NotificationManager - Handles real-time notifications via Server-Sent Events (SSE)
 * Shared implementation for both clients and employees.
 */
class NotificationManager {
    constructor(streamUrl) {
        this.streamUrl = streamUrl;
        this.eventSource = null;
        this.eventListeners = {};
        this.reconnectDelay = 3000;
        this.maxReconnectDelay = 30000;
        this.reconnectAttempts = 0;
        this.isConnected = false;
    }

    connect() {
        if (this.eventSource) {
            console.log("[NotificationManager] Already connected");
            return;
        }

        console.log("[NotificationManager] Connecting to:", this.streamUrl);

        try {
            this.eventSource = new EventSource(this.streamUrl);

            this.eventSource.onopen = () => {
                console.log("[NotificationManager] Connection established");
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.reconnectDelay = 3000;
            };

            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log("[NotificationManager] Received message:", data);
                    this.handleEvent(data);
                } catch (error) {
                    console.error("[NotificationManager] Error parsing message:", error);
                }
            };

            this.eventSource.onerror = (error) => {
                console.error("[NotificationManager] Connection error:", error);
                this.isConnected = false;

                if (this.eventSource) {
                    this.eventSource.close();
                    this.eventSource = null;
                }

                this.reconnect();
            };
        } catch (error) {
            console.error("[NotificationManager] Failed to create EventSource:", error);
            this.reconnect();
        }
    }

    reconnect() {
        this.reconnectAttempts += 1;
        const delay = Math.min(
            this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1),
            this.maxReconnectDelay
        );

        console.log(`[NotificationManager] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})...`);
        setTimeout(() => this.connect(), delay);
    }

    handleEvent(data) {
        const eventType = data.type || data.event || "notification";

        if (this.eventListeners[eventType]) {
            this.eventListeners[eventType].forEach((callback) => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`[NotificationManager] Error in event handler for ${eventType}:`, error);
                }
            });
        }

        if (this.eventListeners.all) {
            this.eventListeners.all.forEach((callback) => {
                try {
                    callback(data);
                } catch (error) {
                    console.error("[NotificationManager] Error in \"all\" event handler:", error);
                }
            });
        }

        if (data.message) {
            this.showUINotification(data);
        }
    }

    on(eventType, callback) {
        if (!this.eventListeners[eventType]) {
            this.eventListeners[eventType] = [];
        }
        this.eventListeners[eventType].push(callback);
    }

    off(eventType, callback) {
        if (!this.eventListeners[eventType]) {
            return;
        }
        this.eventListeners[eventType] = this.eventListeners[eventType].filter((cb) => cb !== callback);
    }

    showUINotification(data) {
        const container = document.getElementById("notification-container");
        if (!container) {
            return;
        }

        const notification = document.createElement("div");
        notification.className = "notification-item notification-slide-in";
        const notificationType = data.priority || data.type || "info";
        notification.classList.add(`notification-${notificationType}`);

        const icons = {
            order_status_update: "📦",
            order_ready: "✅",
            order_delivered: "🎉",
            waiter_accepted: "👍",
            info: "ℹ️",
            success: "✅",
            warning: "⚠️",
            error: "❌",
        };

        const icon = icons[data.type] || icons[notificationType] || "🔔";
        notification.innerHTML = "
            <div class=\"notification-icon\">${icon}</div>
            <div class=\"notification-content\">
                <div class=\"notification-title\">${data.title || "Notificación"}</div>
                <div class=\"notification-message\">${data.message}</div>
            </div>
            <button class=\"notification-close\" onclick=\"event.stopPropagation(); this.parentElement.remove()\">×</button>
        ";

        // Close on click anywhere
        notification.addEventListener('click', () => {
            notification.remove();
        });

        container.appendChild(notification);

        const timeout = window.APP_SETTINGS?.waiter_notification_timeout || 5000;

        setTimeout(() => {
            notification.classList.add("notification-slide-out");
            setTimeout(() => notification.remove(), 300);
        }, timeout);
    }

    disconnect() {
        console.log("[NotificationManager] Disconnecting...");
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        this.isConnected = false;
        this.eventListeners = {};
    }

    connected() {
        return this.isConnected && this.eventSource !== null;
    }
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = NotificationManager;
}

window.NotificationManager = NotificationManager;
