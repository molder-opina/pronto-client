interface AreaRecord {
    id: number;
    name: string;
    description?: string | null;
    color?: string | null;
    prefix?: string | null;
    tables_count?: number;
    background_image?: string | null;
}

const DEFAULT_COLOR = '#ff6b35';

if (!window.ProntoAreas) {
    window.ProntoAreas = {
        reload: async () => {},
        getAreas: () => []
    };
}

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

export function initAreasManager(): void {
    document.addEventListener('DOMContentLoaded', () => {
        const root = document.querySelector<HTMLElement>('[data-areas-root]');
        if (!root) {
            window.ProntoAreas = {
                reload: async () => {},
                getAreas: () => []
            };
            return;
        }

        const manager = new AreasManager(root);
        manager.initialize();

        window.ProntoAreas = {
            reload: () => manager.reload(),
            getAreas: () => manager.getAreas()
        };
    });
}

class AreasManager {
    private root: HTMLElement;
    private grid: HTMLElement | null;
    private openBtn: HTMLButtonElement | null;
    private modal: HTMLElement | null;
    private closeModalBtn: HTMLButtonElement | null;
    private cancelModalBtn: HTMLButtonElement | null;
    private form: HTMLFormElement | null;
    private titleEl: HTMLElement | null;
    private nameInput: HTMLInputElement | null;
    private descriptionInput: HTMLTextAreaElement | null;
    private colorInput: HTMLInputElement | null;
    private prefixInput: HTMLInputElement | null;
    private idInput: HTMLInputElement | null;
    private backgroundCanvas: HTMLCanvasElement | null;
    private backgroundCtx: CanvasRenderingContext2D | null = null;
    private clearCanvasBtn: HTMLButtonElement | null;
    private drawingMode: 'pen' | 'rect' | 'circle' | 'line' = 'pen';
    private drawingColor: string = '#475569';
    private isDrawing: boolean = false;
    private lastX: number = 0;
    private lastY: number = 0;
    private startX: number = 0;
    private startY: number = 0;

    private areas: AreaRecord[] = [];
    private editingId: number | null = null;

    constructor(root: HTMLElement) {
        this.root = root;
        this.grid = root.querySelector('#areas-grid');
        this.openBtn = root.querySelector('#open-area-modal');
        this.modal = document.getElementById('area-modal');
        this.closeModalBtn = document.getElementById('close-area-modal') as HTMLButtonElement | null;
        this.cancelModalBtn = document.getElementById('cancel-area') as HTMLButtonElement | null;
        this.form = document.getElementById('area-form') as HTMLFormElement | null;
        this.titleEl = document.getElementById('area-modal-title');
        this.nameInput = document.getElementById('area-name') as HTMLInputElement | null;
        this.descriptionInput = document.getElementById('area-description') as HTMLTextAreaElement | null;
        this.colorInput = document.getElementById('area-color') as HTMLInputElement | null;
        this.prefixInput = document.getElementById('area-prefix') as HTMLInputElement | null;
        this.idInput = document.getElementById('area-id') as HTMLInputElement | null;
        this.backgroundCanvas = document.getElementById('area-background-canvas') as HTMLCanvasElement | null;
        this.clearCanvasBtn = document.getElementById('clear-canvas-btn') as HTMLButtonElement | null;

        if (this.backgroundCanvas) {
            this.backgroundCtx = this.backgroundCanvas.getContext('2d');
        }
    }

    initialize(): void {
        this.attachEvents();
        void this.reload();
    }

    async reload(): Promise<void> {
        await this.loadAreas();
    }

    getAreas(): AreaRecord[] {
        return [...this.areas];
    }

