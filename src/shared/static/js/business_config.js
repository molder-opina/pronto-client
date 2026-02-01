/**
 * Business Configuration Management - OOP Refactored
 * Handles business info, schedule, and advanced settings
 */

/**
 * Tab Manager - Handles tab navigation
 */
class TabManager {
    constructor() {
        this.tabButtons = document.querySelectorAll('.tab-btn');
        this.tabContents = document.querySelectorAll('.tab-content');
    }

    init() {
        this.tabButtons.forEach(btn => {
            btn.addEventListener('click', () => this.switchTab(btn.dataset.tab));
        });
    }

    switchTab(tabName) {
        this.tabButtons.forEach(b => b.classList.remove('active'));
        this.tabContents.forEach(content => {
            content.classList.remove('active');
            if (content.id === `${tabName}-tab`) {
                content.classList.add('active');
            }
        });

        const activeBtn = document.querySelector(`[data-tab="${tabName}"]`);
        if (activeBtn) activeBtn.classList.add('active');
    }
}

/**
 * Business Info Manager - Handles business info CRUD
 */
class BusinessInfoManager {
    constructor() {
        this.data = null;
        this.form = document.getElementById('business-info-form');
    }

    async load() {
        try {
            const response = await fetch('/api/business-info');
            const result = await response.json();

            if (result.success && result.data) {
                this.data = result.data;
                this.populateForm(result.data);
            }
        } catch (error) {
            console.error('Error loading business info:', error);
            NotificationHelper.show('Error al cargar información del negocio', 'error');
        }
    }

    populateForm(data) {
        if (!this.form) return;

        Object.keys(data).forEach(key => {
            const input = this.form.querySelector(`[name="${key}"]`);
            if (input && data[key]) {
                input.value = data[key];
            }
        });

        if (data.logo_url) {
            this.updateLogoPreview(data.logo_url);
        }
    }

    async save(formData) {
        const validation = this.validate(formData);
        if (!validation.valid) {
            NotificationHelper.show(validation.message || 'Datos inválidos', 'error');
            return;
        }
        const payload = validation.data || formData;
        try {
            const response = await fetch('/api/business-info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            if (result.success) {
                this.data = result.data;
                NotificationHelper.show('Información guardada correctamente', 'success');
            } else {
                NotificationHelper.show(result.message || 'Error al guardar', 'error');
            }
        } catch (error) {
            console.error('Error saving business info:', error);
            NotificationHelper.show('Error al guardar información', 'error');
        }
    }

    validate(data) {
        const trimmed = {};
        Object.keys(data || {}).forEach((key) => {
            const value = data[key];
            trimmed[key] = typeof value === 'string' ? value.trim() : value;
        });

        const businessName = trimmed.business_name || '';
        if (!businessName || businessName.length < 1) {
            return { valid: false, message: 'El nombre del negocio es obligatorio.' };
        }

        const postalCode = trimmed.postal_code || '';
        if (postalCode) {
            if (postalCode.startsWith('-')) {
                return { valid: false, message: 'El código postal no puede ser negativo.' };
            }
            if (!/^[0-9]+$/.test(postalCode)) {
                return { valid: false, message: 'El código postal debe contener solo números.' };
            }
        }

        const phone = trimmed.phone || '';
        if (phone && !/^[0-9+()\\-\\s]+$/.test(phone)) {
            return { valid: false, message: 'El teléfono solo puede contener números y caracteres + ( ) -.' };
        }

        const email = trimmed.email || '';
        if (email && !/^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(email)) {
            return { valid: false, message: 'El email no tiene un formato válido.' };
        }

        const website = trimmed.website || '';
        if (website) {
            try {
                new URL(website);
            } catch (_error) {
                return { valid: false, message: 'El sitio web debe ser una URL válida.' };
            }
        }

        return { valid: true, data: trimmed };
    }

