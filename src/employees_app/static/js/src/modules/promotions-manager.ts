// Pagination config
const ITEMS_PER_PAGE_OPTIONS = [10, 20, 50, 100];
const PROMO_STORAGE_KEY = 'pronto_items_per_page_promotions';
const COUPON_STORAGE_KEY = 'pronto_items_per_page_coupons';

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

function getSavedItemsPerPage(storageKey: string): number {
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved) {
      const value = parseInt(saved, 10);
      if (ITEMS_PER_PAGE_OPTIONS.includes(value)) return value;
    }
    const global = localStorage.getItem('pronto_items_per_page');
    if (global) {
      const value = parseInt(global, 10);
      if (ITEMS_PER_PAGE_OPTIONS.includes(value)) return value;
    }
  } catch (e) {
    /* ignore */
  }
  return 20;
}

function saveItemsPerPage(value: number, storageKey: string): void {
  try {
    localStorage.setItem(storageKey, String(value));
    localStorage.setItem('pronto_items_per_page', String(value));
  } catch (e) {
    /* ignore */
  }
}

interface PromotionRecord {
  id: number;
  name: string;
  description?: string | null;
  promotion_type: 'percentage' | 'fixed' | 'bogo' | string;
  discount_value?: number;
  discount_amount?: number;
  start_date?: string | null;
  end_date?: string | null;
  is_active?: boolean;
  applies_to?: 'products' | 'tags' | 'package';
  package_name?: string | null;
  tags?: string[] | null;
  products?: Array<{ id: number; name: string }>;
}

interface PromotionState {
  allPromotions: PromotionRecord[];
  statusFilter: 'all' | 'active' | 'inactive';
  typeFilter: string;
  search: string;
  currentPage: number;
  itemsPerPage: number;
}

interface CouponRecord {
  id: number;
  code: string;
  description?: string | null;
  discount_type: string;
  discount_value?: number;
  max_redemptions?: number | null;
  redeemed_count?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  is_active?: boolean;
  applies_to?: 'all' | 'tags' | 'products';
  tags?: string[] | null;
  products?: Array<{ id: number; name: string }>;
  min_purchase_amount?: number | null;
}

interface CouponState {
  allCoupons: CouponRecord[];
  statusFilter: 'all' | 'active' | 'expired';
  typeFilter: string;
  search: string;
  currentPage: number;
  itemsPerPage: number;
}

export function initPromotionsManager(): void {
  document.addEventListener('DOMContentLoaded', () => {
    const section = document.querySelector<HTMLElement>('[data-promotions-root]');
    const couponsSection = document.querySelector<HTMLElement>('[data-coupons-root]');
    if (!section && !couponsSection) return;
    const manager = new PromotionsManager(section, couponsSection);
    manager.initialize();
    window.ProntoPromotions = {
      reload: () => manager.reload(),
    };
  });
}

class PromotionsManager {
  private promotionsRoot: HTMLElement | null;
  private couponsRoot: HTMLElement | null;
  private promotionState: PromotionState = {
    allPromotions: [],
    statusFilter: 'all',
    typeFilter: 'all',
    search: '',
    currentPage: 1,
    itemsPerPage: getSavedItemsPerPage(PROMO_STORAGE_KEY),
  };
  private couponState: CouponState = {
    allCoupons: [],
    statusFilter: 'all',
    typeFilter: 'all',
    search: '',
    currentPage: 1,
    itemsPerPage: getSavedItemsPerPage(COUPON_STORAGE_KEY),
  };

  constructor(promotionsRoot: HTMLElement | null, couponsRoot: HTMLElement | null) {
    this.promotionsRoot = promotionsRoot;
    this.couponsRoot = couponsRoot;
  }

  initialize(): void {
    if (this.promotionsRoot) this.attachPromotionEvents();
    if (this.couponsRoot) this.attachCouponEvents();
    void this.reload();
  }

  async reload(): Promise<void> {
    await Promise.all([this.loadPromotions(), this.loadCoupons()]);
  }

  private async loadPromotions(): Promise<void> {
    if (!this.promotionsRoot) return;
    this.setLoading(this.promotionsRoot, true);
    try {
      const response = await fetch('/api/promotions');
      const result = await response.json();
      const payload = unwrapApiResponse<{ promotions?: PromotionRecord[] }>(
        result,
        'Error al cargar promociones'
      );
      this.promotionState.allPromotions = payload.promotions || [];
      this.renderPromotionTypeFilters();
      this.renderPromotionCards();
      this.updatePromotionStats();
    } catch (error) {
      this.renderError(this.promotionsRoot, (error as Error).message);
    } finally {
      this.setLoading(this.promotionsRoot, false);
    }
  }

