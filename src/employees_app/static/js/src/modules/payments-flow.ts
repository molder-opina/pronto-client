import { requestJSON } from '../core/http';
import { isValidEmailFormat, normalizeCustomerEmail } from './email-utils';

interface Window {
    EmployeePayments: any;
    SESSIONS_STATE: any;
    showToast: (message: string, type?: 'info' | 'success' | 'warning' | 'error') => void;
}

declare var window: Window & typeof globalThis;

const toast = (message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') => {
    if (window.showToast) {
        window.showToast(message, type);
    } else {
        console.log(`[${type.toUpperCase()}] ${message}`);
    }
};

interface PaymentState {
    sessionId: number | null;
    method: string | null;
    tip: number;
}

let initialized = false;

export function initPaymentsFlow(): void {
    console.log('[PAYMENTS] initPaymentsFlow() called, document.readyState:', document.readyState);
    const init = () => {
        if (initialized) return;
        initialized = true;

        console.log('[PAYMENTS] Initializing payments flow module');

        const paymentModal = document.getElementById('employee-payment-modal');
        const paymentLabel = document.getElementById('employee-payment-session-label');
        const closePaymentBtn = document.getElementById('close-employee-payment');
        const cancelPaymentBtn = document.getElementById('cancel-employee-payment');

        const tipModal = document.getElementById('employee-tip-modal');
        const tipForm = document.getElementById('employee-tip-form') as HTMLFormElement | null;
        const tipLabel = document.getElementById('employee-tip-session-label');
        const tipButtons = Array.from(
            document.querySelectorAll<HTMLButtonElement>('#employee-tip-options-modal .tip-chip')
        );
        const closeTipBtn = document.getElementById('close-employee-tip');
        const cancelTipBtn = document.getElementById('cancel-employee-tip');

        const ticketModal = document.getElementById('employee-ticket-modal');
        const ticketForm = document.getElementById('employee-ticket-form') as HTMLFormElement | null;
        const ticketLabel = document.getElementById('employee-ticket-session-label');
        const ticketEmailInput = document.getElementById('ticket-email-input') as HTMLInputElement | null;
        const ticketDeliveryInputs = ticketForm
            ? Array.from(ticketForm.querySelectorAll<HTMLInputElement>('input[name="ticket-delivery"]'))
            : [];
        const closeTicketBtn = document.getElementById('close-employee-ticket');
        const cancelTicketBtn = document.getElementById('cancel-employee-ticket');

        console.log('[PAYMENTS] Modal elements check:');
        console.log('  - paymentModal:', paymentModal ? 'FOUND' : 'MISSING');
        console.log('  - tipModal:', tipModal ? 'FOUND' : 'MISSING');
        console.log('  - tipForm:', tipForm ? 'FOUND' : 'MISSING');
        console.log('  - ticketModal:', ticketModal ? 'FOUND' : 'MISSING');
        console.log('  - ticketForm:', ticketForm ? 'FOUND' : 'MISSING');

        if (!paymentModal || !tipModal || !tipForm || !ticketModal || !ticketForm) {
            console.warn('[PAYMENTS] No se encontraron los modales necesarios, se omite la migración.');
            return;
        }

        console.log('[PAYMENTS] All modals found, setting up payment flow');

        const state: PaymentState = {
            sessionId: null,
            method: null,
            tip: 0
        };

        const toast = (message: string, type: ToastType = 'info') => {
            if (typeof window.showToast === 'function') {
                window.showToast(message, type);
            } else {
                console.log(`[toast:${type}] ${message} `);
            }
        };

        const setTip = (value: number) => {
            state.tip = value;
            tipButtons.forEach((btn) => {
                btn.classList.toggle('active', btn.dataset.tip === String(value));
            });
        };

        const openPaymentModal = (sessionId: number, method: string = 'cash', orderId?: number, customerEmail?: string) => {
            console.log('[PAYMENTS] openPaymentModal called from window.EmployeePayments, sessionId:', sessionId, 'orderId:', orderId);
            // NOTE: sessionId is the DiningSession ID (Bill/Cuenta), NOT the Order ID
            // A single session (cuenta) can contain multiple orders (pedidos)
            // Example: Session #37 might contain Order #24, #25, #26
            state.sessionId = Number(sessionId);
            state.method = null; // Reset method, user will select
            state.tip = 0;
            if (paymentLabel) {
                // Show Session ID and optionally Order ID if specific
                paymentLabel.replaceChildren();
                const sessionSpan = document.createElement('span');
                sessionSpan.style.fontWeight = '700';
                sessionSpan.textContent = `Cuenta #${sessionId}`;
                paymentLabel.appendChild(sessionSpan);
                if (orderId) {
                    const orderSpan = document.createElement('span');
                    orderSpan.style.fontWeight = '400';
                    orderSpan.style.color = '#64748b';
                    orderSpan.textContent = `(Orden #${orderId})`;
                    paymentLabel.appendChild(document.createTextNode(' '));
                    paymentLabel.appendChild(orderSpan);
                }
            }
            // Reset to payment method selection step
            showStep('method');
            // Clear terminal form inputs
            if (terminalReference) terminalReference.value = '';
            if (terminalCardType) terminalCardType.value = '';

            // Store customer email for ticket step if provided
            if (ticketEmailInput) {
                const normalizedEmail = normalizeCustomerEmail(customerEmail);
                if (normalizedEmail) {
                    ticketEmailInput.dataset.prefilledEmail = normalizedEmail;
                } else {
                    delete ticketEmailInput.dataset.prefilledEmail;
                }
            }

            paymentModal.classList.add('active');
        };

        const closePaymentModal = () => {
            paymentModal.classList.remove('active');
        };

        const openTipModal = (sessionId: number) => {
            if (tipLabel) {
                tipLabel.textContent = `#${sessionId} `;
            }
            setTip(0);
            tipModal.classList.add('active');
        };

        const closeTipModal = () => {
            tipModal.classList.remove('active');
        };

        const openTicketModal = async (sessionId: number) => {
            // NOTE: sessionId is the DiningSession ID (Bill/Cuenta), NOT the Order ID
            // The ticket shows the complete bill for the session, including all orders
            if (ticketLabel) {
                ticketLabel.textContent = `#${sessionId} `;
            }
            ticketModal.classList.add('active');
            toggleTicketEmail();

            // Pre-fill customer email if available
            // Priority: 1. Email passed from Order Row (stored in dataset) 2. Session customer_email 3. Empty
            if (ticketEmailInput) {
                const passedEmail = normalizeCustomerEmail(ticketEmailInput.dataset.prefilledEmail);

                if (passedEmail) {
                    ticketEmailInput.value = passedEmail;
                    console.log('[PAYMENTS] Pre-filled email from Order:', passedEmail);
                } else {
                    try {
                        const sessionData = await requestJSON<{ session?: { customer_email?: string } }>(`/api/sessions/${sessionId}`);
                        const sessionEmail = normalizeCustomerEmail(sessionData?.session?.customer_email);
                        if (sessionEmail) {
                            ticketEmailInput.value = sessionEmail;
                            console.log('[PAYMENTS] Pre-filled email from Session:', sessionEmail);
                        } else {
                            ticketEmailInput.value = '';
                        }
                    } catch (error) {
                        console.warn('[PAYMENTS] Could not fetch session email:', error);
                    }
                }
            }

            const previewContainer = document.getElementById('ticket-preview-container');
            if (previewContainer) {
                previewContainer.replaceChildren(
                    createFragment('<div style="text-align: center; color: #94a3b8;">Cargando vista previa...</div>')
                );
                try {
                    const data = await requestJSON<{ ticket: string }>(`/api/sessions/${sessionId}/ticket`);
                    const pre = document.createElement('pre');
                    pre.style.whiteSpace = 'pre-wrap';
                    pre.style.fontFamily = "'Courier New', Courier, monospace";
                    pre.style.margin = '0';
                    pre.textContent = data.ticket;
                    previewContainer.replaceChildren(pre);
                } catch (error) {
                    const message = document.createElement('div');
                    message.style.color = '#ef4444';
                    message.style.textAlign = 'center';
                    message.textContent = `Error al cargar ticket: ${(error as Error).message}`;
                    previewContainer.replaceChildren(message);
                }
            }
        };

        const closeTicketModal = () => {
            ticketModal.classList.remove('active');
            if (ticketEmailInput) {
                ticketEmailInput.value = '';
                ticketEmailInput.style.display = 'none';
            }
            state.sessionId = null;
            state.method = null;
            state.tip = 0;
        };

        const toggleTicketEmail = () => {
            if (!ticketEmailInput || ticketDeliveryInputs.length === 0) return;
            const show = ticketDeliveryInputs.some((input) => input.checked && input.value === 'digital');
            ticketEmailInput.style.display = show ? 'block' : 'none';
            if (show) {
                ticketEmailInput.focus();
            }
        };

        ticketDeliveryInputs.forEach((input) => {
            input.addEventListener('change', toggleTicketEmail);
        });

        // Click outside to close logic
        [paymentModal, tipModal, ticketModal].forEach(modal => {
            if (!modal) return;
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    if (modal === paymentModal) closePaymentModal();
                    if (modal === tipModal) closeTipModal();
                    if (modal === ticketModal) closeTicketModal();
                }
            });
        });

        const printTicket = async (sessionId: number) => {
            // Open window BEFORE async fetch to prevent popup blocker
            const ticketWindow = window.open('', '_blank', 'width=420,height=700');

            if (!ticketWindow) {
                window.showToast?.('Por favor permite ventanas emergentes para imprimir el ticket', 'error');
                return;
            }

            // Show loading state in the opened window
            ticketWindow.document.write(`
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Cargando ticket...</title>
                    <meta charset="UTF-8">
                    <style>
                        body {
                            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            height: 100vh;
                            margin: 0;
                            background: #f8fafc;
                        }
                        .loading { text-align: center; color: #64748b; }
                        .spinner {
                            border: 3px solid #e2e8f0;
                            border-top: 3px solid #1e3a5f;
                            border-radius: 50%;
                            width: 40px;
                            height: 40px;
                            animation: spin 1s linear infinite;
                            margin: 0 auto 16px;
                        }
                        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                    </style>
                </head>
                <body>
                    <div class="loading">
                        <div class="spinner"></div>
                        <p>Generando ticket...</p>
                    </div>
                </body>
                </html>
            `);

            try {
                const ticket = await requestJSON<{ ticket: string; data?: any }>(`/api/sessions/${sessionId}/ticket`);
                if (ticketWindow) {
                    const restaurantName = window.APP_DATA?.restaurant_name || 'PRONTO CAFÉ';
                    const now = new Date();
                    const dateStr = now.toLocaleDateString('es-MX', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
                    const timeStr = now.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });

                    const ticketHtml = `
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <title>Ticket #${sessionId}</title>
                            <meta charset="UTF-8">
                            <style>
                                * { margin: 0; padding: 0; box-sizing: border-box; }
                                body {
                                    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
                                    padding: 0;
                                    max-width: 380px;
                                    margin: 0 auto;
                                    background: #f8fafc;
                                }
                                .ticket-container {
                                    background: white;
                                    margin: 20px;
                                    border-radius: 12px;
                                    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
                                    overflow: hidden;
                                }
                                .ticket-header {
                                    background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
                                    color: white;
                                    padding: 24px 20px;
                                    text-align: center;
                                }
                                .ticket-header h1 {
                                    font-size: 1.5rem;
                                    font-weight: 700;
                                    margin-bottom: 4px;
                                    letter-spacing: 1px;
                                }
                                .ticket-header .ticket-number {
                                    font-size: 0.9rem;
                                    opacity: 0.9;
                                }
                                .ticket-meta {
                                    background: #f1f5f9;
                                    padding: 12px 20px;
                                    display: flex;
                                    justify-content: space-between;
                                    font-size: 0.8rem;
                                    color: #64748b;
                                    border-bottom: 1px solid #e2e8f0;
                                }
                                .ticket-body {
                                    padding: 20px;
                                }
                                .ticket-info {
                                    display: grid;
                                    grid-template-columns: 1fr 1fr;
                                    gap: 12px;
                                    margin-bottom: 20px;
                                    padding-bottom: 16px;
                                    border-bottom: 2px dashed #e2e8f0;
                                }
                                .ticket-info-item {
                                    background: #f8fafc;
                                    padding: 10px 12px;
                                    border-radius: 8px;
                                }
                                .ticket-info-label {
                                    font-size: 0.7rem;
                                    color: #94a3b8;
                                    text-transform: uppercase;
                                    letter-spacing: 0.5px;
                                }
                                .ticket-info-value {
                                    font-size: 0.95rem;
                                    font-weight: 600;
                                    color: #1e293b;
                                    margin-top: 2px;
                                }
                                .ticket-items {
                                    margin-bottom: 20px;
                                }
                                .ticket-items-title {
                                    font-size: 0.75rem;
                                    color: #94a3b8;
                                    text-transform: uppercase;
                                    letter-spacing: 0.5px;
                                    margin-bottom: 12px;
                                }
                                .ticket-item {
                                    display: flex;
                                    justify-content: space-between;
                                    padding: 8px 0;
                                    border-bottom: 1px solid #f1f5f9;
                                }
                                .ticket-item:last-child { border-bottom: none; }
                                .ticket-item-name {
                                    font-size: 0.9rem;
                                    color: #334155;
                                }
                                .ticket-item-qty {
                                    color: #64748b;
                                    font-weight: 500;
                                }
                                .ticket-item-price {
                                    font-size: 0.9rem;
                                    font-weight: 600;
                                    color: #1e293b;
                                }
                                .ticket-totals {
                                    background: #f8fafc;
                                    padding: 16px;
                                    border-radius: 8px;
                                    margin-bottom: 16px;
                                }
                                .ticket-total-row {
                                    display: flex;
                                    justify-content: space-between;
                                    padding: 6px 0;
                                    font-size: 0.9rem;
                                    color: #64748b;
                                }
                                .ticket-total-row.final {
                                    border-top: 2px solid #e2e8f0;
                                    margin-top: 8px;
                                    padding-top: 12px;
                                    font-size: 1.1rem;
                                    font-weight: 700;
                                    color: #1e293b;
                                }
                                .ticket-payment {
                                    background: #ecfdf5;
                                    border: 1px solid #a7f3d0;
                                    padding: 12px 16px;
                                    border-radius: 8px;
                                    margin-bottom: 16px;
                                }
                                .ticket-payment-title {
                                    font-size: 0.7rem;
                                    color: #059669;
                                    text-transform: uppercase;
                                    letter-spacing: 0.5px;
                                }
                                .ticket-payment-method {
                                    font-size: 0.95rem;
                                    font-weight: 600;
                                    color: #047857;
                                    margin-top: 2px;
                                }
                                .ticket-payment-ref {
                                    font-size: 0.75rem;
                                    color: #64748b;
                                    margin-top: 4px;
                                    font-family: monospace;
                                }
                                .ticket-footer {
                                    text-align: center;
                                    padding: 20px;
                                    background: #f8fafc;
                                    border-top: 2px dashed #e2e8f0;
                                }
                                .ticket-footer p {
                                    font-size: 0.85rem;
                                    color: #64748b;
                                    margin-bottom: 4px;
                                }
                                .ticket-footer .thank-you {
                                    font-size: 1rem;
                                    font-weight: 600;
                                    color: #1e293b;
                                }
                                .no-print {
                                    padding: 16px 20px;
                                    background: white;
                                    border-bottom: 1px solid #e2e8f0;
                                }
                                .btn-group {
                                    display: flex;
                                    gap: 8px;
                                }
                                .btn {
                                    flex: 1;
                                    padding: 12px 16px;
                                    border: none;
                                    border-radius: 8px;
                                    font-size: 0.9rem;
                                    font-weight: 600;
                                    cursor: pointer;
                                    display: flex;
                                    align-items: center;
                                    justify-content: center;
                                    gap: 6px;
                                    transition: all 0.2s;
                                }
                                .btn-primary {
                                    background: #1e3a5f;
                                    color: white;
                                }
                                .btn-primary:hover { background: #2d5a87; }
                                .btn-secondary {
                                    background: #e2e8f0;
                                    color: #475569;
                                }
                                .btn-secondary:hover { background: #cbd5e1; }
                                .btn-download {
                                    background: #059669;
                                    color: white;
                                }
                                .btn-download:hover { background: #047857; }
                                @media print {
                                    body { background: white; }
                                    .no-print { display: none !important; }
                                    .ticket-container {
                                        margin: 0;
                                        box-shadow: none;
                                        border-radius: 0;
                                    }
                                }
                            </style>
                        </head>
                        <body>
                            <div class="no-print">
                                <div class="btn-group">
                                    <button onclick="window.print()" class="btn btn-primary">🖨️ Imprimir</button>
                                    <button onclick="downloadPDF()" class="btn btn-download">📥 PDF</button>
                                    <button onclick="window.close()" class="btn btn-secondary">✕ Cerrar</button>
                                </div>
                            </div>
                            <div class="ticket-container" id="ticket-content">
                                <div class="ticket-header">
                                    <h1>${restaurantName}</h1>
                                    <div class="ticket-number">Ticket #${sessionId}</div>
                                </div>
                                <div class="ticket-meta">
                                    <span>${dateStr}</span>
                                    <span>${timeStr}</span>
                                </div>
                                <div class="ticket-body">
                                    <div id="ticket-details">
                                        <pre style="white-space: pre-wrap; font-family: inherit; margin: 0; font-size: 0.85rem; line-height: 1.6;">${ticket.ticket}</pre>
                                    </div>
                                </div>
                                <div class="ticket-footer">
                                    <p class="thank-you">¡Gracias por su visita!</p>
                                    <p>Vuelva pronto</p>
                                </div>
                            </div>
                            <script>
                                function downloadPDF() {
                                    window.print();
                                }
                            </script>
                        </body>
                        </html>
                    `;
                    ticketWindow.document.write(ticketHtml);
                    ticketWindow.document.close();
                } else {
                    alert(ticket.ticket);
                }
            } catch (error) {
                // Close the opened window if there was an error
                if (ticketWindow && !ticketWindow.closed) {
                    ticketWindow.close();
                }
                toast((error as Error).message, 'warning');
            }
        };

        const emitSessionUpdated = (sessionId: number, status: string, sessionData?: Record<string, any>) => {
            const mergedSession = {
                id: sessionId,
                status,
                ...(sessionData || {})
            };
            if (window.SESSIONS_STATE) {
                window.SESSIONS_STATE[sessionId] = {
                    ...(window.SESSIONS_STATE[sessionId] || {}),
                    ...mergedSession
                };
            }
            document.dispatchEvent(
                new CustomEvent('employee:session:updated', {
                    detail: { session: mergedSession }
                })
            );
        };

        const notifySessionClosed = (sessionId: number) => {
            if (window.SESSIONS_STATE) {
                delete window.SESSIONS_STATE[sessionId];
            }
            document.dispatchEvent(
                new CustomEvent('employee:session:closed', {
                    detail: {
                        session: {
                            id: sessionId,
                            status: 'paid'
                        }
                    }
                })
            );
        };

        // Payment method selection buttons
        const paymentMethodButtons = Array.from(
            document.querySelectorAll<HTMLButtonElement>('.payment-method-btn')
        );

        // Payment steps
        const paymentMethodSelection = document.getElementById('payment-method-selection');
        const paymentCashConfirmation = document.getElementById('payment-cash-confirmation');
        const paymentTerminalOptions = document.getElementById('payment-terminal-options');
        const paymentStripeConfirmation = document.getElementById('payment-stripe-confirmation');
        const paymentClipConfirmation = document.getElementById('payment-clip-confirmation');

        // Navigation buttons
        const cancelPaymentMethodBtn = document.getElementById('cancel-payment-method');
        const backFromCashBtn = document.getElementById('back-from-cash');
        const confirmCashBtn = document.getElementById('confirm-cash-payment');
        const backFromTerminalBtn = document.getElementById('back-from-terminal');
        const terminalForm = document.getElementById('terminal-payment-form') as HTMLFormElement | null;
        const terminalReference = document.getElementById('terminal-reference') as HTMLInputElement | null;
        const terminalCardType = document.getElementById('terminal-card-type') as HTMLSelectElement | null;
        const terminalReceiptPhoto = document.getElementById('terminal-receipt-photo') as HTMLInputElement | null;
        const terminalPhotoBtn = document.getElementById('terminal-photo-btn') as HTMLButtonElement | null;
        const terminalPhotoPreview = document.getElementById('terminal-photo-preview') as HTMLElement | null;
        const terminalPhotoPreviewImg = document.getElementById('terminal-photo-preview-img') as HTMLImageElement | null;
        const backFromStripeBtn = document.getElementById('back-from-stripe');
        const confirmStripeBtn = document.getElementById('confirm-stripe-payment');
        const backFromClipBtn = document.getElementById('back-from-clip');
        const confirmClipBtn = document.getElementById('confirm-clip-payment');

        let terminalReceiptPhotoData: string | null = null;

        // Helper function to compress image
        const compressImage = (file: File): Promise<string> => {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = (e) => {
                    const img = new Image();
                    img.onload = () => {
                        const canvas = document.createElement('canvas');
                        let width = img.width;
                        let height = img.height;

                        // Resize to max 1200px on longest side
                        const maxSize = 1200;
                        if (width > height && width > maxSize) {
                            height = (height * maxSize) / width;
                            width = maxSize;
                        } else if (height > maxSize) {
                            width = (width * maxSize) / height;
                            height = maxSize;
                        }

                        canvas.width = width;
                        canvas.height = height;

                        const ctx = canvas.getContext('2d');
                        ctx?.drawImage(img, 0, 0, width, height);

                        // Compress to 0.7 quality (moderate quality)
                        const compressed = canvas.toDataURL('image/jpeg', 0.7);
                        resolve(compressed);
                    };
                    img.onerror = reject;
                    img.src = e.target?.result as string;
                };
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
        };

        // Terminal photo button - trigger file input
        terminalPhotoBtn?.addEventListener('click', () => {
            terminalReceiptPhoto?.click();
        });

        // Handle photo selection/capture
        terminalReceiptPhoto?.addEventListener('change', async (e) => {
            const file = (e.target as HTMLInputElement).files?.[0];
            if (!file) return;

            try {
                // Compress the image
                const compressedData = await compressImage(file);
                terminalReceiptPhotoData = compressedData;

                // Show preview
                if (terminalPhotoPreviewImg) {
                    terminalPhotoPreviewImg.src = compressedData;
                }
                if (terminalPhotoPreview) {
                    terminalPhotoPreview.style.display = 'block';
                }
                if (terminalPhotoBtn) {
                    terminalPhotoBtn.textContent = '✓ Foto capturada - Cambiar foto';
                }
            } catch (error) {
                console.error('Error processing image:', error);
                toast('Error al procesar la imagen', 'warning');
            }
        });

        const showStep = (step: 'method' | 'cash' | 'terminal' | 'stripe' | 'clip') => {
            paymentMethodSelection?.setAttribute('style', step === 'method' ? '' : 'display: none;');
            paymentCashConfirmation?.setAttribute('style', step === 'cash' ? '' : 'display: none;');
            paymentTerminalOptions?.setAttribute('style', step === 'terminal' ? '' : 'display: none;');
            paymentStripeConfirmation?.setAttribute('style', step === 'stripe' ? '' : 'display: none;');
            paymentClipConfirmation?.setAttribute('style', step === 'clip' ? '' : 'display: none;');
        };

        // Payment method selection
        paymentMethodButtons.forEach((btn) => {
            btn.addEventListener('click', () => {
                const method = btn.dataset.method;
                state.method = method || null;

                if (method === 'cash') {
                    showStep('cash');
                } else if (method === 'terminal') {
                    showStep('terminal');
                } else if (method === 'stripe') {
                    showStep('stripe');
                } else if (method === 'clip') {
                    showStep('clip');
                }
            });
        });

        // Cash payment confirmation
        // Cash payment confirmation
        confirmCashBtn?.addEventListener('click', async () => {
            if (!state.sessionId) return;
            try {
                const response = await requestJSON<{ requires_confirmation?: boolean; session?: any }>(`/api/sessions/${state.sessionId}/pay`, {
                    method: 'POST',
                    body: { payment_method: 'cash' }
                });
                closePaymentModal();

                if (response.requires_confirmation) {
                    // Auto-confirm cash payments so the session moves to pagadas immediately
                    const confirmedSession = await requestJSON<{ status?: string }>(
                        `/api/sessions/${state.sessionId}/confirm-payment`,
                        { method: 'POST' }
                    );
                    toast('Pago en efectivo confirmado', 'success');
                    emitSessionUpdated(state.sessionId, confirmedSession.status || 'paid', confirmedSession);
                    notifySessionClosed(state.sessionId);
                    // Lleva directo al ticket para imprimir/reenviar y mantener el flujo
                    openTicketModal(state.sessionId);
                } else {
                    toast('PAGADO correctamente', 'success');
                    emitSessionUpdated(state.sessionId, 'paid', response.session);
                    openTipModal(state.sessionId);
                }
            } catch (error) {
                toast((error as Error).message, 'warning');
            }
        });

        // Terminal payment form submission
        // Terminal payment form submission
        terminalForm?.addEventListener('submit', async (event) => {
            event.preventDefault();
            if (!state.sessionId) return;

            const reference = terminalReference?.value.trim() || undefined;
            const cardType = terminalCardType?.value || undefined;

            try {
                // 'terminal' in UI maps to 'card' payment method in backend (physical terminal, no API)
                const body: Record<string, any> = { payment_method: 'card' };
                if (reference) body.payment_reference = reference;
                if (cardType) body.card_type = cardType;
                if (terminalReceiptPhotoData) body.receipt_photo = terminalReceiptPhotoData;

                const response = await requestJSON<{ requires_confirmation?: boolean }>(`/api/sessions/${state.sessionId}/pay`, {
                    method: 'POST',
                    body
                });

                // Reset photo data after successful submission
                terminalReceiptPhotoData = null;
                if (terminalReceiptPhoto) terminalReceiptPhoto.value = '';
                if (terminalPhotoPreview) terminalPhotoPreview.style.display = 'none';
                if (terminalPhotoBtn) terminalPhotoBtn.textContent = '📷 Tomar foto del ticket';

                closePaymentModal();

                if (response.requires_confirmation) {
                    toast('PAGADO con terminal. Confirma el pago para cerrar la cuenta.', 'info');
                    // Update session status to awaiting_payment_confirmation
                    emitSessionUpdated(state.sessionId, 'awaiting_payment_confirmation', response as any);
                    document.dispatchEvent(
                        new CustomEvent('employee:session:payment-pending', {
                            detail: { sessionId: state.sessionId }
                        })
                    );
                } else {
                    toast('PAGADO correctamente', 'success');
                    emitSessionUpdated(state.sessionId, 'paid', response.session);
                    openTipModal(state.sessionId);
                }
            } catch (error) {
                toast((error as Error).message, 'warning');
            }
        });

        // Stripe payment confirmation
        // Stripe payment confirmation
        confirmStripeBtn?.addEventListener('click', async () => {
            if (!state.sessionId) return;
            try {
                const response = await requestJSON<{ requires_confirmation?: boolean }>(`/api/sessions/${state.sessionId}/pay`, {
                    method: 'POST',
                    body: { payment_method: 'stripe' }
                });
                closePaymentModal();

                if (response.requires_confirmation) {
                    toast('PAGADO con efectivo. Confirma el pago para cerrar la cuenta.', 'info');
                    document.dispatchEvent(
                        new CustomEvent('employee:session:payment-pending', {
                            detail: { sessionId: state.sessionId }
                        })
                    );
                } else {
                    toast('PAGADO con efectivo', 'success');
                    emitSessionUpdated(state.sessionId, 'paid', response.session);

                    // Auto-send ticket email if customer email available
                    const sessionEmail = response.session?.customer_email || '';
                    if (sessionEmail && sessionEmail.trim() !== '') {
                        try {
                            await requestJSON(`/api/sessions/${state.sessionId}/resend`, {
                                method: 'POST',
                                body: { email: sessionEmail }
                            });
                            toast(`Ticket enviado a ${sessionEmail}`, 'success');
                        } catch (error) {
                            console.warn('No se pudo enviar ticket auto:', error);
                        }
                    }

                    openTipModal(state.sessionId);
                }
            } catch (error) {
                toast((error as Error).message, 'warning');
            }
        });

        // Clip API payment confirmation (sandbox mode)
        confirmClipBtn?.addEventListener('click', async () => {
            if (!state.sessionId) return;
            try {
                const response = await requestJSON<{ requires_confirmation?: boolean }>(`/api/sessions/${state.sessionId}/pay`, {
                    method: 'POST',
                    body: { payment_method: 'clip' }
                });
                closePaymentModal();

                if (response.requires_confirmation) {
                    toast('PAGADO con Clip API (sandbox). Confirma el pago para cerrar la cuenta.', 'info');
                    document.dispatchEvent(
                        new CustomEvent('employee:session:payment-pending', {
                            detail: { sessionId: state.sessionId }
                        })
                    );
                } else {
                    toast('PAGADO con Clip API (sandbox)', 'success');
                    emitSessionUpdated(state.sessionId, 'paid', response.session);
                    openTipModal(state.sessionId);
                }
            } catch (error) {
                toast((error as Error).message, 'warning');
            }
        });

        // Back navigation
        backFromCashBtn?.addEventListener('click', () => showStep('method'));
        backFromTerminalBtn?.addEventListener('click', () => showStep('method'));
        backFromStripeBtn?.addEventListener('click', () => showStep('method'));
        backFromClipBtn?.addEventListener('click', () => showStep('method'));
        cancelPaymentMethodBtn?.addEventListener('click', closePaymentModal);

        tipButtons.forEach((btn) => {
            btn.addEventListener('click', () => {
                const value = Number(btn.dataset.tip || '0');
                setTip(value);
            });
        });

        // Tip form submission
        tipForm?.addEventListener('submit', async (event) => {
            event.preventDefault();
            if (!state.sessionId) return;

            try {
                await requestJSON(`/api/sessions/${state.sessionId}/tip`, {
                    method: 'POST',
                    body: { amount: state.tip }
                });
                closeTipModal();
                toast('Propina registrada', 'success');
                // Automatically open ticket modal after tip
                openTicketModal(state.sessionId);
            } catch (error) {
                toast((error as Error).message, 'warning');
            }
        });

        ticketForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            if (!state.sessionId) return;
            const selected = ticketDeliveryInputs.find((input) => input.checked);
            const delivery = selected ? selected.value : 'physical';
            const email = delivery === 'digital' ? ticketEmailInput?.value.trim() || '' : '';
            if (delivery === 'digital' && !email) {
                toast('Ingresa el correo electrónico para el ticket digital', 'warning');
                return;
            }
            if (delivery === 'digital' && email && !isValidEmailFormat(email)) {
                toast('Ingresa un correo electrónico válido', 'warning');
                return;
            }
            try {
                if (delivery === 'digital' && email) {
                    // Enviar el ticket directamente sin actualizar el contacto
                    // (la sesión ya está cerrada después de confirmar el pago)
                    await requestJSON(`/api/sessions/${state.sessionId}/resend`, {
                        method: 'POST',
                        body: { email }
                    });
                    toast(`Ticket enviado a ${email}`, 'success');
                } else {
                    await printTicket(state.sessionId);
                    toast('Ticket impreso correctamente', 'success');
                }
                closeTicketModal();
                emitSessionUpdated(state.sessionId, 'paid');
                notifySessionClosed(state.sessionId);
            } catch (error) {
                toast((error as Error).message, 'warning');
            }
        });

        closePaymentBtn?.addEventListener('click', closePaymentModal);
        cancelPaymentBtn?.addEventListener('click', closePaymentModal);

        const skipTip = () => {
            closeTipModal();
            if (state.sessionId) {
                openTicketModal(state.sessionId);
            }
        };
        closeTipBtn?.addEventListener('click', skipTip);
        cancelTipBtn?.addEventListener('click', skipTip);

        const closeTicket = () => {
            closeTicketModal();
        };
        closeTicketBtn?.addEventListener('click', closeTicket);
        cancelTicketBtn?.addEventListener('click', closeTicket);

        document.addEventListener('employee:payments:open', (event) => {
            console.log('[PAYMENTS] Received employee:payments:open event');
            const detail = (event as CustomEvent).detail || {};
            if (!detail.sessionId) return;
            openPaymentModal(Number(detail.sessionId), detail.method || 'cash', detail.orderNumber, detail.prefillEmail);
        });

        // Expose to window
        window.EmployeePayments = {
            openModal: openPaymentModal,
            closeModal: closePaymentModal,
            printTicket: (sessionId: number) => printTicket(Number(sessionId)),
            openTicketModal: (sessionId: number) => openTicketModal(Number(sessionId))
        };
        console.log('[PAYMENTS] window.EmployeePayments initialized:', window.EmployeePayments);

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                closePaymentModal();
                closeTipModal();
                closeTicketModal();
            }
        });

        document.dispatchEvent(new CustomEvent('employee:payments:ready'));
        console.log('[PAYMENTS] Payments flow initialization complete');
    };

    // Execute immediately if DOM is fully loaded, otherwise wait for load event
    if (document.readyState === 'complete') {
        console.log('[PAYMENTS] DOM already complete, initializing immediately');
        init();
    } else {
        console.log('[PAYMENTS] Waiting for DOM to be complete, current state:', document.readyState);
        window.addEventListener('load', init);
    }
}

const createFragment = (html: string): DocumentFragment =>
    document.createRange().createContextualFragment(html);
