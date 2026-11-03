import react from '@vitejs/plugin-react';
import {defineConfig} from 'vite';

const hub = 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {glasses: 'index.html', console: 'console.html'},
    },
  },
  server: {
    proxy: {
      '/api': hub,
      '/hud': {target: hub, ws: true},
      '/audio': {target: hub, ws: true},
    },
  },
});
