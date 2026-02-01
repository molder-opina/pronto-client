import { isAnonymousSession, redirectAfterPayment } from './session-cleanup';

interface FeedbackQuestion {
    id: number;
    question_text: string;
    question_type: string;
    category?: string;
    is_required: boolean;
    min_rating: number;
    max_rating: number;
}

type FeedbackModalAction = 'open-feedback' | 'close-session' | null;

class PostPaymentFeedbackFlow {
    private modal: HTMLElement | null = null;
    private timer: number | null = null;
    private sessionId: number | null = null;
    private timeLeft = 5;
    private action: FeedbackModalAction = null;
    private isAnonymous = true;

    constructor() {
        this.createModal();
    }

    async show(sessionId: number, isAnonymous?: boolean): Promise<FeedbackModalAction> {
        this.sessionId = sessionId;
        this.timeLeft = 5;
        this.action = null;
        this.isAnonymous = isAnonymous ?? isAnonymousSession();

        if (this.modal) {
            this.modal.style.display = 'flex';
            this.startTimer();
        }

        return new Promise((resolve) => {
            const checkAction = setInterval(() => {
                if (this.action !== null) {
                    clearInterval(checkAction);
                    this.hideModal();
                    resolve(this.action);
                }
            }, 100);
        });
    }

    private createModal(): void {
        if (document.getElementById('post-payment-feedback-modal')) return;

        this.modal = document.createElement('div');
        this.modal.id = 'post-payment-feedback-modal';
        this.modal.className = 'post-payment-feedback-modal';
        this.modal.innerHTML = `
            <div class="post-payment-feedback-content">
                <div class="feedback-icon-wrapper">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                        <circle cx="12" cy="7" r="4"></circle>
                    </svg>
                </div>
                <h2>¡Pago completado!</h2>
                <p>¿Te gustaría evaluar tu experiencia?</p>
                <div class="feedback-timer">
                    Cerrando en <span id="feedback-timer-count">${this.timeLeft}</span> segundos...
                </div>
                <div class="feedback-actions">
                    <button class="btn btn-secondary" id="skip-feedback-btn">
                        No, gracias
                    </button>
                    <button class="btn btn-primary" id="open-feedback-btn">
                        Evaluar servicio
                    </button>
                </div>
            </div>
        `;
        document.body.appendChild(this.modal);

        const skipBtn = document.getElementById('skip-feedback-btn');
        const openBtn = document.getElementById('open-feedback-btn');

        skipBtn?.addEventListener('click', () => {
            this.action = 'close-session';
        });

        openBtn?.addEventListener('click', () => {
            this.action = 'open-feedback';
        });
    }

    private startTimer(): void {
        const timerElement = document.getElementById('feedback-timer-count');
        this.timeLeft = 5;

        if (timerElement) {
            timerElement.textContent = String(this.timeLeft);
        }

        this.timer = window.setInterval(() => {
            this.timeLeft--;

            if (timerElement) {
                timerElement.textContent = String(this.timeLeft);
            }

            if (this.timeLeft <= 0) {
                this.stopTimer();
                this.action = 'close-session';
                // Execute cleanup based on session type
                redirectAfterPayment(this.isAnonymous);
            }
        }, 1000);
    }

    private stopTimer(): void {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }

    private hideModal(): void {
        this.stopTimer();
        if (this.modal) {
            this.modal.style.display = 'none';
        }
    }
}

let feedbackFlow: PostPaymentFeedbackFlow | null = null;

export function showPostPaymentFeedbackModal(sessionId: number, isAnonymous?: boolean): Promise<FeedbackModalAction> {
    if (!feedbackFlow) {
        feedbackFlow = new PostPaymentFeedbackFlow();
    }
    return feedbackFlow.show(sessionId, isAnonymous);
}

export function initializePostPaymentFeedback(): void {
    console.log('[post-payment-feedback] Module initialized');
}
