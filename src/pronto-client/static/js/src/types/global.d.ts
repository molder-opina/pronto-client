export { };

declare global {
  interface Window {
    APP_CONFIG: {
      static_host_url: string;
      restaurant_assets: string;
      currency_code: string;
      currency_symbol: string;
    };
    APP_SETTINGS?: {
      currency_code?: string;
      currency_symbol?: string;
      currency_locale?: string;
      checkout_default_method?: string;
      checkout_prompt_duration_seconds?: number;
      payment_confirmed_duration_seconds?: number;
      default_country_code?: string;
      phone_country_options?: Array<{
        iso: string;
        label: string;
        dial_code: string;
        flag?: string;
      }>;
    };
    showNotification?: (message: string, type?: 'success' | 'error' | 'warning' | 'info') => void;
    GlobalLoading?: {
      start: () => void;
      stop: () => void;
    };
    __PRONTO_TS_CLIENT_BASE__?: boolean;
    __PRONTO_TS_MENU__?: boolean;
    __PRONTO_TS_MENU_SHORTCUTS__?: boolean;
    __PRONTO_TS_THANK_YOU__?: boolean;
    keyboardShortcuts?: {
      register: (
        combo: string,
        config: {
          description: string;
          category: string;
          callback: () => void;
          preventDefault?: boolean;
        }
      ) => void;
    };
    THANK_YOU_DATA?: any;
    NotificationManager?: new (url: string) => {
      connect: () => void;
      on: (event: string, callback: (payload: any) => void) => void;
    };
    Stripe?: (publishableKey: string) => any;
    ThankYouPage?: any;
    callWaiter?: () => void;
    formatCurrency?: (value: number, options?: { locale?: string; currency?: string }) => string;
    getSessionId?: () => number | null;
    setSessionId?: (sessionId: number) => void;
    clearSessionId?: () => void;
    createConfetti?: () => void;
    toggleCart?: () => void;
    proceedToCheckout?: () => void;
    backToMenu?: () => void;
    openItemModal?: (itemId: number) => void;
    openProductModal?: (itemId: number) => void;
    closeItemModal?: () => void;
    adjustModalQuantity?: (delta: number) => void;
    addToCartFromModal?: () => void;
    updateCartItemQuantity?: (index: number, delta: number) => void;
    quickAdd?: (event: Event, itemId: number) => void;
    handleModifierChange?: (
      groupId: number,
      modifierId: number,
      maxSelection: number,
      checked: boolean,
      input?: HTMLInputElement | null,
      isSingle?: boolean
    ) => boolean | void;
    requestCheckoutFromTracker?: () => void;
    cancelPendingOrder?: () => void;
    viewFullTracker?: () => void;
    refreshMiniTracker?: () => void;
    switchView?: (view: string) => void;
    resetFilters?: () => void;
    ProntoTableCode?: {
      buildTableCode: (areaCode: string, tableNumber: number) => string;
      validateTableCode: (code: string, raiseError?: boolean) => boolean;
      parseTableCode: (
        code: string
      ) => { areaCode: string; tableNumber: number; code: string } | null;
      deriveAreaCodeFromLabel: (label?: string | null, fallback?: string) => string;
    };
    // Cart persistence functions
    getCartItems?: () => any[];
    addToCart?: (item: any) => void;
    clearCart?: () => void;
    getCartCount?: () => number;
    getCartTotal?: () => number;
    isCartEmpty?: () => boolean;
    checkActiveOrders?: () => void;
    showModal?: (title: string, content: string) => void;
    APP_SESSION?: {
      customer?: {
        name?: string;
        email?: string;
        phone?: string;
      };
    };
    getOrCreateAnonymousClientId?: () => string | null | undefined;
    ensureAnonymousClientId?: () => string | null | undefined;
    getAnonymousClientId?: () => string | null | undefined;
  }

  // Common interfaces used across modules
  interface CheckoutSessionSummary {
    id: number;
    total_amount: number;
    table_number?: string | null;
    status: string;
    created_at?: string;
    notes?: string;
    totals?: {
      total_amount: number;
      subtotal?: number;
      tax?: number;
    };
    table?: {
      table_number: string;
    };
  }
}
