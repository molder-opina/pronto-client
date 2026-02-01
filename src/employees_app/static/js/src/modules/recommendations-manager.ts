interface RecommendationItem {
  id: number;
  name: string;
  description?: string | null;
  price?: number;
  category_id?: number;
  category_name?: string;
  recommendation_periods?: string[];
}

interface PopularItem {
  id: number;
  name: string;
  description?: string | null;
  price: number;
  category_id?: number;
  category_name?: string;
  order_count: number;
  total_quantity: number;
}

interface DayPeriod {
  key: string;
  name: string;
  icon?: string | null;
  start_time?: string;
  end_time?: string;
}

const MAX_RECOMMENDATIONS = 3;

export function initRecommendationsManager(): void {
  document.addEventListener('DOMContentLoaded', () => {
    const root = document.querySelector<HTMLElement>('[data-recommendations-root]');
    if (!root) return;
    const manager = new RecommendationsManager(root);
    manager.initialize();
    window.ProntoRecommendations = manager;
  });
}

class RecommendationsManager {
  private root: HTMLElement;
  private dayPeriods: DayPeriod[];
  private dayPeriodMap: Map<string, DayPeriod>;
  private recommendations: RecommendationItem[] = [];
  private popularItems: PopularItem[] = [];
  private currentPeriod: string | null = null;
  private categoryFilter = 'all';
  private searchTerm = '';
  private currentPage = 1;
  private itemsPerPage = 10;
  private displayOrder: number[] = [];

  private filtersEl: HTMLElement | null;
  private productsListEl: HTMLElement | null;
  private searchInput: HTMLInputElement | null;
  private suggestionsEl: HTMLElement | null;
  private modal: HTMLElement | null;
  private feedbackEl: HTMLElement | null;
  private paginationEl: HTMLElement | null;
  private loadingTimeout: number | null = null;
  private isLoading = false;

  constructor(root: HTMLElement) {
    this.root = root;
    this.dayPeriods = (window.APP_DATA?.day_periods as DayPeriod[]) || [];
    this.dayPeriodMap = new Map(this.dayPeriods.map((period) => [period.key, period]));
    this.filtersEl = document.querySelector('.recommendation-filters');
    this.productsListEl = document.getElementById('recommendation-products-list');
    this.searchInput = document.getElementById('recommendation-search') as HTMLInputElement | null;
    this.suggestionsEl = document.getElementById('recommendation-search-suggestions');
    this.modal = document.getElementById('select-recommendation-modal');
    this.feedbackEl = document.getElementById('recommendations-feedback');
    this.paginationEl = document.getElementById('recommendation-pagination');
  }

  initialize(): void {
    this.bindGlobalHandlers();
    this.attachEvents();
    void this.loadRecommendations();
    void this.loadPopularItems();
  }

  async reload(): Promise<void> {
    await this.loadRecommendations();
  }

  private bindGlobalHandlers(): void {
    window.openAddRecommendationModal = (periodKey: string) => this.openModal(periodKey);
    window.closeSelectRecommendationModal = () => this.closeModal();
    window.filterRecommendationsByCategory = (category: string) =>
      this.handleCategoryChange(category);
    window.selectRecommendationProduct = (itemId: number) => this.handleSelectProduct(itemId);
    window.removeRecommendation = (itemId: number, periodKey: string) =>
      this.removeRecommendation(itemId, periodKey);
    window.previewClientMenu = () => this.showClientMenuPreview();
    window.closeClientMenuPreview = () => this.closeClientMenuPreview();
  }

