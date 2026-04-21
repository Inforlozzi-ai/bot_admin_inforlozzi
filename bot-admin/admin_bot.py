import os, logging, asyncio, re, subprocess
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações obrigatórias do .env
BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID    = int(os.environ.get("API_ID", 0))
API_HASH  = os.environ.get("API_HASH", "")
ADMIN_IDS = set(int(x) for x in os.environ.get("ADMIN_IDS","").split(",") if x.strip().isdigit())
BOTS_BASE = "/opt/bots"

bot = TelegramClient(None, API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Memória temporária para o fluxo de String
GEN_DATA = {}

def is_admin(uid):
    return not ADMIN_IDS or uid in ADMIN_IDS

@bot.on(events.NewMessage(pattern='/start'))
async def start(ev):
    if not is_admin(ev.sender_id): return
    buttons = [
        [Button.inline("🔁 Gerar Session String", b"gen_str")],
        [Button.inline("📋 Meus Bots", b"listar_bots")],
        [Button.inline("🔄 Atualizar Sistema", b"att_sys")]
    ]
    await ev.reply("💎 **Inforlozzi AI - Gestão Central**\nEscolha uma opção:", buttons=buttons)

@bot.on(events.CallbackQuery())
async def callback_handler(ev):
    uid = ev.sender_id
    if not is_admin(uid): return
    
    data = ev.data.decode()
    
    if data == "gen_str":
        GEN_DATA[uid] = {'step': 'phone'}
        await ev.edit("📱 **Gerador de String**\nEnvie o número (Ex: `+5511999998888`):", buttons=[Button.inline("❌ Cancelar", b"cancel")])
    
    elif data == "listar_bots":
        # Lógica para listar pastas em /opt/bots
        if not os.path.exists(BOTS_BASE): os.makedirs(BOTS_BASE)
        bots = [d for d in os.listdir(BOTS_BASE) if os.path.isdir(os.path.join(BOTS_BASE, d))]
        txt = "🤖 **Bots Instalados:**\n\n" + ("\n".join(bots) if bots else "Nenhum bot encontrado.")
        await ev.edit(txt, buttons=[Button.inline("⬅️ Voltar", b"voltar")])

    elif data == "voltar":
        await start(ev)

@bot.on(events.NewMessage())
async def message_handler(ev):
    uid = ev.sender_id
    if uid not in GEN_DATA or ev.text.startswith('/'): return
    
    state = GEN_DATA[uid]
    
    if state['step'] == 'phone':
        phone = ev.text.strip()
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            h = await client.send_code_request(phone)
            GEN_DATA[uid].update({'step': 'code', 'phone': phone, 'client': client, 'hash': h.phone_code_hash})
            await ev.reply("📩 **Código enviado!** Digite o código aqui:")
        except Exception as e:
            await ev.reply(f"❌ Erro: {e}")
            del GEN_DATA[uid]

    elif state['step'] == 'code':
        code = ev.text.strip()
        client = state['client']
        try:
            await client.sign_in(state['phone'], code, phone_code_hash=state['hash'])
            string = client.session.save()
            await ev.reply(f"✅ **String Gerada:**\n\n`{string}`")
            await client.disconnect()
            del GEN_DATA[uid]
        except SessionPasswordNeededError:
            GEN_DATA[uid]['step'] = 'pass'
            await ev.reply("🔐 Digite sua senha de 2 etapas:")
        except Exception as e:
            await ev.reply(f"❌ Erro: {e}")

if __name__ == "__main__":
    bot.run_until_disconnected()