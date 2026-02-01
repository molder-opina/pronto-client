/**
 * Roles Management - OOP Refactored
 * Handles custom role creation, editing, and permission management
 */

/**
 * Notification Helper
 */
class NotificationHelper {
    static show(message, type = 'info') {
        if (typeof window.showNotification === 'function') {
            window.showNotification(message, type);
        } else {
            alert(message);
        }
    }
}

/**
 * HTML Utilities
 */
class HtmlUtils {
    static escape(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

/**
 * Role Modal Manager
 */
class RoleModalManager {
    constructor(rolesManager) {
        this.rolesManager = rolesManager;
        this.modal = document.getElementById('role-modal');
        this.form = document.getElementById('role-form');
        this.modalTitle = document.getElementById('modal-title');
        this.roleCodeInput = document.getElementById('role_code');
        this.tabButtons = Array.from(this.modal?.querySelectorAll('.modal-tab') || []);
        this.tabPanels = Array.from(this.modal?.querySelectorAll('.modal-tab-panel') || []);
    }

    open(role = null) {
        if (role) {
            this.openEdit(role);
        } else {
            this.openCreate();
        }
    }

    openCreate() {
        this.rolesManager.isEditing = false;
        this.rolesManager.currentRole = null;

        this.modalTitle.textContent = 'Crear Nuevo Rol';
        this.form.reset();
        this.roleCodeInput.disabled = false;
        this.clearPermissions();
        this.setActiveTab('info');
        this.modal.classList.add('active');
    }

    openEdit(role) {
        this.rolesManager.isEditing = true;
        this.rolesManager.currentRole = role;

        this.modalTitle.textContent = 'Editar Rol';
        this.populateForm(role);
        this.roleCodeInput.disabled = true;
        this.setActiveTab('info');
        this.modal.classList.add('active');
    }

    close() {
        this.modal.classList.remove('active');
        this.rolesManager.isEditing = false;
        this.rolesManager.currentRole = null;
    }

    clearPermissions() {
        document.querySelectorAll('.permission-checks input[type="checkbox"]').forEach(cb => {
            cb.checked = false;
        });
    }

    populateForm(role) {
        document.getElementById('role_code').value = role.role_code;
        document.getElementById('role_name').value = role.role_name;
        document.getElementById('description').value = role.description || '';
        document.getElementById('color').value = role.color || '#4F46E5';
        document.getElementById('icon').value = role.icon || '';
        document.getElementById('is_active').checked = role.is_active;

        this.clearPermissions();

        if (role.permissions) {
            role.permissions.forEach(perm => {
                const checkbox = document.querySelector(
                    `input[data-resource="${perm.resource_type}"][data-action="${perm.action}"]`
                );
                if (checkbox) {
                    checkbox.checked = perm.allowed;
                }
            });
        }
    }

    collectFormData() {
        const formData = new FormData(this.form);
        return {
            role_code: formData.get('role_code'),
            role_name: formData.get('role_name'),
            description: formData.get('description'),
            color: formData.get('color'),
            icon: formData.get('icon'),
            is_active: formData.get('is_active') === 'on'
        };
    }

    collectPermissions() {
        const permissions = [];
        document.querySelectorAll('.permission-checks input[type="checkbox"]:checked').forEach(cb => {
            permissions.push({
                resource_type: cb.dataset.resource,
                action: cb.dataset.action,
                allowed: true
            });
        });
        return permissions;
    }

    setActiveTab(tabName) {
        if (!this.tabButtons.length || !this.tabPanels.length) return;
        this.tabButtons.forEach((btn) => {
            const isActive = btn.dataset.tab === tabName;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        this.tabPanels.forEach((panel) => {
            panel.classList.toggle('active', panel.dataset.tab === tabName);
        });
    }

    initEventListeners() {
        this.form?.addEventListener('submit', (e) => {
            e.preventDefault();
            const data = this.collectFormData();
            this.rolesManager.save(data, this.collectPermissions());
        });

        this.tabButtons.forEach((btn) => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.tab;
                if (tab) this.setActiveTab(tab);
            });
        });

        this.modal?.addEventListener('click', (e) => {
            if (e.target.id === 'role-modal') {
                this.close();
            }
        });
    }
}

/**
 * Role Card Renderer
 */
class RoleCardRenderer {
    static create(role) {
        const card = document.createElement('div');
        card.className = `role-card ${!role.is_active ? 'inactive' : ''}`;
        card.style.borderLeftColor = role.color || '#4F46E5';

        card.innerHTML = `
            <div class="role-card-header">
                <div class="role-info">
                    <h3>${HtmlUtils.escape(role.role_name)}</h3>
                    <span class="role-code">${HtmlUtils.escape(role.role_code)}</span>
                </div>
                <div class="role-actions">
                    <button class="icon-btn" onclick="window.rolesManager.edit(${role.id})" title="Editar">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                        </svg>
                    </button>
                    <button class="icon-btn delete" onclick="window.rolesManager.delete(${role.id}, '${HtmlUtils.escape(role.role_name)}')" title="Eliminar">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                    </button>
                </div>
            </div>
            <p class="role-description">${HtmlUtils.escape(role.description || 'Sin descripción')}</p>
            <div class="role-stats">
                <div class="stat">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M9 11l3 3L22 4"></path>
                        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
                    </svg>
                    ${role.permissions_count} permisos
                </div>
                <div class="stat">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <circle cx="12" cy="12" r="3"></circle>
                    </svg>
                    ${role.is_active ? 'Activo' : 'Inactivo'}
                </div>
            </div>
        `;

        return card;
    }

