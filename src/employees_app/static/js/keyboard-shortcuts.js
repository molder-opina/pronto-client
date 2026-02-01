/**
 * Keyboard Shortcuts Manager
 * Sistema genérico y configurable de atajos de teclado.
 * Shared implementation for both clients and employees.
 */

class KeyboardShortcutsManager {
    constructor(options = {}) {
        this.shortcuts = new Map();
        this.enabled = true;
        this.showHelpModal = options.showHelp !== false;
        this.helpModal = null;

        // Elementos que deben ignorar shortcuts cuando están enfocados
        this.ignoredElements = options.ignoredElements || ['INPUT', 'TEXTAREA', 'SELECT'];

        // Prefijos para diferentes contextos
        this.contexts = new Map();
        this.currentContext = 'global';

        this.init();
    }

    init() {
        this.attachListener();
        if (this.showHelpModal) {
            this.createHelpModal();
        }
    }

    /**
     * Adjuntar listener global de teclado
     */
    attachListener() {
        document.addEventListener('keydown', (e) => this.handleKeyDown(e));
    }

    /**
     * Manejar evento de tecla presionada
     */
    handleKeyDown(event) {
        if (!this.enabled) return;

        // Ignorar si estamos en un input/textarea/select
        const tagName = event.target.tagName;
        if (this.ignoredElements.includes(tagName)) {
            const isHelpCombo = (event.altKey && event.shiftKey && event.key.toLowerCase() === 'h') ||
                                (event.ctrlKey && event.key === '?');
            if (event.key !== 'Escape' && !isHelpCombo) {
                return;
            }
        }

        // Crear key combo string (ej: "ctrl+k", "ctrl+shift+n")
        const combo = this.getKeyCombo(event);

        // Buscar shortcut en contexto actual primero, luego en global
        let shortcut = this.shortcuts.get(`${this.currentContext}:${combo}`);
        if (!shortcut) {
            shortcut = this.shortcuts.get(`global:${combo}`);
        }

        if (shortcut) {
            // Prevenir acción por defecto si el shortcut lo requiere
            if (shortcut.preventDefault !== false) {
                event.preventDefault();
            }

            // Ejecutar callback
            shortcut.callback(event);
        }
    }

    /**
     * Obtener string de combinación de teclas
     */
    getKeyCombo(event) {
        const parts = [];

        if (event.ctrlKey || event.metaKey) parts.push('ctrl');
        if (event.altKey) parts.push('alt');
        if (event.shiftKey) parts.push('shift');

        // Normalizar la tecla
        let key = event.key.toLowerCase();

        // Mapear teclas especiales
        const keyMap = {
            ' ': 'space',
            'arrowup': 'up',
            'arrowdown': 'down',
            'arrowleft': 'left',
            'arrowright': 'right'
        };

        key = keyMap[key] || key;
        parts.push(key);

        return parts.join('+');
    }

    /**
     * Registrar un nuevo shortcut
     */
    register(combo, options) {
        const context = options.context || 'global';
        const key = `${context}:${combo}`;

        this.shortcuts.set(key, {
            combo: combo,
            callback: options.callback,
            description: options.description || '',
            category: options.category || 'General',
            preventDefault: options.preventDefault !== false,
            context: context
        });

        return this;
    }

    /**
     * Desregistrar un shortcut
     */
    unregister(combo, context = 'global') {
        const key = `${context}:${combo}`;
        this.shortcuts.delete(key);
        return this;
    }

    /**
     * Cambiar contexto actual
     */
    setContext(context) {
        this.currentContext = context;
        return this;
    }

    /**
     * Habilitar/deshabilitar shortcuts
     */
    setEnabled(enabled) {
        this.enabled = enabled;
        return this;
    }

