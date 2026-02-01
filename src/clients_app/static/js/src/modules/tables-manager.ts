import {
  buildTableCode,
  deriveAreaCodeFromLabel,
  parseTableCode,
} from '../../../../../clients_app/static/js/src/shared/table-code';
import { normalizeRole } from './role-context';

interface TableRecord {
  id: number;
  table_number: string;
  area_id?: number | null;
  capacity?: number;
  shape?: 'round' | 'square' | 'rectangular';
  notes?: string | null;
  status?: 'available' | 'occupied' | 'reserved' | 'indisposed';
  position_x?: number | null;
  position_y?: number | null;
  zone?: string | null;
  original_table_number?: string;
  zone_prefix?: string | null;
}

interface AreaRecord {
  id: number;
  name: string;
  color?: string | null;
  description?: string | null;
  prefix?: string | null;
  background_image?: string | null;
}

interface TablesState {
  filter: 'all' | string;
  zoom: number;
}

const STATUS_LABELS: Record<string, string> = {
  available: 'Disponible',
  occupied: 'Ocupada',
  reserved: 'Reservada',
  indisposed: 'No disponible',
};

const SHAPE_LABELS: Record<string, string> = {
  round: 'Redonda',
  square: 'Cuadrada',
  rectangular: 'Rectangular',
};

export function initTablesManager(): void {
  document.addEventListener('DOMContentLoaded', () => {
    const root = document.querySelector<HTMLElement>('[data-tables-root]');
    if (!root) return;

    const manager = new TablesManager(root);
    manager.initialize();

    window.editTable = (tableId: number) => manager.openEditModal(tableId);
    window.deleteTable = (tableId: number) => void manager.deleteTable(tableId);
    window.TablesManager = {
      reload: () => manager.reload(),
    };
  });
}

class TablesManager {
  private tables: TableRecord[] = [];
  private areas: AreaRecord[] = [];
  private state: TablesState = {
    filter: 'all',
    zoom: 1,
  };
  private allowEdits: boolean;

  private canvasContent: HTMLElement | null;
  private canvasAreaLabel: HTMLElement | null;
  private areaSelector: HTMLElement | null;
  private addTableBtn: HTMLButtonElement | null;
  private statsTotal: HTMLElement | null;
  private statsAvailable: HTMLElement | null;
  private statsOccupied: HTMLElement | null;
  private statsReserved: HTMLElement | null;
  private statsIndisposed: HTMLElement | null;
  private noAreasAlert: HTMLElement | null;
  private zoomInBtn: HTMLButtonElement | null;
  private zoomOutBtn: HTMLButtonElement | null;
  private zoomResetBtn: HTMLButtonElement | null;
  private tableModal: HTMLElement | null;
  private tableForm: HTMLFormElement | null;
  private tableIdInput: HTMLInputElement | null;
  private tableNumberInput: HTMLInputElement | null;
  private tableAreaSelect: HTMLSelectElement | null;
  private tableCapacityInput: HTMLInputElement | null;
  private tableShapeSelect: HTMLSelectElement | null;
  private tableNotesInput: HTMLTextAreaElement | null;
  private tableModalTitle: HTMLElement | null;
  private tablesListGrid: HTMLElement | null;
  private tableCodePreview: HTMLElement | null;
  private tableCodeDisplay: HTMLElement | null;

  constructor(root: HTMLElement) {
    this.canvasContent = root.querySelector('#tables-canvas-content');
    this.canvasAreaLabel = root.querySelector('#canvas-area-label');
    this.areaSelector = root.querySelector('#tables-area-selector');
    this.addTableBtn = root.querySelector('#add-table-btn');
    this.statsTotal = root.querySelector('#tables-total-count');
    this.statsAvailable = root.querySelector('#tables-available-count');
    this.statsOccupied = root.querySelector('#tables-occupied-count');
    this.statsReserved = root.querySelector('#tables-reserved-count');
    this.statsIndisposed = root.querySelector('#tables-indisposed-count');
    this.noAreasAlert = root.querySelector('#no-areas-alert');
    this.zoomInBtn = root.querySelector('#canvas-zoom-in');
    this.zoomOutBtn = root.querySelector('#canvas-zoom-out');
    this.zoomResetBtn = root.querySelector('#canvas-reset');
    this.tableModal = document.getElementById('table-modal');
    this.tableForm = document.getElementById('table-form') as HTMLFormElement | null;
    this.tableIdInput = document.getElementById('table-id') as HTMLInputElement | null;
    this.tableNumberInput = document.getElementById('table-number') as HTMLInputElement | null;
    this.tableAreaSelect = document.getElementById('table-area') as HTMLSelectElement | null;
    this.tableCapacityInput = document.getElementById('table-capacity') as HTMLInputElement | null;
    this.tableShapeSelect = document.getElementById('table-shape') as HTMLSelectElement | null;
    this.tableNotesInput = document.getElementById('table-notes') as HTMLTextAreaElement | null;
    this.tableModalTitle = document.getElementById('table-modal-title');
    this.tablesListGrid = document.getElementById('tables-list-grid');
    this.tableCodePreview = document.getElementById('table-code-preview');
    this.tableCodeDisplay = document.getElementById('table-code-display');

    const employeeRole = window.APP_DATA?.employee_role || '';
    const normalizedRole = normalizeRole(employeeRole);
    this.allowEdits = ['admin', 'chef', 'waiter'].includes(normalizedRole);
  }

