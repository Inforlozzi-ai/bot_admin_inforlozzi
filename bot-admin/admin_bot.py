import os, logging, asyncio, re, subprocess
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações
BOT_TOKEN = os.environ["BOT_TOKEN"]
API_ID    = int(os.environ["API_ID"])
API_HASH  = os.environ["API_HASH"]
ADMIN_IDS = set(int(x) for x in os.environ.get("ADMIN_IDS","").split(",") if x.strip().isdigit())
BOTS_BASE = "/opt/bots"

bot = TelegramClient(None, API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Estados para o fluxo de geração de string
GEN_STRING_DATA = {} # {user_id: {'step': 'phone', 'client': client, ...}}

def is_admin(uid):
    return not ADMIN_IDS or uid in ADMIN_IDS

@bot.on(events.NewMessage(pattern='/start'))
async def start(ev):
    if not is_admin(ev.sender_id): return
    buttons = [
        [Button.inline("🆕 Criar Novo Bot", b"novo_bot")],
        [Button.inline("🔁 Gerar Session String (User)", b"gerar_string")],
        [Button.inline("📋 Listar Meus Bots", b"listar_bots")]
    ]
    await ev.reply("💎 **Painel Inforlozzi AI**\nEscolha uma opção abaixo:", buttons=buttons)

@bot.on(events.CallbackQuery(data=b"gerar_string"))
async def iniciar_geracao(ev):
    uid = ev.sender_id
    GEN_STRING_DATA[uid] = {'step': 'phone'}
    await ev.edit("📱 **Geração de Session String**\n\nDigite o número do telefone com +55 e DDD:\nEx: `+5511999998888`", buttons=[Button.inline("❌ Cancelar", b"cancelar_gen")])

@bot.on(events.NewMessage())
async def fluxo_geracao(ev):
    uid = ev.sender_id
    if uid not in GEN_STRING_DATA or ev.text.startswith('/'): return
    
    data = GEN_STRING_DATA[uid]
    
    if data['step'] == 'phone':
        phone = ev.text.strip()
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            sent_code = await client.send_code_request(phone)
            data.update({'step': 'code', 'phone': phone, 'client': client, 'hash': sent_code.phone_code_hash})
            await ev.reply("📩 **Código Enviado!**\nDigite o código que você recebeu no Telegram:")
        except Exception as e:
            await ev.reply(f"❌ Erro: {e}")
            del GEN_STRING_DATA[uid]

    elif data['step'] == 'code':
        code = ev.text.strip()
        client = data['client']
        try:
            await client.sign_in(data['phone'], code, phone_code_hash=data['hash'])
            string = client.session.save()
            await ev.reply(f"✅ **String Gerada com Sucesso!**\n\n`{string}`\n\nUse esta string para configurar seu novo bot.")
            await client.disconnect()
            del GEN_STRING_DATA[uid]
        except SessionPasswordNeededError:
            data['step'] = 'password'
            await ev.reply("🔐 **Verificação em 2 etapas ativa.**\nDigite sua senha da nuvem:")
        except Exception as e:
            await ev.reply(f"❌ Erro no código: {e}")

    elif data['step'] == 'password':
        password = ev.text.strip()
        client = data['client']
        try:
            await client.sign_in(password=password)
            string = client.session.save()
            await ev.reply(f"✅ **String Gerada (com senha)!**\n\n`{string}`")
            await client.disconnect()
            del GEN_STRING_DATA[uid]
        except Exception as e:
            await ev.reply(f"❌ Senha incorreta: {e}")

@bot.on(events.CallbackQuery(data=b"cancelar_gen"))
async def cancelar(ev):
    uid = ev.sender_id
    if uid in GEN_STRING_DATA:
        if 'client' in GEN_STRING_DATA[uid]:
            await GEN_STRING_DATA[uid]['client'].disconnect()
        del GEN_STRING_DATA[uid]
    await ev.edit("❌ Processo cancelado.")

if __name__ == "__main__":
    logger.info("Bot Admin iniciado com Gerador de String!")
    bot.run_until_disconnected()