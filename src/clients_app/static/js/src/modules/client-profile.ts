interface ProntoUser {
  name: string;
  email: string;
  avatar?: string | null;
}

export function initClientProfile(): void {
  const start = (): void => {
    console.log('[client-profile] Initializing module...');
    setupProfileModal();
    setupSupportModal();
    setupPasswordToggles();
    setupPasswordStrength();
    setupTermsCheckbox();
    setupPasswordRecovery();
    setupOrderHistory();
    hydrateHeaderAvatarFromStorage();

    // Expose minimal globals for existing integrations (debug panel, etc.)
    (window as any).toggleProfile = openProfileModal;
    (window as any).closeProfileModal = closeProfileModal;
    (window as any).openSupportModal = openSupportModal;
    (window as any).closeSupportModal = closeSupportModal;
    (window as any).openPasswordRecovery = openPasswordRecovery;
    (window as any).openOrderHistory = openOrderHistory;
    console.log('[client-profile] Module initialized successfully');
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
}

// ---------------------------------------------------------------------------
// Password Toggle
// ---------------------------------------------------------------------------
function setupPasswordToggles(): void {
  const toggleButtons = document.querySelectorAll<HTMLButtonElement>('.password-toggle');
  toggleButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const input = btn.parentElement?.querySelector<HTMLInputElement>(
        'input[type="password"], input[type="text"]'
      );
      if (!input) return;

      const eyeIcon = btn.querySelector('.eye-icon') as HTMLElement;
      const slashIcon = btn.querySelector('.eye-slash-icon') as HTMLElement;

      if (input.type === 'password') {
        input.type = 'text';
        eyeIcon.style.display = 'none';
        slashIcon.style.display = 'block';
        btn.setAttribute('aria-label', 'Ocultar contraseña');
      } else {
        input.type = 'password';
        eyeIcon.style.display = 'block';
        slashIcon.style.display = 'none';
        btn.setAttribute('aria-label', 'Mostrar contraseña');
      }
    });
  });
}

// ---------------------------------------------------------------------------
// Password Strength Indicator
// ---------------------------------------------------------------------------
function setupPasswordStrength(): void {
  const passwordInput = document.getElementById('register-password') as HTMLInputElement | null;
  const strengthBar = document.getElementById('password-strength-bar') as HTMLElement | null;
  const requirements = document.getElementById('password-requirements');

  if (!passwordInput || !strengthBar) return;

  passwordInput.addEventListener('input', () => {
    const password = passwordInput.value;
    const strength = calculatePasswordStrength(password);

    // Update strength bar
    strengthBar.classList.remove('weak', 'medium', 'strong');
    if (password.length > 0) {
      strengthBar.classList.add(strength.level);
    }

    // Update requirements
    if (requirements) {
      requirements.querySelectorAll('.req').forEach((req) => {
        const reqEl = req as HTMLElement;
        const reqType = reqEl.dataset.req;
        if (reqType === 'length') {
          req.classList.toggle('met', password.length >= 6);
        } else if (reqType === 'number') {
          req.classList.toggle('met', /\d/.test(password));
        } else if (reqType === 'uppercase') {
          req.classList.toggle('met', /[A-Z]/.test(password));
        }
      });
    }

    // Update submit button state
    updateRegisterButtonState();
  });
}

function updateRegisterButtonState(): void {
  const termsCheckbox = document.getElementById('accept-terms') as HTMLInputElement | null;
  const passwordInput = document.getElementById('register-password') as HTMLInputElement | null;
  const submitBtn = document.getElementById('register-submit-btn') as HTMLButtonElement | null;

  if (!submitBtn || !passwordInput) return;

  const termsAccepted = termsCheckbox?.checked ?? false;
  const passwordValid = passwordInput.value.length >= 6;

  submitBtn.disabled = !(termsAccepted && passwordValid);
}