    static renderEmpty() {
        return `
            <div style="grid-column: 1/-1; text-align: center; padding: 3rem; color: #64748b;">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin: 0 auto 1rem;">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                    <circle cx="9" cy="7" r="4"></circle>
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                    <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                </svg>
                <p style="font-size: 1.125rem; font-weight: 500; margin: 0;">No hay roles personalizados</p>
                <p style="margin: 0.5rem 0 0 0;">Crea tu primer rol personalizado para empezar</p>
            </div>
        `;
    }
}

/**
 * Roles Manager - Main controller
 */
class RolesManager {
    constructor() {
        this.roles = [];
        this.currentRole = null;
        this.isEditing = false;
        this.container = document.getElementById('roles-list');
        this.modal = new RoleModalManager(this);
    }

    async init() {
        await this.load();
        this.initEventListeners();
        this.modal.initEventListeners();
    }

    async load() {
        try {
            const response = await fetch('/api/roles?include_inactive=true');
            const result = await response.json();

            const payload = result.data || [];
            if (Array.isArray(payload)) {
                this.roles = payload;
                this.render();
            } else if (payload.roles && Array.isArray(payload.roles)) {
                this.roles = payload.roles;
                this.render();
            }
        } catch (error) {
            console.error('Error loading roles:', error);
            NotificationHelper.show('Error al cargar roles', 'error');
        }
    }

    render() {
        if (!this.container) return;
        this.container.innerHTML = '';

        if (this.roles.length === 0) {
            this.container.innerHTML = RoleCardRenderer.renderEmpty();
            return;
        }

        this.roles.forEach(role => {
            const card = RoleCardRenderer.create(role);
            this.container.appendChild(card);
        });
    }

    async edit(roleId) {
        try {
            const response = await fetch(`/api/roles/${roleId}`);
            const result = await response.json();

            if (result.success && result.data) {
                this.modal.open(result.data);
            }
        } catch (error) {
            console.error('Error loading role:', error);
            NotificationHelper.show('Error al cargar rol', 'error');
        }
    }

    async delete(roleId, roleName) {
        if (!confirm(`¿Estás seguro de eliminar el rol "${roleName}"?\n\nEsta acción desactivará el rol.`)) {
            return;
        }

        try {
            const response = await fetch(`/api/roles/${roleId}`, {
                method: 'DELETE'
            });

            const result = await response.json();

            if (result.success) {
                NotificationHelper.show('Rol eliminado correctamente', 'success');
                this.load();
            } else {
                NotificationHelper.show(result.message || 'Error al eliminar rol', 'error');
            }
        } catch (error) {
            console.error('Error deleting role:', error);
            NotificationHelper.show('Error al eliminar rol', 'error');
        }
    }

    async save(formData, permissions) {
        try {
            const data = {
                role_code: formData.role_code,
                role_name: formData.role_name,
                description: formData.description || null,
                color: formData.color || '#4F46E5',
                icon: formData.icon || null,
                is_active: formData.is_active
            };

            if (this.isEditing) {
                await this.updateRole(data, permissions);
            } else {
                await this.createRole(data, permissions);
            }
        } catch (error) {
            console.error('Error saving role:', error);
            NotificationHelper.show('Error al guardar rol', 'error');
        }
    }

    async createRole(data, permissions) {
        data.permissions = permissions;

        const response = await fetch('/api/roles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            NotificationHelper.show('Rol creado correctamente', 'success');
            this.modal.close();
            this.load();
        } else {
            NotificationHelper.show(result.message || 'Error al crear rol', 'error');
        }
    }

    async updateRole(data, permissions) {
        const roleResponse = await fetch(`/api/roles/${this.currentRole.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const roleResult = await roleResponse.json();

        if (!roleResult.success) {
            NotificationHelper.show(roleResult.message || 'Error al actualizar rol', 'error');
            return;
        }

        const permResponse = await fetch(`/api/roles/${this.currentRole.id}/permissions/bulk`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ permissions })
        });

        const permResult = await permResponse.json();

        if (permResult.success) {
            NotificationHelper.show('Rol actualizado correctamente', 'success');
        } else {
            NotificationHelper.show('Rol actualizado pero hubo un error con los permisos', 'warning');
        }

        this.modal.close();
        this.load();
    }

    initEventListeners() {
        const createBtn = document.getElementById('create-role-btn');
        createBtn?.addEventListener('click', () => this.modal.open());

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.modal.close();
            }
        });
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.rolesManager = new RolesManager();
    window.rolesManager.init();
});

// Legacy compatibility
window.editRole = function (roleId) {
    window.rolesManager?.edit(roleId);
};

window.deleteRole = function (roleId, roleName) {
    window.rolesManager?.delete(roleId, roleName);
};

window.openCreateRoleModal = function () {
    window.rolesManager?.modal.open();
};

window.closeRoleModal = function () {
    window.rolesManager?.modal.close();
};
