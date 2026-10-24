# frontend/Dockerfile - Production Multi-Stage Container for Vue 3 PWA Client
#
# Stage 1: Build static PWA assets using Node 20
# Stage 2: Serve optimized bundle using NGINX Alpine with immediate SW updates

# Stage 1: Builder
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency manifests
COPY frontend/package.json frontend/package-lock.json ./

# Install exact dependencies
RUN npm ci

# Copy source code and build production distribution
COPY frontend/ ./
RUN npm run build

# Stage 2: NGINX Runtime
FROM nginx:1.27-alpine AS runner

# Configure default port and API upstream endpoint for NGINX template substitution
ENV PORT=80 \
    API_UPSTREAM=http://127.0.0.1:5000 \
    NGINX_ENVSUBST_FILTER="^(API_UPSTREAM|PORT)$"

# Clean default NGINX public files
RUN rm -rf /usr/share/nginx/html/*

# Copy built static bundle from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy NGINX configuration both as active conf and template for environment substitution
COPY frontend/nginx.conf /etc/nginx/templates/default.conf.template
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy entrypoint wrapper to sanitize API_UPSTREAM before official docker-entrypoint.sh runs
COPY frontend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
