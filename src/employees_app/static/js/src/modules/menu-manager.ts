interface RawProduct {
    id: number;
    name: string;
    description?: string | null;
    price?: number;
    image_path?: string | null;
    is_available?: boolean;
    has_active_promotion?: boolean;
    has_active_coupon?: boolean;
    recommendation_periods?: string[];
    is_breakfast_recommended?: boolean;
    is_afternoon_recommended?: boolean;
    is_night_recommended?: boolean;
    tags?: string[];
    is_quick_serve?: boolean;
}

interface Category {
    name: string;
    items?: RawProduct[];
}

interface ProductWithCategory extends RawProduct {
    categoryName: string;
}

interface MenuState {
    categories: Category[];
    filterCategory: string;
    availability: 'all' | 'available' | 'unavailable';
    search: string;
    filterPromotion: boolean;
    filterCoupon: boolean;
    filterPeriods: string[];
    currentPage: number;
    itemsPerPage: number;
    viewMode: 'grid' | 'compact';
}

const ITEMS_PER_PAGE_OPTIONS = [10, 20, 50, 100];
const STORAGE_KEY_PRODUCTS = 'pronto_items_per_page_products';
const STORAGE_KEY_VIEW_MODE = 'pronto_catalog_view_mode';

function getSavedItemsPerPage(): number {
    try {
        const saved = localStorage.getItem(STORAGE_KEY_PRODUCTS);
        if (saved) {
            const value = parseInt(saved, 10);
            if (ITEMS_PER_PAGE_OPTIONS.includes(value)) {
                return value;
            }
        }
    } catch (e) { /* ignore */ }
    return Number(window.APP_CONFIG?.items_per_page) || 20;
}

function saveItemsPerPage(value: number): void {
    try {
        localStorage.setItem(STORAGE_KEY_PRODUCTS, String(value));
        localStorage.setItem('pronto_items_per_page', String(value)); // Also save global
    } catch (e) { /* ignore */ }
}

function getSavedViewMode(): 'grid' | 'compact' {
    try {
        const saved = localStorage.getItem(STORAGE_KEY_VIEW_MODE);
        if (saved === 'compact' || saved === 'grid') {
            return saved;
        }
    } catch (e) { /* ignore */ }
    return 'grid';
}

function saveViewMode(mode: 'grid' | 'compact'): void {
    try {
        localStorage.setItem(STORAGE_KEY_VIEW_MODE, mode);
    } catch (e) { /* ignore */ }
}

const DEFAULT_ITEMS_PER_PAGE = getSavedItemsPerPage();
const RESTAURANT_ASSETS = window.APP_CONFIG?.restaurant_assets || '';
const STATIC_BASE = window.APP_CONFIG?.static_host_url || '';
const PRODUCT_PLACEHOLDER = RESTAURANT_ASSETS
    ? `${RESTAURANT_ASSETS}/icons/placeholder.png`
    : '/static/img/placeholder.png';

const currencySymbol = window.APP_SETTINGS?.currency_symbol || '$';

function resolveImage(path?: string | null): string {
    if (!path) return PRODUCT_PLACEHOLDER;
    if (path.startsWith('http')) return path;
    return `${STATIC_BASE}${path}`;
}

function formatPrice(value?: number): string {
    const amount = Number(value) || 0;
    return `${currencySymbol}${amount.toFixed(2)}`;
}

export function initMenuManager(): void {
    document.addEventListener('DOMContentLoaded', () => {
        const root = document.querySelector<HTMLElement>('[data-catalog-root]');
        if (!root) return;
        new MenuManager(root).initialize();
    });
}

class MenuManager {
    private root: HTMLElement;
    private state: MenuState;
    private grid: HTMLElement | null;
    private pagination: HTMLElement | null;
    private emptyState: HTMLElement | null;
    private filterList: HTMLElement | null;
    private searchInput: HTMLInputElement | null;
    private suggestions: HTMLElement | null;
    private promotionCheckbox: HTMLInputElement | null;
    private couponCheckbox: HTMLInputElement | null;
    private periodCheckboxes: NodeListOf<HTMLInputElement>;
    private availabilityFilter: HTMLElement | null;
    private statsTotal: HTMLElement | null;
    private statsAvailable: HTMLElement | null;
    private countLabel: HTMLElement | null;
    private datalist: HTMLDataListElement | null;
    private allowProductEdits: boolean;
    private drawer: HTMLElement | null = null;
    private drawerContent: HTMLElement | null = null;
    private drawerTitle: HTMLElement | null = null;
    private drawerCloseBtn: HTMLButtonElement | null = null;
    private drawerCancelBtn: HTMLButtonElement | null = null;
    private drawerDeleteBtn: HTMLButtonElement | null = null;
    private productForm: HTMLFormElement | null = null;
    private productIdInput: HTMLInputElement | null = null;
    private productNameInput: HTMLInputElement | null = null;
    private productPriceInput: HTMLInputElement | null = null;
    private productCategoryInput: HTMLInputElement | null = null;
    private productPrepTimeInput: HTMLInputElement | null = null;
    private productDescriptionInput: HTMLTextAreaElement | null = null;
    private productAvailabilityInput: HTMLInputElement | null = null;
    private productQuickServeInput: HTMLInputElement | null = null;
    private productImageInput: HTMLInputElement | null = null;
    private productImagePreview: HTMLImageElement | null = null;
    private productPeriodToggles: NodeListOf<HTMLInputElement> | null = null;
    private drawerMode: 'create' | 'edit' = 'create';
    private escapeHandler: ((e: KeyboardEvent) => void) | null = null;
    private suggestionHideTimeout: number | null = null;
    private selectedProductId: number | null = null;
    private quickEditBtn: HTMLButtonElement | null = null;
    private quickToggleBtn: HTMLButtonElement | null = null;
    private quickDeleteBtn: HTMLButtonElement | null = null;

