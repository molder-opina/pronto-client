import { formatCurrency } from '../../../../../shared/static/js/src/modules/formatting';

interface ModifierOption {
    id: number;
    name: string;
    price?: number;
    is_available?: boolean;
    description?: string | null;
    order?: number;
}

interface ModifierGroup {
    id: number;
    name: string;
    description?: string | null;
    min_selection?: number;
    max_selection?: number;
    is_required?: boolean;
    order?: number;
    modifiers: ModifierOption[];
}

interface ModifiersState {
    currentPage: number;
    itemsPerPage: number;
    searchQuery: string;
    availabilityFilter: 'all' | 'available' | 'unavailable';
}

const ITEMS_PER_PAGE_OPTIONS = [10, 20, 50, 100];
const STORAGE_KEY = 'pronto_items_per_page_modifiers';

function getSavedItemsPerPage(): number {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const value = parseInt(saved, 10);
            if (ITEMS_PER_PAGE_OPTIONS.includes(value)) return value;
        }
        const global = localStorage.getItem('pronto_items_per_page');
        if (global) {
            const value = parseInt(global, 10);
            if (ITEMS_PER_PAGE_OPTIONS.includes(value)) return value;
        }
    } catch (e) { /* ignore */ }
    return Number(window.APP_CONFIG?.items_per_page) || 20;
}

function saveItemsPerPage(value: number): void {
    try {
        localStorage.setItem(STORAGE_KEY, String(value));
        localStorage.setItem('pronto_items_per_page', String(value));
    } catch (e) { /* ignore */ }
}

const ITEMS_PER_PAGE = getSavedItemsPerPage();

export function initModifiersManager(): void {
    document.addEventListener('DOMContentLoaded', () => {
        const root = document.querySelector<HTMLElement>('[data-modifiers-root]');
        if (!root) return;
        new ModifiersManager(root).initialize();
    });
}

class ModifiersManager {
    private root: HTMLElement;
    private groups: ModifierGroup[] = [];
    private state: ModifiersState = {
        currentPage: 1,
        itemsPerPage: ITEMS_PER_PAGE,
        searchQuery: '',
        availabilityFilter: 'all'
    };

    private listEl: HTMLElement | null;
    private countEl: HTMLElement | null;
    private paginationEl: HTMLElement | null;
    private searchInput: HTMLInputElement | null;
    private availabilityRadios: NodeListOf<HTMLInputElement>;

    private groupDrawer: HTMLElement | null;
    private groupForm: HTMLFormElement | null;
    private modifierDrawer: HTMLElement | null;
    private modifierForm: HTMLFormElement | null;
    private groupSelectorSection: HTMLElement | null;
    private groupSelector: HTMLElement | null;

    private editingGroupId: number | null = null;
    private editingModifierId: number | null = null;
    private currentGroupId: number | null = null;

    constructor(root: HTMLElement) {
        this.root = root;
        this.listEl = root.querySelector('#modifiers-groups-list');
        this.countEl = root.querySelector('#modifiers-count');
        this.paginationEl = root.querySelector('#modifiers-pagination');
        this.searchInput = root.querySelector('#modifiers-search');
        this.availabilityRadios = root.querySelectorAll<HTMLInputElement>('input[name="modifier-availability"]');
        this.groupDrawer = document.getElementById('modifier-group-drawer');
        this.groupForm = document.getElementById('modifier-group-form') as HTMLFormElement | null;
        this.modifierDrawer = document.getElementById('modifier-drawer');
        this.modifierForm = document.getElementById('modifier-form') as HTMLFormElement | null;
        this.groupSelectorSection = document.getElementById('modifier-group-selector-section');
        this.groupSelector = document.getElementById('modifier-group-selector');
    }

    initialize(): void {
        void this.loadGroups();
        this.attachFilters();
        this.attachForms();
    }

    private async loadGroups(): Promise<void> {
        try {
            (window.EmployeeLoading || window.GlobalLoading)?.start?.();
            const response = await fetch('/api/modifiers');
            const data = await response.json();
            this.groups = data.modifier_groups || [];
            this.render();
            this.renderGroupSelector();
        } catch (error) {
            console.error('[MODIFIERS] Error loading modifiers:', error);
            if (this.listEl) {
                this.listEl.innerHTML = '<p class="empty-state">Error al cargar aditamentos</p>';
            }
        } finally {
            (window.EmployeeLoading || window.GlobalLoading)?.stop?.();
        }
    }

    private attachFilters(): void {
        this.searchInput?.addEventListener('input', () => {
            this.state.searchQuery = this.searchInput?.value.trim().toLowerCase() || '';
            this.state.currentPage = 1;
            this.render();
        });
        this.availabilityRadios.forEach((radio) => {
            radio.addEventListener('change', () => {
                this.state.availabilityFilter = (radio.value as ModifiersState['availabilityFilter']) || 'all';
                this.state.currentPage = 1;
                this.render();
            });
        });
    }

