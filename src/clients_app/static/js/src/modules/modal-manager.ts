/**
 * MODAL MANAGER - Item Modal and Modifiers
 * Handles item modal display, modifier selection, and validation
 */

import type { CartItem } from './cart-manager';

export interface MenuModifier {
  id: number;
  name: string;
  price_adjustment: number;
  is_available: boolean;
}

export interface MenuModifierGroup {
  id: number;
  name: string;
  description?: string | null;
  min_selection: number;
  max_selection: number;
  is_required: boolean;
  modifiers: MenuModifier[];
}

export interface MenuItem {
  id: number;
  name: string;
  description?: string | null;
  price: number;
  image_path?: string | null;
  is_available: boolean;
  preparation_time_minutes?: number;
  is_quick_serve?: boolean;
  is_breakfast_recommended?: boolean;
  is_afternoon_recommended?: boolean;
  is_night_recommended?: boolean;
  modifier_groups?: MenuModifierGroup[];
}

export class ModalManager {
  private currentItem: MenuItem | null = null;
  private modalQuantity = 1;
  private selectedModifiers: Map<number, Set<number>> = new Map();
  private previousFocus: HTMLElement | null = null;
  private focusTrapActive = false;
  private liveRegion: HTMLElement | null = null;

  private readonly elements = {
    modal: document.getElementById('item-modal'),
    modalName: document.getElementById('modal-item-name'),
    modalDescription: document.getElementById('modal-item-description'),
    modalImage: document.getElementById('modal-item-image') as HTMLImageElement | null,
    modalQuantity: document.getElementById('modal-quantity'),
    modalPrice: document.getElementById('modal-total-price'),
    modalBasePrice: document.getElementById('modal-base-price'),
    modalExtrasPrice: document.getElementById('modal-extras-price'),
    modalExtrasPriceRow: document.getElementById('modal-extras-price-row'),
    modalBreakdownTotal: document.getElementById('modal-breakdown-total'),
    extrasSection: document.getElementById('extras-section'),
    extrasList: document.getElementById('extras-list'),
    addToCartButton: document.querySelector<HTMLButtonElement>('.modal-add-to-cart'),
  };

  constructor() {
    this.createLiveRegion();
  }

  /**
   * Create live region for screen reader announcements
   */
  private createLiveRegion(): void {
    if (typeof document === 'undefined') return;
    this.liveRegion = document.createElement('div');
    this.liveRegion.setAttribute('aria-live', 'polite');
    this.liveRegion.setAttribute('aria-atomic', 'true');
    this.liveRegion.className = 'sr-only';
    this.liveRegion.id = 'modal-live-region';
    document.body.appendChild(this.liveRegion);
  }

  /**
   * Announce message to screen readers
   */
  private announce(message: string): void {
    if (this.liveRegion) {
      this.liveRegion.textContent = '';
      setTimeout(() => {
        if (this.liveRegion) {
          this.liveRegion.textContent = message;
        }
      }, 100);
    }
  }

  /**
   * Get all focusable elements within the modal
   */
  private getFocusableElements(): HTMLElement[] {
    if (!this.elements.modal) return [];
    return Array.from(
      this.elements.modal.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
    ).filter((el) => !el.hasAttribute('disabled') && el.tabIndex !== -1);
  }

