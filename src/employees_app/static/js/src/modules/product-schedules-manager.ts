import { requestJSON } from '../core/http';

interface MenuCategory {
    id: number;
    name: string;
    items: Array<{ id: number; name: string }>;
}

interface MenuResponse {
    status: string;
    data: {
        categories: MenuCategory[];
    };
}

interface Schedule {
    id: number;
    day_name?: string;
    day_of_week?: number | null;
    start_time?: string | null;
    end_time?: string | null;
    is_active?: boolean;
}

interface ScheduleResponse {
    status: string;
    data: {
        schedules: Schedule[];
    };
}

export function initProductSchedulesManager(): void {
    document.addEventListener('DOMContentLoaded', () => {
        const root = document.querySelector<HTMLElement>('[data-schedules-root]');
        if (!root) return;
        const manager = new ProductSchedulesManager(root);
        manager.initialize();
        window.ProntoSchedules = manager;
        window.deleteSchedule = (scheduleId: number) => manager.deleteSchedule(scheduleId);
    });
}

class ProductSchedulesManager {
    private root: HTMLElement;
    private select: HTMLSelectElement | null;
    private list: HTMLElement | null;
    private formContainer: HTMLElement | null;
    private form: HTMLFormElement | null;
    private feedback: HTMLElement | null;
    private items: Array<{ id: number; label: string }> = [];
    private currentProductId: number | null = null;

    constructor(root: HTMLElement) {
        this.root = root;
        this.select = root.querySelector<HTMLSelectElement>('#schedule-product-select');
        this.list = root.querySelector<HTMLElement>('#schedules-list');
        this.formContainer = root.querySelector<HTMLElement>('#schedule-form-container');
        this.form = root.querySelector<HTMLFormElement>('#schedule-form');
        this.feedback = root.querySelector<HTMLElement>('#schedules-feedback');
    }

    async initialize(): Promise<void> {
        this.attachEventListeners();
        await this.loadMenuItems();
    }

    private attachEventListeners(): void {
        this.select?.addEventListener('change', (event) => {
            const value = Number((event.target as HTMLSelectElement).value);
            if (!value) {
                this.currentProductId = null;
                this.formContainer?.setAttribute('style', 'display:none;');
                this.list && (this.list.innerHTML = '<p style="text-align:center;color:#94a3b8;">Selecciona un producto.</p>');
                return;
            }
            this.currentProductId = value;
            this.formContainer?.setAttribute('style', 'display:block;');
            void this.loadSchedules(value);
        });

        this.form?.addEventListener('submit', (event) => {
            event.preventDefault();
            void this.createSchedule();
        });

        this.list?.addEventListener('click', (event) => {
            const button = (event.target as HTMLElement)?.closest<HTMLButtonElement>('[data-schedule-delete]');
            if (!button) return;
            const id = Number(button.dataset.scheduleDelete);
            void this.deleteSchedule(id);
        });
    }

    private async loadMenuItems(): Promise<void> {
        if (!this.select) return;
        this.select.innerHTML = '<option value="">Cargando productos...</option>';
        try {
            const response = await requestJSON<MenuResponse>('/api/menu');
            const categories = response.data?.categories ?? [];
            this.items = categories.flatMap((category) =>
                category.items.map((item) => ({
                    id: item.id,
                    label: `${item.name} (${category.name})`
                }))
            );
            this.select.innerHTML = '<option value="">-- Selecciona un producto --</option>';
            this.items.forEach((item) => {
                const option = document.createElement('option');
                option.value = String(item.id);
                option.textContent = item.label;
                this.select?.appendChild(option);
            });
        } catch (error) {
            console.error('[Schedules] menu', error);
            this.select.innerHTML = '<option value="">Error al cargar menú</option>';
            this.showFeedback((error as Error).message || 'No se pudo cargar el menú', 'error');
        }
    }