  private async loadCoupons(): Promise<void> {
    if (!this.couponsRoot) return;
    this.setLoading(this.couponsRoot, true);
    try {
      const response = await fetch('/api/discount-codes');
      const result = await response.json();
      const payload = unwrapApiResponse<{ discount_codes?: CouponRecord[] }>(
        result,
        'Error al cargar cupones'
      );
      this.couponState.allCoupons = payload.discount_codes || [];
      this.renderCouponTypeFilters();
      this.renderCouponCards();
      this.updateCouponStats();
    } catch (error) {
      this.renderError(this.couponsRoot, (error as Error).message);
    } finally {
      this.setLoading(this.couponsRoot, false);
    }
  }

  private attachPromotionEvents(): void {
    const searchInput = this.promotionsRoot?.querySelector<HTMLInputElement>('#promotion-search');
    const statusFilter = this.promotionsRoot?.querySelector('#promotion-status-filter');
    const typeFilter = this.promotionsRoot?.querySelector('#promotion-type-filter');
    searchInput?.addEventListener('input', (event) => {
      const target = event.currentTarget as HTMLInputElement | null;
      this.promotionState.search = (target?.value || '').toLowerCase();
      this.renderPromotionCards();
    });
    statusFilter?.addEventListener('click', (event) => {
      const target = (event.target as HTMLElement).closest<HTMLButtonElement>(
        'button[data-status]'
      );
      if (!target) return;
      this.promotionState.statusFilter = target.dataset.status as PromotionState['statusFilter'];
      statusFilter
        .querySelectorAll('button')
        .forEach((btn) => btn.classList.toggle('active', btn === target));
      this.renderPromotionCards();
    });
    typeFilter?.addEventListener('click', (event) => {
      const target = (event.target as HTMLElement).closest<HTMLButtonElement>('button[data-type]');
      if (!target) return;
      this.promotionState.typeFilter = target.dataset.type || 'all';
      typeFilter
        .querySelectorAll('button')
        .forEach((btn) => btn.classList.toggle('active', btn === target));
      this.renderPromotionCards();
    });
    this.promotionsRoot?.querySelector('#new-promotion-btn')?.addEventListener('click', () => {
      this.openDrawer('promotion');
    });
    this.promotionsRoot?.querySelector('#close-promotion-drawer')?.addEventListener('click', () => {
      this.closeDrawer('promotion');
    });
    this.promotionsRoot?.querySelector('#cancel-promotion-btn')?.addEventListener('click', () => {
      this.closeDrawer('promotion');
    });
  }

  private attachCouponEvents(): void {
    const searchInput = this.couponsRoot?.querySelector<HTMLInputElement>('#coupon-search');
    const statusFilter = this.couponsRoot?.querySelector('#coupon-status-filter');
    const typeFilter = this.couponsRoot?.querySelector('#coupon-type-filter');
    searchInput?.addEventListener('input', (event) => {
      const target = event.currentTarget as HTMLInputElement | null;
      this.couponState.search = (target?.value || '').toLowerCase();
      this.renderCouponCards();
    });
    statusFilter?.addEventListener('click', (event) => {
      const target = (event.target as HTMLElement).closest<HTMLButtonElement>(
        'button[data-status]'
      );
      if (!target) return;
      this.couponState.statusFilter = target.dataset.status as CouponState['statusFilter'];
      statusFilter
        .querySelectorAll('button')
        .forEach((btn) => btn.classList.toggle('active', btn === target));
      this.renderCouponCards();
    });
    typeFilter?.addEventListener('click', (event) => {
      const target = (event.target as HTMLElement).closest<HTMLButtonElement>('button[data-type]');
      if (!target) return;
      this.couponState.typeFilter = target.dataset.type || 'all';
      typeFilter
        .querySelectorAll('button')
        .forEach((btn) => btn.classList.toggle('active', btn === target));
      this.renderCouponCards();
    });
    this.couponsRoot?.querySelector('#new-coupon-btn')?.addEventListener('click', () => {
      this.openDrawer('coupon');
    });
    this.couponsRoot?.querySelector('#close-coupon-drawer')?.addEventListener('click', () => {
      this.closeDrawer('coupon');
    });
    this.couponsRoot?.querySelector('#cancel-coupon-btn')?.addEventListener('click', () => {
      this.closeDrawer('coupon');
    });
  }

