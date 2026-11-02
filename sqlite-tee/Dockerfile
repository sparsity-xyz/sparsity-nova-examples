FROM python:3.12-slim-bookworm
WORKDIR /app
COPY app.py queries.sql /app/
EXPOSE 8080
CMD ["python", "-u", "/app/app.py"]
