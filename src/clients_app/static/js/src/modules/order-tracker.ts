/**
 * ORDER TRACKER - Order Status and Payment Tracking
 * Handles active orders, payment polling, and order status updates
 */

import { requestJSON } from '../core/http';

const SESSION_STORAGE_KEY = 'pronto-session-id';

interface OrderResponse {
  orders: Array<{ id: number; status: string; session_id: number; payment_status?: string }>;
  session?: { status?: string };
}

export class OrderTracker {
  private sessionId: number | null = null;
  private paymentPollingInterval?: number;

  private readonly elements = {
    miniTracker: document.getElementById('mini-tracker'),
    miniTrackerClose: document.getElementById('mini-tracker-close'),
    miniTrackerStatus: document.getElementById('mini-tracker-status'),
    miniTrackerProgress: document.getElementById('mini-tracker-progress'),
    miniTrackerPercentage: document.getElementById('mini-tracker-percentage'),
    requestCheckoutBtn: document.getElementById('request-checkout-btn'),
    cancelOrderBtn: document.getElementById('cancel-order-button'),
    viewDetailBtn: document.getElementById('view-detail-btn'),
    checkoutWaitingOverlay: document.getElementById('checkout-waiting-overlay'),
    checkoutWaitingContinue: document.getElementById('checkout-waiting-continue'),
    paymentConfirmedNotification: document.getElementById('payment-confirmed-notification'),
  };

  constructor() {
    this.sessionId = Number(localStorage.getItem(SESSION_STORAGE_KEY)) || null;
    this.attachEventListeners();
    this.attachUnloadCleanup();
  }

