import { bootstrapModule } from '../core/bootstrap';
import { isAnonymousSession, redirectAfterPayment } from './session-cleanup';

interface ThankYouStatusMaps {
  classMap: Record<string, string>;
  labels: Record<string, string>;
  icons: Record<string, string>;
  progress: Record<string, number>;
}

interface ThankYouOrderItem {
  name: string;
  quantity: number;
  total: number;
}

interface ThankYouOrder {
  id: number;
  status: string;
  workflow_status?: string;
  total_amount: number;
  items?: ThankYouOrderItem[];
}

interface ThankYouSession {
  id: number;
  subtotal: number;
  tax_amount: number;
  total_amount: number;
  table_number?: string | null;
}

interface ThankYouData {
  session: ThankYouSession;
  orders: ThankYouOrder[];
  sessionSummary: ThankYouSession;
  statusMaps: ThankYouStatusMaps;
  estimatedTime: { enabled: boolean; min: number; max: number };
  canPayDigital: boolean;
  stripePublishableKey: string;
  notificationStreamUrl: string;
}

type CheckoutMethod = 'cash' | 'terminal' | 'digital';

const CANONICAL_TO_LEGACY: Record<string, string> = {
  new: 'requested',
  queued: 'waiter_accepted',
  preparing: 'kitchen_in_progress',
  ready: 'ready_for_delivery',
  awaiting_payment: 'wait_for_payment',
  paid: 'payed',
  delivered: 'delivered',
  cancelled: 'cancelled',
};

