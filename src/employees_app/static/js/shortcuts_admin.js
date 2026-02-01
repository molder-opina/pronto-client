/**
 * Keyboard Shortcuts Administration Manager
 * Handles CRUD operations for keyboard shortcuts
 */
class ShortcutsManager {
    constructor() {
        this.shortcuts = [];
        this.filteredShortcuts = [];
    }

    async init() {
        await this.loadShortcuts();
    }

    async loadShortcuts() {
        try {
            const response = await fetch('/api/admin/shortcuts');
            const result = await response.json();

            if (result.shortcuts) {
                this.shortcuts = result.shortcuts;
                this.filteredShortcuts = [...this.shortcuts];
                this.render();
            }
        } catch (error) {
            console.error('Error loading shortcuts:', error);
            NotificationHelper.show('Error al cargar atajos', 'error');
        }
    }

    render() {
        const grid = document.querySelector('.shortcuts-grid');
        if (!grid) return;

        if (this.filteredShortcuts.length === 0) {
            grid.innerHTML = `
                <div class="empty-state" style="grid-column: 1 / -1;">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="1.5">
                        <rect x="2" y="4" width="20" height="16" rx="2"></rect>
                        <path d="m9 9-2 2 2 2"></path>
                        <path d="m13 9 2 2-2 2"></path>
                    </svg>
                    <h4>No se encontraron atajos</h4>
                    <p>Crea un nuevo atajo para comenzar</p>
                </div>
            `;
            return;
        }

        grid.innerHTML = this.filteredShortcuts.map(shortcut => `
            <div class="shortcut-card" data-category="${shortcut.category}" data-search="${shortcut.combo} ${shortcut.description}">
                <div class="shortcut-card-header">
                    <span class="shortcut-combo">${this.formatCombo(shortcut.combo)}</span>
                    <label class="toggle-switch small">
                        <input type="checkbox" ${shortcut.is_enabled ? 'checked' : ''}
                               onchange="ShortcutsManager.toggle(${shortcut.id}, this.checked)">
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="shortcut-card-body">
                    <p class="shortcut-description">${shortcut.description}</p>
                    <span class="shortcut-category">${shortcut.category}</span>
                </div>
                <div class="shortcut-card-actions">
                    <button class="btn-icon" onclick="ShortcutsManager.edit(${shortcut.id})" title="Editar">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                        </svg>
                    </button>
                    <button class="btn-icon danger" onclick="ShortcutsManager.delete(${shortcut.id})" title="Eliminar">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                    </button>
                </div>
            </div>
        `).join('');
    }

    formatCombo(combo) {
        return combo.split('+').map(key => {
            const keyMap = {
                'ctrl': 'Ctrl',
                'alt': 'Alt',
                'shift': 'Shift',
                'enter': 'Enter',
                'escape': 'Esc',
                'backspace': 'Back',
                'tab': 'Tab',
                'arrowup': '↑',
                'arrowdown': '↓',
                'arrowleft': '←',
                'arrowright': '→',
                ' ': 'Espacio'
            };
            const lower = key.toLowerCase();
            return keyMap[lower] || key.toUpperCase();
        }).join('+');
    }

    filter() {
        const query = document.getElementById('shortcuts-filter')?.value?.toLowerCase() || '';

        this.filteredShortcuts = this.shortcuts.filter(shortcut => {
            const searchText = `${shortcut.combo} ${shortcut.description} ${shortcut.category}`.toLowerCase();
            return searchText.includes(query);
        });

        this.render();
    }

    async toggle(id, enabled) {
        try {
            const response = await fetch(`/api/admin/shortcuts/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_enabled: enabled })
            });

            const result = await response.json();

            if (result.success) {
                const index = this.shortcuts.findIndex(s => s.id === id);
                if (index >= 0) {
                    this.shortcuts[index].is_enabled = enabled;
                    this.filter();
                }
                NotificationHelper.show('Atajo actualizado', 'success');
            } else {
                NotificationHelper.show(result.error || 'Error al actualizar', 'error');
                this.loadShortcuts();
            }
        } catch (error) {
            console.error('Error toggling shortcut:', error);
            NotificationHelper.show('Error al actualizar', 'error');
            this.loadShortcuts();
        }
    }

    createNew() {
        document.getElementById('modal-title').textContent = 'Nuevo Atajo de Teclado';
        document.getElementById('shortcut-id').value = '';
        document.getElementById('shortcut-form').reset();
        document.getElementById('shortcut-modal').style.display = 'flex';
    }

    edit(id) {
        const shortcut = this.shortcuts.find(s => s.id === id);
        if (!shortcut) return;

        document.getElementById('modal-title').textContent = 'Editar Atajo de Teclado';
        document.getElementById('shortcut-id').value = shortcut.id;
        document.getElementById('shortcut-combo').value = shortcut.combo;
        document.getElementById('shortcut-description').value = shortcut.description;
        document.getElementById('shortcut-category').value = shortcut.category;
        document.getElementById('shortcut-callback').value = shortcut.callback_function || 'goToHome';
        document.getElementById('shortcut-prevent-default').checked = shortcut.prevent_default !== false;
        document.getElementById('shortcut-modal').style.display = 'flex';
    }

    closeModal() {
        document.getElementById('shortcut-modal').style.display = 'none';
    }

    async save(event) {
        event.preventDefault();

        const id = document.getElementById('shortcut-id').value;
        const data = {
            combo: document.getElementById('shortcut-combo').value.trim(),
            description: document.getElementById('shortcut-description').value.trim(),
            category: document.getElementById('shortcut-category').value,
            callback_function: document.getElementById('shortcut-callback').value,
            prevent_default: document.getElementById('shortcut-prevent-default').checked
        };

        try {
            const url = id ? `/api/admin/shortcuts/${id}` : '/api/admin/shortcuts';
            const method = id ? 'PUT' : 'POST';

            const response = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (result.success) {
                NotificationHelper.show(
                    id ? 'Atajo actualizado' : 'Atajo creado',
                    'success'
                );
                this.closeModal();
                await this.loadShortcuts();
            } else {
                NotificationHelper.show(result.error || 'Error al guardar', 'error');
            }
        } catch (error) {
            console.error('Error saving shortcut:', error);
            NotificationHelper.show('Error al guardar', 'error');
        }
    }

    async delete(id) {
        if (!confirm('¿Estás seguro de eliminar este atajo?')) return;

        try {
            const response = await fetch(`/api/admin/shortcuts/${id}`, {
                method: 'DELETE'
            });

            const result = await response.json();

            if (result.success) {
                NotificationHelper.show('Atajo eliminado', 'success');
                await this.loadShortcuts();
            } else {
                NotificationHelper.show(result.error || 'Error al eliminar', 'error');
            }
        } catch (error) {
            console.error('Error deleting shortcut:', error);
            NotificationHelper.show('Error al eliminar', 'error');
        }
    }

    async reloadFromServer() {
        await this.loadShortcuts();
        NotificationHelper.show('Atajos recargados del servidor', 'success');
    }
}
