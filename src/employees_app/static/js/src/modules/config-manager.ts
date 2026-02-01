interface ConfigRecord {
    id: number;
    config_key: string;
    category: string;
    display_name: string;
    description?: string | null;
    value_type: 'bool' | 'int' | 'float' | 'string' | 'json' | 'select';
    raw_value?: string | null;
    value?: boolean | number | string | null;
    min_value?: number | null;
    max_value?: number | null;
    unit?: string | null;
}

type CategoryMap = Record<string, ConfigRecord[]>;

const CATEGORY_NAMES: Record<string, string> = {
    notifications: '🔔 Notificaciones',
    orders: '📋 Órdenes',
    payments: '💰 Pagos',
    sessions: '🪑 Sesiones',
    kitchen: '👨‍🍳 Cocina',
    general: '⚙️ General',
    customers: '👥 Clientes',
    security: '🔒 Seguridad',
    advanced: '⚙️ Parámetros Avanzados'
};

export function initConfigManager(): void {
    document.addEventListener('DOMContentLoaded', () => {
        const root = document.querySelector<HTMLElement>('[data-config-root]');
        if (!root) return;
        const manager = new ConfigManager(root);
        manager.initialize();
        window.ProntoConfig = {
            reload: () => manager.reload()
        };
    });
}

class ConfigManager {
    private container: HTMLElement;
    private configs: ConfigRecord[] = [];

    constructor(root: HTMLElement) {
        this.container = root;
    }

    initialize(): void {
        this.attachEvents();
        void this.loadConfigs();
    }

    async reload(): Promise<void> {
        await this.loadConfigs();
    }

    private attachEvents(): void {
        this.container.addEventListener('click', (event) => {
            const target = (event.target as HTMLElement).closest<HTMLButtonElement>('.save-config');
            if (!target) return;
            const configId = Number(target.dataset.configId);
            if (!configId) return;
            void this.handleSave(configId, target);
        });
    }

    private async loadConfigs(): Promise<void> {
        const loader = window.EmployeeLoading || window.GlobalLoading;
        loader?.start?.();
        this.container.innerHTML = '<p class="loading">Cargando parámetros...</p>';
        try {
            const response = await fetch('/api/config');
            if (!response.ok) throw new Error('Error al cargar configuración');
            const data = await response.json();
            this.configs = data.configs || [];
            this.render();
        } catch (error) {
            this.container.innerHTML = `<p class="error">Error: ${(error as Error).message}</p>`;
        } finally {
            loader?.stop?.();
        }
    }

    private render(): void {
        if (!this.configs.length) {
            this.container.innerHTML = '<p>No hay parámetros configurados</p>';
            return;
        }

        const grouped = this.groupByCategory(this.configs);
        this.container.innerHTML = Object.entries(grouped)
            .map(([category, items]) => this.renderCategory(category, items))
            .join('');
    }

    private groupByCategory(configs: ConfigRecord[]): CategoryMap {
        return configs.reduce<CategoryMap>((acc, config) => {
            if (!acc[config.category]) {
                acc[config.category] = [];
            }
            acc[config.category].push(config);
            return acc;
        }, {});
    }

    private renderCategory(category: string, items: ConfigRecord[]): string {
        const title = CATEGORY_NAMES[category] || category;
        const cards = items.map((item) => this.renderConfigItem(item)).join('');
        return `
            <div class="config-category">
                <h3 class="config-category__title">${title}</h3>
                <div class="config-items">${cards}</div>
            </div>`;
    }

    private renderConfigItem(config: ConfigRecord): string {
        return `
            <div class="config-item" data-config-id="${config.id}">
                <div class="config-item__info">
                    <h4>${config.display_name}</h4>
                    <p>${config.description || ''}</p>
                    <small class="config-item__meta">
                        ${config.min_value !== null && config.min_value !== undefined ? `Min: ${config.min_value}` : ''}
                        ${
                            config.max_value !== null && config.max_value !== undefined
                                ? ` | Max: ${config.max_value}`
                                : ''
                        }
                        ${config.unit ? ` | Unidad: ${config.unit}` : ''}
                    </small>
                </div>
                <div class="config-item__control">
                    ${this.renderInput(config)}
                    <button type="button" class="btn btn--small btn--primary save-config" data-config-id="${config.id}">
                        Guardar
                    </button>
                </div>
                <span class="config-feedback" data-feedback-id="${config.id}"></span>
            </div>`;
    }

    private renderInput(config: ConfigRecord): string {
        const dataAttr = `data-config-input="${config.id}" data-value-type="${config.value_type}"`;
        switch (config.value_type) {
            case 'bool':
                return `<input type="checkbox" class="config-input" ${dataAttr} ${
                    config.value ? 'checked' : ''
                }>`;
            case 'json':
                return `<textarea class="config-input" rows="4" ${dataAttr}>${config.raw_value || ''}</textarea>`;
            case 'select':
                if (config.config_key === 'items_per_page') {
                    const options = [10, 25, 50, 100];
                    const current = config.raw_value || '10';
                    return `<select class="config-input" ${dataAttr}>
                        ${options
                            .map((value) => `<option value="${value}" ${current == value ? 'selected' : ''}>${value}</option>`)
                            .join('')}
                    </select>`;
                }
                return `<input type="text" class="config-input" ${dataAttr} value="${config.raw_value ?? ''}">`;
            case 'int':
            case 'float': {
                const step = config.value_type === 'float' ? '0.1' : '1';
                const minAttr =
                    config.min_value !== undefined && config.min_value !== null ? `min="${config.min_value}"` : '';
                const maxAttr =
                    config.max_value !== undefined && config.max_value !== null ? `max="${config.max_value}"` : '';
                return `<input type="number" class="config-input" ${dataAttr} value="${config.raw_value ?? ''}" ${minAttr} ${maxAttr} step="${step}">`;
            }
            default:
                return `<input type="text" class="config-input" ${dataAttr} value="${config.raw_value ?? ''}">`;
        }
    }

    private async handleSave(configId: number, button: HTMLButtonElement): Promise<void> {
        const input = this.container.querySelector<HTMLElement>(`[data-config-input="${configId}"]`);
        const feedback = this.container.querySelector<HTMLElement>(`[data-feedback-id="${configId}"]`);
        if (!input || !feedback) return;

        const valueType = input.dataset.valueType || 'string';
        let value: string | boolean = '';
        try {
            value = this.extractValue(input, valueType);
        } catch (error) {
            feedback.textContent = (error as Error).message;
            feedback.classList.add('error');
            return;
        }

        button.disabled = true;
        feedback.textContent = 'Guardando...';
        feedback.classList.remove('error', 'success');

        try {
            const response = await fetch(`/api/config/${configId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value: value.toString() })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Error al guardar');
            feedback.textContent = '✓ Guardado';
            feedback.classList.add('success');
            setTimeout(() => {
                feedback.textContent = '';
                feedback.classList.remove('success');
            }, 2000);
        } catch (error) {
            feedback.textContent = (error as Error).message;
            feedback.classList.add('error');
        } finally {
            button.disabled = false;
        }
    }

    private extractValue(input: HTMLElement, valueType: string): string | boolean {
        if (valueType === 'bool') {
            return (input as HTMLInputElement).checked;
        }
        if (valueType === 'json') {
            const value = (input as HTMLTextAreaElement).value.trim();
            if (!value) return '';
            try {
                JSON.parse(value);
            } catch {
                throw new Error('JSON inválido');
            }
            return value;
        }
        return (input as HTMLInputElement).value;
    }
}

declare global {
    interface Window {
        ProntoConfig?: {
            reload: () => Promise<void>;
        };
    }
}
