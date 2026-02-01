(function () {
    const LoadingController = (() => {
        let overlay = null;
        let pending = 0;

        const ensureOverlay = () => {
            if (!overlay) {
                overlay = document.getElementById('global-loading');
            }
            return overlay;
        };

        const showOverlay = () => {
            const el = ensureOverlay();
            if (!el) return;
            if (!el.classList.contains('visible')) {
                requestAnimationFrame(() => el.classList.add('visible'));
            }
        };

        const hideOverlay = () => {
            const el = ensureOverlay();
            if (!el) return;
            if (el.classList.contains('visible')) {
                requestAnimationFrame(() => el.classList.remove('visible'));
            }
        };

        return {
            start() {
                pending += 1;
                showOverlay();
            },
            stop() {
                pending = Math.max(0, pending - 1);
                if (pending === 0) {
                    hideOverlay();
                }
            }
        };
    })();

    function wrapFetch() {
        if (typeof window.fetch !== "function") {
            return;
        }
        const originalFetch = window.fetch.bind(window);
        window.fetch = (resource, init = undefined) => {
            const options = init ? { ...init } : undefined;
            let showLoading = false;
            if (options && Object.prototype.hasOwnProperty.call(options, "showLoading")) {
                showLoading = Boolean(options.showLoading);
                delete options.showLoading;
            } else {
                const method = (options?.method || "GET").toUpperCase();
                showLoading = method !== "GET";
            }

            if (showLoading) {
                LoadingController.start();
            }

            const finalize = () => {
                if (showLoading) {
                    LoadingController.stop();
                }
            };

            return originalFetch(resource, options)
                .then((response) => {
                    finalize();
                    return response;
                })
                .catch((error) => {
                    finalize();
                    throw error;
                });
        };
    }

    window.EmployeeLoading = {
        start: () => LoadingController.start(),
        stop: () => LoadingController.stop()
    };

    if (!window.GlobalLoading) {
        window.GlobalLoading = window.EmployeeLoading;
    }

    wrapFetch();
})();
