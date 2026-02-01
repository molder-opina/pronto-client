type ChartInstance = {
    destroy: () => void;
} | null;

declare const Chart: any;

interface SalesSummary {
    total_orders: number;
    total_revenue: number;
    total_tips: number;
    avg_order_value: number;
}

interface SalesDataPoint {
    date: string;
    total_sales: number;
    total_tips: number;
}

interface TopProduct {
    name: string;
    total_quantity: number;
    order_count: number;
    total_revenue: number;
}

interface PeakHourData {
    hour_label: string;
    order_count: number;
}

interface PeakHourResponse {
    data: PeakHourData[];
    peak_hour?: PeakHourData;
}

interface WaiterTip {
    waiter_name: string;
    order_count: number;
    total_tips: number;
    avg_tip: number;
    tip_percentage: number;
}

interface WaiterTipsSummary {
    total_tips: number;
    waiter_count: number;
}

export function initReportsManager(): void {
    document.addEventListener('DOMContentLoaded', () => {
        const root = document.querySelector<HTMLElement>('[data-reports-root]');
        if (!root) return;
        const manager = new ReportsManager(root);
        manager.initialize();
    });
}

class ReportsManager {
    private root: HTMLElement;
    private salesChart: ChartInstance = null;
    private topProductsChart: ChartInstance = null;
    private peakHoursChart: ChartInstance = null;
    private startDateInput: HTMLInputElement | null;
    private endDateInput: HTMLInputElement | null;
    private groupingSelect: HTMLSelectElement | null;

    constructor(root: HTMLElement) {
        this.root = root;
        this.startDateInput = root.querySelector('#report-start-date');
        this.endDateInput = root.querySelector('#report-end-date');
        this.groupingSelect = root.querySelector('#report-grouping');
    }

    initialize(): void {
        this.initializeDateInputs();
        this.attachQuickFilters();
        this.attachRefreshButton();
        this.loadAllReports().catch((error) => {
            console.error('[REPORTS] initialization error', error);
            this.showFeedback('No se pudieron cargar los reportes iniciales', 'error');
        });
    }

    private attachRefreshButton(): void {
        const refreshBtn = this.root.querySelector<HTMLButtonElement>('#refresh-reports-btn');
        refreshBtn?.addEventListener('click', () => {
            this.loadAllReports().catch((error) => {
                console.error('[REPORTS] refresh error', error);
                this.showFeedback('Error al actualizar los reportes', 'error');
            });
        });
    }

