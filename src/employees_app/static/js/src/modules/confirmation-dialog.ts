/**
 * Confirmation Dialog Component
 * Accessible custom modal for destructive/confirmation actions
 */

interface ConfirmDialogOptions {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  confirmVariant?: 'primary' | 'danger' | 'warning';
  dangerMessage?: string;
  checkboxRequired?: boolean;
  checkboxLabel?: string;
}

type ConfirmDialogCallback = (confirmed: boolean) => void;

class ConfirmationDialog {
  private static instance: ConfirmationDialog | null = null;
  private dialogElement: HTMLDivElement | null = null;
  private resolveCallback: ConfirmDialogCallback | null = null;

  private constructor() {
    this.createDialogElement();
  }

  static getInstance(): ConfirmationDialog {
    if (!ConfirmationDialog.instance) {
      ConfirmationDialog.instance = new ConfirmationDialog();
    }
    return ConfirmationDialog.instance;
  }

  private createDialogElement(): void {
    if (typeof document === 'undefined') return;

    this.dialogElement = document.createElement('div');
    this.dialogElement.id = 'confirmation-dialog';
    this.dialogElement.className = 'confirmation-dialog';
    this.dialogElement.setAttribute('role', 'dialog');
    this.dialogElement.setAttribute('aria-modal', 'true');
    this.dialogElement.setAttribute('aria-labelledby', 'confirm-dialog-title');
    this.dialogElement.innerHTML = `
      <div class="confirmation-dialog__backdrop"></div>
      <div class="confirmation-dialog__content">
        <div class="confirmation-dialog__header">
          <h2 id="confirm-dialog-title" class="confirmation-dialog__title"></h2>
          <button type="button" class="confirmation-dialog__close" aria-label="Cerrar">&times;</button>
        </div>
        <div class="confirmation-dialog__body">
          <p class="confirmation-dialog__message"></p>
          <div class="confirmation-dialog__danger-zone" style="display: none;">
            <p class="confirmation-dialog__danger-message"></p>
          </div>
          <div class="confirmation-dialog__checkbox" style="display: none;">
            <input type="checkbox" id="confirm-dialog-checkbox">
            <label for="confirm-dialog-checkbox"></label>
          </div>
        </div>
        <div class="confirmation-dialog__footer">
          <button type="button" class="btn btn--secondary confirmation-dialog__cancel"></button>
          <button type="button" class="btn confirmation-dialog__confirm"></button>
        </div>
      </div>
    `;

    document.body.appendChild(this.dialogElement);

    this.attachEventListeners();
  }

  private attachEventListeners(): void {
    if (!this.dialogElement) return;

    const closeBtn = this.dialogElement.querySelector(
      '.confirmation-dialog__close'
    ) as HTMLButtonElement;
    const backdrop = this.dialogElement.querySelector(
      '.confirmation-dialog__backdrop'
    ) as HTMLDivElement;
    const cancelBtn = this.dialogElement.querySelector(
      '.confirmation-dialog__cancel'
    ) as HTMLButtonElement;
    const confirmBtn = this.dialogElement.querySelector(
      '.confirmation-dialog__confirm'
    ) as HTMLButtonElement;

    closeBtn?.addEventListener('click', () => this.resolve(false));
    backdrop?.addEventListener('click', () => this.resolve(false));
    cancelBtn?.addEventListener('click', () => this.resolve(false));
    confirmBtn?.addEventListener('click', () => this.resolve(true));

    document.addEventListener('keydown', this.handleKeyDown.bind(this));
  }

  private handleKeyDown(event: KeyboardEvent): void {
    if (!this.dialogElement?.classList.contains('active')) return;

    if (event.key === 'Escape') {
      this.resolve(false);
    }
  }

  private resolve(confirmed: boolean): void {
    if (!this.dialogElement) return;

    this.dialogElement.classList.remove('active');
    document.body.classList.remove('dialog-open');

    if (this.resolveCallback) {
      this.resolveCallback(confirmed);
      this.resolveCallback = null;
    }
  }

  async show(options: ConfirmDialogOptions): Promise<boolean> {
    if (!this.dialogElement) return false;

    const titleEl = this.dialogElement.querySelector('.confirmation-dialog__title') as HTMLElement;
    const messageEl = this.dialogElement.querySelector(
      '.confirmation-dialog__message'
    ) as HTMLElement;
    const dangerZone = this.dialogElement.querySelector(
      '.confirmation-dialog__danger-zone'
    ) as HTMLElement;
    const dangerMessageEl = this.dialogElement.querySelector(
      '.confirmation-dialog__danger-message'
    ) as HTMLElement;
    const checkbox = this.dialogElement.querySelector(
      '#confirm-dialog-checkbox'
    ) as HTMLInputElement;
    const checkboxLabel = this.dialogElement.querySelector(
      '.confirmation-dialog__checkbox label'
    ) as HTMLLabelElement;
    const checkboxContainer = this.dialogElement.querySelector(
      '.confirmation-dialog__checkbox'
    ) as HTMLElement;
    const cancelBtn = this.dialogElement.querySelector(
      '.confirmation-dialog__cancel'
    ) as HTMLButtonElement;
    const confirmBtn = this.dialogElement.querySelector(
      '.confirmation-dialog__confirm'
    ) as HTMLButtonElement;

    titleEl.textContent = options.title;
    messageEl.textContent = options.message;
    cancelBtn.textContent = options.cancelText || 'Cancelar';
    confirmBtn.textContent = options.confirmText || 'Confirmar';

    confirmBtn.className = 'btn';
    if (options.confirmVariant === 'danger') {
      confirmBtn.classList.add('btn--danger');
    } else if (options.confirmVariant === 'warning') {
      confirmBtn.classList.add('btn--warning');
    } else {
      confirmBtn.classList.add('btn--primary');
    }

    if (options.dangerMessage) {
      dangerZone.style.display = 'block';
      dangerMessageEl.textContent = options.dangerMessage;
    } else {
      dangerZone.style.display = 'none';
    }

    if (options.checkboxRequired) {
      checkboxContainer.style.display = 'flex';
      checkboxLabel.textContent = options.checkboxLabel || '';
      checkbox.checked = false;
      confirmBtn.disabled = true;
      checkbox.addEventListener(
        'change',
        () => {
          confirmBtn.disabled = !checkbox.checked;
        },
        { once: true }
      );
    } else {
      checkboxContainer.style.display = 'none';
      confirmBtn.disabled = false;
    }

    this.dialogElement.classList.add('active');
    document.body.classList.add('dialog-open');
    confirmBtn.focus();

    return new Promise((resolve) => {
      this.resolveCallback = resolve;
    });
  }

  static confirm(options: ConfirmDialogOptions): Promise<boolean> {
    return ConfirmationDialog.getInstance().show(options);
  }

  static destroy(): void {
    if (ConfirmationDialog.instance?.dialogElement) {
      ConfirmationDialog.instance.dialogElement.remove();
      ConfirmationDialog.instance.dialogElement = null;
    }
    ConfirmationDialog.instance = null;
  }
}

export function initConfirmationDialog(): void {
  if (typeof window !== 'undefined') {
    window.ConfirmationDialog = ConfirmationDialog;
  }
}

export function destroyConfirmationDialog(): void {
  ConfirmationDialog.destroy();
}

export default ConfirmationDialog;
