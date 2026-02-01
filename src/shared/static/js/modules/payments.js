/**
 * Dashboard - Payment Module
 * Handles payment flow: payment → tip → ticket
 */

export class PaymentModule {
    constructor() {
        this.state = {
            sessionId: null,
            method: null,
            tip: 0,
        };

        this.elements = {
            // Payment modal
            paymentModal: document.getElementById("employee-payment-modal"),
            paymentForm: document.getElementById("employee-payment-form"),
            paymentSessionLabel: document.getElementById("employee-payment-session-label"),
            closePaymentBtn: document.getElementById("close-employee-payment"),
            cancelPaymentBtn: document.getElementById("cancel-employee-payment"),

            // Tip modal
            tipModal: document.getElementById("employee-tip-modal"),
            tipForm: document.getElementById("employee-tip-form"),
            tipSessionLabel: document.getElementById("employee-tip-session-label"),
            closeTipBtn: document.getElementById("close-employee-tip"),
            cancelTipBtn: document.getElementById("cancel-employee-tip"),
            tipButtons: Array.from(document.querySelectorAll("#employee-tip-options-modal .tip-chip")),

            // Ticket modal
            ticketModal: document.getElementById("employee-ticket-modal"),
            ticketForm: document.getElementById("employee-ticket-form"),
            ticketSessionLabel: document.getElementById("employee-ticket-session-label"),
            closeTicketBtn: document.getElementById("close-employee-ticket"),
            cancelTicketBtn: document.getElementById("cancel-employee-ticket"),
            ticketEmailInput: document.getElementById("ticket-email-input"),
        };

        this.init();
    }

    init() {
        this.attachEventListeners();
    }

    attachEventListeners() {
        const { paymentForm, tipForm, ticketForm, tipButtons } = this.elements;
        const {
            closePaymentBtn, cancelPaymentBtn,
            closeTipBtn, cancelTipBtn,
            closeTicketBtn, cancelTicketBtn,
            ticketForm: ticketFormEl
        } = this.elements;

        // Payment modal
        closePaymentBtn?.addEventListener("click", () => this.closePaymentModal());
        cancelPaymentBtn?.addEventListener("click", () => this.closePaymentModal());
        paymentForm?.addEventListener("submit", (e) => this.handlePaymentSubmit(e));

        // Tip modal
        tipButtons.forEach(btn => {
            btn.addEventListener("click", () => this.setTip(btn.dataset.tip));
        });
        closeTipBtn?.addEventListener("click", () => {
            this.closeTipModal();
            this.openTicketModal(this.state.sessionId);
        });
        cancelTipBtn?.addEventListener("click", () => {
            this.closeTipModal();
            this.openTicketModal(this.state.sessionId);
        });
        tipForm?.addEventListener("submit", (e) => this.handleTipSubmit(e));

        // Ticket modal
        closeTicketBtn?.addEventListener("click", () => this.closeTicketModal());
        cancelTicketBtn?.addEventListener("click", () => this.closeTicketModal());
        ticketFormEl?.addEventListener("submit", (e) => this.handleTicketSubmit(e));

        // Ticket delivery type change
        const ticketOptionInputs = ticketFormEl?.querySelectorAll("input[name='ticket-delivery']");
        ticketOptionInputs?.forEach(input => {
            input.addEventListener("change", () => {
                const selectedDigital = input.value === "digital" && input.checked;
                if (this.elements.ticketEmailInput) {
                    this.elements.ticketEmailInput.style.display = selectedDigital ? "block" : "none";
                }
            });
        });
    }

    // Payment Modal
    openPaymentModal(sessionId, method) {
        if (!this.elements.paymentModal) return;

        this.state.sessionId = sessionId;
        this.state.method = method;

        if (this.elements.paymentSessionLabel) {
            this.elements.paymentSessionLabel.textContent = `#${sessionId}`;
        }

        this.elements.paymentModal.classList.add("active");
    }

