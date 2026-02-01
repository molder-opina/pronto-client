/**
 * CHECKOUT HANDLER - Checkout Process and Form Submission
 * Handles checkout flow, form submission, and payment preferences
 */

import { requestJSON } from '../core/http';
import type { CartItem } from './cart-manager';
import { CartPersistence } from './cart-persistence';

const DEFAULT_COUNTRY = '+52';
const ANONYMOUS_CLIENT_ID_KEY = 'pronto-anonymous-client-id';

interface CheckoutResponse {
  session_id?: number;
  session_summary?: { can_pay_digitally?: boolean };
  error?: string;
  message?: string;
}

let onCheckoutSuccessCallbacks: Array<() => void> = [];

export function onCheckoutSuccess(callback: () => void): void {
  onCheckoutSuccessCallbacks.push(callback);
}

export function clearCartOnCheckoutSuccess(): void {
  const persistence = CartPersistence.getInstance();
  persistence.clearCart();
  console.log('[CheckoutHandler] Cart cleared after successful checkout');
  onCheckoutSuccessCallbacks.forEach(callback => callback());
  onCheckoutSuccessCallbacks = [];
}

type CheckoutMethod = 'cash' | 'terminal' | 'digital';

export class CheckoutHandler {
  private isSubmitting = false;
  private canPayDigital = false;
  private checkoutPreferenceTimer: number | null = null;

  private readonly elements = {
    menuSections: document.getElementById('menu-sections'),
    categoryTabs: document.getElementById('category-tabs'),
    checkoutSection: document.getElementById('checkout-section'),
    checkoutSummary: document.getElementById('checkout-summary'),
    checkoutTotal: document.getElementById('checkout-total'),
    checkoutForm: document.getElementById('checkout-form') as HTMLFormElement | null,
    checkoutFeedback: document.getElementById('checkout-feedback'),
    phoneCountrySelect: document.getElementById('phone-country-code') as HTMLSelectElement | null,
    checkoutPreference: document.getElementById('checkout-preference-overlay'),
    preferenceTimer: document.getElementById('checkout-preference-timer'),
    preferenceDefault: document.getElementById('checkout-preference-default'),
  };

  /**
   * Navigate to checkout view
   */
  /**
   * Navigate to checkout view
   */
  public proceedToCheckout(
    cart: CartItem[],
    formatPrice: (value: number) => string,
    onSuccess?: () => void
  ): void {
    if (!cart.length) {
      window.showNotification?.('Tu carrito está vacío', 'error');
      return;
    }

    if (typeof (window as any).switchView === 'function') {
      (window as any).switchView('details');
    }

    // Force visibility states to ensure transition happens
    const main = document.querySelector('main');
    if (main) main.style.display = 'none';

    if (this.elements.checkoutSection) {
      this.elements.checkoutSection.style.display = 'block';
      this.elements.checkoutSection.classList.add('active');
    }

    // Legacy fallback elements
    this.elements.menuSections?.setAttribute('style', 'display:none;');
    this.elements.categoryTabs?.setAttribute('style', 'display:none;');

    const footer = document.querySelector('.footer');
    if (footer) footer.classList.add('hide-on-checkout');

    this.renderCheckoutSummary(cart, formatPrice);
    this.prefillCheckoutForm();
    // updateFooterVisibility handled by switchView usually
    // this.updateFooterVisibility();

    window.scrollTo({ top: 0, behavior: 'smooth' });

    if (onSuccess) onSuccess();
  }

  /**
   * Navigate back to menu view
   */
  public backToMenu(): void {
    if (typeof (window as any).switchView === 'function') {
      (window as any).switchView('menu');
    } else {
      this.elements.menuSections?.setAttribute('style', 'display:block;');
      this.elements.categoryTabs?.setAttribute('style', 'display:flex;');
      this.elements.checkoutSection?.classList.remove('active');
      const footer = document.querySelector('.footer');
      if (footer) footer.classList.remove('hide-on-checkout');
    }
  }

