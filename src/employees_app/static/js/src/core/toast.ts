type ToastType = 'info' | 'success' | 'warning' | 'error';

interface ToastMessage {
    message: string;
    type: ToastType;
}

let toastQueue: ToastMessage[] = [];
let activeToast: HTMLElement | null = null;
let toastTimer: number | null = null;

export function showToastGlobal(message: string, type: ToastType = 'info'): void {
    if (activeToast) {
        toastQueue.push({ message, type });
        return;
    }
    requestAnimationFrame(() => createToast(message, type));
}

function createToast(message: string, type: ToastType): void {
    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.innerHTML = `
        <div style="display: flex; align-items: flex-start; gap: 12px;">
            <span style="flex: 1;">${message}</span>
            <button class="toast-close" style="background: none; border: none; color: white; opacity: 0.8; cursor: pointer; font-size: 1.2rem; line-height: 1; padding: 0;">&times;</button>
        </div>
    `;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: ${getToastColor(type)};
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        z-index: 9999;
        opacity: 0;
        transform: translateY(20px);
        transition: opacity 0.3s ease, transform 0.3s ease;
        font-size: 0.95rem;
        max-width: 320px;
        cursor: grab;
        touch-action: none; /* Prevent scrolling while dragging */
    `;

    // Close button
    const closeBtn = toast.querySelector('.toast-close');
    closeBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        dismissToast();
    });

    // Listen for ESC key to dismiss
    const escListener = (e: KeyboardEvent) => {
        if (e.key === 'Escape') dismissToast();
    };
    document.addEventListener('keydown', escListener, { once: true });

    // Swipe / Drag Logic
    let startX = 0;
    let currentX = 0;
    let isDragging = false;

    const startDrag = (clientX: number) => {
        startX = clientX;
        isDragging = true;
        toast.style.transition = 'none';
        toast.style.cursor = 'grabbing';
    };

    const moveDrag = (clientX: number) => {
        if (!isDragging) return;
        currentX = clientX;
        const diff = currentX - startX;
        toast.style.transform = `translateX(${diff}px)`;
        toast.style.opacity = `${1 - Math.abs(diff) / 300}`;
    };

    const endDrag = (clientX: number) => {
        if (!isDragging) return;
        isDragging = false;
        toast.style.cursor = 'grab';
        toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        const diff = clientX - startX;

        if (Math.abs(diff) > 100) {
            // Dismiss
            const dir = diff > 0 ? 1 : -1;
            toast.style.transform = `translateX(${dir * 100}vw)`;
            toast.style.opacity = '0';
            dismissToast();
        } else {
            // Reset
            toast.style.transform = 'translateY(0)';
            toast.style.opacity = '1';
        }
    };

    toast.addEventListener('mousedown', (e) => {
        if ((e.target as HTMLElement).closest('.toast-close')) return;
        startDrag(e.clientX);
    });
    window.addEventListener('mousemove', (e) => isDragging && moveDrag(e.clientX));
    window.addEventListener('mouseup', (e) => isDragging && endDrag(e.clientX));

    toast.addEventListener('touchstart', (e) => startDrag(e.touches[0].clientX), { passive: true });
    toast.addEventListener('touchmove', (e) => moveDrag(e.touches[0].clientX), { passive: true });
    toast.addEventListener('touchend', (e) => endDrag(e.changedTouches[0].clientX));

    document.body.appendChild(toast);
    activeToast = toast;

    // Animate in
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
    });

    // Auto dismiss
    toastTimer = window.setTimeout(() => {
        dismissToast();
    }, 5000);
}

function dismissToast(): void {
    if (toastTimer) {
        clearTimeout(toastTimer);
        toastTimer = null;
    }
    const toast = activeToast;
    activeToast = null;

    if (toast) {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        setTimeout(() => {
            if (toast.parentElement) {
                toast.parentElement.removeChild(toast);
            }
            const next = toastQueue.shift();
            if (next) {
                requestAnimationFrame(() => showToastGlobal(next.message, next.type));
            }
        }, 200);
    }
}

function getToastColor(type: ToastType): string {
    switch (type) {
        case 'success':
            return '#4CAF50';
        case 'warning':
            return '#FF9800';
        case 'error':
            return '#F44336';
        default:
            return '#2196F3';
    }
}
