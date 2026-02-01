interface EmployeeRecord {
    id: number;
    name?: string | null;
    email?: string | null;
    role?: string | null;
    permissions?: string[];
}

interface RolePermission {
    code: string;
    name: string;
    category?: string;
    roles?: string[];
}

interface ApiResponse<T> {
    status: string;
    message?: string;
    data?: T;
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

export function initRoleManagement(): void {
    document.addEventListener('DOMContentLoaded', () => {
        const assignmentRoot = document.querySelector<HTMLElement>('[data-role-assignment-root]');
        const permissionsRoot = document.querySelector<HTMLElement>('[data-role-permissions-root]');
        if (!assignmentRoot && !permissionsRoot) return;
        const manager = new RoleManagementManager(assignmentRoot, permissionsRoot);
        manager.initialize();
    });
}

class RoleManagementManager {
    private assignmentRoot: HTMLElement | null;
    private permissionsRoot: HTMLElement | null;

    private searchInput: HTMLInputElement | null;
    private searchButton: HTMLButtonElement | null;
    private resultsContainer: HTMLElement | null;
    private panel: HTMLElement | null;
    private selectedName: HTMLElement | null;
    private selectedEmail: HTMLElement | null;
    private closePanelBtn: HTMLButtonElement | null;
    private roleSelector: HTMLElement | null;
    private permissionsList: HTMLElement | null;

    private systemRolesList: HTMLElement | null;
    private selectedRoleTitle: HTMLElement | null;
    private selectedRoleDescription: HTMLElement | null;
    private permissionsGrid: HTMLElement | null;
    private restoreBtn: HTMLButtonElement | null;

    private currentEmployee: EmployeeRecord | null = null;
    private systemPermissions: RolePermission[] = [];
    private currentSystemRole = 'super_admin';

    constructor(assignmentRoot: HTMLElement | null, permissionsRoot: HTMLElement | null) {
        this.assignmentRoot = assignmentRoot;
        this.permissionsRoot = permissionsRoot;
        this.searchInput = assignmentRoot?.querySelector('#employee-role-search') || null;
        this.searchButton = assignmentRoot?.querySelector('#employee-role-search-btn') || null;
        this.resultsContainer = assignmentRoot?.querySelector('#employee-role-search-results') || null;
        this.panel = assignmentRoot?.querySelector('#employee-role-panel') || null;
        this.selectedName = assignmentRoot?.querySelector('#selected-employee-name') || null;
        this.selectedEmail = assignmentRoot?.querySelector('#selected-employee-email') || null;
        this.closePanelBtn = assignmentRoot?.querySelector('#close-employee-role-panel') || null;
        this.roleSelector = assignmentRoot?.querySelector('#employee-role-selector') || null;
        this.permissionsList = assignmentRoot?.querySelector('#employee-permissions-list') || null;

        this.systemRolesList = permissionsRoot?.querySelector('#system-roles-list') || null;
        this.selectedRoleTitle = permissionsRoot?.querySelector('#selected-role-title') || null;
        this.selectedRoleDescription = permissionsRoot?.querySelector('#selected-role-description') || null;
        this.permissionsGrid = permissionsRoot?.querySelector('#permissions-grid') || null;
        this.restoreBtn = permissionsRoot?.querySelector('#restore-role-permissions') || null;
    }

    initialize(): void {
        if (this.assignmentRoot) {
            this.attachAssignmentEvents();
        }
        if (this.permissionsRoot) {
            this.attachPermissionsEvents();
            void this.loadSystemPermissions();
        }
    }

