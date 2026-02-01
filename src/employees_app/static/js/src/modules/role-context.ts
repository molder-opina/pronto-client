type RoleKey = 'waiter' | 'cashier' | 'chef' | 'admin' | 'guest';

export interface RoleCapabilities {
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
}

interface RoleTheme {
    primary: string;
    hover: string;
    accent: string;
    contrast: string;
}

const ROLE_CAPABILITIES: Record<RoleKey, RoleCapabilities> = {
    waiter: {
        canCharge: false,
        canReprint: false,
        canCancel: true,
        canEditOrder: true,
        canMoveTable: true,
        canAdvanceKitchen: false,
        canDiscount: false,
        canReopen: false,
        canCommandItems: true,
        canViewPaid: true,
        canViewActive: true
    },
    cashier: {
        canCharge: true,
        canReprint: true,
        canCancel: false,
        canEditOrder: false,
        canMoveTable: false,
        canAdvanceKitchen: false,
        canDiscount: false,
        canReopen: false,
        canCommandItems: false,
        canViewPaid: true,
        canViewActive: true
    },
    chef: {
        canCharge: false,
        canReprint: false,
        canCancel: false,
        canEditOrder: false,
        canMoveTable: false,
        canAdvanceKitchen: true,
        canDiscount: false,
        canReopen: false,
        canCommandItems: false,
        canViewPaid: false,
        canViewActive: true
    },
    admin: {
        canCharge: true,
        canReprint: true,
        canCancel: true,
        canEditOrder: true,
        canMoveTable: true,
        canAdvanceKitchen: true,
        canDiscount: true,
        canReopen: true,
        canCommandItems: true,
        canViewPaid: true,
        canViewActive: true
    },
    guest: {
        canCharge: false,
        canReprint: false,
        canCancel: false,
        canEditOrder: false,
        canMoveTable: false,
        canAdvanceKitchen: false,
        canDiscount: false,
        canReopen: false,
        canCommandItems: false,
        canViewPaid: false,
        canViewActive: false
    }
};

const ROLE_THEMES: Record<RoleKey, RoleTheme> = {
    waiter: { primary: '#F57C00', hover: '#FFA040', accent: '#FFCC80', contrast: '#FFFFFF' },
    cashier: { primary: '#2E7D32', hover: '#43A047', accent: '#A5D6A7', contrast: '#FFFFFF' },
    chef: { primary: '#1565C0', hover: '#1E88E5', accent: '#90CAF9', contrast: '#FFFFFF' },
    admin: { primary: '#263238', hover: '#37474F', accent: '#B0BEC5', contrast: '#FFFFFF' },
    guest: { primary: '#6B7280', hover: '#4B5563', accent: '#E5E7EB', contrast: '#FFFFFF' }
};

function mapToRoleKey(role?: string | null): RoleKey {
    if (!role) return 'guest';
    const normalized = role.toLowerCase();
    if (['super_admin', 'admin_roles', 'manager', 'admin'].includes(normalized)) return 'admin';
    if (['chef', 'cook'].includes(normalized)) return 'chef';
    if (normalized === 'cashier') return 'cashier';
    if (normalized === 'waiter') return 'waiter';
    return 'guest';
}

export function normalizeRole(role?: string | null): RoleKey {
    return mapToRoleKey(role);
}

export function getCapabilitiesForRole(role?: string | null): RoleCapabilities {
    const key = mapToRoleKey(role);
    return ROLE_CAPABILITIES[key];
}

export function applyRoleTheme(role?: string | null): void {
    const key = mapToRoleKey(role);
    const theme = ROLE_THEMES[key] || ROLE_THEMES.guest;
    const root = document.documentElement;
    root.setAttribute('data-role-theme', key);
    Object.entries(theme).forEach(([token, value]) => {
        root.style.setProperty(`--role-${token}`, value);
    });
}

export function getRoleTheme(role?: string | null): RoleTheme {
    const key = mapToRoleKey(role);
    return ROLE_THEMES[key];
}

export function normalizeBackendCapabilities(backendData: any): RoleCapabilities | null {
    if (!backendData || !backendData.capabilities) {
        return null;
    }
    const caps = backendData.capabilities;
    return {
        canCharge: Boolean(caps.payments?.process),
        canReprint: Boolean(caps.payments?.view),
        canCancel: Boolean(caps.orders?.cancel),
        canEditOrder: Boolean(caps.orders?.modify),
        canMoveTable: Boolean(caps.tables?.edit),
        canAdvanceKitchen: Boolean(caps.kitchen?.start || caps.kitchen?.complete),
        canDiscount: Boolean(caps.payments?.process),
        canReopen: Boolean(caps.orders?.modify),
        canCommandItems: Boolean(caps.orders?.modify),
        canViewPaid: Boolean(caps.orders?.view),
        canViewActive: Boolean(caps.orders?.view)
    };
}