    private attachForms(): void {
        const openGroupBtn = document.getElementById('create-modifier-group-btn');
        openGroupBtn?.addEventListener('click', () => this.openGroupDrawer());
        document.getElementById('close-modifier-group-drawer')?.addEventListener('click', () => this.closeGroupDrawer());
        document.getElementById('cancel-modifier-group-btn')?.addEventListener('click', () => this.closeGroupDrawer());
        this.groupDrawer?.addEventListener('click', (event) => {
            if (event.target === this.groupDrawer) {
                this.closeGroupDrawer();
            }
        });
        this.groupForm?.addEventListener('submit', (event) => {
            event.preventDefault();
            void this.handleGroupSubmit();
        });

        const openModifierBtn = document.getElementById('create-modifier-btn');
        openModifierBtn?.addEventListener('click', () => this.openModifierDrawer());
        document.getElementById('close-modifier-drawer')?.addEventListener('click', () => this.closeModifierDrawer());
        document.getElementById('cancel-modifier-btn')?.addEventListener('click', () => this.closeModifierDrawer());
        this.modifierDrawer?.addEventListener('click', (event) => {
            if (event.target === this.modifierDrawer) {
                this.closeModifierDrawer();
            }
        });
        this.modifierForm?.addEventListener('submit', (event) => {
            event.preventDefault();
            void this.handleModifierSubmit();
        });
    }

