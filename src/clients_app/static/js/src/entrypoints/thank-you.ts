import { bootstrapModule } from '../core/bootstrap';
import { initThankYouPage } from '../modules/thank-you';

bootstrapModule('[data-thank-you-root]', (root) => {
    initThankYouPage(root);
}, { name: 'thank-you' });