    updateLogoPreview(url) {
        const previewContainer = document.getElementById('logo-preview-container');
        const previewImg = document.getElementById('logo-preview-img');

        if (url && previewImg) {
            previewImg.src = url;
            if (previewContainer) previewContainer.style.display = 'block';

            previewImg.onerror = () => {
                if (previewContainer) previewContainer.style.display = 'none';
                NotificationHelper.show('No se pudo cargar la imagen de vista previa', 'warning');
            };
        } else if (previewContainer) {
            previewContainer.style.display = 'none';
        }
    }

    async uploadLogo(file) {
        const progressContainer = document.getElementById('upload-progress');
        const progressBar = document.getElementById('upload-progress-bar');
        const uploadStatus = document.getElementById('upload-status');

        try {
            if (progressContainer) progressContainer.style.display = 'block';
            if (uploadStatus) uploadStatus.textContent = 'Subiendo...';
            if (progressBar) progressBar.style.width = '0%';

            const formData = new FormData();
            formData.append('logo', file);

            const xhr = new XMLHttpRequest();

            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable && progressBar && uploadStatus) {
                    const percentComplete = (e.loaded / e.total) * 100;
                    progressBar.style.width = percentComplete + '%';
                    uploadStatus.textContent = `Subiendo... ${Math.round(percentComplete)}%`;
                }
            });

            xhr.addEventListener('load', () => {
                if (xhr.status === 200) {
                    const result = JSON.parse(xhr.responseText);
                    if (result.success && result.data && result.data.logo_url) {
                        if (uploadStatus) uploadStatus.textContent = '¡Subida exitosa!';
                        NotificationHelper.show('Logo subido correctamente', 'success');

                        const logoUrlInput = document.getElementById('logo_url');
                        if (logoUrlInput) logoUrlInput.value = result.data.logo_url;

                        this.updateLogoPreview(result.data.logo_url);

                        setTimeout(() => {
                            if (progressContainer) progressContainer.style.display = 'none';
                        }, 2000);
                    } else {
                        throw new Error(result.message || 'Error al subir logo');
                    }
                } else {
                    throw new Error('Error al subir archivo');
                }
            });

            xhr.addEventListener('error', () => {
                if (uploadStatus) uploadStatus.textContent = 'Error al subir archivo';
                NotificationHelper.show('Error al subir logo', 'error');
            });

            xhr.open('POST', '/api/business-info/upload-logo');
            xhr.send(formData);

        } catch (error) {
            console.error('Error uploading logo:', error);
            if (uploadStatus) uploadStatus.textContent = 'Error';
            NotificationHelper.show(error.message || 'Error al subir logo', 'error');
        }
    }

    initEventListeners() {
        if (this.form) {
            this.form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(this.form);
                const data = Object.fromEntries(formData.entries());
                await this.save(data);
            });
        }

        this.initLogoHandlers();
    }

    initLogoHandlers() {
        const logoInput = document.getElementById('logo-file-input');
        const logoDropzone = document.getElementById('logo-dropzone');
        const logoServerPath = document.getElementById('logo-server-path');

        if (logoInput) {
            logoInput.addEventListener('change', (e) => {
                if (e.target.files && e.target.files[0]) {
                    this.uploadLogo(e.target.files[0]);
                }
            });
        }

        if (logoDropzone) {
            logoDropzone.addEventListener('dragover', (e) => {
                e.preventDefault();
                logoDropzone.classList.add('dragover');
            });

            logoDropzone.addEventListener('dragleave', () => {
                logoDropzone.classList.remove('dragover');
            });

            logoDropzone.addEventListener('drop', (e) => {
                e.preventDefault();
                logoDropzone.classList.remove('dragover');
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                    this.uploadLogo(e.dataTransfer.files[0]);
                }
            });

            logoDropzone.addEventListener('click', () => {
                if (logoInput) logoInput.click();
            });
        }

        if (logoServerPath) {
            logoServerPath.addEventListener('blur', () => {
                if (logoServerPath.value) {
                    const fullUrl = window.location.origin + logoServerPath.value;
                    this.updateLogoPreview(fullUrl);
                }
            });
        }
    }
}

