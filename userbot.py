import os, logging, asyncio, re, base64, io
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import InputPeerChannel
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
from collections import deque

# Carrega variáveis do .env
load_dotenv()

# Configuração de Logs
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- VARIÁVEIS DE AMBIENTE ORIGINAIS ---
API_ID         = int(os.environ["API_ID"])
API_HASH       = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]
BOT_NOME       = os.environ.get("BOT_NOME","Bot")
ADMIN_IDS      = set(int(x) for x in os.environ.get("ADMIN_IDS","").split(",") if x.strip().isdigit())
TARGET_GROUP_ID= int(os.environ.get("TARGET_GROUP_ID","0"))
SOURCE_IDS_RAW = os.environ.get("SOURCE_CHAT_IDS","")
SOURCE_IDS     = set(int(x) for x in SOURCE_IDS_RAW.split(",") if x.strip().lstrip("-").isdigit()) if SOURCE_IDS_RAW.strip() else set()
FORWARD_MODE   = os.environ.get("FORWARD_MODE","copy")
OPENAI_KEY     = os.environ.get("OPENAI_API_KEY","")
OPENAI_MODEL   = os.environ.get("OPENAI_MODEL","gpt-4o-mini")
IA_TEXTO_FIXO  = os.environ.get("IA_TEXTO_FIXO","")
LOGO_PATH      = os.environ.get("IA_LOGO_PATH","")

# --- NOVAS VARIÁVEIS (UPGRADE) ---
MAX_CONTEXT      = int(os.environ.get("MAX_CONTEXT_MESSAGES", 5))
IGNORE_KEYWORDS  = [k.strip().lower() for k in os.environ.get("IGNORE_KEYWORDS", "").split(",") if k.strip()]
SCHEDULE_INTERVAL= int(os.environ.get("SCHEDULE_MSG_INTERVAL", 0))
SCHEDULE_TEXT    = os.environ.get("SCHEDULE_MSG_TEXT", "")

# Memória curta para contexto da IA
CHAT_CONTEXT = {}

# Inicialização de Clientes
client_ai = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# Função de Filtro Anti-Spam
def deve_ignorar(texto):
    if not texto: return False
    texto_low = texto.lower()
    return any(keyword in texto_low for keyword in IGNORE_KEYWORDS)

# Função para Processar IA com Histórico
async def obter_texto_ia(chat_id, novo_texto):
    if not client_ai: return novo_texto
    
    if chat_id not in CHAT_CONTEXT:
        CHAT_CONTEXT[chat_id] = deque(maxlen=MAX_CONTEXT)
    
    # Adiciona a mensagem atual ao histórico
    CHAT_CONTEXT[chat_id].append(novo_texto)
    historico = "\n".join(list(CHAT_CONTEXT[chat_id]))
    
    prompt_sistema = f"Você é um curador VIP. Melhore e adapte o conteúdo. Texto fixo obrigatório no final: {IA_TEXTO_FIXO}"
    
    try:
        res = client_ai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": f"Histórico recente de mensagens para contexto:\n{historico}"}
            ]
        )
        return res.choices[0].message.content
    except Exception as e:
        logger.error(f"Erro OpenAI: {e}")
        return novo_texto

# Tarefa de Agendamento em Background
async def scheduled_task():
    if SCHEDULE_INTERVAL > 0 and SCHEDULE_TEXT:
        logger.info(f"Agendador ativo: intervalo de {SCHEDULE_INTERVAL}s")
        while True:
            await asyncio.sleep(SCHEDULE_INTERVAL)
            try:
                if TARGET_GROUP_ID:
                    await userbot.send_message(TARGET_GROUP_ID, SCHEDULE_TEXT)
                    logger.info("Mensagem de engajamento enviada.")
            except Exception as e:
                logger.error(f"Erro no agendamento: {e}")

# Handler Principal de Mensagens
@userbot.on(events.NewMessage(chats=list(SOURCE_IDS) if SOURCE_IDS else None))
async def handler(ev):
    if ev.is_private or not TARGET_GROUP_ID: return
    
    texto_original = ev.text or ""
    
    # 1. Filtro Anti-Spam
    if deve_ignorar(texto_original):
        logger.info("Mensagem ignorada pelos filtros definidos.")
        return

    tmp_path = None
    # 2. Processamento de Imagem com Logo
    if ev.photo and LOGO_PATH and os.path.exists(LOGO_PATH):
        tmp_path = await ev.download_media()
        try:
            img = Image.open(tmp_path).convert("RGB")
            logo = Image.open(LOGO_PATH).convert("RGBA")
            # Redimensiona logo para 25% da largura da imagem
            logo.thumbnail((img.width // 4, img.height // 4))
            img.paste(logo, (20, 20), logo)
            img.save(tmp_path + "_proc.jpg")
            tmp_path = tmp_path + "_proc.jpg"
        except Exception as e:
            logger.error(f"Erro ao processar imagem: {e}")

    # 3. Processamento de IA com Contexto
    texto_final = await obter_texto_ia(ev.chat_id, texto_original)

    # 4. Envio
    try:
        if FORWARD_MODE == "copy":
            await userbot.send_message(TARGET_GROUP_ID, texto_final, file=tmp_path)
        else:
            await ev.forward_to(TARGET_GROUP_ID)
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem: {e}")
    finally:
        # Limpeza de arquivos temporários
        if tmp_path and os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass

# Comando de Status
@userbot.on(events.NewMessage(pattern="^/status$"))
async def cmd_status(ev):
    if ev.sender_id not in ADMIN_IDS: return
    status_msg = (
        f"✅ **{BOT_NOME} Operacional**\n\n"
        f"🧠 Memória IA: {MAX_CONTEXT} msgs\n"
        f"🚫 Filtros Ativos: {len(IGNORE_KEYWORDS)}\n"
        f"⏰ Agendamento: {'Ativo' if SCHEDULE_INTERVAL > 0 else 'Desativado'}"
    )
    await ev.reply(status_msg)

# Loop Principal
if __name__ == "__main__":
    logger.info(f"Iniciando UserBot: {BOT_NOME}")
    if SCHEDULE_INTERVAL > 0:
        userbot.loop.create_task(scheduled_task())
    
    userbot.start()
    userbot.run_until_disconnected()