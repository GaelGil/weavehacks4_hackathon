import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// The renderer lives in ./renderer. Electron loads the dev server in dev and
// renderer/dist/index.html in production, so we use a relative base.
export default defineConfig({
  root: resolve(__dirname, "renderer"),
  base: "./",
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: resolve(__dirname, "renderer/dist"),
    emptyOutDir: true,
  },
});
