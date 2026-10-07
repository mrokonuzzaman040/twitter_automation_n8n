#!/bin/sh
# Imports the Social Agents workflows the first time this n8n volume is used (and again when
# the marker version below is raised), then starts n8n.
MARK=/home/node/.n8n/.social-agents-workflows-v2
if [ ! -f "$MARK" ]; then
  n8n import:workflow --separate --input=/workflows/workflows \
    && n8n publish:workflow --id=SocialAgentsEvnt \
    && n8n publish:workflow --id=SocialAgentsAprv \
    && touch "$MARK"
fi
exec n8n start
