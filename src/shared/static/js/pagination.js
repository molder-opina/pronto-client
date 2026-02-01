/**
 * Generic Pagination Manager
 * Reusable component for paginating any list of items
 * With items-per-page selector and localStorage persistence
 */

// Constants for items per page options
const ITEMS_PER_PAGE_OPTIONS = [10, 20, 50, 100];
const GLOBAL_STORAGE_KEY = 'pronto_items_per_page';

/**
 * Get saved items per page from localStorage
 */
function getSavedItemsPerPage(storageKey) {
    try {
        // First check section-specific preference
        if (storageKey) {
            const sectionPref = localStorage.getItem(`${GLOBAL_STORAGE_KEY}_${storageKey}`);
            if (sectionPref) {
                const value = parseInt(sectionPref, 10);
                if (ITEMS_PER_PAGE_OPTIONS.includes(value)) {
                    return value;
                }
            }
        }
        // Fall back to global preference
        const globalPref = localStorage.getItem(GLOBAL_STORAGE_KEY);
        if (globalPref) {
            const value = parseInt(globalPref, 10);
            if (ITEMS_PER_PAGE_OPTIONS.includes(value)) {
                return value;
            }
        }
    } catch (e) { /* ignore */ }
    return (window.APP_CONFIG && window.APP_CONFIG.items_per_page) || 20;
}

/**
 * Save items per page to localStorage
 */
function saveItemsPerPage(value, storageKey) {
    try {
        localStorage.setItem(GLOBAL_STORAGE_KEY, String(value));
        if (storageKey) {
            localStorage.setItem(`${GLOBAL_STORAGE_KEY}_${storageKey}`, String(value));
        }
    } catch (e) { /* ignore */ }
}

class PaginationManager {
    constructor(options) {
        this.container = options.container; // DOM element for pagination controls
        this.storageKey = options.storageKey || null; // Key for localStorage persistence
        this.showItemsPerPage = options.showItemsPerPage !== false; // Show selector by default

        // Use saved preference, configured items per page, or from options, or default to 20
        const savedItemsPerPage = getSavedItemsPerPage(this.storageKey);
        this.itemsPerPage = options.itemsPerPage || savedItemsPerPage;

        this.currentPage = 1;
        this.totalItems = 0;
        this.onPageChange = options.onPageChange || (() => {});
        this.onItemsPerPageChange = options.onItemsPerPageChange || (() => {});

        // Customizable labels
        this.labels = {
            previous: options.labels?.previous || '‹ Anterior',
            next: options.labels?.next || 'Siguiente ›',
            showing: options.labels?.showing || '',
            of: options.labels?.of || 'de',
            items: options.labels?.items || '',
            show: options.labels?.show || 'Mostrar:'
        };
    }

    /**
     * Update pagination state and re-render
     */
    update(totalItems, resetToFirstPage = false) {
        this.totalItems = totalItems;
        if (resetToFirstPage) {
            this.currentPage = 1;
        }
        this.render();
    }

    /**
     * Get current page data for slicing arrays
     */
    getCurrentPageData(items) {
        const startIndex = (this.currentPage - 1) * this.itemsPerPage;
        const endIndex = startIndex + this.itemsPerPage;
        return items.slice(startIndex, endIndex);
    }

    /**
     * Navigate to specific page
     */
    goToPage(page) {
        const totalPages = Math.ceil(this.totalItems / this.itemsPerPage);
        if (page < 1 || page > totalPages) return;

        this.currentPage = page;
        this.render();
        this.onPageChange(page);
    }

    /**
     * Change items per page
     */
    setItemsPerPage(value) {
        if (!ITEMS_PER_PAGE_OPTIONS.includes(value)) return;

        this.itemsPerPage = value;
        saveItemsPerPage(value, this.storageKey);
        this.currentPage = 1; // Reset to first page
        this.render();
        this.onItemsPerPageChange(value);
        this.onPageChange(1);
    }