    private getDefaultPrefix(name?: string | null, prefix?: string | null): string {
        const clean = (prefix || '').trim();
        if (clean) return clean.charAt(0).toUpperCase();
        const source = (name || '').trim();
        if (!source) return '';
        const normalized = source.toLowerCase();
        if (normalized.includes('vip')) return 'V';
        if (normalized.includes('roof')) return 'R';
        if (normalized.includes('terraza') || normalized.includes('terrace')) return 'T';
        if (normalized.includes('bar') || normalized.includes('barra')) return 'B';
        if (normalized.includes('interior') || normalized.includes('salon') || normalized.includes('comedor')) return 'I';
        return source.charAt(0).toUpperCase();
    }

    private attachEvents(): void {
        this.openBtn?.addEventListener('click', () => this.openModal());
        this.closeModalBtn?.addEventListener('click', () => this.closeModal());
        this.cancelModalBtn?.addEventListener('click', () => this.closeModal());
        this.modal?.addEventListener('click', (event) => {
            if (event.target === this.modal) {
                this.closeModal();
            }
        });

        this.form?.addEventListener('submit', (event) => {
            event.preventDefault();
            void this.handleSubmit();
        });

        this.grid?.addEventListener('click', (event) => {
            const target = (event.target as HTMLElement).closest<HTMLButtonElement>('[data-area-action]');
            if (!target) return;
            const areaId = Number(target.dataset.areaId);
            if (!areaId) return;
            if (target.dataset.areaAction === 'edit') {
                const area = this.areas.find((a) => a.id === areaId);
                if (area) this.openModal(area);
            } else if (target.dataset.areaAction === 'delete') {
                void this.handleDelete(areaId);
            }
        });

        // Canvas drawing events
        this.clearCanvasBtn?.addEventListener('click', () => this.clearCanvas());

        this.backgroundCanvas?.addEventListener('pointerdown', (e) => this.startDrawing(e));
        this.backgroundCanvas?.addEventListener('pointermove', (e) => this.draw(e));
        this.backgroundCanvas?.addEventListener('pointerup', () => this.stopDrawing());
        this.backgroundCanvas?.addEventListener('pointercancel', () => this.stopDrawing());

        // Drawing mode buttons
        document.querySelectorAll('[data-draw-mode]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const mode = (btn as HTMLElement).dataset.drawMode as typeof this.drawingMode;
                this.drawingMode = mode;
                document.querySelectorAll('[data-draw-mode]').forEach((b) => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });

        // Drawing color picker
        const colorPicker = document.getElementById('area-draw-color') as HTMLInputElement | null;
        colorPicker?.addEventListener('change', (e) => {
            this.drawingColor = (e.target as HTMLInputElement).value;
        });
    }

    private clearCanvas(): void {
        if (!this.backgroundCanvas || !this.backgroundCtx) return;
        this.backgroundCtx.clearRect(0, 0, this.backgroundCanvas.width, this.backgroundCanvas.height);
    }

    private getCanvasCoords(e: PointerEvent): { x: number; y: number } {
        if (!this.backgroundCanvas) return { x: 0, y: 0 };
        const rect = this.backgroundCanvas.getBoundingClientRect();
        return {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top
        };
    }

    private startDrawing(e: PointerEvent): void {
        if (!this.backgroundCanvas || !this.backgroundCtx) return;
        this.isDrawing = true;
        const coords = this.getCanvasCoords(e);
        this.lastX = coords.x;
        this.lastY = coords.y;
        this.startX = coords.x;
        this.startY = coords.y;
        this.backgroundCanvas.setPointerCapture(e.pointerId);
    }

    private draw(e: PointerEvent): void {
        if (!this.isDrawing || !this.backgroundCtx || !this.backgroundCanvas) return;
        const coords = this.getCanvasCoords(e);

        this.backgroundCtx.strokeStyle = this.drawingColor;
        this.backgroundCtx.lineWidth = 2;
        this.backgroundCtx.lineCap = 'round';

        if (this.drawingMode === 'pen') {
            this.backgroundCtx.beginPath();
            this.backgroundCtx.moveTo(this.lastX, this.lastY);
            this.backgroundCtx.lineTo(coords.x, coords.y);
            this.backgroundCtx.stroke();
            this.lastX = coords.x;
            this.lastY = coords.y;
        } else {
            this.lastX = coords.x;
            this.lastY = coords.y;
        }
    }