    private attachAssignmentEvents(): void {
        this.searchButton?.addEventListener('click', () => this.searchEmployees());
        this.searchInput?.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                void this.searchEmployees();
            }
        });
        this.closePanelBtn?.addEventListener('click', () => this.closePanel());
    }

    private attachPermissionsEvents(): void {
        this.systemRolesList?.addEventListener('click', (event) => {
            const btn = (event.target as HTMLElement).closest<HTMLButtonElement>('.system-role-btn');
            if (btn?.dataset.role) {
                this.switchSystemRole(btn.dataset.role);
            }
        });
        this.restoreBtn?.addEventListener('click', () => {
            void this.restoreDefaultPermissions();
        });
    }

    private async searchEmployees(): Promise<void> {
        if (!this.searchInput || !this.resultsContainer) return;
        const query = this.searchInput.value.trim();
        if (!query) {
            this.resultsContainer.style.display = 'none';
            this.resultsContainer.innerHTML = '';
            return;
        }
        this.resultsContainer.innerHTML =
            '<p style="text-align:center;padding:1rem;color:#64748b;">🔍 Buscando...</p>';
        this.resultsContainer.style.display = 'block';
        try {
            const response = await fetch(`/api/employees/search?q=${encodeURIComponent(query)}`);
            if (!response.ok) {
                throw new Error('Error al buscar empleados');
            }
            const result: ApiResponse<{ employees: EmployeeRecord[] }> = await response.json();
            const payload = unwrapApiResponse<{ employees?: EmployeeRecord[] }>(result, 'Error al buscar empleados');
            const employees = payload.employees || [];
            if (!employees.length) {
                this.resultsContainer.innerHTML = `<p style="text-align:center;padding:2rem;color:#64748b;">No se encontraron empleados con "<strong>${query}</strong>"</p>`;
                return;
            }
            this.renderSearchResults(employees);
        } catch (error) {
            console.error('[Roles] search', error);
            this.resultsContainer.innerHTML =
                '<p style="text-align:center;padding:2rem;color:#ef4444;">Error de conexión</p>';
        }
    }

    private renderSearchResults(employees: EmployeeRecord[]): void {
        if (!this.resultsContainer) return;
        const roleNames: Record<string, string> = {
            super_admin: 'Super Admin',
            admin_roles: 'Administrador',
            manager: 'Gerente',
            waiter: 'Mesero',
            chef: 'Chef',
            cashier: 'Cajero'
        };
        this.resultsContainer.innerHTML = employees
            .map(
                (emp) => `
            <div class="employee-role-search-result-item" data-employee-id="${emp.id}">
                <div class="employee-role-search-result-info">
                    <h4>${emp.name || 'Sin nombre'}</h4>
                    <p>${emp.email || 'Sin email'} ${emp.id ? `• ID: ${emp.id}` : ''}</p>
                </div>
                <div style="text-align:right;">
                    <span style="color:#667eea;font-size:0.875rem;font-weight:600;">
                        ${roleNames[emp.role || ''] || emp.role || ''}
                    </span>
                </div>
            </div>`
            )
            .join('');
        this.resultsContainer.querySelectorAll('.employee-role-search-result-item').forEach((item) => {
            item.addEventListener('click', () => {
                const id = Number((item as HTMLElement).dataset.employeeId);
                if (Number.isFinite(id)) {
                    void this.selectEmployee(id);
                }
            });
        });
    }

    private async selectEmployee(employeeId: number): Promise<void> {
        if (!this.panel || !this.selectedName || !this.selectedEmail) return;
        this.panel.style.display = 'block';
        this.selectedName.textContent = 'Cargando...';
        this.selectedEmail.textContent = '';
        try {
            const response = await fetch(`/api/employees/${employeeId}`);
            if (!response.ok) {
                throw new Error('Error al cargar información del empleado');
            }
            const result: ApiResponse<{ employee: EmployeeRecord }> = await response.json();
            const payload = unwrapApiResponse<{ employee?: EmployeeRecord }>(result, 'Error al cargar información del empleado');
            this.currentEmployee = (payload.employee || payload) as EmployeeRecord;
            this.selectedName.textContent = this.currentEmployee.name || 'Empleado';
            this.selectedEmail.textContent = this.currentEmployee.email || 'Sin email';
            this.renderRoleSelector();
            this.renderEmployeePermissions();
            if (this.resultsContainer) {
                this.resultsContainer.style.display = 'none';
            }
        } catch (error) {
            console.error('[Roles] select employee', error);
            alert('Error al cargar información del empleado');
            this.panel.style.display = 'none';
            this.currentEmployee = null;
        }
    }

    private closePanel(): void {
        if (!this.panel) return;
        this.panel.style.display = 'none';
        this.currentEmployee = null;
    }

    private renderRoleSelector(): void {
        if (!this.roleSelector || !this.currentEmployee) return;
        const roles = [
            { key: 'super_admin', icon: '👑', name: 'Super Admin' },
            { key: 'admin_roles', icon: '⚙️', name: 'Administrador' },
            { key: 'manager', icon: '📊', name: 'Gerente' },
            { key: 'waiter', icon: '🍽️', name: 'Mesero' },
            { key: 'chef', icon: '👨‍🍳', name: 'Chef' },
            { key: 'cashier', icon: '💰', name: 'Cajero' }
        ];
        this.roleSelector.innerHTML = roles
            .map(
                (role) => `
                <div class="role-option ${this.currentEmployee?.role === role.key ? 'active' : ''}"
                     data-role="${role.key}">
                    <span class="role-option-icon">${role.icon}</span>
                    <span class="role-option-name">${role.name}</span>
                </div>`
            )
            .join('');
        this.roleSelector.querySelectorAll('.role-option').forEach((option) => {
            option.addEventListener('click', () => {
                const roleKey = (option as HTMLElement).dataset.role;
                if (roleKey) {
                    void this.assignRole(roleKey);
                }
            });
        });
    }

    private async assignRole(roleKey: string): Promise<void> {
        if (!this.currentEmployee) return;
        try {
            const response = await fetch(`/api/employees/${this.currentEmployee.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ role: roleKey })
            });
            if (!response.ok) {
                throw new Error('Error al asignar rol');
            }
            const result = await response.json();
            unwrapApiResponse(result, 'Error al asignar rol');
            this.currentEmployee.role = roleKey;
            this.renderRoleSelector();
            window.showToast?.('Rol actualizado exitosamente', 'success');
        } catch (error) {
            console.error('[Roles] assign role', error);
            alert('Error al asignar rol');
        }
    }

    private renderEmployeePermissions(): void {
        if (!this.permissionsList || !this.currentEmployee) return;
        const permissions = this.currentEmployee.permissions || [];
        if (!permissions.length) {
            this.permissionsList.innerHTML =
                '<p style="text-align:center;padding:2rem;color:#64748b;">Este empleado no tiene permisos adicionales</p>';
            return;
        }
        this.permissionsList.innerHTML = permissions
            .map(
                (perm) => `
                <div class="permission-item">
                    <div class="permission-info">
                        <div class="permission-name">${perm}</div>
                        <div class="permission-description">Permiso adicional del sistema</div>
                    </div>
                    <button type="button" class="btn btn--small btn--danger" data-permission="${perm}">🗑️ Revocar</button>
                </div>`
            )
            .join('');
        this.permissionsList.querySelectorAll('button[data-permission]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const code = (btn as HTMLElement).dataset.permission;
                if (code) {
                    void this.revokePermission(code);
                }
            });
        });
    }

    private async revokePermission(permissionCode: string): Promise<void> {
        if (!this.currentEmployee) return;
        if (!confirm(`¿Revocar el permiso "${permissionCode}"?`)) return;
        try {
            const response = await fetch(`/api/roles/employees/${this.currentEmployee.id}/revoke`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ permission_code: permissionCode })
            });
            if (!response.ok) {
                throw new Error('Error al revocar permiso');
            }
            const result = await response.json();
            unwrapApiResponse(result, 'Error al revocar permiso');
            await this.selectEmployee(this.currentEmployee.id);
            window.showToast?.('Permiso revocado exitosamente', 'success');
        } catch (error) {
            console.error('[Roles] revoke permission', error);
            alert('Error al revocar permiso');
        }
    }

    private async loadSystemPermissions(): Promise<void> {
        if (!this.permissionsRoot) return;
        try {
            const response = await fetch('/api/permissions/system');
            if (!response.ok) {
                throw new Error('Error al cargar permisos');
            }
            const result: ApiResponse<{ permissions: RolePermission[] }> = await response.json();
            const payload = unwrapApiResponse<{ permissions?: RolePermission[] }>(result, 'Error al cargar permisos');
            this.systemPermissions = payload.permissions || [];
            this.renderSystemRoleButtons();
            this.renderRolePermissions();
        } catch (error) {
            console.error('[Roles] load system permissions', error);
            if (this.permissionsGrid) {
                this.permissionsGrid.innerHTML =
                    '<p style="text-align:center;color:#ef4444;">Error al cargar permisos</p>';
            }
        }
    }

    private renderSystemRoleButtons(): void {
        this.systemRolesList?.querySelectorAll('.system-role-btn').forEach((btn) => {
            btn.classList.toggle('active', btn.dataset.role === this.currentSystemRole);
        });
        this.updateRoleHeader();
    }

    private updateRoleHeader(): void {
        if (!this.selectedRoleTitle || !this.selectedRoleDescription) return;
        const roleInfo: Record<
            string,
            {
                title: string;
                description: string;
            }
        > = {
            super_admin: { title: 'Super Admin', description: 'Acceso completo al sistema' },
            admin_roles: { title: 'Administrador', description: 'Gestión completa del restaurante' },
            manager: { title: 'Gerente', description: 'Supervisión y reportes' },
            waiter: { title: 'Mesero', description: 'Atención de mesas y órdenes' },
            chef: { title: 'Chef', description: 'Gestión de cocina' },
            cashier: { title: 'Cajero', description: 'Cobro y facturación' }
        };
        this.selectedRoleTitle.textContent = roleInfo[this.currentSystemRole]?.title || this.currentSystemRole;
        this.selectedRoleDescription.textContent =
            roleInfo[this.currentSystemRole]?.description || 'Configuración de permisos del rol';
    }

    private renderRolePermissions(): void {
        if (!this.permissionsGrid) return;
        const categories: Record<
            string,
            {
                icon: string;
                title: string;
                permissions: RolePermission[];
            }
        > = {
            orders: { icon: '📋', title: 'Órdenes', permissions: [] },
            menu: { icon: '📖', title: 'Menú', permissions: [] },
            tables: { icon: '🪑', title: 'Mesas', permissions: [] },
            reports: { icon: '📊', title: 'Reportes', permissions: [] },
            settings: { icon: '⚙️', title: 'Configuración', permissions: [] },
            other: { icon: '📦', title: 'Otros', permissions: [] }
        };
        this.systemPermissions.forEach((permission) => {
            const bucket = categories[permission.category || 'other'] || categories.other;
            bucket.permissions.push(permission);
        });
        this.permissionsGrid.innerHTML = Object.values(categories)
            .filter((bucket) => bucket.permissions.length)
            .map(
                (bucket) => `
                <div class="permission-category">
                    <div class="permission-category-header">
                        <span class="permission-category-icon">${bucket.icon}</span>
                        <span class="permission-category-title">${bucket.title}</span>
                    </div>
                    <div class="permission-toggles">
                        ${bucket.permissions
                            .map(
                                (perm) => `
                            <div class="permission-toggle">
                                <span class="permission-toggle-label">${perm.name}</span>
                                <label class="switch">
                                    <input type="checkbox" data-permission="${perm.code}" ${
                                    perm.roles?.includes(this.currentSystemRole) ? 'checked' : ''
                                }>
                                    <span class="slider round"></span>
                                </label>
                            </div>`
                            )
                            .join('')}
                    </div>
                </div>`
            )
            .join('');
        this.permissionsGrid.querySelectorAll('input[data-permission]').forEach((input) => {
            input.addEventListener('change', () => {
                const perm = (input as HTMLInputElement).dataset.permission;
                const enabled = (input as HTMLInputElement).checked;
                if (perm) {
                    void this.toggleRolePermission(this.currentSystemRole, perm, enabled);
                }
            });
        });
    }

    private async toggleRolePermission(roleKey: string, permissionCode: string, enabled: boolean): Promise<void> {
        const endpoint = enabled
            ? `/api/permissions/roles/${roleKey}/add`
            : `/api/permissions/roles/${roleKey}/remove`;
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ permission_code: permissionCode })
            });
            if (!response.ok) {
                throw new Error('Error al actualizar permiso');
            }
            const result = await response.json();
            unwrapApiResponse(result, 'Error al actualizar permiso');
            window.showToast?.(`Permiso ${enabled ? 'agregado' : 'removido'} exitosamente`, 'success');
            await this.loadSystemPermissions();
        } catch (error) {
            console.error('[Roles] toggle permission', error);
            alert('Error al actualizar permiso');
            await this.loadSystemPermissions();
        }
    }

    private async restoreDefaultPermissions(): Promise<void> {
        const roleKey = this.currentSystemRole;
        if (!confirm('¿Restaurar los permisos por defecto para este rol?')) return;
        try {
            const response = await fetch(`/api/permissions/roles/${roleKey}/reset`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            if (!response.ok) {
                const result = await response.json().catch(() => ({}));
                throw new Error(result.error || 'Error al restaurar permisos');
            }
            await this.loadSystemPermissions();
            window.showToast?.('Permisos restaurados al estado por defecto', 'success');
        } catch (error) {
            console.error('[Roles] restore defaults', error);
            alert('Error al restaurar permisos');
        }
    }

    private switchSystemRole(roleKey: string): void {
        this.currentSystemRole = roleKey;
        this.renderSystemRoleButtons();
        this.renderRolePermissions();
    }
}
