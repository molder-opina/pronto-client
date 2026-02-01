/**
 * Anonymous Sessions Manager
 * Handles the UI for managing anonymous sessions assigned to tables
 */

interface AnonymousSession {
    id: number;
    table_number: string | null;
    anonymous_client_id: string | null;
    status: string;
    orders_count: number;
    created_at: string | null;
    customer_name: string | null;
    is_duplicate_table: boolean;
}

interface AnonymousSessionsResponse {
    sessions: AnonymousSession[];
    count: number;
    duplicate_tables: string[];
    duplicate_count: number;
}

const STATUS_LABELS: Record<string, string> = {
    'open': 'Abierta',
    'awaiting_tip': 'Esperando propina',
    'awaiting_payment': 'Esperando pago',
    'awaiting_payment_confirmation': 'Confirmando pago',
    'closed': 'Cerrada',
    'paid': 'Pagada',
    'cancelled': 'Cancelada',
};

export function initAnonymousSessionsManager(): void {
    const tableBody = document.getElementById('anonymous-sessions-table');
    const refreshBtn = document.getElementById('refresh-anonymous-sessions');
    const feedbackEl = document.getElementById('anonymous-sessions-feedback');

    if (!tableBody) {
        console.log('[AnonymousSessions] Table not found, skipping initialization');
        return;
    }

    console.log('[AnonymousSessions] Initializing...');

    // Load initial data
    loadAnonymousSessions(tableBody, feedbackEl);

    // Refresh button
    refreshBtn?.addEventListener('click', () => {
        loadAnonymousSessions(tableBody, feedbackEl);
    });

    // Delegate click events for action buttons
    tableBody.addEventListener('click', async (event) => {
        const target = event.target as HTMLElement;
        const button = target.closest('button');
        if (!button) return;

        const sessionId = button.dataset.sessionId;
        if (!sessionId) return;

        if (button.classList.contains('delete-session-btn')) {
            await handleDeleteSession(Number(sessionId), tableBody, feedbackEl);
        } else if (button.classList.contains('regenerate-session-btn')) {
            await handleRegenerateSession(Number(sessionId), tableBody, feedbackEl);
        }
    });
}