/**
 * Schedule Manager - Handles schedule management
 */
class ScheduleManager {
    constructor() {
        this.schedule = [];
        this.container = document.getElementById('schedule-list');
    }

    async load() {
        try {
            const response = await fetch('/api/business-schedule');
            const result = await response.json();

            if (result?.data?.schedule) {
                this.schedule = result.data.schedule;
                this.render();
            } else if (result?.error) {
                NotificationHelper.show(result.error || 'Error al cargar horarios', 'error');
            }
        } catch (error) {
            console.error('Error loading schedule:', error);
            NotificationHelper.show('Error al cargar horarios', 'error');
        }
    }

    render() {
        if (!this.container) return;
        this.container.innerHTML = '';

        this.schedule.forEach((day, index) => {
            const item = this.createScheduleItem(day, index);
            this.container.appendChild(item);
        });
    }

    createScheduleItem(day, index) {
        const item = document.createElement('div');
        item.className = `schedule-item ${!day.is_open ? 'closed' : ''}`;
        item.dataset.day = day.day_of_week;

        item.innerHTML = `
            <div class="day-name">${day.day_name}</div>
            <div class="schedule-toggle">
                <div class="toggle-switch ${day.is_open ? 'active' : ''}" data-day="${day.day_of_week}">
                </div>
            </div>
            <div>
                <input type="time" class="time-input open-time"
                    value="${day.open_time || '09:00'}"
                    data-day="${day.day_of_week}"
                    ${!day.is_open ? 'disabled' : ''}>
            </div>
            <div>
                <input type="time" class="time-input close-time"
                    value="${day.close_time || '22:00'}"
                    data-day="${day.day_of_week}"
                    ${!day.is_open ? 'disabled' : ''}>
            </div>
            <div>
                <input type="text" class="time-input notes-input"
                    placeholder="Notas..."
                    value="${day.notes || ''}"
                    data-day="${day.day_of_week}"
                    ${!day.is_open ? 'disabled' : ''}>
            </div>
        `;

        const toggle = item.querySelector('.toggle-switch');
        toggle.addEventListener('click', () => this.toggleDay(day.day_of_week));

        return item;
    }

    toggleDay(day) {
        const toggle = document.querySelector(`.toggle-switch[data-day="${day}"]`);
        const item = toggle?.closest('.schedule-item');
        if (!toggle || !item) return;

        const isOpen = !toggle.classList.contains('active');

        toggle.classList.toggle('active');
        item.classList.toggle('closed');

        const inputs = item.querySelectorAll('input');
        inputs.forEach(input => input.disabled = !isOpen);

        const dayIndex = this.schedule.findIndex(d => d.day_of_week === day);
        if (dayIndex >= 0) {
            this.schedule[dayIndex].is_open = isOpen;
        }
    }