  private renderPromotionTypeFilters(): void {
    const container = this.promotionsRoot?.querySelector('#promotion-type-filter');
    if (!container) return;
    const types = Array.from(
      new Set(this.promotionState.allPromotions.map((promo) => promo.promotion_type))
    );
    const buttons = [
      this.createFilterButton('Todos', 'all', this.promotionState.typeFilter === 'all', 'type'),
    ];
    types.forEach((type) =>
      buttons.push(
        this.createFilterButton(
          this.getPromotionTypeLabel(type),
          type,
          type === this.promotionState.typeFilter,
          'type'
        )
      )
    );
    container.innerHTML = buttons.join('');
  }

  private renderCouponTypeFilters(): void {
    const container = this.couponsRoot?.querySelector('#coupon-type-filter');
    if (!container) return;
    const types = Array.from(
      new Set(this.couponState.allCoupons.map((coupon) => coupon.discount_type))
    );
    const buttons = [
      this.createFilterButton('Todos', 'all', this.couponState.typeFilter === 'all', 'type'),
    ];
    types.forEach((type) =>
      buttons.push(
        this.createFilterButton(
          this.getCouponTypeLabel(type),
          type,
          type === this.couponState.typeFilter,
          'type'
        )
      )
    );
    container.innerHTML = buttons.join('');
  }

  private createFilterButton(
    label: string,
    value: string,
    active: boolean,
    attr: 'type' | 'status'
  ): string {
    return `<button data-${attr}="${value}" class="${active ? 'active' : ''}">${label}</button>`;
  }

  private renderPromotionCards(): void {
    const grid = this.promotionsRoot?.querySelector('#promotion-grid');
    const emptyState = this.promotionsRoot?.querySelector('#promotion-empty-state');
    const paginationEl = this.promotionsRoot?.querySelector('#promotion-pagination');
    const allPromotions = this.getFilteredPromotions();
    if (!grid || !emptyState) return;

    if (!allPromotions.length) {
      emptyState.classList.remove('hidden');
      grid.innerHTML = '';
      if (paginationEl) paginationEl.innerHTML = '';
      return;
    }

    emptyState.classList.add('hidden');

    // Paginate
    const { currentPage, itemsPerPage } = this.promotionState;
    const totalPages = Math.ceil(allPromotions.length / itemsPerPage);
    const startIndex = (currentPage - 1) * itemsPerPage;
    const promotions = allPromotions.slice(startIndex, startIndex + itemsPerPage);

    grid.innerHTML = promotions.map((promo) => this.renderPromotionCard(promo)).join('');
    grid.querySelectorAll<HTMLButtonElement>('[data-promotion-id]').forEach((button) => {
      button.addEventListener('click', () => {
        const id = Number(button.dataset.promotionId);
        if (button.dataset.action === 'edit') this.openPromotionEditor(id);
        if (button.dataset.action === 'delete') void this.deletePromotion(id);
      });
    });

    // Render pagination
    if (paginationEl) {
      this.renderPaginationControls(
        paginationEl,
        allPromotions.length,
        totalPages,
        currentPage,
        itemsPerPage,
        'promotion'
      );
    }
  }

  private renderPromotionCard(promo: PromotionRecord): string {
    return `
            <article class="promotion-card ${promo.is_active ? 'active' : 'inactive'}">
                <header class="promotion-card__header">
                    <div>
                        <h3>${promo.name}</h3>
                        <p>${promo.description || 'Sin descripción'}</p>
                    </div>
                    <div class="promotion-card__status">
                        <span class="badge ${promo.is_active ? 'badge--success' : 'badge--neutral'}">
                            ${promo.is_active ? 'Activa' : 'Inactiva'}
                        </span>
                        <span class="badge">${this.getPromotionTypeLabel(promo.promotion_type)}</span>
                    </div>
                </header>
                <div class="promotion-card__body">
                    ${promo.applies_to === 'package' ? `<p>Paquete: <strong>${promo.package_name || 'Sin nombre'}</strong></p>` : ''}
                    ${promo.applies_to === 'tags' && promo.tags?.length ? `<p>Etiquetas: ${promo.tags.join(', ')}</p>` : ''}
                    ${promo.applies_to === 'products' && promo.products?.length ? `<p>Productos: ${promo.products.map((p) => p.name).join(', ')}</p>` : ''}
                    <p>Vigencia: ${this.formatDateRange(promo.start_date, promo.end_date)}</p>
                </div>
                <footer class="promotion-card__footer">
                    <button class="btn btn--small btn--secondary" data-action="edit" data-promotion-id="${promo.id}">Editar</button>
                    <button class="btn btn--small btn--danger" data-action="delete" data-promotion-id="${promo.id}">Eliminar</button>
                </footer>
            </article>`;
  }

