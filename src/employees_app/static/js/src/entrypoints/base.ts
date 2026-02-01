import { initRealtimeGlobal } from '../core/realtime';
import { exposeNotificationManager } from '../core/notifications';
import { showToastGlobal } from '../core/toast';
import { playNotificationSound } from '../core/audio';
import { initGlobalEscapeToCloseOverlays } from '../core/overlays';
import { getCapabilitiesForRole, normalizeRole } from '../modules/role-context';
import { initDraggableModals } from '../modules/draggable-modals';
// Activar interceptor de autenticación para redirigir automáticamente al login cuando la sesión expira
import '../core/auth-interceptor';
import { createIcons, icons } from 'lucide/dist/umd/lucide.js';

initRealtimeGlobal();
exposeNotificationManager();
initGlobalEscapeToCloseOverlays();
initDraggableModals();

declare global {
  interface Window {
    showToast?: (message: string, type?: 'info' | 'success' | 'warning' | 'error') => void;
    playEmployeeNotificationSound?: (urgent?: boolean) => void;
    Lucide?: {
      createIcons: typeof createIcons;
      icons: typeof icons;
    };
  }
}

// Expose Lucide globally
window.Lucide = {
  createIcons,
  icons
};

window.showToast = (message, type = 'info') => showToastGlobal(message, type);
window.playEmployeeNotificationSound = (urgent = false) => playNotificationSound(urgent);

const currentRole = window.APP_DATA?.employee_role;
const normalizedRole = normalizeRole(currentRole);

if (window.APP_DATA) {
  window.APP_DATA.normalized_role = normalizedRole;
  window.APP_DATA.role_capabilities = getCapabilitiesForRole(currentRole);
}
