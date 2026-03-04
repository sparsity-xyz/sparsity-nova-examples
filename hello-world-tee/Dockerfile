FROM python:3.12-slim

WORKDIR /app

COPY enclave/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY enclave/ .

ENV IN_ENCLAVE=true

EXPOSE 8000

CMD ["python", "app.py"]