    async save() {
        const scheduleData = this.collectScheduleData();

        try {
            const response = await fetch('/api/business-schedule/bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ schedules: scheduleData })
            });

            const result = await response.json();

            if (!result.error) {
                if (result?.data?.schedules) {
                    this.schedule = result.data.schedules;
                    this.render();
                }
                NotificationHelper.show('Horarios guardados correctamente', 'success');
            } else {
                NotificationHelper.show(result.error || 'Error al guardar horarios', 'error');
            }
        } catch (error) {
            console.error('Error saving schedule:', error);
            NotificationHelper.show('Error al guardar horarios', 'error');
        }
    }

    async applyMondayToAll() {
        if (!this.schedule.length) {
            await this.load();
        }

        const monday = this.schedule.find(day => day.day_of_week === 0) || this.schedule[0];
        if (!monday) {
            NotificationHelper.show('No se encontró el horario del lunes', 'error');
            return;
        }

        const updated = this.schedule.map((day) => ({
            ...day,
            is_open: monday.is_open,
            open_time: monday.open_time,
            close_time: monday.close_time,
            notes: monday.notes || ''
        }));

        this.schedule = updated;
        this.render();

        try {
            const response = await fetch('/api/business-schedule/bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    schedules: updated.map((day) => ({
                        day_of_week: day.day_of_week,
                        is_open: day.is_open,
                        open_time: day.open_time,
                        close_time: day.close_time,
                        notes: day.notes || ''
                    }))
                })
            });

            const result = await response.json();
            if (!result.error) {
                if (result?.data?.schedules) {
                    this.schedule = result.data.schedules;
                    this.render();
                }
                NotificationHelper.show('Horario del lunes aplicado a todos', 'success');
            } else {
                NotificationHelper.show(result.error || 'Error al aplicar horarios', 'error');
                await this.load();
            }
        } catch (error) {
            console.error('Error applying schedule to all:', error);
            NotificationHelper.show('Error al aplicar horarios', 'error');
            await this.load();
        }
    }

    collectScheduleData() {
        const items = document.querySelectorAll('.schedule-item');
        return Array.from(items).map(item => {
            const day = item.dataset.day;
            const toggle = item.querySelector('.toggle-switch');
            const openInput = item.querySelector('.open-time');
            const closeInput = item.querySelector('.close-time');
            const notesInput = item.querySelector('.notes-input');

            return {
                day_of_week: day,
                is_open: toggle?.classList.contains('active') || false,
                open_time: openInput?.value || '09:00',
                close_time: closeInput?.value || '22:00',
                notes: notesInput?.value || ''
            };
        });
    }

    initEventListeners() {
        const saveBtn = document.getElementById('save-schedule-btn');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.save());
        }
    }
}

/**
 * Settings Manager - Handles settings/parameters management
 */
class SettingsManager {
    constructor() {
        this.settings = [];
        this.currentCategory = 'all';
        this.currentTypeFilter = 'all';
        this.currentSortField = null;
        this.currentSortDirection = 'asc';
        this.tableBody = document.getElementById('parameters-table-body');
    }

    async load() {
        try {
            const response = await fetch('/api/settings');
            const result = await response.json();

            if (result?.error) {
                NotificationHelper.show(result.error || 'Error al cargar configuración', 'error');
                return;
            }

            const payload = result?.data || result || {};
            let settings = [];

            if (Array.isArray(payload)) {
                settings = payload;
            } else if (payload.settings && Array.isArray(payload.settings)) {
                settings = payload.settings;
            }

            if (!settings.length) {
                const initResponse = await fetch('/api/settings/initialize', { method: 'POST' });
                const initResult = await initResponse.json().catch(() => ({}));
                if (initResult?.error) {
                    NotificationHelper.show(initResult.error || 'Error al inicializar configuración', 'error');
                } else {
                    const reloadResponse = await fetch('/api/settings');
                    const reloadResult = await reloadResponse.json().catch(() => ({}));
                    const reloadPayload = reloadResult?.data || reloadResult || {};
                    settings = reloadPayload.settings || settings;
                }
            }

            this.settings = settings;
            this.render();
        } catch (error) {
            console.error('Error loading settings:', error);
            NotificationHelper.show('Error al cargar configuración', 'error');
        }
    }

    render() {
        if (!this.tableBody) return;

        let filtered = this.filterSettings();
        let sorted = this.sortSettings(filtered);

        this.tableBody.innerHTML = sorted.map(setting => this.createSettingRow(setting)).join('');
    }

