import { describe, it, expect, beforeEach, vi } from 'vitest';
import { MenuFlow } from './menu-flow';
import type { MenuItem } from './modal-manager';

// Mock window globals
vi.stubGlobal('APP_CONFIG', {
  static_host_url: '/static',
  restaurant_assets: '/assets',
  currency_code: 'MXN',
  currency_symbol: '$'
});

vi.stubGlobal('APP_SETTINGS', {
  currency_locale: 'es-MX',
  currency_code: 'MXN'
});

describe('MenuFlow', () => {
  let root: HTMLElement;
  let menuFlow: MenuFlow;

  beforeEach(() => {
    document.body.innerHTML = `
      <div id="category-tabs"></div>
      <div id="menu-sections"></div>
      <div id="menu-search"></div>
      <div id="menu-search-suggestions"></div>
      <div id="filters-results-count"></div>
      <div id="menu-empty-state"></div>
    `;
    root = document.createElement('div');
    menuFlow = new MenuFlow(root);
  });

  it('renderMenuCard should include preparation time', () => {
    const item: MenuItem = {
      id: 1,
      name: 'Test Item',
      price: 100,
      is_available: true,
      preparation_time_minutes: 25,
      description: 'Test description',
      modifier_groups: []
    };

    const html = menuFlow.renderMenuCard(item);

    expect(html).toContain('Test Item');
    expect(html).toContain('$100.00');
    expect(html).toContain('⏱️ 25 min');
    expect(html).toContain('menu-item-card__prep-time');
  });

  it('renderMenuCard should NOT include preparation time if missing', () => {
    const item: MenuItem = {
      id: 2,
      name: 'Fast Item',
      price: 50,
      is_available: true,
      // No preparation_time_minutes
      description: 'Fast description',
      modifier_groups: []
    };

    const html = menuFlow.renderMenuCard(item);

    expect(html).toContain('Fast Item');
    expect(html).not.toContain('⏱️');
    expect(html).not.toContain('menu-item-card__prep-time');
  });

  it('getCategoryIcon should return SVG for "Bebidas"', () => {
    // @ts-ignore
    const icon = menuFlow.getCategoryIcon('Bebidas Frías');
    expect(icon).toContain('<svg');
    expect(icon).toContain('path');
  });

  it('getCategoryIcon should return SVG for "Hamburguesas"', () => {
    // @ts-ignore
    const icon = menuFlow.getCategoryIcon('Hamburguesas');
    expect(icon).toContain('<svg');
  });

  it('getCategoryIcon should return default SVG for unknown category', () => {
    // @ts-ignore
    const icon = menuFlow.getCategoryIcon('Unknown Category');
    expect(icon).toContain('<svg');
  });
});