    constructor(root: HTMLElement) {
        this.root = root;
        const categories = (window.APP_DATA?.categories as Category[]) || [];
        this.state = {
            categories,
            filterCategory: 'all',
            availability: 'all',
            search: '',
            filterPromotion: false,
            filterCoupon: false,
            filterPeriods: [],
            currentPage: 1,
            itemsPerPage: DEFAULT_ITEMS_PER_PAGE,
            viewMode: getSavedViewMode()
        };
        this.grid = root.querySelector('#product-grid');
        this.pagination = root.querySelector('#product-pagination');
        this.emptyState = root.querySelector('#product-empty-state');
        this.filterList = root.querySelector('#product-filter-list');
        this.searchInput = root.querySelector('#product-search');
        this.suggestions = root.querySelector('#product-search-suggestions');
        this.promotionCheckbox = root.querySelector('#filter-promotion');
        this.couponCheckbox = root.querySelector('#filter-coupon');
        this.periodCheckboxes = root.querySelectorAll<HTMLInputElement>('.period-filter-checkbox');
        this.availabilityFilter = root.querySelector('#availability-filter');
        this.statsTotal = root.querySelector('#product-total-count');
        this.statsAvailable = root.querySelector('#product-available-count');
        this.countLabel = root.querySelector('#product-count-label');
        this.datalist = document.getElementById('category-options') as HTMLDataListElement | null;

        // Check if user has permission to edit products (not just if form exists)
        const employeeRole = window.APP_DATA?.employee_role || '';
        const canEditProducts = ['super_admin', 'admin_roles', 'content_manager', 'chef'].includes(employeeRole);
        this.allowProductEdits = canEditProducts && Boolean(document.getElementById('product-form'));
        this.quickEditBtn = document.getElementById('edit-product-btn') as HTMLButtonElement | null;
        this.quickToggleBtn = document.getElementById('mark-available-btn') as HTMLButtonElement | null;
        this.quickDeleteBtn = document.getElementById('delete-product-btn') as HTMLButtonElement | null;
    }

    initialize(): void {
        this.renderFilters();
        this.renderGrid();
        this.updateViewButtons();
        this.attachEvents();
        this.initProductDrawer();
        this.syncQuickPeriodButtons();
        this.updateQuickActions();
        window.goToProductPage = (page: number) => {
            this.goToPage(page);
        };
    }