  private tableHasSavedPosition(table: TableRecord): boolean {
    return (
      Number.isFinite(table.position_x as number) && Number.isFinite(table.position_y as number)
    );
  }

  private getTableSortParts(table: TableRecord): {
    areaCode: string;
    areaName: string;
    tableNumber: number;
    raw: string;
  } {
    const area = this.findAreaForTable(table);
    const parsed = parseTableCode(table.table_number || '') || null;
    const areaCode = (
      parsed?.areaCode ||
      table.zone_prefix ||
      this.resolveAreaCode(area, table.zone)
    ).toUpperCase();
    const areaName = (area?.name || table.zone || '').toString().trim().toLowerCase();
    const rawNumber = table.original_table_number || table.table_number || '';
    const fallbackDigits = Number(this.extractTableDigits(rawNumber)) || 0;
    const tableNumber = parsed?.tableNumber ?? fallbackDigits;
    return { areaCode, areaName, tableNumber, raw: String(table.table_number || rawNumber) };
  }

  private sortTablesForDisplay(tables: TableRecord[]): TableRecord[] {
    const cloned = [...tables];
    // Sort by ID (creation order) to maintain visual order as they were registered
    cloned.sort((a, b) => a.id - b.id);
    return cloned;
  }

  private deriveDefaultCanvasPositions(
    tables: TableRecord[]
  ): Map<number, { x: number; y: number }> {
    const positions = new Map<number, { x: number; y: number }>();
    const withoutSaved = tables.filter((t) => !this.tableHasSavedPosition(t));
    if (!withoutSaved.length) return positions;

    // Group by area (code + name) and place in blocks left-to-right.
    const groups = new Map<string, TableRecord[]>();
    withoutSaved.forEach((table) => {
      const parts = this.getTableSortParts(table);
      const key = `${parts.areaCode}:${parts.areaName || 'general'}`;
      const list = groups.get(key) || [];
      list.push(table);
      groups.set(key, list);
    });

    const orderedKeys = Array.from(groups.keys()).sort((a, b) => a.localeCompare(b));

    const marginX = 56;
    const marginY = 56;
    const colCount = 4;
    const stepX = 120;
    const stepY = 96;
    const blockPaddingX = 56;
    const blockWidth = colCount * stepX + blockPaddingX;

    orderedKeys.forEach((key, groupIndex) => {
      const groupTables = this.sortTablesForDisplay(groups.get(key) || []);
      const baseX = marginX + groupIndex * blockWidth;
      const baseY = marginY;

      groupTables.forEach((table, index) => {
        const col = index % colCount;
        const row = Math.floor(index / colCount);
        positions.set(table.id, {
          x: baseX + col * stepX,
          y: baseY + row * stepY,
        });
      });
    });

    return positions;
  }

  private normalizeAreasList(areas: AreaRecord[]): AreaRecord[] {
    return (areas || []).map((area) => ({
      ...area,
      prefix: this.deriveZonePrefix(area, area.name),
    }));
  }

  private deriveZonePrefix(area?: AreaRecord | null, zone?: string | null): string {
    const explicit = (area?.prefix || '').trim();
    if (explicit) return deriveAreaCodeFromLabel(explicit);
    const source = (zone || area?.name || '').trim();
    return deriveAreaCodeFromLabel(source || '', 'G');
  }

  private resolveAreaCode(area?: AreaRecord | null, zone?: string | null): string {
    const prefix = this.deriveZonePrefix(area, zone);
    return prefix || deriveAreaCodeFromLabel(zone || area?.name || '', 'G');
  }

