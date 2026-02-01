/**
 * Branding Manager - Gestión de recursos de marca con IA
 * Permite subir, generar y administrar logos, iconos y banners
 */

interface BrandingConfig {
  restaurant_name: string;
  restaurant_slug: string;
  static_url: string;
  branding_url: string;
  files: {
    logo: boolean;
    icon: boolean;
    banner: boolean;
    placeholder: boolean;
  };
  product_images_count: number;
  available_apis: string[];
}

interface GenerateResult {
  type: string;
  success: boolean;
  path?: string;
  error?: string;
}

class BrandingManager {
  private container: HTMLElement | null = null;
  private config: BrandingConfig | null = null;
  private selectedApi: string = 'pollinations';
  private selectedStyle: string = 'modern';

  constructor() {
    this.init();
  }

  private async init(): Promise<void> {
    this.container = document.getElementById('branding-manager');
    if (!this.container) return;

    await this.loadConfig();
    this.render();
    this.bindEvents();
  }

  private async loadConfig(): Promise<void> {
    try {
      const response = await fetch('/api/branding/config');
      const data = await response.json();
      if (data.success) {
        this.config = data.data;
      }
    } catch (error) {
      console.error('Error cargando configuración de branding:', error);
    }
  }

  private render(): void {
    if (!this.container || !this.config) return;

    this.container.innerHTML = `
            <div class="branding-manager">
                <div class="branding-header">
                    <h2>Gestión de Marca</h2>
                    <p class="text-muted">Administra los recursos visuales de tu restaurante</p>
                </div>

                <div class="branding-grid">
                    <!-- Logo Principal -->
                    <div class="branding-card">
                        <div class="branding-preview ${this.config.files.logo ? 'has-image' : ''}">
                            ${
                              this.config.files.logo
                                ? `<img src="${this.config.branding_url}/logo.png?t=${Date.now()}" alt="Logo">`
                                : '<div class="placeholder-icon"><i class="icon-image"></i></div>'
                            }
                        </div>
                        <div class="branding-info">
                            <h4>Logo Principal</h4>
                            <p>512x512px recomendado</p>
                            <div class="branding-actions">
                                <input type="file" id="upload-logo" accept="image/*" hidden>
                                <button class="btn btn-sm btn-outline" data-upload="logo">
                                    <i class="icon-upload"></i> Subir
                                </button>
                                <button class="btn btn-sm btn-primary" data-generate="logo">
                                    <i class="icon-magic"></i> Generar con IA
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- Icono/Favicon -->
                    <div class="branding-card">
                        <div class="branding-preview small ${this.config.files.icon ? 'has-image' : ''}">
                            ${
                              this.config.files.icon
                                ? `<img src="${this.config.branding_url}/icon.png?t=${Date.now()}" alt="Icono">`
                                : '<div class="placeholder-icon"><i class="icon-image"></i></div>'
                            }
                        </div>
                        <div class="branding-info">
                            <h4>Icono / Favicon</h4>
                            <p>128x128px recomendado</p>
                            <div class="branding-actions">
                                <input type="file" id="upload-icon" accept="image/*" hidden>
                                <button class="btn btn-sm btn-outline" data-upload="icon">
                                    <i class="icon-upload"></i> Subir
                                </button>
                                <button class="btn btn-sm btn-primary" data-generate="icon">
                                    <i class="icon-magic"></i> Generar
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- Banner -->
                    <div class="branding-card wide">
                        <div class="branding-preview banner ${this.config.files.banner ? 'has-image' : ''}">
                            ${
                              this.config.files.banner
                                ? `<img src="${this.config.branding_url}/banner.png?t=${Date.now()}" alt="Banner">`
                                : '<div class="placeholder-icon"><i class="icon-image"></i></div>'
                            }
                        </div>
                        <div class="branding-info">
                            <h4>Banner</h4>
                            <p>1200x400px recomendado</p>
                            <div class="branding-actions">
                                <input type="file" id="upload-banner" accept="image/*" hidden>
                                <button class="btn btn-sm btn-outline" data-upload="banner">
                                    <i class="icon-upload"></i> Subir
                                </button>
                                <button class="btn btn-sm btn-primary" data-generate="banner">
                                    <i class="icon-magic"></i> Generar
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- Placeholder productos -->
                    <div class="branding-card">
                        <div class="branding-preview ${this.config.files.placeholder ? 'has-image' : ''}">
                            ${
                              this.config.files.placeholder
                                ? `<img src="${this.config.static_url}/assets/${this.config.restaurant_slug}/icons/placeholder.png?t=${Date.now()}" alt="Placeholder">`
                                : '<div class="placeholder-icon"><i class="icon-image"></i></div>'
                            }
                        </div>
                        <div class="branding-info">
                            <h4>Placeholder Productos</h4>
                            <p>256x256px - Imagen por defecto</p>
                            <div class="branding-actions">
                                <input type="file" id="upload-placeholder" accept="image/*" hidden>
                                <button class="btn btn-sm btn-outline" data-upload="placeholder">
                                    <i class="icon-upload"></i> Subir
                                </button>
                                <button class="btn btn-sm btn-primary" data-generate="placeholder">
                                    <i class="icon-magic"></i> Generar
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Generación con IA -->
                <div class="branding-section">
                    <h3>Generación con IA</h3>

                    <div class="generation-options">
                        <div class="option-group">
                            <label>API de Generación</label>
                            <select id="api-select" class="form-select">
                                <option value="pollinations" selected>Pollinations (Gratis)</option>
                                <option value="stability">Stability AI (Requiere API Key)</option>
                                <option value="replicate">Replicate (Requiere API Key)</option>
                            </select>
                        </div>

                        <div class="option-group">
                            <label>Estilo</label>
                            <select id="style-select" class="form-select">
                                <option value="modern" selected>Moderno</option>
                                <option value="classic">Clásico</option>
                                <option value="minimal">Minimalista</option>
                                <option value="playful">Divertido</option>
                            </select>
                        </div>

                        <button class="btn btn-lg btn-primary" id="generate-all">
                            <i class="icon-magic"></i> Generar Todo el Branding
                        </button>
                    </div>
                </div>

                <!-- Imágenes de Productos -->
                <div class="branding-section">
                    <h3>Imágenes de Productos</h3>
                    <p class="text-muted">
                        Imágenes generadas: <strong>${this.config.product_images_count}</strong>
                    </p>

                    <div class="product-generation">
                        <div class="option-group">
                            <label>Categoría (opcional)</label>
                            <input type="text" id="product-category" class="form-input" placeholder="Todas las categorías">
                        </div>

                        <div class="option-group">
                            <label>Límite</label>
                            <input type="number" id="product-limit" class="form-input" value="10" min="1" max="100">
                        </div>

                        <button class="btn btn-lg btn-secondary" id="generate-products">
                            <i class="icon-image"></i> Generar Imágenes de Productos
                        </button>
                    </div>
                </div>

                <!-- Estado -->
                <div id="branding-status" class="branding-status hidden"></div>
            </div>
        `;
  }