  private renderCouponCards(): void {
    const grid = this.couponsRoot?.querySelector('#coupon-grid');
    const emptyState = this.couponsRoot?.querySelector('#coupon-empty-state');
    const paginationEl = this.couponsRoot?.querySelector('#coupon-pagination');
    const allCoupons = this.getFilteredCoupons();
    if (!grid || !emptyState) return;

    if (!allCoupons.length) {
      emptyState.classList.remove('hidden');
      grid.innerHTML = '';
      if (paginationEl) paginationEl.innerHTML = '';
      return;
    }

    emptyState.classList.add('hidden');

    // Paginate
    const { currentPage, itemsPerPage } = this.couponState;
    const totalPages = Math.ceil(allCoupons.length / itemsPerPage);
    const startIndex = (currentPage - 1) * itemsPerPage;
    const coupons = allCoupons.slice(startIndex, startIndex + itemsPerPage);

    grid.innerHTML = coupons.map((coupon) => this.renderCouponCard(coupon)).join('');
    grid.querySelectorAll<HTMLButtonElement>('[data-coupon-id]').forEach((button) => {
      button.addEventListener('click', () => {
        const id = Number(button.dataset.couponId);
        if (button.dataset.action === 'edit') this.openCouponEditor(id);
        if (button.dataset.action === 'delete') void this.deleteCoupon(id);
      });
    });

    // Render pagination
    if (paginationEl) {
      this.renderPaginationControls(
        paginationEl,
        allCoupons.length,
        totalPages,
        currentPage,
        itemsPerPage,
        'coupon'
      );
    }
  }

