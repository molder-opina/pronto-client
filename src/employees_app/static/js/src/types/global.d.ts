export { };

declare global {
    type AppRoleCapabilities = {
        canCharge: boolean;
        canReprint: boolean;
        canCancel: boolean;
        canEditOrder: boolean;
        canMoveTable: boolean;
        canAdvanceKitchen: boolean;
        canDiscount: boolean;
        canReopen: boolean;
        canCommandItems: boolean;
        canViewPaid: boolean;
        canViewActive: boolean;
    };

    interface Window {
        APP_CONFIG?: {
            static_host_url: string;
            restaurant_assets: string;
            items_per_page: number;
        };
        APP_DATA?: {
            employee_id?: number;
            employee_role?: string;
            employee_name?: string;
            can_process_payments?: boolean;
            day_periods?: Array<Record<string, any>>;
            paid_orders_retention_minutes?: number;
            payment_action_delay_seconds?: number;
            table_base_prefix?: string;
            role_capabilities?: AppRoleCapabilities;
            normalized_role?: string;
        };
        SESSIONS_STATE?: Record<number, { id: number; status: string }>;
        showToast?: (message: string, type?: 'info' | 'success' | 'warning' | 'error') => void;
        __PRONTO_TS_ORDERS_BOARD__?: boolean;
        __PRONTO_TS_WAITER__?: boolean;
        __PRONTO_TS_KITCHEN__?: boolean;
        __PRONTO_TS_PAYMENTS__?: boolean;
        __PRONTO_TS_CATALOG__?: boolean;
        __PRONTO_TS_MODIFIERS__?: boolean;
        __PRONTO_TS_AREAS__?: boolean;
        __PRONTO_TS_TABLES__?: boolean;
        __PRONTO_TS_CONFIG__?: boolean;
        __PRONTO_TS_PROMOTIONS__?: boolean;
        __PRONTO_TS_RECOMMENDATIONS__?: boolean;
        __PRONTO_TS_REPORTS__?: boolean;
        __PRONTO_TS_CUSTOMERS__?: boolean;
        __PRONTO_TS_EMPLOYEE_EVENTS__?: boolean;
        __PRONTO_TS_ROLES__?: boolean;
        __PRONTO_TS_SESSIONS__?: boolean;
        __PRONTO_TS_PREP_TIMES__?: boolean;
        __PRONTO_TS_SCHEDULES__?: boolean;
        WAITER_ORDERS_DATA?: Array<Record<string, any>>;
        CASHIER_ORDERS_DATA?: Array<Record<string, any>>;
        KITCHEN_ORDERS_DATA?: Array<Record<string, any>>;
        refreshCashierOrders?: () => Promise<void>;
        WaiterPanel?: {
            confirmWaiterCall?: (callId: number) => void;
            toggleNotificationsPanel?: () => void;
            getPendingCalls?: () => Array<Record<string, unknown>>;
        };
        KitchenPanel?: {
            initialize?: (orders: Array<Record<string, any>>) => void;
        };
        LegacyMenu?: {
            openProductDrawer?: (mode: string, product?: Record<string, any>) => void;
            toggleProductAvailability?: (productId: number, isAvailable: boolean) => void;
            onCategoriesUpdated?: (categories: Array<Record<string, any>>) => void;
        };
        EmployeePayments?: {
            openModal?: (sessionId: number, method?: string) => void;
            printTicket?: (sessionId: number) => void;
        };
        EmployeeBell?: {
            setState?: (state: string) => void;
            setCount?: (count: number) => void;
        };
        io?: (...args: any[]) => any;
        NotificationManager?: new (streamUrl: string) => any;
        ProntoRealtime?: {
            subscribe: (callback: (event: any) => void) => () => void;
        };
        ProntoAreas?: {
            reload: () => Promise<void>;
            getAreas: () => Array<Record<string, any>>;
        };
        EmployeeLoading?: {
            start?: () => void;
            stop?: () => void;
        };
        GlobalLoading?: {
            start?: () => void;
            stop?: () => void;
        };
        editTable?: (tableId: number) => void;
        deleteTable?: (tableId: number) => void;
        TablesManager?: {
            reload: () => Promise<void>;
        };
        ProntoConfig?: {
            reload: () => Promise<void>;
        };
        ProntoPromotions?: {
            reload: () => Promise<void>;
        };
        ProntoRecommendations?: {
            reload: () => Promise<void>;
        };
        ProntoTableCode?: {
            buildTableCode: (areaCode: string, tableNumber: number) => string;
            validateTableCode: (code: string, raiseError?: boolean) => boolean;
            parseTableCode: (code: string) => { areaCode: string; tableNumber: number; code: string } | null;
            deriveAreaCodeFromLabel: (label?: string | null, fallback?: string) => string;
        };
        PaginationManager?: new (options: {
            container: HTMLElement;
            itemsPerPage?: number;
            onPageChange?: () => void;
            labels?: Record<string, string>;
        }) => {
            update: (total: number, resetToFirstPage?: boolean) => void;
            getCurrentPageData: <T>(items: T[]) => T[];
            register: () => void;
        };
        paginationInstances?: Record<string, unknown>;
        openAddRecommendationModal?: (periodKey: string) => void;
        selectRecommendationProduct?: (itemId: number) => void;
        removeRecommendation?: (itemId: number, periodKey: string) => void;
        filterRecommendationsByCategory?: (category: string) => void;
        closeSelectRecommendationModal?: () => void;
        openCustomerDetail?: (customerId: number) => void;
        closeCustomerDetail?: () => void;
        openEmployeePaymentModal?: (sessionId: string | number, method: string) => void;
        printTicket?: (sessionId: string | number) => Promise<void>;
        ProntoSessions?: {
            loadPendingSessions?: () => Promise<void>;
            loadClosedSessions?: () => Promise<void>;
        };
        ProntoPrepTimes?: {
            reload: () => Promise<void>;
            savePrepTime: (itemId: number) => Promise<void>;
        };
        updatePrepTime?: (itemId: number) => void;
        ProntoSchedules?: {
            initialize: () => Promise<void>;
            deleteSchedule: (scheduleId: number) => Promise<void>;
        };
        deleteSchedule?: (scheduleId: number) => void;
    }
}
