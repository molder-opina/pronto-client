import { mount } from '@vue/test-utils';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import EmployeesManager from './EmployeesManager.vue';

describe('EmployeesManager', () => {
  beforeEach(() => {
    global.fetch = vi.fn();

    // Mock window.currentUser
    Object.defineProperty(window, 'currentUser', {
      value: {
        permissions: ['employees:create', 'employees:edit', 'employees:delete'],
      },
      writable: true,
      configurable: true,
    });
  });

  it('renders correctly and has accessible buttons', async () => {
    // Mock API responses
    const mockEmployees = [
      { id: 1, name: 'John Doe', email: 'john@example.com', role: 'waiter', is_active: true },
    ];

    const mockRoles = [{ name: 'waiter', display_name: 'Mesero' }];

    // Mock fetch implementation
    (global.fetch as any).mockImplementation((url: string) => {
      if (url.includes('/api/roles')) {
        return Promise.resolve({
          json: () => Promise.resolve({ status: 'success', data: mockRoles }),
        });
      }
      if (url.includes('/api/employees')) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              status: 'success',
              data: { employees: mockEmployees },
            }),
        });
      }
      return Promise.reject(new Error('Unknown URL: ' + url));
    });

    const wrapper = mount(EmployeesManager);

    // Wait for data loading (fetch is async)
    await new Promise((resolve) => setTimeout(resolve, 0));
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();

    // Find the edit button
    const editBtn = wrapper.find('button[title="Editar"]');
    expect(editBtn.exists()).toBe(true);

    // Check for aria-label
    expect(editBtn.attributes('aria-label')).toBe('Editar John Doe');

    // Find the delete button
    const deleteBtn = wrapper.find('button[title="Desactivar"]');
    expect(deleteBtn.exists()).toBe(true);
    expect(deleteBtn.attributes('aria-label')).toBe('Desactivar John Doe');
  });

  it('shows loading state on save button', async () => {
    // Mock basic load fetch to avoid errors
    (global.fetch as any).mockResolvedValue({
      json: () => Promise.resolve({ status: 'success', data: [] }),
    });

    const wrapper = mount(EmployeesManager);
    await wrapper.vm.$nextTick();

    // Open modal
    wrapper.vm.showModal = true;
    await wrapper.vm.$nextTick();

    const saveBtn = wrapper.find('button[type="submit"]');
    expect(saveBtn.exists()).toBe(true);

    // Initially text is 'Guardar'
    expect(saveBtn.text()).toContain('Guardar');

    // Set loading state manually to test the UI response
    wrapper.vm.isSaving = true;
    await wrapper.vm.$nextTick();

    // Should show loading text
    expect(saveBtn.text()).toContain('Guardando...');

    // Check for spinner
    const spinner = saveBtn.find('svg.animate-spin');
    expect(spinner.exists()).toBe(true);
  });
});