  private renderPaginationControls(
    container: Element,
    totalItems: number,
    totalPages: number,
    currentPage: number,
    itemsPerPage: number,
    type: 'promotion' | 'coupon'
  ): void {
    const startItem = totalItems > 0 ? (currentPage - 1) * itemsPerPage + 1 : 0;
    const endItem = Math.min(currentPage * itemsPerPage, totalItems);

    const perPageOptions = ITEMS_PER_PAGE_OPTIONS.map(
      (opt) => `<option value="${opt}" ${opt === itemsPerPage ? 'selected' : ''}>${opt}</option>`
    ).join('');

    let html = `<div class="pagination">
            <div class="pagination__per-page">
                <label>Mostrar:</label>
                <select class="pagination__select" data-pagination-type="${type}">
                    ${perPageOptions}
                </select>
            </div>`;

    if (totalPages > 1) {
      html += `<div class="pagination__controls">
                <button class="pagination__btn pagination__btn--nav" data-page="prev" data-type="${type}" ${currentPage === 1 ? 'disabled' : ''}>‹ Anterior</button>
                <div class="pagination__numbers">`;

      const maxVisible = 5;
      let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
      let endPage = Math.min(totalPages, startPage + maxVisible - 1);
      if (endPage - startPage < maxVisible - 1) startPage = Math.max(1, endPage - maxVisible + 1);

      if (startPage > 1) {
        html += `<button class="pagination__btn" data-page="1" data-type="${type}">1</button>`;
        if (startPage > 2) html += `<span class="pagination__ellipsis">...</span>`;
      }
      for (let i = startPage; i <= endPage; i++) {
        html += `<button class="pagination__btn ${i === currentPage ? 'pagination__btn--active' : ''}" data-page="${i}" data-type="${type}">${i}</button>`;
      }
      if (endPage < totalPages) {
        if (endPage < totalPages - 1) html += `<span class="pagination__ellipsis">...</span>`;
        html += `<button class="pagination__btn" data-page="${totalPages}" data-type="${type}">${totalPages}</button>`;
      }

      html += `</div>
                <button class="pagination__btn pagination__btn--nav" data-page="next" data-type="${type}" ${currentPage === totalPages ? 'disabled' : ''}>Siguiente ›</button>
            </div>`;
    }

    html += `<div class="pagination__info">${startItem}-${endItem} de ${totalItems}</div></div>`;
    container.innerHTML = html;

    // Attach event listeners
    container.querySelectorAll<HTMLButtonElement>('[data-page]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const pageVal = btn.dataset.page;
        const state = type === 'promotion' ? this.promotionState : this.couponState;
        let newPage = state.currentPage;
        if (pageVal === 'prev') newPage = Math.max(1, state.currentPage - 1);
        else if (pageVal === 'next') newPage = state.currentPage + 1;
        else newPage = parseInt(pageVal || '1', 10);

        state.currentPage = newPage;
        if (type === 'promotion') this.renderPromotionCards();
        else this.renderCouponCards();
      });
    });

    const perPageSelect = container.querySelector<HTMLSelectElement>(
      `[data-pagination-type="${type}"]`
    );
    perPageSelect?.addEventListener('change', () => {
      const newValue = parseInt(perPageSelect.value, 10);
      const storageKey = type === 'promotion' ? PROMO_STORAGE_KEY : COUPON_STORAGE_KEY;
      saveItemsPerPage(newValue, storageKey);

      const state = type === 'promotion' ? this.promotionState : this.couponState;
      state.itemsPerPage = newValue;
      state.currentPage = 1;

      if (type === 'promotion') this.renderPromotionCards();
      else this.renderCouponCards();
    });
  }

  private renderCouponCard(coupon: CouponRecord): string {
    return `
            <article class="promotion-card ${coupon.is_active ? 'active' : 'inactive'}">
                <header class="promotion-card__header">
                    <div>
                        <h3>${coupon.code}</h3>
                        <p>${coupon.description || 'Sin descripción'}</p>
                    </div>
                    <div class="promotion-card__status">
                        <span class="badge ${coupon.is_active ? 'badge--success' : 'badge--neutral'}">
                            ${coupon.is_active ? 'Activo' : 'Inactivo'}
                        </span>
                        <span class="badge">${this.getCouponTypeLabel(coupon.discount_type)}</span>
                    </div>
                </header>
                <div class="promotion-card__body">
                    <p>Aplicación: ${this.getCouponScopeLabel(coupon.applies_to)}</p>
                    <p>Vigencia: ${this.formatDateRange(coupon.start_date, coupon.end_date)}</p>
                    ${
                      typeof coupon.redeemed_count === 'number'
                        ? `<p>Canjes: ${coupon.redeemed_count}/${coupon.max_redemptions ?? '∞'}</p>`
                        : ''
                    }
                </div>
                <footer class="promotion-card__footer">
                    <button class="btn btn--small btn--secondary" data-action="edit" data-coupon-id="${coupon.id}">Editar</button>
                    <button class="btn btn--small btn--danger" data-action="delete" data-coupon-id="${coupon.id}">Eliminar</button>
                </footer>
            </article>`;
  }

  private updatePromotionStats(): void {
    const totalEl = this.promotionsRoot?.querySelector('#promotion-total-count');
    const activeEl = this.promotionsRoot?.querySelector('#promotion-active-count');
    const countLabel = this.promotionsRoot?.querySelector('#promotion-count-label');
    totalEl && (totalEl.textContent = String(this.promotionState.allPromotions.length));
    activeEl &&
      (activeEl.textContent = String(
        this.promotionState.allPromotions.filter((p) => p.is_active).length
      ));
    countLabel &&
      (countLabel.textContent = `${this.getFilteredPromotions().length} promoción(es) encontradas`);
  }

  private updateCouponStats(): void {
    const totalEl = this.couponsRoot?.querySelector('#coupon-total-count');
    const activeEl = this.couponsRoot?.querySelector('#coupon-active-count');
    const countLabel = this.couponsRoot?.querySelector('#coupon-count-label');
    totalEl && (totalEl.textContent = String(this.couponState.allCoupons.length));
    activeEl &&
      (activeEl.textContent = String(
        this.couponState.allCoupons.filter((c) => c.is_active).length
      ));
    countLabel &&
      (countLabel.textContent = `${this.getFilteredCoupons().length} cupón(es) encontrados`);
  }

  private getFilteredPromotions(): PromotionRecord[] {
    return this.promotionState.allPromotions.filter((promo) => {
      const matchesStatus =
        this.promotionState.statusFilter === 'all' ||
        (this.promotionState.statusFilter === 'active' && promo.is_active) ||
        (this.promotionState.statusFilter === 'inactive' && !promo.is_active);
      const matchesType =
        this.promotionState.typeFilter === 'all' ||
        promo.promotion_type === this.promotionState.typeFilter ||
        (this.promotionState.typeFilter === 'packages' && promo.applies_to === 'package');
      const matchesSearch =
        !this.promotionState.search ||
        promo.name.toLowerCase().includes(this.promotionState.search) ||
        (promo.description || '').toLowerCase().includes(this.promotionState.search);
      return matchesStatus && matchesType && matchesSearch;
    });
  }

  private getFilteredCoupons(): CouponRecord[] {
    return this.couponState.allCoupons.filter((coupon) => {
      const matchesStatus =
        this.couponState.statusFilter === 'all' ||
        (this.couponState.statusFilter === 'active' && coupon.is_active) ||
        (this.couponState.statusFilter === 'expired' && !coupon.is_active);
      const matchesType =
        this.couponState.typeFilter === 'all' ||
        coupon.discount_type === this.couponState.typeFilter;
      const matchesSearch =
        !this.couponState.search ||
        coupon.code.toLowerCase().includes(this.couponState.search) ||
        (coupon.description || '').toLowerCase().includes(this.couponState.search);
      return matchesStatus && matchesType && matchesSearch;
    });
  }

  private getPromotionTypeLabel(type: string): string {
    switch (type) {
      case 'percentage':
        return 'Porcentaje';
      case 'fixed':
        return 'Monto fijo';
      case 'bogo':
        return 'Compra x y lleva y';
      default:
        return type;
    }
  }

  private getCouponTypeLabel(type: string): string {
    switch (type) {
      case 'percentage':
        return 'Porcentaje';
      case 'fixed':
        return 'Monto fijo';
      case 'shipping':
        return 'Envío';
      default:
        return type;
    }
  }

  private getCouponScopeLabel(scope?: string | null): string {
    switch (scope) {
      case 'tags':
        return 'Etiquetas específicas';
      case 'products':
        return 'Productos específicos';
      default:
        return 'Todo el catálogo';
    }
  }

  private formatDateRange(start?: string | null, end?: string | null): string {
    if (!start && !end) return 'Sin vigencia definida';
    const startDate = start ? new Date(start).toLocaleDateString() : 'Inicio abierto';
    const endDate = end ? new Date(end).toLocaleDateString() : 'Sin fecha fin';
    return `${startDate} - ${endDate}`;
  }

  private openDrawer(type: 'promotion' | 'coupon'): void {
    const drawer = document.getElementById(`${type}-drawer`);
    drawer?.classList.add('active');
  }

  private closeDrawer(type: 'promotion' | 'coupon'): void {
    const drawer = document.getElementById(`${type}-drawer`);
    drawer?.classList.remove('active');
  }

  private openPromotionEditor(id: number): void {
    console.info('[PROMOTIONS] open editor for', id);
    this.openDrawer('promotion');
  }

  private openCouponEditor(id: number): void {
    console.info('[COUPONS] open editor for', id);
    this.openDrawer('coupon');
  }

  private async deletePromotion(id: number): Promise<void> {
    if (!window.confirm('¿Eliminar esta promoción?')) return;
    try {
      const response = await fetch(`/api/promotions/${id}`, { method: 'DELETE' });
      const result = await response.json();
      unwrapApiResponse(result, 'Error al eliminar');
      showToast('Promoción eliminada', 'success');
      await this.loadPromotions();
    } catch (error) {
      showToast((error as Error).message, 'error');
    }
  }

  private async deleteCoupon(id: number): Promise<void> {
    if (!window.confirm('¿Eliminar este cupón?')) return;
    try {
      const response = await fetch(`/api/discount-codes/${id}`, { method: 'DELETE' });
      const result = await response.json();
      unwrapApiResponse(result, 'Error al eliminar');
      showToast('Cupón eliminado', 'success');
      await this.loadCoupons();
    } catch (error) {
      showToast((error as Error).message, 'error');
    }
  }

  private renderError(root: HTMLElement, message: string): void {
    const target = root.querySelector('.promo-errors') || root;
    target.innerHTML = `<p class="error">${message}</p>`;
  }

  private setLoading(root: HTMLElement, loading: boolean): void {
    if (loading) {
      (window.EmployeeLoading || window.GlobalLoading)?.start?.();
    } else {
      (window.EmployeeLoading || window.GlobalLoading)?.stop?.();
    }
  }
}

function showToast(message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info'): void {
  if (typeof window.showToast === 'function') {
    window.showToast(message, type);
  } else {
    console.log(`[toast:${type}] ${message}`);
  }
}

declare global {
  interface Window {
    ProntoPromotions?: {
      reload: () => Promise<void>;
    };
  }
}
