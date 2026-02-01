<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';

// Interfaces
interface Role {
    value: string;
    label: string;
}

interface Employee {
    id: number;
    name: string;
    email: string;
    role: string;
    is_active: boolean;
}

interface UserPermissions {
    permissions: string[];
}

// State
const employees = ref<Employee[]>([]);
const roles = ref<Role[]>([]);
const isLoading = ref(false);
const error = ref<string | null>(null);
const showModal = ref(false);
const isSaving = ref(false);

// Form State
const editingId = ref<number | null>(null);
const form = ref({
    name: '',
    email: '',
    role: '',
    password: ''
});

// Permissions (from window.currentUser injected by Flask)
const permissions = computed(() => {
    const user = (window as any).currentUser as UserPermissions | undefined;
    return user?.permissions || [];
});

const canCreate = computed(() => permissions.value.includes('employees:create'));
const canEdit = computed(() => permissions.value.includes('employees:edit'));
const canDelete = computed(() => permissions.value.includes('employees:delete'));

// Methods
const loadRoles = async () => {
    try {
        const res = await fetch('/api/roles');
        const data = await res.json();
        if (data.status === 'success' && data.data) {
            roles.value = data.data.map((r: any) => ({
                value: r.name,
                label: r.display_name
            }));
        }
    } catch (e) {
        console.error('Error loading roles, using fallback', e);
        roles.value = [
            { value: 'waiter', label: 'Mesero' },
            { value: 'chef', label: 'Cocinero' },
            { value: 'cashier', label: 'Cajero' },
            { value: 'supervisor', label: 'Supervisor' },
            { value: 'admin_roles', label: 'Administrador' }
        ];
    }
};

const loadEmployees = async () => {
    isLoading.value = true;
    error.value = null;
    try {
        const res = await fetch('/api/employees');
        const data = await res.json();

        if (data.status === 'error' || data.error) {
            throw new Error(data.error || 'Error cargando empleados');
        }

        // Handle different response structures gracefully
        if (data.data && Array.isArray(data.data.employees)) {
            employees.value = data.data.employees;
        } else if (Array.isArray(data.employees)) {
            employees.value = data.employees;
        } else if (Array.isArray(data.data)) {
            employees.value = data.data;
        } else {
            employees.value = [];
        }
    } catch (e: any) {
        error.value = e.message;
    } finally {
        isLoading.value = false;
    }
};

const getRoleLabel = (roleVal: string) => {
    const r = roles.value.find(r => r.value === roleVal);
    return r ? r.label : roleVal;
};

const getRoleBadgeClass = (role: string) => {
    const map: Record<string, string> = {
        'admin_roles': 'bg-purple-100 text-purple-800',
        'supervisor': 'bg-blue-100 text-blue-800',
        'chef': 'bg-orange-100 text-orange-800',
        'waiter': 'bg-green-100 text-green-800',
        'cashier': 'bg-teal-100 text-teal-800'
    };
    return map[role] || 'bg-gray-100 text-gray-800';
};

// Actions
const openModal = (emp?: Employee) => {
    error.value = null;
    if (emp) {
        editingId.value = emp.id;
        form.value = {
            name: emp.name,
            email: emp.email,
            role: emp.role,
            password: '' // Password always empty on edit
        };
    } else {
        editingId.value = null;
        form.value = { name: '', email: '', role: '', password: '' };
    }
    showModal.value = true;
};

const saveEmployee = async () => {
    isSaving.value = true;
    try {
        const url = editingId.value
            ? `/api/employees/${editingId.value}`
            : '/api/employees';
        const method = editingId.value ? 'PUT' : 'POST';

        const payload: any = { ...form.value };
        if (!payload.password) delete payload.password; // Don't send empty pwd

        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await res.json();
        if (!res.ok || result.status === 'error') throw new Error(result.error || 'Error al guardar');

        showModal.value = false;
        loadEmployees();
        // Here you could add a toast library call like toast.success(...)
    } catch (e: any) {
        alert(e.message); // Simple fallback
    } finally {
        isSaving.value = false;
    }
};

const toggleStatus = async (emp: Employee) => {
    if (!confirm('¿Estás seguro de que deseas desactivar este empleado?')) return;
    try {
        await fetch(`/api/employees/${emp.id}`, { method: 'DELETE' });
        loadEmployees();
    } catch (e) {
        alert("Error al desactivar");
    }
};

onMounted(() => {
    loadRoles();
    loadEmployees();
});
</script>

