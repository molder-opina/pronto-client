/**
 * MICRO-ANIMATIONS - JavaScript Utilities
 * Complex animations and interactions
 */

export class MicroAnimations {
  /**
   * Animate number counting
   */
  static countNumber(
    element: HTMLElement,
    from: number,
    to: number,
    duration: number = 500,
    formatter?: (value: number) => string
  ): void {
    const startTime = performance.now();
    const isIncrease = to > from;
    const diff = Math.abs(to - from);

    const animate = (currentTime: number): void => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const easeOutQuart = 1 - Math.pow(1 - progress, 4);
      const current = from + diff * easeOutQuart;

      if (formatter) {
        element.textContent = formatter(current);
      } else {
        element.textContent = Math.round(current).toString();
      }

      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        element.textContent = formatter ? formatter(to) : to.toString();
      }
    };

    requestAnimationFrame(animate);
  }

  /**
   * Create ripple effect on click
   */
  static createRipple(
    event: MouseEvent | TouchEvent,
    options: {
      color?: string;
      scale?: number;
      duration?: number;
    } = {}
  ): void {
    const target = event.currentTarget as HTMLElement;
    if (!target) return;

    const rect = target.getBoundingClientRect();
    const clientX = 'touches' in event ? event.touches[0].clientX : event.clientX;
    const clientY = 'touches' in event ? event.touches[0].clientY : event.clientY;

    const x = clientX - rect.left;
    const y = clientY - rect.top;

    const ripple = document.createElement('span');
    ripple.className = 'ripple-effect__circle';
    ripple.style.left = `${x}px`;
    ripple.style.top = `${y}px`;
    ripple.style.setProperty('--ripple-color', options.color || 'rgba(255, 255, 255, 0.5)');
    ripple.style.setProperty('--ripple-scale', (options.scale || 2.5).toString());

    const existingRipple = target.querySelector('.ripple-effect__circle');
    if (existingRipple) {
      existingRipple.remove();
    }

    target.style.position = 'relative';
    target.style.overflow = 'hidden';
    target.appendChild(ripple);

    const duration = options.duration || 400;
    setTimeout(() => {
      ripple.remove();
    }, duration);
  }

  /**
   * Add button ripple effect listeners
   */
  static initRippleButtons(selector: string = '.ripple-effect'): void {
    document.addEventListener(
      'click',
      (e) => {
        const target = e.target as HTMLElement;
        const button = target.closest(selector) as HTMLElement | null;
        if (!button) return;

        MicroAnimations.createRipple(e as MouseEvent, {
          color: 'rgba(255, 255, 255, 0.4)',
          duration: 300,
        });
      },
      { passive: true }
    );
  }

  /**
   * Animate success checkmark
   */
  static animateSuccess(element: SVGElement): void {
    const paths = element.querySelectorAll('path');
    paths.forEach((path, index) => {
      const length = path.getTotalLength?.() || 24;
      path.style.strokeDasharray = length.toString();
      path.style.strokeDashoffset = length.toString();

      setTimeout(() => {
        path.style.transition = `stroke-dashoffset ${0.3 + index * 0.1}s ease ${index * 0.1}s`;
        path.style.strokeDashoffset = '0';
      }, 50);
    });
  }

  /**
   * Shake element for error feedback
   */
  static shake(element: HTMLElement, duration: number = 500): void {
    element.classList.add('input-animate--error');
    setTimeout(() => {
      element.classList.remove('input-animate--error');
    }, duration);
  }

  /**
   * Pulse element
   */
  static pulse(element: HTMLElement, scale: number = 1.1, duration: number = 200): void {
    element.style.transition = `transform ${duration}ms ease`;
    element.style.transform = `scale(${scale})`;
    setTimeout(() => {
      element.style.transform = 'scale(1)';
    }, duration);
  }

  /**
   * Animate price change
   */
  static animatePriceChange(
    element: HTMLElement,
    oldPrice: number,
    newPrice: number,
    formatter: (value: number) => string
  ): void {
    const isIncrease = newPrice > oldPrice;
    element.classList.add(isIncrease ? 'price-update--up' : 'price-update--down');

    MicroAnimations.countNumber(element, oldPrice, newPrice, 400, formatter);

    setTimeout(() => {
      element.classList.remove('price-update--up', 'price-update--down');
    }, 600);
  }

  /**
   * Staggered entrance for multiple elements
   */
  static staggeredEntrance(
    elements: HTMLElement[],
    baseDelay: number = 50,
    animationClass: string = 'card-entrance'
  ): void {
    elements.forEach((element, index) => {
      setTimeout(() => {
        element.classList.add(
          animationClass,
          `${animationClass}--stagger-${Math.min(index + 1, 6)}`
        );
      }, index * baseDelay);
    });
  }

  /**
   * Confetti celebration effect
   */
  static confetti(
    element: HTMLElement,
    options: {
      particleCount?: number;
      colors?: string[];
      duration?: number;
    } = {}
  ): void {
    const particleCount = options.particleCount || 50;
    const colors = options.colors || ['#ff6b35', '#48bb78', '#4299e1', '#ed8936', '#9f7aea'];
    const duration = options.duration || 3000;

    const container = document.createElement('div');
    container.style.cssText = `
      position: fixed;
      inset: 0;
      pointer-events: none;
      overflow: hidden;
      z-index: 9999;
    `;
    document.body.appendChild(container);

    for (let i = 0; i < particleCount; i++) {
      const particle = document.createElement('div');
      const size = Math.random() * 8 + 4;
      const color = colors[Math.floor(Math.random() * colors.length)];
      const left = Math.random() * 100;
      const angle = Math.random() * 360;
      const velocity = Math.random() * 100 + 50;
      const durationVariation = Math.random() * 0.5 + 0.5;

      particle.style.cssText = `
        position: absolute;
        left: ${left}%;
        top: -20px;
        width: ${size}px;
        height: ${size}px;
        background: ${color};
        border-radius: ${Math.random() > 0.5 ? '50%' : '0'};
        transform: rotate(${angle}deg);
        opacity: 1;
        animation: confetti-fall ${duration * durationVariation}ms linear forwards;
      `;

      container.appendChild(particle);
    }

    const style = document.createElement('style');
    style.textContent = `
      @keyframes confetti-fall {
        0% {
          transform: translateY(0) rotate(0deg);
          opacity: 1;
        }
        100% {
          transform: translateY(100vh) rotate(720deg);
          opacity: 0;
        }
      }
    `;
    document.head.appendChild(style);

    setTimeout(() => {
      container.remove();
      style.remove();
    }, duration);
  }

  /**
   * Add hover sound effect (optional)
   */
  static playHoverSound(audioUrl?: string): void {
    if (!audioUrl) return;
    const audio = new Audio(audioUrl);
    audio.volume = 0.1;
    audio.play().catch(() => {});
  }

  /**
   * Throttled animation frame
   */
  static throttleAnimationFrame<T extends (...args: any[]) => void>(func: T): T {
    let ticking = false;
    return ((...args: any[]) => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          func(...args);
          ticking = false;
        });
        ticking = true;
      }
    }) as T;
  }

  /**
   * Debounced animation reset
   */
  static debounceReset(element: HTMLElement, className: string, duration: number = 300): void {
    element.classList.remove(className);
    void element.offsetWidth;
    element.classList.add(className);
    setTimeout(() => {
      element.classList.remove(className);
    }, duration);
  }
}

/**
 * Initialize all micro-animations
 */
export function initMicroAnimations(): void {
  MicroAnimations.initRippleButtons('.ripple-effect');
  console.log('[MicroAnimations] Initialized');
}

export default MicroAnimations;
