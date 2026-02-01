/**
 * Waiter UI Utilities
 * Handles feedback messages and visual notifications
 */

export function showFeedback(feedbackEl: HTMLElement | null, message: string, isError = false): void {
    if (!feedbackEl) return;
    feedbackEl.textContent = message;
    feedbackEl.classList.toggle('error', isError);
    if (!isError && message) {
        setTimeout(() => {
            if (feedbackEl?.textContent === message) {
                feedbackEl.textContent = '';
            }
        }, 4000);
    }
}

export function showNewOrderNotification(message: string, orderCount: number): void {
    // Crear notificación visual pequeña
    const notification = document.createElement('div');
    notification.className = 'waiter-new-order-notification';
    notification.innerHTML = `
        <div class="waiter-notification-icon">🔔</div>
        <div class="waiter-notification-content">
            <div class="waiter-notification-title">Nueva Orden</div>
            <div class="waiter-notification-message">${message}</div>
        </div>
    `;

    // Estilos inline para la notificación
    Object.assign(notification.style, {
        position: 'fixed',
        top: '20px',
        right: '20px',
        background: 'linear-gradient(135deg, #4CAF50 0%, #45a049 100%)',
        color: 'white',
        padding: '1rem 1.5rem',
        borderRadius: '12px',
        boxShadow: '0 8px 24px rgba(76, 175, 80, 0.4), 0 4px 8px rgba(0, 0, 0, 0.2)',
        zIndex: '10000',
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        minWidth: '280px',
        maxWidth: '400px',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        animation: 'waiter-slide-in 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)',
        opacity: '0',
        transform: 'translateX(400px)',
        transition: 'opacity 0.4s ease, transform 0.4s ease',
        cursor: 'pointer',
        border: '2px solid rgba(255, 255, 255, 0.2)'
    });

    // Estilos para el ícono
    const iconEl = notification.querySelector('.waiter-notification-icon');
    if (iconEl) {
        Object.assign((iconEl as HTMLElement).style, {
            fontSize: '1.8rem',
            lineHeight: '1',
            animation: 'waiter-bell-ring 0.5s ease-in-out 3'
        });
    }

    // Estilos para el contenido
    const contentEl = notification.querySelector('.waiter-notification-content');
    if (contentEl) {
        Object.assign((contentEl as HTMLElement).style, {
            flex: '1',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.25rem'
        });
    }

    // Estilos para el título
    const titleEl = notification.querySelector('.waiter-notification-title');
    if (titleEl) {
        Object.assign((titleEl as HTMLElement).style, {
            fontWeight: '700',
            fontSize: '1rem',
            lineHeight: '1.2'
        });
    }

    // Estilos para el mensaje
    const messageEl = notification.querySelector('.waiter-notification-message');
    if (messageEl) {
        Object.assign((messageEl as HTMLElement).style, {
            fontSize: '0.85rem',
            opacity: '0.95',
            lineHeight: '1.3'
        });
    }

    // Agregar keyframes para animaciones
    if (!document.querySelector('#waiter-notification-styles')) {
        const style = document.createElement('style');
        style.id = 'waiter-notification-styles';
        style.textContent = `
            @keyframes waiter-slide-in {
                to { opacity: 1; transform: translateX(0); }
            }
            @keyframes waiter-bell-ring {
                0%, 100% { transform: rotate(0deg); }
                10%, 30%, 50%, 70%, 90% { transform: rotate(-10deg); }
                20%, 40%, 60%, 80% { transform: rotate(10deg); }
            }
        `;
        document.head.appendChild(style);
    }

    document.body.appendChild(notification);

    // Animar entrada
    requestAnimationFrame(() => {
        notification.style.opacity = '1';
        notification.style.transform = 'translateX(0)';
    });

    // Cerrar al hacer clic
    notification.addEventListener('click', () => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(400px)';
        setTimeout(() => {
            if (notification.parentElement) {
                notification.parentElement.removeChild(notification);
            }
        }, 400);
    });

    // Auto-cerrar después de 5 segundos
    setTimeout(() => {
        if (notification.parentElement) {
            notification.style.opacity = '0';
            notification.style.transform = 'translateX(400px)';
            setTimeout(() => {
                if (notification.parentElement) {
                    notification.parentElement.removeChild(notification);
                }
            }, 400);
        }
    }, 5000);
}

export function notifyAction(feedbackEl: HTMLElement | null, message: string): void {
    if ((window as any).showToast) {
        (window as any).showToast(message, 'success');
    } else {
        showFeedback(feedbackEl, message);
    }
}

