/**
 * Cart Persistence Module
 * Handles cart state that persists across page navigations
 * Works independently of MenuFlow
 *
 * Storage strategy:
 * - Authenticated users: Cart stored keyed by user email
 * - Anonymous users: Cart stored keyed by anonymous client ID
 */

export interface CartItem {
  id: number;
  name: string;
  price: number;
  quantity: number;
  image?: string | null;
  extras: string[];
  extrasTotal: number;
  modifiers: number[];
  addedAt?: number; // Timestamp when item was added
}

const ANONYMOUS_CLIENT_ID_KEY = 'pronto-anonymous-client-id';
const USER_STORAGE_KEY = 'pronto-user';
const SESSION_CART_KEY = 'pronto-cart-session-v2';
const CART_VERSION = 'v2-pronto'; // Bump to invalidate old carts

let cartInstance: CartPersistence | null = null;

export class CartPersistence {
  private cart: CartItem[] = [];
  private listeners: Set<(cart: CartItem[]) => void> = new Set();
  private storageKey: string;

  constructor() {
    this.storageKey = this.getStorageKey();
    this.restoreCart();
  }

  static getInstance(): CartPersistence {
    if (!cartInstance) {
      cartInstance = new CartPersistence();
    }
    return cartInstance;
  }

  private getStorageKey(): string {
    const user = this.getCurrentUser();
    if (user && user.email) {
      const key = `pronto-cart-user-${user.email.toLowerCase().replace(/[^a-z0-9@.]/g, '_')}-${CART_VERSION}`;
      console.log('[CartPersistence] Using user-based storage key:', key);
      return key;
    }

    // Check for legacy cart key first (optional, maybe skip to force clear)
    // We skip legacy checks to force new version

    // Get or create anonymous client ID
    let anonId = localStorage.getItem(ANONYMOUS_CLIENT_ID_KEY);
    if (!anonId) {
      anonId = this.generateAnonymousId();
      localStorage.setItem(ANONYMOUS_CLIENT_ID_KEY, anonId);
      console.log('[CartPersistence] Generated new anonymous client ID:', anonId);
    } else {
      console.log('[CartPersistence] Using existing anonymous client ID:', anonId);
    }

    const key = `pronto-cart-anon-${anonId}-${CART_VERSION}`;
    console.log('[CartPersistence] Using anonymous storage key:', key);
    return key;
  }

  private getCurrentUser(): { email: string } | null {
    try {
      const raw = localStorage.getItem(USER_STORAGE_KEY);
      if (raw) {
        const user = JSON.parse(raw);
        if (user && user.email) {
          return { email: user.email };
        }
      }
    } catch {
      // Ignore parse errors
    }
    return null;
  }

