interface SessionData {
  session_id: number;
  table_id: number;
  anon_id: string;
  status: string;
  expires_at: string | null;
}

let currentSession: SessionData | null = null;

export async function initSession(tableId: number): Promise<number> {
  const cachedSessionId = localStorage.getItem('pronto-session-id');
  const cachedAnonId = localStorage.getItem('pronto-anon-id');

  if (cachedSessionId) {
    const ok = await validateSession(parseInt(cachedSessionId, 10), tableId);
    if (ok) return parseInt(cachedSessionId, 10);
    localStorage.removeItem('pronto-session-id');
  }

  const sess = await openSession(tableId, cachedAnonId);
  localStorage.setItem('pronto-session-id', String(sess.session_id));
  localStorage.setItem('pronto-anon-id', sess.anon_id);
  currentSession = sess;
  return sess.session_id;
}

async function openSession(tableId: number, anonId: string | null): Promise<SessionData> {
  const r = await fetch('/api/sessions/open', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ table_id: tableId, anon_id: anonId }),
  });

  const payload = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(payload?.error || 'Error abriendo sesión');
  return payload.data as SessionData;
}

async function validateSession(sessionId: number, tableId: number): Promise<boolean> {
  try {
    const r = await fetch(`/api/sessions/validate?session_id=${sessionId}&table_id=${tableId}`);
    const payload = await r.json().catch(() => ({}));
    return payload.valid === true;
  } catch {
    return false;
  }
}

export function getSessionId(): number | null {
  const v = localStorage.getItem('pronto-session-id');
  return v ? parseInt(v, 10) : null;
}

export function getAnonId(): string | null {
  return localStorage.getItem('pronto-anon-id');
}

export function clearSession(): void {
  localStorage.removeItem('pronto-session-id');
  localStorage.removeItem('pronto-anon-id');
  currentSession = null;
}

export function getCurrentSession(): SessionData | null {
  return currentSession;
}

export function setSessionId(sessionId: number): void {
  localStorage.setItem('pronto-session-id', String(sessionId));
  if (typeof window !== 'undefined') {
    (window as any).setSessionId?.(sessionId);
  }
}
