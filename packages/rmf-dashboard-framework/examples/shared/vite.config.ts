import react from '@vitejs/plugin-react-swc';
import path from 'path';
import { defineConfig } from 'vite';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  publicDir: path.resolve(__dirname, 'public'),
  server: {
    host: '0.0.0.0', // Escucha en todas las interfaces
    port: 5173,
  },
});
