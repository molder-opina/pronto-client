interface CustomerBasic {
    id: number;
    name?: string | null;
    email?: string | null;
    phone?: string | null;
    user_id?: string | null;
    total_orders?: number;
    is_active?: boolean;
    total_spent?: number;
    loyalty_points?: number;
    created_at?: string;
}

interface CustomerOrder {
    id: number;
    created_at: string;
    items?: Array<Record<string, unknown>>;
    total: number;
    status?: string | null;
}

interface CustomerCoupon {
    code: string;
    used_at: string;
    discount_type: 'percentage' | 'fixed';
    discount_percentage?: number;
    discount_amount?: number;
}

interface PaginationInstance<T = any> {
    update: (totalItems: number, resetToFirstPage?: boolean) => void;
    getCurrentPageData: (items: T[]) => T[];
    register: () => void;
}

type PaginationCtor = new (options: {
    container: HTMLElement;
    itemsPerPage?: number;
    onPageChange?: () => void;
    labels?: Record<string, string>;
}) => PaginationInstance;

function unwrapApiResponse<T = any>(result: any, fallbackMessage: string): T {
    if (!result) {
        throw new Error(fallbackMessage);
    }
    if (result.error) {
        throw new Error(result.error || fallbackMessage);
    }
    if (result.status && result.status !== 'success') {
        throw new Error(result.message || fallbackMessage);
    }
    return (result.data ?? result) as T;
}

export function initCustomersManager(): void {
    document.addEventListener('DOMContentLoaded', () => {
        const root = document.querySelector<HTMLElement>('[data-customers-root]');
        if (!root) return;
        const manager = new CustomersManager(root);
        manager.initialize();
        window.openCustomerDetail = (customerId: number) => manager.openCustomerDetail(customerId);
        window.closeCustomerDetail = () => manager.closeDetail();
    });
}

class CustomersManager {
    private root: HTMLElement;
    private searchInput: HTMLInputElement | null;
    private searchBtn: HTMLButtonElement | null;
    private resultsContainer: HTMLElement | null;
    private detailPanel: HTMLElement | null;
    private detailName: HTMLElement | null;
    private detailEmail: HTMLElement | null;
    private closeDetailBtn: HTMLButtonElement | null;
    private statsTotal: HTMLElement | null;
    private statsActive: HTMLElement | null;
    private infoGrid: HTMLElement | null;
    private statsCards: HTMLElement | null;
    private ordersList: HTMLElement | null;
    private couponsList: HTMLElement | null;
    private searchPagination: PaginationInstance | null = null;
    private ordersPagination: PaginationInstance | null = null;
    private searchResults: CustomerBasic[] = [];
    private orderResults: CustomerOrder[] = [];
    private viewingCustomerId: number | null = null;
    private currencySymbol = window.APP_SETTINGS?.currency_symbol || '$';

    constructor(root: HTMLElement) {
        this.root = root;
        this.searchInput = root.querySelector('#customer-search-main');
        this.searchBtn = root.querySelector('#customer-search-btn');
        this.resultsContainer = root.querySelector('#customer-search-results');
        this.detailPanel = root.querySelector('#customer-detail-panel');
        this.detailName = root.querySelector('#customer-detail-name');
        this.detailEmail = root.querySelector('#customer-detail-email');
        this.closeDetailBtn = root.querySelector('#close-customer-detail');
        this.statsTotal = root.querySelector('#customer-total-count');
        this.statsActive = root.querySelector('#customer-active-count');
        this.infoGrid = root.querySelector('#customer-info-grid');
        this.statsCards = root.querySelector('#customer-stats-cards');
        this.ordersList = root.querySelector('#customer-orders-list');
        this.couponsList = root.querySelector('#customer-coupons-list');
    }

    initialize(): void {
        this.setupPagination();
        this.attachEvents();
        void this.loadCustomerStats();
    }

