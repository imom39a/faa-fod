import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const BACKEND = 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': BACKEND,
      '/images': BACKEND,
    },
    // Mock mode reads the shared rule set from app/data/rules/fod-rules.json.
    fs: { allow: ['..'] },
  },
  test: {
    environment: 'node',
    // src/design.test.ts reads the stylesheets; without this the test runner replaces CSS with an empty file.
    css: true,
    include: ['src/**/*.test.ts'],
  },
});
