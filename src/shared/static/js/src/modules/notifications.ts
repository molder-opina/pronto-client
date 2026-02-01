/**
 * Notifications Module
 * Handles visual notifications for the application.
 */

export function showNewOrderNotification(message: string, duration: number = 3000): void {
    // Check if styles already exist
    if (!document.querySelector('#waiter-notification-styles')) {
        const style = document.createElement('style');
        style.id = 'waiter-notification-styles';
        style.textContent = `
            @keyframes waiter-slide-in {
                from { opacity: 0; transform: translateX(400px); }
                to { opacity: 1; transform: translateX(0); }
            }
            @keyframes waiter-bell-ring {
                0%, 100% { transform: rotate(0deg); }
                10%, 30%, 50%, 70%, 90% { transform: rotate(-10deg); }
                20%, 40%, 60%, 80% { transform: rotate(10deg); }
            }
            .waiter-new-order-notification {
                position: fixed;
                top: 20px;
                right: 20px;
                background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
                color: white;
                padding: 1rem 1.5rem;
                border-radius: 12px;
                box-shadow: 0 8px 24px rgba(76, 175, 80, 0.4), 0 4px 8px rgba(0, 0, 0, 0.2);
                z-index: 10000;
                display: flex;
                align-items: center;
                gap: 0.75rem;
                min-width: 280px;
                max-width: 400px;
                font-family: system-ui, -apple-system, sans-serif;
                animation: waiter-slide-in 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
                opacity: 0;
                transform: translateX(400px);
                transition: opacity 0.4s ease, transform 0.4s ease;
                cursor: pointer;
                border: 2px solid rgba(255, 255, 255, 0.2);
            }
            .waiter-notification-icon {
                font-size: 1.8rem;
                line-height: 1;
                animation: waiter-bell-ring 0.5s ease-in-out 3;
            }
            .waiter-notification-content {
                flex: 1;
                display: flex;
                flex-direction: column;
                gap: 0.25rem;
            }
            .waiter-notification-title {
                font-weight: 700;
                font-size: 1rem;
                line-height: 1.2;
            }
            .waiter-notification-message {
                font-size: 0.85rem;
                opacity: 0.95;
                line-height: 1.3;
            }
        `;
        document.head.appendChild(style);
    }

    const notification = document.createElement('div');
    notification.className = 'waiter-new-order-notification';
    notification.innerHTML = `
        <div class="waiter-notification-icon">🔔</div>
        <div class="waiter-notification-content">
            <div class="waiter-notification-title">Nueva Orden</div>
            <div class="waiter-notification-message">${message}</div>
        </div>
    `;

    document.body.appendChild(notification);

    // Animate entry
    requestAnimationFrame(() => {
        notification.style.opacity = '1';
        notification.style.transform = 'translateX(0)';
    });

    const close = () => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(400px)';
        setTimeout(() => {
            if (notification.parentElement) {
                notification.parentElement.removeChild(notification);
            }
        }, 400);
    };

    // Close on click
    notification.addEventListener('click', close);

    // Auto-close
    setTimeout(close, duration);
}

export function notifyAction(feedbackEl: HTMLElement | null, message: string): void {
    if ((window as any).showToast) {
        (window as any).showToast(message, 'success');
    } else if (feedbackEl) {
        feedbackEl.textContent = message;
        setTimeout(() => {
            if (feedbackEl.textContent === message) {
                feedbackEl.textContent = '';
            }
        }, 4000);
    }
}