function setupProfileModal(): void {
  const profileButton = document.querySelector<HTMLButtonElement>('.profile-btn');
  const modal = document.getElementById('profile-modal');
  if (!modal || !profileButton) return;

  const overlay = modal.querySelector<HTMLElement>('.profile-modal-overlay');
  const closeButton = modal.querySelector<HTMLButtonElement>('.profile-modal-close');

  profileButton.addEventListener('click', () => openProfileModal());
  overlay?.addEventListener('click', () => closeProfileModal());
  closeButton?.addEventListener('click', () => closeProfileModal());

  // Tabs: login / register
  const tabs = modal.querySelectorAll<HTMLButtonElement>('.profile-tab');
  tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab === 'register' ? 'register' : 'login';
      switchTab(target);
    });
  });

  // Phone input validation - only numbers
  const phoneInput = document.getElementById('register-phone') as HTMLInputElement | null;
  phoneInput?.addEventListener('input', (event) => {
    const input = event.target as HTMLInputElement;
    input.value = input.value.replace(/[^0-9]/g, '');
  });

  // Login form
  const loginForm = document.getElementById('login-form') as HTMLFormElement | null;
  loginForm?.addEventListener('submit', (event) => {
    event.preventDefault();
    void handleLoginSubmit(loginForm);
  });

  // Register form
  const registerForm = document.getElementById('register-form') as HTMLFormElement | null;
  registerForm?.addEventListener('submit', (event) => {
    event.preventDefault();
    void handleRegisterSubmit(registerForm);
  });

  // Profile menu actions
  const ordersBtn = modal.querySelector<HTMLButtonElement>('[data-profile-action="orders"]');
  const settingsBtn = modal.querySelector<HTMLButtonElement>('[data-profile-action="settings"]');
  const logoutBtn = modal.querySelector<HTMLButtonElement>('[data-profile-action="logout"]');

  ordersBtn?.addEventListener('click', () => {
    closeProfileModal();
    (window as any).showNotification?.('Historial de pedidos próximamente', 'info');
  });

  settingsBtn?.addEventListener('click', () => {
    closeProfileModal();
    (window as any).showNotification?.('Configuración próximamente', 'info');
  });

  logoutBtn?.addEventListener('click', () => {
    performLogout();
  });

  // Initial state based on current user
  const currentUser = getCurrentUser();
  if (currentUser) {
    updateHeaderAvatar(currentUser);
  }
}

function openProfileModal(): void {
  const ids = Array.from(document.querySelectorAll('*[id]')).map(el => el.id);
  console.log('[client-profile] openProfileModal called. All IDs on page:', ids);
  const modal = document.getElementById('profile-modal');
  console.log('[client-profile] openProfileModal - profile-modal found:', !!modal);

  if (!modal) return;

  modal.classList.add('active');
  const user = getCurrentUser();
  if (user) {
    showLoggedInView(user);
  } else {
    showNotLoggedInView();
  }
}

function closeProfileModal(): void {
  const modal = document.getElementById('profile-modal');
  modal?.classList.remove('active');
}

function switchTab(tab: 'login' | 'register'): void {
  const loginForm = document.getElementById('login-form') as HTMLElement | null;
  const registerForm = document.getElementById('register-form') as HTMLElement | null;
  const tabs = document.querySelectorAll<HTMLButtonElement>('.profile-tab');

  tabs.forEach((t) => t.classList.remove('active'));

  if (tab === 'login') {
    if (loginForm) loginForm.style.display = 'block';
    if (registerForm) registerForm.style.display = 'none';
    const loginTab = document.querySelector('.profile-tab[data-tab="login"]');
    loginTab?.classList.add('active');
  } else {
    if (loginForm) loginForm.style.display = 'none';
    if (registerForm) registerForm.style.display = 'block';
    const registerTab = document.querySelector('.profile-tab[data-tab="register"]');
    registerTab?.classList.add('active');
  }
}

function showLoggedInView(user: ProntoUser): void {
  const notLoggedInView = document.getElementById('profile-not-logged-in');
  const loggedInView = document.getElementById('profile-logged-in');
  const nameEl = document.getElementById('profile-name');
  const emailEl = document.getElementById('profile-email');
  const avatarEl = document.getElementById('profile-modal-avatar') as HTMLImageElement | null;

  if (notLoggedInView) notLoggedInView.style.display = 'none';
  if (loggedInView) loggedInView.style.display = 'block';
  if (nameEl) nameEl.textContent = user.name;
  if (emailEl) emailEl.textContent = user.email;
  if (avatarEl && user.avatar) {
    avatarEl.src = user.avatar;
  }
}

function showNotLoggedInView(): void {
  const notLoggedInView = document.getElementById('profile-not-logged-in');
  const loggedInView = document.getElementById('profile-logged-in');

  if (notLoggedInView) notLoggedInView.style.display = 'block';
  if (loggedInView) loggedInView.style.display = 'none';
  switchTab('login');
}

async function handleLoginSubmit(form: HTMLFormElement): Promise<void> {
  const feedback = document.getElementById('login-feedback');
  const submitBtn = form.querySelector<HTMLButtonElement>('button[type="submit"]');
  const emailInput = document.getElementById('login-email') as HTMLInputElement | null;
  const passwordInput = document.getElementById('login-password') as HTMLInputElement | null;

  if (!feedback || !emailInput || !passwordInput || !submitBtn) return;

  feedback.className = 'form-feedback';
  feedback.textContent = 'Iniciando sesión...';
  (feedback as HTMLElement).style.display = 'block';
  submitBtn.disabled = true;

  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: emailInput.value, password: passwordInput.value }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Error al iniciar sesión');
    }
    const user = data.user as ProntoUser;
    saveCurrentUser(user);
    feedback.className = 'form-feedback success';
    feedback.textContent = '¡Bienvenido de nuevo!';

    window.setTimeout(() => {
      showLoggedInView(user);
      updateHeaderAvatar(user);
      closeProfileModal();
    }, 1000);
  } catch (error: any) {
    feedback.className = 'form-feedback error';
    feedback.textContent = error.message || 'Error al iniciar sesión';
  } finally {
    submitBtn.disabled = false;
  }
}

