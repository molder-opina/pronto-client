import { requestJSON } from '../core/http';

interface MenuCategory {
    id: number;
    name: string;
    items: Array<{
        id: number;
        name: string;
        preparation_time_minutes?: number;
    }>;
}

interface MenuResponse {
    status: string;
    data: {
        categories: MenuCategory[];
    };
}

interface PrepTimeItem {
    id: number;
    name: string;
    categoryId: number;
    categoryName: string;
    preparationTime: number;
}

type FeedbackType = 'success' | 'error' | 'warning' | 'info';

export function initPrepTimesManager(): void {
    document.addEventListener('DOMContentLoaded', () => {
        const root = document.querySelector<HTMLElement>('[data-prep-times-root]');
        if (!root) return;
        const manager = new PrepTimesManager(root);
        manager.initialize();
        window.ProntoPrepTimes = manager;
        window.updatePrepTime = (itemId: number) => manager.savePrepTime(itemId);
    });
}

class PrepTimesManager {
    private root: HTMLElement;
    private select: HTMLSelectElement | null;
    private tableBody: HTMLTableSectionElement | null;
    private feedback: HTMLElement | null;
    private items: PrepTimeItem[] = [];
    private categories: Array<{ id: number; name: string }> = [];

    constructor(root: HTMLElement) {
        this.root = root;
        this.select = root.querySelector<HTMLSelectElement>('#prep-category-filter');
        this.tableBody = root.querySelector<HTMLTableSectionElement>('#prep-times-table tbody');
        this.feedback = root.querySelector<HTMLElement>('#prep-times-feedback');
    }

    async initialize(): Promise<void> {
        this.attachEventListeners();
        await this.loadData();
    }

    private attachEventListeners(): void {
        this.select?.addEventListener('change', () => {
            this.renderTable();
        });

        this.tableBody?.addEventListener('click', (event) => {
            const button = (event.target as HTMLElement)?.closest<HTMLButtonElement>('[data-prep-save]');
            if (!button) return;
            const id = Number(button.dataset.prepSave);
            void this.savePrepTime(id);
        });
    }

    private async loadData(): Promise<void> {
        if (!this.tableBody) return;
        this.tableBody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align:center;">Cargando tiempos de preparación...</td>
            </tr>`;
        try {
            const response = await requestJSON<MenuResponse>('/api/menu');
            const categories = response.data?.categories ?? [];
            this.categories = categories.map((category) => ({
                id: category.id,
                name: category.name
            }));
            this.items = categories.flatMap((category) =>
                category.items.map((item) => ({
                    id: item.id,
                    name: item.name,
                    categoryId: category.id,
                    categoryName: category.name,
                    preparationTime: Number(item.preparation_time_minutes) || 15
                }))
            );
            this.populateCategoryFilter();
            this.renderTable();
        } catch (error) {
            console.error('[PrepTimes] load', error);
            this.tableBody.innerHTML = `
                <tr>
                    <td colspan="5" style="text-align:center;color:#ef4444;">
                        Error al cargar productos del menú
                    </td>
                </tr>`;
            this.showFeedback((error as Error).message || 'Error al cargar productos', 'error');
        }
    }

    private populateCategoryFilter(): void {
        if (!this.select) return;
        this.select.innerHTML = '<option value="">Todas las categorías</option>';
        this.categories.forEach((category) => {
            const option = document.createElement('option');
            option.value = String(category.id);
            option.textContent = category.name;
            this.select?.appendChild(option);
        });
    }

    private renderTable(): void {
        if (!this.tableBody) return;
        if (!this.items.length) {
            this.tableBody.innerHTML =
                '<tr><td colspan="5" style="text-align:center;">No hay productos para mostrar</td></tr>';
            return;
        }
        const selectedCategory = this.select?.value || '';
        const filtered = selectedCategory
            ? this.items.filter((item) => String(item.categoryId) === selectedCategory)
            : this.items;

        if (!filtered.length) {
            this.tableBody.innerHTML =
                '<tr><td colspan="5" style="text-align:center;">No hay productos para esta categoría</td></tr>';
            return;
        }

        this.tableBody.innerHTML = filtered
            .map(
                (item) => `
                <tr data-prep-id="${item.id}">
                    <td><strong>${item.name}</strong></td>
                    <td>${item.categoryName}</td>
                    <td><span class="current-time">${item.preparationTime} min</span></td>
                    <td>
                        <input
                            type="number"
                            class="prep-time-input filter-input"
                            data-prep-input="${item.id}"
                            min="0"
                            max="300"
                            value="${item.preparationTime}"
                            style="max-width: 110px;"
                        >
                    </td>
                    <td>
                        <button type="button" class="btn btn--sm btn--primary" data-prep-save="${item.id}">
                            Guardar
                        </button>
                    </td>
                </tr>`
            )
            .join('');
    }

    async savePrepTime(itemId: number): Promise<void> {
        if (!itemId) return;
        const input = this.root.querySelector<HTMLInputElement>(`[data-prep-input="${itemId}"]`);
        if (!input) {
            this.showFeedback('No se encontró el campo a actualizar', 'error');
            return;
        }
        const value = Number(input.value);
        if (Number.isNaN(value) || value < 0 || value > 300) {
            this.showFeedback('El tiempo debe estar entre 0 y 300 minutos', 'warning');
            return;
        }
        input.disabled = true;
        try {
            await requestJSON(`/api/menu-items/${itemId}/preparation-time`, {
                method: 'PATCH',
                body: { preparation_time_minutes: value }
            });
            const item = this.items.find((entry) => entry.id === itemId);
            if (item) {
                item.preparationTime = value;
            }
            const row = this.root.querySelector<HTMLTableRowElement>(`tr[data-prep-id="${itemId}"]`);
            row?.querySelector<HTMLElement>('.current-time')?.replaceChildren(document.createTextNode(`${value} min`));
            this.showFeedback('Tiempo actualizado correctamente', 'success');
            window.showToast?.('Tiempo de preparación actualizado', 'success');
        } catch (error) {
            console.error('[PrepTimes] save', error);
            this.showFeedback((error as Error).message || 'Error al actualizar tiempo', 'error');
        } finally {
            input.disabled = false;
        }
    }

    reload(): Promise<void> {
        return this.loadData();
    }

    private showFeedback(message: string, type: FeedbackType = 'info'): void {
        if (!this.feedback) return;
        this.feedback.textContent = message;
        this.feedback.className = `feedback ${type}`;
        setTimeout(() => {
            if (!this.feedback) return;
            this.feedback.textContent = '';
            this.feedback.className = 'feedback';
        }, 3000);
    }
}

declare global {
    interface Window {
        ProntoPrepTimes?: PrepTimesManager;
        updatePrepTime?: (itemId: number) => void;
    }
}
