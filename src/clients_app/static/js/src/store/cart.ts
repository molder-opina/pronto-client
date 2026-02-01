import { reactive, computed, watch } from 'vue';
import { CartPersistence, type CartItem } from '../modules/cart-persistence';

const persistence = CartPersistence.getInstance();

export const cartStore = reactive({
  items: persistence.getCart(),
  isOpen: false,

  // Actions
  addItem(item: CartItem) {
    persistence.addItem(item);
    this.refreshFromPersistence();
    this.isOpen = true; // Auto-open on add
  },

  updateItemQuantity(index: number, delta: number) {
    persistence.updateItemQuantity(index, delta);
    this.refreshFromPersistence();
  },

  removeItem(index: number) {
    persistence.removeItem(index);
    this.refreshFromPersistence();
  },

  clearCart() {
    persistence.clearCart();
    this.refreshFromPersistence();
  },

  toggleCart() {
    this.isOpen = !this.isOpen;
    if (this.isOpen) this.checkOldItems();
  },

  closeCart() {
    this.isOpen = false;
  },

  openCart() {
    this.isOpen = true;
    this.checkOldItems();
  },

  checkOldItems() {
    if (persistence.hasOldItems(10)) {
      const count = persistence.getOldItems(10).length;
      if (typeof (window as any).showNotification === 'function') {
        (window as any).showNotification(
          `Tienes ${count} producto(s) en el carrito por más de 10 minutos. Considera revisarlos.`,
          'warning'
        );
      }
    }
  },

  // Sync helper
  refreshFromPersistence() {
    this.items = persistence.getCart();
  },

  // Computed-like getters
  get totalItems() {
    return this.items.reduce((sum, item) => sum + item.quantity, 0);
  },

  get totalPrice() {
    return this.items.reduce((sum, item) => {
      return sum + (item.price + item.extrasTotal) * item.quantity;
    }, 0);
  },

  get isEmpty() {
    return this.items.length === 0;
  }
});

// Bridge to Legacy DOM & Events
const updateLegacyDom = () => {
  const count = cartStore.totalItems;
  const total = cartStore.totalPrice;

  // 1. Update Badge
  const badge = document.getElementById('cart-count');
  if (badge) {
    badge.textContent = String(count);
    badge.style.display = count > 0 ? 'inline-block' : 'none';

    // Animate pulse
    if (count > 0) {
      badge.classList.remove('cart-badge--pulse');
      void badge.offsetWidth;
      badge.classList.add('cart-badge--pulse');
    }
  }

  // 2. Dispatch Event for sticky bar
  window.dispatchEvent(new CustomEvent('cart-updated', {
    detail: { count, total }
  }));
};

// Watch for state changes
watch(() => cartStore.items, updateLegacyDom, { deep: true });

// Initial sync when DOM is ready
const initDomSync = () => {
  updateLegacyDom();
  cartStore.checkOldItems();
};

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initDomSync);
} else {
  initDomSync();
}

// Listen to external changes (e.g. from other tabs or legacy code)
persistence.addListener((items) => {
  cartStore.items = items;
});
