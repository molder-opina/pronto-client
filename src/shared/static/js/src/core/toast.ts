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
    toast.textContent = message;
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
        pointer-events: none;
    `;
    document.body.appendChild(toast);
    activeToast = toast;
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
    });
    toastTimer = window.setTimeout(() => {
        if (!activeToast) return;
        activeToast.style.opacity = '0';
        activeToast.style.transform = 'translateY(20px)';
        window.setTimeout(() => dismissToast(), 200);
    }, 3000);
}

function dismissToast(): void {
    if (toastTimer) {
        clearTimeout(toastTimer);
        toastTimer = null;
    }
    if (activeToast?.parentElement) {
        activeToast.parentElement.removeChild(activeToast);
    }
    activeToast = null;
    const next = toastQueue.shift();
    if (next) {
        requestAnimationFrame(() => showToastGlobal(next.message, next.type));
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