    private attachQuickFilters(): void {
        const quickFiltersBtn = this.root.querySelector<HTMLButtonElement>('#quick-filters-btn');
        const quickFilters = this.root.querySelector<HTMLElement>('#quick-filters');
        quickFiltersBtn?.addEventListener('click', () => {
            if (!quickFilters) return;
            const isVisible = window.getComputedStyle(quickFilters).display !== 'none';
            quickFilters.style.display = isVisible ? 'none' : 'flex';
            quickFiltersBtn.textContent = isVisible ? 'Filtros rápidos ▼' : 'Filtros rápidos ▲';
        });
        this.root.querySelectorAll<HTMLButtonElement>('#quick-filters .quick-filter-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                const period = btn.dataset.period as 'today' | 'week' | 'month' | undefined;
                if (period) {
                    this.applyQuickFilter(period);
                    this.loadAllReports().catch((error) => {
                        console.error('[REPORTS] quick filter error', error);
                        this.showFeedback('Error al actualizar reportes con filtros rápidos', 'error');
                    });
                }
            });
        });
    }

    private initializeDateInputs(): void {
        const today = new Date();
        const sevenDaysAgo = new Date(today);
        sevenDaysAgo.setDate(today.getDate() - 7);
        if (this.startDateInput) this.startDateInput.valueAsDate = sevenDaysAgo;
        if (this.endDateInput) this.endDateInput.valueAsDate = today;
    }

    private applyQuickFilter(period: 'today' | 'week' | 'month'): void {
        const end = new Date();
        let start = new Date(end);
        if (period === 'week') {
            const dayOfWeek = end.getDay();
            const daysToMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
            start.setDate(end.getDate() - daysToMonday);
        } else if (period === 'month') {
            start = new Date(end.getFullYear(), end.getMonth(), 1);
        }
        if (this.startDateInput) this.startDateInput.valueAsDate = start;
        if (this.endDateInput) this.endDateInput.valueAsDate = end;
    }

    private async loadAllReports(): Promise<void> {
        await Promise.all([
            this.loadSalesReport(),
            this.loadTopProductsReport(),
            this.loadPeakHoursReport(),
            this.loadWaiterTipsReport()
        ]);
    }

    private async loadSalesReport(): Promise<void> {
        const startDate = this.startDateInput?.value || '';
        const endDate = this.endDateInput?.value || '';
        const groupBy = this.groupingSelect?.value || 'day';
        if (!startDate || !endDate) return;
        try {
            const response = await fetch(
                `/api/reports/sales?start_date=${startDate}&end_date=${endDate}&group_by=${groupBy}`
            );
            const result = await response.json();
            if (result?.error) throw new Error(result.error || 'Error al cargar ventas');
            this.renderSalesSummary(result.data.summary as SalesSummary);
            this.renderSalesChart(result.data.data as SalesDataPoint[]);
        } catch (error) {
            console.error('[REPORTS] sales', error);
            this.showFeedback('Error al cargar reporte de ventas', 'error');
        }
    }

    private renderSalesSummary(summary: SalesSummary): void {
        this.updateText('#total-orders', summary.total_orders.toLocaleString());
        this.updateText('#total-revenue', this.formatCurrency(summary.total_revenue));
        this.updateText('#total-tips-summary', this.formatCurrency(summary.total_tips));
        this.updateText('#avg-order-value', this.formatCurrency(summary.avg_order_value));
    }

    private renderSalesChart(points: SalesDataPoint[]): void {
        const canvas = this.root.querySelector<HTMLCanvasElement>('#sales-chart');
        if (!canvas || typeof Chart === 'undefined') return;
        if (this.salesChart) this.salesChart.destroy();
        const labels = points.map((point) => point.date);
        const salesData = points.map((point) => point.total_sales);
        const tipsData = points.map((point) => point.total_tips);
        this.salesChart = new Chart(canvas.getContext('2d'), {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Ventas',
                        data: salesData,
                        backgroundColor: 'rgba(102, 126, 234, 0.8)',
                        borderColor: 'rgba(102, 126, 234, 1)',
                        borderWidth: 1
                    },
                    {
                        label: 'Propinas',
                        data: tipsData,
                        backgroundColor: 'rgba(118, 75, 162, 0.8)',
                        borderColor: 'rgba(118, 75, 162, 1)',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: (value: number) => this.formatCurrency(value)
                        }
                    }
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: (context: any) => {
                                return `${context.dataset.label}: ${this.formatCurrency(context.parsed.y)}`;
                            }
                        }
                    }
                }
            }
        });
    }

    private async loadTopProductsReport(): Promise<void> {
        const startDate = this.startDateInput?.value || '';
        const endDate = this.endDateInput?.value || '';
        if (!startDate || !endDate) return;
        try {
            const response = await fetch(
                `/api/reports/top-products?start_date=${startDate}&end_date=${endDate}&limit=10`
            );
            const result = await response.json();
            if (result?.error) throw new Error(result.error || 'Error al cargar productos');
            this.renderTopProducts(result.data.data as TopProduct[]);
        } catch (error) {
            console.error('[REPORTS] top products', error);
            this.showFeedback('Error al cargar productos más vendidos', 'error');
        }
    }

    private renderTopProducts(products: TopProduct[]): void {
        const tbody = this.root.querySelector<HTMLTableSectionElement>('#top-products-table tbody');
        if (!tbody) return;
        if (!products.length) {
            tbody.innerHTML =
                '<tr><td colspan="5" style="text-align:center;padding:2rem;color:#64748b;">No hay productos vendidos en este período</td></tr>';
            if (this.topProductsChart) {
                this.topProductsChart.destroy();
                this.topProductsChart = null;
            }
            return;
        }
        tbody.innerHTML = products
            .map(
                (product, index) => `
                <tr>
                    <td>${index + 1}</td>
                    <td>${product.name}</td>
                    <td>${product.total_quantity}</td>
                    <td>${product.order_count}</td>
                    <td>${this.formatCurrency(product.total_revenue)}</td>
                </tr>`
            )
            .join('');
        const canvas = this.root.querySelector<HTMLCanvasElement>('#top-products-chart');
        if (!canvas || typeof Chart === 'undefined') return;
        if (this.topProductsChart) this.topProductsChart.destroy();
        this.topProductsChart = new Chart(canvas.getContext('2d'), {
            type: 'bar',
            data: {
                labels: products.map((p) => p.name),
                datasets: [
                    {
                        label: 'Cantidad Vendida',
                        data: products.map((p) => p.total_quantity),
                        backgroundColor: 'rgba(16, 185, 129, 0.8)',
                        borderColor: 'rgba(16, 185, 129, 1)',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { beginAtZero: true }
                }
            }
        });
    }

    private async loadPeakHoursReport(): Promise<void> {
        const startDate = this.startDateInput?.value || '';
        const endDate = this.endDateInput?.value || '';
        if (!startDate || !endDate) return;
        try {
            const response = await fetch(`/api/reports/peak-hours?start_date=${startDate}&end_date=${endDate}`);
            const result = await response.json();
            if (result?.error) throw new Error(result.error || 'Error al cargar horarios pico');
            const data: PeakHourResponse = result.data;
            this.renderPeakHours(data);
        } catch (error) {
            console.error('[REPORTS] peak hours', error);
            this.showFeedback('Error al cargar horarios pico', 'error');
        }
    }

    private renderPeakHours(response: PeakHourResponse): void {
        const display = this.root.querySelector('#peak-hour-display');
        const canvas = this.root.querySelector<HTMLCanvasElement>('#peak-hours-chart');
        const data = response.data?.length ? response.data : response.data?.data || [];
        if (!data.length) {
            if (display) display.textContent = 'Sin datos en este período';
            if (this.peakHoursChart) {
                this.peakHoursChart.destroy();
                this.peakHoursChart = null;
            }
            return;
        }
        if (display && response.peak_hour) {
            display.textContent = `${response.peak_hour.hour_label} (${response.peak_hour.order_count} órdenes)`;
        }
        if (!canvas || typeof Chart === 'undefined') return;
        if (this.peakHoursChart) this.peakHoursChart.destroy();
        this.peakHoursChart = new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: {
                labels: data.map((point) => point.hour_label),
                datasets: [
                    {
                        label: 'Órdenes',
                        data: data.map((point) => point.order_count),
                        borderColor: 'rgba(236, 72, 153, 0.9)',
                        backgroundColor: 'rgba(236, 72, 153, 0.2)',
                        tension: 0.4,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true }
                }
            }
        });
    }

    private async loadWaiterTipsReport(): Promise<void> {
        const startDate = this.startDateInput?.value || '';
        const endDate = this.endDateInput?.value || '';
        if (!startDate || !endDate) return;
        try {
            const response = await fetch(`/api/reports/waiter-tips?start_date=${startDate}&end_date=${endDate}`);
            const result = await response.json();
            if (result?.error) throw new Error(result.error || 'Error al cargar propinas');
            this.renderWaiterTips(result.data.summary as WaiterTipsSummary, result.data.data || result.data);
        } catch (error) {
            console.error('[REPORTS] waiter tips', error);
            this.showFeedback('Error al cargar propinas de meseros', 'error');
        }
    }

    private renderWaiterTips(summary: WaiterTipsSummary, waiters: WaiterTip[]): void {
        this.updateText('#total-tips-waiter', this.formatCurrency(summary.total_tips));
        this.updateText('#waiter-count', `${summary.waiter_count}`);
        const tbody = this.root.querySelector<HTMLTableSectionElement>('#waiter-tips-table tbody');
        if (!tbody) return;
        if (!waiters.length) {
            tbody.innerHTML =
                '<tr><td colspan="5" style="text-align:center;padding:2rem;color:#64748b;">Sin propinas registradas</td></tr>';
            return;
        }
        tbody.innerHTML = waiters
            .map(
                (waiter) => `
                <tr>
                    <td>${waiter.waiter_name}</td>
                    <td>${waiter.order_count}</td>
                    <td>${this.formatCurrency(waiter.total_tips)}</td>
                    <td>${this.formatCurrency(waiter.avg_tip)}</td>
                    <td>${waiter.tip_percentage.toFixed(1)}%</td>
                </tr>`
            )
            .join('');
    }

    private updateText(selector: string, text: string): void {
        const el = this.root.querySelector<HTMLElement>(selector);
        if (el) el.textContent = text;
    }

    private formatCurrency(value: number): string {
        const symbol = window.APP_SETTINGS?.currency_symbol || '€';
        const amount = Number(value) || 0;
        return `${symbol}${amount.toFixed(2)}`;
    }

    private showFeedback(message: string, type: 'info' | 'success' | 'warning' | 'error'): void {
        const feedback = this.root.querySelector('#reports-feedback');
        if (!feedback) return;
        feedback.textContent = message;
        feedback.className = `feedback ${type}`;
        window.setTimeout(() => {
            feedback.textContent = '';
            feedback.className = 'feedback';
        }, 3000);
    }
}
