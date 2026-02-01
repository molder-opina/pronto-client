/**
 * Formatting Utilities
 * Shared functions for formatting data across the application.
 */

/**
 * Format a number as a currency string.
 * @param value The amount to format.
 * @param currency The currency code (default: 'MXN').
 * @param locale The locale (default: 'es-MX').
 */
export function formatCurrency(value: number, currency = 'MXN', locale = 'es-MX'): string {
    return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: currency,
    }).format(value || 0);
}

/**
 * Escape HTML characters to prevent XSS.
 * @param text The string to escape.
 */
export function escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Format a date string or object to a localized string.
 * @param dateStr The date to format.
 * @param locale The locale (default: 'es-MX').
 * @param options Intl.DateTimeFormatOptions.
 */
export function formatDateTime(
    dateStr: string | Date,
    locale = 'es-MX',
    options: Intl.DateTimeFormatOptions = { dateStyle: 'short', timeStyle: 'short' }
): string {
    if (!dateStr) return 'N/A';
    const date = typeof dateStr === 'string' ? new Date(dateStr) : dateStr;
    if (isNaN(date.getTime())) return 'N/A';
    return date.toLocaleString(locale, options);
}

/**
 * Get relative time string (e.g. "Hace 5 minutos").
 * @param date The date to compare against now.
 */
export function getTimeAgo(date: Date): string {
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return 'Hace unos segundos';
    if (seconds < 120) return 'Hace 1 minuto';
    if (seconds < 3600) return `Hace ${Math.floor(seconds / 60)} minutos`;
    if (seconds < 7200) return 'Hace 1 hora';
    return `Hace ${Math.floor(seconds / 3600)} horas`;
}
