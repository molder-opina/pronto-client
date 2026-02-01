type DragOffsets = {
  x: number;
  y: number;
};

const MODAL_SELECTORS = [
  '.modal-content',
  '.waiter-filters-modal__content',
  '.partial-delivery-modal__content',
  '.table-assignment-modal__panel',
  '.payment-modal-content',
];

const HANDLE_SELECTORS = [
  '.modal-header',
  '.waiter-filters-modal__header',
  '.partial-delivery-modal__header',
  '.table-assignment-modal__header',
  '.payment-modal-header',
];

const INTERACTIVE_SELECTOR = 'button, a, input, select, textarea, [data-drag-ignore]';

export function initDraggableModals(): void {
  const modals = MODAL_SELECTORS.flatMap((selector) =>
    Array.from(document.querySelectorAll<HTMLElement>(selector))
  );

  modals.forEach((modal) => {
    const handle = findHandle(modal);
    if (!handle || handle.dataset.dragBound === 'true') return;

    handle.dataset.dragBound = 'true';
    handle.style.cursor = 'move';
    handle.style.userSelect = 'none';

    handle.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest(INTERACTIVE_SELECTOR)) return;

      event.preventDefault();
      const startX = event.clientX;
      const startY = event.clientY;
      const origin = getOffsets(modal);

      const onMove = (moveEvent: PointerEvent) => {
        const nextX = origin.x + moveEvent.clientX - startX;
        const nextY = origin.y + moveEvent.clientY - startY;
        applyOffsets(modal, { x: nextX, y: nextY });
      };

      const onUp = () => {
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onUp);
      };

      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
      handle.setPointerCapture?.(event.pointerId);
    });
  });
}

function findHandle(modal: HTMLElement): HTMLElement | null {
  for (const selector of HANDLE_SELECTORS) {
    const handle = modal.querySelector<HTMLElement>(selector);
    if (handle) return handle;
  }
  return null;
}

function getOffsets(modal: HTMLElement): DragOffsets {
  const x = Number.parseFloat(modal.dataset.dragX || '0');
  const y = Number.parseFloat(modal.dataset.dragY || '0');
  return { x, y };
}

function applyOffsets(modal: HTMLElement, offsets: DragOffsets): void {
  modal.dataset.dragX = offsets.x.toString();
  modal.dataset.dragY = offsets.y.toString();
  modal.style.transform = `translate3d(${offsets.x}px, ${offsets.y}px, 0)`;
}