    createSettingRow(setting) {
        const valueDisplay = this.formatValue(setting);
        const editControl = this.createEditControl(setting);

        return `
            <tr data-key="${setting.key}" data-category="${setting.category}">
                <td><span class="param-key">${setting.key}</span></td>
                <td><div class="param-description">${setting.description || 'Sin descripción'}</div></td>
                <td><span class="param-category">${setting.category}</span></td>
                <td><span class="param-type">${setting.value_type}</span></td>
                <td class="param-value-cell">
                    <div class="param-value-display ${setting.value_type === 'bool' ? (setting.value ? 'bool-true' : 'bool-false') : ''}">
                        ${valueDisplay}
                    </div>
                </td>
                <td><div class="param-actions">${editControl}</div></td>
            </tr>
        `;
    }

    formatValue(setting) {
        if (setting.value_type === 'bool') {
            return setting.value ? '✓ true' : '✗ false';
        } else if (setting.value_type === 'json') {
            return JSON.stringify(setting.value);
        }
        return String(setting.value);
    }

    createEditControl(setting) {
        if (setting.value_type === 'bool') {
            return `
                <div class="toggle-switch ${setting.value ? 'active' : ''}"
                     data-key="${setting.key}"
                     onclick="window.businessConfig.settings.toggle('${setting.key}', ${!setting.value})"
                     style="width: 44px; height: 24px; display: inline-block;">
                </div>
            `;
        }
        return `
            <button type="button" class="btn-edit-param"
                onclick="window.businessConfig.settings.edit('${setting.key}', '${setting.value_type}')">
                Editar
            </button>
        `;
    }

    filterSettings() {
        const searchTerm = document.getElementById('settings-search')?.value.toLowerCase() || '';

        return this.settings.filter(setting => {
            const matchesSearch = !searchTerm ||
                setting.key.toLowerCase().includes(searchTerm) ||
                (setting.description && setting.description.toLowerCase().includes(searchTerm)) ||
                String(setting.value).toLowerCase().includes(searchTerm);

            const matchesCategory = this.currentCategory === 'all' || setting.category === this.currentCategory;
            const matchesType = this.currentTypeFilter === 'all' || setting.value_type === this.currentTypeFilter;

            return matchesSearch && matchesCategory && matchesType;
        });
    }

    sortSettings(settings) {
        if (!this.currentSortField) return settings;

        return [...settings].sort((a, b) => {
            const fieldA = a[this.currentSortField];
            const fieldB = b[this.currentSortField];

            let comparison = 0;
            if (fieldA < fieldB) comparison = -1;
            if (fieldA > fieldB) comparison = 1;

            return this.currentSortDirection === 'asc' ? comparison : -comparison;
        });
    }

    edit(key, valueType) {
        const setting = this.settings.find(s => s.key === key);
        if (!setting) return;

        // Special handling for waiter_notification_sound
        if (key === 'waiter_notification_sound') {
            this.editNotificationSound(setting);
            return;
        }

        let newValue;
        if (valueType === 'json') {
            newValue = prompt('Ingrese el nuevo valor (JSON):', JSON.stringify(setting.value, null, 2));
        } else {
            newValue = prompt('Ingrese el nuevo valor:', setting.value);
        }

        if (newValue !== null) {
            this.update(key, newValue, valueType);
        }
    }

