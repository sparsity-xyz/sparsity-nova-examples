FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

ENV IN_DOCKER=True

# Run the chatbot application
CMD ["python", "/app/app.py"]
