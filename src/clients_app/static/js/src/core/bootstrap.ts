export type ModuleInitializer = (root: HTMLElement) => void;

export function bootstrapModule(
  rootSelector: string,
  init: ModuleInitializer,
  options: { name: string } = { name: 'module' }
): void {
  const handler = () => {
    const root = document.querySelector<HTMLElement>(rootSelector);
    if (!root) {
      console.debug(`[bootstrap:${options.name}] No se encontró el contenedor ${rootSelector}`);
      return;
    }
    init(root);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', handler);
  } else {
    handler();
  }
}
