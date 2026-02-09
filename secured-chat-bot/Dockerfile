# Stage 1: Build frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# Stage 2: Final image
FROM python:3.11-slim
WORKDIR /app

# Install python dependencies
COPY enclave/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy enclave code
COPY enclave/ .

# Copy built frontend from Stage 1
COPY --from=frontend-builder /build/out ./frontend

ENV IN_ENCLAVE=true
CMD ["python", "app.py"]
