<template>
  <div class="cart-wrapper">
    <!-- Backdrop -->
    <div
      class="cart-backdrop"
      :class="{ 'open': store.isOpen }"
      @click="store.closeCart()"
      id="cart-backdrop"
    ></div>

    <!-- Panel -->
    <div
      class="cart-panel"
      :class="{ 'open': store.isOpen }"
      id="cart-panel"
    >
      <div class="cart-header">
        <h2>Tu pedido</h2>
        <button class="cart-close" @click="store.closeCart()">×</button>
      </div>

      <div class="cart-items" id="cart-items">
        <!-- Empty State -->
        <div v-if="store.isEmpty" class="empty-state">
          <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="9" cy="21" r="1" />
            <circle cx="20" cy="21" r="1" />
            <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
          </svg>
          <h3 class="empty-state-title">Tu carrito está vacío</h3>
          <p class="empty-state-description">Agrega algunos platillos deliciosos para empezar</p>
          <button class="btn btn-primary" @click="handleBackToMenu">Ver menú</button>
        </div>

        <!-- Cart Items List -->
        <template v-else>
          <div v-for="(item, index) in store.items" :key="item.id + '-' + index" class="cart-item">
            <img
              :src="item.image || ''"
              :alt="item.name"
              class="cart-item-image"
              loading="lazy"
              @error="handleImageError"
            >

            <div class="cart-item-info">
              <h4 class="cart-item-name">{{ item.name }}</h4>
              <p v-if="item.extras && item.extras.length" class="cart-item-extras">
                + {{ item.extras.join(', ') }}
              </p>

              <div class="cart-item-controls">
                <button
                  class="quantity-btn"
                  @click="store.updateItemQuantity(index, -1)"
                  aria-label="Disminuir cantidad"
                >-</button>

                <span class="cart-item-quantity">{{ item.quantity }}</span>

                <button
                  class="quantity-btn"
                  @click="store.updateItemQuantity(index, 1)"
                  aria-label="Aumentar cantidad"
                >+</button>

                <span class="cart-item-price">
                  {{ formatPrice((item.price + item.extrasTotal) * item.quantity) }}
                </span>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- Footer -->
      <div v-if="!store.isEmpty" class="cart-footer" id="cart-footer">
        <div class="cart-total">
          <span>Total:</span>
          <span id="cart-total">{{ formatPrice(store.totalPrice) }}</span>
        </div>
        <div class="cart-actions">
          <button
            class="btn btn-secondary btn--small"
            id="clear-cart-btn"
            @click="store.clearCart()"
            title="Vaciar carrito"
          >
            🗑️ Vaciar
          </button>
          <button
            class="checkout-btn btn btn-primary btn--full"
            id="checkout-btn"
            @click="handleCheckout"
          >
            Ir a pagar
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { cartStore as store } from '../store/cart';

// Formatting Logic
const formatPrice = (value: number): string => {
  const settings = (window as any).APP_SETTINGS || {};
  const config = (window as any).APP_CONFIG || {};

  const locale = settings.currency_locale || 'es-MX';
  const currency = settings.currency_code || config.currency_code || 'MXN';

  try {
    return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(value || 0);
  } catch {
    const symbol = settings.currency_symbol || config.currency_symbol || '$';
    return `${symbol}${(value || 0).toFixed(2)}`;
  }
};

const handleImageError = (e: Event) => {
  const target = e.target as HTMLImageElement;
  target.style.display = 'none'; // Or set placeholder
};

const handleBackToMenu = () => {
  store.closeCart();
  if (typeof (window as any).backToMenu === 'function') {
    (window as any).backToMenu();
  }
};

const handleCheckout = (event: Event) => {
  event.preventDefault();
  store.closeCart();

  if (typeof (window as any).proceedToCheckout === 'function') {
    (window as any).proceedToCheckout();
  } else {
    window.location.href = '/checkout';
  }
};
</script>

<style scoped>
/* Reuse existing styles where possible, but add specific fixes if needed */
/* Ensure the wrapper doesn't break layout */
.cart-wrapper {
  display: contents;
}
</style>