  private attachEvents(): void {
    this.root.querySelectorAll<HTMLButtonElement>('.add-recommendation-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const period = btn.dataset.period || '';
        this.openModal(period);
      });
    });

    const managePeriodsBtn = document.getElementById('manage-day-periods-secondary');
    managePeriodsBtn?.addEventListener('click', () => {
      if (typeof window.activateSection === 'function') {
        window.activateSection('horarios');
      } else {
        window.location.hash = '#horarios';
      }
    });

    this.searchInput?.addEventListener('input', (event) => {
      const target = event.currentTarget as HTMLInputElement | null;
      this.searchTerm = target?.value || '';
      this.currentPage = 1; // Reset to first page when searching
      this.renderProducts();
      this.renderSuggestions();
    });
    this.searchInput?.addEventListener('focus', () => {
      this.renderSuggestions();
    });
    this.searchInput?.addEventListener('blur', () => {
      window.setTimeout(() => this.hideSuggestions(), 200);
    });
    this.filtersEl?.addEventListener('click', (event) => {
      const button = (event.target as HTMLElement).closest<HTMLButtonElement>('[data-category]');
      if (!button) return;
      const category = button.dataset.category || 'all';
      this.handleCategoryChange(category);
    });
  }

  private async loadRecommendations(): Promise<void> {
    if (this.isLoading) return;

    this.isLoading = true;
    const TIMEOUT_MS = 5000; // 5 segundos máximo

    try {
      // Clear any existing timeout
      if (this.loadingTimeout) {
        window.clearTimeout(this.loadingTimeout);
      }

      // Create timeout promise
      const timeoutPromise = new Promise<never>((_, reject) => {
        this.loadingTimeout = window.setTimeout(() => {
          reject(new Error('Tiempo de espera agotado (5s). Por favor, intenta de nuevo.'));
        }, TIMEOUT_MS);
      });

      // Race between fetch and timeout
      const response = await Promise.race([
        fetch('/api/menu-items/recommendations'),
        timeoutPromise,
      ]);

      // Clear timeout on success
      if (this.loadingTimeout) {
        window.clearTimeout(this.loadingTimeout);
        this.loadingTimeout = null;
      }

      const result = await response.json();
      if (result.status !== 'success')
        throw new Error(result.message || 'Error al cargar productos');

      const items: RecommendationItem[] = [];
      (result.data.categories || []).forEach((category: any) => {
        (category.items || []).forEach((item: any) => {
          items.push({
            id: item.id,
            name: item.name,
            description: item.description,
            price: item.price,
            category_id: category.id,
            category_name: category.name,
            recommendation_periods: item.recommendation_periods || [],
          });
        });
      });
      this.recommendations = items;
      this.renderAllPeriods();
      this.renderFilterChips();
    } catch (error) {
      this.showFeedback((error as Error).message, 'error');
    } finally {
      this.isLoading = false;
      if (this.loadingTimeout) {
        window.clearTimeout(this.loadingTimeout);
        this.loadingTimeout = null;
      }
    }
  }

  private async loadPopularItems(): Promise<void> {
    try {
      const response = await fetch('/api/menu-items/popular?days=30&limit=10');
      const result = await response.json();
      if (result.status === 'success') {
        this.popularItems = result.data.popular_items || [];
      }
    } catch (error) {
      console.error('Error loading popular items:', error);
    }
  }

  private renderAllPeriods(): void {
    this.dayPeriods.forEach((period) => this.renderPeriodRecommendations(period.key));
  }

  private renderPeriodRecommendations(periodKey: string): void {
    const container = document.getElementById(`${periodKey}-recommendations`);
    const countEl = document.getElementById(`${periodKey}-count`);
    if (!container || !countEl) return;
    const recommended = this.recommendations.filter((item) =>
      (item.recommendation_periods || []).includes(periodKey)
    );
    countEl.textContent = `${recommended.length}/${MAX_RECOMMENDATIONS}`;
    if (!recommended.length) {
      const periodName = this.dayPeriodMap.get(periodKey)?.name || periodKey;
      container.innerHTML = `<p class="empty-recommendations">No hay productos recomendados para ${periodName.toLowerCase()}</p>`;
      return;
    }
    container.innerHTML = recommended
      .map(
        (item, index) => `
                <div class="recommendation-item"
                     data-item-id="${item.id}"
                     data-period="${periodKey}"
                     data-index="${index}"
                     draggable="true">
                    <div class="recommendation-item__drag-handle" title="Arrastrar para reordenar">
                        ⋮⋮
                    </div>
                    <div class="recommendation-item__info">
                        <h4>${item.name}</h4>
                        <p>${item.category_name || 'Sin categoría'}</p>
                    </div>
                    <span class="recommendation-item__price">${this.formatPrice(item.price)}</span>
                    <button class="recommendation-item__remove" data-action="remove" data-item-id="${item.id}" data-period="${periodKey}">
                        ✕ Quitar
                    </button>
                </div>`
      )
      .join('');

    // Add remove button listeners
    container.querySelectorAll<HTMLButtonElement>('[data-action="remove"]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = Number(btn.dataset.itemId);
        const period = btn.dataset.period || '';
        void this.removeRecommendation(id, period);
      });
    });

    // Add drag-and-drop listeners
    this.attachDragAndDropListeners(container, periodKey);
  }

  private attachDragAndDropListeners(container: HTMLElement, periodKey: string): void {
    let draggedElement: HTMLElement | null = null;

    container.querySelectorAll<HTMLElement>('.recommendation-item').forEach((item) => {
      item.addEventListener('dragstart', (e) => {
        draggedElement = item;
        item.classList.add('dragging');
        if (e.dataTransfer) {
          e.dataTransfer.effectAllowed = 'move';
        }
      });

      item.addEventListener('dragend', () => {
        item.classList.remove('dragging');
        draggedElement = null;
      });

      item.addEventListener('dragover', (e) => {
        e.preventDefault();
        if (e.dataTransfer) {
          e.dataTransfer.dropEffect = 'move';
        }

        if (!draggedElement || draggedElement === item) return;

        const afterElement = this.getDragAfterElement(container, e.clientY);
        if (afterElement === null) {
          container.appendChild(draggedElement);
        } else {
          container.insertBefore(draggedElement, afterElement);
        }
      });

      item.addEventListener('drop', (e) => {
        e.preventDefault();
        void this.saveRecommendationOrder(periodKey);
      });
    });
  }

  private getDragAfterElement(container: HTMLElement, y: number): HTMLElement | null {
    const draggableElements = [
      ...container.querySelectorAll<HTMLElement>('.recommendation-item:not(.dragging)'),
    ];

    return draggableElements.reduce<{ offset: number; element: HTMLElement | null }>(
      (closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;

        if (offset < 0 && offset > closest.offset) {
          return { offset: offset, element: child };
        } else {
          return closest;
        }
      },
      { offset: Number.NEGATIVE_INFINITY, element: null }
    ).element;
  }

  private async saveRecommendationOrder(periodKey: string): Promise<void> {
    const container = document.getElementById(`${periodKey}-recommendations`);
    if (!container) return;

    const items = Array.from(container.querySelectorAll<HTMLElement>('.recommendation-item'));
    const itemIds = items.map((item) => Number(item.dataset.itemId));

    // Update local order
    this.displayOrder = itemIds;

    // Here you could save the order to the backend
    // For now, we'll just show a success message
    this.showFeedback('Orden actualizado', 'success');
  }

  private renderFilterChips(): void {
    if (!this.filtersEl) return;
    const categories = new Set<string>();
    this.recommendations.forEach((item) => {
      if (item.category_name) categories.add(item.category_name);
    });
    const chips = ['all', ...Array.from(categories)].map((category) => {
      const active = this.categoryFilter === category;
      const label = category === 'all' ? 'Todos' : category;
      return `<button type="button" class="filter-chip ${active ? 'active' : ''}" data-category="${category}">${label}</button>`;
    });
    this.filtersEl.innerHTML = chips.join('');
  }

  private renderProducts(): void {
    if (!this.productsListEl || !this.currentPeriod) return;

    // Filter items
    const allItems = this.recommendations
      .filter((item) => !(item.recommendation_periods || []).includes(this.currentPeriod!))
      .filter((item) =>
        this.categoryFilter === 'all' ? true : item.category_name === this.categoryFilter
      )
      .filter((item) => {
        if (!this.searchTerm) return true;
        const term = this.searchTerm.toLowerCase();
        return (
          item.name.toLowerCase().includes(term) ||
          (item.category_name || '').toLowerCase().includes(term)
        );
      });

    if (!allItems.length) {
      this.productsListEl.innerHTML =
        '<p style="text-align:center;padding:2rem;color:#94a3b8;">No se encontraron productos</p>';
      if (this.paginationEl) this.paginationEl.innerHTML = '';
      return;
    }

    // Show popular suggestions if no search term
    let popularSuggestions = '';
    if (!this.searchTerm && this.popularItems.length > 0) {
      const suggestedItems = this.popularItems
        .filter(
          (item) =>
            !(
              this.recommendations.find((r) => r.id === item.id)?.recommendation_periods || []
            ).includes(this.currentPeriod!)
        )
        .slice(0, 3);

      if (suggestedItems.length > 0) {
        popularSuggestions = `
                    <div class="popular-suggestions">
                        <h4 class="popular-suggestions__title">💡 Sugerencias populares</h4>
                        <div class="popular-suggestions__list">
                            ${suggestedItems
                              .map(
                                (item) => `
                                <article class="recommendation-product-option recommendation-product-option--popular" data-action="select" data-item-id="${item.id}">
                                    <div class="recommendation-product-option__badge">🔥 Popular</div>
                                    <div class="recommendation-product-option__info">
                                        <h4>${item.name}</h4>
                                        <p>${item.category_name || 'Sin categoría'} • ${item.total_quantity} vendidos</p>
                                    </div>
                                    <div class="recommendation-product-option__meta">
                                        <span class="recommendation-product-option__price">${this.formatPrice(item.price)}</span>
                                        <button class="btn btn--primary btn--small" type="button" data-action="select" data-item-id="${item.id}">
                                            Agregar
                                        </button>
                                    </div>
                                </article>
                            `
                              )
                              .join('')}
                        </div>
                    </div>
                `;
      }
    }

    // Pagination
    const totalPages = Math.ceil(allItems.length / this.itemsPerPage);
    const startIndex = (this.currentPage - 1) * this.itemsPerPage;
    const endIndex = startIndex + this.itemsPerPage;
    const items = allItems.slice(startIndex, endIndex);

    // Render items
    const productsHTML = items
      .map(
        (item) => `
                <article class="recommendation-product-option" data-action="select" data-item-id="${item.id}">
                    <div class="recommendation-product-option__info">
                        <h4>${item.name}</h4>
                        <p>${item.category_name || 'Sin categoría'}</p>
                    </div>
                    <div class="recommendation-product-option__meta">
                        <span class="recommendation-product-option__price">${this.formatPrice(item.price)}</span>
                        <button class="btn btn--primary btn--small" type="button" data-action="select" data-item-id="${item.id}">
                            Agregar
                        </button>
                    </div>
                </article>`
      )
      .join('');

    this.productsListEl.innerHTML = popularSuggestions + productsHTML;

    // Render pagination
    this.renderPagination(totalPages, allItems.length);

    // Add event listeners
    this.productsListEl
      .querySelectorAll<HTMLButtonElement>('[data-action="select"]')
      .forEach((btn) => {
        btn.addEventListener('click', () => {
          const id = Number(btn.dataset.itemId);
          void this.handleSelectProduct(id);
        });
      });
  }

  private renderPagination(totalPages: number, totalItems: number): void {
    if (!this.paginationEl || totalPages <= 1) {
      if (this.paginationEl) this.paginationEl.innerHTML = '';
      return;
    }

    const pages: string[] = [];

    // Previous button
    if (this.currentPage > 1) {
      pages.push(
        `<button class="pagination-btn" data-page="${this.currentPage - 1}">← Anterior</button>`
      );
    }

    // Page numbers
    for (let i = 1; i <= totalPages; i++) {
      if (i === 1 || i === totalPages || (i >= this.currentPage - 1 && i <= this.currentPage + 1)) {
        const active = i === this.currentPage ? 'active' : '';
        pages.push(`<button class="pagination-btn ${active}" data-page="${i}">${i}</button>`);
      } else if (i === this.currentPage - 2 || i === this.currentPage + 2) {
        pages.push(`<span class="pagination-ellipsis">...</span>`);
      }
    }

    // Next button
    if (this.currentPage < totalPages) {
      pages.push(
        `<button class="pagination-btn" data-page="${this.currentPage + 1}">Siguiente →</button>`
      );
    }

    // Info text
    const startItem = (this.currentPage - 1) * this.itemsPerPage + 1;
    const endItem = Math.min(this.currentPage * this.itemsPerPage, totalItems);

    this.paginationEl.innerHTML = `
            <div class="pagination-container">
                <div class="pagination-info">
                    Mostrando ${startItem}-${endItem} de ${totalItems} productos
                </div>
                <div class="pagination-buttons">
                    ${pages.join('')}
                </div>
            </div>
        `;

    // Add event listeners for pagination buttons
    this.paginationEl.querySelectorAll<HTMLButtonElement>('[data-page]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const page = Number(btn.dataset.page);
        if (page && page !== this.currentPage) {
          this.currentPage = page;
          this.renderProducts();
        }
      });
    });
  }

  private renderSuggestions(): void {
    if (!this.suggestionsEl || !this.searchTerm) {
      this.hideSuggestions();
      return;
    }
    const term = this.searchTerm.toLowerCase();
    const suggestions = this.recommendations
      .filter((item) => item.name.toLowerCase().includes(term))
      .slice(0, 5);
    if (!suggestions.length) {
      this.hideSuggestions();
      return;
    }
    this.suggestionsEl.innerHTML = suggestions
      .map((item) => `<button type="button" data-suggestion="${item.name}">${item.name}</button>`)
      .join('');
    this.suggestionsEl.style.display = 'block';
    this.suggestionsEl.querySelectorAll<HTMLButtonElement>('[data-suggestion]').forEach((btn) =>
      btn.addEventListener('click', () => {
        const value = btn.dataset.suggestion || '';
        if (this.searchInput) this.searchInput.value = value;
        this.searchTerm = value;
        this.renderProducts();
        this.hideSuggestions();
      })
    );
  }

  private hideSuggestions(): void {
    if (this.suggestionsEl) this.suggestionsEl.style.display = 'none';
  }

  private openModal(periodKey: string): void {
    this.currentPeriod = periodKey;
    const recommended = this.recommendations.filter((item) =>
      (item.recommendation_periods || []).includes(periodKey)
    );
    if (recommended.length >= MAX_RECOMMENDATIONS) {
      this.showFeedback(
        `Ya tienes ${MAX_RECOMMENDATIONS} recomendaciones para este periodo`,
        'warning'
      );
      return;
    }
    const titleEl = document.getElementById('select-recommendation-title');
    const periodName = this.dayPeriodMap.get(periodKey)?.name || periodKey;
    if (titleEl) titleEl.textContent = `Agregar a ${periodName}`;
    this.categoryFilter = 'all';
    this.searchTerm = '';
    this.currentPage = 1; // Reset pagination
    if (this.searchInput) this.searchInput.value = '';
    this.renderFilterChips();
    this.renderProducts();
    this.modal?.classList.add('active');
  }

  private closeModal(): void {
    this.modal?.classList.remove('active');
    this.currentPeriod = null;
  }

  private handleCategoryChange(category: string): void {
    this.categoryFilter = category;
    this.currentPage = 1; // Reset to first page when changing category
    if (this.filtersEl) {
      this.filtersEl.querySelectorAll('[data-category]').forEach((btn) => {
        btn.classList.toggle(
          'active',
          btn instanceof HTMLElement && btn.dataset.category === category
        );
      });
    }
    this.renderProducts();
  }

  private async handleSelectProduct(itemId: number): Promise<void> {
    if (!this.currentPeriod) return;
    try {
      const response = await fetch(`/api/menu-items/${itemId}/recommendations`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period_key: this.currentPeriod, enabled: true }),
      });
      const result = await response.json();
      if (result.status !== 'success')
        throw new Error(result.message || 'Error al agregar recomendación');
      const item = this.recommendations.find((target) => target.id === itemId);
      if (item) {
        const periods = new Set(item.recommendation_periods || []);
        periods.add(this.currentPeriod);
        item.recommendation_periods = Array.from(periods);
      }
      this.renderPeriodRecommendations(this.currentPeriod);
      this.closeModal();
      this.showFeedback('Producto agregado a recomendaciones', 'success');
    } catch (error) {
      this.showFeedback((error as Error).message, 'error');
    }
  }

  private async removeRecommendation(itemId: number, periodKey: string): Promise<void> {
    const item = this.recommendations.find((target) => target.id === itemId);
    const itemName = item?.name || 'este producto';
    const periodName = this.dayPeriodMap.get(periodKey)?.name || periodKey;

    // Show confirmation dialog
    const confirmed = window.confirm(
      `¿Estás seguro de que deseas quitar "${itemName}" de las recomendaciones de ${periodName}?`
    );

    if (!confirmed) {
      return; // User cancelled
    }

    try {
      const response = await fetch(`/api/menu-items/${itemId}/recommendations`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period_key: periodKey, enabled: false }),
      });
      const result = await response.json();
      if (result.status !== 'success')
        throw new Error(result.message || 'Error al remover recomendación');

      if (item) {
        item.recommendation_periods = (item.recommendation_periods || []).filter(
          (key) => key !== periodKey
        );
      }
      this.renderPeriodRecommendations(periodKey);
      this.showFeedback('Producto removido de recomendaciones', 'info');
    } catch (error) {
      this.showFeedback((error as Error).message, 'error');
    }
  }

  private formatPrice(value?: number): string {
    const symbol = window.APP_SETTINGS?.currency_symbol || '$';
    const amount = Number(value) || 0;
    return `${symbol}${amount.toFixed(2)}`;
  }

  private showFeedback(message: string, type: 'info' | 'success' | 'warning' | 'error'): void {
    if (!this.feedbackEl) return;
    this.feedbackEl.textContent = message;
    this.feedbackEl.className = `feedback ${type}`;
    window.setTimeout(() => {
      if (this.feedbackEl) {
        this.feedbackEl.textContent = '';
        this.feedbackEl.className = 'feedback';
      }
    }, 3000);
  }

  private showClientMenuPreview(): void {
    const previewModal = document.getElementById('client-menu-preview-modal');
    if (!previewModal) {
      // Create modal if it doesn't exist
      this.createClientMenuPreviewModal();
      return this.showClientMenuPreview();
    }

    const previewContent = document.getElementById('client-menu-preview-content');
    if (!previewContent) return;

    // Generate preview HTML
    let html = '<div class="client-menu-preview">';

    this.dayPeriods.forEach((period) => {
      const recommended = this.recommendations.filter((item) =>
        (item.recommendation_periods || []).includes(period.key)
      );

      if (recommended.length > 0) {
        html += `
                    <div class="preview-period-section">
                        <h3 class="preview-period-title">
                            ${period.icon || '⭐'} ${period.name}
                        </h3>
                        <div class="preview-recommendations-grid">
                            ${recommended
                              .map(
                                (item) => `
                                <div class="preview-recommendation-card">
                                    <div class="preview-card-content">
                                        <h4 class="preview-item-name">${item.name}</h4>
                                        <p class="preview-item-description">${item.description || ''}</p>
                                        <span class="preview-item-price">${this.formatPrice(item.price)}</span>
                                    </div>
                                </div>
                            `
                              )
                              .join('')}
                        </div>
                    </div>
                `;
      }
    });

    html += '</div>';

    if (html === '<div class="client-menu-preview"></div>') {
      html = '<p class="preview-empty">No hay recomendaciones configuradas para ningún periodo</p>';
    }

    previewContent.innerHTML = html;
    previewModal.classList.add('active');
  }

  private createClientMenuPreviewModal(): void {
    const modalHTML = `
            <div id="client-menu-preview-modal" class="modal">
                <div class="modal-content modal-content--large">
                    <div class="modal-header">
                        <h2>Vista Previa del Menú Cliente</h2>
                        <button type="button" class="modal-close" onclick="closeClientMenuPreview()">✕</button>
                    </div>
                    <div class="modal-body" id="client-menu-preview-content"></div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn--secondary" onclick="closeClientMenuPreview()">
                            Cerrar
                        </button>
                    </div>
                </div>
            </div>
        `;

    document.body.insertAdjacentHTML('beforeend', modalHTML);
  }

  private closeClientMenuPreview(): void {
    const previewModal = document.getElementById('client-menu-preview-modal');
    if (previewModal) {
      previewModal.classList.remove('active');
    }
  }
}

declare global {
  interface Window {
    APP_DATA?: {
      day_periods?: DayPeriod[];
    };
    APP_SETTINGS?: {
      currency_symbol?: string;
    };
    ProntoRecommendations?: RecommendationsManager;
    openAddRecommendationModal?: (periodKey: string) => void;
    closeSelectRecommendationModal?: () => void;
    filterRecommendationsByCategory?: (category: string) => void;
    selectRecommendationProduct?: (itemId: number) => void;
    removeRecommendation?: (itemId: number, periodKey: string) => void;
    previewClientMenu?: () => void;
    closeClientMenuPreview?: () => void;
    activateSection?: (sectionId: string) => void;
  }
}