    private stopDrawing(): void {
        if (!this.isDrawing || !this.backgroundCtx) return;

        if (this.drawingMode === 'rect') {
            const width = this.lastX - this.startX;
            const height = this.lastY - this.startY;
            this.backgroundCtx.strokeStyle = this.drawingColor;
            this.backgroundCtx.lineWidth = 2;
            this.backgroundCtx.strokeRect(this.startX, this.startY, width, height);
        } else if (this.drawingMode === 'circle') {
            const radius = Math.sqrt(
                Math.pow(this.lastX - this.startX, 2) + Math.pow(this.lastY - this.startY, 2)
            );
            this.backgroundCtx.strokeStyle = this.drawingColor;
            this.backgroundCtx.lineWidth = 2;
            this.backgroundCtx.beginPath();
            this.backgroundCtx.arc(this.startX, this.startY, radius, 0, 2 * Math.PI);
            this.backgroundCtx.stroke();
        } else if (this.drawingMode === 'line') {
            this.backgroundCtx.strokeStyle = this.drawingColor;
            this.backgroundCtx.lineWidth = 2;
            this.backgroundCtx.beginPath();
            this.backgroundCtx.moveTo(this.startX, this.startY);
            this.backgroundCtx.lineTo(this.lastX, this.lastY);
            this.backgroundCtx.stroke();
        }

        this.isDrawing = false;
    }

    private async loadAreas(): Promise<void> {
        try {
            this.setLoading(true);
            const response = await fetch('/api/areas');
            const result = await response.json();
            const payload = unwrapApiResponse<{ areas?: AreaRecord[] }>(result, 'Error al cargar áreas');
            const fetched = payload.areas || [];
            this.areas = fetched.map((area: AreaRecord) => ({
                ...area,
                prefix: this.getDefaultPrefix(area.name, area.prefix)
            }));
            this.renderGrid();
            this.notifyAreasUpdate();
        } catch (error) {
            console.error('[AREAS] Error loading areas', error);
            this.renderError((error as Error).message);
        } finally {
            this.setLoading(false);
        }
    }

    private renderGrid(): void {
        if (!this.grid) return;
        if (!this.areas.length) {
            this.grid.innerHTML =
                '<p style="text-align: center; color: #64748b; padding: 2rem;">No hay áreas creadas. Crea la primera área para comenzar.</p>';
            return;
        }

        this.grid.innerHTML = this.areas
            .map(
                (area) => `
                <div class="area-card">
                    <div class="area-card__header">
                        <div class="area-card__color" style="background: ${area.color || DEFAULT_COLOR};"></div>
                        <h4 class="area-card__name">${area.name}</h4>
                        ${this.getDefaultPrefix(area.name, area.prefix) ? `<span class="area-card__prefix" style="font-size: 0.875rem; color: #475569;">Prefijo: ${this.getDefaultPrefix(area.name, area.prefix)}</span>` : ''}
                    </div>
                    ${area.description ? `<p class="area-card__description">${area.description}</p>` : ''}
                    <div class="area-card__stats">
                        <div class="area-stat">
                            <span>Mesas</span>
                            <strong>${area.tables_count || 0}</strong>
                        </div>
                    </div>
                    <div class="area-card__actions">
                        <button type="button" class="btn btn--small btn--secondary" data-area-action="edit" data-area-id="${area.id}">
                            ✏️ Editar
                        </button>
                        <button type="button" class="btn btn--small btn--danger" data-area-action="delete" data-area-id="${area.id}">
                            🗑️ Eliminar
                        </button>
                    </div>
                </div>`
            )
            .join('');
    }

    private renderError(message: string): void {
        if (this.grid) {
            this.grid.innerHTML = `<p style="text-align: center; color: #ef4444; padding: 2rem;">${message}</p>`;
        }
    }

