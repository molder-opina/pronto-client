/**
 * MENU FLOW - Main Orchestrator
 * Coordinates menu display, search, filters, and delegates to specialized modules
 */

import { requestJSON } from '../core/http';
import { cartStore } from '../store/cart';
import { ModalManager, type MenuItem } from './modal-manager';
import { OrderTracker } from './order-tracker';
import { CheckoutHandler } from './checkout-handler';

declare global {
  interface Window {
    toggleCart: () => void;
    proceedToCheckout: () => void;
    backToMenu: () => void;
    openItemModal: (itemId: number) => void;
    openProductModal: (itemId: number) => void;
    closeItemModal: () => void;
    adjustModalQuantity: (delta: number) => void;
    addToCartFromModal: () => void;
    quickAdd: (event: Event, itemId: number) => void;
    updateCartItemQuantity: (index: number, delta: number) => void;
    handleModifierChange: (
      groupId: number,
      modifierId: number,
      maxSelection: number,
      checked: boolean,
      input?: HTMLInputElement | null,
      isSingle?: boolean
    ) => void;
    requestCheckoutFromTracker: () => void;
    cancelPendingOrder: () => void;
    viewFullTracker: () => void;
    showNotification?: (message: string, type: 'success' | 'error' | 'warning' | 'info') => void;
    APP_SETTINGS?: any;
    APP_CONFIG: any;
    resetFilters: () => void;
    switchView: (view: string) => void;
  }
}

const DEFAULT_COUNTRY = '+52';
const FILTER_STORAGE_KEY = 'pronto-menu-filters';

interface MenuCategory {
  id: number;
  name: string;
  description?: string | null;
  items: MenuItem[];
}

interface MenuResponse {
  categories: MenuCategory[];
}

export function initMenuFlow(root: HTMLElement): void {
  const app = new MenuFlow(root);
  void app.initialize();
}

export class MenuFlow {
  // Specialized managers
  private readonly modalManager: ModalManager;
  private readonly orderTracker: OrderTracker;
  private readonly checkoutHandler: CheckoutHandler;

  // Menu state
  private categories: MenuCategory[] = [];
  private searchIndex: Array<{
    id: number;
    name: string;
    description: string;
    category: string;
    price: number;
  }> = [];

  // Filter state
  private activeFilter = 'all';
  private searchQuery = '';
  private priceMin: number | null = null;
  private priceMax: number | null = null;
  private sortBy = 'recommended';
  private menuEventsBound = false;

  private readonly elements = {
    categoryTabs: document.getElementById('category-tabs'),
    menuSections: document.getElementById('menu-sections'),
    searchInput: document.getElementById('menu-search') as HTMLInputElement | null,
    searchSuggestions: document.getElementById('menu-search-suggestions'),
    filterToggleBtn: document.getElementById('filter-toggle-btn'),
    advancedFilters: document.getElementById('advanced-filters'),
    filterButtons: document.querySelectorAll<HTMLButtonElement>('.filter-chip'),
    filterCounts: document.querySelectorAll<HTMLElement>('[data-filter-count]'),
    resultsCount: document.getElementById('filters-results-count'),
    sortSelect: document.getElementById('filters-sort') as HTMLSelectElement | null,
    priceMinInput: document.getElementById('filters-price-min') as HTMLInputElement | null,
    priceMaxInput: document.getElementById('filters-price-max') as HTMLInputElement | null,
    clearFiltersBtn: document.getElementById('filters-clear-btn') as HTMLButtonElement | null,
    emptyState: document.getElementById('menu-empty-state'),
    phoneCountrySelect: document.getElementById('phone-country-code') as HTMLSelectElement | null,
    checkoutForm: document.getElementById('checkout-form') as HTMLFormElement | null,
  };

  constructor(root: HTMLElement) {
    // Initialize specialized managers
    this.modalManager = new ModalManager();
    this.orderTracker = new OrderTracker();
    this.checkoutHandler = new CheckoutHandler();
  }

  async initialize(): Promise<void> {
    this.bindGlobalFunctions();
    this.populatePhoneOptions();
    this.attachEventListeners();

    // Initialize cart (logic moved to store/Vue)
    // this.cartManager.updateCartBadge();
    // this.cartManager.renderCartItems(this.formatPrice.bind(this));

    // Load menu
    await this.loadMenu();

    // Restore filters and apply
    this.restoreFilterState();
    this.applyCatalogFilters();

    // Check for active orders
    window.setTimeout(() => this.orderTracker.checkActiveOrders().catch(console.error), 500);

    // Initial view check for checkout
    const params = new URLSearchParams(window.location.search);
    if (params.get('view') === 'details') {
      this.checkoutHandler.proceedToCheckout(
        cartStore.items,
        this.formatPrice.bind(this)
      );
    }
  }