    /**
     * Render pagination controls
     */
    render() {
        if (!this.container) return;

        const totalPages = Math.ceil(this.totalItems / this.itemsPerPage);
        const startItem = this.totalItems > 0 ? (this.currentPage - 1) * this.itemsPerPage + 1 : 0;
        const endItem = Math.min(this.currentPage * this.itemsPerPage, this.totalItems);

        // Items per page selector
        let itemsPerPageHtml = '';
        if (this.showItemsPerPage) {
            const options = ITEMS_PER_PAGE_OPTIONS.map(opt =>
                `<option value="${opt}" ${opt === this.itemsPerPage ? 'selected' : ''}>${opt}</option>`
            ).join('');

            itemsPerPageHtml = `
                <div class="pagination__per-page">
                    <label>${this.labels.show}</label>
                    <select class="pagination__select" onchange="window.paginationInstances['${this.container.id}'].setItemsPerPage(parseInt(this.value, 10))">
                        ${options}
                    </select>
                </div>
            `;
        }

        // Only show if there are items or we need the per-page selector
        if (this.totalItems === 0 && !this.showItemsPerPage) {
            this.container.innerHTML = '';
            return;
        }

        let html = `<div class="pagination">`;

        // Add items per page selector
        html += itemsPerPageHtml;

        // Add page controls if more than 1 page
        if (totalPages > 1) {
            html += `
                <div class="pagination__controls">
                    <button
                        class="pagination__btn pagination__btn--nav ${this.currentPage === 1 ? 'disabled' : ''}"
                        onclick="window.paginationInstances['${this.container.id}'].goToPage(${this.currentPage - 1})"
                        ${this.currentPage === 1 ? 'disabled' : ''}
                    >
                        ${this.labels.previous}
                    </button>
                    <div class="pagination__numbers">
                        ${this.renderPageButtons(totalPages)}
                    </div>
                    <button
                        class="pagination__btn pagination__btn--nav ${this.currentPage === totalPages ? 'disabled' : ''}"
                        onclick="window.paginationInstances['${this.container.id}'].goToPage(${this.currentPage + 1})"
                        ${this.currentPage === totalPages ? 'disabled' : ''}
                    >
                        ${this.labels.next}
                    </button>
                </div>
            `;
        }

        // Add info
        html += `
            <div class="pagination__info">
                ${startItem}-${endItem} ${this.labels.of} ${this.totalItems}
            </div>
        </div>`;

        this.container.innerHTML = html;
    }

    /**
     * Render page number buttons with ellipsis for many pages
     */
    renderPageButtons(totalPages) {
        let buttons = '';
        const maxVisible = 5;

        if (totalPages <= maxVisible) {
            // Show all pages
            for (let i = 1; i <= totalPages; i++) {
                buttons += this.createPageButton(i);
            }
        } else {
            // Show first, last, current and surrounding pages
            buttons += this.createPageButton(1);

            if (this.currentPage > 3) {
                buttons += '<span class="pagination__ellipsis">...</span>';
            }

            let start = Math.max(2, this.currentPage - 1);
            let end = Math.min(totalPages - 1, this.currentPage + 1);

            for (let i = start; i <= end; i++) {
                buttons += this.createPageButton(i);
            }

            if (this.currentPage < totalPages - 2) {
                buttons += '<span class="pagination__ellipsis">...</span>';
            }

            buttons += this.createPageButton(totalPages);
        }

        return buttons;
    }

    /**
     * Create a single page button
     */
    createPageButton(page) {
        const isActive = page === this.currentPage;
        return `
            <button
                class="pagination__btn ${isActive ? 'pagination__btn--active' : ''}"
                onclick="window.paginationInstances['${this.container.id}'].goToPage(${page})"
            >
                ${page}
            </button>
        `;
    }

    /**
     * Register this instance globally for onclick handlers
     */
    register() {
        if (!window.paginationInstances) {
            window.paginationInstances = {};
        }
        window.paginationInstances[this.container.id] = this;
    }
}

/**
 * Generic Search and Filter Manager
 * Handles text search with debouncing
 */