    editNotificationSound(setting) {
        const soundOptions = [
            { value: 'bell', label: '🔔 Campanita (por defecto)' },
            { value: 'chime', label: '🎵 Carillón' },
            { value: 'beep', label: '📢 Bip' },
            { value: 'ding', label: '🔔 Timbre' },
            { value: 'pop', label: '💫 Pop suave' }
        ];

        const currentIndex = soundOptions.findIndex(opt => opt.value === setting.value);
        const optionsHtml = soundOptions.map((opt, index) =>
            `<option value="${opt.value}" ${index === currentIndex ? 'selected' : ''}>${opt.label}</option>`
        ).join('');

        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
        `;

        const content = document.createElement('div');
        content.style.cssText = `
            background: white;
            padding: 2rem;
            border-radius: 12px;
            max-width: 400px;
            width: 90%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        `;

        content.innerHTML = `
            <h3 style="margin: 0 0 1rem 0; font-size: 1.25rem; color: #1e293b;">Seleccionar Sonido de Notificación</h3>
            <p style="margin: 0 0 1.5rem 0; color: #64748b; font-size: 0.9rem;">
                Elige el tipo de sonido que se reproducirá cuando haya una nueva orden en el panel de mesero.
            </p>
            <select id="sound-selector" style="
                width: 100%;
                padding: 0.75rem;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                font-size: 1rem;
                margin-bottom: 1.5rem;
                cursor: pointer;
            ">
                ${optionsHtml}
            </select>
            <div style="display: flex; gap: 0.75rem; justify-content: flex-end;">
                <button type="button" id="cancel-sound" style="
                    padding: 0.75rem 1.5rem;
                    border: 2px solid #e2e8f0;
                    background: white;
                    border-radius: 8px;
                    cursor: pointer;
                    font-size: 0.95rem;
                ">Cancelar</button>
                <button type="button" id="save-sound" style="
                    padding: 0.75rem 1.5rem;
                    border: none;
                    background: #1e3a5f;
                    color: white;
                    border-radius: 8px;
                    cursor: pointer;
                    font-size: 0.95rem;
                ">Guardar</button>
            </div>
        `;

        modal.appendChild(content);
        document.body.appendChild(modal);

        const closeModal = () => {
            document.body.removeChild(modal);
        };

        const saveSound = () => {
            const selector = content.querySelector('#sound-selector');
            const newValue = selector.value;
            if (newValue) {
                this.update(setting.key, newValue, 'string');
                closeModal();
            }
        };

        content.querySelector('#cancel-sound').addEventListener('click', closeModal);
        content.querySelector('#save-sound').addEventListener('click', saveSound);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });
    }

    async toggle(key, value) {
        await this.update(key, value, 'bool');
    }

    async update(key, value, valueType) {
        try {
            let parsedValue = value;
            if (valueType === 'int') parsedValue = parseInt(value);
            else if (valueType === 'float') parsedValue = parseFloat(value);
            else if (valueType === 'json') {
                try {
                    parsedValue = JSON.parse(value);
                } catch (e) {
                    NotificationHelper.show('JSON inválido', 'error');
                    return;
                }
            }

            const response = await fetch(`/api/settings/${key}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value: parsedValue })
            });

            const result = await response.json();

            if (result.success) {
                const settingIndex = this.settings.findIndex(s => s.key === key);
                if (settingIndex >= 0) {
                    this.settings[settingIndex].value = parsedValue;
                }
                this.render();
                NotificationHelper.show('Configuración actualizada', 'success');
            } else {
                NotificationHelper.show(result.message || 'Error al actualizar', 'error');
            }
        } catch (error) {
            console.error('Error updating setting:', error);
            NotificationHelper.show('Error al actualizar configuración', 'error');
        }
    }

    initEventListeners() {
        const searchInput = document.getElementById('settings-search');
        if (searchInput) {
            searchInput.addEventListener('input', () => this.render());
        }

        const categoryButtons = document.querySelectorAll('.category-btn');
        categoryButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                this.currentCategory = btn.dataset.category;
                categoryButtons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.render();
            });
        });

        const typeFilter = document.getElementById('type-filter');
        if (typeFilter) {
            typeFilter.addEventListener('change', (e) => {
                this.currentTypeFilter = e.target.value;
                this.render();
            });
        }

        const filtersToggle = document.getElementById('advanced-filters-toggle');
        const filtersPanel = document.getElementById('advanced-filters-panel');
        if (filtersToggle && filtersPanel) {
            filtersToggle.addEventListener('click', () => {
                const isVisible = filtersPanel.style.display === 'block';
                filtersPanel.style.display = isVisible ? 'none' : 'block';
                filtersToggle.classList.toggle('active');
            });
        }

        const sortableHeaders = document.querySelectorAll('.parameters-table th.sortable');
        sortableHeaders.forEach(header => {
            header.addEventListener('click', () => {
                const sortField = header.dataset.sort;

                if (this.currentSortField === sortField) {
                    this.currentSortDirection = this.currentSortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    this.currentSortField = sortField;
                    this.currentSortDirection = 'asc';
                }

                sortableHeaders.forEach(h => {
                    h.classList.remove('sorted-asc', 'sorted-desc');
                });
                header.classList.add(`sorted-${this.currentSortDirection}`);

                this.render();
            });
        });
    }
}

