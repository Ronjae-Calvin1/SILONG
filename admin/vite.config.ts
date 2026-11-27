import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The admin console runs on its own port (5174), apart from the user site (5173).
export default defineConfig({
  plugins: [react()],
  server: { port: 5174, strictPort: true },
  // maplibre-gl alone is about 1 MB, so the default 500 kB size warning would always show.
  build: { chunkSizeWarningLimit: 1500 },
})
