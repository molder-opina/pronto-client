/**
 * Interceptor global de fetch para verificar automáticamente la autenticación
 * en todas las peticiones HTTP de la aplicación.
 *
 * Este módulo debe ser importado al inicio de la aplicación para activarse.
 */

import { checkAuthAndRedirect } from './http';

// Guardar referencia original de fetch
const originalFetch = window.fetch;

// Sobrescribir fetch global con versión que verifica autenticación
window.fetch = async function(
    input: RequestInfo | URL,
    init?: RequestInit
): Promise<Response> {
    try {
        const response = await originalFetch(input, init);

        // Solo verificar autenticación para peticiones a nuestra API
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/') || url.startsWith('/api/')) {
            checkAuthAndRedirect(response);
        }

        return response;
    } catch (error) {
        // Re-lanzar errores de red u otros errores
        throw error;
    }
};

console.log('[AUTH] Interceptor de autenticación activado');