<template>
<div class="p-6 bg-white rounded-xl shadow-sm border border-gray-200">
    <div class="flex justify-between items-center mb-6">
        <h2 class="text-xl font-bold text-gray-800">Administración de Empleados</h2>
        <button
            v-if="canCreate"
            class="bg-gray-900 hover:bg-black text-white px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2"
            @click="openModal()"
        >
            <span>+</span> Nuevo Empleado
        </button>
    </div>

    <!-- Loading / Error States -->
    <div v-if="isLoading" class="p-8 text-center text-gray-500">Cargando empleados...</div>
    <div v-else-if="error" class="p-8 text-center text-red-500">{{ error }}</div>

    <!-- Table -->
    <div v-else class="overflow-x-auto rounded-lg border border-gray-100">
        <table class="w-full text-left border-collapse">
            <thead class="bg-gray-50 text-gray-600 uppercase text-xs font-bold">
                <tr>
                    <th class="p-4 border-b">Nombre</th>
                    <th class="p-4 border-b">Email</th>
                    <th class="p-4 border-b">Rol</th>
                    <th class="p-4 border-b">Estado</th>
                    <th class="p-4 border-b">Acciones</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
                <tr v-if="employees.length === 0">
                    <td colspan="5" class="p-8 text-center text-gray-400">No hay empleados registrados</td>
                </tr>
                <tr v-for="emp in employees" :key="emp.id" class="hover:bg-gray-50 transition-colors">
                    <td class="p-4 font-medium text-gray-900">{{ emp.name }}</td>
                    <td class="p-4 text-gray-500">{{ emp.email }}</td>
                    <td class="p-4">
                        <span :class="['px-3 py-1 rounded-full text-xs font-semibold', getRoleBadgeClass(emp.role)]">
                            {{ getRoleLabel(emp.role) }}
                        </span>
                    </td>
                    <td class="p-4">
                        <div class="flex items-center gap-2">
                            <span :class="['w-2 h-2 rounded-full', emp.is_active ? 'bg-green-500' : 'bg-red-500']"></span>
                            <span class="text-sm text-gray-600">{{ emp.is_active ? 'Activo' : 'Inactivo' }}</span>
                        </div>
                    </td>
                    <td class="p-4 flex gap-2">
                        <button
                            v-if="canEdit"
                            class="text-gray-500 hover:text-blue-600 p-1 rounded hover:bg-blue-50 transition-colors"
                            title="Editar"
                            @click="openModal(emp)"
                        >✏️</button>
                        <button
                            v-if="canDelete && emp.is_active"
                            class="text-gray-500 hover:text-red-600 p-1 rounded hover:bg-red-50 transition-colors"
                            title="Desactivar"
                            @click="toggleStatus(emp)"
                        >🗑️</button>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>

    <!-- Modal -->
    <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" @click.self="showModal = false">
        <div class="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200">
            <div class="bg-gray-50 px-6 py-4 border-b border-gray-100 flex justify-between items-center">
                <h3 class="font-bold text-lg text-gray-800">{{ editingId ? 'Editar Empleado' : 'Nuevo Empleado' }}</h3>
                <button class="text-gray-400 hover:text-gray-600 text-xl font-bold" @click="showModal = false">&times;</button>
            </div>

            <form class="p-6 space-y-4" @submit.prevent="saveEmployee">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Nombre</label>
                    <input v-model="form.name" required type="text" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none transition-all">
                </div>

                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Email</label>
                    <input v-model="form.email" required type="email" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none transition-all">
                </div>

                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Rol</label>
                    <div class="relative">
                        <select v-model="form.role" required class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none transition-all appearance-none bg-white">
                            <option value="">Selecciona un rol...</option>
                            <option v-for="role in roles" :key="role.value" :value="role.value">{{ role.label }}</option>
                        </select>
                         <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-gray-700">
                            <svg class="fill-current h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M9.293 12.95l.707.707L15.657 8l-1.414-1.414L10 10.828 5.757 6.586 4.343 8z"/></svg>
                        </div>
                    </div>
                </div>

                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Contraseña</label>
                    <input v-model="form.password" :required="!editingId" type="password" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none transition-all" :placeholder="editingId ? 'Dejar vacío para no cambiar' : 'Nueva contraseña'">
                </div>

                <div class="pt-4 flex justify-end gap-3">
                    <button type="button" class="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg font-medium transition-colors" @click="showModal = false">Cancelar</button>
                    <button type="submit" :disabled="isSaving" class="px-6 py-2 bg-primary-orange hover:bg-primary-orange-dark text-white rounded-lg font-medium shadow-md hover:shadow-lg transform active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed">
                        {{ isSaving ? 'Guardando...' : 'Guardar' }}
                    </button>
                </div>
            </form>
        </div>
    </div>
</div>
</template>