    private attachEvents(): void {
        this.filterList?.addEventListener('click', (event) => {
            const button = (event.target as HTMLElement).closest<HTMLButtonElement>('button[data-category]');
            if (!button) return;
            this.state.filterCategory = button.dataset.category || 'all';
            this.state.currentPage = 1;
            this.renderFilters();
            this.renderGrid();
        });

        this.availabilityFilter?.addEventListener('click', (event) => {
            const button = (event.target as HTMLElement).closest<HTMLButtonElement>('button[data-availability]');
            if (!button) return;
            this.state.availability = (button.dataset.availability as MenuState['availability']) || 'all';
            this.state.currentPage = 1;
            this.availabilityFilter
                ?.querySelectorAll('.segment-btn, .segment-btn-modern')
                .forEach((btn) => btn.classList.toggle('active', btn === button));
            this.renderGrid();
        });

        this.promotionCheckbox?.addEventListener('change', () => {
            this.state.filterPromotion = !!this.promotionCheckbox?.checked;
            this.state.currentPage = 1;
            this.renderGrid();
        });

        this.couponCheckbox?.addEventListener('change', () => {
            this.state.filterCoupon = !!this.couponCheckbox?.checked;
            this.state.currentPage = 1;
            this.renderGrid();
        });

        this.periodCheckboxes.forEach((checkbox) => {
            checkbox.addEventListener('change', () => {
                const key = checkbox.dataset.periodKey;
                if (!key) return;
                if (checkbox.checked) {
                    if (!this.state.filterPeriods.includes(key)) {
                        this.state.filterPeriods.push(key);
                    }
                } else {
                    this.state.filterPeriods = this.state.filterPeriods.filter((period) => period !== key);
                }
                this.state.currentPage = 1;
                this.renderGrid();
                this.syncQuickPeriodButtons();
            });
        });

        this.root.querySelectorAll<HTMLButtonElement>('[data-quick-period]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const key = btn.dataset.quickPeriod;
                if (!key) return;

                const enabled = this.state.filterPeriods.includes(key);
                this.state.filterPeriods = enabled ? [] : [key];

                this.periodCheckboxes.forEach((checkbox) => {
                    checkbox.checked = checkbox.dataset.periodKey === key ? !enabled : false;
                });

                this.state.currentPage = 1;
                this.renderGrid();
                this.syncQuickPeriodButtons();
            });
        });

        this.searchInput?.addEventListener('input', () => {
            this.state.search = this.searchInput?.value.trim().toLowerCase() || '';
            this.state.currentPage = 1;
            this.renderGrid();
            this.updateSuggestions(this.searchInput?.value || '');
        });

        this.searchInput?.addEventListener('focus', () => {
            this.updateSuggestions(this.searchInput?.value || '');
        });

        this.searchInput?.addEventListener('blur', () => {
            this.suggestionHideTimeout = window.setTimeout(() => {
                this.suggestions?.classList.remove('active');
            }, 180);
        });

        this.suggestions?.addEventListener('mousedown', (event) => {
            const button = (event.target as HTMLElement).closest<HTMLButtonElement>('button[data-suggested]');
            if (!button) return;
            event.preventDefault();
            if (this.suggestionHideTimeout) {
                clearTimeout(this.suggestionHideTimeout);
            }
            const label = button.dataset.label || '';
            if (this.searchInput) {
                this.searchInput.value = label;
                this.searchInput.focus();
            }
            this.state.search = label.toLowerCase();
            this.suggestions?.classList.remove('active');
            this.renderGrid();
        });

        // New product creation
        if (this.allowProductEdits) {
            const newProductBtn = document.getElementById('new-product-btn');
            newProductBtn?.addEventListener('click', () => {
                this.openProductDrawer('create');
            });

            this.quickEditBtn?.addEventListener('click', () => {
                if (!this.selectedProductId) return;
                this.handleEdit(this.selectedProductId);
            });

            this.quickToggleBtn?.addEventListener('click', () => {
                if (!this.selectedProductId) return;
                const product = this.flattenProducts().find((item) => item.id === this.selectedProductId);
                if (!product) return;
                void this.handleToggle(this.selectedProductId, Boolean(product.is_available));
                this.updateQuickActions();
            });

            this.quickDeleteBtn?.addEventListener('click', () => {
                if (!this.selectedProductId) return;
                void this.handleDelete(this.selectedProductId);
            });
        }

        document.querySelectorAll<HTMLButtonElement>('[data-product-view-mode]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const mode = btn.dataset.productViewMode === 'compact' ? 'compact' : 'grid';
                this.state.viewMode = mode;
                saveViewMode(mode);
                this.updateViewButtons();
                this.renderGrid();
            });
        });

        const toggleSidebarBtn = document.getElementById('toggle-product-sidebar');
        toggleSidebarBtn?.addEventListener('click', () => {
            const catalogRoot = document.querySelector<HTMLElement>('#menu[data-catalog-root]');
            if (!catalogRoot) return;
            catalogRoot.classList.toggle('catalog-sidebar-collapsed');
            toggleSidebarBtn.classList.toggle('active', catalogRoot.classList.contains('catalog-sidebar-collapsed'));
        });

        this.grid?.addEventListener('click', (event) => {
            const button = (event.target as HTMLElement).closest<HTMLButtonElement>('[data-action]');
            if (!button) return;
            const productId = Number(button.dataset.id);
            if (Number.isNaN(productId)) return;
            if (button.dataset.action === 'edit') {
                this.handleEdit(productId);
            } else if (button.dataset.action === 'toggle') {
                const isAvailable = button.dataset.available === 'true';
                this.handleToggle(productId, isAvailable);
            }
        });

        this.grid?.addEventListener('click', (event) => {
            if (!this.allowProductEdits) return;
            const target = event.target as HTMLElement;
            if (target.closest('[data-action]')) return;
            const card = target.closest<HTMLElement>('.product-card, .product-row');
            if (!card) return;
            const productId = Number(card.dataset.itemId);
            if (Number.isNaN(productId)) return;
            this.setSelectedProduct(productId);
        });
    }

    private syncQuickPeriodButtons(): void {
        const active = new Set(this.state.filterPeriods || []);
        this.root.querySelectorAll<HTMLButtonElement>('[data-quick-period]').forEach((btn) => {
            const key = btn.dataset.quickPeriod || '';
            btn.classList.toggle('active', Boolean(key) && active.has(key));
        });
    }

    private async handleEdit(productId: number): Promise<void> {
        const product = this.flattenProducts().find((item) => item.id === productId);
        if (!product) return;

        if (!this.allowProductEdits) return;
        this.openProductDrawer('edit', product);
    }

    private initProductDrawer(): void {
        if (!this.allowProductEdits) return;
        this.drawer = document.getElementById('product-drawer');
        if (!this.drawer) return;

        this.drawerContent = this.drawer.querySelector<HTMLElement>('.product-drawer__content');
        this.drawerTitle = document.getElementById('product-drawer-title');
        this.drawerCloseBtn = document.getElementById('close-product-drawer') as HTMLButtonElement | null;
        this.drawerCancelBtn = document.getElementById('cancel-product-btn') as HTMLButtonElement | null;
        this.drawerDeleteBtn = document.getElementById('delete-product-drawer-btn') as HTMLButtonElement | null;
        this.productForm = document.getElementById('product-form') as HTMLFormElement | null;

        this.productIdInput = document.getElementById('product-id') as HTMLInputElement | null;
        this.productNameInput = document.getElementById('product-name') as HTMLInputElement | null;
        this.productPriceInput = document.getElementById('product-price') as HTMLInputElement | null;
        this.productCategoryInput = document.getElementById('product-category') as HTMLInputElement | null;
        this.productPrepTimeInput = document.getElementById('product-prep-time') as HTMLInputElement | null;
        this.productDescriptionInput = document.getElementById('product-description') as HTMLTextAreaElement | null;
        this.productAvailabilityInput = document.getElementById('product-availability') as HTMLInputElement | null;
        this.productQuickServeInput = document.getElementById('product-quick-serve') as HTMLInputElement | null;
        this.productImageInput = document.getElementById('product-image') as HTMLInputElement | null;
        this.productImagePreview = document.getElementById('product-image-preview') as HTMLImageElement | null;
        this.productPeriodToggles = document.querySelectorAll<HTMLInputElement>('.product-period-toggle');

        // Tabs
        document.querySelectorAll<HTMLButtonElement>('.product-tab').forEach((btn) => {
            btn.addEventListener('click', () => {
                const tabKey = btn.dataset.tab;
                if (!tabKey) return;
                this.setProductDrawerTab(tabKey);
            });
        });

        // Close behaviors
        const close = () => this.closeProductDrawer();
        this.drawerCloseBtn?.addEventListener('click', close);
        this.drawerCancelBtn?.addEventListener('click', close);
        this.drawerDeleteBtn?.addEventListener('click', () => {
            const idValue = this.productIdInput?.value ? Number(this.productIdInput.value) : null;
            if (!idValue) return;
            void this.handleDelete(idValue, true);
        });
        this.drawer.addEventListener('mousedown', (event) => {
            // Click on overlay closes drawer
            if (!this.drawerContent) return;
            if (event.target === this.drawer) {
                this.closeProductDrawer();
            }
        });

        // Submit
        this.productForm?.addEventListener('submit', (event) => {
            event.preventDefault();
            void this.saveProductFromDrawer();
        });
    }

    private openProductDrawer(mode: 'create' | 'edit', product?: ProductWithCategory): void {
        if (!this.allowProductEdits) {
            this.showToast('No tienes permisos para editar productos', 'warning');
            return;
        }
        if (!this.drawer) {
            this.showToast('No se encontró el formulario de producto', 'warning');
            return;
        }

        this.drawerMode = mode;
        if (this.drawerTitle) {
            this.drawerTitle.textContent = mode === 'create' ? 'Nuevo producto' : 'Editar producto';
        }
        if (this.drawerDeleteBtn) {
            this.drawerDeleteBtn.style.display = mode === 'edit' ? 'inline-flex' : 'none';
        }

        // Reset form (keep defaultChecked for period toggles on create)
        this.productForm?.reset();
        if (mode === 'create') {
            if (this.productIdInput) this.productIdInput.value = '';
            if (this.productPeriodToggles) {
                this.productPeriodToggles.forEach((toggle) => {
                    toggle.checked = toggle.defaultChecked;
                });
            }
            if (this.productImageInput) this.productImageInput.value = '';
            if (this.productImagePreview) {
                this.productImagePreview.src = PRODUCT_PLACEHOLDER;
                this.productImagePreview.dataset.state = 'empty';
            }
        } else if (product) {
            if (this.productIdInput) this.productIdInput.value = String(product.id);
            if (this.productNameInput) this.productNameInput.value = product.name || '';
            if (this.productPriceInput) this.productPriceInput.value = String(product.price ?? '');
            if (this.productCategoryInput) this.productCategoryInput.value = product.categoryName || '';
            if (this.productPrepTimeInput) {
                this.productPrepTimeInput.value = product.preparation_time_minutes ? String(product.preparation_time_minutes) : '';
            }
            if (this.productDescriptionInput) this.productDescriptionInput.value = product.description || '';
            if (this.productAvailabilityInput) this.productAvailabilityInput.checked = Boolean(product.is_available);
            if (this.productQuickServeInput) this.productQuickServeInput.checked = Boolean(product.is_quick_serve);

            if (this.productImageInput) this.productImageInput.value = product.image_path || '';
            if (this.productImagePreview) {
                this.productImagePreview.src = resolveImage(product.image_path);
                this.productImagePreview.dataset.state = product.image_path ? 'filled' : 'empty';
            }

            const periods = Array.isArray(product.recommendation_periods) ? product.recommendation_periods : [];
            if (this.productPeriodToggles) {
                this.productPeriodToggles.forEach((toggle) => {
                    const key = toggle.dataset.periodKey || '';
                    toggle.checked = key ? periods.includes(key) : false;
                });
            }
            this.setSelectedProduct(product.id);
        }

        this.setProductDrawerTab('info');
        this.drawer.classList.add('active');

        // ESC to close
        if (!this.escapeHandler) {
            this.escapeHandler = (e: KeyboardEvent) => {
                if (e.key === 'Escape') {
                    this.closeProductDrawer();
                }
            };
        }
        window.addEventListener('keydown', this.escapeHandler);
    }

    private closeProductDrawer(): void {
        if (!this.drawer) return;
        this.drawer.classList.remove('active');
        if (this.escapeHandler) {
            window.removeEventListener('keydown', this.escapeHandler);
        }
    }

    private setProductDrawerTab(tabKey: string): void {
        document.querySelectorAll<HTMLButtonElement>('.product-tab').forEach((btn) => {
            btn.classList.toggle('active', btn.dataset.tab === tabKey);
        });
        document.querySelectorAll<HTMLElement>('.product-tab-content').forEach((content) => {
            content.classList.toggle('active', content.dataset.tabContent === tabKey);
        });
    }

    private async saveProductFromDrawer(): Promise<void> {
        if (!this.productNameInput || !this.productPriceInput || !this.productCategoryInput) {
            this.showToast('Formulario incompleto', 'warning');
            return;
        }
        const name = this.productNameInput.value.trim();
        const category = this.productCategoryInput.value.trim();
        const priceRaw = this.productPriceInput.value;
        const price = Number(priceRaw);
        if (!name || !category || Number.isNaN(price)) {
            this.showToast('Nombre, precio y categoría son obligatorios', 'warning');
            return;
        }

        const payload: Record<string, any> = {
            name,
            price,
            category,
            description: this.productDescriptionInput?.value?.trim() || null,
            is_available: this.productAvailabilityInput ? Boolean(this.productAvailabilityInput.checked) : true,
            is_quick_serve: this.productQuickServeInput ? Boolean(this.productQuickServeInput.checked) : false,
        };

        const imagePath = this.productImageInput?.value?.trim();
        if (imagePath !== undefined) {
            payload.image_path = imagePath || null;
        }

        if (this.productPeriodToggles) {
            const selected: string[] = [];
            this.productPeriodToggles.forEach((toggle) => {
                const key = toggle.dataset.periodKey;
                if (toggle.checked && key) selected.push(key);
            });
            payload.recommendation_periods = selected;
        }

        // Optional prep time if present
        const prep = this.productPrepTimeInput?.value?.trim();
        if (prep) {
            const prepTime = Number(prep);
            if (!Number.isNaN(prepTime)) payload.preparation_time_minutes = prepTime;
        }

        const isEdit = this.drawerMode === 'edit';
        const idValue = this.productIdInput?.value ? Number(this.productIdInput.value) : null;
        const url = isEdit && idValue ? `/api/menu-items/${idValue}` : '/api/menu-items';
        const method = isEdit ? 'PUT' : 'POST';

        try {
            this.showToast(isEdit ? 'Guardando cambios...' : 'Creando producto...', 'info');
            const response = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(data.error || data.message || 'No se pudo guardar el producto');
            }

            this.showToast(isEdit ? 'Producto actualizado' : 'Producto creado', 'success');
            this.closeProductDrawer();
            await this.refreshMenuData();
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Error al guardar';
            this.showToast(message, 'warning');
        }
    }

    private async refreshMenuData(): Promise<void> {
        try {
            const response = await fetch('/api/menu');
            const data = await response.json().catch(() => ({}));
            const categories = data?.categories;
            if (Array.isArray(categories)) {
                this.state.categories = categories as Category[];
                if (window.APP_DATA) {
                    (window.APP_DATA as any).categories = this.state.categories;
                }
                this.renderFilters();
                this.renderGrid();
            }
        } catch (e) {
            // If refresh fails, keep existing UI but warn.
            this.showToast('Guardado, pero no se pudo refrescar el catálogo', 'warning');
        }
    }

    private async handleToggle(productId: number, isAvailable: boolean): Promise<void> {
        const newAvailability = !isAvailable;
        const chipClass = newAvailability ? 'chip--success' : 'chip--danger';
        const chipLabel = newAvailability ? 'Disponible' : 'Agotado';
        const buttonClass = newAvailability ? 'btn--product-disable' : 'btn--product-enable';
        const buttonLabel = newAvailability ? '🚫 Marcar agotado' : '✅ Reactivar';

        // Optimistically update UI
        const productCard = document.querySelector(`.product-card[data-item-id="${productId}"]`);
        const availabilityChip = productCard?.querySelector<HTMLElement>('.product-chip[data-action="toggle"]');
        const toggleButton = productCard?.querySelector<HTMLButtonElement>('button[data-action="toggle"]');

        // Save previous state for rollback
        const previousChipClass = availabilityChip?.className;
        const previousChipText = availabilityChip?.textContent;
        const previousButtonClass = toggleButton?.className;
        const previousButtonHTML = toggleButton?.innerHTML;

        // Update UI immediately
        if (availabilityChip) {
            availabilityChip.className = `product-chip ${chipClass}`;
            availabilityChip.textContent = chipLabel;
            availabilityChip.dataset.available = String(newAvailability);
        }

        if (toggleButton) {
            toggleButton.className = `btn ${buttonClass} btn--small`;
            toggleButton.innerHTML = buttonLabel;
            toggleButton.dataset.available = String(newAvailability);
            toggleButton.disabled = true;
        }

        // Update local state
        let productUpdated = false;
        for (const category of this.state.categories || []) {
            const productIndex = (category.items || []).findIndex((item) => item.id === productId);
            if (productIndex !== -1 && category.items) {
                category.items[productIndex].is_available = newAvailability;
                productUpdated = true;
                break;
            }
        }

        const newStatus = newAvailability ? 'disponible' : 'agotado';
        this.showToast(`Actualizando... ${newStatus}`, 'info');

        // Sync with server
        try {
            const response = await fetch(`/api/menu-items/${productId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_available: newAvailability })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'No se pudo actualizar la disponibilidad');
            }

            this.showToast(`Producto marcado como ${newStatus}`, 'success');
            this.updateQuickActions();
        } catch (error) {
            // Rollback on error
            console.error('Error al actualizar disponibilidad:', error);

            if (availabilityChip && previousChipClass && previousChipText) {
                availabilityChip.className = previousChipClass;
                availabilityChip.textContent = previousChipText;
                availabilityChip.dataset.available = String(isAvailable);
            }

            if (toggleButton && previousButtonClass && previousButtonHTML) {
                toggleButton.className = previousButtonClass;
                toggleButton.innerHTML = previousButtonHTML;
                toggleButton.dataset.available = String(isAvailable);
            }

            // Revert local state
            if (productUpdated) {
                for (const category of this.state.categories || []) {
                    const productIndex = (category.items || []).findIndex((item) => item.id === productId);
                    if (productIndex !== -1 && category.items) {
                        category.items[productIndex].is_available = isAvailable;
                        break;
                    }
                }
            }

            const errorMessage = error instanceof Error ? error.message : 'Error desconocido';
            this.showToast(`Error: ${errorMessage}`, 'warning');
        } finally {
            if (toggleButton) {
                toggleButton.disabled = false;
            }
        }
    }

    private async handleDelete(productId: number, fromDrawer = false): Promise<void> {
        const product = this.flattenProducts().find((item) => item.id === productId);
        if (!product) return;
        const confirmDelete = window.confirm(`¿Eliminar "${product.name}"? Esta acción no se puede deshacer.`);
        if (!confirmDelete) return;

        try {
            this.showToast('Eliminando producto...', 'info');
            const response = await fetch(`/api/menu-items/${productId}`, { method: 'DELETE' });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(data.error || data.message || 'No se pudo eliminar el producto');
            }

            this.state.categories = this.state.categories
                .map((category) => ({
                    ...category,
                    items: (category.items || []).filter((item) => item.id !== productId),
                }))
                .filter((category) => (category.items || []).length > 0);

            if (window.APP_DATA) {
                (window.APP_DATA as any).categories = this.state.categories;
            }

            this.selectedProductId = null;
            this.updateQuickActions();
            this.renderFilters();
            this.renderGrid();
            if (fromDrawer) {
                this.closeProductDrawer();
            }
            this.showToast('Producto eliminado', 'success');
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Error al eliminar';
            this.showToast(message, 'warning');
        }
    }

    private showToast(message: string, type: 'success' | 'warning' | 'info'): void {
        // Use global toast if available
        if (typeof (window as any).showToast === 'function') {
            (window as any).showToast(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }

    private goToPage(page: number): void {
        const totalPages = Math.ceil(this.flattenProducts().length / this.state.itemsPerPage);
        if (page < 1 || page > totalPages) return;
        this.state.currentPage = page;
        this.renderGrid();
        this.grid?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    private flattenProducts(): ProductWithCategory[] {
        const items: ProductWithCategory[] = [];
        (this.state.categories || []).forEach((category) => {
            (category.items || []).forEach((item) => {
                items.push({ ...item, categoryName: category.name });
            });
        });
        return items;
    }

    private filterProducts(list: ProductWithCategory[]): ProductWithCategory[] {
        return list.filter((product) => {
            if (this.state.filterCategory !== 'all' && product.categoryName !== this.state.filterCategory) {
                return false;
            }
            if (this.state.availability === 'available' && !product.is_available) {
                return false;
            }
            if (this.state.availability === 'unavailable' && product.is_available) {
                return false;
            }
            if (this.state.search) {
                const haystack = `${product.name} ${(product.description || '')}`.toLowerCase();
                if (!haystack.includes(this.state.search)) {
                    return false;
                }
            }
            if (this.state.filterPromotion && !product.has_active_promotion) {
                return false;
            }
            if (this.state.filterCoupon && !product.has_active_coupon) {
                return false;
            }
            if (this.state.filterPeriods.length > 0) {
                const periods = new Set(product.recommendation_periods || []);
                if (product.is_breakfast_recommended) periods.add('breakfast');
                if (product.is_afternoon_recommended) periods.add('afternoon');
                if (product.is_night_recommended) periods.add('night');
                const hasMatch = this.state.filterPeriods.some((period) => periods.has(period));
                if (!hasMatch) return false;
            }
            return true;
        });
    }

    private renderFilters(): void {
        const categories = Array.from(new Set((this.state.categories || []).map((cat) => cat.name)));
        if (this.filterList) {
            const buttons = [
                `<button type="button" data-category="all" class="${this.state.filterCategory === 'all' ? 'active' : ''}">Todos</button>`
            ].concat(
                categories.map((name) =>
                    `<button type="button" data-category="${name}" class="${this.state.filterCategory === name ? 'active' : ''}">${name}</button>`
                )
            );
            this.filterList.innerHTML = buttons.join('');
        }
        if (this.datalist) {
            this.datalist.innerHTML = categories.map((name) => `<option value="${name}">`).join('');
        }
        if (this.countLabel) {
            this.countLabel.textContent = `${(this.state.categories || []).length} categorías`;
        }
    }

    private renderGrid(): void {
        if (!this.grid) return;
        const allProducts = this.filterProducts(this.flattenProducts());
        this.renderStats(allProducts);
        if (allProducts.length === 0) {
            this.grid.innerHTML = '';
            if (this.emptyState) this.emptyState.style.display = 'block';
            this.renderPagination(0, 0);
            return;
        }
        if (this.emptyState) this.emptyState.style.display = 'none';
        const totalPages = Math.ceil(allProducts.length / this.state.itemsPerPage);
        const startIndex = (this.state.currentPage - 1) * this.state.itemsPerPage;
        const products = allProducts.slice(startIndex, startIndex + this.state.itemsPerPage);
        const allowAvailabilityToggle = true;
        const isCompact = this.state.viewMode === 'compact';

        const renderActions = (product: ProductWithCategory): string => {
            if (!this.allowProductEdits) {
                return '';
            }
            return `<div class="product-card__actions">
                        <button type="button" class="btn btn--product-edit btn--small" data-action="edit" data-id="${product.id}">✏️ Editar</button>
                    </div>`;
        };

        const cards = products
            .map((product) => {
                const availabilityChip = product.is_available ? 'chip--success' : 'chip--danger';
                const availabilityLabel = product.is_available ? 'Disponible' : 'Agotado';
                const actions = renderActions(product);
                const isUnavailable = !product.is_available;
                if (isCompact) {
                    return `
                        <article class="product-row ${isUnavailable ? 'product-row--unavailable' : ''}" data-item-id="${product.id}" data-category="${product.categoryName}">
                            <div class="product-row__media">
                                <img src="${resolveImage(product.image_path)}" alt="${product.name}">
                            </div>
                            <div class="product-row__content">
                                <div class="product-row__header">
                                    <div>
                                        <div class="product-row__title">${product.name}</div>
                                        <div class="product-row__meta">${product.categoryName}</div>
                                    </div>
                                    <div class="product-row__price">${formatPrice(product.price)}</div>
                                </div>
                                <p class="product-row__description">${product.description || 'Sin descripción'}</p>
                                <div class="product-row__tags">
                                    <span class="product-chip ${availabilityChip}" data-action="toggle" data-id="${product.id}" data-available="${product.is_available}" title="Clic para cambiar disponibilidad">${availabilityLabel}</span>
                                    ${product.is_quick_serve ? '<span class="product-note product-note--quick">Entrega inmediata</span>' : ''}
                                    <span class="product-note product-note--id">ID #${product.id}</span>
                                </div>
                            </div>
                            <div class="product-row__actions">
                                ${actions}
                            </div>
                        </article>
                    `;
                }

                return `
                    <article class="product-card ${isUnavailable ? 'product-card--unavailable' : ''}" data-item-id="${product.id}" data-category="${product.categoryName}">
                        <div class="product-card__media">
                            <img src="${resolveImage(product.image_path)}" alt="${product.name}">
                            ${allowAvailabilityToggle
                        ? `<span class="product-chip ${availabilityChip}" data-action="toggle" data-id="${product.id}" data-available="${product.is_available}" title="Clic para cambiar disponibilidad">${availabilityLabel}</span>`
                        : `<span class="product-chip ${availabilityChip}">${availabilityLabel}</span>`}
                        </div>
                        <div class="product-card__body">
                            <div class="product-card__header">
                                <div>
                                    <h4>${product.name}</h4>
                                    <p class="product-card__category">${product.categoryName}</p>
                                </div>
                                <div class="product-card__price product-card__price--prominent">${formatPrice(product.price)}</div>
                            </div>
                            <p class="product-card__description">${product.description || 'Sin descripción'}</p>
                            <div class="product-card__meta">
                                ${product.is_quick_serve ? '<span class="product-note product-note--quick">Entrega inmediata</span>' : ''}
                                <span class="product-note product-note--id">ID #${product.id}</span>
                            </div>
                        </div>
                        <div class="product-card__footer">
                            ${actions}
                        </div>
                    </article>
                `;
            })
            .join('');

        this.grid.innerHTML = isCompact ? `<div class="product-list--compact">${cards}</div>` : cards;
        this.renderPagination(allProducts.length, totalPages);
        if (this.selectedProductId) {
            const selected = this.grid.querySelector<HTMLElement>(`[data-item-id="${this.selectedProductId}"]`);
            if (selected) {
                selected.classList.add('is-selected');
            } else {
                this.selectedProductId = null;
            }
        }
        this.updateQuickActions();
    }

    private renderStats(products: ProductWithCategory[]): void {
        if (this.statsTotal) {
            this.statsTotal.textContent = String(products.length);
        }
        if (this.statsAvailable) {
            const available = products.filter((item) => item.is_available).length;
            this.statsAvailable.textContent = String(available);
        }
    }

    private renderPagination(totalItems: number, totalPages: number): void {
        if (!this.pagination) return;

        // Always show items per page selector, even with 1 page
        const currentPage = this.state.currentPage;
        const itemsPerPage = this.state.itemsPerPage;
        const startItem = totalItems > 0 ? (currentPage - 1) * itemsPerPage + 1 : 0;
        const endItem = Math.min(currentPage * itemsPerPage, totalItems);

        // Items per page selector
        const perPageOptions = ITEMS_PER_PAGE_OPTIONS.map(opt =>
            `<option value="${opt}" ${opt === itemsPerPage ? 'selected' : ''}>${opt}</option>`
        ).join('');

        let html = `
            <div class="pagination">
                <div class="pagination__per-page">
                    <label>Mostrar:</label>
                    <select class="pagination__select" id="products-per-page">
                        ${perPageOptions}
                    </select>
                </div>`;

        if (totalPages > 1) {
            const maxVisiblePages = 5;
            let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
            let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
            if (endPage - startPage < maxVisiblePages - 1) {
                startPage = Math.max(1, endPage - maxVisiblePages + 1);
            }

            html += `
                <div class="pagination__controls">
                    <button class="pagination__btn pagination__btn--nav ${currentPage === 1 ? 'disabled' : ''}"
                        onclick="window.goToProductPage(${currentPage - 1})"
                        ${currentPage === 1 ? 'disabled' : ''}>
                        ‹ Anterior
                    </button>
                    <div class="pagination__numbers">`;

            if (startPage > 1) {
                html += `<button class="pagination__btn" onclick="window.goToProductPage(1)">1</button>`;
                if (startPage > 2) {
                    html += `<span class="pagination__ellipsis">...</span>`;
                }
            }

            for (let i = startPage; i <= endPage; i += 1) {
                html += `<button class="pagination__btn ${i === currentPage ? 'pagination__btn--active' : ''}" onclick="window.goToProductPage(${i})">${i}</button>`;
            }

            if (endPage < totalPages) {
                if (endPage < totalPages - 1) {
                    html += `<span class="pagination__ellipsis">...</span>`;
                }
                html += `<button class="pagination__btn" onclick="window.goToProductPage(${totalPages})">${totalPages}</button>`;
            }

            html += `
                    </div>
                    <button class="pagination__btn pagination__btn--nav ${currentPage === totalPages ? 'disabled' : ''}"
                        onclick="window.goToProductPage(${currentPage + 1})"
                        ${currentPage === totalPages ? 'disabled' : ''}>
                        Siguiente ›
                    </button>
                </div>`;
        }

        html += `
                <div class="pagination__info">
                    ${startItem}-${endItem} de ${totalItems} productos
                </div>
            </div>`;

        this.pagination.innerHTML = html;

        // Attach event listener for items per page change
        const perPageSelect = document.getElementById('products-per-page') as HTMLSelectElement;
        perPageSelect?.addEventListener('change', () => {
            const newValue = parseInt(perPageSelect.value, 10);
            saveItemsPerPage(newValue);
            this.state.itemsPerPage = newValue;
            this.state.currentPage = 1;
            this.renderGrid();
        });
    }

    private updateSuggestions(query: string): void {
        if (!this.suggestions) return;
        const trimmed = query.trim().toLowerCase();
        if (!trimmed) {
            this.suggestions.classList.remove('active');
            this.suggestions.innerHTML = '';
            return;
        }
        const matches = this.flattenProducts()
            .filter((product) => `${product.name} ${(product.description || '')}`.toLowerCase().includes(trimmed))
            .slice(0, 6);
        if (!matches.length) {
            this.suggestions.classList.remove('active');
            this.suggestions.innerHTML = '';
            return;
        }
        this.suggestions.innerHTML = matches
            .map(
                (match) => `
                <button type="button" data-suggested data-label="${match.name}">
                    <span>${match.name}</span>
                    <small>${match.categoryName || ''}</small>
                </button>`
            )
            .join('');
        this.suggestions.classList.add('active');
    }

    private updateViewButtons(): void {
        document.querySelectorAll<HTMLButtonElement>('[data-product-view-mode]').forEach((btn) => {
            const mode = btn.dataset.productViewMode === 'compact' ? 'compact' : 'grid';
            btn.classList.toggle('active', mode === this.state.viewMode);
        });
    }

    private setSelectedProduct(productId: number): void {
        if (!this.grid) return;
        this.grid.querySelectorAll<HTMLElement>('.product-card, .product-row').forEach((card) => {
            card.classList.remove('is-selected');
        });
        const card = this.grid.querySelector<HTMLElement>(`[data-item-id="${productId}"]`);
        if (!card) return;
        card.classList.add('is-selected');
        this.selectedProductId = productId;
        this.updateQuickActions();
    }

    private updateQuickActions(): void {
        const enabled = Boolean(this.selectedProductId && this.allowProductEdits);
        if (this.quickEditBtn) this.quickEditBtn.disabled = !enabled;
        if (this.quickToggleBtn) this.quickToggleBtn.disabled = !enabled;
        if (this.quickDeleteBtn) this.quickDeleteBtn.disabled = !enabled;
        if (!enabled || !this.selectedProductId || !this.quickToggleBtn) return;
        const product = this.flattenProducts().find((item) => item.id === this.selectedProductId);
        if (!product) return;
        this.quickToggleBtn.title = product.is_available ? 'Marcar Agotado' : 'Marcar Disponible';
    }
}
