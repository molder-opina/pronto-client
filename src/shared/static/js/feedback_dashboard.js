/**
 * Feedback Dashboard - OOP Refactored
 * Displays statistics, charts, and recent feedback
 */

/**
 * Utilities
 */
class FeedbackUtils {
    static escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    static showNotification(message, type = 'info') {
        if (typeof window.showNotification === 'function') {
            window.showNotification(message, type);
        } else {
            console.log(`[${type}] ${message}`);
        }
    }
}

/**
 * Stats Renderer - Handles rendering of statistics
 */
class StatsRenderer {
    static CATEGORY_NAMES = {
        'waiter_service': 'Servicio del Mesero',
        'food_quality': 'Calidad de Comida',
        'food_presentation': 'Presentación',
        'overall_experience': 'Experiencia General'
    };

    renderOverallStats(stats) {
        document.getElementById('avg-rating').textContent = stats.average_rating.toFixed(1) + ' ⭐';
        document.getElementById('total-feedback').textContent = stats.total_feedback;
        document.getElementById('feedback-change').textContent = `En ${stats.period_days} días`;

        const fiveStarCount = stats.rating_distribution[5] || 0;
        document.getElementById('five-star-count').textContent = fiveStarCount;

        const foodQuality = stats.by_category['food_quality'];
        if (foodQuality) {
            document.getElementById('food-rating').textContent = foodQuality.average_rating.toFixed(1) + ' ⭐';
        } else {
            document.getElementById('food-rating').textContent = 'N/A';
        }
    }

    renderRatingDistribution(distribution) {
        const container = document.getElementById('rating-distribution');
        container.innerHTML = '';

        const total = Object.values(distribution).reduce((sum, count) => sum + count, 0);

        for (let rating = 5; rating >= 1; rating--) {
            const count = distribution[rating] || 0;
            const percentage = total > 0 ? (count / total * 100) : 0;

            const item = document.createElement('div');
            item.className = 'rating-bar-item';
            item.innerHTML = `
                <div class="rating-label">${rating} ⭐</div>
                <div class="rating-bar-bg">
                    <div class="rating-bar-fill" style="width: ${percentage}%">
                        ${count > 0 ? count : ''}
                    </div>
                </div>
            `;
            container.appendChild(item);
        }
    }

    renderCategoryRatings(categories) {
        const container = document.getElementById('category-ratings');
        container.innerHTML = '';

        Object.entries(categories).forEach(([categoryKey, data]) => {
            const percentage = (data.average_rating / 5) * 100;
            const fullStars = Math.floor(data.average_rating);
            const hasHalfStar = (data.average_rating % 1) >= 0.5;

            const item = document.createElement('div');
            item.className = 'category-item';

            let starsHTML = '';
            for (let i = 0; i < 5; i++) {
                if (i < fullStars) {
                    starsHTML += '<span class="star">★</span>';
                } else if (i === fullStars && hasHalfStar) {
                    starsHTML += '<span class="star">★</span>';
                } else {
                    starsHTML += '<span class="star empty">★</span>';
                }
            }

            item.innerHTML = `
                <div class="category-header">
                    <span class="category-name">${StatsRenderer.CATEGORY_NAMES[categoryKey] || categoryKey}</span>
                    <div class="category-rating">
                        <div class="stars">${starsHTML}</div>
                        <span style="font-weight: 600; color: #0f172a;">${data.average_rating.toFixed(1)}</span>
                    </div>
                </div>
                <div class="category-bar">
                    <div class="category-bar-fill" style="width: ${percentage}%"></div>
                </div>
            `;
            container.appendChild(item);
        });
    }

    renderTopEmployees(employees) {
        const container = document.getElementById('top-employees');
        container.innerHTML = '';

        if (employees.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 2rem; color: #64748b;">
                    <p>No hay datos de feedback aún</p>
                </div>
            `;
            return;
        }

        employees.forEach((employee, index) => {
            const item = document.createElement('div');
            item.className = 'employee-item';

            item.innerHTML = `
                <div class="employee-rank">${index + 1}</div>
                <div class="employee-info">
                    <div class="employee-name">${FeedbackUtils.escapeHtml(employee.employee_name)}</div>
                    <div class="employee-feedback">${employee.feedback_count} calificaciones</div>
                </div>
                <div class="employee-rating">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="color: #FFA500;">
                        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
                    </svg>
                    ${employee.average_rating.toFixed(1)}
                </div>
            `;
            container.appendChild(item);
        });
    }

    renderRecentFeedbackPlaceholder() {
        const container = document.getElementById('recent-feedback');
        container.innerHTML = `
            <div style="text-align: center; padding: 2rem; color: #64748b;">
                <p>Endpoint de feedback reciente próximamente</p>
            </div>
        `;
    }
}

/**
 * Feedback Dashboard - Main Controller
 */
class FeedbackDashboard {
    constructor() {
        this.state = {
            period: 30,
            overallStats: null,
            topEmployees: [],
            recentFeedback: []
        };
        this.renderer = new StatsRenderer();
    }

    async init() {
        await this.loadDashboardData();
    }

    async loadDashboardData() {
        try {
            await Promise.all([
                this.loadOverallStats(),
                this.loadTopEmployees(),
                this.loadRecentFeedback()
            ]);
        } catch (error) {
            console.error('Error loading dashboard data:', error);
            FeedbackUtils.showNotification('Error al cargar datos', 'error');
        }
    }

    async loadOverallStats() {
        try {
            const response = await fetch(`/api/feedback/stats/overall?days=${this.state.period}`);
            const result = await response.json();

            if (result.success && result.data) {
                this.state.overallStats = result.data;
                this.renderer.renderOverallStats(result.data);
                this.renderer.renderRatingDistribution(result.data.rating_distribution);
                this.renderer.renderCategoryRatings(result.data.by_category);
            }
        } catch (error) {
            console.error('Error loading overall stats:', error);
        }
    }

    async loadTopEmployees() {
        try {
            const response = await fetch(`/api/feedback/stats/top-employees?days=${this.state.period}&limit=5`);
            const result = await response.json();

            if (result.success && result.data.employees) {
                this.state.topEmployees = result.data.employees;
                this.renderer.renderTopEmployees(result.data.employees);
            }
        } catch (error) {
            console.error('Error loading top employees:', error);
        }
    }

    async loadRecentFeedback() {
        this.renderer.renderRecentFeedbackPlaceholder();
    }

    changePeriod(days) {
        this.state.period = parseInt(days);
        this.loadDashboardData();
    }

    viewAllFeedback() {
        FeedbackUtils.showNotification('Función de ver todo próximamente', 'info');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.feedbackDashboard = new FeedbackDashboard();
    window.feedbackDashboard.init();
});

// Legacy compatibility
window.changePeriod = function(days) {
    window.feedbackDashboard?.changePeriod(days);
};

window.viewAllFeedback = function() {
    window.feedbackDashboard?.viewAllFeedback();
};