    private openModal(area?: AreaRecord): void {
        this.editingId = area?.id ?? null;
        if (this.idInput) this.idInput.value = area?.id?.toString() || '';
        if (this.nameInput) this.nameInput.value = area?.name || '';
        if (this.descriptionInput) this.descriptionInput.value = area?.description || '';
        if (this.colorInput) this.colorInput.value = area?.color || DEFAULT_COLOR;
        if (this.prefixInput) this.prefixInput.value = this.getDefaultPrefix(area?.name, area?.prefix) || '';
        if (this.titleEl) this.titleEl.textContent = area ? 'Editar Área/Salón' : 'Crear Área/Salón';

        // Load background image to canvas if exists
        this.clearCanvas();
        if (area?.background_image && this.backgroundCanvas && this.backgroundCtx) {
            const img = new Image();
            img.onload = () => {
                if (this.backgroundCtx && this.backgroundCanvas) {
                    this.backgroundCtx.drawImage(img, 0, 0, this.backgroundCanvas.width, this.backgroundCanvas.height);
                }
            };
            img.src = area.background_image;
        }

        this.modal?.classList.add('active');
    }

    private closeModal(): void {
        this.modal?.classList.remove('active');
        this.editingId = null;
    }

    private async handleSubmit(): Promise<void> {
        if (!this.form) return;

        // Convert canvas to base64 image
        let backgroundImage: string | null = null;
        if (this.backgroundCanvas && this.backgroundCtx) {
            // Check if canvas has any drawings
            const imageData = this.backgroundCtx.getImageData(0, 0, this.backgroundCanvas.width, this.backgroundCanvas.height);
            const hasDrawing = imageData.data.some((channel) => channel !== 0);
            if (hasDrawing) {
                backgroundImage = this.backgroundCanvas.toDataURL('image/png');
            }
        }

        const payload: Record<string, any> = {
            name: this.nameInput?.value.trim() || '',
            description: this.descriptionInput?.value || '',
            color: this.colorInput?.value || DEFAULT_COLOR,
            prefix: this.getDefaultPrefix(this.nameInput?.value, this.prefixInput?.value || ''),
            background_image: backgroundImage
        };
        if (!payload.name) {
            showToast('El nombre del área es obligatorio', 'warning');
            return;
        }
        const url = this.editingId ? `/api/areas/${this.editingId}` : '/api/areas';
        const method = this.editingId ? 'PUT' : 'POST';
        try {
            const response = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json();
            unwrapApiResponse(result, 'Error al guardar área');
            showToast(this.editingId ? 'Área actualizada' : 'Área creada', 'success');
            this.closeModal();
            await this.reload();
            this.requestTablesRefresh();
        } catch (error) {
            console.error('[AREAS] Error saving area', error);
            showToast((error as Error).message, 'error');
        }
    }

    private async handleDelete(areaId: number): Promise<void> {
        const confirmDelete = window.confirm(
            '¿Estás seguro de eliminar esta área? Las mesas asociadas quedarán sin área.'
        );
        if (!confirmDelete) return;
        try {
            const response = await fetch(`/api/areas/${areaId}`, { method: 'DELETE' });
            const result = await response.json();
            unwrapApiResponse(result, 'Error al eliminar área');
            showToast('Área eliminada', 'success');
            await this.reload();
            this.requestTablesRefresh();
        } catch (error) {
            console.error('[AREAS] Error deleting area', error);
            showToast((error as Error).message, 'error');
        }
    }

    private notifyAreasUpdate(): void {
        window.dispatchEvent(
            new CustomEvent('pronto:areas:updated', {
                detail: { areas: this.getAreas() }
            })
        );
    }

    private requestTablesRefresh(): void {
        window.dispatchEvent(new CustomEvent('pronto:tables:reload'));
    }

    private setLoading(isLoading: boolean): void {
        if (isLoading) {
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