/**
 * Notification Helper - Centralized notifications
 */
class NotificationHelper {
    static show(message, type = 'info') {
        if (typeof window.showNotification === 'function') {
            window.showNotification(message, type);
        } else {
            alert(message);
        }
    }
}

/**
 * Feedback Configuration Manager - Handles feedback settings
 */
class FeedbackConfigManager {
    constructor() {
        this.settings = {
            'feedback_prompt_enabled': 'true',
            'feedback_prompt_timeout_seconds': '10',
            'feedback_email_enabled': 'true',
            'feedback_email_token_ttl_hours': '24',
            'feedback_email_allow_anonymous_if_email_present': 'true',
            'feedback_email_throttle_per_order': 'true',
            'feedback_email_subject': 'Cuéntanos tu experiencia en {{restaurant_name}}',
            'feedback_email_body_template': ''
        };
    }

    async load() {
        try {
            const response = await fetch('/api/settings/feedback');
            if (response.ok) {
                const result = await response.json();
                if (result.data) {
                    this.settings = { ...this.settings, ...result.data };
                }
            }
            this.populateForm();
        } catch (error) {
            console.error('Error loading feedback settings:', error);
            this.populateForm();
        }
    }

    populateForm() {
        Object.keys(this.settings).forEach(key => {
            const input = document.getElementById(key);
            if (input) {
                input.value = this.settings[key] || '';
            }
        });
    }

    collectFormData() {
        const fields = [
            'feedback_prompt_enabled',
            'feedback_prompt_timeout_seconds',
            'feedback_email_enabled',
            'feedback_email_token_ttl_hours',
            'feedback_email_allow_anonymous_if_email_present',
            'feedback_email_throttle_per_order',
            'feedback_email_subject',
            'feedback_email_body_template'
        ];

        const data = {};
        fields.forEach(key => {
            const input = document.getElementById(key);
            if (input) {
                data[key] = input.value;
            }
        });

        return data;
    }

    async save() {
        const data = this.collectFormData();

        try {
            const response = await fetch('/api/settings/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (result.success) {
                NotificationHelper.show('Configuración de feedback guardada correctamente', 'success');
            } else {
                NotificationHelper.show(result.message || 'Error al guardar', 'error');
            }
        } catch (error) {
            console.error('Error saving feedback settings:', error);
            NotificationHelper.show('Error al guardar configuración', 'error');
        }
    }
}

/**
 * Main Business Configuration Application
 */
class BusinessConfigApp {
    constructor() {
        this.tabs = new TabManager();
        this.businessInfo = new BusinessInfoManager();
        this.schedule = new ScheduleManager();
        this.settings = new SettingsManager();
        this.feedback = new FeedbackConfigManager();
    }

    async init() {
        this.tabs.init();

        await Promise.all([
            this.businessInfo.load(),
            this.schedule.load(),
            this.settings.load(),
            this.feedback.load()
        ]);

        this.businessInfo.initEventListeners();
        this.schedule.initEventListeners();
        this.settings.initEventListeners();
    }
}



// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.businessConfig = new BusinessConfigApp();
    window.businessConfig.init();
});

// Legacy compatibility - expose global functions
window.editParameter = function (key, valueType) {
    window.businessConfig?.settings?.edit(key, valueType);
};

window.toggleSetting = function (key, value) {
    window.businessConfig?.settings?.toggle(key, value);
};

window.applyToAll = function () {
    window.businessConfig?.schedule?.applyMondayToAll();
};