async function handleRegisterSubmit(form: HTMLFormElement): Promise<void> {
  const feedback = document.getElementById('register-feedback');
  const submitBtn = form.querySelector<HTMLButtonElement>('button[type="submit"]');
  const nameInput = document.getElementById('register-name') as HTMLInputElement | null;
  const emailInput = document.getElementById('register-email') as HTMLInputElement | null;
  const phoneInput = document.getElementById('register-phone') as HTMLInputElement | null;
  const passwordInput = document.getElementById('register-password') as HTMLInputElement | null;

  if (!feedback || !submitBtn || !nameInput || !emailInput || !phoneInput || !passwordInput) return;

  feedback.className = 'form-feedback';
  feedback.textContent = 'Creando cuenta...';
  (feedback as HTMLElement).style.display = 'block';
  submitBtn.disabled = true;

  const phone = phoneInput.value;
  if (phone && phone.length !== 10) {
    feedback.className = 'form-feedback error';
    feedback.textContent = 'El teléfono debe tener 10 dígitos';
    submitBtn.disabled = false;
    return;
  }

  try {
    const response = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: nameInput.value,
        email: emailInput.value,
        phone: phone ? `+52${phone}` : null,
        password: passwordInput.value,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Error al crear la cuenta');
    }
    const user = data.user as ProntoUser;
    saveCurrentUser(user);
    feedback.className = 'form-feedback success';
    feedback.textContent = '¡Cuenta creada exitosamente!';

    // Clear form immediately
    form.reset();

    // Close modal and show notification
    window.setTimeout(() => {
      closeProfileModal();
      (window as any).showNotification?.(
        '¡Cuenta creada exitosamente! Bienvenido/a, ' + user.name,
        'success'
      );
      showLoggedInView(user);
      updateHeaderAvatar(user);
    }, 800);
  } catch (error: any) {
    feedback.className = 'form-feedback error';
    feedback.textContent = error.message || 'Error al registrarse';
  } finally {
    submitBtn.disabled = false;
  }
}

function saveCurrentUser(user: ProntoUser): void {
  localStorage.setItem('pronto-user', JSON.stringify(user));
}

function getCurrentUser(): ProntoUser | null {
  const item = localStorage.getItem('pronto-user');
  if (!item) return null;
  try {
    return JSON.parse(item) as ProntoUser;
  } catch {
    return null;
  }
}

function performLogout(): void {
  localStorage.removeItem('pronto-user');
  showNotLoggedInView();
  updateHeaderAvatar(null);
}

function updateHeaderAvatar(user: ProntoUser | null): void {
  const headerAvatar = document.querySelector<HTMLImageElement>('.header-btn.profile-btn .header-btn-icon img, .profile-btn img');
  if (!headerAvatar) return;

  if (user && user.avatar) {
    headerAvatar.src = user.avatar;
  } else {
    // Default avatar
    headerAvatar.src = '/static/images/default-avatar.png'; // Or some dummy data URL
  }
}

function hydrateHeaderAvatarFromStorage(): void {
  const user = getCurrentUser();
  updateHeaderAvatar(user);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function calculatePasswordStrength(password: string): { level: 'weak' | 'medium' | 'strong'; score: number } {
  let score = 0;
  if (password.length >= 6) score += 1;
  if (password.length >= 10) score += 1;
  if (/\d/.test(password)) score += 1;
  if (/[A-Z]/.test(password)) score += 1;
  if (/[^A-Za-z0-9]/.test(password)) score += 1;

  if (score <= 2) return { level: 'weak', score };
  if (score <= 4) return { level: 'medium', score };
  return { level: 'strong', score };
}

// Remaining stubs...
function setupSupportModal(): void { }
function setupTermsCheckbox(): void {
  const termsCheckbox = document.getElementById('accept-terms') as HTMLInputElement | null;
  termsCheckbox?.addEventListener('change', () => {
    updateRegisterButtonState();
  });
}

function setupPasswordRecovery(): void { }
function setupOrderHistory(): void { }
function openSupportModal(): void { }
function closeSupportModal(): void { }
function openPasswordRecovery(): void { }
function openOrderHistory(): void { }
