
/**
 * Employees Manager (Vanilla JS Version)
 */
class EmployeesManager {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            console.error(`EmployeesManager: Container ${containerId} not found`);
            return;
        }

        // Initialize state
        this.employees = [];
        this.currentEmployeeId = null;
        this.roles = []; // Cargar dinámicamente

        // Cache DOM elements
        this.tableBody = this.container.querySelector('tbody');
        this.modal = document.getElementById('employee-modal');
        this.form = document.getElementById('employee-form');

        this.init();
    }

    async init() {
        this.bindEvents();
        await this.loadRoles(); // Cargar roles antes de empleados para formatear correctamente
        this.loadEmployees();
    }

    async loadRoles() {
        try {
            const response = await fetch('/api/roles');
            const result = await response.json();
            if (result.status === 'success' && result.data) {
                this.roles = result.data.map(r => ({
                    value: r.name,
                    label: r.display_name
                }));
                this.updateRoleSelect();
            }
        } catch (error) {
            console.error('Error loading roles:', error);
            // Fallback
            this.roles = [
                { value: 'waiter', label: 'Mesero' },
                { value: 'chef', label: 'Cocinero' },
                { value: 'cashier', label: 'Cajero' },
                { value: 'admin_roles', label: 'Administrador' }
            ];
            this.updateRoleSelect();
        }
    }

    updateRoleSelect() {
        const select = document.getElementById('emp-role');
        if (!select) return;

        // Guardar selección actual si hay
        const currentVal = select.value;

        select.innerHTML = '<option value="">Seleccionar Rol...</option>';
        this.roles.forEach(r => {
            const opt = document.createElement('option');
            opt.value = r.value;
            opt.textContent = r.label;
            select.appendChild(opt);
        });

        if (currentVal) select.value = currentVal;
    }

    bindEvents() {
        // Botón nuevo empleado
        const addBtn = document.getElementById('btn-add-employee');
        if (addBtn) {
            if (!this.hasPermission('employees:create')) {
                addBtn.style.display = 'none';
            } else {
                addBtn.addEventListener('click', () => this.openModal());
            }
        }

        // Form submit
        if (this.form) {
            this.form.addEventListener('submit', (e) => {
                e.preventDefault();
                this.saveEmployee();
            });
        }

        // Cerrar modal
        const closeBtns = document.querySelectorAll('.close-modal-btn');
        closeBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault(); // prevenir comportamiento default si es link
                this.closeModal();
            });
        });

        // Click fuera del modal para cerrar
        if (this.modal) {
            this.modal.addEventListener('click', (e) => {
                if (e.target === this.modal) this.closeModal();
            });
        }
    }

    async loadEmployees() {
        if (!this.tableBody) return;

        try {
            this.tableBody.innerHTML = '<tr><td colspan="5" class="text-center" style="padding: 2rem;">Cargando empleados...</td></tr>';

            const response = await fetch('/api/employees');
            const result = await response.json();

            // Handle standard response wrapper { status: 'success', data: ... }
            if (result.status === 'error' || result.error) {
                throw new Error(result.error || 'Error al cargar empleados');
            }

            // Extract employees list
            // Puede venir en result.data.employees o result.employees (dependiendo del serializer)
            let list = [];
            if (result.data && result.data.employees) {
                list = result.data.employees;
            } else if (result.employees) {
                list = result.employees;
            } else if (Array.isArray(result.data)) {
                list = result.data; // raro, pero posible
            }

            this.employees = list;
            this.renderTable();

        } catch (error) {
            console.error('Error loading employees:', error);
            this.tableBody.innerHTML = `<tr><td colspan="5" style="color: red; text-align: center; padding: 2rem;">Error: ${error.message}</td></tr>`;
        }
    }

    hasPermission(permission) {
        if (!window.currentUser || !window.currentUser.permissions) return false;
        return window.currentUser.permissions.includes(permission);
    }

    renderTable() {
        if (!this.tableBody) return;
        this.tableBody.innerHTML = '';

        if (!this.employees || this.employees.length === 0) {
            this.tableBody.innerHTML = '<tr><td colspan="5" class="text-center" style="padding: 3rem; color: #64748b;">No hay empleados registrados. Haz clic en "Nuevo Empleado" para comenzar.</td></tr>';
            return;
        }

        const canEdit = this.hasPermission('employees:edit');
        const canDelete = this.hasPermission('employees:delete');

        this.employees.forEach(emp => {
            const tr = document.createElement('tr');
            const roleLabel = this.formatRole(emp.role);
            const badgeColor = this.getRoleBadgeColor(emp.role);
            const statusClass = emp.is_active ? 'active' : 'inactive';
            const statusText = emp.is_active ? 'Activo' : 'Inactivo';

            let actionsHtml = '<div style="display: flex; gap: 0.5rem;">';

            if (canEdit) {
                actionsHtml += `<button type="button" class="btn btn--small btn--secondary btn-edit" data-id="${emp.id}">✏️ Editar</button>`;
            }

            if (canDelete && emp.is_active) {
                actionsHtml += `<button type="button" class="btn btn--small btn--danger btn-delete" data-id="${emp.id}" style="background-color: #fee2e2; color: #ef4444; border:none;">🗑️ Desactivar</button>`;
            }

            actionsHtml += '</div>';

            tr.innerHTML = `
                <td>
                    <div style="font-weight: 600; color: #1e293b;">${this.escapeHtml(emp.name)}</div>
                </td>
                <td style="color: #64748b;">${this.escapeHtml(emp.email)}</td>
                <td>
                    <span class="status ${badgeColor}" style="font-size: 0.75rem; padding: 0.25rem 0.75rem;">${roleLabel}</span>
                </td>
                <td>
                    <span style="display: inline-flex; align-items: center; gap: 0.5rem;">
                        <span style="width: 8px; height: 8px; border-radius: 50%; background-color: ${emp.is_active ? '#10b981' : '#ef4444'};"></span>
                        ${statusText}
                    </span>
                </td>
                <td>
                    ${actionsHtml}
                </td>
            `;
            this.tableBody.appendChild(tr);
        });

        // Bind dynamic buttons
        this.tableBody.querySelectorAll('.btn-edit').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = Number(e.currentTarget.dataset.id);
                this.openModal(id);
            });
        });

        this.tableBody.querySelectorAll('.btn-delete').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = Number(e.currentTarget.dataset.id);
                this.deleteEmployee(id);
            });
        });
    }

    getRoleBadgeColor(role) {
        switch (role) {
            case 'admin_roles': return 'purple'; // estilo css debe existir o usar inline
            case 'supervisor': return 'blue';
            case 'chef': return 'orange';
            case 'waiter': return 'green';
            case 'cashier': return 'teal';
            default: return 'gray';
        }
    }

    formatRole(role) {
        const found = this.roles.find(r => r.value === role);
        return found ? found.label : role;
    }

    escapeHtml(text) {
        if (!text) return '';
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    openModal(employeeId = null) {
        if (!this.modal || !this.form) return;

        this.currentEmployeeId = employeeId;
        const titleEl = this.modal.querySelector('.modal-title');
        if (titleEl) titleEl.textContent = employeeId ? 'Editar Empleado' : 'Nuevo Empleado';

        // Reset form
        this.form.reset();

        const passwordInput = document.getElementById('emp-password');
        const getVal = (id) => document.getElementById(id);

        if (employeeId) {
            const emp = this.employees.find(e => e.id === employeeId);
            if (emp) {
                if (getVal('emp-name')) getVal('emp-name').value = emp.name;
                if (getVal('emp-email')) getVal('emp-email').value = emp.email;
                if (getVal('emp-role')) getVal('emp-role').value = emp.role;

                if (passwordInput) {
                    passwordInput.required = false;
                    passwordInput.placeholder = 'Dejar vacío para mantener actual';
                }
            }
        } else {
            if (passwordInput) {
                passwordInput.required = true;
                passwordInput.placeholder = 'Contraseña';
            }
        }

        this.modal.classList.add('active'); // Clase 'active' para mostrar modal
        this.modal.style.display = 'flex'; // Asegurar display flex por si acaso
    }

    closeModal() {
        if (this.modal) {
            this.modal.classList.remove('active');
            this.modal.style.display = 'none';
            this.currentEmployeeId = null;
        }
    }

    async saveEmployee() {
        if (!this.form) return;

        const getVal = (id) => document.getElementById(id)?.value;
        const name = getVal('emp-name');
        const email = getVal('emp-email');
        const role = getVal('emp-role');
        const password = getVal('emp-password');

        const payload = { name, email, role };
        if (password) payload.password = password;

        const btnSubmit = this.form.querySelector('button[type="submit"]');
        if (btnSubmit) {
            btnSubmit.disabled = true;
            btnSubmit.textContent = 'Guardando...';
        }

        try {
            const url = this.currentEmployeeId
                ? `/api/employees/${this.currentEmployeeId}`
                : '/api/employees';

            const method = this.currentEmployeeId ? 'PUT' : 'POST';

            const response = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            if (!response.ok || result.status === 'error' || result.error) {
                throw new Error(result.error || result.message || 'Error al guardar');
            }

            this.showToast(this.currentEmployeeId ? 'Empleado actualizado exitosamente' : 'Empleado creado exitosamente', 'success');
            this.closeModal();
            this.loadEmployees();

        } catch (error) {
            console.error('Error saving:', error);
            this.showToast(error.message || 'Error al guardar', 'error');
        } finally {
            if (btnSubmit) {
                btnSubmit.disabled = false;
                btnSubmit.textContent = 'Guardar';
            }
        }
    }

    async deleteEmployee(id) {
        if (!confirm('¿Estás seguro de que deseas desactivar este empleado? No podrá iniciar sesión.')) return;

        try {
            const response = await fetch(`/api/employees/${id}`, { method: 'DELETE' });
            const result = await response.json();

            if (!response.ok || (result.status && result.status === 'error')) {
                throw new Error(result.error || 'Error al eliminar');
            }

            this.showToast('Empleado desactivado', 'success');
            this.loadEmployees();
        } catch (error) {
            this.showToast(error.message, 'error');
        }
    }

    showToast(message, type) {
        if (window.ToastManager) {
            window.ToastManager.show(message, type);
        } else {
            alert(message);
        }
    }
}

// Inicializar cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
    // Solo inicializar si existe la sección de empleados
    if (document.getElementById('employees-table')) {
        new EmployeesManager('empleados');
    }
});
