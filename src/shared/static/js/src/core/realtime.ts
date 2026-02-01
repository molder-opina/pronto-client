interface RealtimeEvent {
    type?: string;
    payload?: Record<string, unknown>;
    [key: string]: any;
}

type Subscriber = (event: RealtimeEvent) => void;

export class RealtimeClient {
    private endpoint: string;
    private intervalMs: number;
    private afterId = '0-0';
    private subscribers = new Set<Subscriber>();
    private isRunning = false;
    private timer: number | null = null;
    private static STORAGE_KEY = 'pronto_realtime_after_id';

    constructor(endpoint: string, intervalMs: number) {
        this.endpoint = endpoint;
        this.intervalMs = intervalMs;
        // Restore last known position from sessionStorage
        this.restorePosition();
    }

    private restorePosition(): void {
        try {
            const stored = sessionStorage.getItem(RealtimeClient.STORAGE_KEY);
            const storedTimestamp = sessionStorage.getItem(RealtimeClient.STORAGE_KEY + '_ts');
            const now = Date.now();

            // If we have a stored ID and it's not too old (less than 5 minutes), use it
            if (stored && stored !== '0-0' && storedTimestamp) {
                const age = now - parseInt(storedTimestamp, 10);
                if (age < 5 * 60 * 1000) { // 5 minutes
                    this.afterId = stored;
                    return;
                }
            }
            // Fresh session or stale data: skip initial events to avoid showing old notifications
            this.skipInitialEvents = true;
        } catch {
            // sessionStorage not available
            this.skipInitialEvents = true;
        }
    }

    private skipInitialEvents = false;

    private persistPosition(): void {
        try {
            sessionStorage.setItem(RealtimeClient.STORAGE_KEY, this.afterId);
            sessionStorage.setItem(RealtimeClient.STORAGE_KEY + '_ts', String(Date.now()));
        } catch {
            // sessionStorage not available
        }
    }

    subscribe(callback: Subscriber): () => void {
        if (typeof callback !== 'function') {
            return () => {};
        }
        this.subscribers.add(callback);
        this.ensureRunning();
        return () => {
            this.subscribers.delete(callback);
            if (this.subscribers.size === 0) {
                this.stop();
            }
        };
    }

    private ensureRunning(): void {
        if (this.isRunning || this.subscribers.size === 0) {
            return;
        }
        this.isRunning = true;
        this.schedulePoll(0);
    }

    private schedulePoll(delay: number): void {
        if (!this.isRunning) {
            return;
        }
        if (this.timer) {
            window.clearTimeout(this.timer);
        }
        this.timer = window.setTimeout(() => {
            void this.poll();
        }, delay);
    }

    private async poll(): Promise<void> {
        if (!this.isRunning) {
            return;
        }
        const url = new URL(this.endpoint, window.location.origin);
        url.searchParams.set('after_id', this.afterId);
        try {
            const response = await fetch(url.toString(), {
                credentials: 'include',
                headers: { Accept: 'application/json' }
            });
            if (!response.ok) {
                if (response.status === 401 || response.status === 403) {
                    this.emit({ type: 'realtime.auth_error', payload: {} });
                    this.schedulePoll(this.intervalMs * 2);
                    return;
                }
                throw new Error(`Realtime polling failed with status ${response.status}`);
            }
            const data = await response.json();
            if (data.last_id) {
                this.afterId = data.last_id;
                this.persistPosition();
            }
            // On fresh session, skip emitting initial events to avoid old notifications
            if (this.skipInitialEvents) {
                this.skipInitialEvents = false;
                this.schedulePoll(this.intervalMs);
                return;
            }
            if (Array.isArray(data.events)) {
                data.events.forEach((event: RealtimeEvent) => this.emit(event));
            }
            this.schedulePoll(this.intervalMs);
        } catch (error) {
            console.warn('[Realtime] Error while fetching events:', error);
            this.schedulePoll(this.intervalMs * 2);
        }
    }

    private emit(event: RealtimeEvent): void {
        if (!event) return;
        this.subscribers.forEach((callback) => {
            try {
                callback(event);
            } catch (error) {
                console.warn('[Realtime] Subscriber threw an error:', error);
            }
        });
    }

    private stop(): void {
        this.isRunning = false;
        if (this.timer) {
            window.clearTimeout(this.timer);
            this.timer = null;
        }
    }
}

export function initRealtimeGlobal(): void {
    const endpoint = window.REALTIME_EVENTS_ENDPOINT || '/api/realtime/events';
    const interval = Number(
        window.REALTIME_POLL_INTERVAL_MS ||
        (window.APP_SETTINGS && window.APP_SETTINGS.realtime_poll_interval_ms) ||
        1000
    );
    const client = new RealtimeClient(endpoint, interval);
    window.ProntoRealtime = client;
}
