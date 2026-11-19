import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// The central server (central_factory_server.py) serves dist/ and the /api routes from one
// origin, so the built app calls /api with relative URLs. In dev, Vite proxies them to it.
export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: { "/api": "http://127.0.0.1:5173" },
    port: 5174,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  // Under vitest, resolve Svelte's browser build so components can be mounted in jsdom.
  resolve: process.env.VITEST ? { conditions: ["browser"] } : undefined,
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.js"],
  },
});
