type CloseAttempt = {
    selector: string;
    description: string;
};

function isElementVisible(element: Element | null): element is HTMLElement {
    if (!element) return false;
    if (!(element instanceof HTMLElement)) return false;
    const style = window.getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
}

function hideElementById(id: string): boolean {
    const el = document.getElementById(id);
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none') return false;
    el.style.display = 'none';
    return true;
}

function removeActiveBySelector(selector: string): number {
    const nodes = Array.from(document.querySelectorAll<HTMLElement>(selector));
    let changed = 0;
    nodes.forEach((node) => {
        if (node.classList.contains('active')) {
            node.classList.remove('active');
            changed += 1;
        }
    });
    return changed;
}

function clickAllVisible(selectors: CloseAttempt[]): number {
    let clicks = 0;
    selectors.forEach(({ selector }) => {
        const nodes = Array.from(document.querySelectorAll(selector));
        nodes.forEach((node) => {
            if (!isElementVisible(node)) return;
            (node as HTMLElement).click();
            clicks += 1;
        });
    });
    return clicks;
}

function anyOverlayOpen(): boolean {
    if (document.querySelector('.modal.active')) return true;
    if (document.querySelector('.product-drawer.active')) return true;
    if (document.querySelector('.promotion-drawer.active')) return true;
    if (document.querySelector('#modifier-drawer.active, #modifier-group-drawer.active')) return true;
    const displayOverlays = ['waiter-filters-modal', 'partial-delivery-modal', 'cancel-order-modal', 'order-floating-panel'];
    return displayOverlays.some((id) => {
        const el = document.getElementById(id);
        if (!el) return false;
        return window.getComputedStyle(el).display !== 'none';
    });
}

export function closeAllFloatingOverlays(): boolean {
    if (!anyOverlayOpen()) return false;

    const closeButtons: CloseAttempt[] = [
        { selector: '#close-table-assignment', description: 'Cerrar modal asignación mesas' },
        { selector: '#cancel-table-assignment', description: 'Cancelar modal asignación mesas' },
        { selector: '#close-transfer-modal', description: 'Cerrar modal transferencia' },
        { selector: '#close-conflict-modal', description: 'Cerrar modal conflicto' },
        { selector: '#cancel-conflict-assignment', description: 'Cancelar modal conflicto' },

        { selector: '#close-product-drawer', description: 'Cerrar drawer producto' },
        { selector: '#cancel-product-btn', description: 'Cancelar drawer producto' },
        { selector: '#close-promotion-drawer', description: 'Cerrar drawer promoción' },
        { selector: '#close-coupon-drawer', description: 'Cerrar drawer cupón' },
        { selector: '#close-modifier-drawer', description: 'Cerrar drawer modificador' },
        { selector: '#close-modifier-group-drawer', description: 'Cerrar drawer grupo modificador' },

        { selector: '#close-employee-payment', description: 'Cerrar modal pago' },
        { selector: '#close-employee-tip', description: 'Cerrar modal propina' },
        { selector: '#close-employee-ticket', description: 'Cerrar modal ticket' },
        { selector: '#close-resend-ticket', description: 'Cerrar modal reenviar ticket' },
        { selector: '#close-table-modal', description: 'Cerrar modal mesa' },
        { selector: '#close-area-modal', description: 'Cerrar modal área' },
        { selector: '#close-day-periods-modal', description: 'Cerrar modal periodos' },
        { selector: '#close-employee-role-panel', description: 'Cerrar panel roles' },

        { selector: '#close-filters-btn', description: 'Cerrar filtros mesero' },
        { selector: '.waiter-filters-modal__overlay', description: 'Cerrar filtros mesero (overlay)' },

        { selector: '.partial-delivery-close', description: 'Cerrar entrega parcial' },
        { selector: '#cancel-partial-delivery', description: 'Cancelar entrega parcial' },
        { selector: '.cancel-order-close', description: 'Cerrar cancelar orden' },
        { selector: '#cancel-order-modal-close', description: 'Cerrar cancelar orden (botón)' },

        { selector: '[data-close-floating]', description: 'Cerrar panel flotante' },

        // Generic close buttons inside modals
        { selector: '.modal.active .modal-close', description: 'Cerrar modal genérico' },
        { selector: '.modal.active .btn-close', description: 'Cerrar modal genérico (btn-close)' }
    ];

    let didSomething = false;

    const clicks = clickAllVisible(closeButtons);
    if (clicks > 0) didSomething = true;

    // Fallbacks: remove active classes
    const removed =
        removeActiveBySelector('.modal.active') +
        removeActiveBySelector('.product-drawer.active') +
        removeActiveBySelector('.promotion-drawer.active') +
        removeActiveBySelector('#modifier-drawer.active, #modifier-group-drawer.active');
    if (removed > 0) didSomething = true;

    // Fallbacks: hide display:none overlays
    const hidden =
        (hideElementById('waiter-filters-modal') ? 1 : 0) +
        (hideElementById('partial-delivery-modal') ? 1 : 0) +
        (hideElementById('cancel-order-modal') ? 1 : 0) +
        (hideElementById('order-floating-panel') ? 1 : 0);
    if (hidden > 0) didSomething = true;

    return didSomething;
}

export function initGlobalEscapeToCloseOverlays(): void {
    document.addEventListener(
        'keydown',
        (event) => {
            if (event.key !== 'Escape') return;
            if (event.defaultPrevented) return;

            const closed = closeAllFloatingOverlays();
            if (!closed) return;

            event.preventDefault();
            event.stopPropagation();
        },
        true
    );
}
