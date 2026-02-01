/**
 * SESSION TIMEOUT MANAGER
 * Monitors session timeout and shows warnings to users before expiration
 */

const SESSION_TIMEOUT_KEY = 'pronto-session-timeout';
const SESSION_WARNING_BEFORE_MS = 60000;
const SESSION_CHECK_INTERVAL_MS = 30000;

let sessionTimeoutTimer: number | null = null;
let sessionWarningTimer: number | null = null;
let lastSessionCheck: number = 0;

export function initSessionTimeoutMonitor(): void {
  const sessionId = localStorage.getItem('pronto-session-id');
  if (!sessionId) return;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => startSessionMonitor(sessionId));
  } else {
    startSessionMonitor(sessionId);
  }

  document.addEventListener('visibilitychange', handleVisibilityChange);
  window.addEventListener('focus', handleWindowFocus);
}

function startSessionMonitor(sessionId: string): void {
  console.log('[SessionTimeout] Starting monitor for session:', sessionId);
  checkSessionTimeout(sessionId);
}

async function checkSessionTimeout(sessionId: string): Promise<void> {
  try {
    const response = await fetch(`/api/session/${sessionId}/timeout`);
    if (!response.ok) return;

    const data = await response.json();
    const expiresAt = data.expires_at;

    if (!expiresAt) return;

    const now = Date.now();
    const expiresAtMs = new Date(expiresAt).getTime();
    const timeUntilExpiry = expiresAtMs - now;

    if (timeUntilExpiry <= 0) {
      handleSessionExpired();
      return;
    }

    scheduleSessionWarning(timeUntilExpiry);
    scheduleNextCheck(timeUntilExpiry);
  } catch (error) {
    console.warn('[SessionTimeout] Failed to check session timeout:', error);
  }
}

function scheduleSessionWarning(timeUntilExpiry: number): void {
  if (sessionWarningTimer !== null) {
    clearTimeout(sessionWarningTimer);
  }

  const warningTime = timeUntilExpiry - SESSION_WARNING_BEFORE_MS;

  if (warningTime > 0) {
    sessionWarningTimer = window.setTimeout(() => {
      showSessionWarning();
      sessionWarningTimer = null;
    }, warningTime);
  } else {
    showSessionWarning();
  }
}

function scheduleNextCheck(timeUntilExpiry: number): void {
  if (sessionTimeoutTimer !== null) {
    clearTimeout(sessionTimeoutTimer);
  }

  const checkTime = Math.min(
    timeUntilExpiry - SESSION_WARNING_BEFORE_MS / 2,
    SESSION_CHECK_INTERVAL_MS
  );

  sessionTimeoutTimer = window.setTimeout(
    () => {
      const sessionId = localStorage.getItem('pronto-session-id');
      if (sessionId) {
        checkSessionTimeout(sessionId);
      }
    },
    Math.max(checkTime, 10000)
  );
}

function showSessionWarning(): void {
  const remainingMinutes = Math.round(SESSION_WARNING_BEFORE_MS / 60000);

  if (typeof window.showNotification === 'function') {
    window.showNotification(
      `Tu sesión expirará en ${remainingMinutes} minuto${remainingMinutes > 1 ? 's' : ''}. Guarda tu pedido.`,
      'warning'
    );
  }

  showSessionWarningBanner(remainingMinutes);
}

function showSessionWarningBanner(minutes: number): void {
  if (document.getElementById('session-warning-banner')) return;

  const banner = document.createElement('div');
  banner.id = 'session-warning-banner';
  banner.className = 'session-warning-banner';
  banner.innerHTML = `
    <div class="session-warning-content">
      <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <span>Tu sesión expirará en ${minutes} minuto${minutes > 1 ? 's' : ''}</span>
      <button class="session-warning-dismiss" aria-label="Cerrar">&times;</button>
    </div>
  `;

  Object.assign(banner.style, {
    position: 'fixed',
    top: '0',
    left: '0',
    right: '0',
    background: 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)',
    color: 'white',
    padding: '0.75rem 1rem',
    zIndex: '10050',
    fontSize: '0.9rem',
    fontWeight: '500',
    boxShadow: '0 2px 8px rgba(249, 115, 22, 0.4)',
    animation: 'sessionWarningSlideDown 0.3s ease',
  });

  const contentStyle = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.5rem',
    maxWidth: '1200px',
    margin: '0 auto',
  };

  const dismissStyle = {
    background: 'none',
    border: 'none',
    color: 'white',
    fontSize: '1.25rem',
    cursor: 'pointer',
    padding: '0 0.25rem',
    marginLeft: 'auto',
    opacity: '0.8',
  };

  const content = banner.querySelector('.session-warning-content') as HTMLElement;
  const dismissBtn = banner.querySelector('.session-warning-dismiss') as HTMLButtonElement;

  if (content) Object.assign(content.style, contentStyle);
  if (dismissBtn) Object.assign(dismissBtn.style, dismissStyle);

  dismissBtn?.addEventListener('click', () => {
    banner.remove();
  });

  document.body.appendChild(banner);

  if (!document.getElementById('session-warning-styles')) {
    const style = document.createElement('style');
    style.id = 'session-warning-styles';
    style.textContent = `
      @keyframes sessionWarningSlideDown {
        from {
          opacity: 0;
          transform: translateY(-100%);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }
    `;
    document.head.appendChild(style);
  }
}

function handleSessionExpired(): void {
  cleanupSessionTimers();

  if (typeof window.showNotification === 'function') {
    window.showNotification('Tu sesión ha expirado. Serás redirigido al inicio.', 'error');
  }

  setTimeout(() => {
    localStorage.removeItem('pronto-session-id');
    window.location.href = '/';
  }, 3000);
}

function handleVisibilityChange(): void {
  if (document.visibilityState === 'visible') {
    const sessionId = localStorage.getItem('pronto-session-id');
    if (sessionId) {
      checkSessionTimeout(sessionId);
    }
  }
}

function handleWindowFocus(): void {
  const now = Date.now();
  if (now - lastSessionCheck > SESSION_CHECK_INTERVAL_MS) {
    const sessionId = localStorage.getItem('pronto-session-id');
    if (sessionId) {
      checkSessionTimeout(sessionId);
      lastSessionCheck = now;
    }
  }
}

function cleanupSessionTimers(): void {
  if (sessionTimeoutTimer !== null) {
    clearTimeout(sessionTimeoutTimer);
    sessionTimeoutTimer = null;
  }
  if (sessionWarningTimer !== null) {
    clearTimeout(sessionWarningTimer);
    sessionWarningTimer = null;
  }

  const banner = document.getElementById('session-warning-banner');
  banner?.remove();
}

export function cleanupSessionMonitor(): void {
  cleanupSessionTimers();
  document.removeEventListener('visibilitychange', handleVisibilityChange);
  window.removeEventListener('focus', handleWindowFocus);
}

export function refreshSessionTimeout(): void {
  const sessionId = localStorage.getItem('pronto-session-id');
  if (sessionId) {
    cleanupSessionTimers();
    checkSessionTimeout(sessionId);
  }
}
