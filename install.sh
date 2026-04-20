#!/bin/bash
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

BOT_BASE="/opt/bots"
REPO_RAW="https://raw.githubusercontent.com/Inforlozzi-ai/bot_admin_inforlozzi/main"
ADMIN_RAW="https://raw.githubusercontent.com/Inforlozzi-ai/bot_admin_inforlozzi/main/bot-admin"
ADMIN_BASE="/opt/bot-admin-reseller"

ok()   { echo -e "${GREEN}✅ $*${NC}"; }
err()  { echo -e "${RED}❌ $*${NC}"; }
info() { echo -e "${CYAN}ℹ️  $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }
ask()  { echo -e "${YELLOW}$*${NC}"; }

header() {
  clear
  echo -e "${BLUE}${BOLD}"
  echo "╔══════════════════════════════════════════╗"
  echo "║     UserBot Telegram Pro — Gerenciador   ║"
  echo "╚══════════════════════════════════════════╝"
  echo -e "${NC}"
}

instalar_deps() {
  info "Verificando dependências..."
  apt-get update -qq
  for pkg in python3 python3-pip curl git; do
    dpkg -s "$pkg" &>/dev/null || apt-get install -y "$pkg" 2>/dev/null || true
  done
  systemctl enable --now docker &>/dev/null || true
  ok "Dependências OK"
}

listar_bots() {
  bots=()
  if [ -d "$BOT_BASE" ]; then
    for d in "$BOT_BASE"/*/; do
      [ -f "$d/bot.py" ] && bots+=("$(basename "$d")")
    done
  fi
}

selecionar_bot() {
  listar_bots
  if [ ${#bots[@]} -eq 0 ]; then err "Nenhum bot instalado."; return 1; fi
  echo ""
  for i in "${!bots[@]}"; do
    estado="🔴 PARADO"
    docker ps --format "{{.Names}}" 2>/dev/null | grep -q "^userbot_${bots[$i]}$" && estado="🟢 ATIVO"
    echo "  [$((i+1))] ${bots[$i]}  $estado"
  done
  echo ""
  ask "Escolha o bot [1-${#bots[@]}] ou 0 para cancelar: "
  read -r escolha
  [[ "$escolha" == "0" ]] && return 1
  if [[ "$escolha" =~ ^[0-9]+$ ]] && [ "$escolha" -ge 1 ] && [ "$escolha" -le "${#bots[@]}" ]; then
    BOT_SELECIONADO="${bots[$((escolha-1))]}"
    BOT_DIR="$BOT_BASE/$BOT_SELECIONADO"
    return 0
  fi
  err "Opção inválida."; return 1
}

make_dockerfile() {
  local dir="$1"
  printf 'FROM python:3.12-slim\nWORKDIR /app\nRUN pip install --no-cache-dir telethon openai pillow python-dotenv\nCOPY bot.py .\nCMD ["python3", "-u", "bot.py"]\n' > "$dir/Dockerfile"
}

instalar_bot() {
  instalar_deps
  echo ""
  ask "Nome do bot (sem espaços, ex: cliente1): "
  read -r nome
  nome="${nome// /_}"
  dir="$BOT_BASE/$nome"
  if [ -d "$dir" ]; then err "Bot '$nome' já existe."; return; fi
  mkdir -p "$dir"
  ask "API_ID: ";      read -r api_id
  ask "API_HASH: ";    read -r api_hash
  ask "SESSION_STRING: "; read -r session
  ask "BOT_TOKEN: ";   read -r bot_token
  ask "BOT_NOME: ";    read -r bot_nome
  ask "ADMIN_IDS (separados por vírgula): "; read -r admin_ids
  ask "TARGET_GROUP_ID: "; read -r target
  ask "SOURCE_CHAT_IDS (ou Enter para todos): "; read -r sources
  printf "API_ID=%s\nAPI_HASH=%s\nSESSION_STRING=%s\nBOT_TOKEN=%s\nBOT_NOME=%s\nADMIN_IDS=%s\nCLIENT_IDS=\nTARGET_GROUP_ID=%s\nSOURCE_CHAT_IDS=%s\nFORWARD_MODE=copy\nOPENAI_API_KEY=\nOPENAI_MODEL=gpt-4o-mini\nIA_LOGO_PATH=\nIA_TEXTO_FIXO=\n" \
    "$api_id" "$api_hash" "$session" "$bot_token" "$bot_nome" "$admin_ids" "$target" "$sources" > "$dir/.env"
  info "Baixando bot.py de $REPO_RAW ..."
  curl -fsSL "$REPO_RAW/bot.py" -o "$dir/bot.py"
  ok "bot.py: $(wc -l < "$dir/bot.py") linhas"
  make_dockerfile "$dir"
  docker build -q -t "userbot_img_$nome" "$dir"
  docker run -d --name "userbot_$nome" --restart unless-stopped \
    --env-file "$dir/.env" \
    "userbot_img_$nome" &>/dev/null
  ok "Bot '$nome' instalado! Container: userbot_$nome"
}

gerenciar_bots() {
  listar_bots
  if [ ${#bots[@]} -eq 0 ]; then err "Nenhum bot instalado."; return; fi
  echo ""
  for i in "${!bots[@]}"; do
    estado="🔴"
    docker ps --format "{{.Names}}" 2>/dev/null | grep -q "^userbot_${bots[$i]}$" && estado="🟢"
    echo "  $estado ${bots[$i]}"
  done
  echo ""
  echo "  [1] Iniciar   [2] Parar   [3] Reiniciar"
  echo "  [4] Ver logs  [5] Ver .env"
  echo "  [0] Voltar"
  ask "Ação: "; read -r acao
  [[ "$acao" == "0" ]] && return
  selecionar_bot || return
  container="userbot_$BOT_SELECIONADO"
  case "$acao" in
    1) docker start   "$container" && ok "Iniciado: $container" ;;
    2) docker stop    "$container" && ok "Parado: $container" ;;
    3) docker restart "$container" && ok "Reiniciado: $container" ;;
    4) info "Logs (Ctrl+C para sair):"; docker logs -f --tail=60 "$container" ;;
    5) cat "$BOT_DIR/.env" ;;
    *) err "Opção inválida." ;;
  esac
}

desinstalar_bot() {
  selecionar_bot || return
  warn "Vai REMOVER o bot '${BOT_SELECIONADO}' e todos os seus dados!"
  ask "Confirmar? (s/N): "; read -r conf
  [[ "$conf" =~ ^[sS]$ ]] || { info "Cancelado."; return; }
  docker stop "userbot_${BOT_SELECIONADO}" 2>/dev/null || true
  docker rm   "userbot_${BOT_SELECIONADO}" 2>/dev/null || true
  docker rmi  "userbot_img_${BOT_SELECIONADO}" 2>/dev/null || true
  rm -rf "${BOT_DIR:?}"
  ok "Bot '${BOT_SELECIONADO}' removido!"
}

ver_logs() {
  selecionar_bot || return
  info "Logs de userbot_$BOT_SELECIONADO (Ctrl+C para sair):"
  docker logs -f --tail=80 "userbot_$BOT_SELECIONADO"
}

regerar_session() {
  selecionar_bot || return
  ask "Nova SESSION_STRING: "; read -r nova_session
  sed -i "s|^SESSION_STRING=.*|SESSION_STRING=$nova_session|" "$BOT_DIR/.env"
  docker restart "userbot_$BOT_SELECIONADO"
  ok "Session atualizada e bot reiniciado!"
}

atualizar_bots() {
  echo ""
  echo "  [1] Atualizar TODOS os bots"
  echo "  [2] Atualizar bot específico"
  echo "  [3] Atualizar Bot Admin Revendedor"
  echo "  [0] Voltar"
  ask "Escolha: "; read -r opcao
  case "$opcao" in
    1)
      listar_bots
      if [ ${#bots[@]} -eq 0 ]; then err "Nenhum bot instalado."; return; fi
      curl -fsSL "$REPO_RAW/bot.py" -o "/tmp/bot_novo.py"
      for nome in "${bots[@]}"; do
        cp /tmp/bot_novo.py "$BOT_BASE/$nome/bot.py"
        docker stop  "userbot_$nome" 2>/dev/null || true
        docker rm    "userbot_$nome" 2>/dev/null || true
        docker rmi   "userbot_img_$nome" 2>/dev/null || true
        docker build -q -t "userbot_img_$nome" "$BOT_BASE/$nome"
        docker run -d --name "userbot_$nome" --restart unless-stopped \
          --env-file "$BOT_BASE/$nome/.env" \
          "userbot_img_$nome" &>/dev/null
        ok "$nome atualizado!"
      done
      ;;
    2)
      selecionar_bot || return
      curl -fsSL "$REPO_RAW/bot.py" -o "$BOT_DIR/bot.py"
      docker stop  "userbot_$BOT_SELECIONADO" 2>/dev/null || true
      docker rm    "userbot_$BOT_SELECIONADO" 2>/dev/null || true
      docker rmi   "userbot_img_$BOT_SELECIONADO" 2>/dev/null || true
      docker build -q -t "userbot_img_$BOT_SELECIONADO" "$BOT_DIR"
      docker run -d --name "userbot_$BOT_SELECIONADO" --restart unless-stopped \
        --env-file "$BOT_DIR/.env" \
        "userbot_img_$BOT_SELECIONADO" &>/dev/null
      ok "Bot '$BOT_SELECIONADO' atualizado!"
      ;;
    3) atualizar_admin ;;
    0) return ;;
    *) err "Opção inválida." ;;
  esac
}

limpar_tudo() {
  warn "ATENÇÃO: Remove TODOS os bots e dados!"
  ask "Confirmar? (s/N): "; read -r conf
  [[ "$conf" =~ ^[sS]$ ]] || { info "Cancelado."; return; }
  listar_bots
  for nome in "${bots[@]}"; do
    docker stop "userbot_$nome" 2>/dev/null || true
    docker rm   "userbot_$nome" 2>/dev/null || true
    docker rmi  "userbot_img_$nome" 2>/dev/null || true
    rm -rf "$BOT_BASE/$nome"
    warn "Removido: $nome"
  done
  ok "Todos os bots removidos!"
}

instalar_admin() {
  instalar_deps
  if docker ps -a --format "{{.Names}}" | grep -q "^bot-admin-reseller$"; then
    warn "Bot Admin já instalado!"
    ask "Reinstalar? (s/N): "; read -r conf
    [[ "$conf" =~ ^[sS]$ ]] || return
    docker stop bot-admin-reseller 2>/dev/null || true
    docker rm   bot-admin-reseller 2>/dev/null || true
    docker rmi  bot-admin-img      2>/dev/null || true
    rm -rf "$ADMIN_BASE"
  fi
  mkdir -p "$ADMIN_BASE"
  ask "BOT_TOKEN do bot admin: ";           read -r bot_token
  ask "ADMIN_IDS: ";                         read -r admin_ids
  ask "API_ID: ";                            read -r api_id
  ask "API_HASH: ";                          read -r api_hash
  ask "OPENAI_API_KEY (ou Enter para pular): "; read -r openai_key
  printf "BOT_TOKEN=%s\nADMIN_IDS=%s\nAPI_ID=%s\nAPI_HASH=%s\nOPENAI_API_KEY=%s\nBOTS_BASE=/opt/bots\nREPO_RAW=%s\n" \
    "$bot_token" "$admin_ids" "$api_id" "$api_hash" "$openai_key" "$REPO_RAW" > "$ADMIN_BASE/.env"
  info "Baixando admin_bot.py de $ADMIN_RAW ..."
  curl -fsSL "$ADMIN_RAW/admin_bot.py" -o "$ADMIN_BASE/bot.py"
  ok "bot.py: $(wc -l < "$ADMIN_BASE/bot.py") linhas"
  printf 'FROM python:3.12-slim\nWORKDIR /app\nRUN pip install --no-cache-dir telethon openai pillow python-dotenv\nCOPY bot.py .\nCMD ["python3", "-u", "bot.py"]\n' > "$ADMIN_BASE/Dockerfile"
  docker build -q -t bot-admin-img "$ADMIN_BASE"
  docker run -d --name bot-admin-reseller --restart unless-stopped \
    --env-file "$ADMIN_BASE/.env" \
    -v /opt/bots:/opt/bots \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$(which docker)":/usr/local/bin/docker \
    bot-admin-img &>/dev/null
  ok "Bot Admin instalado! Container: bot-admin-reseller"
}

atualizar_admin() {
  if ! docker ps -a --format "{{.Names}}" | grep -q "^bot-admin-reseller$"; then
    err "Bot Admin não está instalado."; return
  fi
  info "Baixando admin_bot.py de $ADMIN_RAW ..."
  curl -fsSL "$ADMIN_RAW/admin_bot.py" -o "$ADMIN_BASE/bot.py"
  ok "bot.py: $(wc -l < "$ADMIN_BASE/bot.py") linhas"
  docker stop  bot-admin-reseller 2>/dev/null || true
  docker rm    bot-admin-reseller 2>/dev/null || true
  docker rmi   bot-admin-img      2>/dev/null || true
  printf 'FROM python:3.12-slim\nWORKDIR /app\nRUN pip install --no-cache-dir telethon openai pillow python-dotenv\nCOPY bot.py .\nCMD ["python3", "-u", "bot.py"]\n' > "$ADMIN_BASE/Dockerfile"
  docker build -q -t bot-admin-img "$ADMIN_BASE"
  docker run -d --name bot-admin-reseller --restart unless-stopped \
    --env-file "$ADMIN_BASE/.env" \
    -v /opt/bots:/opt/bots \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$(which docker)":/usr/local/bin/docker \
    bot-admin-img &>/dev/null
  ok "Bot Admin atualizado e reiniciado!"
}

desinstalar_admin() {
  if ! docker ps -a --format "{{.Names}}" | grep -q "^bot-admin-reseller$"; then
    err "Bot Admin não está instalado."; return
  fi
  warn "Vai remover o Bot Admin Revendedor!"
  ask "Confirmar? (s/N): "; read -r conf
  [[ "$conf" =~ ^[sS]$ ]] || { info "Cancelado."; return; }
  docker stop bot-admin-reseller 2>/dev/null || true
  docker rm   bot-admin-reseller 2>/dev/null || true
  docker rmi  bot-admin-img      2>/dev/null || true
  rm -rf "$ADMIN_BASE"
  ok "Bot Admin removido!"
}

menu_admin() {
  while true; do
    header
    admin_ok="🔴 PARADO"
    docker ps --format "{{.Names}}" 2>/dev/null | grep -q "^bot-admin-reseller$" && admin_ok="🟢 ATIVO"
    echo -e "  ${BOLD}Bot Admin Revendedor${NC} — $admin_ok"
    echo ""
    echo "  [1] 🤖 Instalar Bot Admin"
    echo "  [2] 🔄 Atualizar Bot Admin"
    echo "  [3] 📊 Logs Bot Admin"
    echo "  [4] 🗑  Desinstalar Bot Admin"
    echo "  [0] ⬅️  Voltar"
    echo ""
    ask "Escolha: "; read -r opcao
    case "$opcao" in
      1) instalar_admin ;;
      2) atualizar_admin ;;
      3) info "Logs (Ctrl+C para sair):"; docker logs -f --tail=80 bot-admin-reseller ;;
      4) desinstalar_admin ;;
      0) return ;;
      *) err "Opção inválida." ;;
    esac
    echo ""; ask "Pressione Enter para continuar..."; read -r
  done
}

while true; do
  header
  listar_bots
  echo -e "  Bots instalados: ${BOLD}${#bots[@]}${NC}"
  echo ""
  echo "  [1] 🆕  Instalar novo bot"
  echo "  [2] 📋  Gerenciar bots"
  echo "  [3] 🗑   Desinstalar bot"
  echo "  [4] 📊  Ver logs em tempo real"
  echo "  [5] 🔁  Regerar Session String"
  echo "  [6] 🔄  Atualizar bots (todos ou específico)"
  echo "  [7] 🧹  Limpar tudo (todos os bots)"
  echo "  [8] 🤖  Gerenciar Bot Admin Revendedor"
  echo "  [9] ❌  Sair"
  echo ""
  ask "Escolha [1-9]: "; read -r opcao
  case "$opcao" in
    1) instalar_bot ;;
    2) gerenciar_bots ;;
    3) desinstalar_bot ;;
    4) ver_logs ;;
    5) regerar_session ;;
    6) atualizar_bots ;;
    7) limpar_tudo ;;
    8) menu_admin ;;
    9) echo -e "${GREEN}Até logo! 👋${NC}"; exit 0 ;;
    *) err "Opção inválida." ;;
  esac
  echo ""; ask "Pressione Enter para continuar..."; read -r
done