  private extractTableDigits(tableNumber: string): string {
    const match = (tableNumber || '').match(/(\d+)/);
    return match ? match[1] : '';
  }

  private formatTableNumber(
    rawNumber: string,
    area?: AreaRecord | null,
    zone?: string | null
  ): string {
    const digits = this.extractTableDigits(rawNumber);
    const tableNumber = Number(digits);
    const resolvedNumber = Number.isInteger(tableNumber) ? tableNumber : 1;
    const areaCode = this.resolveAreaCode(area, zone || area?.name);
    try {
      return buildTableCode(areaCode, resolvedNumber);
    } catch (error) {
      console.warn('[TABLES] Código de mesa inválido', error);
      return '';
    }
  }

  private buildZoneLabel(area?: AreaRecord | null, fallbackZone?: string | null): string {
    if (area) {
      const prefix = this.deriveZonePrefix(area, area.name);
      return prefix ? `${prefix}-${area.name}` : area.name;
    }
    const base = (fallbackZone || 'General').trim();
    const prefix = this.deriveZonePrefix(undefined, base);
    return prefix ? `${prefix}-${base}` : base;
  }

  private findAreaForTable(
    table: TableRecord,
    areaIdOverride?: number | null
  ): AreaRecord | undefined {
    const areaId = areaIdOverride ?? table.area_id;
    if (areaId) {
      const byId = this.areas.find((area) => area.id === areaId);
      if (byId) return byId;
    }
    const zoneName = (table.zone || '').trim().toLowerCase();
    if (!zoneName) return undefined;
    const candidates = [zoneName];
    if (zoneName.includes('-')) candidates.push(zoneName.split('-').slice(1).join('-').trim());
    if (zoneName.includes('·')) candidates.push(zoneName.split('·').slice(1).join('·').trim());
    return this.areas.find((area) => candidates.includes(area.name.trim().toLowerCase()));
  }

  private normalizeTableRecord(table: TableRecord): TableRecord {
    const area = this.findAreaForTable(table);
    const rawNumber = table.original_table_number || table.table_number;
    const parsed = parseTableCode(table.table_number || '') || null;
    const derivedNumber = parsed?.tableNumber ?? (Number(this.extractTableDigits(rawNumber)) || 1);
    const areaCode = parsed?.areaCode || this.resolveAreaCode(area, table.zone);
    let formattedNumber = '';
    try {
      formattedNumber = buildTableCode(areaCode, derivedNumber);
    } catch (error) {
      console.warn('[TABLES] No se pudo formatear la mesa', error);
    }
    const prefix = areaCode;
    const zoneLabel = this.buildZoneLabel(area, table.zone);
    return {
      ...table,
      original_table_number: rawNumber,
      table_number: formattedNumber,
      area_id: table.area_id ?? area?.id ?? null,
      zone: zoneLabel,
      zone_prefix: prefix,
    };
  }

  private applyAreaMetadata(): void {
    this.tables = this.tables.map((table) => this.normalizeTableRecord(table));
  }

  private getNextTableNumber(area?: AreaRecord | null): string {
    const areaId = area?.id;
    const relevant = this.tables.filter((table) => {
      const tableArea = this.findAreaForTable(table);
      return areaId ? tableArea?.id === areaId : true;
    });
    const highest = relevant.reduce((max, table) => {
      const digits = this.extractTableDigits(table.original_table_number || table.table_number);
      const numeric = Number(digits);
      return Number.isFinite(numeric) ? Math.max(max, numeric) : max;
    }, 0);
    return this.formatTableNumber(String(highest + 1), area || null, area?.name);
  }

  initialize(): void {
    this.attachEvents();
    void this.loadAreas().then(() => {
      this.renderAreaSelector();
      this.populateAreaSelect();
      this.toggleAreasAlert();
      return this.loadTables();
    });

    window.addEventListener('pronto:areas:updated', (event: Event) => {
      const detail = (event as CustomEvent<{ areas: AreaRecord[] }>).detail;
      this.areas = this.normalizeAreasList(detail?.areas || []);
      this.applyAreaMetadata();
      this.renderAreaSelector();
      this.populateAreaSelect();
      this.toggleAreasAlert();
      this.renderStats();
      this.renderCanvas();
      this.renderList();
    });

    window.addEventListener('pronto:tables:reload', () => {
      void this.loadTables();
    });
  }