    private render(): void {
        if (!this.listEl) return;
        const filtered = this.filterGroups();
        if (this.countEl) {
            this.countEl.textContent = `${filtered.length} grupo${filtered.length === 1 ? '' : 's'} encontrados`;
        }
        if (filtered.length === 0) {
            this.listEl.innerHTML = '<p class="empty-state">No hay grupos de aditamentos.</p>';
            this.renderPagination(0, 0);
            return;
        }
        const totalPages = Math.ceil(filtered.length / this.state.itemsPerPage);
        const startIndex = (this.state.currentPage - 1) * this.state.itemsPerPage;
        const groups = filtered.slice(startIndex, startIndex + this.state.itemsPerPage);
        this.listEl.innerHTML = groups.map((group) => this.renderGroupCard(group)).join('');
        this.renderPagination(totalPages, filtered.length);
        this.listEl.querySelectorAll<HTMLButtonElement>('[data-group-action="edit"]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const id = Number(btn.dataset.groupId);
                const group = this.groups.find((g) => g.id === id);
                if (group) {
                    this.openGroupDrawer(group);
                }
            });
        });
    }

    private renderGroupCard(group: ModifierGroup): string {
        const modifiersHTML = group.modifiers.length
            ? `<div class="modifiers-list">
                    <div class="modifiers-list__header">
                        <h4 class="modifiers-list__title">Opciones disponibles</h4>
                        <span>${group.modifiers.length} opción${group.modifiers.length === 1 ? '' : 'es'}</span>
                    </div>
                    <div class="modifiers-list__grid">
                        ${group.modifiers
                            .map(
                                (mod) => `
                                    <article class="modifier-card" data-modifier-id="${mod.id}">
                                        <div class="modifier-card__main">
                                            <h5>${mod.name}</h5>
                                            <span>${formatCurrency(mod.price || 0)}</span>
                                        </div>
                                        <div class="modifier-card__meta">
                                            <span class="modifier-card__status ${mod.is_available ? 'available' : 'unavailable'}">
                                                ${mod.is_available ? 'Disponible' : 'Agotado'}
                                            </span>
                                            <small>Orden ${mod.order ?? 0}</small>
                                        </div>
                                    </article>`
                            )
                            .join('')}
                    </div>
                </div>`
            : '<p class="empty-state">Aún no hay modificadores en este grupo.</p>';
        return `
            <div class="modifier-group-card" data-group-id="${group.id}">
                <div class="modifier-group-card__header">
                    <div>
                        <h3 class="modifier-group-card__title">${group.name}</h3>
                        ${group.description ? `<p class="modifier-group-card__description">${group.description}</p>` : ''}
                        <div class="modifier-group-card__badges">
                            ${group.is_required ? '<span class="modifier-group-card__badge modifier-group-card__badge--required">⚠️ Requerido</span>' : ''}
                            <span class="modifier-group-card__badge">Min: ${group.min_selection ?? 0} | Max: ${group.max_selection ?? 1}</span>
                            <span class="modifier-group-card__badge">${group.modifiers.length} opción${group.modifiers.length === 1 ? '' : 'es'}</span>
                        </div>
                    </div>
                    <div class="modifier-group-card__actions">
                        <button type="button" class="btn btn--small btn--outline" data-group-action="edit" data-group-id="${group.id}">✏️ Editar</button>
                    </div>
                </div>
                ${modifiersHTML}
            </div>`;
    }

    private renderPagination(totalPages: number, totalItems: number): void {
        if (!this.paginationEl) return;

        const currentPage = this.state.currentPage;
        const itemsPerPage = this.state.itemsPerPage;
        const startItem = totalItems > 0 ? (currentPage - 1) * itemsPerPage + 1 : 0;
        const endItem = Math.min(currentPage * itemsPerPage, totalItems);

        // Items per page selector
        const perPageOptions = ITEMS_PER_PAGE_OPTIONS.map(opt =>
            `<option value="${opt}" ${opt === itemsPerPage ? 'selected' : ''}>${opt}</option>`
        ).join('');

        let html = `<div class="pagination">
            <div class="pagination__per-page">
                <label>Mostrar:</label>
                <select class="pagination__select" data-per-page-select>
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

            html += `<div class="pagination__controls">
                <button class="pagination__btn pagination__btn--nav ${currentPage === 1 ? 'disabled' : ''}" data-page="${currentPage - 1}" ${currentPage === 1 ? 'disabled' : ''}>‹ Anterior</button>
                <div class="pagination__numbers">`;

            if (startPage > 1) {
                html += `<button class="pagination__btn" data-page="1">1</button>`;
                if (startPage > 2) html += `<span class="pagination__ellipsis">...</span>`;
            }
            for (let i = startPage; i <= endPage; i += 1) {
                html += `<button class="pagination__btn ${i === currentPage ? 'pagination__btn--active' : ''}" data-page="${i}">${i}</button>`;
            }
            if (endPage < totalPages) {
                if (endPage < totalPages - 1) html += `<span class="pagination__ellipsis">...</span>`;
                html += `<button class="pagination__btn" data-page="${totalPages}">${totalPages}</button>`;
            }

            html += `</div>
                <button class="pagination__btn pagination__btn--nav ${currentPage === totalPages ? 'disabled' : ''}" data-page="${currentPage + 1}" ${currentPage === totalPages ? 'disabled' : ''}>Siguiente ›</button>
            </div>`;
        }

        html += `<div class="pagination__info">${startItem}-${endItem} de ${totalItems}</div></div>`;

        this.paginationEl.innerHTML = html;

        // Attach page button listeners
        this.paginationEl.querySelectorAll<HTMLButtonElement>('button[data-page]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const page = Number(btn.dataset.page);
                if (Number.isNaN(page)) return;
                this.state.currentPage = page;
                this.render();
                this.listEl?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
        });

        // Attach items per page listener
        const perPageSelect = this.paginationEl.querySelector<HTMLSelectElement>('[data-per-page-select]');
        perPageSelect?.addEventListener('change', () => {
            const newValue = parseInt(perPageSelect.value, 10);
            saveItemsPerPage(newValue);
            this.state.itemsPerPage = newValue;
            this.state.currentPage = 1;
            this.render();
        });
    }

    private filterGroups(): ModifierGroup[] {
        return this.groups
            .map((group) => {
                const filteredModifiers = group.modifiers.filter((mod) => {
                    const matchesSearch = this.state.searchQuery
                        ? mod.name.toLowerCase().includes(this.state.searchQuery)
                        : true;
                    const matchesAvailability =
                        this.state.availabilityFilter === 'all'
                            ? true
                            : this.state.availabilityFilter === 'available'
                            ? !!mod.is_available
                            : !mod.is_available;
                    return matchesSearch && matchesAvailability;
                });
                return { ...group, modifiers: filteredModifiers };
            })
            .filter((group) => group.modifiers.length || !this.state.searchQuery);
    }

    private openGroupDrawer(group?: ModifierGroup): void {
        this.editingGroupId = group ? group.id : null;
        this.groupForm?.reset();
        (document.getElementById('modifier-group-id') as HTMLInputElement | null)!.value = group?.id?.toString() || '';
        (document.getElementById('modifier-group-name') as HTMLInputElement | null)!.value = group?.name || '';
        (document.getElementById('modifier-group-description') as HTMLTextAreaElement | null)!.value = group?.description || '';
        (document.getElementById('modifier-group-min') as HTMLInputElement | null)!.value = String(group?.min_selection ?? 0);
        (document.getElementById('modifier-group-max') as HTMLInputElement | null)!.value = String(group?.max_selection ?? 1);
        (document.getElementById('modifier-group-required') as HTMLInputElement | null)!.checked = Boolean(group?.is_required);
        (document.getElementById('modifier-group-order') as HTMLInputElement | null)!.value = String(group?.order ?? 0);
        const title = document.getElementById('modifier-group-drawer-title');
        if (title) {
            title.textContent = group ? 'Editar grupo' : 'Nuevo grupo';
        }
        this.groupDrawer?.classList.add('active');
    }

    private closeGroupDrawer(): void {
        this.groupDrawer?.classList.remove('active');
        this.editingGroupId = null;
    }

    private async handleGroupSubmit(): Promise<void> {
        if (!this.groupForm) return;
        const formData = new FormData(this.groupForm);
        const payload = {
            name: (formData.get('name') as string).trim(),
            description: (formData.get('description') as string) || '',
            min_selection: Number(formData.get('min_selection') || 0),
            max_selection: Number(formData.get('max_selection') || 1),
            is_required: formData.get('is_required') === 'on',
            order: Number(formData.get('order') || 0)
        };
        if (!payload.name) {
            showToast('Ingresa un nombre para el grupo', 'warning');
            return;
        }
        if (payload.min_selection > payload.max_selection) {
            showToast('El mínimo no puede ser mayor que el máximo', 'warning');
            return;
        }
        const endpoint = this.editingGroupId ? `/api/modifiers/groups/${this.editingGroupId}` : '/api/modifiers/groups';
        const method = this.editingGroupId ? 'PUT' : 'POST';
        try {
            const response = await fetch(endpoint, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Error al guardar el grupo');
            showToast(this.editingGroupId ? 'Grupo actualizado' : 'Grupo creado', 'success');
            this.closeGroupDrawer();
            await this.loadGroups();
        } catch (error) {
            showToast((error as Error).message, 'error');
        }
    }

    private openModifierDrawer(modifier?: ModifierOption, group?: ModifierGroup): void {
        this.editingModifierId = modifier ? modifier.id : null;
        const form = this.modifierForm;
        if (!form) return;
        (document.getElementById('modifier-id') as HTMLInputElement | null)!.value = modifier?.id?.toString() || '';
        (document.getElementById('modifier-group-id-input') as HTMLInputElement | null)!.value = group?.id?.toString() || this.currentGroupId?.toString() || '';
        (document.getElementById('modifier-name') as HTMLInputElement | null)!.value = modifier?.name || '';
        (document.getElementById('modifier-price') as HTMLInputElement | null)!.value = String(modifier?.price ?? 0);
        (document.getElementById('modifier-order') as HTMLInputElement | null)!.value = String(modifier?.order ?? 0);
        (document.getElementById('modifier-available') as HTMLInputElement | null)!.checked = modifier ? !!modifier.is_available : true;
        const title = document.getElementById('modifier-drawer-title');
        if (title) {
            title.textContent = modifier ? 'Editar aditamento' : 'Nuevo aditamento';
        }
        if (this.groupSelectorSection) {
            this.groupSelectorSection.style.display = this.currentGroupId ? 'none' : 'block';
        }
        this.modifierDrawer?.classList.add('active');
    }

    private closeModifierDrawer(): void {
        this.modifierDrawer?.classList.remove('active');
        this.editingModifierId = null;
    }

    private renderGroupSelector(): void {
        if (!this.groupSelector) return;
        this.groupSelector.innerHTML = this.groups
            .map((group) => `
                <label class="group-selector-option">
                    <input type="checkbox" value="${group.id}">
                    <span>${group.name}</span>
                </label>`)
            .join('');
    }

    private async handleModifierSubmit(): Promise<void> {
        if (!this.modifierForm) return;
        const formData = new FormData(this.modifierForm);
        const payload = {
            name: (formData.get('name') as string).trim(),
            price: Number(formData.get('price') || 0),
            order: Number(formData.get('order') || 0),
            is_available: formData.get('is_available') === 'on',
            description: (formData.get('description') as string) || '',
            groups: formData.getAll('groups').map((value) => Number(value))
        };
        const groupId = formData.get('group_id');
        if (groupId) {
            payload.groups = [Number(groupId)];
        }
        if (!payload.name) {
            showToast('Ingresa un nombre para el aditamento', 'warning');
            return;
        }
        if (!payload.groups.length) {
            showToast('Selecciona al menos un grupo para este aditamento', 'warning');
            return;
        }
        const endpoint = this.editingModifierId ? `/api/modifiers/${this.editingModifierId}` : '/api/modifiers';
        const method = this.editingModifierId ? 'PUT' : 'POST';
        try {
            const response = await fetch(endpoint, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Error al guardar el aditamento');
            showToast(this.editingModifierId ? 'Aditamento actualizado' : 'Aditamento creado', 'success');
            this.closeModifierDrawer();
            await this.loadGroups();
        } catch (error) {
            showToast((error as Error).message, 'error');
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
