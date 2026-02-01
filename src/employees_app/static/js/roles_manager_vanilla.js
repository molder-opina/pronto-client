
/**
 * roles_manager_vanilla.js
 * Gestión de Roles y Permisos (Vanilla JS)
 */

const RolesManager = {
    API_BASE: '/api',

    state: {
        roles: [],
        permissions: [], // Catálogo de permisos agrupados
        currentRole: null,
        isEditing: false
    },

    dom: {
        tableBody: null,
        modal: null,
        form: null,
        permissionsContainer: null,
        modalTitle: null,
        saveBtn: null,
        template: null
    },

    init() {
        console.log('RolesManager: Initializing...');
        this.dom.tableBody = document.getElementById('roles-table-body');
        this.dom.modal = document.getElementById('roles-modal');
        this.dom.form = document.getElementById('roles-form');
        this.dom.permissionsContainer = document.getElementById('roles-permissions-container');
        this.dom.modalTitle = document.getElementById('roles-modal-title');
        this.dom.saveBtn = document.getElementById('roles-save-btn');

        if (!this.dom.tableBody) {
            console.warn('RolesManager: Table body not found, skipping init.');
            return;
        }

        this.bindEvents();
        this.loadInitialData();
    },

    bindEvents() {
        // Nuevo Rol
        const createBtn = document.getElementById('btn-create-role');
        if (createBtn) {
            createBtn.addEventListener('click', () => this.openModal());
        }

        // Form Submit
        if (this.dom.form) {
            this.dom.form.addEventListener('submit', (e) => this.handleSubmit(e));
        }

        // Cerrar Modal
        const closeBtns = document.querySelectorAll('.close-roles-modal');
        closeBtns.forEach(btn => {
            btn.addEventListener('click', () => this.closeModal());
        });

        // Clic fuera del modal
        if (this.dom.modal) {
            this.dom.modal.addEventListener('click', (e) => {
                if (e.target === this.dom.modal) this.closeModal();
            });
        }
    },

    async loadInitialData() {
        try {
            await Promise.all([
                this.fetchPermissions(),
                this.fetchRoles()
            ]);
            this.renderRoles();
            this.renderPermissionsForm();
        } catch (error) {
            console.error('RolesManager: Error loading initial data', error);
            this.showNotification('Error cargando datos', 'error');
        }
    },

    async fetchRoles() {
        const response = await fetch(`${this.API_BASE}/roles`);
        if (!response.ok) throw new Error('Failed to fetch roles');
        const json = await response.json();
        this.state.roles = json.data || [];
    },

    async fetchPermissions() {
        const response = await fetch(`${this.API_BASE}/permissions`);
        if (!response.ok) throw new Error('Failed to fetch permissions');
        const json = await response.json();
        this.state.permissions = json.data || [];
    },

    renderRoles() {
        if (!this.dom.tableBody) return;
        this.dom.tableBody.innerHTML = '';

        this.state.roles.forEach(role => {
            const tr = document.createElement('tr');

            // Determinar estilo del badge
            const badgeClass = role.is_custom ? 'badge--purple' : 'badge--blue';
            const typeLabel = role.is_custom ? 'Personalizado' : 'Sistema';

            tr.innerHTML = `
                <td>
                    <div class="user-info">
                        <div class="user-avatar" style="background-color: var(--primary-light); color: var(--primary);">
                            ${role.display_name.charAt(0).toUpperCase()}
                        </div>
                        <div>
                            <div class="font-bold">${role.display_name}</div>
                            <div class="text-sm text-gray">${role.name}</div>
                        </div>
                    </div>
                </td>
                <td>
                    <span class="badge ${badgeClass}">${typeLabel}</span>
                </td>
                <td>
                    <div class="text-sm" title="${role.description || ''}">
                        ${role.description || '-'}
                    </div>
                </td>
                <td>
                    <span class="text-sm font-medium">${role.permissions.length} permisos</span>
                </td>
                <td>
                    <div class="actions-cell">
                        <button class="btn-icon" onclick="RolesManager.openModal(${role.id})" title="Editar">
                            ✏️
                        </button>
                        ${role.is_custom ? `
                        <button class="btn-icon text-red" onclick="RolesManager.deleteRole(${role.id})" title="Eliminar">
                            🗑️
                        </button>` : ''}
                    </div>
                </td>
            `;
            this.dom.tableBody.appendChild(tr);
        });
    },

    groupPermissionsByCategory(perms) {
        const groups = {};
        perms.forEach(p => {
            const cat = p.category || 'Otros';
            if (!groups[cat]) groups[cat] = [];
            groups[cat].push(p);
        });
        return groups;
    },

    renderPermissionsForm() {
        if (!this.dom.permissionsContainer) return;

        const groups = this.groupPermissionsByCategory(this.state.permissions);
        let html = '';

        for (const [category, perms] of Object.entries(groups)) {
            // Traducir categoría si es posible
            const catTitle = category.charAt(0).toUpperCase() + category.slice(1);

            html += `
                <div class="permissions-group mb-4">
                    <h4 class="text-sm font-bold uppercase text-gray-500 mb-2 border-b pb-1">${catTitle}</h4>
                    <div class="grid grid-cols-2 gap-2">
            `;

            perms.forEach(p => {
                html += `
                    <label class="flex items-center space-x-2 p-2 rounded hover:bg-gray-50 cursor-pointer">
                        <input type="checkbox" name="permissions" value="${p.code}" class="form-checkbox text-primary rounded">
                        <span class="text-sm">
                            <span class="font-medium block">${p.code}</span>
                            ${p.description ? `<span class="text-xs text-gray-400">${p.description}</span>` : ''}
                        </span>
                    </label>
                `;
            });

            html += `
                    </div>
                </div>
            `;
        }

        this.dom.permissionsContainer.innerHTML = html;
    },

    openModal(roleId = null) {
        this.state.isEditing = !!roleId;
        this.dom.form.reset();

        if (roleId) {
            const role = this.state.roles.find(r => r.id === roleId);
            this.state.currentRole = role;
            this.dom.modalTitle.textContent = `Editar Rol: ${role.display_name}`;

            // Llenar campos
            document.getElementById('role_name').value = role.name;
            document.getElementById('role_display_name').value = role.display_name;
            document.getElementById('role_description').value = role.description || '';

            // Si es sistema, bloquear nombre técnico
            document.getElementById('role_name').disabled = !role.is_custom;

            // Marcar checkboxes
            const permCodes = new Set(role.permissions.map(p => p.code));
            const checkboxes = this.dom.permissionsContainer.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach(cb => {
                cb.checked = permCodes.has(cb.value);
            });

        } else {
            this.state.currentRole = null;
            this.dom.modalTitle.textContent = 'Nuevo Rol Personalizado';
            document.getElementById('role_name').disabled = false;

            // Desmarcar checkboxes
            const checkboxes = this.dom.permissionsContainer.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach(cb => cb.checked = false);
        }

        this.dom.modal.showModal();
    },

    closeModal() {
        this.dom.modal.close();
    },

    async handleSubmit(e) {
        e.preventDefault();

        try {
            // Validar
            if (!this.dom.form.checkValidity()) {
                this.dom.form.reportValidity();
                return;
            }

            const formData = new FormData(this.dom.form);
            const data = {
                name: formData.get('name'),
                display_name: formData.get('display_name'),
                description: formData.get('description'),
                permissions: Array.from(formData.getAll('permissions'))
            };

            let url = `${this.API_BASE}/roles`;
            let method = 'POST';

            if (this.state.isEditing) {
                url += `/${this.state.currentRole.id}`;
                method = 'PUT';
            }

            this.setLoading(true);

            const response = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.message || 'Error saving role');
            }

            this.showNotification('Rol guardado correctamente', 'success');
            this.closeModal();
            await this.fetchRoles(); // Recargar lista
            this.renderRoles();

        } catch (error) {
            console.error(error);
            this.showNotification(error.message, 'error');
        } finally {
            this.setLoading(false);
        }
    },

    async deleteRole(roleId) {
        if (!confirm('¿Estás seguro de eliminar este rol? Esta acción no se puede deshacer.')) return;

        try {
            const response = await fetch(`${this.API_BASE}/roles/${roleId}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                const json = await response.json();
                throw new Error(json.message || 'Error deleting role');
            }

            this.showNotification('Rol eliminado', 'success');
            await this.fetchRoles();
            this.renderRoles();
        } catch (error) {
            this.showNotification(error.message, 'error');
        }
    },

    setLoading(isLoading) {
        if (this.dom.saveBtn) {
            this.dom.saveBtn.disabled = isLoading;
            this.dom.saveBtn.innerHTML = isLoading ? '<span class="spinner-small"></span> Guardando...' : 'Guardar';
        }
    },

    showNotification(message, type = 'info') {
        // Usar sistema de notificaciones existente si hay, o alert simple por ahora
        // Asumiendo que existe showToast global o similar de employees_manager
        if (window.showToast) {
            window.showToast(message, type);
        } else {
            alert(message);
        }
    }
};

// Hacer global
window.RolesManager = RolesManager;