  private generateAnonymousId(): string {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
    return `anon-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
  }

  getCart(): CartItem[] {
    return [...this.cart];
  }

  addItem(item: CartItem): void {
    const itemWithTimestamp = {
      ...item,
      addedAt: Date.now()
    };
    this.cart.push(itemWithTimestamp);
    this.saveCart();
    this.notifyListeners();
  }

  updateItemQuantity(index: number, delta: number): void {
    const item = this.cart[index];
    if (!item) return;

    item.quantity += delta;
    if (item.quantity <= 0) {
      this.cart.splice(index, 1);
    }
    this.saveCart();
    this.notifyListeners();
  }

  removeItem(index: number): void {
    this.cart.splice(index, 1);
    this.saveCart();
    this.notifyListeners();
  }

  clearCart(): void {
    this.cart = [];
    this.saveCart();
    this.notifyListeners();
  }

  getTotalCount(): number {
    return this.cart.reduce((sum, item) => sum + item.quantity, 0);
  }

  getTotalPrice(): number {
    return this.cart.reduce((sum, item) => {
      return sum + (item.price + item.extrasTotal) * item.quantity;
    }, 0);
  }

  isEmpty(): boolean {
    return this.cart.length === 0;
  }

  getOldItems(maxAgeMinutes: number = 10): CartItem[] {
    const maxAgeMs = maxAgeMinutes * 60 * 1000;
    const now = Date.now();
    return this.cart.filter(item => {
      const age = now - (item.addedAt || 0);
      return age > maxAgeMs;
    });
  }

  hasOldItems(maxAgeMinutes: number = 10): boolean {
    return this.getOldItems(maxAgeMinutes).length > 0;
  }

  clearOldItems(maxAgeMinutes: number = 10): void {
    const maxAgeMs = maxAgeMinutes * 60 * 1000;
    const now = Date.now();
    const originalLength = this.cart.length;
    this.cart = this.cart.filter(item => {
      const age = now - (item.addedAt || 0);
      return age <= maxAgeMs;
    });
    if (this.cart.length !== originalLength) {
      this.saveCart();
      this.notifyListeners();
      console.log(`[CartPersistence] Cleared ${originalLength - this.cart.length} old items`);
    }
  }

  addListener(callback: (cart: CartItem[]) => void): void {
    this.listeners.add(callback);
  }

  removeListener(callback: (cart: CartItem[]) => void): void {
    this.listeners.delete(callback);
  }

  private restoreCart(): void {
    try {
      const sessionRaw = sessionStorage.getItem(SESSION_CART_KEY);
      const raw = sessionRaw ?? localStorage.getItem(this.storageKey);
      if (!raw) {
        console.log('[CartPersistence] No cart found for key:', this.storageKey);
        return;
      }

      const parsed = JSON.parse(raw) as unknown;
      const items = Array.isArray(parsed)
        ? parsed
        : typeof parsed === 'object' &&
          parsed &&
          Array.isArray((parsed as { items?: unknown }).items)
          ? (parsed as { items: unknown[] }).items
          : [];

      this.cart = items
        .filter((item): item is CartItem => Boolean(item))
        .map((item) => ({
          id: Number((item as CartItem).id),
          name: (item as CartItem).name,
          price: Number((item as CartItem).price || 0),
          quantity: Number((item as CartItem).quantity || 0),
          image: (item as CartItem).image,
          extras: Array.isArray((item as CartItem).extras) ? (item as CartItem).extras : [],
          extrasTotal: Number((item as CartItem).extrasTotal || 0),
          modifiers: Array.isArray((item as CartItem).modifiers)
            ? (item as CartItem).modifiers
            : [],
          addedAt: Number((item as any).addedAt) || Date.now(),
        }))
        .filter((item) => item.id && item.quantity > 0);

      console.log(
        '[CartPersistence] Restored cart:',
        this.cart.length,
        'items (key:',
        sessionRaw ? SESSION_CART_KEY : this.storageKey,
        ')'
      );

      if (!sessionRaw) {
        sessionStorage.setItem(SESSION_CART_KEY, JSON.stringify(this.cart));
      }
    } catch (error) {
      console.warn('[CartPersistence] Failed to restore cart:', error);
      this.cart = [];
    }
  }

  private saveCart(): void {
    try {
      sessionStorage.setItem(SESSION_CART_KEY, JSON.stringify(this.cart));
      localStorage.setItem(this.storageKey, JSON.stringify(this.cart));
      console.log(
        '[CartPersistence] Saved cart:',
        this.cart.length,
        'items (key:',
        SESSION_CART_KEY,
        ')'
      );
    } catch (error) {
      console.warn('[CartPersistence] Failed to save cart:', error);
      this.handleStorageError(error);
    }
  }

  private handleStorageError(error: unknown): void {
    if (this.isQuotaExceededError(error)) {
      console.warn('[CartPersistence] Storage quota exceeded, clearing cart');
      this.notifyStorageError('El carrito está lleno. Intenta eliminar algunos productos.');
      this.clearCart();
    } else if (this.isStorageBlockedError(error)) {
      console.warn('[CartPersistence] Storage blocked, using in-memory only');
      this.notifyStorageError(
        'No se pudo guardar el carrito. El navegador puede estar en modo privado.'
      );
    } else {
      console.warn('[CartPersistence] Unknown storage error:', error);
    }
  }

  private isQuotaExceededError(error: unknown): boolean {
    if (error instanceof DOMException) {
      return (
        error.name === 'QuotaExceededError' ||
        error.code === DOMException.QUOTA_EXCEEDED_ERR ||
        error.message.includes('QuotaExceeded') ||
        error.message.includes('storage')
      );
    }
    return false;
  }

  private isStorageBlockedError(error: unknown): boolean {
    if (error instanceof DOMException) {
      return (
        error.name === 'SecurityError' ||
        error.code === DOMException.SECURITY_ERR ||
        error.message.includes('access') ||
        error.message.includes('private')
      );
    }
    return false;
  }

  private notifyStorageError(message: string): void {
    if (typeof window.showNotification === 'function') {
      window.showNotification(message, 'warning');
    }
  }

  private notifyListeners(): void {
    const cartCopy = [...this.cart];
    this.listeners.forEach((callback) => callback(cartCopy));
  }
}

// Global access functions for inline onclick handlers
window.getCartItems = (): CartItem[] => CartPersistence.getInstance().getCart();
window.addToCart = (item: CartItem): void => CartPersistence.getInstance().addItem(item);
window.clearCart = (): void => CartPersistence.getInstance().clearCart();
window.getCartCount = (): number => CartPersistence.getInstance().getTotalCount();
window.getCartTotal = (): number => CartPersistence.getInstance().getTotalPrice();
window.isCartEmpty = (): boolean => CartPersistence.getInstance().isEmpty();
