
import { requestJSON } from '../utils/request';
import { showToast } from '../utils/toast';

interface Employee {
    id: number;
    name: string;
    email: string;
    role: string;
    is_active: boolean;
    last_activity_at?: string;
}

interface CreateEmployeePayload {
    name: string;
    email: string;
    role: string;
    password?: string;
}

function escape(str: any): string {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

export class EmployeesManager {
    private container: HTMLElement;
    private tableBody: HTMLElement | null;
    private modal: HTMLElement | null;
    private form: HTMLFormElement | null;
    private currentEmployeeId: number | null = null;
    private employees: Employee[] = [];

    // Roles disponibles (podrían venir del backend, hardcoded por ahora para MVP)
    private roles = [
        { value: 'waiter', label: 'Mesero' },
        { value: 'chef', label: 'Cocinero' },
        { value: 'cashier', label: 'Cajero' },
        { value: 'admin_roles', label: 'Administrador' }, // role real backend name
        { value: 'supervisor', label: 'Supervisor' }
    ];

    constructor(containerId: string) {
        const el = document.getElementById(containerId);
        if (!el) {
            console.error(`EmployeesManager: Container ${containerId} not found`);
            this.container = document.createElement('div'); // fallback
            return;
        }
        this.container = el;
        this.tableBody = this.container.querySelector('tbody');
        this.modal = document.getElementById('employee-modal');
        this.form = document.getElementById('employee-form') as HTMLFormElement;

        this.init();
    }

    private init() {
        this.bindEvents();
        this.loadEmployees();
    }

    private bindEvents() {
        // Botón nuevo empleado (debe existir en el HTML inyectado/existente)
        const addBtn = document.getElementById('btn-add-employee');
        if (addBtn) {
            addBtn.addEventListener('click', () => this.openModal());
        }

        // Form submit
        if (this.form) {
            this.form.addEventListener('submit', (e) => {
                e.preventDefault();
                this.saveEmployee();
            });
        }

        // Cerrar modal
        const closeBtns = document.querySelectorAll('.close-modal-btn'); // clase genérica
        closeBtns.forEach(btn => btn.addEventListener('click', () => this.closeModal()));
    }

    private async loadEmployees() {
        if (!this.tableBody) return;

        try {
            this.tableBody.innerHTML = '<tr><td colspan="5" class="text-center">Cargando...</td></tr>';

            const response = await requestJSON<{ employees: Employee[] }>('/api/employees');
            if (response.error) throw new Error(response.error);

            // Backend devuelve { data: { employees: [...] }, status: 'success' }
            // requestJSON ya maneja data wrapping normalmente.
            // Si requestJSON retorna el body parseado:
            // Revisar estructura retornada por requestJSON.
            // Asumo que requestJSON devuelve el payload completo: { status, data, error }

            const list = response.data?.employees || [];
            this.employees = list;
            this.renderTable();
        } catch (error) {
            console.error('Error loading employees:', error);
            this.tableBody.innerHTML = `<tr><td colspan="5" class="error-text">Error: ${(error as Error).message}</td></tr>`;
        }
    }

    private renderTable() {
        if (!this.tableBody) return;
        this.tableBody.innerHTML = '';

        if (this.employees.length === 0) {
            this.tableBody.innerHTML = '<tr><td colspan="5" class="text-center">No hay empleados registrados</td></tr>';
            return;
        }

        this.employees.forEach(emp => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>
                    <div class="font-medium">${escape(emp.name)}</div>
                </td>
                <td>${escape(emp.email)}</td>
                <td><span class="badge badge--${escape(this.getRoleBadgeColor(emp.role))}">${escape(this.formatRole(emp.role))}</span></td>
                <td>
                    <span class="status-dot ${emp.is_active ? 'active' : 'inactive'}"></span>
                    ${emp.is_active ? 'Activo' : 'Inactivo'}
                </td>
                <td>
                    <button class="btn btn--small btn--secondary btn-edit" data-id="${emp.id}">Editar</button>
                    ${emp.is_active ? `<button class="btn btn--small btn--danger btn-delete" data-id="${emp.id}">Desactivar</button>` : ''}
                </td>
            `;
            this.tableBody!.appendChild(tr);
        });

        // Bind events for dynamic buttons
        this.container.querySelectorAll('.btn-edit').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = Number((e.target as HTMLElement).dataset.id);
                this.openModal(id);
            });
        });

        this.container.querySelectorAll('.btn-delete').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = Number((e.target as HTMLElement).dataset.id);
                this.deleteEmployee(id);
            });
        });
    }

    private getRoleBadgeColor(role: string): string {
        switch (role) {
            case 'admin_roles': return 'purple';
            case 'supervisor': return 'blue';
            case 'chef': return 'orange';
            case 'waiter': return 'green';
            case 'cashier': return 'teal';
            default: return 'gray';
        }
    }

    private formatRole(role: string): string {
        const found = this.roles.find(r => r.value === role);
        return found ? found.label : role;
    }

    private openModal(employeeId?: number) {
        if (!this.modal || !this.form) return;

        this.currentEmployeeId = employeeId || null;
        const title = this.modal.querySelector('.modal-title');
        if (title) title.textContent = employeeId ? 'Editar Empleado' : 'Nuevo Empleado';

        // Reset form
        this.form.reset();

        if (employeeId) {
            const emp = this.employees.find(e => e.id === employeeId);
            if (emp) {
                (document.getElementById('emp-name') as HTMLInputElement).value = emp.name;
                (document.getElementById('emp-email') as HTMLInputElement).value = emp.email;
                (document.getElementById('emp-role') as HTMLSelectElement).value = emp.role;
                // Password field optional on edit
                (document.getElementById('emp-password') as HTMLInputElement).required = false;
                (document.getElementById('emp-password') as HTMLInputElement).placeholder = 'Dejar vacío para mantener actual';
            }
        } else {
            (document.getElementById('emp-password') as HTMLInputElement).required = true;
            (document.getElementById('emp-password') as HTMLInputElement).placeholder = 'Contraseña';
        }

        this.modal.classList.add('active');
    }

    private closeModal() {
        if (this.modal) this.modal.classList.remove('active');
    }

    private async saveEmployee() {
        if (!this.form) return;

        const name = (document.getElementById('emp-name') as HTMLInputElement).value;
        const email = (document.getElementById('emp-email') as HTMLInputElement).value;
        const role = (document.getElementById('emp-role') as HTMLSelectElement).value;
        const password = (document.getElementById('emp-password') as HTMLInputElement).value;

        const payload: CreateEmployeePayload = { name, email, role };
        if (password) payload.password = password;

        try {
            let res;
            if (this.currentEmployeeId) {
                res = await requestJSON(`/api/employees/${this.currentEmployeeId}`, {
                    method: 'PUT',
                    body: JSON.stringify(payload)
                });
            } else {
                res = await requestJSON('/api/employees', {
                    method: 'POST',
                    body: JSON.stringify(payload)
                });
            }

            if (res.error) throw new Error(res.error);

            showToast(this.currentEmployeeId ? 'Empleado actualizado' : 'Empleado creado', 'success');
            this.closeModal();
            this.loadEmployees();
        } catch (error) {
            console.error('Error saving employee:', error);
            showToast((error as Error).message || 'Error al guardar', 'error');
        }
    }

    private async deleteEmployee(id: number) {
        if (!confirm('¿Estás seguro de desactivar este empleado?')) return;

        try {
            const res = await requestJSON(`/api/employees/${id}`, { method: 'DELETE' });
            if (res.error) throw new Error(res.error);
            showToast('Empleado desactivado', 'success');
            this.loadEmployees();
        } catch (error) {
            showToast((error as Error).message, 'error');
        }
    }
}
