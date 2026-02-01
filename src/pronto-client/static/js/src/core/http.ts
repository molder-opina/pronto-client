export interface RequestOptions<TBody = unknown> {
  method?: string;
  body?: TBody;
  headers?: Record<string, string>;
}

export class HTTPError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public statusText: string,
    public endpoint: string,
    public responseData?: unknown
  ) {
    super(message);
    this.name = 'HTTPError';
  }
}

const RETRYABLE_STATUSES = [408, 429, 500, 502, 503, 504];
const MAX_RETRIES = 2;
const BASE_DELAY_MS = 500;

async function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getRetryDelay(attempt: number): number {
  return BASE_DELAY_MS * Math.pow(2, attempt);
}

export async function requestJSON<TResponse = unknown, TBody = unknown>(
  endpoint: string,
  { method = 'GET', body, headers = {} }: RequestOptions<TBody> = {}
): Promise<TResponse> {
  let lastError: Error | null = null;
  let statusCode = 0;
  let statusText = '';
  let responseData: unknown;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      const response = await fetch(endpoint, {
        method,
        headers: body ? { 'Content-Type': 'application/json', ...headers } : headers,
        credentials: 'same-origin',
        body: body ? JSON.stringify(body) : undefined,
      });

      statusCode = response.status;
      statusText = response.statusText;

      responseData = await response.json().catch(() => ({}));

      if (response.ok) {
        return responseData as TResponse;
      }

      const message = extractErrorMessage(responseData);
      const isRetryable = RETRYABLE_STATUSES.includes(statusCode);

      if (isRetryable && attempt < MAX_RETRIES) {
        lastError = new HTTPError(message, statusCode, statusText, endpoint, responseData);
        await delay(getRetryDelay(attempt));
        continue;
      }

      throw new HTTPError(message, statusCode, statusText, endpoint, responseData);
    } catch (error) {
      if (error instanceof HTTPError) {
        throw error;
      }
      lastError = error instanceof Error ? error : new Error('Unknown error');
      if (attempt < MAX_RETRIES) {
        await delay(getRetryDelay(attempt));
        continue;
      }
      throw new HTTPError(
        lastError.message || 'Network error',
        statusCode || 0,
        statusText || 'Network Error',
        endpoint,
        responseData
      );
    }
  }

  throw lastError;
}

function extractErrorMessage(data: unknown): string {
  if (typeof data === 'object' && data !== null) {
    const obj = data as Record<string, unknown>;
    if (typeof obj.error === 'string') return obj.error;
    if (typeof obj.message === 'string') return obj.message;
    if (typeof obj.detail === 'string') return obj.detail;
    if (typeof obj.non_field_errors === 'string') return obj.non_field_errors;
    if (Array.isArray(obj.non_field_errors) && obj.non_field_errors.length > 0) {
      return String(obj.non_field_errors[0]);
    }
  }
  return 'Operación no disponible';
}