  private async loadAreas(): Promise<void> {
    try {
      const fromGlobal = window.ProntoAreas?.getAreas?.() || [];
      if (fromGlobal.length) {
        this.areas = this.normalizeAreasList(fromGlobal);
        return;
      }

      const response = await fetch('/api/areas');
      const result = await response.json().catch(() => ({}));
      const areasPayload =
        (Array.isArray(result?.data?.areas) && result.data.areas) ||
        (Array.isArray(result?.areas) && result.areas) ||
        [];
      this.areas = this.normalizeAreasList(areasPayload);
    } catch (error) {
      console.warn('[TABLES] No se pudieron cargar áreas, usando fallback por mesas', error);
      this.areas = [];
    }
  }

  private ensureAreasFromTables(): void {
    if (this.areas.length || !this.tables.length) return;

    const byZone = new Map<string, { name: string; prefix: string; tables_count: number }>();
    this.tables.forEach((table) => {
      const zoneName = (table.zone || '').trim() || 'General';
      const parsed = parseTableCode(table.table_number || '') || null;
      const prefix = parsed?.areaCode || deriveAreaCodeFromLabel(zoneName, 'G');
      const key = `${prefix}:${zoneName}`;
      const current = byZone.get(key);
      if (current) {
        current.tables_count += 1;
      } else {
        byZone.set(key, { name: zoneName, prefix, tables_count: 1 });
      }
    });

    const entries = Array.from(byZone.values()).sort((a, b) => {
      const ak = `${a.prefix}:${a.name}`.toLowerCase();
      const bk = `${b.prefix}:${b.name}`.toLowerCase();
      return ak.localeCompare(bk);
    });

    this.areas = this.normalizeAreasList(
      entries.map((item, index) => ({
        id: index + 1,
        name: item.name,
        prefix: item.prefix,
        color: '#ff6b35',
        description: '',
        tables_count: item.tables_count,
      }))
    );
  }

  async reload(): Promise<void> {
    await this.loadTables();
  }

  private attachEvents(): void {
    this.zoomInBtn?.addEventListener('click', () => {
      this.state.zoom = Math.min(this.state.zoom + 0.1, 2);
      this.updateCanvasZoom();
    });

    this.zoomOutBtn?.addEventListener('click', () => {
      this.state.zoom = Math.max(this.state.zoom - 0.1, 0.5);
      this.updateCanvasZoom();
    });

    this.zoomResetBtn?.addEventListener('click', () => {
      this.state.zoom = 1;
      this.updateCanvasZoom();
    });

    this.addTableBtn?.addEventListener('click', () => {
      if (!this.allowEdits) {
        showToast('No tienes permisos para crear mesas', 'warning');
        return;
      }
      if (!this.areas.length) {
        showToast('Primero crea un área para poder registrar mesas', 'warning');
        return;
      }
      this.openCreateModal();
    });

    const closeTableModalBtn = document.getElementById('close-table-modal');
    const cancelTableBtn = document.getElementById('cancel-table');
    closeTableModalBtn?.addEventListener('click', () => this.closeModal());
    cancelTableBtn?.addEventListener('click', () => this.closeModal());
    this.tableModal?.addEventListener('click', (event) => {
      if (event.target === this.tableModal) {
        this.closeModal();
      }
    });

    this.tableForm?.addEventListener('submit', (event) => {
      event.preventDefault();
      void this.handleFormSubmit();
    });

    // Update table code preview when area or number changes
    this.tableAreaSelect?.addEventListener('change', () => this.updateTableCodePreview());
    this.tableNumberInput?.addEventListener('input', () => this.updateTableCodePreview());
  }

  private updateTableCodePreview(): void {
    if (!this.tableCodePreview || !this.tableCodeDisplay) return;

    const areaId = this.tableAreaSelect?.value ? Number(this.tableAreaSelect.value) : null;
    const numberValue = this.tableNumberInput?.value ? Number(this.tableNumberInput.value) : null;

    if (!areaId || !numberValue || numberValue < 1 || numberValue > 99) {
      this.tableCodePreview.style.display = 'none';
      return;
    }

    const area = this.areas.find((a) => a.id === areaId);
    if (!area) {
      this.tableCodePreview.style.display = 'none';
      return;
    }

    const prefix = this.deriveZonePrefix(area, area.name);
    const tableCode = `${prefix}-M${String(numberValue).padStart(2, '0')}`;
    this.tableCodeDisplay.textContent = tableCode;
    this.tableCodePreview.style.display = 'block';
  }

  /**
   * Public method to refresh tables display
   */
  public async refresh(): Promise<void> {
    await this.loadTables();
  }