  /**
   * Attach cleanup handlers for page unload
   */
  private attachUnloadCleanup(): void {
    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', () => {
        this.stopPaymentPolling();
      });
      window.addEventListener('pagehide', () => {
        this.stopPaymentPolling();
      });
    }
  }

  /**
   * Get current session ID
   */
  public getSessionId(): number | null {
    return this.sessionId;
  }

  /**
   * Set session ID
   */
  public setSessionId(sessionId: number | null): void {
    this.sessionId = sessionId;
    if (sessionId !== null) {
      localStorage.setItem(SESSION_STORAGE_KEY, String(sessionId));
    } else {
      localStorage.removeItem(SESSION_STORAGE_KEY);
    }
  }

  /**
   * Check for active orders on session
   */
  public async checkActiveOrders(): Promise<void> {
    if (!this.sessionId) return;

    try {
      const data = await requestJSON<OrderResponse>(`/api/session/${this.sessionId}/orders`);
      const active = data.orders?.find((order) => order.status !== 'delivered');

      if (active) {
        (window as any).refreshMiniTracker?.();
        if (!(window as any).refreshMiniTracker) {
          this.elements.miniTracker?.classList.add('visible');
        }
      }
    } catch (error) {
      console.warn('[OrderTracker] checkActiveOrders', error);
    }
  }

  /**
   * Request checkout from tracker (user wants to pay)
   */
  public async requestCheckout(): Promise<void> {
    if (!this.sessionId) {
      window.showNotification?.('No hay una sesión activa', 'warning');
      return;
    }

    try {
      // Call the checkout endpoint to change session status to awaiting_tip
      await requestJSON(`/api/sessions/${this.sessionId}/checkout`, {
        method: 'POST',
      });

      // Show waiting overlay
      this.showWaitingOverlay();

      // Start polling for payment completion
      this.startPaymentPolling();
    } catch (error) {
      window.showNotification?.(`Error: ${(error as Error).message}`, 'error');
    }
  }

  /**
   * Cancel pending order
   */
  public cancelOrder(): void {
    window.showNotification?.('Contacta al personal para cancelar el pedido.', 'info');
  }

  /**
   * View full tracker / switch to orders view
   */
  public viewFullTracker(): void {
    // Prefer orders view to show cards per order
    if (typeof (window as any).switchView === 'function') {
      (window as any).switchView('orders');
    } else {
      const ordersTab = document.getElementById('tab-orders') as HTMLButtonElement | null;
      ordersTab?.click();
    }
  }

  /**
   * Stop any active payment polling
   */
  public stopPaymentPolling(): void {
    if (this.paymentPollingInterval) {
      clearInterval(this.paymentPollingInterval);
      this.paymentPollingInterval = undefined;
    }
  }

  /**
   * Attach event listeners for checkout waiting overlay and mini tracker
   */
  private attachEventListeners(): void {
    // Mini tracker close button
    this.elements.miniTrackerClose?.addEventListener('click', () => {
      this.hideMiniTracker();
    });

    // Checkout waiting overlay - Continue button
    this.elements.checkoutWaitingContinue?.addEventListener('click', () => {
      this.hideWaitingOverlay();
    });

    // Checkout waiting overlay - ESC key
    document.addEventListener('keydown', (event) => {
      if (
        event.key === 'Escape' &&
        this.elements.checkoutWaitingOverlay?.style.display === 'flex'
      ) {
        this.hideWaitingOverlay();
      }
    });
  }

  /**
   * Show checkout waiting overlay
   */
  private showWaitingOverlay(): void {
    if (this.elements.checkoutWaitingOverlay) {
      this.elements.checkoutWaitingOverlay.style.display = 'flex';
    }
  }

  /**
   * Hide checkout waiting overlay
   */
  private hideWaitingOverlay(): void {
    if (this.elements.checkoutWaitingOverlay) {
      this.elements.checkoutWaitingOverlay.style.display = 'none';
    }
  }

  /**
   * Start polling for payment status
   */
  private startPaymentPolling(): void {
    if (this.paymentPollingInterval) {
      clearInterval(this.paymentPollingInterval);
    }

    this.paymentPollingInterval = window.setInterval(async () => {
      try {
        const response = await fetch(`/api/session/${this.sessionId}/orders`);
        if (!response.ok) return;

        const data = await response.json();
        const session = data.session;

        // If the session is paid, handle completion
        if (session?.status === 'paid') {
          await this.handlePaymentCompleted();
        }
      } catch (error) {
        console.error('[OrderTracker] Error checking payment status:', error);
      }
    }, 3000); // Poll every 3 seconds
  }

  /**
   * Handle payment completion
   */
  private async handlePaymentCompleted(): Promise<void> {
    // Stop polling
    this.stopPaymentPolling();

    // Hide waiting overlay
    this.hideWaitingOverlay();

    // Show payment confirmed notification
    this.showPaymentConfirmedNotification();

    // Show confetti effect
    if (typeof window.createConfetti === 'function') {
      window.createConfetti();
    }

    // Get auto-close duration from settings (default 5 seconds)
    const autoCloseDuration = window.APP_SETTINGS?.payment_confirmed_duration_seconds || 5;

    // Check if there are other unpaid orders in the session before resetting
    const shouldReset = await this.shouldResetSession();

    // Auto-close notification
    setTimeout(() => {
      this.hidePaymentConfirmedNotification();

      if (shouldReset) {
        // Clear session and reload page
        if (typeof window.clearSessionId === 'function') {
          window.clearSessionId();
        }
        window.location.reload();
      } else {
        // Don't reset - there are other unpaid orders in this session
        // Just refresh the mini-tracker to show remaining orders
        if (typeof window.refreshMiniTracker === 'function') {
          window.refreshMiniTracker();
        }
      }
    }, autoCloseDuration * 1000);
  }

  /**
   * Check if session should be reset after payment
   */
  private async shouldResetSession(): Promise<boolean> {
    if (!this.sessionId) return true;

    try {
      const response = await fetch(`/api/session/${this.sessionId}/orders`);
      if (!response.ok) return true;

      const data = await response.json();
      const orders = data.orders || [];
      const session = data.session || {};

      // Session statuses that indicate the session is finished
      const finishedStatuses = ['closed', 'paid', 'billed', 'cancelled'];
      const isSessionFinished = finishedStatuses.includes(session.status);

      // Check if all orders are paid
      const allOrdersPaid =
        orders.length === 0 || orders.every((o: any) => o.payment_status === 'paid');

      // Reset if session is finished OR all orders are paid
      return isSessionFinished || allOrdersPaid;
    } catch (error) {
      console.error('[OrderTracker] Error checking if should reset:', error);
      // On error, don't reset to be safe
      return false;
    }
  }

  /**
   * Show payment confirmed notification
   */
  private showPaymentConfirmedNotification(): void {
    if (this.elements.paymentConfirmedNotification) {
      this.elements.paymentConfirmedNotification.style.display = 'flex';
    }
  }

  /**
   * Hide payment confirmed notification
   */
  private hidePaymentConfirmedNotification(): void {
    if (this.elements.paymentConfirmedNotification) {
      this.elements.paymentConfirmedNotification.style.display = 'none';
    }
  }

  /**
   * Hide mini tracker temporarily (user can see it again by viewing orders tab)
   */
  private hideMiniTracker(): void {
    if (this.elements.miniTracker) {
      this.elements.miniTracker.classList.remove('visible');
    }
  }
}
