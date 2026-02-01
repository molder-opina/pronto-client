/**
 * Dashboard Keyboard Shortcuts (TypeScript port)
 * Configuración de atajos de teclado para el dashboard de empleados.
 */

import type { KeyboardShortcutManager } from '../types/global';

interface WindowWithShortcuts extends Window {
    keyboardShortcuts?: KeyboardShortcutManager;
}

const NAV_PREFIX = 'alt+shift+';

function navigateToSection(id: string): void {
    const el = document.getElementById(id);
    if (el) {
        el.scrollIntoView({ behavior: 'smooth' });
    }
}

function registerNavigation(shortcuts: KeyboardShortcutManager): void {
    shortcuts.register(`${NAV_PREFIX}2`, {
        description: 'Ir a Reportes',
        category: 'Navegación',
        callback: () => navigateToSection('reportes')
    });

    shortcuts.register(`${NAV_PREFIX}3`, {
        description: 'Ir a Órdenes en curso',
        category: 'Navegación',
        callback: () => navigateToSection('operaciones')
    });

    shortcuts.register(`${NAV_PREFIX}4`, {
        description: 'Ir a Operación de Meseros',
        category: 'Navegación',
        callback: () => navigateToSection('panel-meseros')
    });

    shortcuts.register(`${NAV_PREFIX}5`, {
        description: 'Ir a Operación de Cocina',
        category: 'Navegación',
        callback: () => navigateToSection('panel-cocina')
    });

    shortcuts.register(`${NAV_PREFIX}6`, {
        description: 'Ir a Caja',
        category: 'Navegación',
        callback: () => navigateToSection('caja')
    });

    shortcuts.register(`${NAV_PREFIX}7`, {
        description: 'Ir a Menú y productos',
        category: 'Navegación',
        callback: () => navigateToSection('menu')
    });

    shortcuts.register(`${NAV_PREFIX}8`, {
        description: 'Ir a Órdenes cerradas',
        category: 'Navegación',
        callback: () => navigateToSection('ordenes-cerradas')
    });
}

export function initDashboardShortcuts(): void {
    const win = window as WindowWithShortcuts;
    if (!win.keyboardShortcuts) {
        console.warn('KeyboardShortcutsManager no está disponible');
        return;
    }
    const shortcuts = win.keyboardShortcuts;
    registerNavigation(shortcuts);
}
