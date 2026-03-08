FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application and config
COPY app.py .
COPY config.json .
COPY nova_python_sdk ./nova_python_sdk
RUN chmod +x app.py

ENV IN_ENCLAVE=true

# Run the oracle application
CMD ["python", "/app/app.py"]