  private bindEvents(): void {
    if (!this.container) return;

    // Selects
    const apiSelect = this.container.querySelector('#api-select') as HTMLSelectElement;
    const styleSelect = this.container.querySelector('#style-select') as HTMLSelectElement;

    apiSelect?.addEventListener('change', () => {
      this.selectedApi = apiSelect.value;
    });

    styleSelect?.addEventListener('change', () => {
      this.selectedStyle = styleSelect.value;
    });

    // Botones de subir
    this.container.querySelectorAll('[data-upload]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        const type = (e.currentTarget as HTMLElement).dataset.upload;
        const input = this.container?.querySelector(`#upload-${type}`) as HTMLInputElement;
        input?.click();
      });
    });

    // Inputs de archivo
    ['logo', 'icon', 'banner', 'placeholder'].forEach((type) => {
      const input = this.container?.querySelector(`#upload-${type}`) as HTMLInputElement;
      input?.addEventListener('change', () => this.handleUpload(type, input));
    });

    // Botones de generar individual
    this.container.querySelectorAll('[data-generate]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        const type = (e.currentTarget as HTMLElement).dataset.generate;
        if (type) this.generateAsset(type);
      });
    });

    // Generar todo
    this.container.querySelector('#generate-all')?.addEventListener('click', () => {
      this.generateAsset('all');
    });

    // Generar productos
    const generateProductsBtn = this.container.querySelector(
      '#generate-products'
    ) as HTMLButtonElement;
    generateProductsBtn?.addEventListener('click', () => {
      this.validateAndGenerateProducts();
    });

    // Validar límite de productos
    const limitInput = this.container.querySelector('#product-limit') as HTMLInputElement;
    limitInput?.addEventListener('change', () => this.validateLimit());
    limitInput?.addEventListener('blur', () => this.validateLimit());
  }

  private validateLimit(): void {
    const limitInput = this.container?.querySelector('#product-limit') as HTMLInputElement;
    if (!limitInput) return;

    let value = parseInt(limitInput.value);
    const min = 1;
    const max = 100;

    if (isNaN(value) || value < min) {
      value = min;
    } else if (value > max) {
      value = max;
    }

    limitInput.value = value.toString();
  }

  private validateAndGenerateProducts(): void {
    this.validateLimit();
    this.generateProductImages();
  }

  private async handleUpload(type: string, input: HTMLInputElement): Promise<void> {
    const file = input.files?.[0];
    if (!file) return;

    this.showStatus('loading', `Subiendo ${type}...`);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`/api/branding/upload/${type}`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (data.success) {
        this.showStatus('success', `${type} actualizado correctamente`);
        await this.loadConfig();
        this.render();
        this.bindEvents();
      } else {
        this.showStatus('error', data.error || 'Error al subir');
      }
    } catch (error) {
      this.showStatus('error', 'Error de conexión');
    }
  }

  private async generateAsset(type: string): Promise<void> {
    this.showStatus('loading', `Generando ${type} con IA...`);

    try {
      const response = await fetch(`/api/branding/generate/${type}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api: this.selectedApi,
          style: this.selectedStyle,
        }),
      });

      const data = await response.json();

      if (data.success) {
        this.showStatus('success', 'Generación completada');
        await this.loadConfig();
        this.render();
        this.bindEvents();
      } else {
        const errors = data.results
          ?.filter((r: GenerateResult) => !r.success)
          .map((r: GenerateResult) => r.error)
          .join(', ');
        this.showStatus('error', errors || 'Error en la generación');
      }
    } catch (error) {
      this.showStatus('error', 'Error de conexión');
    }
  }

  private async generateProductImages(): Promise<void> {
    const category =
      (this.container?.querySelector('#product-category') as HTMLInputElement)?.value || '';
    const limit = parseInt(
      (this.container?.querySelector('#product-limit') as HTMLInputElement)?.value || '10'
    );

    this.showStatus('loading', 'Iniciando generación de imágenes de productos...');

    try {
      const response = await fetch('/api/branding/generate-products', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category,
          limit,
          api: this.selectedApi,
        }),
      });

      const data = await response.json();

      if (data.success) {
        this.showStatus(
          'success',
          `Generación iniciada en background. Procesando hasta ${limit} productos.`
        );
      } else {
        this.showStatus('error', data.error || 'Error al iniciar generación');
      }
    } catch (error) {
      this.showStatus('error', 'Error de conexión');
    }
  }

  private showStatus(type: 'loading' | 'success' | 'error', message: string): void {
    const status = this.container?.querySelector('#branding-status');
    if (!status) return;

    status.className = `branding-status ${type}`;
    status.innerHTML = `
            <span class="status-icon">
                ${type === 'loading' ? '<span class="spinner"></span>' : ''}
                ${type === 'success' ? '<i class="icon-check"></i>' : ''}
                ${type === 'error' ? '<i class="icon-x"></i>' : ''}
            </span>
            <span class="status-message">${message}</span>
        `;
    status.classList.remove('hidden');

    if (type !== 'loading') {
      setTimeout(() => status.classList.add('hidden'), 5000);
    }
  }
}

// Inicializar cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
  new BrandingManager();
});

export { BrandingManager };