  /**
   * Handle focus trap for keyboard navigation
   */
  private handleFocusTrap(event: KeyboardEvent): void {
    if (event.key !== 'Tab' || !this.focusTrapActive) return;

    const focusableElements = this.getFocusableElements();
    if (focusableElements.length === 0) return;

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    if (event.shiftKey) {
      if (document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      }
    } else {
      if (document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    }
  }

  /**
   * Activate focus trap for the modal
   */
  private activateFocusTrap(): void {
    this.focusTrapActive = true;
    document.addEventListener('keydown', this.handleFocusTrap.bind(this));

    const focusableElements = this.getFocusableElements();
    if (focusableElements.length > 0) {
      focusableElements[0].focus();
    }
  }

  /**
   * Deactivate focus trap for the modal
   */
  private deactivateFocusTrap(): void {
    this.focusTrapActive = false;
    document.removeEventListener('keydown', this.handleFocusTrap.bind(this));
  }

  /**
   * Open item modal for given menu item
   */
  public openModal(item: MenuItem, formatPrice: (value: number) => string): void {
    if (!this.elements.modal || !this.elements.modalName || !this.elements.modalDescription) {
      return;
    }

    if (!item.is_available) {
      window.showNotification?.('Producto agotado', 'warning');
      this.announce('Producto agotado');
      return;
    }

    this.currentItem = item;
    this.modalQuantity = 1;
    this.selectedModifiers.clear();

    const baseUrl = window.APP_CONFIG?.static_host_url || '';
    const assets = window.APP_CONFIG?.restaurant_assets || '';
    const image = item.image_path
      ? `${baseUrl}${item.image_path}`
      : `${assets}/icons/placeholder.png`;

    this.elements.modalName.textContent = item.name;
    this.elements.modalDescription.textContent = item.description || 'Sin descripción';

    if (this.elements.modalImage) {
      // Reset error state before loading new image
      this.elements.modalImage.classList.remove('img-error');
      this.elements.modalImage.parentElement?.classList.remove('modal-item-image--placeholder');
      this.elements.modalImage.src = image;
      this.elements.modalImage.onerror = () => {
        this.elements.modalImage?.classList.add('img-error');
        this.elements.modalImage?.parentElement?.classList.add('modal-item-image--placeholder');
      };
    }

    if (this.elements.modalQuantity) {
      this.elements.modalQuantity.textContent = '1';
    }

    this.renderModifierGroups(item.modifier_groups || [], formatPrice);
    this.updateModalPrice(formatPrice);
    this.updateAddToCartState();

    this.previousFocus = document.activeElement as HTMLElement;
    this.elements.modal.classList.add('open');
    this.activateFocusTrap();

    this.announce(`Modal abierto para ${item.name}. ${item.description || ''}`);

    const modalInner = this.elements.modal.querySelector('.modal') as HTMLElement;
    if (modalInner) {
      modalInner.scrollTop = 0;
    }
    const modalBody = this.elements.modal.querySelector('.modal-body') as HTMLElement;
    if (modalBody) {
      modalBody.scrollTop = 0;
    }
    this.elements.modal.scrollTop = 0;
    // Remove window scroll as it might be jarring and unnecessary for fixed modal
    // window.scrollTo({ top: 0, behavior: 'smooth' });

    this.scrollToRequiredModifiers();
  }

  /**
   * Close item modal
   */
  public closeModal(): void {
    this.deactivateFocusTrap();
    this.announce('Modal cerrado');
    this.elements.modal?.classList.remove('open');
    this.currentItem = null;

    if (this.previousFocus && document.body.contains(this.previousFocus)) {
      this.previousFocus.focus();
      this.previousFocus = null;
    }
  }

  /**
   * Adjust modal quantity by delta
   */
  public adjustQuantity(delta: number, formatPrice: (value: number) => string): void {
    this.modalQuantity = Math.max(1, this.modalQuantity + delta);

    if (this.elements.modalQuantity) {
      this.elements.modalQuantity.textContent = String(this.modalQuantity);
    }

    this.updateModalPrice(formatPrice);
  }

  /**
   * Validate current item modifiers and return cart item if valid
   */
  public getCartItemIfValid(): CartItem | null {
    if (!this.currentItem) return null;

    if (!this.currentItem.is_available) {
      window.showNotification?.('Producto agotado', 'warning');
      return null;
    }

    // Enforce validation for required and limited modifier groups
    if (!this.validateCurrentItemModifiers()) {
      return null;
    }

    const modifiers: number[] = [];
    const extras: string[] = [];
    let extrasTotal = 0;

    this.currentItem.modifier_groups?.forEach((group) => {
      const selection = this.selectedModifiers.get(group.id);
      if (!selection || !selection.size) return;

      selection.forEach((modifierId) => {
        const modifier = group.modifiers.find((mod) => mod.id === modifierId);
        if (modifier) {
          modifiers.push(modifier.id);
          extras.push(modifier.name);
          extrasTotal += modifier.price_adjustment;
        }
      });
    });

    const baseUrl = window.APP_CONFIG?.static_host_url || '';
    const assets = window.APP_CONFIG?.restaurant_assets || '';
    const image = this.currentItem.image_path
      ? `${baseUrl}${this.currentItem.image_path}`
      : `${assets}/icons/placeholder.png`;

    return {
      id: this.currentItem.id,
      name: this.currentItem.name,
      price: this.currentItem.price,
      quantity: this.modalQuantity,
      image,
      extras,
      extrasTotal,
      modifiers,
    };
  }

  /**
   * Handle modifier selection change
   */
  public handleModifierChange(
    groupId: number,
    modifierId: number,
    maxSelection: number,
    checked: boolean,
    isSingle = false,
    input?: HTMLInputElement | null,
    formatPrice?: (value: number) => string
  ): boolean {
    if (!this.selectedModifiers.has(groupId)) {
      this.selectedModifiers.set(groupId, new Set());
    }

    const selection = this.selectedModifiers.get(groupId)!;

    if (isSingle) {
      selection.clear();
      if (checked) selection.add(modifierId);
    } else if (checked) {
      if (maxSelection > 0 && selection.size >= maxSelection) {
        // Reject the new selection and keep existing ones intact
        if (input) input.checked = false;
        this.showModifierLimitError(groupId, maxSelection);
        return false;
      }
      selection.add(modifierId);
    } else {
      selection.delete(modifierId);
    }

    if (formatPrice) {
      this.updateModalPrice(formatPrice);
    }

    this.updateAddToCartState();

    return true;
  }

  /**
   * Update modifier group UI (counter, error states)
   */
  public updateModifierGroupUI(groupId: number): void {
    if (!this.currentItem || !this.currentItem.modifier_groups || !this.elements.extrasList) {
      return;
    }

    const group = this.currentItem.modifier_groups.find((g) => g.id === groupId);
    if (!group) return;

    const groupEl = this.elements.extrasList.querySelector<HTMLElement>(
      `.modifier-group[data-group-id="${groupId}"]`
    );
    if (!groupEl) return;

    const selection = this.selectedModifiers.get(groupId);
    const selectedCount = selection ? selection.size : 0;
    const counterEl = groupEl.querySelector<HTMLElement>('.modifier-selection-counter');
    const errorEl = groupEl.querySelector<HTMLElement>('.modifier-group__error');

    const max = group.max_selection || group.min_selection || selectedCount || 0;

    if (counterEl) {
      counterEl.textContent = `${selectedCount}/${max}`;
      counterEl.classList.toggle(
        'modifier-selection-counter--full',
        max > 0 && selectedCount >= max
      );
    }

    // Clear error feedback as the user interacts
    groupEl.classList.remove('modifier-group--error');
    if (errorEl) {
      errorEl.textContent = '';
    }

    this.updateAddToCartState();
  }

  /**
   * Render modifier groups in modal
   */
  private renderModifierGroups(
    groups: MenuModifierGroup[],
    formatPrice: (value: number) => string
  ): void {
    if (!this.elements.extrasSection || !this.elements.extrasList) return;

    if (!groups.length) {
      this.elements.extrasSection.style.display = 'none';
      this.elements.extrasList.replaceChildren();
      return;
    }

    this.elements.extrasSection.style.display = 'block';

    const html = groups
      .map((group) => {
        const controlType = group.max_selection === 1 ? 'radio' : 'checkbox';
        const isRequired = group.is_required || group.min_selection > 0;
        const requirementLabel = isRequired
          ? 'OBLIGATORIO'
          : group.max_selection
            ? `Opcional · Máx. ${group.max_selection}`
            : 'Opcional';
        const counterMax = group.max_selection || group.min_selection || 0;
        const groupId = escapeHtml(String(group.id));
        const groupName = escapeHtml(group.name);
        const groupDescription = group.description ? escapeHtml(group.description) : '';
        const minSelection = escapeHtml(String(group.min_selection));
        const maxSelection = escapeHtml(String(group.max_selection));
        const modifiersHtml = group.modifiers
          .filter((modifier) => modifier.is_available)
          .map((modifier) => {
            const modifierId = escapeHtml(String(modifier.id));
            const modifierName = escapeHtml(modifier.name);
            const priceAdjustment = escapeHtml(String(modifier.price_adjustment));
            const extraPrice =
              modifier.price_adjustment > 0
                ? `+${escapeHtml(formatPrice(modifier.price_adjustment))}`
                : '';
            const maxAttr =
              controlType === 'radio'
                ? ''
                : `data-max="${escapeHtml(String(group.max_selection))}"`;
            return `
                    <label class="extra-option">
                      <input type="${controlType}" name="modifier-${groupId}" value="${modifierId}"
                          data-group="${groupId}" data-modifier="${modifierId}"
                          data-price="${priceAdjustment}"
                          ${maxAttr}
                      >
                      <span class="extra-label">${modifierName}</span>
                      <span class="extra-price">${extraPrice}</span>
                    </label>`;
          })
          .join('');

        return `
          <div class="modifier-group" data-group-id="${groupId}"
               data-required="${isRequired ? 'true' : 'false'}"
               data-min="${minSelection}" data-max="${maxSelection}">
            <div class="modifier-group__header">
              <h4>${groupName}${isRequired ? ' *' : ''}</h4>
              <span class="modifier-required-badge">${escapeHtml(requirementLabel)}</span>
              <span class="modifier-selection-counter" data-counter-for="${groupId}">
                0/${escapeHtml(String(counterMax))}
              </span>
            </div>
            ${group.description ? `<p class="modifier-description">${groupDescription}</p>` : ''}
            <div class="modifiers-list">
              ${modifiersHtml}
            </div>
            <div class="modifier-group__error" data-error-for="${groupId}"></div>
          </div>`;
      })
      .join('');

    this.elements.extrasList.replaceChildren(createFragment(html));

    // Attach event listeners to modifier inputs
    this.elements.extrasList
      .querySelectorAll<HTMLInputElement>('input[type="checkbox"],input[type="radio"]')
      .forEach((input) => {
        input.addEventListener('change', (event) => {
          const target = event.target as HTMLInputElement;
          const groupId = Number(target.dataset.group);
          const modifierId = Number(target.dataset.modifier);
          const maxSelection = Number(target.dataset.max) || 1;

          const allowed = this.handleModifierChange(
            groupId,
            modifierId,
            maxSelection,
            target.checked,
            target.type === 'radio',
            target,
            formatPrice
          );

          if (allowed === false) {
            return;
          }

          this.updateModifierGroupUI(groupId);
        });
      });
  }

  /**
   * Scroll to required modifiers section
   */
  private scrollToRequiredModifiers(): void {
    if (!this.currentItem || !this.currentItem.modifier_groups || !this.elements.extrasList) {
      return;
    }

    const requiredGroup = this.currentItem.modifier_groups.find(
      (group) => group.is_required || group.min_selection > 0
    );

    if (!requiredGroup) return;

    const groupEl = this.elements.extrasList.querySelector<HTMLElement>(
      `.modifier-group[data-group-id="${requiredGroup.id}"]`
    );

    if (!groupEl) return;

    const modalContainer = this.elements.modal?.querySelector<HTMLElement>('.modal');
    const scrollContainer = groupEl.closest<HTMLElement>('.modal-body') || modalContainer;

    if (!scrollContainer) return;

    const containerRect = scrollContainer.getBoundingClientRect();
    const groupRect = groupEl.getBoundingClientRect();
    const isVisible =
      groupRect.top >= containerRect.top && groupRect.bottom <= containerRect.bottom;

    if (isVisible) return;

    const targetTop = Math.max(0, groupEl.offsetTop - 12);
    scrollContainer.scrollTo({ top: targetTop, behavior: 'smooth' });
  }

  /**
   * Show modifier limit error
   */
  private showModifierLimitError(groupId: number, maxSelection: number): void {
    if (!this.elements.extrasList) return;

    const groupEl = this.elements.extrasList.querySelector<HTMLElement>(
      `.modifier-group[data-group-id="${groupId}"]`
    );

    if (!groupEl) return;

    const errorEl = groupEl.querySelector<HTMLElement>('.modifier-group__error');
    groupEl.classList.add('modifier-group--error');

    if (errorEl) {
      errorEl.textContent = `Máximo ${maxSelection} opción(es) permitidas.`;
    }

    window.showNotification?.(`Solo puedes elegir hasta ${maxSelection} opción(es).`, 'warning');
  }

  /**
   * Validate current item modifiers
   */
  private validateCurrentItemModifiers(): boolean {
    if (!this.currentItem || !this.currentItem.modifier_groups || !this.elements.extrasList) {
      return true;
    }

    let isValid = true;
    let firstInvalidGroup: HTMLElement | null = null;
    let firstInvalidMessage = '';

    for (const group of this.currentItem.modifier_groups) {
      const selection = this.selectedModifiers.get(group.id);
      const selectedCount = selection ? selection.size : 0;

      const groupEl = this.elements.extrasList!.querySelector<HTMLElement>(
        `.modifier-group[data-group-id="${group.id}"]`
      );

      if (!groupEl) continue;

      const errorEl = groupEl.querySelector<HTMLElement>('.modifier-group__error');
      const counterEl = groupEl.querySelector<HTMLElement>('.modifier-selection-counter');

      const max = group.max_selection || group.min_selection || selectedCount || 0;

      if (counterEl) {
        counterEl.textContent = `${selectedCount}/${max}`;
        counterEl.classList.toggle(
          'modifier-selection-counter--full',
          max > 0 && selectedCount >= max
        );
      }

      let errorMsg = '';

      const requiresSelection = group.is_required || group.min_selection > 0;
      const minRequired = group.min_selection > 0 ? group.min_selection : group.is_required ? 1 : 0;

      if (requiresSelection && selectedCount < minRequired) {
        const groupLabel = group.name ? ` en "${group.name}"` : '';

        if (group.min_selection === group.max_selection && group.min_selection > 0) {
          const isDressing = (group.name || '').toLowerCase().includes('aderezo');
          const label = isDressing ? 'aderezos incluidos' : 'opción(es)';
          errorMsg = `Selecciona ${group.min_selection} ${label} (${selectedCount}/${group.min_selection}).`;
        } else {
          errorMsg = `Selecciona al menos ${minRequired} opción(es)${groupLabel}.`;
        }
      } else if (group.max_selection && selectedCount > group.max_selection) {
        const groupLabel = group.name ? ` en "${group.name}"` : '';
        errorMsg = `No puedes seleccionar más de ${group.max_selection} opción(es)${groupLabel}.`;
      }

      if (errorMsg) {
        groupEl.classList.add('modifier-group--error');
        if (errorEl) errorEl.textContent = errorMsg;

        if (!firstInvalidGroup) {
          firstInvalidGroup = groupEl;
          if (!firstInvalidMessage) {
            firstInvalidMessage = group.name
              ? `Por favor selecciona ${group.name}`
              : 'Por favor selecciona las opciones obligatorias';
          }
        }

        isValid = false;
      } else {
        groupEl.classList.remove('modifier-group--error');
        if (errorEl) errorEl.textContent = '';
      }
    }

    if (!isValid && firstInvalidGroup) {
      firstInvalidGroup.scrollIntoView({ behavior: 'smooth', block: 'center' });

      window.showNotification?.(
        firstInvalidMessage || 'Completa los aditamentos obligatorios antes de continuar.',
        'error'
      );

      const addButton = this.getAddToCartButton();
      if (addButton) {
        // Remove class first to re-trigger animation if clicked rapidly
        addButton.classList.remove('shake-error');
        void addButton.offsetWidth; // Trigger reflow
        addButton.classList.add('shake-error');

        // Ensure tooltip is visible or some text feedback near button
        const priceSpan = document.getElementById('modal-total-price');
        if (priceSpan) {
          const originalText = priceSpan.innerText;
          // priceSpan.innerText = "Faltan opciones";
          setTimeout(() => {
            //   if(priceSpan) priceSpan.innerText = originalText;
            addButton.classList.remove('shake-error');
          }, 500);
        } else {
          setTimeout(() => addButton.classList.remove('shake-error'), 500);
        }
      }
    }

    return isValid;
  }

  private canSubmitCurrentItem(): boolean {
    if (!this.currentItem || !this.currentItem.is_available) {
      return false;
    }

    if (!this.currentItem.modifier_groups || !this.currentItem.modifier_groups.length) {
      return true;
    }

    for (const group of this.currentItem.modifier_groups) {
      const selection = this.selectedModifiers.get(group.id);
      const selectedCount = selection ? selection.size : 0;
      const requiredMin = group.min_selection > 0 ? group.min_selection : group.is_required ? 1 : 0;

      if (requiredMin > 0 && selectedCount < requiredMin) {
        return false;
      }

      if (group.max_selection && selectedCount > group.max_selection) {
        return false;
      }
    }

    return true;
  }

  /**
   * Check if customer has provided email or phone
   */
  public hasCustomerContact(): boolean {
    try {
      // Check if session has customer data
      const session = (window as any).APP_SESSION;
      if (session?.customer?.email || session?.customer?.phone) {
        return true;
      }

      // Check form inputs directly
      const emailInput = document.getElementById('customer-email') as HTMLInputElement | null;
      const phoneInput = document.getElementById('customer-phone') as HTMLInputElement | null;

      const email = emailInput?.value?.trim();
      const phone = phoneInput?.value?.trim();

      return !!(email || phone);
    } catch (error) {
      console.warn('[ModalManager] Error checking customer contact:', error);
      return true; // Allow proceeding if check fails
    }
  }

  private getFirstMissingRequiredGroupName(): string | null {
    if (!this.currentItem?.modifier_groups) return null;

    for (const group of this.currentItem.modifier_groups) {
      const selection = this.selectedModifiers.get(group.id);
      const selectedCount = selection ? selection.size : 0;
      const requiredMin = group.min_selection > 0 ? group.min_selection : group.is_required ? 1 : 0;

      if (requiredMin > 0 && selectedCount < requiredMin) {
        return group.name || null;
      }
    }

    return null;
  }

  private getAddToCartButton(): HTMLButtonElement | null {
    const button = this.elements.addToCartButton;
    if (button && document.body.contains(button)) {
      return button;
    }

    const refreshed =
      this.elements.modal?.querySelector<HTMLButtonElement>('.modal-add-to-cart') ||
      document.querySelector<HTMLButtonElement>('.modal-add-to-cart');

    this.elements.addToCartButton = refreshed || null;
    return this.elements.addToCartButton;
  }

  private updateAddToCartState(): void {
    const button = this.getAddToCartButton();
    if (!button) return;

    // Disable button until all required fields are selected
    // This is better UX than allowing clicks and showing errors after
    const canSubmit = this.canSubmitCurrentItem();
    button.classList.toggle('is-disabled', !canSubmit);
    button.disabled = !canSubmit;
    button.setAttribute('aria-disabled', String(!canSubmit));

    if (!canSubmit && this.currentItem?.modifier_groups) {
      const missingGroup = this.getFirstMissingRequiredGroupName();
      let message = '';

      if (missingGroup) {
        message = `Selecciona: ${missingGroup}`;
      } else {
        message = 'Completa las opciones obligatorias';
      }

      button.title = message;
      button.setAttribute('aria-label', `Agregar al carrito: ${message}`);
    } else {
      button.title = '';
      button.removeAttribute('aria-label');
    }
  }

  /**
   * Update modal price display
   */
  private updateModalPrice(formatPrice: (value: number) => string): void {
    if (!this.currentItem || !this.elements.modalPrice) return;

    const extrasTotal = this.calculateExtrasTotal();
    const basePrice = this.currentItem.price * this.modalQuantity;
    const total = (this.currentItem.price + extrasTotal) * this.modalQuantity;

    // Update main price button
    this.elements.modalPrice.textContent = formatPrice(total);

    // Update price breakdown if elements exist
    if (this.elements.modalBasePrice) {
      this.elements.modalBasePrice.textContent = formatPrice(basePrice);
    }

    if (this.elements.modalExtrasPrice) {
      this.elements.modalExtrasPrice.textContent = formatPrice(extrasTotal * this.modalQuantity);
    }

    if (this.elements.modalBreakdownTotal) {
      this.elements.modalBreakdownTotal.textContent = formatPrice(total);
    }

    // Hide extras row if no extras selected
    if (this.elements.modalExtrasPriceRow) {
      this.elements.modalExtrasPriceRow.style.display = extrasTotal > 0 ? 'flex' : 'none';
    }
  }

  /**
   * Calculate total price of selected extras/modifiers
   */
  private calculateExtrasTotal(): number {
    if (!this.currentItem?.modifier_groups) return 0;

    let total = 0;

    this.currentItem.modifier_groups.forEach((group) => {
      const selection = this.selectedModifiers.get(group.id);
      if (!selection?.size) return;

      selection.forEach((modifierId) => {
        const modifier = group.modifiers.find((mod) => mod.id === modifierId);
        if (modifier) total += modifier.price_adjustment;
      });
    });

    return total;
  }
}

const createFragment = (html: string): DocumentFragment =>
  document.createRange().createContextualFragment(html);

const escapeHtml = (value: string): string => {
  const div = document.createElement('div');
  div.textContent = value;
  return div.innerHTML;
};