  private bindGlobalFunctions(): void {
    // Cart functions
    window.toggleCart = () => cartStore.toggleCart();

    // Checkout functions
    window.proceedToCheckout = () => {
      this.checkoutHandler.proceedToCheckout(
        cartStore.items,
        this.formatPrice.bind(this),
        () => {
          cartStore.closeCart();
        }
      );
    };

    window.backToMenu = () => {
      this.checkoutHandler.backToMenu();
      cartStore.closeCart();
      const orderHistoryModal = document.getElementById('order-history-modal');
      orderHistoryModal?.classList.remove('active');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    // Modal functions
    window.openItemModal = (itemId: number) => this.openItemModal(itemId);
    window.openProductModal = (itemId: number) => this.openItemModal(itemId);
    window.closeItemModal = () => this.modalManager.closeModal();
    window.adjustModalQuantity = (delta: number) => {
      this.modalManager.adjustQuantity(delta, this.formatPrice.bind(this));
    };

    window.addToCartFromModal = () => {
      const cartItem = this.modalManager.getCartItemIfValid();
      if (cartItem) {
        cartStore.addItem(cartItem);
        this.checkoutHandler.refreshCheckoutSummaryIfActive(
          cartStore.items,
          this.formatPrice.bind(this)
        );
        this.modalManager.closeModal();
        window.showNotification?.('Producto agregado al carrito', 'success');
      }
    };

    // Quick add
    window.quickAdd = (event: Event, itemId: number) => this.quickAdd(event, itemId);

    // Cart item quantity
    window.updateCartItemQuantity = (index: number, delta: number) => {
      cartStore.updateItemQuantity(index, delta);
      this.checkoutHandler.refreshCheckoutSummaryIfActive(
        cartStore.items,
        this.formatPrice.bind(this)
      );
    };

    // Modifier handling
    window.handleModifierChange = (
      groupId: number,
      modifierId: number,
      maxSelection: number,
      checked: boolean,
      input?: HTMLInputElement | null,
      isSingle?: boolean
    ) => {
      const allowed = this.modalManager.handleModifierChange(
        groupId,
        modifierId,
        maxSelection,
        checked,
        isSingle,
        input,
        this.formatPrice.bind(this)
      );
      if (allowed) {
        this.modalManager.updateModifierGroupUI(groupId);
      }
    };

    // Order tracking
    window.requestCheckoutFromTracker = () => {
      void this.orderTracker.requestCheckout();
    };

    if (!(window as any).cancelPendingOrder) {
      window.cancelPendingOrder = () => this.orderTracker.cancelOrder();
    }

    if (!(window as any).viewFullTracker) {
      window.viewFullTracker = () => this.orderTracker.viewFullTracker();
    }
  }

  private attachEventListeners(): void {
    // Cart toggle button in header
    document.querySelectorAll<HTMLButtonElement>('[data-toggle-cart]').forEach((button) => {
      button.addEventListener('click', (event) => {
        event.preventDefault();
        cartStore.toggleCart();
      });
    });

    // Cart close button inside panel
    document.querySelectorAll<HTMLButtonElement>('.cart-close').forEach((button) => {
      button.addEventListener('click', () => {
        cartStore.closeCart();
      });
    });

    const backToTopBtn = document.getElementById('back-to-top');
    if (backToTopBtn) {
      const updateVisibility = () => {
        const shouldShow = window.scrollY > 260;
        backToTopBtn.classList.toggle('visible', shouldShow);
      };

      updateVisibility();
      window.addEventListener('scroll', updateVisibility, { passive: true });
      backToTopBtn.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    }

    // Filter buttons (Chips)
    this.elements.filterButtons.forEach((button) => {
      button.addEventListener('click', () => {
        this.applyFilter(button.dataset.filter || 'all');
      });
    });

    // Filter Toggle
    this.elements.filterToggleBtn?.addEventListener('click', () => {
      const filters = this.elements.advancedFilters;
      if (filters) {
        const isHidden = filters.hasAttribute('hidden');
        if (isHidden) {
          filters.removeAttribute('hidden');
          this.elements.filterToggleBtn?.classList.add('active');
        } else {
          filters.setAttribute('hidden', '');
          this.elements.filterToggleBtn?.classList.remove('active');
        }
      }
    });

    // Cart backdrop click
    document.getElementById('cart-backdrop')?.addEventListener('click', () => {
      cartStore.closeCart();
    });

    // Escape key handling
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;

      const cartPanel = document.getElementById('cart-panel');
      const modal = document.getElementById('item-modal');

      if (cartPanel?.classList.contains('open')) {
        cartStore.toggleCart();
        e.preventDefault();
      } else if (modal?.classList.contains('open')) {
        this.modalManager.closeModal();
        e.preventDefault();
      }
    });