  private async loadTables(): Promise<void> {
    try {
      this.setLoading(true);
      if (this.tablesListGrid) {
        this.tablesListGrid.innerHTML =
          '<p style="text-align: center; color: #64748b; padding: 2rem;">Cargando mesas...</p>';
      }
      const response = await fetch('/api/tables');
      if (!response.ok) {
        throw new Error('Error al cargar mesas');
      }
      const result = await response.json();
      const fetchedTables = (result.tables || []) as TableRecord[];
      this.tables = fetchedTables.map((table) => this.normalizeTableRecord(table));
      this.ensureAreasFromTables();
      this.applyAreaMetadata();
      this.renderAreaSelector();
      this.populateAreaSelect();
      this.toggleAreasAlert();
      this.renderStats();
      this.renderCanvas();
      this.renderList();
    } catch (error) {
      console.error('[TABLES] Error loading tables', error);
      if (this.tablesListGrid) {
        this.tablesListGrid.innerHTML = `<p style="color:#ef4444; text-align:center;">${
          (error as Error).message || 'Error al cargar mesas'
        }</p>`;
      }
    } finally {
      this.setLoading(false);
    }
  }

  private renderStats(): void {
    if (!this.tables.length) {
      this.statsTotal && (this.statsTotal.textContent = '0');
      this.statsAvailable && (this.statsAvailable.textContent = '0');
      this.statsOccupied && (this.statsOccupied.textContent = '0');
      this.statsReserved && (this.statsReserved.textContent = '0');
      this.statsIndisposed && (this.statsIndisposed.textContent = '0');
      return;
    }
    const total = this.tables.length;
    const available = this.tables.filter((table) => table.status === 'available').length;
    const occupied = this.tables.filter((table) => table.status === 'occupied').length;
    const reserved = this.tables.filter((table) => table.status === 'reserved').length;
    const indisposed = this.tables.filter((table) => table.status === 'indisposed').length;
    if (this.statsTotal) this.statsTotal.textContent = String(total);
    if (this.statsAvailable) this.statsAvailable.textContent = String(available);
    if (this.statsOccupied) this.statsOccupied.textContent = String(occupied);
    if (this.statsReserved) this.statsReserved.textContent = String(reserved);
    if (this.statsIndisposed) this.statsIndisposed.textContent = String(indisposed);
  }

