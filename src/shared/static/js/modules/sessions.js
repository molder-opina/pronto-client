/**
 * Dashboard - Sessions Module
 * Handles open and closed sessions management
 */

export class SessionsModule {
    constructor() {
        this.elements = {
            sessionsList: document.getElementById("sessions-list"),
            closedSessionsList: document.getElementById("closed-sessions-list"),
            closedSessionsPagination: document.getElementById("closed-sessions-pagination"),
            resendTicketModal: document.getElementById("resend-ticket-modal"),
            resendTicketForm: document.getElementById("resend-ticket-form"),
            resendTicketSessionLabel: document.getElementById("resend-ticket-session-label"),
            resendTicketEmailInput: document.getElementById("resend-ticket-email"),
            closeResendTicketBtn: document.getElementById("close-resend-ticket"),
            cancelResendTicketBtn: document.getElementById("cancel-resend-ticket"),
        };

        this.sessionsState = {};
        this.chargeableSessionStatuses = new Set(['awaiting_tip', 'awaiting_payment']);
        this.allClosedSessions = []; // Store all closed sessions for pagination

        this.init();
    }

    init() {
        this.initializePagination();
        this.attachEventListeners();
        this.loadClosedSessions();
    }

    initializePagination() {
        if (!this.elements.closedSessionsPagination) return;

        this.closedSessionsPagination = new PaginationManager({
            container: this.elements.closedSessionsPagination,
            onPageChange: () => {
                this.renderClosedSessions(this.allClosedSessions);
            },
            labels: {
                previous: 'Anterior',
                next: 'Siguiente',
                showing: 'Mostrando',
                of: 'de',
                items: 'órdenes'
            }
        });

        // Register the pagination instance
        this.closedSessionsPagination.register();
    }