function escape(str: any): string {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export function initThankYouPage(root: HTMLElement): void {
  const data = window.THANK_YOU_DATA;
  if (!data) {
    console.warn('[thank-you] No se encontraron datos iniciales.');
    return;
  }
  const page = new ThankYouPage(root, data);
  page.initialize().catch((error) => console.error('[thank-you] initialize', error));
  window.ThankYouPage = page;
}

class ThankYouPage {
  private data: ThankYouData;
  private orders: ThankYouOrder[];
  private sessionSummary: ThankYouSession;
  private session: ThankYouSession;
  private canPayDigital: boolean;
  private statusMaps: ThankYouStatusMaps;
  private estimatedTime = { enabled: false, min: 0, max: 0 };
  private stripe?: any;
  private stripeCard?: any;
  private notificationManager?: any;
  private countdownInterval?: number;
  private paymentModalAutoClose?: number;
  private currentMethod: CheckoutMethod | null = null;
  private checkoutCallId: number | null = null;

  constructor(
    private root: HTMLElement,
    data: ThankYouData
  ) {
    this.data = data;
    this.session = data.session;
    this.orders = data.orders || [];
    this.sessionSummary = data.sessionSummary || data.session;
    this.statusMaps = data.statusMaps;
    this.canPayDigital = Boolean(data.canPayDigital);
    this.estimatedTime = data.estimatedTime;
  }

  async initialize(): Promise<void> {
    this.renderOrderHistory();
    this.updateEstimatedTime();
    this.attachEventListeners();
    this.setupRealtime();
    this.setupToasts();
    await this.setupStripe();
    window.setTimeout(() => void this.refreshOrders(true), 8000);
  }

  private attachEventListeners(): void {
    document
      .getElementById('request-checkout-btn')
      ?.addEventListener('click', () => void this.requestCheckout());
    document
      .getElementById('view-detail-btn')
      ?.addEventListener('click', () => this.showDetailsToast());
    document
      .getElementById('cancel-order-button')
      ?.addEventListener('click', () => window.cancelPendingOrder?.());
    document
      .getElementById('pay-digital-btn')
      ?.addEventListener('click', () => this.selectDigitalPayment());
    document
      .querySelectorAll<HTMLButtonElement>('.provider-btn')
      .forEach((btn) =>
        btn.addEventListener('click', () =>
          this.setDigitalProvider(btn.dataset.provider || 'stripe')
        )
      );
    document
      .querySelectorAll<HTMLButtonElement>('[data-tip-percentage]')
      .forEach((btn) =>
        btn.addEventListener('click', () =>
          this.selectTipPercentage(Number(btn.dataset.tipPercentage))
        )
      );
    document
      .getElementById('confirm-cash-payment')
      ?.addEventListener('click', () => this.markPaymentCompleted());
    document
      .getElementById('confirm-terminal-payment')
      ?.addEventListener('click', () => this.markPaymentCompleted());
    document
      .getElementById('confirm-digital-payment')
      ?.addEventListener('click', () => this.submitStripePayment());
    document.getElementById('clip-payment-form')?.addEventListener('submit', (event) => {
      event.preventDefault();
      void this.submitClipPayment();
    });
  }

  private async requestCheckout(): Promise<void> {
    try {
      const response = await requestJSON<{ waiter_call_id?: number }>(
        `/api/sessions/${this.session.id}/checkout`,
        {
          method: 'POST',
        }
      );
      this.checkoutCallId = response.waiter_call_id ?? null;
      window.showNotification?.('Cuenta solicitada', 'success');
    } catch (error) {
      window.showNotification?.('Error al solicitar cuenta', 'error');
    }
  }

  private selectDigitalPayment(): void {
    const modal = document.getElementById('payment-method-modal');
    const helper = document.getElementById('payment-modal-helper');

    if (modal) {
      const helper = document.getElementById('payment-modal-helper');
      if (helper) {
        helper.style.display = 'none';
        modal.style.display = 'block';
      }

      let timeLeft = Math.max(
        3,
        Number(window.APP_SETTINGS?.checkout_prompt_duration_seconds || 6)
      );
      if (this.paymentModalAutoClose) window.clearTimeout(this.paymentModalAutoClose);
      this.paymentModalAutoClose = window.setTimeout(
        () => this.autoSelectDefaultMethod(),
        timeLeft * 1000
      );

      const defaultMethod = (
        window.APP_SETTINGS?.checkout_default_method || 'cash'
      ).toLowerCase() as CheckoutMethod;

      switch (defaultMethod) {
        case 'terminal':
          document.getElementById('terminal-payment-modal')?.classList.add('active');
          break;
        case 'cash':
        default:
          document.getElementById('cash-payment-modal')?.classList.add('active');
      }
    }
  }

  private setDigitalProvider(provider: string): void {
    document.querySelectorAll<HTMLButtonElement>('.provider-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.provider === provider);
    });
    document.getElementById('digital-payment-modal')?.classList.add('active');
  }

  private autoSelectDefaultMethod(): void {
    const defaultMethod = (
      window.APP_SETTINGS?.checkout_default_method || 'cash'
    ).toLowerCase() as CheckoutMethod;
    if (this.currentMethod === null) {
      this.currentMethod = defaultMethod;
      document.querySelectorAll('.payment-modal').forEach((modal) => {
        modal.classList.remove('active');
      });
      document.getElementById('terminal-payment-modal')?.classList.add('active');
    }
  }

  private async setupStripe(): Promise<void> {
    if (!this.data.stripePublishableKey || typeof window.Stripe !== 'function') return;
    this.stripe = window.Stripe(this.data.stripePublishableKey);
    const elements = this.stripe.elements();
    this.stripeCard = elements.create('card');
    this.stripeCard.mount('#stripe-card-element');
  }

  private async submitStripePayment(): Promise<void> {
    if (!this.stripe || !this.stripeCard) return;
    try {
      const intent = await requestJSON<{ client_secret: string; payment_intent_id: string }>(
        `/api/sessions/${this.session.id}/pay/stripe`,
        { method: 'POST' }
      );
      const result = await this.stripe.confirmCardPayment(intent.client_secret, {
        payment_method: {
          card: this.stripeCard,
          billing_details: { name: 'Cliente Pronto' },
        },
      });
      if (result.error) throw new Error(result.error.message);
      window.showNotification?.('Pago digital procesado', 'success');
      this.markPaymentCompleted();
    } catch (error) {
      window.showNotification?.(
        (error as Error).message || 'Error al procesar pago digital',
        'error'
      );
    }
  }

  private async submitClipPayment(): Promise<void> {
    try {
      await requestJSON(`/api/sessions/${this.session.id}/pay/clip`, { method: 'POST' });
      window.showNotification?.('Pago con terminal registrado', 'success');
      this.markPaymentCompleted();
    } catch (error) {
      window.showNotification?.(
        (error as Error).message || 'Error al procesar pago con terminal',
        'error'
      );
    }
  }

  private markPaymentCompleted(): void {
    this.closeAllModals();
    window.document.getElementById('success-modal')?.classList.add('active');
    void this.refreshOrders(true);

    void this.showPostPaymentFeedback();
  }

  private async showPostPaymentFeedback(): Promise<void> {
    try {
      const isAnonymous = isAnonymousSession();
      const action = await showPostPaymentFeedbackModal(this.session.id, isAnonymous);

      if (action === 'open-feedback') {
        // User wants to give feedback - redirect to feedback form
        window.location.href = `/feedback?session_id=${this.session.id}`;
      } else {
        // User skipped or timeout occurred - cleanup based on session type
        if (!isAnonymous) {
          // For logged-in users, trigger email feedback as fallback
          void this.triggerFeedbackEmail();
        }
        // The cleanup and redirect is already handled by post-payment-feedback.ts
      }
    } catch (error) {
      console.warn('[thank-you] Error showing post-payment feedback:', error);
      // Fallback: redirect with cleanup
      redirectAfterPayment(isAnonymousSession());
    }
  }

  private async triggerFeedbackEmail(): Promise<void> {
    try {
      if (!this.session || !this.session.id) return;

      await fetch(`/api/orders/${this.session.id}/feedback/email-trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
    } catch (error) {
      console.warn('[thank-you] Error triggering feedback email:', error);
    }
  }

  private closeAllModals(): void {
    document.querySelectorAll('.modal').forEach((modal) => modal.classList.remove('active'));
  }

  private async refreshOrders(silent = false): Promise<void> {
    try {
      const payload = await requestJSON<{
        orders: ThankYouOrder[];
        session_summary: ThankYouSession;
      }>(`/api/session/${this.session.id}/orders`);
      this.orders = (payload.orders || []).map((order) => ({
        ...order,
        status: this.normalizeStatus(
          order.workflow_status_legacy || order.workflow_status || order.status
        ),
      }));
      this.sessionSummary = payload.session_summary || this.sessionSummary;
      this.renderOrderHistory();
      this.updateEstimatedTime();
    } catch (error) {
      if (!silent) {
        window.showNotification?.(
          (error as Error).message || 'No pudimos actualizar el estado del pedido',
          'warning'
        );
      }
    }
  }

  private setupRealtime(): void {
    if (!window.NotificationManager || !this.data.notificationStreamUrl) return;
    try {
      this.notificationManager = new window.NotificationManager(this.data.notificationStreamUrl);
      this.notificationManager.connect();
      this.notificationManager.on('payment_confirmed', () => {
        window.document.getElementById('success-modal')?.classList.add('active');
        void this.refreshOrders(true);
      });
      this.notificationManager.on('waiter_call', () => {
        window.showNotification?.('El mesero recibió tu llamado', 'success');
      });
      this.notificationManager.on('session_closed', () => {
        window.showNotification?.('Tu sesión ha sido cerrada. ¡Gracias por tu visita!', 'success');
      });
      this.notificationManager.on('all', (event: { type?: string }) => {
        const types = new Set([
          'order_status_changed',
          'order_status_update',
          'order_ready',
          'order_delivered',
        ]);
        if (event && event.type && types.has(event.type)) {
          void this.refreshOrders(true);
        }
      });
    } catch (error) {
      console.warn('[thank-you] realtime not available', error);
    }
  }

  private setupToasts(): void {
    const params = new URLSearchParams(window.location.search);
    const fromCheckout = params.get('from_checkout') === '1';
    const shown = sessionStorage.getItem('pronto-toasts-shown');
    if (fromCheckout && !shown) {
      this.showDetailsToast();
      sessionStorage.setItem('pronto-toasts-shown', 'true');
    }
  }

  private showDetailsToast(): void {
    const toast = document.getElementById('details-toast');
    if (!toast) return;
    toast.classList.add('visible');
    window.setTimeout(() => toast.classList.add('hide'), 4000);
  }

  private selectTipPercentage(percentage: number): void {
    document.querySelectorAll('[data-tip-percentage]').forEach((btn) => {
      btn.classList.toggle(
        'active',
        Number(btn.getAttribute('data-tip-percentage')) === percentage
      );
    });
    const subtotal = this.sessionSummary.subtotal;
    const amount = (subtotal * percentage) / 100;
    document
      .getElementById('payment-tip')
      ?.replaceChildren(document.createTextNode(this.formatCurrency(amount)));
    document
      .getElementById('payment-total')
      ?.replaceChildren(
        document.createTextNode(this.formatCurrency(this.sessionSummary.total_amount + amount))
      );
  }

  private formatCurrency(value: number): string {
    return (
      window.formatCurrency?.(value, {
        locale: window.APP_SETTINGS?.currency_locale || 'es-MX',
        currency: window.APP_SETTINGS?.currency_code || window.APP_CONFIG.currency_code,
      }) || `${window.APP_CONFIG.currency_symbol}${(value || 0).toFixed(2)}`
    );
  }

  private normalizeStatus(status?: string): string {
    if (!status) return 'requested';
    const key = status.toLowerCase();
    const legacyKey = CANONICAL_TO_LEGACY[key] || key;
    return this.statusMaps.classMap[legacyKey] || legacyKey;
  }

  private getOrderMeta(status: string): {
    key: string;
    label: string;
    icon: string;
    progress: number;
  } {
    const normalized = this.normalizeStatus(status);
    return {
      key: normalized,
      label: this.statusMaps.labels[normalized] || status || 'En proceso',
      icon: this.statusMaps.icons[normalized] || '📦',
      progress: this.statusMaps.progress[normalized] || 15,
    };
  }

  private renderOrderHistory(): void {
    const container = document.getElementById('order-history');
    if (!container) return;

    const orders =
      this.orders
        .sort(
          (a, b) => new Date(b.created_at || '').getTime() - new Date(a.created_at || '').getTime()
        )
        .map((order) => {
          const meta = this.getOrderMeta(order.status);
          const itemsHtml =
            order.items
              ?.map(
                (item) => `
                    <div class="order-history-item">
                        <div class="order-item-quantity">${escape(item.quantity)}x</div>
                        <div class="order-item-name">${escape(item.name)}</div>
                        <div class="order-item-total">${escape(this.formatCurrency(item.total))}</div>
                    </div>
                `
              )
              .join('') || '';

          return `
                    <div class="order-history-card">
                        <div class="order-header">
                            <div class="order-meta">
                                <span class="order-status ${escape(meta.key)}">${escape(meta.icon)}</span>
                                <span class="order-label">${escape(meta.label)}</span>
                            </div>
                            <div class="order-id">#${escape(order.id)}</div>
                        </div>
                        <div class="order-progress">
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: ${escape(meta.progress)}%"></div>
                            </div>
                        </div>
                        <div class="order-total">${escape(this.formatCurrency(order.total_amount))}</div>
                        <div class="order-items">${itemsHtml}</div>
                    </div>
                `;
        })
        .join('') || '<p class="empty-state">No hay órdenes aún</p>';

    container.innerHTML = orders;
  }

  private updateEstimatedTime(): void {
    if (!this.estimatedTime.enabled) return;

    const timeElement = document.getElementById('estimated-delivery-time');
    if (!timeElement) return;

    const { min, max } = this.estimatedTime;
    timeElement.textContent = `Tiempo estimado: ${min}-${max} minutos`;
  }
}

declare global {
  interface Window {
    THANK_YOU_DATA?: ThankYouData;
    __PRONTO_TS_THANK_YOU__?: boolean;
    APP_CONFIG?: { currency_symbol: string };
    APP_SETTINGS?: {
      currency_locale?: string;
      currency_code?: string;
      checkout_prompt_duration_seconds?: number;
      checkout_default_method?: string;
    };
    Stripe?: stripe.StripeStatic;
    NotificationManager?: new (url: string) => {
      connect: () => void;
      on: (event: string, callback: (payload: any) => void) => void;
    };
    showNotification?: (message: string, type: 'success' | 'error' | 'warning' | 'info') => void;
    formatCurrency?: (value: number, options: { locale: string; currency: string }) => string;
    cancelPendingOrder?: () => void;
  }
}

bootstrapModule(
  '[data-thank-you-root]',
  (root) => {
    initThankYouPage(root);
  },
  { name: 'thank-you' }
);
