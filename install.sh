#!/bin/bash
set -e

REPO_RAW="${REPO_RAW:-https://raw.githubusercontent.com/Inforlozzi-ai/bot_admin_inforlozzi_Oficial/main}"
INSTALL_DIR="/opt/bot-admin-reseller"
CTR="bot-admin-reseller"

echo "=== InforLozzi AI - Bot Admin Installer ==="

# Diretório
mkdir -p "$INSTALL_DIR" /opt/bots

# Baixa arquivos
for f in bot.py chat_lister.py userbot.py Dockerfile .env.example; do
  curl -fsSL "$REPO_RAW/$f" -o "$INSTALL_DIR/$f"
done

# Configura .env
if [ ! -f "$INSTALL_DIR/.env" ]; then
  cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
  echo ""
  echo "ATENÇÃO: Edite o arquivo /opt/bot-admin-reseller/.env com seus dados!"
  echo "Depois execute: docker build -t bot-admin-img $INSTALL_DIR && docker run -d --name $CTR --restart unless-stopped --env-file $INSTALL_DIR/.env -v /opt/bots:/opt/bots -v /var/run/docker.sock:/var/run/docker.sock bot-admin-img"
else
  # Constrói e sobe
  docker build -t bot-admin-img "$INSTALL_DIR"
  docker stop "$CTR" 2>/dev/null || true
  docker rm   "$CTR" 2>/dev/null || true
  docker run -d --name "$CTR" --restart unless-stopped \
    --env-file "$INSTALL_DIR/.env" \
    -v /opt/bots:/opt/bots \
    -v /var/run/docker.sock:/var/run/docker.sock \
    bot-admin-img
  echo "Bot Admin instalado! Container: $CTR"
fi
