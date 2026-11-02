FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends gocryptfs fuse3 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir cryptography==46.0.3
WORKDIR /app
COPY app.py client-public.txt /app/
EXPOSE 8080
CMD ["python", "-u", "/app/app.py"]
