import { defineConfig } from 'vite';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vue from '@vitejs/plugin-vue';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

type TargetKey = 'employees' | 'clients';

const targets: Record<
  TargetKey,
  {
    srcDir: string;
    outDir: string;
    base: string;
    entrypoints: Record<string, string>;
  }
> = {
  employees: {
    srcDir: path.resolve(__dirname, 'src/employees_app/static/js/src'),
    outDir: path.resolve(__dirname, 'src/employees_app/static/js/dist/employees'),
    base: '/static/js/dist/employees/',
    entrypoints: {
      dashboard: 'entrypoints/dashboard.ts',
      base: 'entrypoints/base.ts',
    },
  },
  clients: {
    srcDir: path.resolve(__dirname, 'src/clients_app/static/js/src'),
    outDir: path.resolve(__dirname, 'src/clients_app/static/js/dist/clients'),
    base: '/static/js/dist/clients/',
    entrypoints: {
      base: 'entrypoints/base.ts',
      menu: 'entrypoints/menu.ts',
      'thank-you': 'entrypoints/thank-you.ts',
    },
  },
};

const target = (process.env.PRONTO_TARGET || 'employees') as TargetKey;
const descriptor = targets[target];

export default defineConfig({
  plugins: [vue()],
  root: descriptor.srcDir,
  base: descriptor.base,
  publicDir: false,
  resolve: {
    alias: {
      'lucide/dist/umd/lucide.js': path.resolve(
        __dirname,
        'node_modules/lucide/dist/umd/lucide.js'
      ),
    },
  },
  define: {
    'import.meta.env.VITE_STATIC_HOST': JSON.stringify(
      process.env.PRONTO_STATIC_CONTAINER_HOST || 'http://localhost:9088'
    ),
    'import.meta.env.VITE_APP_BASE_URL': JSON.stringify(
      process.env.APP_BASE_URL || 'http://localhost:6080'
    ),
  },
  build: {
    outDir: descriptor.outDir,
    emptyOutDir: true,
    sourcemap: true,
    manifest: true,
    rollupOptions: {
      input: Object.fromEntries(
        Object.entries(descriptor.entrypoints).map(([name, relativePath]) => [
          name,
          path.resolve(descriptor.srcDir, relativePath),
        ])
      ),
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
  server: {
    port: 6080,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:6081',
        changeOrigin: true,
      },
    },
  },
});