    attachEventListeners() {
        const { sessionsList, resendTicketForm, closeResendTicketBtn, cancelResendTicketBtn } = this.elements;

        // Open sessions actions
        sessionsList?.addEventListener("click", (e) => this.handleSessionAction(e));

        // Resend ticket modal
        closeResendTicketBtn?.addEventListener("click", () => this.closeResendTicketModal());
        cancelResendTicketBtn?.addEventListener("click", () => this.closeResendTicketModal());
        resendTicketForm?.addEventListener("submit", (e) => this.handleResendTicketSubmit(e));

        // ESC key support
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                this.closeResendTicketModal();
            }
        });
    }

    handleSessionAction(event) {
        const button = event.target.closest("button[data-action]");
        if (!button) return;

        // Don't process clicks on disabled buttons
        if (button.disabled || button.classList.contains('btn--disabled')) {
            return;
        }

        const card = button.closest(".session-card");
        const sessionId = card.dataset.sessionId;
        const action = button.dataset.action;

        switch (action) {
            case "checkout":
                this.requestCheckout(sessionId);
                break;
            case "tip":
                this.openTipModal(sessionId);
                break;
            case "pay-cash":
                this.openPaymentModal(sessionId, "cash");
                break;
            case "pay-clip":
                this.openPaymentModal(sessionId, "clip");
                break;
            case "ticket":
                this.printTicket(sessionId);
                break;
        }
    }

    renderSessions(sessions = {}) {
        const sessionsList = this.elements.sessionsList;
        if (!sessionsList) return;

        const sessionsArray = Object.values(sessions);
        const statusLabelMap = {
            open: 'Activa',
            awaiting_tip: 'Propina solicitada',
            awaiting_payment: 'Listo para cobrar'
        };

        if (sessionsArray.length === 0) {
            sessionsList.innerHTML = "<p>No hay cuentas abiertas.</p>";
            return;
        }

        sessionsList.innerHTML = sessionsArray.map(session => `
            <article class="session-card" data-session-id="${session.id}">
                ${['awaiting_tip','awaiting_payment'].includes(session.status) ?
                    '<div class="session-card__flag">Cuenta solicitada</div>' : ''}
                <header>
                    <h3>Cuenta #${session.id} · Mesa ${session.table_number || 'N/A'}</h3>
                    <span class="session-status session-status--${session.status}">
                        ${statusLabelMap[session.status] || session.status}
                    </span>
                </header>
                <ul class="session-card__orders">
                    ${session.orders.map(order => `
                        <li>#${order.id} · ${order.workflow_status} · ${order.customer.name} ·
                            ${this.formatCurrency(order.total_amount)}</li>
                    `).join('')}
                </ul>
                <div class="session-card__totals">
                    <span>Subtotal: ${this.formatCurrency(session.totals.subtotal)}</span>
                    <span>IVA: ${this.formatCurrency(session.totals.tax_amount)}</span>
                    <span>Propina: ${this.formatCurrency(session.totals.tip_amount)}</span>
                    <strong>Total: ${this.formatCurrency(session.totals.total_amount)}</strong>
                </div>
                <div class="session-card__actions">
                    ${session.status === 'open' ?
                        '<button type="button" data-action="checkout" class="btn btn--secondary">Solicitar propina</button>' : ''}
                    ${session.status === 'awaiting_tip' ?
                        '<button type="button" data-action="tip" class="btn btn--secondary">Registrar propina</button>' : ''}

                    <!-- Payment buttons always visible, disabled until checkout requested -->
                    ${!this.chargeableSessionStatuses.has(session.status) ?
                        '<div class="session-card__payment-pending"><p class="payment-hint">💡 Los botones de cobro se habilitarán cuando el cliente solicite la cuenta</p></div>' : ''}

                    <button type="button"
                            data-action="pay-cash"
                            class="btn btn--primary ${!this.chargeableSessionStatuses.has(session.status) ? 'btn--disabled' : ''}"
                            ${!this.chargeableSessionStatuses.has(session.status) ? 'disabled' : ''}>
                        ${!this.chargeableSessionStatuses.has(session.status) ? '🔒 ' : ''}Cobrar en efectivo
                    </button>
                    <button type="button"
                            data-action="pay-clip"
                            class="btn btn--primary ${!this.chargeableSessionStatuses.has(session.status) ? 'btn--disabled' : ''}"
                            ${!this.chargeableSessionStatuses.has(session.status) ? 'disabled' : ''}>
                        ${!this.chargeableSessionStatuses.has(session.status) ? '🔒 ' : ''}Cobrar con terminal
                    </button>
                    ${this.chargeableSessionStatuses.has(session.status) ?
                        '<button type="button" data-action="ticket" class="btn btn--outline">Imprimir ticket</button>' : ''}
                </div>
            </article>
        `).join('');
    }

    async loadClosedSessions() {
        if (!this.elements.closedSessionsList) return;

        try {
            const response = await this.requestJSON('/api/sessions/closed', 'GET');
            if (response && response.closed_sessions) {
                this.allClosedSessions = response.closed_sessions;
                this.renderClosedSessions(this.allClosedSessions);
            }
        } catch (error) {
            console.error('Error loading closed sessions:', error);
            this.elements.closedSessionsList.innerHTML =
                '<p style="color:#ef4444;">Error al cargar órdenes cerradas</p>';
        }
    }

    renderClosedSessions(sessions) {
        const list = this.elements.closedSessionsList;
        if (!list) return;

        if (sessions.length === 0) {
            list.innerHTML = "<p>No hay órdenes cerradas en las últimas 24 horas.</p>";
            if (this.closedSessionsPagination) {
                this.closedSessionsPagination.update(0);
            }
            return;
        }

        // Update pagination
        if (this.closedSessionsPagination) {
            this.closedSessionsPagination.update(sessions.length);
        }

        // Get current page sessions
        const pageSessions = this.closedSessionsPagination
            ? this.closedSessionsPagination.getCurrentPageData(sessions)
            : sessions;

        list.innerHTML = pageSessions.map(session => {
            const closedDate = new Date(session.closed_at);
            const formattedDate = closedDate.toLocaleDateString('es-MX', {
                year: 'numeric', month: 'short', day: 'numeric',
                hour: '2-digit', minute: '2-digit'
            });

            return `
            <article class="session-card session-card--closed" data-session-id="${session.id}">
                <div class="session-card__flag session-card__flag--closed">Cerrada</div>
                <header>
                    <h3>Cuenta #${session.id} · Mesa ${session.table_number || 'N/A'}</h3>
                    <span class="session-status session-status--closed">${formattedDate}</span>
                </header>
                <div class="session-card__info">
                    <p><strong>Cliente:</strong> ${session.customer_name}</p>
                    <p><strong>Método de pago:</strong> ${session.payment_method || 'N/A'}</p>
                    ${session.payment_reference ? `<p><strong>Referencia:</strong> ${session.payment_reference}</p>` : ''}
                    <p><strong>Órdenes:</strong> ${session.orders_count}</p>
                </div>
                <div class="session-card__totals">
                    <span>Subtotal: ${this.formatCurrency(session.subtotal)}</span>
                    <span>IVA: ${this.formatCurrency(session.tax_amount)}</span>
                    <span>Propina: ${this.formatCurrency(session.tip_amount)}</span>
                    <strong>Total: ${this.formatCurrency(session.total_amount)}</strong>
                </div>
                <div class="session-card__actions">
                    <button type="button" data-action="reprint" data-session-id="${session.id}"
                            class="btn btn--secondary">Reimprimir ticket</button>
                    <button type="button" data-action="resend" data-session-id="${session.id}"
                            data-email="${session.customer_email || ''}"
                            class="btn btn--outline">Reenviar por email</button>
                </div>
            </article>
        `}).join('');

        // Attach event listeners for closed session actions
        this.attachClosedSessionListeners();
    }

    attachClosedSessionListeners() {
        const list = this.elements.closedSessionsList;
        if (!list) return;

        list.querySelectorAll('button[data-action="reprint"]').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleReprintTicket(e));
        });

        list.querySelectorAll('button[data-action="resend"]').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleResendTicket(e));
        });
    }

    async handleReprintTicket(event) {
        const sessionId = event.target.dataset.sessionId;
        if (!sessionId) return;

        try {
            const response = await this.requestJSON(`/api/sessions/${sessionId}/reprint`, 'POST');
            if (response && response.ticket) {
                await this.printTicket(sessionId);
                this.showToast('Ticket generado para impresión', 'success');
            }
        } catch (error) {
            this.showToast(error.message || 'Error al reimprimir ticket', 'error');
        }
    }

    handleResendTicket(event) {
        const sessionId = event.target.dataset.sessionId;
        const customerEmail = event.target.dataset.email;
        if (!sessionId) return;

        this.openResendTicketModal(sessionId, customerEmail);
    }

    openResendTicketModal(sessionId, defaultEmail = '') {
        const { resendTicketModal, resendTicketForm, resendTicketSessionLabel, resendTicketEmailInput } = this.elements;
        if (!resendTicketModal || !resendTicketForm) return;

        if (resendTicketSessionLabel) {
            resendTicketSessionLabel.textContent = `#${sessionId}`;
        }

        if (resendTicketEmailInput) {
            resendTicketEmailInput.value = defaultEmail;
        }

        resendTicketForm.dataset.sessionId = sessionId;
        resendTicketModal.classList.add('active');
    }

    closeResendTicketModal() {
        const { resendTicketModal, resendTicketEmailInput } = this.elements;
        if (!resendTicketModal) return;

        resendTicketModal.classList.remove('active');
        if (resendTicketEmailInput) {
            resendTicketEmailInput.value = '';
        }
    }

    async handleResendTicketSubmit(event) {
        event.preventDefault();
        const { resendTicketForm, resendTicketEmailInput } = this.elements;

        const sessionId = resendTicketForm.dataset.sessionId;
        const email = resendTicketEmailInput.value.trim();

        if (!email) {
            this.showToast('Ingresa un correo electrónico válido', 'warning');
            return;
        }

        try {
            const response = await this.requestJSON(`/api/sessions/${sessionId}/resend`, 'POST', { email });
            this.showToast(response.message || 'Ticket reenviado exitosamente', 'success');
            this.closeResendTicketModal();
        } catch (error) {
            this.showToast(error.message || 'Error al reenviar ticket', 'error');
        }
    }

    // Utilities
    async requestJSON(endpoint, method = "GET", body = undefined) {
        const response = await fetch(endpoint, {
            method,
            headers: body ? { "Content-Type": "application/json" } : undefined,
            body: body ? JSON.stringify(body) : undefined,
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || "Operación no disponible");
        }
        return data;
    }

    async printTicket(sessionId) {
        try {
            const response = await this.requestJSON(`/api/sessions/${sessionId}/ticket`, "GET");
            const ticketWindow = window.open("", "_blank", "width=500,height=600");
            if (ticketWindow) {
                ticketWindow.document.write(`<pre>${response.ticket}</pre>`);
                ticketWindow.document.close();
            } else {
                alert(response.ticket);
            }
        } catch (error) {
            this.showToast(error.message || "Error al imprimir ticket", "error");
        }
    }

    formatCurrency(amount) {
        const settings = window.APP_SETTINGS || {};
        const formatter = new Intl.NumberFormat(settings.currency_locale || 'es-MX', {
            style: 'currency',
            currency: settings.currency_code || 'MXN',
        });
        return formatter.format(amount);
    }

    showToast(message, type = "info") {
        console.log(`[${type}] ${message}`);
    }

    // Bridge methods to payment module
    openPaymentModal(sessionId, method) {
        document.dispatchEvent(new CustomEvent('session:payment-requested', {
            detail: { sessionId, method }
        }));
    }

    openTipModal(sessionId) {
        document.dispatchEvent(new CustomEvent('session:tip-requested', {
            detail: { sessionId }
        }));
    }

    async requestCheckout(sessionId) {
        try {
            const response = await this.requestJSON(`/api/sessions/${sessionId}/checkout`, 'POST', {});
            this.showToast('Propina solicitada al cliente', 'success');
            // Reload sessions
            document.dispatchEvent(new CustomEvent('sessions:refresh'));
        } catch (error) {
            this.showToast(error.message || 'Error al solicitar cuenta', 'error');
        }
    }
}