  /**
   * Render checkout summary with cart items
   */
  public renderCheckoutSummary(cart: CartItem[], formatPrice: (value: number) => string): void {
    if (!this.elements.checkoutSummary || !this.elements.checkoutTotal) return;

    const isEmpty = !cart.length;
    const submitBtn = document.querySelector(
      'button[type="submit"][form="checkout-form"]'
    ) as HTMLButtonElement;

    if (isEmpty) {
      const empty = document.createElement('div');
      empty.className = 'summary-item';
      empty.style.justifyContent = 'center';
      empty.style.color = 'var(--muted)';
      empty.textContent = 'No hay productos en tu carrito todavía';
      this.elements.checkoutSummary.replaceChildren(empty);
      this.elements.checkoutTotal.textContent = formatPrice(0);

      // Hide the entire accordion if empty
      const accordion = document.getElementById('accordion-current-order');
      if (accordion) accordion.style.display = 'none';

      // Disable submit button when cart is empty
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.style.opacity = '0.5';
        submitBtn.style.cursor = 'not-allowed';
        submitBtn.title = 'Debes agregar al menos un producto al carrito';
      }
      return;
    }

    // Show accordion and enable submit button when cart has items
    const accordion = document.getElementById('accordion-current-order');
    if (accordion) accordion.style.display = 'block';

