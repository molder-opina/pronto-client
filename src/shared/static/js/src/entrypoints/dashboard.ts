import '../index.css';
import { bootstrapModule } from '../core/bootstrap';
import { initOrdersBoard } from '../modules/orders-board';
import { initPaymentsFlow } from '../modules/payments-flow';
import { initMenuManager } from '../modules/menu-manager';
import { initModifiersManager } from '../modules/modifiers-manager';
import { initAreasManager } from '../modules/areas-manager';
import { initTablesManager } from '../modules/tables-manager';
import { initConfigManager } from '../modules/config-manager';
import { initPromotionsManager } from '../modules/promotions-manager';
import { initRecommendationsManager } from '../modules/recommendations-manager';
import { initReportsManager } from '../modules/reports-manager';
import { initCustomersManager } from '../modules/customers-manager';
import { initRoleManagement } from '../modules/role-management';
import { initSessionsManager } from '../modules/sessions-manager';
import { initPrepTimesManager } from '../modules/prep-times-manager';
import { initProductSchedulesManager } from '../modules/product-schedules-manager';
import { initDashboardShortcuts } from '../modules/dashboard-shortcuts';
import { initAnonymousSessionsManager } from '../modules/anonymous-sessions-manager';
import { initWaiterBoard } from '../modules/waiter-board';
import { initKitchenBoard } from '../modules/kitchen-board';
import { initTableAssignment } from '../modules/table-assignment';
import { initCashierBoard } from '../modules/cashier-board';
import { initEmployeeEvents } from '../modules/employee-events';

bootstrapModule('[data-orders-board-root]', (root) => {
    initOrdersBoard(root);
}, { name: 'orders-board' });

bootstrapModule('[data-waiter-root]', (root) => {
    initWaiterBoard(root);
}, { name: 'waiter-board' });

bootstrapModule('[data-kitchen-root]', (root) => {
    initKitchenBoard(root);
}, { name: 'kitchen-board' });

bootstrapModule('[data-cashier-root]', (root) => {
    initCashierBoard(root);
}, { name: 'cashier-board' });

initPaymentsFlow();
initMenuManager();
initModifiersManager();
initAreasManager();
initTablesManager();
initConfigManager();
initPromotionsManager();
initRecommendationsManager();
initReportsManager();
initCustomersManager();
initRoleManagement();
initSessionsManager();
initPrepTimesManager();
initProductSchedulesManager();
initDashboardShortcuts();
initAnonymousSessionsManager();
initTableAssignment();
initEmployeeEvents();

// Expose unified refreshOrders function for realtime updates
(window as any).refreshOrders = () => {
    if (typeof (window as any).refreshWaiterOrders === 'function') {
        (window as any).refreshWaiterOrders();
    }
    if (typeof (window as any).refreshKitchenOrders === 'function') {
        (window as any).refreshKitchenOrders();
    }
};

// Vue Components Mounting
import { createApp } from 'vue';
// @ts-expect-error Vue component import
import EmployeesManager from '../components/EmployeesManager.vue';

const employeesRoot = document.getElementById('employees-table');
if (employeesRoot) {
    console.log('Mounting Vue EmployeesManager...');
    // Replace legacy container content
    const appContainer = document.createElement('div');
    employeesRoot.innerHTML = '';
    employeesRoot.appendChild(appContainer);

    // Mount Vue App
    createApp(EmployeesManager).mount(appContainer);
}