async function loadAnonymousSessions(
    tableBody: HTMLElement,
    feedbackEl: HTMLElement | null
): Promise<void> {
    tableBody.innerHTML = `
        <tr>
            <td colspan="6" style="text-align: center; padding: 2rem; color: #64748b;">
                Cargando sesiones anónimas...
            </td>
        </tr>
    `;

    try {
        const response = await fetch('/api/sessions/anonymous', {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Error al cargar sesiones');
        }

        const data: AnonymousSessionsResponse = await response.json();
        renderSessions(tableBody, data.sessions || []);

        // Build feedback message with duplicate info
        let feedbackMsg = `${data.count} sesiones anónimas`;
        if (data.duplicate_count > 0) {
            feedbackMsg += ` | ⚠️ ${data.duplicate_count} mesa(s) con sesiones duplicadas: ${data.duplicate_tables.join(', ')}`;
        }
        showFeedback(feedbackEl, feedbackMsg, data.duplicate_count > 0);
    } catch (error) {
        console.error('[AnonymousSessions] Error loading:', error);
        tableBody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; padding: 2rem; color: #ef4444;">
                    Error al cargar sesiones anónimas
                </td>
            </tr>
        `;
        showFeedback(feedbackEl, 'Error al cargar sesiones', true);
    }
}

function renderSessions(tableBody: HTMLElement, sessions: AnonymousSession[]): void {
    if (sessions.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; padding: 2rem; color: #64748b;">
                    <div style="font-size: 2rem; margin-bottom: 0.5rem;">✅</div>
                    No hay sesiones anónimas activas
                </td>
            </tr>
        `;
        return;
    }

    tableBody.innerHTML = sessions.map(session => {
        const createdAt = session.created_at
            ? new Date(session.created_at).toLocaleString('es-ES', {
                dateStyle: 'short',
                timeStyle: 'short'
            })
            : 'N/A';

        const statusLabel = STATUS_LABELS[session.status] || session.status;
        const statusClass = getStatusClass(session.status);

        // Highlight duplicate tables with warning style
        const rowStyle = session.is_duplicate_table
            ? 'background: #fef3c7; border-left: 4px solid #f59e0b;'
            : '';
        const duplicateBadge = session.is_duplicate_table
            ? '<span style="background: #f59e0b; color: white; padding: 0.125rem 0.375rem; border-radius: 4px; font-size: 0.7rem; margin-left: 0.5rem;">DUPLICADA</span>'
            : '';

        return `
            <tr data-session-id="${session.id}" style="${rowStyle}">
                <td>
                    <strong>${session.table_number || 'Sin mesa'}</strong>${duplicateBadge}
                </td>
                <td>
                    <code style="background: #f1f5f9; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.85rem;">
                        ${session.anonymous_client_id || 'N/A'}
                    </code>
                </td>
                <td>
                    <span class="status ${statusClass}">${statusLabel}</span>
                </td>
                <td>
                    <span style="display: inline-flex; align-items: center; gap: 0.25rem;">
                        📦 ${session.orders_count}
                    </span>
                </td>
                <td style="font-size: 0.85rem; color: #64748b;">
                    ${createdAt}
                </td>
                <td>
                    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                        <button type="button"
                            class="btn btn--small btn--secondary regenerate-session-btn"
                            data-session-id="${session.id}"
                            title="Regenerar ID de cliente anónimo">
                            🔄 Regenerar ID
                        </button>
                        <button type="button"
                            class="btn btn--small btn--danger delete-session-btn"
                            data-session-id="${session.id}"
                            title="${session.orders_count > 0 ? 'Eliminar sesión y sus órdenes' : 'Eliminar sesión vacía'}">
                            🗑️ Eliminar
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

function getStatusClass(status: string): string {
    const statusClasses: Record<string, string> = {
        'open': 'status--open',
        'awaiting_tip': 'status--warning',
        'awaiting_payment': 'status--warning',
        'awaiting_payment_confirmation': 'status--info',
        'closed': 'status--success',
        'paid': 'status--success',
        'cancelled': 'status--error',
    };
    return statusClasses[status] || 'status--default';
}

async function handleDeleteSession(
    sessionId: number,
    tableBody: HTMLElement,
    feedbackEl: HTMLElement | null
): Promise<void> {
    const confirmed = window.confirm(
        '¿Estás seguro de que deseas eliminar esta sesión anónima?\n\n' +
        'Esta acción cancelará la sesión y eliminará todas sus órdenes no pagadas.'
    );

    if (!confirmed) return;

    showFeedback(feedbackEl, 'Eliminando sesión...', false);

    try {
        const response = await fetch(`/api/sessions/${sessionId}/anonymous`, {
            method: 'DELETE',
            credentials: 'include'
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Error al eliminar sesión');
        }

        showFeedback(feedbackEl, '✅ Sesión eliminada correctamente', false);
        // Reload the table
        await loadAnonymousSessions(tableBody, feedbackEl);
    } catch (error) {
        console.error('[AnonymousSessions] Error deleting:', error);
        showFeedback(feedbackEl, (error as Error).message, true);
    }
}

async function handleRegenerateSession(
    sessionId: number,
    tableBody: HTMLElement,
    feedbackEl: HTMLElement | null
): Promise<void> {
    const confirmed = window.confirm(
        '¿Regenerar el ID de cliente anónimo para esta sesión?\n\n' +
        'Esto creará un nuevo cliente anónimo y reasignará la sesión. ' +
        'El cliente actual perderá acceso a esta sesión en su dispositivo.'
    );

    if (!confirmed) return;

    showFeedback(feedbackEl, 'Regenerando ID...', false);

    try {
        const response = await fetch(`/api/sessions/${sessionId}/regenerate-anonymous`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Error al regenerar ID');
        }

        showFeedback(feedbackEl, `✅ Nuevo ID: ${data.new_anonymous_id}`, false);
        // Reload the table
        await loadAnonymousSessions(tableBody, feedbackEl);
    } catch (error) {
        console.error('[AnonymousSessions] Error regenerating:', error);
        showFeedback(feedbackEl, (error as Error).message, true);
    }
}

function showFeedback(element: HTMLElement | null, message: string, isError: boolean): void {
    if (!element) return;
    element.textContent = message;
    element.style.color = isError ? '#ef4444' : '#10b981';

    // Clear after 5 seconds
    setTimeout(() => {
        if (element.textContent === message) {
            element.textContent = '';
        }
    }, 5000);
}
