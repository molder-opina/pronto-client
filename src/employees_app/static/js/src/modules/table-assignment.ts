/**
 * Table Assignment Manager
 * Handles waiter table assignments and transfer requests
 */

import { requestJSON } from '../core/http';

interface Table {
    id: number;
    table_number: string;
    zone: string;
    capacity: number;
    status: string;
    assigned_at?: string;
}

interface TransferRequest {
    id: number;
    table_id: number;
    table_number: string;
    from_waiter_id: number;
    from_waiter_name: string;
    message: string | null;
    created_at: string;
}

interface AssignmentResponse {
    assigned: string[];
    already_assigned: string[];
    conflicts: Array<{ table_id: number; table_number: string; reason: string; current_waiter_id?: number; current_waiter_name?: string }>;
}

interface ConflictInfo {
    table_id: number;
    table_number: string;
    zone?: string;
    current_waiter_id: number;
    current_waiter_name: string;
}

export class TableAssignmentManager {
    private modal: HTMLElement | null = null;
    private transferModal: HTMLElement | null = null;
    private conflictModal: HTMLElement | null = null;
    private myTablesContainer: HTMLElement | null = null;
    private availableTablesContainer: HTMLElement | null = null;
    private zoneFilter: HTMLSelectElement | null = null;
    private selectedTables: Set<number> = new Set();
    private allTables: Table[] = [];
    private myTables: Table[] = [];
    private pollingInterval: number | null = null;
    private assignedTablesDisplay: HTMLElement | null = null;
    private assignedTablesList: HTMLElement | null = null;
    private tableBasePrefix: string = (window.APP_DATA as any)?.table_base_prefix || 'M';
    private pendingAssignment: number[] | null = null;
    private assignBtn: HTMLButtonElement | null = null;
    private acceptBtnFooter: HTMLButtonElement | null = null;

    public getAssignedTables(): Table[] {
        return [...this.myTables];
    }

    public isTableAssigned(tableCode: string): boolean {
        if (!tableCode) return false;
        // Normalize input code
        const normalizedInput = tableCode.toLowerCase().replace(/[^a-z0-9]/g, '');

        return this.myTables.some(table => {
            // Generate formatted code for this table
            const formatted = this.formatDisplayTable(table.zone, table.table_number);
            const normalizedFormatted = formatted.toLowerCase().replace(/[^a-z0-9]/g, '');

            // Also check raw number just in case
            const raw = table.table_number.toString();

            return normalizedInput === normalizedFormatted || normalizedInput === raw;
        });
    }

    constructor() {
        this.tableBasePrefix = this.sanitizeBasePrefix(this.tableBasePrefix);
        this.setupModal();
        this.setupEventListeners();
        this.setupAssignedTablesDisplay();
        this.loadAndDisplayAssignedTables();
    }

    private setupModal(): void {
        // Create main assignment modal
        this.modal = document.getElementById('table-assignment-modal');
        if (!this.modal) {
            console.warn('[TABLE_ASSIGNMENT] Modal not found in DOM');
        }

        this.myTablesContainer = document.getElementById('my-tables-container');
        this.availableTablesContainer = document.getElementById('available-tables-container');
        this.zoneFilter = document.getElementById('zone-filter') as HTMLSelectElement;
        this.assignBtn = document.getElementById('assign-selected-tables') as HTMLButtonElement | null;
        this.acceptBtnFooter = document.getElementById('accept-table-assignment-footer') as HTMLButtonElement | null;

        // Create transfer request modal
        this.transferModal = document.getElementById('transfer-request-modal');

        // Create conflict confirmation modal
        this.setupConflictModal();
    }

