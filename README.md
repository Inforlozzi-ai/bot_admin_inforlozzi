# Bot Admin Revendedor — InforLozzi AI

Sistema completo de bot Telegram para revendedores de conteúdo IPTV com IA integrada.

## Arquivos

| Arquivo | Descrição |
|---|---|
| `bot.py` | Bot Admin — painel de controle principal |
| `admin_bot.py` | Bot Admin legado (compatibilidade) |
| `userbot.py` | Userbot cliente — encaminha mensagens com IA |
| `chat_lister.py` | Script auxiliar — lista chats da conta userbot |
| `install.sh` | Script de instalação automática |
| `docker-compose.yml` | Compose para subir o admin |

## Instalação rápida

```bash
curl -fsSL https://raw.githubusercontent.com/Inforlozzi-ai/bot_admin_inforlozzi_Oficial/master/install.sh | bash
```

## Variáveis de ambiente (bot admin)

```env
BOT_TOKEN=         # Token do @BotFather
API_ID=            # my.telegram.org
API_HASH=          # my.telegram.org
ADMIN_IDS=         # IDs separados por vírgula
BOTS_BASE=/opt/bots
REPO_RAW=curl -fsSL https://raw.githubusercontent.com/Inforlozzi-ai/bot_admin_inforlozzi_Oficial/master/install.sh | bash
```

## Funcionalidades

- Instalar/iniciar/parar/reiniciar/remover bots clientes
- Reencaminhar mensagens (copiar ou encaminhar)
- Seletor visual de chats: Grupos, Canais, Bots, Busca
- Config IA por bot: troca de logo, filtro de conteúdo, texto fixo
- Modelo GPT configurável (gpt-4o, gpt-4o-mini, etc.)
- Atualização em massa de todos os bots com 1 clique
