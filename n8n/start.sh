#!/bin/sh
# Imports the Social Agents workflows the first time this n8n volume is used, then starts n8n.
MARK=/home/node/.n8n/.social-agents-workflows-v1
if [ ! -f "$MARK" ]; then
  n8n import:workflow --separate --input=/workflows/workflows \
    && n8n publish:workflow --id=SocialAgentsEvnt \
    && touch "$MARK"
fi
exec n8n start
