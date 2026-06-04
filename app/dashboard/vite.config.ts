import react from "@vitejs/plugin-react";
import { defineConfig, splitVendorChunkPlugin } from "vite";
import svgr from "vite-plugin-svgr";
import { visualizer } from "rollup-plugin-visualizer";
import tsconfigPaths from "vite-tsconfig-paths";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    tsconfigPaths(),
    react({
      include: "**/*.tsx",
    }),
    svgr(),
    visualizer(),
    splitVendorChunkPlugin(),
  ],
  server: {
    // Proxy /api and /sub to the backend when running `npm run dev` standalone.
    // When the backend starts the dev server (DEBUG=True), VITE_BASE_API is set
    // to the full backend URL so these proxy rules are bypassed automatically.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/sub": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
