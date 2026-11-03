FROM python:3.12-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends mariadb-server mariadb-client procps git ca-certificates \
    && rm -rf /var/lib/apt/lists/* /var/lib/mysql/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt requests==2.32.5
WORKDIR /launcher
COPY launcher.py policy.json /launcher/
ENV AWS_EC2_METADATA_DISABLED=true
EXPOSE 8080
CMD ["python", "-u", "/launcher/launcher.py"]
