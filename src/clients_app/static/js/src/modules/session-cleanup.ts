/**
 * Session Cleanup Module
 * 
 * Handles cleanup of client sessions after payment completion.
 * Differentiates between anonymous sessions (no JWT) and logged-in sessions (with JWT).
 */

/**
 * Check if the user has a JWT token (is logged in)
 * @returns true if user has JWT, false if anonymous
 */
export function isLoggedInUser(): boolean {
  if (typeof document === 'undefined') {
    return false;
  }
  
  const cookies = document.cookie.split(';');
  return cookies.some(cookie => {
    const [name] = cookie.trim().split('=');
    return name === 'access_token' || name === 'jwt_access_token';
  });
}

/**
 * Check if the current session is anonymous (no JWT)
 * @returns true if anonymous session
 */
export function isAnonymousSession(): boolean {
  return !isLoggedInUser();
}

/**
 * Clear anonymous session data from storage
 * Removes all client-side data associated with anonymous users
 */
export function clearAnonymousSession(): void {
  if (typeof localStorage === 'undefined') {
    return;
  }
  
  // Clear anonymous client ID
  localStorage.removeItem('pronto-anonymous-client-id');
  localStorage.removeItem('anon_id');
  
  // Clear cart data
  localStorage.removeItem('pronto-cart');
  localStorage.removeItem('pronto-cart-draft');
  
  // Clear session storage
  if (typeof sessionStorage !== 'undefined') {
    sessionStorage.removeItem('pronto-session-data');
    sessionStorage.removeItem('pronto-table-number');
    sessionStorage.removeItem('pronto-table-label');
    sessionStorage.removeItem('pronto-checkout-draft');
  }
  
  // Clear any draft data
  localStorage.removeItem('pronto-menu-draft');
  localStorage.removeItem('pronto-order-draft');
  
  console.log('[session-cleanup] Anonymous session cleared');
}

/**
 * Clear user session data from storage
 * Only removes cart data, keeps user session data intact
 */
export function clearUserSession(): void {
  if (typeof localStorage === 'undefined') {
    return;
  }
  
  // Clear cart data only
  localStorage.removeItem('pronto-cart');
  localStorage.removeItem('pronto-cart-draft');
  
  // Clear session storage (keep table info if needed)
  if (typeof sessionStorage !== 'undefined') {
    sessionStorage.removeItem('pronto-checkout-draft');
    sessionStorage.removeItem('pronto-session-data');
  }
  
  // Clear draft data
  localStorage.removeItem('pronto-menu-draft');
  localStorage.removeItem('pronto-order-draft');
  
  console.log('[session-cleanup] User session cleared (cart only)');
}

/**
 * Clear all session data based on session type
 * @param isAnonymous - true for anonymous session, false for logged-in user
 */
export function clearSessionByType(isAnonymous: boolean): void {
  if (isAnonymous) {
    clearAnonymousSession();
  } else {
    clearUserSession();
  }
}

/**
 * Redirect user after payment based on session type
 * @param isAnonymous - true for anonymous session, false for logged-in user
 */
export function redirectAfterPayment(isAnonymous: boolean): void {
  if (isAnonymous) {
    // Anonymous users: clear all data and go to home page
    clearAnonymousSession();
    window.location.href = '/';
  } else {
    // Logged-in users: clear cart, go to orders page
    clearUserSession();
    window.location.href = '/?tab=orders&cleared=true';
  }
}

/**
 * Execute cleanup and redirect for post-payment feedback flow
 * @param isAnonymous - true for anonymous session, false for logged-in user
 */
export function executePostPaymentCleanup(isAnonymous: boolean): void {
  redirectAfterPayment(isAnonymous);
}

// Export for use in other modules
export default {
  isLoggedInUser,
  isAnonymousSession,
  clearAnonymousSession,
  clearUserSession,
  clearSessionByType,
  redirectAfterPayment,
  executePostPaymentCleanup
};
