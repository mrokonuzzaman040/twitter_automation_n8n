FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Docker CLI so the container can talk to the host Docker daemon via socket.
RUN apt-get update && apt-get install -y --no-install-recommends docker.io git && rm -rf /var/lib/apt/lists/*

COPY app ./app

# Run unprivileged; /data is the shared volume (control DB + one DB per account).
RUN useradd -m -u 10001 agent && mkdir -p /data/accounts && chown -R agent /data
USER agent