    // Checkout form submission
    if (this.elements.checkoutForm) {
      console.log('[MenuFlow] Attaching checkout form submit listener');

      this.elements.checkoutForm.addEventListener('submit', (event) => {
        event.preventDefault();
        console.log('[MenuFlow] Checkout form submitted');

        const cart = cartStore.items;
        console.log('[MenuFlow] Cart items:', cart);

        void this.checkoutHandler.submitCheckout(
          cart,
          this.orderTracker.getSessionId(),
          (response) => {
            console.log('[MenuFlow] Checkout success callback triggered', response);
            if (response.session_id) {
              this.orderTracker.setSessionId(response.session_id);
            }
            cartStore.clearCart();

            // Switch to orders view via global switchView
            if (typeof (window as any).switchView === 'function') {
              (window as any).switchView('orders');
            }
          }
        );
      });
    } else {
      console.warn('[MenuFlow] Checkout form not found in DOM');
    }

    // Setup search and filters
    this.setupSearch();
    this.setupFilters();
  }

  private populatePhoneOptions(): void {
    if (!this.elements.phoneCountrySelect) return;
    const options = window.APP_SETTINGS?.phone_country_options || [];
    if (!options.length) {
      const fallback = document.createElement('option');
      fallback.value = DEFAULT_COUNTRY;
      fallback.textContent = DEFAULT_COUNTRY;
      this.elements.phoneCountrySelect.replaceChildren(fallback);
      return;
    }
    const fragment = document.createDocumentFragment();
    options.forEach((option: { dial_code: string; flag?: string; label: string }) => {
      const entry = document.createElement('option');
      entry.value = option.dial_code;
      entry.textContent = `${option.flag || ''} ${option.label} (${option.dial_code})`;
      if (option.dial_code === DEFAULT_COUNTRY) {
        entry.selected = true;
      }
      fragment.appendChild(entry);
    });
    this.elements.phoneCountrySelect.replaceChildren(fragment);
  }

  private async loadMenu(retryCount = 0): Promise<void> {
    if (retryCount === 0) this.renderMenuSkeleton();

    try {
      const data = await requestJSON<MenuResponse>('/api/menu');
      if (!data || !data.categories) {
        throw new Error('Datos de menú inválidos o vacíos');
      }

      this.categories = data.categories || [];
      this.renderCategoryTabs();
      this.renderMenu();
      this.refreshSearchIndex();

      // Force layout update just in case
      window.requestAnimationFrame(() => {
        this.updateSectionVisibility();
      });

    } catch (error) {
      console.error(`[MenuFlow] Error cargando menú (intento ${retryCount + 1}):`, error);

      if (retryCount < 2) {
        console.log(`[MenuFlow] Reintentando en 1s...`);
        setTimeout(() => void this.loadMenu(retryCount + 1), 1000);
        return;
      }

      if (this.elements.menuSections) {
        this.elements.menuSections.replaceChildren(
          createFragment(
            '<div class="error-state"><p>No pudimos cargar el menú.</p><button class="btn btn--primary" onclick="window.location.reload()">Reintentar</button></div>'
          )
        );
      }
    }
  }

  private renderMenuSkeleton(): void {
    if (!this.elements.menuSections) return;
    const skeletonCount = 8;
    this.elements.menuSections.replaceChildren(createFragment(`
      <div class="menu-skeleton">
        ${Array.from({ length: skeletonCount })
        .map(
          () => `
          <article class="menu-item-card menu-item-card--skeleton">
            <div class="menu-item-card__image skeleton-image"></div>
            <div class="menu-item-card__content">
              <div class="skeleton-title"></div>
              <div class="skeleton-text"></div>
              <div class="skeleton-text short"></div>
            </div>
          </article>`
        )
        .join('')}
      </div>`));
  }

  private getCategoryIcon(name: string): string {
    const lower = name.toLowerCase();

    // Default SVG properties
    const props = 'width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';

    if (lower.includes('bebida') || lower.includes('jugo') || lower.includes('refresco') || lower.includes('café')) {
      // Cup / Drink icon
      return `<svg ${props} viewBox="0 0 24 24"><path d="M18 8h1a4 4 0 0 1 0 8h-1"></path><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"></path><line x1="6" y1="1" x2="6" y2="4"></line><line x1="10" y1="1" x2="10" y2="4"></line><line x1="14" y1="1" x2="14" y2="4"></line></svg>`;
    }
    else if (lower.includes('postre') || lower.includes('dulce') || lower.includes('pastel')) {
      // Cake / Muffin icon (Cherry on top)
      return `<svg ${props} viewBox="0 0 24 24"><path d="M20 21v-8a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8"></path><path d="M4 16s.5-1 2-1 2.5 2 4 2 2.5-2 4-2 2.5 2 4 2 2-1 2-1"></path><path d="M2 21h20"></path><path d="M7 8v2"></path><path d="M12 8v2"></path><path d="M17 8v2"></path><path d="M7 4h.01"></path><path d="M12 4h.01"></path><path d="M17 4h.01"></path></svg>`;
    }
    else if (lower.includes('entrada') || lower.includes('ensalada') || lower.includes('botana')) {
      // Salad / Bowl icon
      return `<svg ${props} viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 10 10 4 4 0 0 1-5-5 4 4 0 0 1-5-5"></path></svg>`;
    }
    else if (lower.includes('hamburguesa') || lower.includes('torta') || lower.includes('sandwich')) {
      // Burger icon logic
      return `<svg ${props} viewBox="0 0 24 24"><rect x="4" y="15" width="16" height="4" rx="2"></rect><path d="M4 11h16a1 1 0 0 1 1 1v1a2 2 0 0 1-2 2h-12a2 2 0 0 1-2-2v-1a1 1 0 0 1 1-1Z"></path><path d="M6.023 7.5a4 4 0 0 1 7.954 0"></path></svg>`;
    }
    else if (lower.includes('pizza')) {
      // Pizza slice icon
      return `<svg ${props} viewBox="0 0 24 24"><path d="M15 11h.01"/><path d="M11 15h.01"/><path d="M16 16h.01"/><path d="M2 16h20"/><path d="M6 16v-4a10 10 0 0 1 20 0v4"/></svg>`; // Approximated
    }
    else if (lower.includes('taco')) {
      // Taco / Shell
      return `<svg ${props} viewBox="0 0 24 24"><path d="M2 12a10 10 0 0 1 20 0c0 5.5-4.5 10-10 10S2 17.5 2 12z"/><path d="M6 12h12"/></svg>`;
    }
    else if (lower.includes('desayuno') || lower.includes('huevo')) {
      // Sun / Egg icon
      return `<svg ${props} viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="M4.93 4.93l1.41 1.41"></path><path d="M17.66 17.66l1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="M6.34 17.66l-1.41 1.41"></path><path d="M19.07 4.93l-1.41 1.41"></path></svg>`;
    }

    // Default Utensils
    return `<svg ${props} viewBox="0 0 24 24"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"></path><path d="M7 2v20"></path><path d="M21 15V2v0a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"></path></svg>`;
  }

  private renderCategoryTabs(): void {
    if (!this.elements.categoryTabs) return;
    const fragment = document.createDocumentFragment();
    this.categories.forEach((category, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `category-tab ${index === 0 ? 'active' : ''}`;
      button.dataset.category = String(category.id);

      const icon = document.createElement('span');
      icon.className = 'category-tab__icon';
      icon.innerHTML = this.getCategoryIcon(category.name);

      const label = document.createElement('span');
      label.className = 'category-tab__label';
      label.textContent = category.name;

      button.appendChild(icon);
      button.appendChild(label);
      fragment.appendChild(button);
    });
    this.elements.categoryTabs.replaceChildren(fragment);
    this.elements.categoryTabs
      .querySelectorAll<HTMLButtonElement>('.category-tab')
      .forEach((button) => {
        button.addEventListener('click', () => {
          this.elements.categoryTabs?.querySelectorAll('.category-tab').forEach(b => b.classList.remove('active'));
          button.classList.add('active');
          const target = document.getElementById(`category-${button.dataset.category}`);
          if (target) {
            const headerOffset = 130; // Header + tabs height
            const elementPosition = target.getBoundingClientRect().top;
            const offsetPosition = elementPosition + window.pageYOffset - headerOffset;
            window.scrollTo({ top: offsetPosition, behavior: 'smooth' });
          }
        });
      });
  }

  private renderMenu(): void {
    if (!this.elements.menuSections) return;
    const categories = this.getSortedCategories();
    const menuHtml = categories
      .map((category) => {
        const categoryId = escapeHtml(String(category.id));
        const categoryName = escapeHtml(category.name);
        const categoryDescription = category.description
          ? `<p>${escapeHtml(category.description)}</p>`
          : '';
        const itemsHtml = category.items.map((item) => this.renderMenuCard(item)).join('');
        return `
          <section class="menu-section" id="category-${categoryId}">
            <header class="menu-section__header">
              <h2>${categoryName}</h2>
              ${categoryDescription}
            </header>
            <div class="menu-grid">
              ${itemsHtml}
            </div>
          </section>`;
      })
      .join('');

    this.elements.menuSections.replaceChildren(createFragment(menuHtml));

    // Event delegation for card clicks and quick add buttons
    if (this.menuEventsBound) return;
    this.menuEventsBound = true;
    this.elements.menuSections.addEventListener('click', (event) => {
      const target = event.target as HTMLElement;

      // Handle quick add button clicks
      const quickAddBtn = target.closest('[data-quick-add]') as HTMLElement;
      if (quickAddBtn) {
        event.preventDefault();
        event.stopPropagation();
        const itemId = Number(quickAddBtn.dataset.quickAdd);
        if (!Number.isNaN(itemId)) {
          this.quickAdd(event, itemId);
        }
        return;
      }

      // Handle card clicks (image or content area)
      const clickableArea = target.closest('[data-card-clickable]');
      if (clickableArea) {
        const card = clickableArea.closest('.menu-item-card') as HTMLElement;
        if (card) {
          const itemId = Number(card.dataset.itemId);
          if (!Number.isNaN(itemId)) {
            this.openItemModal(itemId);
          }
        }
      }
    });
  }

  public renderMenuCard(item: MenuItem): string {
    const baseUrl = window.APP_CONFIG?.static_host_url || '';
    const assets = window.APP_CONFIG?.restaurant_assets || '';
    const image = item.image_path
      ? `${baseUrl}${item.image_path}`
      : `${assets}/icons/placeholder.png`;
    const safeImage = escapeHtml(image);
    const itemId = escapeHtml(String(item.id));
    const itemName = escapeHtml(item.name);
    const itemDescription = escapeHtml(item.description || 'Sin descripción');
    const itemPrice = escapeHtml(this.formatPrice(item.price));

    // Preparation time indicator
    const prepTime = item.preparation_time_minutes
      ? `<span class="menu-item-card__prep-time">⏱️ ${item.preparation_time_minutes} min</span>`
      : '';

    return `
      <article class="menu-item-card" data-item-id="${itemId}">
        <div class="menu-item-card__image-wrapper" data-card-clickable>
          <img src="${safeImage}" alt="${itemName}" class="menu-item-card__image" loading="lazy" onerror="this.classList.add('img-error');this.parentElement.classList.add('menu-item-card__image--placeholder');">
          ${item.is_available
        ? `
          <button class="menu-item-card__quick-add" data-quick-add="${itemId}" title="Agregar">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
              <path d="M12 5v14M5 12h14" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
          `
        : '<div class="menu-item-card__status badge--sold-out">Agotado</div>'
      }
        </div>
        <div class="menu-item-card__info" data-card-clickable>
          <h3 class="menu-item-card__title">${itemName}</h3>
          <p class="menu-item-card__desc">${itemDescription}</p>
          <div class="menu-item-card__footer">
            <div class="menu-item-card__price-row">
              <span class="menu-item-card__price">${itemPrice}</span>
              ${prepTime}
            </div>
            ${item.is_quick_serve ? '<span class="menu-item-card__quick-badge">⚡</span>' : ''}
          </div>
        </div>
      </article>`;
  }

  private openItemModal(itemId: number): void {
    const item = this.findItemById(itemId);
    if (item) {
      this.modalManager.openModal(item, this.formatPrice.bind(this));
    }
  }

  private quickAdd(event: Event, itemId: number): void {
    event.preventDefault();
    event.stopPropagation();

    const item = this.findItemById(itemId);
    if (!item || !item.is_available) return;

    // If item has required modifiers, open modal instead
    if (item.modifier_groups && item.modifier_groups.length > 0) {
      const hasRequiredModifiers = item.modifier_groups.some(
        (group) => group.is_required || group.min_selection > 0
      );
      if (hasRequiredModifiers) {
        this.openItemModal(itemId);
        return;
      }
    }

    // Add item directly to cart without modifiers
    const baseUrl = window.APP_CONFIG?.static_host_url || '';
    const assets = window.APP_CONFIG?.restaurant_assets || '';
    const image = item.image_path
      ? `${baseUrl}${item.image_path}`
      : `${assets}/icons/placeholder.png`;

    cartStore.addItem({
      id: item.id,
      name: item.name,
      price: item.price,
      quantity: 1,
      image,
      extras: [],
      extrasTotal: 0,
      modifiers: [],
    });

    this.checkoutHandler.refreshCheckoutSummaryIfActive(
      cartStore.items,
      this.formatPrice.bind(this)
    );

    window.showNotification?.(`${item.name} agregado al carrito`, 'success');
  }

  private refreshSearchIndex(): void {
    this.searchIndex = [];
    this.categories.forEach((category) => {
      category.items.forEach((item) => {
        this.searchIndex.push({
          id: item.id,
          name: item.name,
          description: item.description || '',
          category: category.name,
          price: item.price,
        });
      });
    });
  }

  private setupSearch(): void {
    const input = this.elements.searchInput;
    const suggestions = this.elements.searchSuggestions;
    if (!input || !suggestions) return;

    let debounce: number | null = null;
    input.addEventListener('input', (event) => {
      const query = (event.target as HTMLInputElement).value.trim().toLowerCase();
      this.searchQuery = query;
      this.applyCatalogFilters();
      if (debounce) window.clearTimeout(debounce);
      if (query.length < 2) {
        suggestions.replaceChildren();
        suggestions.classList.remove('visible');
        suggestions.style.display = 'none'; // Force hide
        return;
      }
      suggestions.style.display = 'block'; // Enable display for results
      suggestions.replaceChildren(
        createFragment('<p class="smart-search__empty">Buscando...</p>')
      );
      suggestions.classList.add('visible');
      debounce = window.setTimeout(() => {
        this.renderSearchSuggestions(query);
      }, 200);
    });

    input.addEventListener('blur', () => {
      window.setTimeout(() => {
        suggestions.classList.remove('visible');
        suggestions.style.display = 'none';
      }, 150);
    });

    input.addEventListener('keydown', (event) => {
      if (!['ArrowDown', 'ArrowUp', 'Enter'].includes(event.key)) return;
      const options = suggestions.querySelectorAll<HTMLButtonElement>('[data-suggestion-id]');
      if (!options.length) return;

      const current = suggestions.querySelector<HTMLButtonElement>('.selected');
      let nextIndex = 0;
      if (current) {
        const currentIndex = Array.from(options).indexOf(current);
        if (event.key === 'ArrowDown') {
          nextIndex = Math.min(options.length - 1, currentIndex + 1);
        } else if (event.key === 'ArrowUp') {
          nextIndex = Math.max(0, currentIndex - 1);
        } else if (event.key === 'Enter') {
          event.preventDefault();
          current.click();
          return;
        }
      } else {
        nextIndex = event.key === 'ArrowUp' ? options.length - 1 : 0;
      }

      options.forEach((opt) => opt.classList.remove('selected'));
      const next = options[nextIndex];
      next.classList.add('selected');
      next.scrollIntoView({ block: 'nearest' });
    });
  }

  private renderSearchSuggestions(query: string): void {
    if (!this.elements.searchSuggestions) return;
    const matches = this.searchIndex
      .filter(
        (entry) =>
          entry.name.toLowerCase().includes(query) ||
          entry.description.toLowerCase().includes(query)
      )
      .slice(0, 6);
    if (!matches.length) {
      this.elements.searchSuggestions.replaceChildren(
        createFragment(
          '<p class="smart-search__empty smart-search__empty--strong">Sin coincidencias.</p>'
        )
      );
      return;
    }
    const fragment = document.createDocumentFragment();
    matches.forEach((match) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'smart-search__suggestion';
      button.dataset.suggestionId = String(match.id);

      const textWrap = document.createElement('div');
      textWrap.className = 'smart-search__suggestion-text';

      const name = document.createElement('span');
      name.className = 'smart-search__suggestion-name';
      name.textContent = match.name;

      const category = document.createElement('span');
      category.className = 'smart-search__suggestion-meta';
      category.textContent = match.category;

      textWrap.appendChild(name);
      textWrap.appendChild(category);

      const price = document.createElement('span');
      price.className = 'smart-search__suggestion-price';
      price.textContent = this.formatPrice(match.price);

      button.appendChild(textWrap);
      button.appendChild(price);
      fragment.appendChild(button);
    });
    this.elements.searchSuggestions.replaceChildren(fragment);
    this.elements.searchSuggestions
      .querySelectorAll<HTMLButtonElement>('[data-suggestion-id]')
      .forEach((button) => {
        button.addEventListener('click', () => {
          const id = Number(button.dataset.suggestionId);
          this.scrollToItem(id);
          this.elements.searchSuggestions?.classList.remove('visible');
        });
      });
  }

  private scrollToItem(itemId: number): void {
    const card = this.elements.menuSections?.querySelector<HTMLElement>(
      `.menu-item-card[data-item-id="${itemId}"]`
    );
    card?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    card?.classList.add('highlight');
    window.setTimeout(() => card?.classList.remove('highlight'), 1500);
  }

  private setupFilters(): void {
    this.elements.filterButtons.forEach((button) => {
      button.addEventListener('click', () => this.applyFilter(button.dataset.filter || 'all'));
    });
    this.elements.sortSelect?.addEventListener('change', () => {
      this.sortBy = this.elements.sortSelect?.value || 'recommended';
      this.persistFilterState();
      this.renderMenu();
      this.applyCatalogFilters();
    });
    const priceHandler = () => {
      const minValue = Number(this.elements.priceMinInput?.value);
      const maxValue = Number(this.elements.priceMaxInput?.value);
      this.priceMin = Number.isFinite(minValue) && minValue >= 0 ? minValue : null;
      this.priceMax = Number.isFinite(maxValue) && maxValue >= 0 ? maxValue : null;
      this.persistFilterState();
      this.applyCatalogFilters();
    };
    this.elements.priceMinInput?.addEventListener('input', priceHandler);
    this.elements.priceMaxInput?.addEventListener('input', priceHandler);
    this.elements.clearFiltersBtn?.addEventListener('click', () => this.resetFilters());
    (window as any).resetFilters = () => this.resetFilters();
  }

  private applyFilter(filter: string): void {
    this.activeFilter = filter || 'all';
    this.updateFilterButtons();
    this.persistFilterState();
    this.applyCatalogFilters();
  }

  private findItemById(itemId: number): MenuItem | null {
    for (const category of this.categories) {
      const match = category.items.find((item) => item.id === itemId);
      if (match) return match;
    }
    return null;
  }

  private getSortedCategories(): MenuCategory[] {
    return this.categories.map((category) => ({
      ...category,
      items: this.sortItems(category.items),
    }));
  }

  private sortItems(items: MenuItem[]): MenuItem[] {
    const sorted = [...items];
    switch (this.sortBy) {
      case 'price-asc':
        return sorted.sort((a, b) => a.price - b.price);
      case 'price-desc':
        return sorted.sort((a, b) => b.price - a.price);
      case 'name-asc':
        return sorted.sort((a, b) => a.name.localeCompare(b.name, 'es'));
      default:
        return sorted;
    }
  }

  private applyCatalogFilters(): void {
    if (!this.elements.menuSections) return;
    const query = this.searchQuery.trim().toLowerCase();
    const useQuery = query.length >= 2;
    let visibleCount = 0;

    this.elements.menuSections.querySelectorAll<HTMLElement>('.menu-item-card').forEach((card) => {
      const itemId = Number(card.dataset.itemId);
      const item = this.findItemById(itemId);
      if (!item) return;

      const matchesQuery =
        !useQuery ||
        item.name.toLowerCase().includes(query) ||
        (item.description || '').toLowerCase().includes(query) ||
        this.getCategoryName(item)?.toLowerCase().includes(query);
      const matchesPrice = this.matchesPrice(item.price);
      const matchesFilter = this.matchesFilter(item, this.activeFilter);
      const visible = matchesQuery && matchesPrice && matchesFilter;

      card.classList.toggle('hidden', !visible);
      if (visible) {
        visibleCount += 1;
      }
    });

    this.updateSectionVisibility();
    this.updateResultsCount(visibleCount);
    this.updateFilterCounts(useQuery ? query : '');
    if (this.elements.emptyState) {
      if (visibleCount === 0) {
        this.elements.emptyState.style.setProperty('display', 'block', 'important');
        this.elements.emptyState.classList.remove('hidden');
        this.elements.emptyState.removeAttribute('hidden');
      } else {
        this.elements.emptyState.style.setProperty('display', 'none', 'important');
        this.elements.emptyState.classList.add('hidden');
        this.elements.emptyState.setAttribute('hidden', '');
      }
    }
  }

  private updateSectionVisibility(): void {
    this.elements.menuSections
      ?.querySelectorAll<HTMLElement>('.menu-section')
      .forEach((section) => {
        const hasVisible = Array.from(section.querySelectorAll('.menu-item-card')).some(
          (card) => !card.classList.contains('hidden')
        );
        section.classList.toggle('hidden', !hasVisible);
      });
  }

  private updateResultsCount(count: number): void {
    if (!this.elements.resultsCount) return;
    const label = count === 1 ? 'producto' : 'productos';
    this.elements.resultsCount.textContent = `Mostrando ${count} ${label}`;
  }

  private updateFilterCounts(query: string): void {
    const filters = ['all', 'breakfast', 'afternoon', 'dinner', 'quick-serve', 'promotion'];
    const counts: Record<string, number> = {};
    filters.forEach((filter) => (counts[filter] = 0));

    this.categories.forEach((category) => {
      category.items.forEach((item) => {
        const matchesQuery =
          !query ||
          item.name.toLowerCase().includes(query) ||
          (item.description || '').toLowerCase().includes(query) ||
          category.name.toLowerCase().includes(query);
        if (!matchesQuery || !this.matchesPrice(item.price)) return;

        counts.all += 1;
        filters.forEach((filter) => {
          if (filter === 'all') return;
          if (this.matchesFilter(item, filter)) {
            counts[filter] += 1;
          }
        });
      });
    });

    this.elements.filterCounts.forEach((badge) => {
      const filter = badge.dataset.filterCount || 'all';
      badge.textContent = String(counts[filter] || 0);
    });
  }

  private matchesFilter(item: MenuItem, filter: string): boolean {
    if (filter === 'all') return true;
    if (filter === 'promotion') return Boolean(item.is_quick_serve);
    if (filter === 'quick-serve') return Boolean(item.is_quick_serve);
    if (filter === 'breakfast') return Boolean(item.is_breakfast_recommended);
    if (filter === 'afternoon') return Boolean(item.is_afternoon_recommended);
    if (filter === 'dinner') return Boolean(item.is_night_recommended);
    return true;
  }

  private matchesPrice(price: number): boolean {
    if (this.priceMin !== null && price < this.priceMin) return false;
    if (this.priceMax !== null && price > this.priceMax) return false;
    return true;
  }

  private getCategoryName(item: MenuItem): string | null {
    for (const category of this.categories) {
      if (category.items.some((entry) => entry.id === item.id)) {
        return category.name;
      }
    }
    return null;
  }

  private updateFilterButtons(): void {
    this.elements.filterButtons.forEach((button) => {
      button.setAttribute(
        'data-active',
        button.dataset.filter === this.activeFilter ? 'true' : 'false'
      );
    });
  }

  private resetFilters(): void {
    this.activeFilter = 'all';
    this.searchQuery = '';
    this.priceMin = null;
    this.priceMax = null;
    this.sortBy = 'recommended';
    if (this.elements.searchInput) this.elements.searchInput.value = '';
    if (this.elements.priceMinInput) this.elements.priceMinInput.value = '';
    if (this.elements.priceMaxInput) this.elements.priceMaxInput.value = '';
    if (this.elements.sortSelect) this.elements.sortSelect.value = 'recommended';
    this.updateFilterButtons();
    this.persistFilterState();
    this.renderMenu();
    this.applyCatalogFilters();
  }

  private persistFilterState(): void {
    const payload = {
      activeFilter: this.activeFilter,
      searchQuery: this.searchQuery,
      priceMin: this.priceMin,
      priceMax: this.priceMax,
      sortBy: this.sortBy,
    };
    sessionStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(payload));
  }

  private restoreFilterState(): void {
    const stored = sessionStorage.getItem(FILTER_STORAGE_KEY);
    if (!stored) return;
    try {
      const parsed = JSON.parse(stored) as {
        activeFilter?: string;
        searchQuery?: string;
        priceMin?: number | null;
        priceMax?: number | null;
        sortBy?: string;
      };
      this.activeFilter = parsed.activeFilter || 'all';
      this.searchQuery = parsed.searchQuery || '';
      this.priceMin = typeof parsed.priceMin === 'number' ? parsed.priceMin : null;
      this.priceMax = typeof parsed.priceMax === 'number' ? parsed.priceMax : null;
      this.sortBy = parsed.sortBy || 'recommended';
      if (this.elements.searchInput) this.elements.searchInput.value = this.searchQuery;
      if (this.elements.priceMinInput && this.priceMin !== null) {
        this.elements.priceMinInput.value = String(this.priceMin);
      }
      if (this.elements.priceMaxInput && this.priceMax !== null) {
        this.elements.priceMaxInput.value = String(this.priceMax);
      }
      if (this.elements.sortSelect) {
        this.elements.sortSelect.value = this.sortBy;
      }
      this.updateFilterButtons();
      this.renderMenu();
      this.applyCatalogFilters();
    } catch (error) {
      console.warn('[MenuFlow] Failed to restore filters', error);
    }
  }

  private formatPrice(value: number): string {
    const locale = window.APP_SETTINGS?.currency_locale || 'es-MX';
    const currency = window.APP_SETTINGS?.currency_code || window.APP_CONFIG.currency_code || 'MXN';
    try {
      return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(value || 0);
    } catch {
      const symbol =
        window.APP_SETTINGS?.currency_symbol || window.APP_CONFIG.currency_symbol || '$';
      return `${symbol}${(value || 0).toFixed(2)}`;
    }
  }
}

const createFragment = (html: string): DocumentFragment =>
  document.createRange().createContextualFragment(html);

const escapeHtml = (value: string): string => {
  const div = document.createElement('div');
  div.textContent = value;
  return div.innerHTML;
};
