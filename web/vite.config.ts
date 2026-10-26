import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  // Never inline fonts as data: URIs — the production CSP (default-src 'self') blocks them,
  // which would drop the small Noto Sans SC / pixel-font subsets.
  build: { emptyOutDir: false, assetsInlineLimit: (file) => (console.error("INL", file), /\.woff2?($|\?)/.test(file) ? false : undefined) },
  server: { port: 5183, proxy: { "/api": "http://127.0.0.1:18383" } },
});