    private async loadSchedules(productId: number): Promise<void> {
        if (!this.list) return;
        this.list.innerHTML = '<p style="text-align:center;color:#94a3b8;">Cargando horarios...</p>';
        try {
            const response = await requestJSON<ScheduleResponse>(`/api/menu-items/${productId}/schedules`);
            const schedules = response.data?.schedules ?? [];
            if (!schedules.length) {
                this.list.innerHTML =
                    '<p class="no-schedules">Sin horarios configurados. Este producto está disponible siempre.</p>';
                return;
            }
            this.list.innerHTML = schedules
                .map((schedule) => this.buildScheduleRow(schedule))
                .join('');
        } catch (error) {
            console.error('[Schedules] load', error);
            this.list.innerHTML =
                '<p style="text-align:center;color:#ef4444;">Error al cargar los horarios del producto.</p>';
            this.showFeedback((error as Error).message || 'No se pudieron cargar los horarios', 'error');
        }
    }

    private buildScheduleRow(schedule: Schedule): string {
        const dayText = schedule.day_name || this.dayName(schedule.day_of_week) || 'Todos los días';
        const timeText =
            schedule.start_time && schedule.end_time
                ? `${schedule.start_time} - ${schedule.end_time}`
                : 'Disponible todo el día';
        const status = schedule.is_active !== false;
        return `
            <article class="schedule-card" data-schedule-id="${schedule.id}">
                <div>
                    <strong>${dayText}</strong>
                    <p style="margin:0.25rem 0; color:#475569;">${timeText}</p>
                    <span class="schedule-status ${status ? 'active' : 'inactive'}">
                        ${status ? '✓ Activo' : '✗ Inactivo'}
                    </span>
                </div>
                <button type="button" class="btn btn--sm btn--danger" data-schedule-delete="${schedule.id}">
                    Eliminar
                </button>
            </article>`;
    }

    private dayName(day?: number | null): string | null {
        if (!day) return null;
        const map: Record<number, string> = {
            1: 'Lunes',
            2: 'Martes',
            3: 'Miércoles',
            4: 'Jueves',
            5: 'Viernes',
            6: 'Sábado',
            7: 'Domingo'
        };
        return map[day] || null;
    }

    private async createSchedule(): Promise<void> {
        if (!this.form || !this.currentProductId) {
            this.showFeedback('Selecciona un producto primero', 'warning');
            return;
        }
        const dayValue = (this.form.querySelector<HTMLSelectElement>('#schedule-day')?.value ?? '').trim();
        const startTime = this.form.querySelector<HTMLInputElement>('#schedule-start-time')?.value ?? '';
        const endTime = this.form.querySelector<HTMLInputElement>('#schedule-end-time')?.value ?? '';

        const payload = {
            menu_item_id: this.currentProductId,
            day_of_week: dayValue ? Number(dayValue) : null,
            start_time: startTime || null,
            end_time: endTime || null,
            is_active: true
        };

        try {
            await requestJSON('/api/product-schedules', {
                method: 'POST',
                body: payload
            });
            this.showFeedback('Horario agregado exitosamente', 'success');
            this.form.reset();
            await this.loadSchedules(this.currentProductId);
        } catch (error) {
            console.error('[Schedules] create', error);
            this.showFeedback((error as Error).message || 'Error al crear horario', 'error');
        }
    }

    async deleteSchedule(scheduleId: number): Promise<void> {
        if (!scheduleId || !this.currentProductId) return;
        const confirmed = window.confirm('¿Eliminar este horario?');
        if (!confirmed) return;
        try {
            await requestJSON(`/api/product-schedules/${scheduleId}`, { method: 'DELETE' });
            this.showFeedback('Horario eliminado', 'success');
            await this.loadSchedules(this.currentProductId);
        } catch (error) {
            console.error('[Schedules] delete', error);
            this.showFeedback((error as Error).message || 'Error al eliminar horario', 'error');
        }
    }

    private showFeedback(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info'): void {
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
        ProntoSchedules?: ProductSchedulesManager;
        deleteSchedule?: (scheduleId: number) => void;
    }
}