class SearchFilterManager {
    constructor(options) {
        this.input = options.input; // DOM input element
        this.onSearch = options.onSearch || (() => {});
        this.debounceTime = options.debounceTime || 300;
        this.searchFields = options.searchFields || ['name']; // Fields to search in
        this.debounceTimer = null;

        this.attachListeners();
    }

    /**
     * Attach event listeners to search input
     */
    attachListeners() {
        if (!this.input) return;

        this.input.addEventListener('input', (e) => {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = setTimeout(() => {
                this.onSearch(e.target.value.toLowerCase().trim());
            }, this.debounceTime);
        });
    }

    /**
     * Filter items based on search query
     */
    filterItems(items, query) {
        if (!query) return items;

        return items.filter(item => {
            return this.searchFields.some(field => {
                const value = this.getNestedValue(item, field);
                return value && value.toString().toLowerCase().includes(query);
            });
        });
    }

    /**
     * Get nested object value by path (e.g., 'user.name')
     */
    getNestedValue(obj, path) {
        return path.split('.').reduce((current, prop) => current?.[prop], obj);
    }

    /**
     * Reset search
     */
    reset() {
        if (this.input) {
            this.input.value = '';
            this.onSearch('');
        }
    }
}

/**
 * Generic Filter Manager
 * Handles checkbox and radio button filters
 */
class FilterManager {
    constructor(options) {
        this.filters = options.filters || {}; // { filterName: { type: 'checkbox|radio', values: [] } }
        this.onFilterChange = options.onFilterChange || (() => {});
        this.activeFilters = {};

        // Initialize active filters
        Object.keys(this.filters).forEach(filterName => {
            const filter = this.filters[filterName];
            this.activeFilters[filterName] = filter.type === 'checkbox' ? [] : 'all';
        });
    }

    /**
     * Attach listeners to filter elements
     */
    attachListeners(container) {
        if (!container) return;

        // Checkbox filters
        container.querySelectorAll('[data-filter-type="checkbox"]').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const filterName = e.target.dataset.filterName;
                const value = e.target.dataset.filterValue;

                if (e.target.checked) {
                    if (!this.activeFilters[filterName].includes(value)) {
                        this.activeFilters[filterName].push(value);
                    }
                } else {
                    this.activeFilters[filterName] = this.activeFilters[filterName].filter(v => v !== value);
                }

                this.onFilterChange(this.activeFilters);
            });
        });

        // Radio filters
        container.querySelectorAll('[data-filter-type="radio"]').forEach(radio => {
            radio.addEventListener('change', (e) => {
                const filterName = e.target.name;
                const value = e.target.value;

                this.activeFilters[filterName] = value;
                this.onFilterChange(this.activeFilters);
            });
        });
    }

    /**
     * Filter items based on active filters
     */
    filterItems(items, customFilterFn = null) {
        if (customFilterFn) {
            return customFilterFn(items, this.activeFilters);
        }

        return items.filter(item => {
            return Object.entries(this.activeFilters).every(([filterName, filterValue]) => {
                const filter = this.filters[filterName];

                if (filter.type === 'checkbox') {
                    // If no checkboxes selected, show all
                    if (filterValue.length === 0) return true;
                    // Check if item matches any selected checkbox value
                    return filterValue.some(value => this.matchesFilter(item, filterName, value));
                } else if (filter.type === 'radio') {
                    // If 'all' selected, show all
                    if (filterValue === 'all') return true;
                    return this.matchesFilter(item, filterName, filterValue);
                }

                return true;
            });
        });
    }

    /**
     * Check if item matches a filter value
     * Override this method for custom matching logic
     */
    matchesFilter(item, filterName, value) {
        return item[filterName] === value;
    }

    /**
     * Reset all filters
     */
    reset() {
        Object.keys(this.filters).forEach(filterName => {
            const filter = this.filters[filterName];
            this.activeFilters[filterName] = filter.type === 'checkbox' ? [] : 'all';
        });

        this.onFilterChange(this.activeFilters);
    }

    /**
     * Get active filters
     */
    getActiveFilters() {
        return { ...this.activeFilters };
    }
}

// Export for use in other files
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { PaginationManager, SearchFilterManager, FilterManager };
}