    private setupConflictModal(): void {
        // Create conflict modal if it doesn't exist
        let modal = document.getElementById('table-conflict-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'table-conflict-modal';
            modal.className = 'modal';
            modal.innerHTML = `
                <div class="modal-content" style="max-width: 500px;">
                    <div class="modal-header">
                        <h3>⚠️ Confirmar Reasignación de Mesa</h3>
                        <button type="button" class="modal-close" id="close-conflict-modal">×</button>
                    </div>
                    <div class="modal-body" style="padding: 1.5rem;">
                        <p class="modal-hint">
                            Las siguientes mesas ya están asignadas a otros meseros. ¿Deseas retirarlas y asignártelas?
                        </p>
                        <div id="conflict-tables-list" style="margin-bottom: 1.5rem;"></div>
                        <div style="display: flex; gap: 0.75rem; justify-content: flex-end;">
                            <button type="button" id="cancel-conflict-assignment" class="btn btn--secondary" style="padding: 0.75rem 1.5rem;">
                                Cancelar
                            </button>
                            <button type="button" id="confirm-conflict-assignment" class="btn btn--primary" style="padding: 0.75rem 1.5rem;">
                                Sí, Reasignar
                            </button>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }
        this.conflictModal = modal;

        // Setup event listeners
        const closeBtn = document.getElementById('close-conflict-modal');
        const cancelBtn = document.getElementById('cancel-conflict-assignment');
        const confirmBtn = document.getElementById('confirm-conflict-assignment');

        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.closeConflictModal());
        }
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.closeConflictModal());
        }
        if (confirmBtn) {
            confirmBtn.addEventListener('click', () => this.confirmConflictAssignment());
        }

        // Close on backdrop click
        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.closeConflictModal();
                }
            });
        }
    }

    private showConflictModal(conflicts: ConflictInfo[]): void {
        if (!this.conflictModal) return;

        const listContainer = document.getElementById('conflict-tables-list');
        if (listContainer) {
            listContainer.innerHTML = conflicts.map(conflict => {
                const tableDisplay = conflict.zone
                    ? this.formatDisplayTable(conflict.zone, conflict.table_number)
                    : this.formatTableCode(conflict.table_number);
                return `
                <div style="padding: 1rem; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 0.75rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <span style="font-weight: 600; color: #1e293b;">
                            ${tableDisplay}
                        </span>
                    </div>
                    <div style="color: #64748b; font-size: 0.9rem;">
                        Actualmente asignada a: <strong style="color: #ea580c;">${conflict.current_waiter_name}</strong>
                    </div>
                </div>
            `;
            }).join('');
        }

        this.conflictModal.classList.add('active');

        // Close on ESC key
        const handleEsc = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && this.conflictModal?.classList.contains('active')) {
                this.closeConflictModal();
                document.removeEventListener('keydown', handleEsc);
            }
        };
        document.addEventListener('keydown', handleEsc);
    }

    private closeConflictModal(): void {
        if (this.conflictModal) {
            this.conflictModal.classList.remove('active');
        }
        this.pendingAssignment = null;
    }

    private async confirmConflictAssignment(): Promise<void> {
        if (!this.pendingAssignment) return;

        this.closeConflictModal();
        await this.performAssignment(this.pendingAssignment, true);
    }

    private setupEventListeners(): void {
        // Open modal button
        const openBtn = document.getElementById('open-table-assignment');
        console.log('[TABLE_ASSIGNMENT] Setup event listeners - Open button found:', !!openBtn);
        if (openBtn) {
            openBtn.addEventListener('click', () => {
                console.log('[TABLE_ASSIGNMENT] Open button clicked');
                this.openModal();
            });
        } else {
            console.warn('[TABLE_ASSIGNMENT] Open button not found in DOM');
        }

        // Close modal buttons
        const closeBtn = document.getElementById('close-table-assignment');
        const cancelBtn = document.getElementById('cancel-table-assignment');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.closeModal());
        }
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.closeModal());
        }

        // Assign selected tables (restored dedicated button)
        this.assignBtn?.addEventListener('click', () => this.assignSelectedTables());

        // Accept (close modal)
        this.acceptBtnFooter?.addEventListener('click', () => this.closeModal());

        // Zone filter
        if (this.zoneFilter) {
            this.zoneFilter.addEventListener('change', () => this.renderAvailableTables());
        }

        // Transfer modal buttons
        const acceptTransferBtn = document.getElementById('accept-transfer-btn');
        const rejectTransferBtn = document.getElementById('reject-transfer-btn');
        const transferOrdersCheckbox = document.getElementById('transfer-orders-checkbox') as HTMLInputElement;

        if (acceptTransferBtn) {
            acceptTransferBtn.addEventListener('click', () => {
                const requestId = this.transferModal?.dataset.requestId;
                if (requestId) {
                    this.acceptTransferRequest(
                        Number(requestId),
                        transferOrdersCheckbox?.checked || false
                    );
                }
            });
        }

        if (rejectTransferBtn) {
            rejectTransferBtn.addEventListener('click', () => {
                const requestId = this.transferModal?.dataset.requestId;
                if (requestId) {
                    this.rejectTransferRequest(Number(requestId));
                }
            });
        }

        // Close transfer modal
        const closeTransferBtn = document.getElementById('close-transfer-modal');
        if (closeTransferBtn) {
            closeTransferBtn.addEventListener('click', () => this.closeTransferModal());
        }

        // Auto-assign preference checkbox
        const autoAssignCheckbox = document.getElementById('auto-assign-table-on-order-accept') as HTMLInputElement;
        if (autoAssignCheckbox) {
            autoAssignCheckbox.addEventListener('change', () => {
                this.saveAutoAssignPreference(autoAssignCheckbox.checked);
            });
        }
    }

    public async openModal(): Promise<void> {
        console.log('[TABLE_ASSIGNMENT] Opening modal...');
        if (!this.modal) {
            console.error('[TABLE_ASSIGNMENT] Modal element not found');
            return;
        }

        try {
            this.updateAcceptButtons();
            console.log('[TABLE_ASSIGNMENT] Loading table data...');
            // Load data
            await Promise.all([
                this.loadMyTables(),
                this.loadAllTables(),
                this.loadAutoAssignPreference()
            ]);

            console.log('[TABLE_ASSIGNMENT] Rendering tables...');
            // Render tables
            this.renderMyTables();
            this.renderAvailableTables();

            // Show modal
            console.log('[TABLE_ASSIGNMENT] Showing modal...');
            this.modal.classList.add('active');

            // Start polling for transfer requests
            this.startPolling();
            console.log('[TABLE_ASSIGNMENT] Modal opened successfully');
        } catch (error) {
            console.error('[TABLE_ASSIGNMENT] Error opening modal:', error);
            this.showToast('Error al cargar información de mesas. Por favor, verifica que hayas iniciado sesión.', 'danger');
        }
    }

    private closeModal(): void {
        if (!this.modal) return;

        this.modal.classList.remove('active');
        this.selectedTables.clear();
        this.updateAcceptButtons();

        // Stop polling
        this.stopPolling();
    }

    private async loadMyTables(): Promise<void> {
        try {
            console.log('[TABLE_ASSIGNMENT] Fetching my tables from /api/table-assignments/my-tables');
            const response = await requestJSON('/api/table-assignments/my-tables', {
                method: 'GET'
            });

            console.log('[TABLE_ASSIGNMENT] My tables response:', response);
            if (response.tables) {
                this.myTables = response.tables;
                console.log('[TABLE_ASSIGNMENT] Loaded', this.myTables.length, 'assigned tables');
            } else {
                console.warn('[TABLE_ASSIGNMENT] Response has no tables property');
                this.myTables = [];
            }
        } catch (error) {
            console.error('[TABLE_ASSIGNMENT] Error loading my tables:', error);
            const message = error instanceof Error ? error.message : 'Error desconocido';
            this.showToast(`Error al cargar tus mesas asignadas: ${message}`, 'danger');
            this.myTables = [];
        }
    }

    private async loadAllTables(): Promise<void> {
        try {
            console.log('[TABLE_ASSIGNMENT] Fetching all tables from /api/tables');
            const response = await requestJSON('/api/tables', {
                method: 'GET'
            });

            console.log('[TABLE_ASSIGNMENT] All tables response:', response);
            if (response.tables) {
                this.allTables = response.tables.filter((t: Table) => t.status !== 'inactive');
                console.log('[TABLE_ASSIGNMENT] Loaded', this.allTables.length, 'active tables (filtered from', response.tables.length, 'total)');
            } else {
                console.warn('[TABLE_ASSIGNMENT] Response has no tables property');
                this.allTables = [];
            }
        } catch (error) {
            console.error('[TABLE_ASSIGNMENT] Error loading all tables:', error);
            const message = error instanceof Error ? error.message : 'Error desconocido';
            this.showToast(`Error al cargar las mesas disponibles: ${message}`, 'danger');
            this.allTables = [];
        }
    }

    private renderMyTables(): void {
        if (!this.myTablesContainer) return;

        // If API is down, we may have an empty list; show a clearer hint.
        if (!this.myTables.length && !this.allTables.length) {
            this.myTablesContainer.innerHTML = `
                <div class="border-2 border-dashed border-red-200 bg-red-50 rounded-xl px-4 py-8 text-center">
                    <p class="text-sm text-red-700 font-medium" style="margin: 0;">No se pudo cargar la información de mesas</p>
                    <p class="text-xs text-red-600" style="margin: 0.5rem 0 0;">Reintenta en unos segundos (posible reinicio del servidor).</p>
                </div>
            `;
            return;
        }

        if (this.myTables.length === 0) {
            this.myTablesContainer.innerHTML = `
                <div class="border-2 border-dashed border-gray-200 rounded-xl px-4 py-8 text-center">
                    <svg class="w-12 h-12 mx-auto text-gray-300 mb-2" style="width: 48px; height: 48px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
                    </svg>
                    <p class="text-sm text-gray-400">No hay mesas asignadas aún</p>
                </div>
            `;
            return;
        }

        this.myTablesContainer.innerHTML = `
            <div class="assigned-tables-scroll">
                ${this.myTables.map(table => `
                    <div class="assigned-table-token"
                         data-table-info="${table.table_number}"
                         data-table-number="${table.table_number}"
                         data-zone="${table.zone}">
                        <div class="assigned-table-token__info">
                            <p class="assigned-table-token__number">Mesa ${this.formatDisplayTable(table.zone, table.table_number)}</p>
                            <p class="assigned-table-token__zone">${table.zone} · ${table.capacity} personas</p>
                        </div>
                        <button
                            class="assigned-table-token__remove"
                            data-table-id="${table.id}"
                            onclick="event.stopPropagation(); window.tableAssignmentManager?.unassignTable(${table.id})"
                            title="Quitar mesa"
                        >
                            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                            </svg>
                        </button>
                    </div>
                `).join('')}
            </div>
        `;
    }

    private renderAvailableTables(): void {
        if (!this.availableTablesContainer) return;

        if (!this.allTables.length) {
            this.availableTablesContainer.innerHTML = `
                <div class="col-span-full border-2 border-dashed border-red-200 bg-red-50 rounded-xl px-4 py-8 text-center">
                    <p class="text-sm text-red-700 font-medium" style="margin: 0;">No se pudieron cargar las mesas</p>
                    <p class="text-xs text-red-600" style="margin: 0.5rem 0 0;">Intenta de nuevo en unos segundos.</p>
                </div>
            `;
            return;
        }

        // Get selected zone filter
        const selectedZone = this.zoneFilter?.value || 'all';

        // Filter tables
        let availableTables = this.allTables.filter(table => {
            // Exclude already assigned tables
            const isMyTable = this.myTables.some(t => t.id === table.id);
            return !isMyTable;
        });

        // Apply zone filter
        if (selectedZone !== 'all') {
            availableTables = availableTables.filter(t => t.zone === selectedZone);
        }

        // Get unique zones for filter
        const zones = Array.from(new Set(this.allTables.map(t => t.zone).filter(Boolean)));

        // Update zone filter options
        if (this.zoneFilter) {
            const previous = this.zoneFilter.value || 'all';
            this.zoneFilter.innerHTML = `
                <option value="all">Todas las zonas</option>
                ${zones.map(zone => `<option value="${zone}">${zone}</option>`).join('')}
            `;
            if (previous !== 'all' && zones.includes(previous)) {
                this.zoneFilter.value = previous;
            }
        }

        if (availableTables.length === 0) {
            this.availableTablesContainer.innerHTML = `
                <div class="col-span-full border-2 border-dashed border-yellow-200 bg-yellow-50 rounded-xl px-4 py-8 text-center">
                    <svg class="w-12 h-12 mx-auto text-yellow-400 mb-2" style="width: 48px; height: 48px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                    </svg>
                    <p class="text-sm text-yellow-700 font-medium">No hay mesas disponibles para asignar</p>
                </div>
            `;
            return;
        }

        this.availableTablesContainer.innerHTML = availableTables.map(table => {
            const isSelected = this.selectedTables.has(table.id);
            return `
                <div
                    class="available-table-card ${isSelected ? 'selected' : ''}"
                    data-table-id="${table.id}"
                    onclick="window.tableAssignmentManager?.toggleTableSelection(${table.id})"
                >
                    <div class="available-table-card__checkmark">
                        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"></path>
                        </svg>
                    </div>
                    <p class="available-table-card__number">${this.formatDisplayTable(table.zone, table.table_number)}</p>
                    <div class="available-table-card__meta">
                        <p class="available-table-card__zone">${table.zone}</p>
                        <p class="available-table-card__capacity">👥 ${table.capacity} personas</p>
                    </div>
                </div>
            `;
        }).join('');
    }

    public toggleTableSelection(tableId: number): void {
        if (this.selectedTables.has(tableId)) {
            this.selectedTables.delete(tableId);
        } else {
            this.selectedTables.add(tableId);
        }

        this.renderAvailableTables();

        // Update button state
        this.updateAcceptButtons();
    }

    private updateAcceptButtons(): void {
        const hasSelection = this.selectedTables.size > 0;
        if (!this.assignBtn) return;
        this.assignBtn.disabled = !hasSelection;
        this.assignBtn.classList.toggle('btn--primary', hasSelection);
        this.assignBtn.classList.toggle('btn--secondary', !hasSelection);
    }

    private async assignSelectedTables(): Promise<void> {
        if (this.selectedTables.size === 0) {
            this.showToast('Selecciona al menos una mesa', 'warning');
            return;
        }

        const tableIds = Array.from(this.selectedTables);

        // First, check for conflicts
        try {
            const conflictsResponse = await requestJSON<{ conflicts: ConflictInfo[] }>('/api/table-assignments/check-conflicts', {
                method: 'POST',
                body: { table_ids: tableIds }
            });

            if (conflictsResponse.conflicts && conflictsResponse.conflicts.length > 0) {
                // Show confirmation modal
                this.pendingAssignment = tableIds;
                this.showConflictModal(conflictsResponse.conflicts);
                return;
            }
        } catch (error: any) {
            console.error('[TABLE_ASSIGNMENT] Error checking conflicts:', error);
            // Continue with assignment if check fails
        }

        // No conflicts, proceed with assignment
        await this.performAssignment(tableIds, false);
    }

    private async performAssignment(tableIds: number[], force: boolean): Promise<void> {
        try {
            const response: AssignmentResponse = await requestJSON('/api/table-assignments/assign', {
                method: 'POST',
                body: {
                    table_ids: tableIds,
                    force: force
                }
            });

            let message = '';
            if (response.assigned.length > 0) {
                message += `Mesas asignadas: ${response.assigned.map((num: string) => this.formatTableCode(num)).join(', ')}. `;
            }
            if (response.already_assigned.length > 0) {
                message += `Ya asignadas: ${response.already_assigned.map((num: string) => this.formatTableCode(num)).join(', ')}. `;
            }
            if (response.conflicts.length > 0) {
                message += `Conflictos: ${response.conflicts.map(c => `${this.formatTableCode(c.table_number)} (${c.reason})`).join(', ')}`;
            }

            this.showToast(message || 'Mesas asignadas correctamente', 'success');

            // Clear selection and reload
            this.selectedTables.clear();
            this.updateAcceptButtons();
            await this.loadMyTables();
            await this.loadAllTables();
            this.renderMyTables();
            this.renderAvailableTables();

            // Refresh waiter board if available
            if ((window as any).refreshWaiterOrders) {
                (window as any).refreshWaiterOrders();
            }

            // Refresh assigned tables display
            this.refreshAssignedTablesDisplay();

            // Refresh tables list if available
            const tablesManager = (window as any).tablesManager;
            if (tablesManager?.refresh) {
                console.log('[TABLE_ASSIGNMENT] Refreshing tables list after assignment');
                await tablesManager.refresh();
            }
        } catch (error: any) {
            console.error('[TABLE_ASSIGNMENT] Error assigning tables:', error);
            this.showToast(error.message || 'Error al asignar mesas', 'danger');
        }
    }

    public async unassignTable(tableId: number): Promise<void> {
        if (!confirm('¿Estás seguro de que quieres desasignar esta mesa?')) {
            return;
        }

        try {
            await requestJSON(`/api/table-assignments/unassign/${tableId}`, {
                method: 'DELETE'
            });

            this.showToast('Mesa desasignada correctamente', 'success');

            // Reload tables
            await this.loadMyTables();
            await this.loadAllTables();
            this.renderMyTables();
            this.renderAvailableTables();

            // Refresh waiter board if available
            if ((window as any).refreshWaiterOrders) {
                (window as any).refreshWaiterOrders();
            }

            // Refresh assigned tables display
            this.refreshAssignedTablesDisplay();

            // Refresh tables list if available
            const tablesManager = (window as any).tablesManager;
            if (tablesManager?.refresh) {
                console.log('[TABLE_ASSIGNMENT] Refreshing tables list after unassignment');
                await tablesManager.refresh();
            }
        } catch (error: any) {
            console.error('[TABLE_ASSIGNMENT] Error unassigning table:', error);
            this.showToast(error.message || 'Error al desasignar mesa', 'danger');
        }
    }

    private startPolling(): void {
        // Poll for transfer requests every 15 seconds
        this.pollForTransferRequests();
        this.pollingInterval = window.setInterval(() => {
            this.pollForTransferRequests();
        }, 15000);
    }

    private stopPolling(): void {
        if (this.pollingInterval !== null) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }

    private async pollForTransferRequests(): Promise<void> {
        try {
            const response = await requestJSON('/api/table-assignments/transfer-requests', {
                method: 'GET'
            });

            if (response.requests && response.requests.length > 0) {
                // Show first pending request
                this.showTransferRequestModal(response.requests[0]);
            }
        } catch (error) {
            console.error('[TABLE_ASSIGNMENT] Error polling transfer requests:', error);
        }
    }

    private showTransferRequestModal(request: TransferRequest): void {
        if (!this.transferModal) return;

        // Set request ID in modal data
        this.transferModal.dataset.requestId = String(request.id);

        // Update modal content
        const messageEl = document.getElementById('transfer-request-message');
        if (messageEl) {
            messageEl.textContent = `${request.from_waiter_name} quiere transferirte la Mesa ${this.formatTableCode(request.table_number)}`;
        }

        const noteEl = document.getElementById('transfer-request-note');
        if (noteEl && request.message) {
            noteEl.textContent = `Nota: ${request.message}`;
            noteEl.style.display = 'block';
        } else if (noteEl) {
            noteEl.style.display = 'none';
        }

        // Reset checkbox
        const checkbox = document.getElementById('transfer-orders-checkbox') as HTMLInputElement;
        if (checkbox) {
            checkbox.checked = false;
        }

        // Show modal
        this.transferModal.classList.add('active');
    }

    private closeTransferModal(): void {
        if (!this.transferModal) return;

        this.transferModal.classList.remove('active');
        delete this.transferModal.dataset.requestId;
    }

    private async acceptTransferRequest(requestId: number, transferOrders: boolean): Promise<void> {
        try {
            await requestJSON(`/api/table-assignments/transfer-request/${requestId}/accept`, {
                method: 'POST',
                body: {
                    transfer_orders: transferOrders
                }
            });

            this.showToast('Transferencia aceptada correctamente', 'success');
            this.closeTransferModal();

            // Reload my tables
            await this.loadMyTables();
            this.renderMyTables();

            // Refresh waiter board if available
            if ((window as any).refreshWaiterOrders) {
                (window as any).refreshWaiterOrders();
            }

            // Refresh assigned tables display
            this.refreshAssignedTablesDisplay();
        } catch (error: any) {
            console.error('[TABLE_ASSIGNMENT] Error accepting transfer:', error);
            this.showToast(error.message || 'Error al aceptar transferencia', 'danger');
        }
    }

    private async rejectTransferRequest(requestId: number): Promise<void> {
        try {
            await requestJSON(`/api/table-assignments/transfer-request/${requestId}/reject`, {
                method: 'POST'
            });

            this.showToast('Transferencia rechazada', 'info');
            this.closeTransferModal();
        } catch (error: any) {
            console.error('[TABLE_ASSIGNMENT] Error rejecting transfer:', error);
            this.showToast(error.message || 'Error al rechazar transferencia', 'danger');
        }
    }

    private showToast(message: string, variant: 'success' | 'danger' | 'warning' | 'info' = 'info'): void {
        // Try to use existing toast system
        if ((window as any).showToast) {
            (window as any).showToast(message, variant);
            return;
        }

        // Fallback to alert
        alert(message);
    }

    private setupAssignedTablesDisplay(): void {
        this.assignedTablesDisplay = document.getElementById('waiter-assigned-tables-display');
        this.assignedTablesList = document.getElementById('assigned-tables-list');
    }

    private async loadAndDisplayAssignedTables(): Promise<void> {
        try {
            const response = await requestJSON('/api/table-assignments/my-tables', {
                method: 'GET'
            });

            if (response.tables && response.tables.length > 0) {
                this.displayAssignedTables(response.tables);
            } else {
                this.hideAssignedTablesDisplay();
            }
        } catch (error) {
            console.error('[TABLE_ASSIGNMENT] Error loading assigned tables for display:', error);
            this.hideAssignedTablesDisplay();
        }
    }

    private displayAssignedTables(tables: Table[]): void {
        // Update legacy display
        if (this.assignedTablesDisplay && this.assignedTablesList) {
            this.assignedTablesList.innerHTML = tables.map(table => `
                <div class="assigned-table-chip">
                    <span class="assigned-table-chip__icon">📍</span>
                    <div class="assigned-table-chip__info">
                        <span class="assigned-table-chip__number">${this.formatDisplayTable(table.zone, table.table_number)}</span>
                        <span class="assigned-table-chip__zone">${table.zone}</span>
                    </div>
                </div>
            `).join('');

            this.assignedTablesDisplay.style.display = 'block';
        }

        // Update modern header badges with area-based colors
        const headerBadges = document.getElementById('header-tables-badges');
        if (headerBadges) {
            headerBadges.innerHTML = tables.map(table => {
                const zoneClass = this.getZoneClass(table.zone);
                const acronym = this.getTableAcronym(table.zone, table.table_number);
                // Extract number from table_number for cleaner display
                const numberMatch = (table.table_number || '').match(/(\d+)/);
                const tableNum = numberMatch ? numberMatch[1].padStart(2, '0') : '01';
                const descriptiveName = `${table.zone} Mesa ${tableNum}`;
                return `
                    <button type="button" class="table-badge ${zoneClass}"
                        title="${descriptiveName}"
                        aria-label="Ir a mesa ${acronym}"
                        data-table-number="${acronym}">
                        <span class="table-badge__text">${acronym}</span>
                    </button>
                `;
            }).join('');
        }
    }

    private getZoneClass(zone: string): string {
        const zoneLower = zone.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");

        if (zoneLower.includes('terraz') || zoneLower.includes('terrace') || zoneLower.includes('exterior')) {
            return 'table-badge--terraza';
        } else if (zoneLower.includes('bar') || zoneLower.includes('barra')) {
            return 'table-badge--bar';
        } else if (zoneLower.includes('interior') || zoneLower.includes('salon') || zoneLower.includes('comedor')) {
            return 'table-badge--interior';
        } else if (zoneLower.includes('vip')) {
            return 'table-badge--vip';
        }

        return 'table-badge--default';
    }

    private getZonePrefix(zone: string): string {
        const zoneLower = zone.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        if (zoneLower.includes('vip')) return 'V';
        if (zoneLower.includes('roof')) return 'R';
        if (zoneLower.includes('terraz') || zoneLower.includes('terrace') || zoneLower.includes('exterior')) return 'T';
        if (zoneLower.includes('bar') || zoneLower.includes('barra')) return 'B';
        if (zoneLower.includes('interior') || zoneLower.includes('salon') || zoneLower.includes('comedor')) return 'I';
        return zone.trim().charAt(0).toUpperCase() || '';
    }

    private sanitizeBasePrefix(value: string): string {
        const cleaned = (value || 'M').replace(/[^A-Za-z0-9]/g, '').toUpperCase();
        return cleaned.slice(0, 3) || 'M';
    }

    private formatTableCode(tableNumber: string): string {
        const match = (tableNumber || '').match(/(\d+)/);
        const digits = match ? match[1] : '1';
        const base = this.sanitizeBasePrefix(this.tableBasePrefix);
        return `${base}${digits.padStart(2, '0')}`;
    }

    private formatDisplayTable(zone: string, tableNumber: string): string {
        const prefix = this.getZonePrefix(zone);
        const code = this.formatTableCode(tableNumber);
        return prefix ? `${prefix}-${code}` : code;
    }

    private getTableAcronym(zone: string, tableNumber: string): string {
        return this.formatDisplayTable(zone, tableNumber);
    }

    private hideAssignedTablesDisplay(): void {
        if (this.assignedTablesDisplay) {
            this.assignedTablesDisplay.style.display = 'none';
        }

        // Clear modern header badges
        const headerBadges = document.getElementById('header-tables-badges');
        if (headerBadges) {
            headerBadges.innerHTML = '';
        }
    }

    public async refreshAssignedTablesDisplay(): Promise<void> {
        // Update the header display
        await this.loadAndDisplayAssignedTables();

        // If modal is open, also refresh the modal's table list
        if (this.modal && this.modal.classList.contains('active')) {
            console.log('[TABLE_ASSIGNMENT] Modal is open, refreshing table lists...');
            await this.loadMyTables();
            this.renderMyTables();
        }
    }

    private async loadAutoAssignPreference(): Promise<void> {
        try {
            const response = await requestJSON<{ preferences: Record<string, any> }>('/api/employees/me/preferences');
            const autoAssign = response.preferences?.auto_assign_table_on_order_accept ?? true;

            const checkbox = document.getElementById('auto-assign-table-on-order-accept') as HTMLInputElement;
            if (checkbox) {
                checkbox.checked = autoAssign;
            }
            console.log('[TABLE_ASSIGNMENT] Auto-assign preference loaded:', autoAssign);
        } catch (error) {
            console.error('[TABLE_ASSIGNMENT] Error loading auto-assign preference:', error);
            // Default to true if error
            const checkbox = document.getElementById('auto-assign-table-on-order-accept') as HTMLInputElement;
            if (checkbox) {
                checkbox.checked = true;
            }
        }
    }

    private async saveAutoAssignPreference(value: boolean): Promise<void> {
        try {
            await requestJSON('/api/employees/me/preferences', {
                method: 'PUT',
                body: { auto_assign_table_on_order_accept: value }
            });
            console.log('[TABLE_ASSIGNMENT] Auto-assign preference saved:', value);
            this.showToast(
                value ? 'Auto-asignación de mesas activada' : 'Auto-asignación de mesas desactivada',
                'success'
            );
        } catch (error) {
            console.error('[TABLE_ASSIGNMENT] Error saving auto-assign preference:', error);
            this.showToast('Error al guardar preferencia', 'danger');
        }
    }
}

// Initialize and expose globally
export function initTableAssignment(): TableAssignmentManager {
    console.log('[TABLE_ASSIGNMENT] Initializing table assignment module...');
    const manager = new TableAssignmentManager();
    (window as any).tableAssignmentManager = manager;
    console.log('[TABLE_ASSIGNMENT] Module initialized successfully');
    return manager;
}
