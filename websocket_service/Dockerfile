FROM node:20-alpine

# Set working directory
WORKDIR /app

# Install dependencies first (leverages Docker cache layer)
COPY package*.json ./
RUN npm install --omit=dev

# Copy application source
COPY . .

# Expose microservice port
EXPOSE 6001

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:6001/health || exit 1

# Start microservice
CMD ["node", "server.js"]
