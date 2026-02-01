export type ModuleInitializer = (root: HTMLElement) => void;

/**
 * Helper que espera al DOM y monta un módulo cuando encuentra el contenedor raíz.
 */
export function bootstrapModule(
    rootSelector: string,
    init: ModuleInitializer,
    options: { name: string } = { name: 'module' }
): void {
    document.addEventListener('DOMContentLoaded', () => {
        const root = document.querySelector<HTMLElement>(rootSelector);
        if (!root) {
            console.warn(`[bootstrap:${options.name}] No se encontró el contenedor ${rootSelector}`);
            return;
        }
        init(root);
    });
}
