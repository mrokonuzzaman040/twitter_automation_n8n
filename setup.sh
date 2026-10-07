#!/bin/sh
# Generates .env with a random master key (encrypts all stored credentials) and admin password.
set -e
cd "$(dirname "$0")"

if [ -f .env ]; then
  echo ".env already exists - leaving it untouched."
  exit 0
fi

MASTER_KEY=$(openssl rand -hex 32)
ADMIN_PASSWORD=$(openssl rand -hex 9)

cat > .env <<EOF
# Encrypts every stored credential. If you lose it, saved API keys cannot be decrypted. Back it up.
MASTER_KEY=$MASTER_KEY
# Password for the admin panel
ADMIN_PASSWORD=$ADMIN_PASSWORD
PANEL_PORT=8080
# Max parallel LLM requests across all agents (NVIDIA free tier is rate limited)
LLM_CONCURRENCY=3
GRAPH_API_VERSION=v23.0
EOF
chmod 600 .env

echo "Created .env"
echo "Admin panel password: $ADMIN_PASSWORD"