  private renderAreaSelector(): void {
    if (!this.areaSelector) return;
    const buttons = [
      `<button type="button" class="area-selector-btn ${this.state.filter === 'all' ? 'active' : ''}" data-area="all">
                <span class="area-color" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);"></span>
                <span>Todas las áreas</span>
            </button>`,
    ];
    this.areas.forEach((area) => {
      const isActive = this.state.filter === String(area.id);
      const prefix = this.deriveZonePrefix(area, area.name);
      const label = prefix ? `${prefix} · ${area.name}` : area.name;
      buttons.push(`
                <button type="button" class="area-selector-btn ${isActive ? 'active' : ''}" data-area="${area.id}">
                    <span class="area-color" style="background: ${area.color || '#ff6b35'};"></span>
                    <span>${label}</span>
                </button>
            `);
    });
    this.areaSelector.innerHTML = buttons.join('');
    this.areaSelector.querySelectorAll<HTMLButtonElement>('.area-selector-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const value = btn.dataset.area || 'all';
        this.state.filter = value as TablesState['filter'];
        this.areaSelector?.querySelectorAll('.area-selector-btn').forEach((element) => {
          element.classList.toggle('active', element === btn);
        });
        this.updateAreaLabel();
        this.renderCanvas();
      });
    });
  }

  private populateAreaSelect(): void {
    if (!this.tableAreaSelect) return;
    const options = ['<option value="">Seleccionar área</option>'].concat(
      this.areas.map((area) => {
        const prefix = this.deriveZonePrefix(area, area.name);
        const label = prefix ? `${prefix} · ${area.name}` : area.name;
        return `<option value="${area.id}">${label}</option>`;
      })
    );
    this.tableAreaSelect.innerHTML = options.join('');
  }

  private updateAreaLabel(): void {
    if (!this.canvasAreaLabel) return;
    if (this.state.filter === 'all') {
      this.canvasAreaLabel.textContent = 'Todas las áreas';
      return;
    }
    const area = this.areas.find((item) => String(item.id) === this.state.filter);
    this.canvasAreaLabel.textContent = area
      ? this.buildZoneLabel(area, area.name)
      : 'Área desconocida';
  }

  private renderCanvas(): void {
    if (!this.canvasContent) return;
    const filteredTables =
      this.state.filter === 'all'
        ? this.tables
        : this.tables.filter((table) => String(table.area_id || '') === this.state.filter);

    this.canvasContent.innerHTML = '';

    // Add background image if area has one
    if (this.state.filter !== 'all') {
      const area = this.areas.find((item) => String(item.id) === this.state.filter);
      if (area?.background_image) {
        const bgImage = document.createElement('div');
        bgImage.className = 'canvas-background-image';
        bgImage.style.backgroundImage = `url(${area.background_image})`;
        bgImage.style.backgroundSize = 'contain';
        bgImage.style.backgroundRepeat = 'no-repeat';
        bgImage.style.backgroundPosition = 'top left';
        bgImage.style.position = 'absolute';
        bgImage.style.top = '0';
        bgImage.style.left = '0';
        bgImage.style.width = '100%';
        bgImage.style.height = '100%';
        bgImage.style.opacity = '0.3';
        bgImage.style.pointerEvents = 'none';
        bgImage.style.zIndex = '0';
        this.canvasContent.appendChild(bgImage);
      }
    }

    if (!filteredTables.length) {
      const empty = document.createElement('div');
      empty.className = 'canvas-empty-state';
      empty.style.position = 'relative';
      empty.style.zIndex = '1';
      empty.innerHTML = `
                <span style="font-size: 3rem; opacity: 0.5;">🪑</span>
                <p style="font-size: 1.125rem; color: #64748b; margin-top: 1rem;">
                    No hay mesas ${this.state.filter === 'all' ? 'registradas' : 'para esta área'}
                </p>
                <p style="font-size: 0.875rem; color: #94a3b8;">
                    Haz clic en "➕ Mesa" para agregar ${this.state.filter === 'all' ? 'tu primera mesa' : 'una mesa a esta área'}
                </p>`;
      this.canvasContent.appendChild(empty);
      return;
    }

    const sorted = this.sortTablesForDisplay(filteredTables);
    const defaultPositions = this.deriveDefaultCanvasPositions(sorted);

    sorted.forEach((table) => {
      const node = this.createTableNode(table, defaultPositions.get(table.id));
      this.canvasContent!.appendChild(node);
    });
  }

  private createTableNode(
    table: TableRecord,
    defaultPosition?: { x: number; y: number }
  ): HTMLElement {
    const node = document.createElement('div');
    node.className = `table-node ${table.shape || 'round'} ${table.status || 'available'}`;
    node.dataset.tableId = String(table.id);
    const x = this.tableHasSavedPosition(table)
      ? (table.position_x as number)
      : (defaultPosition?.x ?? 56);
    const y = this.tableHasSavedPosition(table)
      ? (table.position_y as number)
      : (defaultPosition?.y ?? 56);
    node.style.left = `${x}px`;
    node.style.top = `${y}px`;
    node.style.position = 'absolute';
    node.style.zIndex = '10';
    node.innerHTML = `
            <div class="table-node__number">${table.table_number}</div>
            <div class="table-node__capacity">👥 ${table.capacity || 0}</div>
            <div class="table-node__actions">
                <button type="button" class="table-action-btn" data-action="edit" title="Editar">✏️</button>
                <button type="button" class="table-action-btn" data-action="delete" title="Eliminar">🗑️</button>
            </div>
        `;
    if (!this.allowEdits) {
      node.querySelector<HTMLElement>('.table-node__actions')?.remove();
    } else {
      node.querySelector('[data-action="edit"]')?.addEventListener('click', (event) => {
        event.stopPropagation();
        this.openEditModal(table.id);
      });
      node.querySelector('[data-action="delete"]')?.addEventListener('click', (event) => {
        event.stopPropagation();
        void this.deleteTable(table.id);
      });
      this.enableDrag(node, table);
    }
    return node;
  }

  private enableDrag(node: HTMLElement, table: TableRecord): void {
    let isDragging = false;
    let startX = 0;
    let startY = 0;
    let initialX = 0;
    let initialY = 0;

    const onPointerDown = (event: PointerEvent) => {
      if ((event.target as HTMLElement).classList.contains('table-action-btn')) return;
      if (!this.canvasContent) return;
      isDragging = true;
      node.classList.add('dragging');
      startX = event.clientX;
      startY = event.clientY;
      initialX = parseFloat(node.style.left) || 0;
      initialY = parseFloat(node.style.top) || 0;
      node.setPointerCapture(event.pointerId);
    };

    const onPointerMove = (event: PointerEvent) => {
      if (!isDragging) return;
      const dx = event.clientX - startX;
      const dy = event.clientY - startY;
      node.style.left = `${Math.max(0, initialX + dx)}px`;
      node.style.top = `${Math.max(0, initialY + dy)}px`;
    };

    const onPointerUp = async (event: PointerEvent) => {
      if (!isDragging) return;
      isDragging = false;
      node.classList.remove('dragging');
      node.releasePointerCapture(event.pointerId);
      const x = parseInt(node.style.left, 10) || 0;
      const y = parseInt(node.style.top, 10) || 0;
      try {
        await fetch(`/api/tables/${table.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ position_x: x, position_y: y }),
        });
        const index = this.tables.findIndex((item) => item.id === table.id);
        if (index !== -1) {
          this.tables[index].position_x = x;
          this.tables[index].position_y = y;
        }
      } catch (error) {
        console.error('[TABLES] Error saving table position', error);
      }
    };

    node.addEventListener('pointerdown', onPointerDown);
    node.addEventListener('pointermove', onPointerMove);
    node.addEventListener('pointerup', onPointerUp);
    node.addEventListener('pointercancel', onPointerUp);
  }

  private renderList(): void {
    if (!this.tablesListGrid) return;
    if (!this.tables.length) {
      this.tablesListGrid.innerHTML =
        '<p style="text-align: center; color: #64748b; padding: 2rem;">No hay mesas creadas</p>';
      return;
    }
    const sorted = this.sortTablesForDisplay(this.tables);
    this.tablesListGrid.innerHTML = sorted
      .map((table) => {
        const area = this.areas.find((item) => item.id === table.area_id);
        const zoneLabel = this.buildZoneLabel(area, table.zone);
        return `
                    <div class="table-list-card">
                        <div class="table-list-card__header">
                            <div>
                                <h4 class="table-list-card__title">${table.table_number}</h4>
                                <div class="table-list-card__area">
                                    ${
                                      area
                                        ? `<span class="area-color" style="background:${area.color || '#ff6b35'};width:16px;height:16px;border-radius:4px;display:inline-block;"></span>`
                                        : ''
                                    }
                                    <span>${zoneLabel || 'Sin área'}</span>
                                </div>
                            </div>
                            <span class="table-list-card__status ${table.status || 'available'}">
                                ${STATUS_LABELS[table.status || ''] || 'Disponible'}
                            </span>
                        </div>
                        <div class="table-list-card__info">
                            <div class="table-info-item">
                                <span>Capacidad</span>
                                <strong>${table.capacity || 0} personas</strong>
                            </div>
                            <div class="table-info-item">
                                <span>Forma</span>
                                <strong>${SHAPE_LABELS[table.shape || ''] || 'Redonda'}</strong>
                            </div>
                        </div>
                        ${table.notes ? `<p class="table-list-card__notes">${table.notes}</p>` : ''}
                        <div class="table-list-card__actions">
                            ${this.allowEdits ? `<button type="button" class="btn btn--small btn--secondary" data-action="edit" data-id="${table.id}">✏️ Editar</button>` : ''}
                            ${this.allowEdits ? `<button type="button" class="btn btn--small btn--danger" data-action="delete" data-id="${table.id}">🗑️ Eliminar</button>` : ''}
                            <a href="/api/tables/${table.id}/qr" target="_blank" class="btn btn--small btn--primary">📱 QR</a>
                        </div>
                    </div>
                `;
      })
      .join('');

    if (this.allowEdits) {
      this.tablesListGrid
        .querySelectorAll<HTMLButtonElement>('button[data-action="edit"]')
        .forEach((btn) => {
          btn.addEventListener('click', () => {
            const id = Number(btn.dataset.id);
            this.openEditModal(id);
          });
        });
      this.tablesListGrid
        .querySelectorAll<HTMLButtonElement>('button[data-action="delete"]')
        .forEach((btn) => {
          btn.addEventListener('click', () => {
            const id = Number(btn.dataset.id);
            void this.deleteTable(id);
          });
        });
    }
  }

  openEditModal(tableId: number): void {
    const table = this.tables.find((item) => item.id === tableId);
    if (!table) return;
    if (this.tableIdInput) this.tableIdInput.value = String(table.id);
    if (this.tableNumberInput) this.tableNumberInput.value = table.table_number || '';
    if (this.tableAreaSelect)
      this.tableAreaSelect.value = table.area_id ? String(table.area_id) : '';
    if (this.tableCapacityInput) this.tableCapacityInput.value = String(table.capacity || 4);
    if (this.tableShapeSelect) this.tableShapeSelect.value = table.shape || 'round';
    if (this.tableNotesInput) this.tableNotesInput.value = table.notes || '';
    if (this.tableModalTitle) this.tableModalTitle.textContent = 'Editar Mesa';
    this.updateTableCodePreview();
    this.tableModal?.classList.add('active');
  }

  private openCreateModal(): void {
    if (this.tableIdInput) this.tableIdInput.value = '';
    if (this.tableNumberInput) this.tableNumberInput.value = '';
    if (this.tableCapacityInput) this.tableCapacityInput.value = '4';
    if (this.tableShapeSelect) this.tableShapeSelect.value = 'round';
    if (this.tableNotesInput) this.tableNotesInput.value = '';
    let defaultArea: AreaRecord | undefined;
    if (this.tableAreaSelect) {
      this.tableAreaSelect.value = this.state.filter !== 'all' ? this.state.filter : '';
      if (this.state.filter !== 'all') {
        defaultArea = this.areas.find((area) => String(area.id) === this.state.filter);
      }
    }
    if (this.tableNumberInput) {
      this.tableNumberInput.value = this.getNextTableNumber(defaultArea);
    }
    if (this.tableModalTitle) this.tableModalTitle.textContent = 'Crear Mesa';
    this.updateTableCodePreview();
    this.tableModal?.classList.add('active');
  }

  private closeModal(): void {
    this.tableModal?.classList.remove('active');
  }

  private async handleFormSubmit(): Promise<void> {
    if (!this.tableForm || !this.tableNumberInput || !this.tableAreaSelect) return;
    const tableId = this.tableIdInput?.value;
    const areaId = this.tableAreaSelect.value ? Number(this.tableAreaSelect.value) : null;
    const selectedArea = this.areas.find(
      (area) => area.id === areaId || area.id === Number(areaId)
    );
    const formattedNumber = this.formatTableNumber(
      this.tableNumberInput.value.trim(),
      selectedArea || null,
      selectedArea?.name
    );
    const payload = {
      table_number: formattedNumber,
      area_id: areaId,
      capacity: Number(this.tableCapacityInput?.value || 0),
      shape: this.tableShapeSelect?.value || 'round',
      notes: this.tableNotesInput?.value || '',
      zone: this.buildZoneLabel(selectedArea, selectedArea?.name || 'General'),
    };
    if (!payload.table_number) {
      showToast('Ingresa un nombre o número válido para la mesa (AREA-MNN)', 'warning');
      return;
    }
    if (!payload.area_id) {
      showToast('Selecciona un área para la mesa', 'warning');
      return;
    }

    const url = tableId ? `/api/tables/${tableId}` : '/api/tables';
    const method = tableId ? 'PUT' : 'POST';
    try {
      this.setLoading(true);
      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (result.status !== 'success') {
        throw new Error(result.message || 'Error al guardar mesa');
      }
      showToast(tableId ? 'Mesa actualizada' : 'Mesa creada', 'success');
      this.closeModal();
      await this.loadTables();
      void window.ProntoAreas?.reload?.();
    } catch (error) {
      console.error('[TABLES] Error saving table', error);
      showToast((error as Error).message || 'Error al guardar mesa', 'error');
    } finally {
      this.setLoading(false);
    }
  }

  async deleteTable(tableId: number): Promise<void> {
    const confirmDelete = window.confirm('¿Estás seguro de eliminar esta mesa?');
    if (!confirmDelete) return;
    try {
      this.setLoading(true);
      const response = await fetch(`/api/tables/${tableId}`, { method: 'DELETE' });
      const result = await response.json();
      if (result.status !== 'success') {
        throw new Error(result.message || 'Error al eliminar mesa');
      }
      showToast('Mesa eliminada', 'success');
      await this.loadTables();
      void window.ProntoAreas?.reload?.();
    } catch (error) {
      console.error('[TABLES] Error deleting table', error);
      showToast((error as Error).message || 'Error al eliminar mesa', 'error');
    } finally {
      this.setLoading(false);
    }
  }

  private updateCanvasZoom(): void {
    if (this.canvasContent) {
      this.canvasContent.style.transform = `scale(${this.state.zoom})`;
    }
  }

  private toggleAreasAlert(): void {
    if (!this.noAreasAlert) return;
    if (!this.areas.length) {
      this.noAreasAlert.style.display = 'block';
      // Don't disable the button, let the click handler show the toast
      // this.addTableBtn?.setAttribute('disabled', 'disabled');
    } else {
      this.noAreasAlert.style.display = 'none';
      if (this.allowEdits) {
        this.addTableBtn?.removeAttribute('disabled');
      }
    }
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
