type ShortcutConfig = {
  combo: string;
  description: string;
  category: string;
  callback_function: string;
  prevent_default: boolean;
};

type ShortcutCallback = () => void;

let loadedShortcuts: ShortcutConfig[] = [];

async function loadShortcutsFromAPI(): Promise<ShortcutConfig[]> {
  try {
    const res = await fetch('/api/shortcuts');
    if (!res.ok) throw new Error('Failed to load shortcuts');
    const data = await res.json();
    loadedShortcuts = data.shortcuts || [];
    return loadedShortcuts;
  } catch (e) {
    console.warn('[menu-shortcuts] Error loading shortcuts from API:', e);
    return [];
  }
}

function getCallback(functionName: string): ShortcutCallback | null {
  switch (functionName) {
    case 'goToHome':
      return goToHome;
    case 'viewOrder':
      return viewOrder;
    case 'viewTracker':
      return viewTracker;
    case 'focusSearch':
      return focusSearch;
    case 'showFilters':
      return showFilters;
    case 'confirmOrder':
      return confirmOrder;
    case 'viewCart':
      return viewCart;
    case 'requestCheckout':
      return requestCheckout;
    case 'cancelOrder':
      return cancelOrder;
    case 'closeActiveView':
      return closeActiveView;
    case 'refreshMenu':
      return refreshMenu;
    case 'navigateProductsNext':
      return () => navigateProducts('next');
    case 'navigateProductsPrev':
      return () => navigateProducts('prev');
    case 'openSelectedProduct':
      return openSelectedProduct;
    case 'adjustSelectedQuantityUp':
      return () => adjustSelectedQuantity(1);
    case 'adjustSelectedQuantityDown':
      return () => adjustSelectedQuantity(-1);
    case 'selectCategory1':
      return () => selectCategory(0);
    case 'selectCategory2':
      return () => selectCategory(1);
    case 'selectCategory3':
      return () => selectCategory(2);
    case 'selectCategory4':
      return () => selectCategory(3);
    case 'selectCategoryAll':
      return () => selectCategory('all');
    default:
      console.warn(`[menu-shortcuts] Unknown callback function: ${functionName}`);
      return null;
  }
}

export async function initMenuShortcuts(): Promise<void> {
  const maxRetries = 10;
  const retryDelay = 50;

  for (let i = 0; i < maxRetries; i++) {
    if (typeof window.keyboardShortcuts !== 'undefined') {
      const manager = window.keyboardShortcuts;

      const shortcuts = await loadShortcutsFromAPI();
      console.log(`[menu-shortcuts] Loaded ${shortcuts.length} shortcuts from API`);

      for (const shortcut of shortcuts) {
        const callback = getCallback(shortcut.callback_function);
        if (!callback) continue;

        manager.register(shortcut.combo, {
          description: shortcut.description,
          category: shortcut.category,
          callback,
          preventDefault: shortcut.prevent_default,
        });
      }
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, retryDelay));
  }

  console.warn('[menu-shortcuts] KeyboardShortcutsManager no disponible después de reintentos');
}

export function reloadShortcuts(): void {
  console.log('[menu-shortcuts] Reloading shortcuts...');
  loadShortcutsFromAPI().then((shortcuts) => {
    if (typeof window.keyboardShortcuts === 'undefined') return;
    console.log(`[menu-shortcuts] Loaded ${shortcuts.length} shortcuts from API`);
  });
}

function goToHome(): void {
  window.scrollTo({ top: 0, behavior: 'smooth' });
  window.resetFilters?.();
  window.showNotification?.('Volviendo al inicio', 'info');
}

function viewOrder(): void {
  const button =
    document.getElementById('view-order-btn') ||
    document.querySelector<HTMLButtonElement>('button[onclick*="viewOrder"]');
  if (button && button.offsetParent !== null) {
    button.click();
  } else {
    window.showNotification?.('No hay orden activa', 'warning');
  }
}

function viewTracker(): void {
  const button =
    document.getElementById('view-detail-btn') ||
    document.querySelector<HTMLButtonElement>('button[onclick*="viewFullTracker"]');
  if (button && button.offsetParent !== null) {
    button.click();
  } else {
    window.showNotification?.('No hay seguimiento disponible', 'warning');
  }
}

function focusSearch(): void {
  document.getElementById('menu-search')?.focus();
}

function showFilters(): void {
  document.getElementById('menu-filters')?.scrollIntoView({ behavior: 'smooth' });
}

function confirmOrder(): void {
  document
    .getElementById('checkout-form')
    ?.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
}

function viewCart(): void {
  window.toggleCart?.();
}

function requestCheckout(): void {
  window.requestCheckoutFromTracker?.();
}

function cancelOrder(): void {
  window.cancelPendingOrder?.();
}

function closeActiveView(): void {
  const modal = document.getElementById('item-modal');
  if (modal?.classList.contains('open')) {
    window.closeItemModal?.();
    return;
  }
  window.backToMenu?.();
}

function refreshMenu(): void {
  window.location.reload();
}

function navigateProducts(direction: 'next' | 'prev'): void {
  const cards = Array.from(document.querySelectorAll<HTMLDivElement>('.menu-item-card'));
  if (!cards.length) return;
  const currentIndex = cards.findIndex((card) => card.classList.contains('highlight'));
  const nextIndex =
    currentIndex === -1
      ? 0
      : direction === 'next'
        ? (currentIndex + 1) % cards.length
        : (currentIndex - 1 + cards.length) % cards.length;
  cards[currentIndex]?.classList.remove('highlight');
  const target = cards[nextIndex];
  target.classList.add('highlight');
  target.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function openSelectedProduct(): void {
  const selected = document.querySelector<HTMLElement>('.menu-item-card.highlight');
  if (!selected) return;
  const itemId = selected.dataset.itemId ? Number(selected.dataset.itemId) : null;
  if (itemId) {
    window.openItemModal?.(itemId);
  }
}

function adjustSelectedQuantity(delta: number): void {
  const selected = document.querySelector<HTMLElement>('.menu-item-card.highlight');
  if (!selected) return;
  const itemId = selected.dataset.itemId ? Number(selected.dataset.itemId) : null;
  if (!itemId) return;
  window.openItemModal?.(itemId);
  window.adjustModalQuantity?.(delta);
}

function selectCategory(index: number | 'all'): void {
  const tabs = document.querySelectorAll<HTMLButtonElement>('.category-tab');
  if (index === 'all') {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    return;
  }
  const tab = tabs[index];
  if (!tab) return;
  tab.click();
}
