# Stage 1: Build the React Frontend SPA
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Build the FastAPI Backend & Playwright Runner
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy AS runner

# Expose server port
EXPOSE 8000

# Set working directory
WORKDIR /app

# Install python requirements
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy built frontend assets
COPY --from=frontend-builder /frontend/dist ./frontend/dist

# Copy backend application files
COPY backend/ ./backend/

# Run migrations and start FastAPI server
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