    // Enable submit button when cart has items
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.style.opacity = '1';
      submitBtn.style.cursor = 'pointer';
      submitBtn.title = '';
    }

    let total = 0;

    const summaryFragment = document.createDocumentFragment();
    cart.forEach((item) => {
      const itemTotal = (item.price + item.extrasTotal) * item.quantity;
      total += itemTotal;

      const summaryItem = document.createElement('div');
      summaryItem.className = 'summary-item';

      const details = document.createElement('div');
      const title = document.createElement('div');
      title.textContent = `${item.quantity}x ${item.name}`;
      details.appendChild(title);

      if (item.extras?.length) {
        const extras = document.createElement('div');
        extras.className = 'summary-extras';
        extras.textContent = `+ ${item.extras.join(', ')}`;
        details.appendChild(extras);
      }

      const price = document.createElement('div');
      price.textContent = formatPrice(itemTotal);

      summaryItem.appendChild(details);
      summaryItem.appendChild(price);
      summaryFragment.appendChild(summaryItem);
    });

    this.elements.checkoutSummary.replaceChildren(summaryFragment);

    this.elements.checkoutTotal.textContent = formatPrice(total);
  }

  /**
   * Refresh checkout summary if checkout is active
   */
  public refreshCheckoutSummaryIfActive(
    cart: CartItem[],
    formatPrice: (value: number) => string
  ): void {
    if (this.elements.checkoutSection?.classList.contains('active')) {
      this.renderCheckoutSummary(cart, formatPrice);
    }
  }

  /**
   * Submit checkout form
   */
  public async submitCheckout(
    cart: CartItem[],
    sessionId: number | null,
    onSuccess?: (response: CheckoutResponse) => void
  ): Promise<void> {
    if (!this.elements.checkoutFeedback || !this.elements.checkoutForm) {
      console.error('[CheckoutHandler] Missing required DOM elements');
      return;
    }

    console.log('[CheckoutHandler] submitCheckout called');
    console.log('[CheckoutHandler] Cart length:', cart.length);
    console.log(
      '[CheckoutHandler] Cart items:',
      JSON.stringify(
        cart.map((i) => ({
          id: i.id,
          name: i.name,
          quantity: i.quantity,
          price: i.price,
          modifiers: i.modifiers,
        }))
      )
    );

    if (!cart.length) {
      window.showNotification?.('Tu carrito está vacío', 'warning');
      console.warn('[CheckoutHandler] Cart is empty, aborting checkout');
      return;
    }

    if (this.isSubmitting) {
      console.log('[CheckoutHandler] Submission already in progress, ignoring');
      return;
    }

    this.isSubmitting = true;

    const submitBtn = document.querySelector(
      'button[type="submit"][form="checkout-form"]'
    ) as HTMLButtonElement | null;

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.classList.add('btn--disabled', 'btn--loading');
      submitBtn.setAttribute('aria-busy', 'true');
    }

    this.elements.checkoutFeedback.textContent = 'Enviando pedido...';
    this.elements.checkoutFeedback.className = 'feedback-message';

    // Capture FormData BEFORE disabling inputs, otherwise they are excluded
    const formData = new FormData(this.elements.checkoutForm);
    const phoneCode = this.elements.phoneCountrySelect?.value || DEFAULT_COUNTRY;
    const phoneNumber = ((formData.get('phone') as string) || '').trim();

    const formInputs =
      this.elements.checkoutForm.querySelectorAll<HTMLInputElement>('input, textarea, select');
    formInputs.forEach((input) => input.setAttribute('disabled', ''));
    const phoneDigits = phoneNumber.replace(/\D/g, '');
    const storedUser = this.getStoredUserData();

    const resolvedEmail =
      ((formData.get('email') as string) || '').trim() || storedUser?.email || undefined;
    const resolvedName =
      ((formData.get('name') as string) || '').trim() || storedUser?.name || 'Cliente Anónimo';

    if (phoneNumber && phoneDigits.length !== 10) {
      this.elements.checkoutFeedback.textContent = 'Ingresa un celular de 10 dígitos.';
      this.elements.checkoutFeedback.className = 'feedback-message error';
      window.showNotification?.('Ingresa un celular válido de 10 dígitos', 'warning');
      this.isSubmitting = false;
      return;
    }

    const payload: Record<string, unknown> = {
      customer: {
        name: resolvedName,
        email: resolvedEmail,
        phone: phoneDigits ? `${phoneCode}${phoneDigits}` : storedUser?.phone || undefined,
      },
      notes: formData.get('notes'),
      table_number: formData.get('table_number'),
      items: cart.map((item) => ({
        menu_item_id: item.id,
        quantity: item.quantity,
        modifiers: item.modifiers,
      })),
    };

    console.log('[CheckoutHandler] Payload items:', JSON.stringify(payload.items));

    if (!resolvedEmail) {
      const anonId = this.resolveAnonymousClientId();
      if (anonId) payload.anonymous_client_id = anonId;
    }

    if (sessionId) payload.session_id = sessionId;

    try {
      const response = await requestJSON<CheckoutResponse, typeof payload>('/api/orders', {
        method: 'POST',
        body: payload,
      });

      this.canPayDigital = Boolean(response.session_summary?.can_pay_digitally);

      // Update mini tracker
      (window as any).refreshMiniTracker?.();
      if (!(window as any).refreshMiniTracker) {
        document.getElementById('mini-tracker')?.classList.add('visible');
      }

      // Show success notification
      window.showNotification?.('✅ ¡Pedido creado exitosamente!', 'success');

      // Show prominent email confirmation if email was provided
      if (resolvedEmail) {
        // Use the dedicated modal for email confirmation (more visible than toast)
        this.showEmailConfirmationModal(resolvedEmail);
      }

      // Clear cart on successful checkout to prevent duplicate orders
      clearCartOnCheckoutSuccess();

      // Switch to Orders tab instead of redirecting to /thanks page
      if (typeof (window as any).switchView === 'function') {
        (window as any).switchView('orders');
      } else {
        // Fallback
        const ordersTab = document.getElementById('tab-orders');
        ordersTab?.click();
      }

      // Refresh active orders to show the new order
      // Refresh active orders to show the new order
      if (typeof window.checkActiveOrders === 'function') {
        setTimeout(() => {
          window.checkActiveOrders?.();
        }, 500);
      }

      if (onSuccess) onSuccess(response);
    } catch (error) {
      this.elements.checkoutFeedback.textContent = (error as Error).message;
      this.elements.checkoutFeedback.className = 'feedback-message error';
    } finally {
      const submitBtn = document.querySelector(
        'button[type="submit"][form="checkout-form"]'
      ) as HTMLButtonElement | null;

      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.classList.remove('btn--disabled', 'btn--loading');
        submitBtn.removeAttribute('aria-busy');
      }

      const formInputs =
        this.elements.checkoutForm?.querySelectorAll<HTMLInputElement>('input, textarea, select');
      formInputs?.forEach((input) => input.removeAttribute('disabled'));

      this.isSubmitting = false;
    }
  }

  /**
   * Open checkout preference dialog
   */
  public openCheckoutPreference(): void {
    if (!this.elements.checkoutPreference) return;

    const defaultMethod = this.resolveDefaultCheckoutMethod();

    if (this.elements.preferenceDefault) {
      this.elements.preferenceDefault.textContent =
        defaultMethod === 'cash' ? 'Efectivo' : 'Tarjeta';
    }

    this.elements.checkoutPreference.classList.add('visible');

    let remaining = Number(window.APP_SETTINGS?.checkout_prompt_duration_seconds || 6);

    if (this.elements.preferenceTimer) {
      this.elements.preferenceTimer.textContent = String(remaining);
    }

    if (this.checkoutPreferenceTimer) {
      window.clearInterval(this.checkoutPreferenceTimer);
    }

    this.checkoutPreferenceTimer = window.setInterval(() => {
      remaining -= 1;

      if (this.elements.preferenceTimer) {
        this.elements.preferenceTimer.textContent = String(Math.max(remaining, 0));
      }

      if (remaining <= 0) {
        this.handleCheckoutPreference(defaultMethod);
      }
    }, 1000);

    this.elements.checkoutPreference
      .querySelectorAll<HTMLButtonElement>('[data-checkout-method]')
      .forEach((button) =>
        button.addEventListener('click', () => {
          const method = button.dataset.checkoutMethod as CheckoutMethod;
          this.handleCheckoutPreference(method);
        })
      );
  }

  /**
   * Prefill checkout form from stored user data
   */
  private prefillCheckoutForm(): void {
    try {
      const userData = this.getStoredUserData();
      if (!userData) return;

      const nameInput = document.getElementById('customer-name') as HTMLInputElement | null;
      const emailInput = document.getElementById('customer-email') as HTMLInputElement | null;
      const phoneInput = document.getElementById('customer-phone') as HTMLInputElement | null;

      if (nameInput && userData.name) {
        nameInput.value = userData.name;
      }

      if (emailInput && userData.email) {
        emailInput.value = userData.email;
      }

      if (phoneInput && userData.phone) {
        // Remove country code prefix if present (e.g., +52)
        const phone = userData.phone.replace(/^\+\d{1,3}/, '');
        phoneInput.value = phone;
      }
    } catch (error) {
      console.warn('[CheckoutHandler] Error prefilling checkout form:', error);
    }
  }

  /**
   * Handle checkout preference selection
   */
  private handleCheckoutPreference(method: CheckoutMethod): void {
    if (this.checkoutPreferenceTimer) {
      window.clearInterval(this.checkoutPreferenceTimer);
      this.checkoutPreferenceTimer = null;
    }

    this.elements.checkoutPreference?.classList.remove('visible');
    window.showNotification?.(`Preferencia registrada: ${method}`, 'success');
  }

  /**
   * Resolve default checkout method from settings
   */
  private resolveDefaultCheckoutMethod(): CheckoutMethod {
    const configured = (window.APP_SETTINGS?.checkout_default_method || 'cash').toLowerCase();

    if (configured === 'terminal') return 'terminal';
    if (configured === 'digital') return 'digital';
    return 'cash';
  }

  /**
   * Update footer visibility based on checkout state
   */
  private updateFooterVisibility(): void {
    const footer = document.querySelector('.footer') as HTMLElement;
    if (!footer) return;

    const isCheckoutActive = this.elements.checkoutSection?.classList.contains('active');

    if (isCheckoutActive) {
      footer.classList.add('hide-on-checkout');
    } else {
      footer.classList.remove('hide-on-checkout');
    }
  }

  /**
   * Get stored user data from the customer session (server-provided).
   */
  private getStoredUserData(): { name?: string; email?: string; phone?: string } | null {
    try {
      const session = window.APP_SESSION;
      return session?.customer || null;
    } catch (error) {
      console.warn('[CheckoutHandler] Error reading stored user data:', error);
      return null;
    }
  }

  /**
   * Resolve or create anonymous client ID
   */
  private resolveAnonymousClientId(): string | null {
    const globalGetter =
      window.getOrCreateAnonymousClientId ||
      window.ensureAnonymousClientId ||
      window.getAnonymousClientId;

    if (typeof globalGetter === 'function') {
      const fromGlobal = globalGetter();
      if (fromGlobal) return fromGlobal;
    }

    const stored = localStorage.getItem(ANONYMOUS_CLIENT_ID_KEY);
    if (stored) return stored;

    const generated =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `anon-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;

    try {
      localStorage.setItem(ANONYMOUS_CLIENT_ID_KEY, generated);
    } catch (error) {
      console.warn('[CheckoutHandler] Could not persist anonymous client ID:', error);
    }

    return generated;
  }

  /**
   * Show email confirmation modal with prominent messaging
   */
  private showEmailConfirmationModal(email: string): void {
    // Enhanced fallback: Create a custom prominent notification
    // that's more visible than standard toast
    const notification = document.createElement('div');
    notification.className = 'email-confirmation-modal';
    notification.innerHTML = `
      <div class="email-confirmation-overlay"></div>
      <div class="email-confirmation-content">
        <div class="email-confirmation-icon">📧</div>
        <h3 class="email-confirmation-title">Ticket Enviado por Email</h3>
        <p class="email-confirmation-text">
          Hemos enviado una confirmación de tu pedido a:
        </p>
        <p class="email-confirmation-email">${this.escapeHtml(email)}</p>
        <p class="email-confirmation-hint">
          Por favor revisa tu bandeja de entrada y carpeta de spam.
        </p>
        <button class="email-confirmation-close btn btn--primary">Entendido</button>
      </div>
    `;

    // Add styles inline to ensure they work
    const style = document.createElement('style');
    style.textContent = `
      .email-confirmation-modal {
        position: fixed;
        inset: 0;
        z-index: 10000;
        display: flex;
        align-items: center;
        justify-content: center;
        animation: fadeIn 0.2s ease-out;
      }
      .email-confirmation-overlay {
        position: absolute;
        inset: 0;
        background: rgba(0, 0, 0, 0.6);
      }
      .email-confirmation-content {
        position: relative;
        background: white;
        border-radius: 16px;
        padding: 2rem;
        max-width: 400px;
        width: 90%;
        text-align: center;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        animation: slideUp 0.3s ease-out;
      }
      .email-confirmation-icon {
        font-size: 4rem;
        margin-bottom: 1rem;
        animation: bounce 0.6s ease-out;
      }
      .email-confirmation-title {
        font-size: 1.5rem;
        font-weight: 700;
        margin-bottom: 1rem;
        color: #1a1a1a;
      }
      .email-confirmation-text {
        font-size: 1rem;
        color: #666;
        margin-bottom: 0.5rem;
      }
      .email-confirmation-email {
        font-size: 1.1rem;
        font-weight: 600;
        color: #007bff;
        margin-bottom: 1rem;
        word-break: break-word;
      }
      .email-confirmation-hint {
        font-size: 0.9rem;
        color: #999;
        margin-bottom: 1.5rem;
      }
      .email-confirmation-close {
        padding: 0.75rem 2rem;
        font-size: 1rem;
      }
      @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
      }
      @keyframes slideUp {
        from { transform: translateY(20px); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
      }
      @keyframes bounce {
        0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
        40% { transform: translateY(-10px); }
        60% { transform: translateY(-5px); }
      }
    `;

    document.head.appendChild(style);
    document.body.appendChild(notification);

    // Close handlers
    const closeBtn = notification.querySelector('.email-confirmation-close');
    const overlay = notification.querySelector('.email-confirmation-overlay');

    const closeModal = () => {
      notification.style.animation = 'fadeOut 0.2s ease-out';
      setTimeout(() => {
        notification.remove();
        style.remove();
      }, 200);
    };

    closeBtn?.addEventListener('click', closeModal);
    overlay?.addEventListener('click', closeModal);

    // Auto-close after 8 seconds
    setTimeout(closeModal, 8000);
  }

  /**
   * Escape HTML to prevent XSS
   */
  private escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}
