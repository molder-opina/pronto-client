(function (global) {
    class ProntoRealtime {
        constructor(options = {}) {
            this.endpoint = options.endpoint || '/api/realtime/events';
            this.intervalMs = Number(options.intervalMs || 1000);
            this.afterId = '0-0';
            this.subscribers = new Set();
            this.isRunning = false;
            this.timer = null;
        }

        subscribe(callback) {
            if (typeof callback !== 'function') {
                return () => {};
            }

            this.subscribers.add(callback);
            this._ensureRunning();

            return () => {
                this.subscribers.delete(callback);
                if (this.subscribers.size === 0) {
                    this._stop();
                }
            };
        }

        _ensureRunning() {
            if (this.isRunning || this.subscribers.size === 0) {
                return;
            }
            this.isRunning = true;
            this._schedulePoll(0);
        }

        _schedulePoll(delay) {
            if (!this.isRunning) {
                return;
            }

            if (this.timer) {
                clearTimeout(this.timer);
            }

            this.timer = window.setTimeout(() => this._poll(), delay);
        }

        async _poll() {
            if (!this.isRunning) {
                return;
            }

            const url = new URL(this.endpoint, window.location.origin);
            url.searchParams.set('after_id', this.afterId);

            try {
                const response = await fetch(url.toString(), {
                    credentials: 'include',
                    headers: {
                        'Accept': 'application/json'
                    }
                });

                if (!response.ok) {
                    if (response.status === 401 || response.status === 403) {
                        this._emit({ type: 'realtime.auth_error', payload: {} });
                        this._schedulePoll(this.intervalMs * 2);
                        return;
                    }
                    throw new Error(`Realtime polling failed with status ${response.status}`);
                }

                const data = await response.json();

                if (data.last_id) {
                    this.afterId = data.last_id;
                }

                if (Array.isArray(data.events)) {
                    data.events.forEach((event) => this._emit(event));
                }

                this._schedulePoll(this.intervalMs);
            } catch (error) {
                console.warn('[Realtime] Error while fetching events:', error);
                this._schedulePoll(this.intervalMs * 2);
            }
        }

        _emit(event) {
            if (!event) return;
            this.subscribers.forEach((callback) => {
                try {
                    callback(event);
                } catch (error) {
                    console.warn('[Realtime] Subscriber threw an error:', error);
                }
            });
        }

        _stop() {
            this.isRunning = false;
            if (this.timer) {
                clearTimeout(this.timer);
                this.timer = null;
            }
        }
    }

    const endpoint = global.REALTIME_EVENTS_ENDPOINT || '/api/realtime/events';
    const intervalMs = Number(
        global.REALTIME_POLL_INTERVAL_MS ||
        (global.APP_SETTINGS && global.APP_SETTINGS.realtime_poll_interval_ms) ||
        1000
    );

    global.ProntoRealtime = new ProntoRealtime({ endpoint, intervalMs });
})(window);
