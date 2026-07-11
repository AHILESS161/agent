FROM node:20-alpine

# Set working directory
WORKDIR /app

# Install dependencies first (layer caching)
COPY package*.json ./
RUN npm ci

# Copy application code
COPY . .

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000 || exit 1

# Run development server
# For production, replace with:
# RUN npm run build
# CMD ["npx", "serve", "-s", "dist", "-l", "3000"]
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