    closePaymentModal() {
        if (!this.elements.paymentModal) return;
        this.elements.paymentModal.classList.remove("active");
    }

    async handlePaymentSubmit(event) {
        event.preventDefault();

        const { sessionId, method } = this.state;
        if (!sessionId) return;

        try {
            const response = await this.requestJSON(`/api/sessions/${sessionId}/pay`, "POST", {
                payment_method: method
            });

            this.closePaymentModal();
            this.openTipModal(sessionId);

            // Emit event for other modules
            document.dispatchEvent(new CustomEvent('payment:completed', {
                detail: { sessionId, method, response }
            }));
        } catch (error) {
            console.error("Payment error:", error);
            this.showToast(error.message || "Error al procesar el pago", "error");
        }
    }

    // Tip Modal
    openTipModal(sessionId) {
        if (!this.elements.tipModal) return;

        this.state.sessionId = sessionId;
        this.state.tip = 0;

        if (this.elements.tipSessionLabel) {
            this.elements.tipSessionLabel.textContent = `#${sessionId}`;
        }

        // Reset tip buttons
        this.elements.tipButtons.forEach(btn => btn.classList.remove("active"));

        this.elements.tipModal.classList.add("active");
    }

    closeTipModal() {
        if (!this.elements.tipModal) return;
        this.elements.tipModal.classList.remove("active");
    }

    setTip(value) {
        this.state.tip = parseFloat(value) || 0;
        this.elements.tipButtons.forEach(btn => {
            btn.classList.toggle("active", btn.dataset.tip === String(value));
        });
    }

    async handleTipSubmit(event) {
        event.preventDefault();

        const { sessionId, tip } = this.state;
        if (!sessionId) return;

        try {
            if (tip > 0) {
                await this.requestJSON(`/api/sessions/${sessionId}/tip`, "POST", {
                    tip_percentage: tip
                });
            }

            this.closeTipModal();
            this.openTicketModal(sessionId);

            document.dispatchEvent(new CustomEvent('tip:completed', {
                detail: { sessionId, tip }
            }));
        } catch (error) {
            console.error("Tip error:", error);
            this.showToast(error.message || "Error al registrar propina", "error");
        }
    }

    // Ticket Modal
    openTicketModal(sessionId) {
        if (!this.elements.ticketModal) return;

        this.state.sessionId = sessionId;

        if (this.elements.ticketSessionLabel) {
            this.elements.ticketSessionLabel.textContent = `#${sessionId}`;
        }

        this.elements.ticketModal.classList.add("active");
    }

    closeTicketModal() {
        if (!this.elements.ticketModal) return;
        this.elements.ticketModal.classList.remove("active");
        this.state = { sessionId: null, method: null, tip: 0 };
    }

    async handleTicketSubmit(event) {
        event.preventDefault();

        const { sessionId } = this.state;
        if (!sessionId) return;

        const formData = new FormData(event.target);
        const delivery = formData.get("ticket-delivery");

        try {
            if (delivery === "physical") {
                await this.printTicket(sessionId);
                this.showToast("Ticket enviado a impresora", "success");
            } else if (delivery === "digital") {
                const email = formData.get("ticket-email");
                if (!email) {
                    this.showToast("Ingresa un email válido", "warning");
                    return;
                }
                // Implement email sending
                this.showToast(`Ticket enviado a ${email}`, "success");
            }

            this.closeTicketModal();

            document.dispatchEvent(new CustomEvent('ticket:completed', {
                detail: { sessionId, delivery }
            }));
        } catch (error) {
            console.error("Ticket error:", error);
            this.showToast(error.message || "Error al generar ticket", "error");
        }
    }

    // Utilities
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
            throw new Error(error.message || "No se pudo generar el ticket");
        }
    }

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

    showToast(message, type = "info") {
        // Implement toast notification
        console.log(`[${type}] ${message}`);
    }
}