    /**
     * Crear modal de ayuda
     */
    createHelpModal() {
        const modal = document.createElement('div');
        modal.id = 'keyboard-shortcuts-modal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal__overlay" onclick="window.keyboardShortcuts.hideHelp()"></div>
            <div class="modal__content modal__content--large">
                <header class="modal__header">
                    <h2>⌨️ Atajos de teclado</h2>
                    <button type="button" class="modal__close" onclick="window.keyboardShortcuts.hideHelp()">✕</button>
                </header>
                <div class="modal__body" id="keyboard-shortcuts-list">
                    <!-- Lista de shortcuts se genera dinámicamente -->
                </div>
                <footer class="modal__footer">
                    <button type="button" class="btn btn--secondary" onclick="window.keyboardShortcuts.hideHelp()">
                        Cerrar
                    </button>
                </footer>
            </div>
        `;

        document.body.appendChild(modal);
        this.helpModal = modal;

        // Registrar shortcut para mostrar ayuda
        const showHelp = () => this.showHelp();

        this.register('alt+shift+h', {
            description: 'Mostrar ayuda de atajos de teclado',
            category: 'General',
            callback: showHelp
        });

        this.register('ctrl+?', {
            description: 'Mostrar ayuda de atajos de teclado',
            category: 'General',
            callback: showHelp
        });

        this.register('shift+?', {
            description: 'Mostrar ayuda de atajos de teclado',
            category: 'General',
            callback: showHelp
        });
    }

    /**
     * Mostrar modal de ayuda
     */
    showHelp() {
        if (!this.helpModal) return;

        // Generar lista de shortcuts agrupados por categoría
        const listContainer = document.getElementById('keyboard-shortcuts-list');
        if (!listContainer) return;

        const categories = new Map();

        // Agrupar shortcuts por categoría
        this.shortcuts.forEach(shortcut => {
            if (!categories.has(shortcut.category)) {
                categories.set(shortcut.category, []);
            }
            categories.get(shortcut.category).push(shortcut);
        });

        // Generar HTML
        let html = '';
        categories.forEach((shortcuts, category) => {
            html += `
                <div class="shortcuts-category">
                    <h3 class="shortcuts-category__title">${category}</h3>
                    <div class="shortcuts-list">
                        ${shortcuts.map(s => `
                            <div class="shortcut-item">
                                <div class="shortcut-item__keys">
                                    ${this.formatKeyCombo(s.combo)}
                                </div>
                                <div class="shortcut-item__description">
                                    ${s.description}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        });

        listContainer.innerHTML = html;
        this.helpModal.classList.add('active');
    }

    /**
     * Ocultar modal de ayuda
     */
    hideHelp() {
        if (this.helpModal) {
            this.helpModal.classList.remove('active');
        }
    }

    /**
     * Formatear combinación de teclas para mostrar
     */
    formatKeyCombo(combo) {
        const parts = combo.split('+');
        const keyNames = {
            'ctrl': '⌃ Ctrl',
            'alt': '⌥ Alt',
            'shift': '⇧ Shift',
            'space': '␣ Space',
            'enter': '↵ Enter',
            'escape': 'Esc',
            'up': '↑',
            'down': '↓',
            'left': '←',
            'right': '→'
        };

        return parts.map(part => {
            const displayName = keyNames[part] || part.toUpperCase();
            return `<kbd class="shortcut-key">${displayName}</kbd>`;
        }).join('<span class="shortcut-plus">+</span>');
    }

    /**
     * Obtener todos los shortcuts registrados
     */
    getAll() {
        return Array.from(this.shortcuts.values());
    }

    /**
     * Obtener shortcuts de una categoría específica
     */
    getByCategory(category) {
        return this.getAll().filter(s => s.category === category);
    }

    /**
     * Limpiar todos los shortcuts
     */
    clear() {
        this.shortcuts.clear();
        return this;
    }
}

// Crear instancia global si no existe
if (typeof window !== 'undefined' && !window.keyboardShortcuts) {
    window.keyboardShortcuts = new KeyboardShortcutsManager();
}

// Export para módulos
if (typeof module !== 'undefined' && module.exports) {
    module.exports = KeyboardShortcutsManager;
}
