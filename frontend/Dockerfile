# frontend/Dockerfile - Production Multi-Stage Container for Vue 3 PWA Client
#
# Stage 1: Build static PWA assets using Node 20
# Stage 2: Serve optimized bundle using NGINX Alpine with immediate SW updates

# Stage 1: Builder
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency manifests
COPY package.json package-lock.json ./

# Install exact dependencies
RUN npm ci

# Copy source code and build production distribution
COPY . ./
RUN npm run build

# Stage 2: NGINX Runtime
FROM nginx:1.27-alpine AS runner

# Configure default API upstream endpoint for NGINX template substitution
ENV API_UPSTREAM=http://127.0.0.1:5000 \
    NGINX_ENVSUBST_FILTER=API_UPSTREAM

# Clean default NGINX public files
RUN rm -rf /usr/share/nginx/html/*

# Copy built static bundle from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy NGINX configuration both as active conf and template for environment substitution
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy upstream validation script to docker-entrypoint.d (runs before 20-envsubst-on-templates.sh)
COPY 15-validate-upstream.sh /docker-entrypoint.d/15-validate-upstream.sh
RUN chmod +x /docker-entrypoint.d/15-validate-upstream.sh

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