export function getTimeAgo(date: Date): string {
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return 'Hace unos segundos';
    if (seconds < 120) return 'Hace 1 minuto';
    if (seconds < 3600) return `Hace ${Math.floor(seconds / 60)} minutos`;
    if (seconds < 7200) return 'Hace 1 hora';
    return `Hace ${Math.floor(seconds / 3600)} horas`;
}

/**
 * Creates a modal dialog and returns a promise that resolves when user makes a choice
 */
export function showModal(options: {
    title: string;
    message?: string;
    buttons: Array<{
        text: string;
        value: any;
        primary?: boolean;
        danger?: boolean;
    }>;
}): Promise<any> {
    return new Promise((resolve) => {
        // Create modal overlay
        const overlay = document.createElement('div');
        overlay.className = 'payment-modal-overlay';
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
            backdrop-filter: blur(4px);
        `;

        // Create modal container
        const modal = document.createElement('div');
        modal.className = 'payment-modal';
        modal.style.cssText = `
            background: white;
            border-radius: 12px;
            padding: 2rem;
            max-width: 500px;
            width: 90%;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            animation: modal-slide-in 0.3s ease-out;
        `;

        // Create title
        const titleEl = document.createElement('h2');
        titleEl.textContent = options.title;
        titleEl.style.cssText = `
            margin: 0 0 1rem 0;
            font-size: 1.5rem;
            font-weight: 600;
            color: #333;
        `;
        modal.appendChild(titleEl);

        // Create message if provided
        if (options.message) {
            const messageEl = document.createElement('p');
            messageEl.textContent = options.message;
            messageEl.style.cssText = `
                margin: 0 0 1.5rem 0;
                font-size: 1rem;
                color: #666;
                line-height: 1.5;
            `;
            modal.appendChild(messageEl);
        }

        // Create buttons container
        const buttonsContainer = document.createElement('div');
        buttonsContainer.style.cssText = `
            display: flex;
            gap: 0.75rem;
            justify-content: flex-end;
        `;

        // Create buttons
        options.buttons.forEach((btn) => {
            const button = document.createElement('button');
            button.textContent = btn.text;
            button.type = 'button';

            let bgColor = '#6c757d';
            if (btn.primary) bgColor = '#007bff';
            if (btn.danger) bgColor = '#dc3545';

            button.style.cssText = `
                padding: 0.75rem 1.5rem;
                border: none;
                border-radius: 6px;
                font-size: 1rem;
                font-weight: 500;
                cursor: pointer;
                background: ${bgColor};
                color: white;
                transition: all 0.2s;
            `;

            button.addEventListener('mouseenter', () => {
                button.style.filter = 'brightness(1.1)';
                button.style.transform = 'translateY(-1px)';
            });

            button.addEventListener('mouseleave', () => {
                button.style.filter = 'brightness(1)';
                button.style.transform = 'translateY(0)';
            });

            button.addEventListener('click', () => {
                document.body.removeChild(overlay);
                resolve(btn.value);
            });

            buttonsContainer.appendChild(button);
        });

        modal.appendChild(buttonsContainer);
        overlay.appendChild(modal);

        // Add animation styles
        if (!document.querySelector('#payment-modal-styles')) {
            const style = document.createElement('style');
            style.id = 'payment-modal-styles';
            style.textContent = `
                @keyframes modal-slide-in {
                    from {
                        opacity: 0;
                        transform: translateY(-20px) scale(0.95);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0) scale(1);
                    }
                }
            `;
            document.head.appendChild(style);
        }

        document.body.appendChild(overlay);
    });
}

/**
 * Shows a modal to select which orders to pay from a session
 */
export function showOrderSelectionModal(orders: Array<{
    id: number;
    customer_name: string;
    total_amount: number;
    items_count: number;
    payment_status: string;
}>): Promise<number[] | null> {
    return new Promise((resolve) => {
        // Create modal overlay
        const overlay = document.createElement('div');
        overlay.className = 'order-selection-modal-overlay';
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10001;
            backdrop-filter: blur(4px);
        `;

        // Create modal container
        const modal = document.createElement('div');
        modal.className = 'order-selection-modal';
        modal.style.cssText = `
            background: white;
            border-radius: 12px;
            padding: 2rem;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            animation: modal-slide-in 0.3s ease-out;
        `;

        // Create title
        const titleEl = document.createElement('h2');
        titleEl.textContent = 'Seleccionar órdenes a cobrar';
        titleEl.style.cssText = `
            margin: 0 0 1rem 0;
            font-size: 1.5rem;
            font-weight: 600;
            color: #333;
        `;
        modal.appendChild(titleEl);

        // Create instructions
        const instructionsEl = document.createElement('p');
        instructionsEl.textContent = 'Por defecto se cobrarán todas las órdenes. Desmarca las que no quieras incluir:';
        instructionsEl.style.cssText = `
            margin: 0 0 1.5rem 0;
            font-size: 0.95rem;
            color: #666;
        `;
        modal.appendChild(instructionsEl);

        // Create orders list
        const ordersList = document.createElement('div');
        ordersList.style.cssText = `
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            margin-bottom: 1.5rem;
        `;

        // Filter out already paid orders
        const unpaidOrders = orders.filter(order => order.payment_status !== 'paid');

        unpaidOrders.forEach((order) => {
            const orderItem = document.createElement('label');
            orderItem.style.cssText = `
                display: flex;
                align-items: center;
                padding: 1rem;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.2s;
                background: white;
            `;

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = true;
            checkbox.dataset.orderId = order.id.toString();
            checkbox.style.cssText = `
                width: 20px;
                height: 20px;
                margin-right: 1rem;
                cursor: pointer;
            `;

            const orderInfo = document.createElement('div');
            orderInfo.style.cssText = `
                flex: 1;
                display: flex;
                justify-content: space-between;
                align-items: center;
            `;

            const orderDetails = document.createElement('div');
            orderDetails.innerHTML = `
                <div style="font-weight: 600; color: #333; margin-bottom: 0.25rem;">
                    ${order.customer_name || 'Sin nombre'}
                </div>
                <div style="font-size: 0.85rem; color: #666;">
                    ${order.items_count} ${order.items_count === 1 ? 'artículo' : 'artículos'}
                </div>
            `;

            const orderAmount = document.createElement('div');
            orderAmount.textContent = `$${order.total_amount.toFixed(2)}`;
            orderAmount.style.cssText = `
                font-size: 1.25rem;
                font-weight: 700;
                color: #007bff;
            `;

            orderInfo.appendChild(orderDetails);
            orderInfo.appendChild(orderAmount);

            orderItem.appendChild(checkbox);
            orderItem.appendChild(orderInfo);

            // Hover effect
            orderItem.addEventListener('mouseenter', () => {
                orderItem.style.borderColor = '#007bff';
                orderItem.style.backgroundColor = '#f8f9fa';
            });

            orderItem.addEventListener('mouseleave', () => {
                orderItem.style.borderColor = '#e0e0e0';
                orderItem.style.backgroundColor = 'white';
            });

            ordersList.appendChild(orderItem);
        });

        modal.appendChild(ordersList);

        // Create buttons container
        const buttonsContainer = document.createElement('div');
        buttonsContainer.style.cssText = `
            display: flex;
            gap: 0.75rem;
            justify-content: flex-end;
        `;

        // Cancel button
        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = 'Cancelar';
        cancelBtn.type = 'button';
        cancelBtn.style.cssText = `
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            font-weight: 500;
            cursor: pointer;
            background: #6c757d;
            color: white;
            transition: all 0.2s;
        `;

        cancelBtn.addEventListener('click', () => {
            document.body.removeChild(overlay);
            resolve(null);
        });

        // Confirm button
        const confirmBtn = document.createElement('button');
        confirmBtn.textContent = 'Confirmar pago';
        confirmBtn.type = 'button';
        confirmBtn.style.cssText = `
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            font-weight: 500;
            cursor: pointer;
            background: #28a745;
            color: white;
            transition: all 0.2s;
        `;

        confirmBtn.addEventListener('click', () => {
            const selectedOrderIds: number[] = [];
            ordersList.querySelectorAll<HTMLInputElement>('input[type="checkbox"]:checked').forEach((cb) => {
                const orderId = Number(cb.dataset.orderId);
                if (orderId) {
                    selectedOrderIds.push(orderId);
                }
            });

            if (selectedOrderIds.length === 0) {
                alert('Debes seleccionar al menos una orden');
                return;
            }

            document.body.removeChild(overlay);
            resolve(selectedOrderIds);
        });

        buttonsContainer.appendChild(cancelBtn);
        buttonsContainer.appendChild(confirmBtn);
        modal.appendChild(buttonsContainer);
        overlay.appendChild(modal);

        document.body.appendChild(overlay);
    });
}
