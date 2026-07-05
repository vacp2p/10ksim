# Production-Optimized Docker Image (Recommended for Kubernetes)
# Multi-stage build: Build with Node, serve with Nginx
# 
# Why Nginx instead of npm start?
# - 10x smaller image: ~20MB vs ~200MB
# - 10x faster: Static file serving optimized
# - Production-ready: Compression, caching, security
# - No dev dependencies in final image
#
# For simpler development deployment, see Dockerfile.dev

# Build stage
FROM node:18-alpine AS build

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies (use npm install instead of ci for flexibility)
RUN npm install --production

# Copy source code
COPY public/ ./public/
COPY src/ ./src/

# Build-time argument for API URL (baked into the build)
ARG REACT_APP_API_URL=http://localhost:8000
ENV REACT_APP_API_URL=$REACT_APP_API_URL

# Build the app
RUN npm run build

# Production stage with nginx
FROM nginx:alpine

# Copy built files from build stage
COPY --from=build /app/build /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
