/**
 * Reports Module - Sistema completo de reportes y análisis
 *
 * Incluye:
 * - Filtros rápidos con auto-search
 * - Validación de entrada y seguridad
 * - Timeout con AbortController
 * - Estados de carga/vacío/error
 * - Gráficos interactivos con Chart.js
 */

class ReportsManager {
    constructor() {
        // DOM Elements
        this.startDateInput = document.getElementById('report-start-date');
        this.endDateInput = document.getElementById('report-end-date');
        this.groupingSelect = document.getElementById('report-grouping');
        this.searchBtn = document.getElementById('refresh-reports-btn');
        this.quickFiltersBtn = document.getElementById('quick-filters-btn');
        this.quickFiltersContainer = document.getElementById('quick-filters');
        this.feedbackEl = document.getElementById('reports-feedback');

        // State
        this.currentPeriod = null;
        this.lastSubmittedQuery = null;
        this.abortController = null;
        this.charts = {};
        this.isLoading = false;

        // Constants
        this.API_TIMEOUT = 5000; // 5 seconds
        this.MAX_INPUT_LENGTH = 100;

        this.init();
    }

    init() {
        if (!this.searchBtn) {
            console.warn('[Reports] Reports section not found on this page');
            return;
        }

        // Set default dates (last 7 days)
        this.setDefaultDates();

        // Event listeners
        this.searchBtn.addEventListener('click', () => this.handleSearch());

        if (this.quickFiltersBtn) {
            this.quickFiltersBtn.addEventListener('click', () => this.toggleQuickFilters());
        }

        // Quick filter buttons
        const quickFilterBtns = document.querySelectorAll('.quick-filter-btn');
        quickFilterBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const button = e.currentTarget;
                const period = button?.dataset?.period;
                this.handleQuickFilter(period, button);
            });
        });

        // Enter key support on date inputs
        [this.startDateInput, this.endDateInput].forEach(input => {
            if (input) {
                input.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') {
                        this.handleSearch();
                    }
                });
            }
        });

        // Load initial data
        this.loadAllReports();

        console.log('[Reports] Reports manager initialized');
    }

    /**
     * Set default date range (last 7 days)
     */
    setDefaultDates() {
        const today = new Date();
        const lastWeek = new Date();
        lastWeek.setDate(today.getDate() - 7);

        if (this.endDateInput) {
            this.endDateInput.valueAsDate = today;
        }
        if (this.startDateInput) {
            this.startDateInput.valueAsDate = lastWeek;
        }
    }

    /**
     * Toggle quick filters visibility
     */
    toggleQuickFilters() {
        if (!this.quickFiltersContainer) return;

        const isVisible = this.quickFiltersContainer.style.display !== 'none';
        this.quickFiltersContainer.style.display = isVisible ? 'none' : 'flex';
    }

    /**
     * Handle quick filter selection
     * Auto-triggers search and updates date inputs
     */
    handleQuickFilter(period, button) {
        const dates = this.calculateDateRange(period);

        // Update visual state
        document.querySelectorAll('.quick-filter-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        if (button) {
            button.classList.add('active');
        }

        // Update date inputs
        if (this.startDateInput) {
            this.startDateInput.valueAsDate = dates.start;
        }
        if (this.endDateInput) {
            this.endDateInput.valueAsDate = dates.end;
        }

        // Store current period
        this.currentPeriod = period;

        // Auto-trigger search
        this.loadAllReports();

        // Show period indicator
        this.showPeriodIndicator(period, dates);
    }

    /**
     * Calculate date range based on period
     */
    calculateDateRange(period) {
        const today = new Date();
        let start = new Date();

        switch (period) {
            case 'today':
                start = new Date(today);
                break;
            case 'week':
                // Start of current week (Monday)
                const dayOfWeek = today.getDay();
                const diff = dayOfWeek === 0 ? 6 : dayOfWeek - 1; // Adjust for Monday start
                start = new Date(today);
                start.setDate(today.getDate() - diff);
                break;
            case 'month':
                start = new Date(today.getFullYear(), today.getMonth(), 1);
                break;
            default:
                start = new Date(today);
                start.setDate(today.getDate() - 7);
        }

        return { start, end: today };
    }

    /**
     * Show period indicator badge
     */
    showPeriodIndicator(period, dates) {
        const options = { year: 'numeric', month: 'long', day: 'numeric' };
        const startStr = dates.start.toLocaleDateString('es-ES', options);
        const endStr = dates.end.toLocaleDateString('es-ES', options);

        let periodLabel = '';
        switch (period) {
            case 'today':
                periodLabel = `Hoy (${endStr})`;
                break;
            case 'week':
                periodLabel = `Esta semana (${startStr} - ${endStr})`;
                break;
            case 'month':
                periodLabel = `Este mes (${dates.start.toLocaleDateString('es-ES', { month: 'long', year: 'numeric' })})`;
                break;
        }

        // Remove existing indicator
        const existingIndicator = document.querySelector('.period-indicator');
        if (existingIndicator) {
            existingIndicator.remove();
        }

        // Create new indicator
        const indicator = document.createElement('div');
        indicator.className = 'period-indicator';
        indicator.style.cssText = 'background: #e3f2fd; padding: 12px; border-radius: 8px; margin: 16px 0; color: #1565c0;';
        indicator.innerHTML = `📅 <strong>Período activo:</strong> ${periodLabel}`;

        // Insert after filters
        const filtersContainer = document.querySelector('.reports-filters');
        if (filtersContainer) {
            filtersContainer.after(indicator);
        }
    }

    /**
     * Handle search button click
     */
    handleSearch() {
        // Validate inputs
        if (!this.validateInputs()) {
            return;
        }

        this.loadAllReports();
    }

    /**
     * Validate date inputs
     */
    validateInputs() {
        if (!this.startDateInput?.value || !this.endDateInput?.value) {
            this.showFeedback('Por favor selecciona un rango de fechas válido', 'error');
            return false;
        }

        const start = new Date(this.startDateInput.value);
        const end = new Date(this.endDateInput.value);

        if (start > end) {
            this.showFeedback('La fecha de inicio debe ser anterior a la fecha de fin', 'error');
            return false;
        }

        // Validate date range (max 1 year)
        const daysDiff = (end - start) / (1000 * 60 * 60 * 24);
        if (daysDiff > 365) {
            this.showFeedback('El rango de fechas no puede exceder 1 año', 'error');
            return false;
        }

        return true;
    }

    /**
     * Sanitize input to prevent XSS and injection attacks
     */
    sanitizeInput(input) {
        if (!input) return '';

        // Allow only letters, numbers, spaces, @, ., -, /
        const sanitized = input.replace(/[^a-zA-Z0-9\s@.\-\/]/g, '');

        // Limit length
        return sanitized.substring(0, this.MAX_INPUT_LENGTH);
    }

    /**
     * Load all reports with current filters
     */
    async loadAllReports() {
        if (this.isLoading) {
            console.log('[Reports] Already loading, ignoring request');
            return;
        }

        this.isLoading = true;
        this.setLoadingState(true);

        const startDate = this.startDateInput?.value;
        const endDate = this.endDateInput?.value;
        const groupBy = this.groupingSelect?.value || 'day';

        try {
            // Load all reports in parallel
            await Promise.all([
                this.loadSalesReport(startDate, endDate, groupBy),
                this.loadTopProducts(startDate, endDate),
                this.loadPeakHours(startDate, endDate),
                this.loadWaiterTips(startDate, endDate)
            ]);

            this.showFeedback('Reportes actualizados correctamente', 'success');
        } catch (error) {
            console.error('[Reports] Error loading reports:', error);

            if (error.name === 'AbortError') {
                this.showFeedback('La solicitud tardó demasiado. Por favor intenta de nuevo.', 'error');
            } else {
                this.showFeedback('Error al cargar reportes. Por favor intenta de nuevo.', 'error');
            }
        } finally {
            this.isLoading = false;
            this.setLoadingState(false);
        }
    }

    /**
     * Fetch with timeout using AbortController
     */
    async fetchWithTimeout(url, options = {}) {
        // Abort previous request if exists
        if (this.abortController) {
            this.abortController.abort();
        }

        // Create new AbortController
        this.abortController = new AbortController();
        const { signal } = this.abortController;

        // Set timeout
        const timeoutId = setTimeout(() => {
            this.abortController.abort();
        }, this.API_TIMEOUT);

        try {
            const response = await fetch(url, {
                ...options,
                signal,
                credentials: 'include'
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            clearTimeout(timeoutId);
            throw error;
        }
    }

    /**
     * Load sales report
     */
    async loadSalesReport(startDate, endDate, groupBy) {
        try {
            const url = `/api/reports/sales?start_date=${startDate}&end_date=${endDate}&group_by=${groupBy}`;
            const result = await this.fetchWithTimeout(url);

            if (!result?.error && result?.data) {
                this.renderSalesReport(result.data);
            } else {
                this.renderEmptySales();
            }
        } catch (error) {
            console.error('[Reports] Error loading sales:', error);
            this.renderEmptySales();
            throw error;
        }
    }

    /**
     * Render sales report
     */
    renderSalesReport(data) {
        const { summary, data: salesData } = data;

        // Update summary metrics
        document.getElementById('total-orders').textContent = summary?.total_orders || 0;
        document.getElementById('total-revenue').textContent = `$${(summary?.total_revenue || 0).toFixed(2)}`;
        document.getElementById('total-tips-summary').textContent = `$${(summary?.total_tips || 0).toFixed(2)}`;
        document.getElementById('avg-order-value').textContent = `$${(summary?.avg_order_value || 0).toFixed(2)}`;

        // Render chart
        this.renderSalesChart(salesData);
    }

    /**
     * Render empty state for sales
     */
    renderEmptySales() {
        document.getElementById('total-orders').textContent = '0';
        document.getElementById('total-revenue').textContent = '$0.00';
        document.getElementById('total-tips-summary').textContent = '$0.00';
        document.getElementById('avg-order-value').textContent = '$0.00';

        // Destroy chart if exists
        if (this.charts.sales) {
            this.charts.sales.destroy();
            this.charts.sales = null;
        }

        this.showNoDataMessage('sales-chart', 'No hay datos de ventas para el período seleccionado');
    }

    /**
     * Render sales chart
     */
    renderSalesChart(data) {
        const canvas = document.getElementById('sales-chart');
        if (!canvas) return;

        this.clearNoDataMessage(canvas);
        const ctx = canvas.getContext('2d');

        // Destroy existing chart
        if (this.charts.sales) {
            this.charts.sales.destroy();
        }

        if (!data || data.length === 0) {
            this.showNoDataMessage('sales-chart', 'No hay datos de ventas para el período seleccionado');
            return;
        }

        // Prepare data
        const labels = data.map(d => d.date);
        const sales = data.map(d => d.total_sales);
        const tips = data.map(d => d.total_tips);

        this.charts.sales = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Ventas',
                        data: sales,
                        borderColor: '#2196F3',
                        backgroundColor: 'rgba(33, 150, 243, 0.1)',
                        tension: 0.4,
                        fill: true
                    },
                    {
                        label: 'Propinas',
                        data: tips,
                        borderColor: '#4CAF50',
                        backgroundColor: 'rgba(76, 175, 80, 0.1)',
                        tension: 0.4,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                label += '$' + context.parsed.y.toFixed(2);
                                return label;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return '$' + value.toFixed(0);
                            }
                        }
                    }
                }
            }
        });
    }

    /**
     * Load top products
     */
    async loadTopProducts(startDate, endDate) {
        try {
            const url = `/api/reports/top-products?start_date=${startDate}&end_date=${endDate}&limit=10`;
            const result = await this.fetchWithTimeout(url);

            if (!result?.error && result?.data) {
                this.renderTopProducts(result.data.data);
            } else {
                this.renderEmptyTopProducts();
            }
        } catch (error) {
            console.error('[Reports] Error loading top products:', error);
            this.renderEmptyTopProducts();
            throw error;
        }
    }

    /**
     * Render top products table and chart
     */
    renderTopProducts(data) {
        // Render table
        const tbody = document.querySelector('#top-products-table tbody');
        if (tbody) {
            if (!data || data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 20px; color: #999;">No hay datos disponibles para el período seleccionado</td></tr>';
            } else {
                tbody.innerHTML = data.map((product, index) => `
                    <tr>
                        <td>${index + 1}</td>
                        <td>${this.escapeHtml(product.name)}</td>
                        <td>${product.total_quantity}</td>
                        <td>${product.order_count}</td>
                        <td>$${product.total_revenue.toFixed(2)}</td>
                    </tr>
                `).join('');
            }
        }

        // Render chart
        this.renderTopProductsChart(data);
    }

    /**
     * Render empty state for top products
     */
    renderEmptyTopProducts() {
        const tbody = document.querySelector('#top-products-table tbody');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 20px; color: #999;">No hay datos disponibles para el período seleccionado</td></tr>';
        }

        if (this.charts.topProducts) {
            this.charts.topProducts.destroy();
            this.charts.topProducts = null;
        }

        this.showNoDataMessage('top-products-chart', 'No hay datos de productos para el período seleccionado');
    }

    /**
     * Render top products chart
     */
    renderTopProductsChart(data) {
        const canvas = document.getElementById('top-products-chart');
        if (!canvas) return;

        this.clearNoDataMessage(canvas);
        const ctx = canvas.getContext('2d');

        // Destroy existing chart
        if (this.charts.topProducts) {
            this.charts.topProducts.destroy();
        }

        if (!data || data.length === 0) {
            this.showNoDataMessage('top-products-chart', 'No hay datos de productos para el período seleccionado');
            return;
        }

        // Take top 5 for chart
        const topFive = data.slice(0, 5);

        this.charts.topProducts = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: topFive.map(p => p.name),
                datasets: [{
                    label: 'Cantidad Vendida',
                    data: topFive.map(p => p.total_quantity),
                    backgroundColor: [
                        'rgba(255, 99, 132, 0.8)',
                        'rgba(54, 162, 235, 0.8)',
                        'rgba(255, 206, 86, 0.8)',
                        'rgba(75, 192, 192, 0.8)',
                        'rgba(153, 102, 255, 0.8)'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    /**
     * Load peak hours report
     */
    async loadPeakHours(startDate, endDate) {
        try {
            const url = `/api/reports/peak-hours?start_date=${startDate}&end_date=${endDate}`;
            const result = await this.fetchWithTimeout(url);

            if (!result?.error && result?.data) {
                this.renderPeakHours(result.data);
            } else {
                this.renderEmptyPeakHours();
            }
        } catch (error) {
            console.error('[Reports] Error loading peak hours:', error);
            this.renderEmptyPeakHours();
            throw error;
        }
    }

    /**
     * Render peak hours
     */
    renderPeakHours(data) {
        const { data: hoursData, peak_hour } = data;

        // Update peak hour display
        const peakHourEl = document.getElementById('peak-hour-display');
        if (peakHourEl) {
            if (peak_hour) {
                peakHourEl.textContent = `${peak_hour.hour_label} (${peak_hour.order_count} órdenes)`;
            } else {
                peakHourEl.textContent = 'Sin datos';
            }
        }

        // Render chart
        this.renderPeakHoursChart(hoursData);
    }

    /**
     * Render empty state for peak hours
     */
    renderEmptyPeakHours() {
        const peakHourEl = document.getElementById('peak-hour-display');
        if (peakHourEl) {
            peakHourEl.textContent = 'Sin datos';
        }

        if (this.charts.peakHours) {
            this.charts.peakHours.destroy();
            this.charts.peakHours = null;
        }

        this.showNoDataMessage('peak-hours-chart', 'No hay datos de horarios para el período seleccionado');
    }

    /**
     * Render peak hours chart
     */
    renderPeakHoursChart(data) {
        const canvas = document.getElementById('peak-hours-chart');
        if (!canvas) return;

        this.clearNoDataMessage(canvas);
        const ctx = canvas.getContext('2d');

        // Destroy existing chart
        if (this.charts.peakHours) {
            this.charts.peakHours.destroy();
        }

        if (!data || data.length === 0) {
            this.showNoDataMessage('peak-hours-chart', 'No hay datos de horarios para el período seleccionado');
            return;
        }

        this.charts.peakHours = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(d => d.hour_label),
                datasets: [{
                    label: 'Órdenes por Hora',
                    data: data.map(d => d.order_count),
                    backgroundColor: 'rgba(33, 150, 243, 0.8)',
                    borderColor: 'rgba(33, 150, 243, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0
                        }
                    }
                }
            }
        });
    }

    /**
     * Load waiter tips report
     */
    async loadWaiterTips(startDate, endDate) {
        try {
            const url = `/api/reports/waiter-tips?start_date=${startDate}&end_date=${endDate}`;
            const result = await this.fetchWithTimeout(url);

            if (!result?.error && result?.data) {
                this.renderWaiterTips(result.data);
            } else {
                this.renderEmptyWaiterTips();
            }
        } catch (error) {
            console.error('[Reports] Error loading waiter tips:', error);
            this.renderEmptyWaiterTips();
            throw error;
        }
    }

    /**
     * Render waiter tips
     */
    renderWaiterTips(data) {
        const { data: tipsData, summary } = data;

        // Update summary
        document.getElementById('total-tips-waiter').textContent = `$${(summary?.total_tips || 0).toFixed(2)}`;
        document.getElementById('waiter-count').textContent = summary?.waiter_count || 0;

        // Render table
        const tbody = document.querySelector('#waiter-tips-table tbody');
        if (tbody) {
            if (!tipsData || tipsData.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 20px; color: #999;">No hay datos disponibles para el período seleccionado</td></tr>';
            } else {
                tbody.innerHTML = tipsData.map(waiter => `
                    <tr>
                        <td>${this.escapeHtml(waiter.waiter_name)}</td>
                        <td>${waiter.order_count}</td>
                        <td>$${waiter.total_tips.toFixed(2)}</td>
                        <td>$${waiter.avg_tip.toFixed(2)}</td>
                        <td>${waiter.tip_percentage.toFixed(1)}%</td>
                    </tr>
                `).join('');
            }
        }
    }

    /**
     * Render empty state for waiter tips
     */
    renderEmptyWaiterTips() {
        document.getElementById('total-tips-waiter').textContent = '$0.00';
        document.getElementById('waiter-count').textContent = '0';

        const tbody = document.querySelector('#waiter-tips-table tbody');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 20px; color: #999;">No hay datos disponibles para el período seleccionado</td></tr>';
        }
    }

    /**
     * Show "no data" message in chart container
     */
    showNoDataMessage(canvasId, message) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        const container = canvas.parentElement;

        // Remove existing message
        const existing = container.querySelector('.no-data-message');
        if (existing) {
            existing.remove();
        }

        // Hide canvas
        canvas.style.display = 'none';

        // Create message
        const messageEl = document.createElement('div');
        messageEl.className = 'no-data-message';
        messageEl.style.cssText = 'text-align: center; padding: 40px; color: #999; font-size: 14px;';
        messageEl.innerHTML = `
            <div style="font-size: 48px; margin-bottom: 16px;">📊</div>
            <p>${message}</p>
        `;

        container.appendChild(messageEl);
    }

    /**
     * Clear "no data" message and reveal canvas
     */
    clearNoDataMessage(canvas) {
        const container = canvas.parentElement;
        if (!container) return;
        const existing = container.querySelector('.no-data-message');
        if (existing) {
            existing.remove();
        }
        canvas.style.display = '';
    }

    /**
     * Set loading state
     */
    setLoadingState(isLoading) {
        if (this.searchBtn) {
            this.searchBtn.disabled = isLoading;
            this.searchBtn.textContent = isLoading ? '⏳ Cargando...' : '🔍 Buscar';
        }

        // Show skeleton loaders
        if (isLoading) {
            this.showSkeletonLoaders();
        } else {
            this.hideSkeletonLoaders();
        }
    }

    /**
     * Show skeleton loaders (simplified version)
     */
    showSkeletonLoaders() {
        // Could add skeleton loading animations here
        console.log('[Reports] Loading...');
    }

    /**
     * Hide skeleton loaders
     */
    hideSkeletonLoaders() {
        console.log('[Reports] Loading complete');
    }

    /**
     * Show feedback message
     */
    showFeedback(message, type = 'info') {
        if (!this.feedbackEl) return;

        this.feedbackEl.className = `feedback feedback--${type}`;
        this.feedbackEl.textContent = message;
        this.feedbackEl.style.display = 'block';

        setTimeout(() => {
            this.feedbackEl.style.display = 'none';
        }, 5000);
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
    window.ReportsManager = new ReportsManager();
});
