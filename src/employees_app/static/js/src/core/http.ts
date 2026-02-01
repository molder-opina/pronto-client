export interface RequestOptions<TBody = unknown> {
  method?: string;
  body?: TBody;
  headers?: Record<string, string>;
}

/**
 * Detecta el scope actual desde la URL del navegador.
 * Retorna el path del scope (ej: "/waiter", "/chef", "/cashier", "/admin") o null.
 */
function getCurrentScope(): string | null {
  const path = window.location.pathname;
  const scopePrefixes = ['/waiter', '/chef', '/cashier', '/admin', '/system'];

  for (const prefix of scopePrefixes) {
    if (path.startsWith(prefix)) {
      return prefix;
    }
  }

  return null;
}

/**
 * Verifica si la respuesta indica una sesión inválida (401/403) y redirige al login.
 * Esta función puede ser llamada desde cualquier lugar que use fetch directamente.
 * @param response - La respuesta de fetch a verificar
 * @returns true si la sesión es válida, false si fue redirigido al login
 */
export function checkAuthAndRedirect(response: Response): boolean {
  if (response.status === 401) {
    console.warn('[AUTH] Sesión inválida detectada (401), redirigiendo al login...');
    if (typeof window.showToast === 'function') {
      window.showToast('Tu sesión ha expirado. Por favor inicia sesión nuevamente.', 'warning');
    }
    setTimeout(() => {
      window.location.href = '/login';
    }, 1500);
    return false;
  }

  if (response.status === 403) {
    console.warn('[AUTH] Permisos insuficientes (403).');
    // Redirigir a pantalla de error de autorización
    // Intentar leer header de mensaje si existe, sino genérico
    const reason = 'El usuario firmado no tiene permiso para acceder a este recurso.';
    window.location.href = `/authorization-error?code=403&message=${encodeURIComponent(reason)}&from=${encodeURIComponent(window.location.pathname)}`;
    return false;
  }

  return true;
}

/**
 * Wrapper de fetch que automáticamente verifica la autenticación.
 * Usar esta función en lugar de fetch() para tener verificación automática de sesión.
 */
export async function authenticatedFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  const currentScope = getCurrentScope();
  let url = typeof input === 'string' ? input : input.toString();

  // Rewrite /api/* to /<scope>/api/* for scoped API calls
  if (currentScope && url.startsWith('/api/')) {
    url = `${currentScope}${url}`;
    input = url;
  }

  const response = await fetch(input, init);
  checkAuthAndRedirect(response);
  return response;
}

export async function requestJSON<TResponse = unknown, TBody = unknown>(
  endpoint: string,
  { method = 'GET', body, headers = {} }: RequestOptions<TBody> = {}
): Promise<TResponse> {
  // Rewrite /api/* to /<scope>/api/* for scoped API calls
  const currentScope = getCurrentScope();
  let finalEndpoint = endpoint;

  if (currentScope && endpoint.startsWith('/api/')) {
    finalEndpoint = `${currentScope}${endpoint}`;
  }

  // Add CSRF token for non-GET requests
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
  const requestHeaders: Record<string, string> = body
    ? { 'Content-Type': 'application/json', ...headers }
    : { ...headers };

  if (csrfToken && !['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase())) {
    requestHeaders['X-CSRFToken'] = csrfToken;
  }

  const response = await fetch(finalEndpoint, {
    method,
    headers: requestHeaders,
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  });

  let data: any = {};
  try {
    data = await response.json();
  } catch (e) {
    // Si falla el parseo de JSON, intentar obtener el texto de respuesta
    console.error('[HTTP] JSON parse failed for response:', e);
    data = {};
  }

  if (!response.ok) {
    // Detectar sesión inválida y redirigir al login
    if (!checkAuthAndRedirect(response)) {
      throw new Error('Sesión expirada');
    }

    const message =
      (data as { error?: string }).error || `Error ${response.status}: ${response.statusText}`;
    throw new Error(message);
  }

  return data;
}
