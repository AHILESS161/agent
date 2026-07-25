# Vite + React SPA. Собственного backend у фронтенда нет: запросы к /api
# проксируются на FastAPI (адрес задаётся переменной VITE_API_URL).
FROM node:20-alpine

WORKDIR /app

# Зависимости отдельным слоем — для кэширования.
COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000 || exit 1

# Dev-сервер Vite: он же выполняет проксирование на API.
# Для production-сборки: RUN npm run build && npx serve -s dist/public -l 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
