/**
 * Waiter Sounds Module
 * Handles notification sound playback with different sound types
 */

export type SoundType = 'bell' | 'chime' | 'beep' | 'ding' | 'pop';

export class WaiterSoundManager {
    private soundType: SoundType = 'bell';

    async loadSoundSettings(): Promise<void> {
        try {
            const response = await fetch('/api/settings/public/waiter_notification_sound');
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.value) {
                    this.soundType = data.value as SoundType;
                    console.log('[WAITER] Sonido de notificación configurado:', this.soundType);
                }
            }
        } catch (error) {
            console.log('[WAITER] Error al cargar configuración de sonido, usando default:', error);
        }
    }

    play(): void {
        try {
            const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();

            switch (this.soundType) {
                case 'bell':
                    this.playBell(audioContext);
                    break;
                case 'chime':
                    this.playChime(audioContext);
                    break;
                case 'beep':
                    this.playBeep(audioContext);
                    break;
                case 'ding':
                    this.playDing(audioContext);
                    break;
                case 'pop':
                    this.playPop(audioContext);
                    break;
                default:
                    this.playBell(audioContext);
            }
        } catch (error) {
            console.log('[Audio] No se pudo reproducir el sonido:', error);
        }
    }

    private playBell(audioContext: AudioContext): void {
        // Sonido de campanita usando múltiples osciladores
        // Frecuencias típicas de una campanita: fundamental + armónicos
        const frequencies = [523.25, 659.25, 783.99]; // Do, Mi, Sol (acorde mayor)
        const duration = 0.6;
        const startTime = audioContext.currentTime;

        frequencies.forEach((freq, index) => {
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();

            oscillator.type = 'sine';
            oscillator.frequency.value = freq;

            // Volumen más bajo para los armónicos
            const volume = index === 0 ? 0.4 : 0.2;

            // Envolvente de ataque y decaimiento suave
            gainNode.gain.setValueAtTime(0, startTime);
            gainNode.gain.linearRampToValueAtTime(volume, startTime + 0.05);
            gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + duration);

            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);

            oscillator.start(startTime);
            oscillator.stop(startTime + duration);
        });
    }

    private playChime(audioContext: AudioContext): void {
        // Sonido de carillón más suave y melódico
        const frequencies = [523.25, 659.25, 783.99, 1046.50]; // Do, Mi, Sol, Do (octava superior)
        const duration = 0.8;
        const startTime = audioContext.currentTime;

        frequencies.forEach((freq, index) => {
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();

            oscillator.type = 'sine';
            oscillator.frequency.value = freq;

            // Volumen decreciente para crear efecto de carillón
            const volume = (1 - index * 0.15) * 0.3;
            const delay = index * 0.1; // Escalonado para efecto cascada

            gainNode.gain.setValueAtTime(0, startTime + delay);
            gainNode.gain.linearRampToValueAtTime(volume, startTime + delay + 0.1);
            gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + delay + duration);

            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);

            oscillator.start(startTime + delay);
            oscillator.stop(startTime + delay + duration);
        });
    }

    private playBeep(audioContext: AudioContext): void {
        // Sonido de bip simple y directo
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();

        oscillator.type = 'square';
        oscillator.frequency.value = 800;

        const duration = 0.2;
        const startTime = audioContext.currentTime;

        gainNode.gain.setValueAtTime(0, startTime);
        gainNode.gain.linearRampToValueAtTime(0.3, startTime + 0.01);
        gainNode.gain.linearRampToValueAtTime(0.3, startTime + duration - 0.01);
        gainNode.gain.linearRampToValueAtTime(0, startTime + duration);

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        oscillator.start(startTime);
        oscillator.stop(startTime + duration);
    }

    private playDing(audioContext: AudioContext): void {
        // Sonido de timbre más agudo
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();

        oscillator.type = 'sine';
        oscillator.frequency.value = 1000;

        const duration = 0.3;
        const startTime = audioContext.currentTime;

        gainNode.gain.setValueAtTime(0, startTime);
        gainNode.gain.linearRampToValueAtTime(0.4, startTime + 0.05);
        gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + duration);

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        oscillator.start(startTime);
        oscillator.stop(startTime + duration);
    }

    private playPop(audioContext: AudioContext): void {
        // Sonido pop suave y corto
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();

        oscillator.type = 'sine';
        oscillator.frequency.value = 600;

        const duration = 0.15;
        const startTime = audioContext.currentTime;

        gainNode.gain.setValueAtTime(0, startTime);
        gainNode.gain.linearRampToValueAtTime(0.25, startTime + 0.02);
        gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + duration);

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        oscillator.start(startTime);
        oscillator.stop(startTime + duration);
    }
}