    private setupPagination(): void {
        const paginationCtor: PaginationCtor | undefined = window.PaginationManager;
        if (!paginationCtor) return;
        const searchContainer = this.root.querySelector<HTMLElement>('#customer-search-pagination');
        if (searchContainer) {
            this.searchPagination = new paginationCtor({
                container: searchContainer,
                storageKey: 'customers',
                onPageChange: () => this.renderSearchResults(),
                labels: {
                    previous: '‹ Anterior',
                    next: 'Siguiente ›',
                    of: 'de',
                    items: ''
                }
            });
            this.searchPagination.register();
        }
        const ordersContainer = this.root.querySelector<HTMLElement>('#customer-orders-pagination');
        if (ordersContainer) {
            this.ordersPagination = new paginationCtor({
                container: ordersContainer,
                storageKey: 'customer_orders',
                onPageChange: () => this.renderOrders(),
                labels: {
                    previous: '‹ Anterior',
                    next: 'Siguiente ›',
                    of: 'de',
                    items: ''
                }
            });
            this.ordersPagination.register();
        }
    }

    private attachEvents(): void {
        this.searchBtn?.addEventListener('click', () => this.searchCustomers());
        this.searchInput?.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                void this.searchCustomers();
            }
        });
        this.closeDetailBtn?.addEventListener('click', () => this.closeDetail());
    }

    private async loadCustomerStats(): Promise<void> {
        try {
            const response = await fetch('/api/customers/stats');
            if (!response.ok) {
                throw new Error('Error al cargar estadísticas');
            }
            const result = await response.json();
            const stats = unwrapApiResponse<{ total?: number; active?: number }>(result, 'Error al cargar estadísticas');
            if (this.statsTotal) this.statsTotal.textContent = String(stats.total ?? '--');
            if (this.statsActive) this.statsActive.textContent = String(stats.active ?? '--');
        } catch (error) {
            console.error('[CUSTOMERS] stats', error);
        }
    }

    private async searchCustomers(): Promise<void> {
        if (!this.searchInput || !this.resultsContainer) return;
        const query = this.searchInput.value.trim();
        if (!query) {
            this.resultsContainer.style.display = 'none';
            this.resultsContainer.innerHTML = '';
            return;
        }
        this.resultsContainer.innerHTML =
            '<p style="text-align:center;padding:1rem;color:#64748b;">🔍 Buscando...</p>';
        this.resultsContainer.style.display = 'block';
        try {
            const response = await fetch(`/api/customers/search?q=${encodeURIComponent(query)}`);
            if (!response.ok) {
                throw new Error('Error al buscar clientes');
            }
            const result = await response.json();
            const payload = unwrapApiResponse<{ customers?: CustomerBasic[] }>(result, 'Error al buscar clientes');
            this.searchResults = payload.customers || [];
            if (!this.searchResults.length) {
                this.resultsContainer.innerHTML = `<p style="text-align:center;padding:2rem;color:#64748b;">No se encontraron clientes con "<strong>${query}</strong>"</p>`;
                this.searchPagination?.update(0, true);
                return;
            }
            this.searchPagination?.update(this.searchResults.length, true);
            this.renderSearchResults();
        } catch (error) {
            console.error('[CUSTOMERS] search', error);
            this.resultsContainer.innerHTML =
                '<p style="text-align:center;padding:2rem;color:#ef4444;">Error al buscar clientes</p>';
        }
    }

    private renderSearchResults(): void {
        if (!this.resultsContainer) return;
        const data = this.searchPagination
            ? this.searchPagination.getCurrentPageData(this.searchResults)
            : this.searchResults;
        this.resultsContainer.innerHTML = data
            .map((customer) => {
                const statusBadge =
                    customer.is_active !== false
                        ? '<span style="color:#10b981;font-size:0.75rem;">✓ Activo</span>'
                        : '<span style="color:#94a3b8;font-size:0.75rem;">○ Inactivo</span>';
                return `
                    <div class="customer-search-result-item" data-customer-id="${customer.id}">
                        <div class="customer-search-result-info">
                            <h4>${customer.name || 'Sin nombre'}</h4>
                            <p>
                                ${customer.email || 'Sin email'}
                                ${customer.user_id ? ` • ID: ${customer.user_id}` : ''}
                                ${customer.phone ? ` • ${customer.phone}` : ''}
                            </p>
                        </div>
                        <div style="text-align:right;">
                            ${statusBadge}
                            <p style="color:#64748b;font-size:0.875rem;margin:0.25rem 0 0;">
                                ${customer.total_orders || 0} pedidos
                            </p>
                        </div>
                    </div>`;
            })
            .join('');
        this.resultsContainer
            .querySelectorAll('.customer-search-result-item')
            .forEach((item) =>
                item.addEventListener('click', () => {
                    const id = Number(item.getAttribute('data-customer-id'));
                    if (Number.isFinite(id)) {
                        void this.openCustomerDetail(id);
                    }
                })
            );
    }

    async openCustomerDetail(customerId: number): Promise<void> {
        if (!this.detailPanel) return;
        this.viewingCustomerId = customerId;
        this.detailPanel.style.display = 'block';
        if (this.detailName) this.detailName.textContent = 'Cargando...';
        if (this.detailEmail) this.detailEmail.textContent = '';
        try {
            const response = await fetch(`/api/customers/${customerId}`);
            if (!response.ok) {
                throw new Error('Error al cargar cliente');
            }
            const result = await response.json();
            const payload = unwrapApiResponse<{ customer?: CustomerBasic }>(result, 'Error al cargar cliente');
            const customer = (payload.customer || payload) as CustomerBasic;
            if (this.detailName) this.detailName.textContent = customer.name || 'Cliente';
            if (this.detailEmail) this.detailEmail.textContent = customer.email || 'Sin email';
            this.renderCustomerInfo(customer);
            this.renderCustomerStats(customer);
            await Promise.all([this.loadCustomerOrders(customerId), this.loadCustomerCoupons(customerId)]);
            if (this.resultsContainer) this.resultsContainer.style.display = 'none';
        } catch (error) {
            console.error('[CUSTOMERS] detail', error);
            alert('Error al cargar información del cliente');
            this.detailPanel.style.display = 'none';
        }
    }

    closeDetail(): void {
        if (!this.detailPanel) return;
        this.detailPanel.style.display = 'none';
        this.viewingCustomerId = null;
    }

    private renderCustomerInfo(customer: CustomerBasic): void {
        if (!this.infoGrid) return;
        const createdDate = customer.created_at ? new Date(customer.created_at).toLocaleDateString() : 'Desconocido';
        this.infoGrid.innerHTML = `
            <div class="customer-info-item">
                <span>Email</span>
                <strong>${customer.email || 'No registrado'}</strong>
            </div>
            <div class="customer-info-item">
                <span>Teléfono</span>
                <strong>${customer.phone || 'No registrado'}</strong>
            </div>
            <div class="customer-info-item">
                <span>Cliente desde</span>
                <strong>${createdDate}</strong>
            </div>
            <div class="customer-info-item">
                <span>Estado</span>
                <strong>${customer.is_active !== false ? 'Activo' : 'Inactivo'}</strong>
            </div>`;
    }

    private renderCustomerStats(customer: CustomerBasic): void {
        if (!this.statsCards) return;
        const totalOrders = customer.total_orders || 0;
        const totalSpent = customer.total_spent || 0;
        const loyaltyPoints = customer.loyalty_points || 0;
        this.statsCards.innerHTML = `
            <div class="customer-stat-card">
                <span>Total pedidos</span>
                <strong>${totalOrders}</strong>
            </div>
            <div class="customer-stat-card">
                <span>Total gastado</span>
                <strong>${this.formatCurrency(totalSpent)}</strong>
            </div>
            <div class="customer-stat-card">
                <span>Puntos</span>
                <strong>${loyaltyPoints}</strong>
            </div>`;
    }

    private async loadCustomerOrders(customerId: number): Promise<void> {
        if (!this.ordersList) return;
        this.ordersList.innerHTML = '<p style="text-align:center;color:#64748b;">Cargando órdenes...</p>';
        try {
            const response = await fetch(`/api/customers/${customerId}/orders`);
            if (!response.ok) {
                throw new Error('Error al cargar órdenes');
            }
            const result = await response.json();
            const payload = unwrapApiResponse<{ orders?: CustomerOrder[] }>(result, 'Error al cargar órdenes');
            this.orderResults = payload.orders || [];
            if (!this.orderResults.length) {
                this.ordersList.innerHTML =
                    '<p style="text-align:center;color:#64748b;">Este cliente no tiene órdenes</p>';
                this.ordersPagination?.update(0, true);
                return;
            }
            this.ordersPagination?.update(this.orderResults.length, true);
            this.renderOrders();
        } catch (error) {
            console.error('[CUSTOMERS] orders', error);
            this.ordersList.innerHTML =
                '<p style="text-align:center;color:#ef4444;">Error al cargar órdenes</p>';
        }
    }

    private renderOrders(): void {
        if (!this.ordersList) return;
        const orders = this.ordersPagination
            ? this.ordersPagination.getCurrentPageData(this.orderResults)
            : this.orderResults;
        this.ordersList.innerHTML = orders
            .map((order) => {
                const date = new Date(order.created_at);
                const itemsCount = order.items?.length || 0;
                const itemsText = itemsCount === 1 ? '1 producto' : `${itemsCount} productos`;
                return `
                    <div class="customer-order-item">
                        <div class="customer-order-header">
                            <span class="customer-order-id">#${order.id}</span>
                            <span class="customer-order-date">${date.toLocaleDateString()} ${date.toLocaleTimeString()}</span>
                        </div>
                        <div class="customer-order-items">${itemsText}</div>
                        <div class="customer-order-footer">
                            <span class="customer-order-total">${this.formatCurrency(order.total)}</span>
                            <span class="customer-order-status">${order.status || 'Completada'}</span>
                        </div>
                    </div>`;
            })
            .join('');
    }

    private async loadCustomerCoupons(customerId: number): Promise<void> {
        if (!this.couponsList) return;
        this.couponsList.innerHTML = '<p style="text-align:center;color:#64748b;">Cargando cupones...</p>';
        try {
            const response = await fetch(`/api/customers/${customerId}/coupons`);
            if (!response.ok) {
                throw new Error('Error al cargar cupones');
            }
            const result = await response.json();
            const payload = unwrapApiResponse<{ coupons?: CustomerCoupon[] }>(result, 'Error al cargar cupones');
            const coupons: CustomerCoupon[] = payload.coupons || [];
            if (!coupons.length) {
                this.couponsList.innerHTML =
                    '<p style="text-align:center;color:#64748b;">Este cliente no ha usado cupones</p>';
                return;
            }
            this.couponsList.innerHTML = coupons
                .map((coupon) => {
                    const usedDate = new Date(coupon.used_at).toLocaleDateString();
                    const discount =
                        coupon.discount_type === 'percentage'
                            ? `${coupon.discount_percentage}%`
                            : this.formatCurrency(coupon.discount_amount || 0);
                    return `
                        <div class="customer-coupon-item">
                            <div class="customer-coupon-code">${coupon.code}</div>
                            <div class="customer-coupon-info">
                                <div class="customer-coupon-date">Usado el ${usedDate}</div>
                                <div class="customer-coupon-discount">-${discount}</div>
                            </div>
                        </div>`;
                })
                .join('');
        } catch (error) {
            console.error('[CUSTOMERS] coupons', error);
            this.couponsList.innerHTML =
                '<p style="text-align:center;color:#ef4444;">Error al cargar cupones</p>';
        }
    }

    private formatCurrency(value?: number): string {
        const amount = Number(value) || 0;
        return `${this.currencySymbol}${amount.toFixed(2)}`;
    }
}
