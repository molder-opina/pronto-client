export function mountPlaceholder(moduleName: string, root: HTMLElement): void {
  root.setAttribute('data-placeholder-module', moduleName);
  console.info(`[placeholder:${moduleName}] módulo pendiente de implementación`, root);
}
