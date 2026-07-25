import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "client", "src"),
      "@shared": path.resolve(import.meta.dirname, "shared"),
      "@assets": path.resolve(import.meta.dirname, "attached_assets"),
    },
  },
  root: path.resolve(import.meta.dirname, "client"),
  base: "./",
  build: {
    outDir: path.resolve(import.meta.dirname, "dist/public"),
    emptyOutDir: true,
  },
  server: {
    port: 3000,
    // Слушаем на всех интерфейсах: нужно для запуска в Docker и для
    // проброса через туннель (Cloudflare/ngrok).
    host: true,
    fs: {
      strict: true,
      deny: ["**/.*"],
    },
    proxy: {
      // Все запросы к API уходят на FastAPI. Адрес бэкенда задаётся
      // переменной окружения и не зашивается в исходный код —
      // это же позволяет работать через внешний туннель.
      "/api": {
        target: process.env.VITE_API_URL || "http://localhost:8000",
        changeOrigin: true,
      },
    },
    // Туннели Cloudflare/ngrok отдают собственный хост, который Vite
    // по умолчанию отклоняет.
    allowedHosts: true,
  },
});
