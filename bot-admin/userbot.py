import os, logging, asyncio, re, base64, io
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import InputPeerChannel
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID         = int(os.environ["API_ID"])
API_HASH       = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]
BOT_TOKEN      = os.environ.get("BOT_TOKEN","")
BOT_NOME       = os.environ.get("BOT_NOME","Bot")
ADMIN_IDS      = set(int(x) for x in os.environ.get("ADMIN_IDS","").split(",") if x.strip().isdigit())
CLIENT_IDS     = set(int(x) for x in os.environ.get("CLIENT_IDS","").split(",") if x.strip().isdigit())
TARGET_GROUP_ID= int(os.environ.get("TARGET_GROUP_ID","0"))
SOURCE_IDS_RAW = os.environ.get("SOURCE_CHAT_IDS","")
SOURCE_IDS     = set(int(x) for x in SOURCE_IDS_RAW.split(",") if x.strip().lstrip("-").isdigit()) if SOURCE_IDS_RAW.strip() else set()
FORWARD_MODE   = os.environ.get("FORWARD_MODE","copy")
OPENAI_KEY     = os.environ.get("OPENAI_API_KEY","")
OPENAI_MODEL   = os.environ.get("OPENAI_MODEL","gpt-4o-mini")
LOGO_PATH      = os.environ.get("IA_LOGO_PATH","")
TEXTO_FIXO     = os.environ.get("IA_TEXTO_FIXO","")
# IA features
IA_TROCAR_LOGO = os.environ.get("IA_TROCAR_LOGO","0") == "1"
IA_FILTRO_ATIVO= os.environ.get("IA_FILTRO_ATIVO","0") == "1"
IA_FILTRO_TAGS = os.environ.get("IA_FILTRO_TAGS","")   # ex: "futebol,filmes,series"

NL = chr(10)

userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
admin_bot = None
if BOT_TOKEN:
    admin_bot = TelegramClient("admin_notify", API_ID, API_HASH)

def is_allowed(uid):
    if not CLIENT_IDS: return True
    return uid in CLIENT_IDS or uid in ADMIN_IDS

# â”€â”€ helpers OpenAI Vision â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def img_to_b64(path):
    with open(path,"rb") as f:
        return base64.b64encode(f.read()).decode()

async def openai_vision(prompt, img_b64, modelo=None):
    import urllib.request, json
    modelo = modelo or OPENAI_MODEL
    payload = json.dumps({
        "model": modelo,
        "max_tokens": 800,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text",  "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + img_b64, "detail": "high"}}
            ]
        }]
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Authorization":"Bearer " + OPENAI_KEY, "Content-Type":"application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error("OpenAI Vision erro: " + str(e))
        return ""

async def ia_filtrar_imagem(img_path):
    """Retorna True se a imagem passa no filtro de conteudo"""
    if not IA_FILTRO_ATIVO or not IA_FILTRO_TAGS or not OPENAI_KEY:
        return True
    tags = [t.strip() for t in IA_FILTRO_TAGS.split(",") if t.strip()]
    if not tags: return True
    lista = ", ".join(tags)
    prompt = (
        "Analise esta imagem. Ela contem algum destes tipos de conteudo: " + lista + "?" + NL +
        "Responda APENAS com SIM ou NAO. Sem explicacoes."
    )
    b64 = await asyncio.to_thread(img_to_b64, img_path)
    resp = await openai_vision(prompt, b64)
    passou = resp.upper().startswith("S")
    logger.info("Filtro IA (" + lista + "): " + resp + " -> " + ("PASSA" if passou else "BLOQUEADO"))
    return passou

async def ia_trocar_logo(img_path):
    """
    Usa Pillow para:
    1. Detectar via Vision a regiao da logo de terceiro (bbox em %)
    2. Cobrir com patch da cor predominante local
    3. Inserir a logo do cliente no canto determinado
    Retorna path da nova imagem ou None se falhar
    """
    if not IA_TROCAR_LOGO or not OPENAI_KEY:
        return None
    try:
        from PIL import Image, ImageDraw, ImageFilter
        import json as _json

        b64 = await asyncio.to_thread(img_to_b64, img_path)

        prompt = (
            "Analise esta imagem de banner/card de IPTV ou streaming." + NL +
            "Identifique TODAS as logos, marcas d'agua ou watermarks de terceiros presentes." + NL +
            "Para cada uma, retorne um JSON array com objetos: " +
            "{\"x\": %, \"y\": %, \"w\": %, \"h\": %} onde os valores sao porcentagens (0-100) da largura/altura da imagem." + NL +
            "Se nao houver logos de terceiros, retorne: []" + NL +
            "Responda APENAS com o JSON array, sem texto adicional."
        )
        resp = await openai_vision(prompt, b64)
        # extrai json da resposta
        match = re.search(r'\[.*?\]', resp, re.DOTALL)
        if not match:
            return None
        regioes = _json.loads(match.group())
        if not regioes:
            return None

        img = await asyncio.to_thread(Image.open, img_path)
        img = img.convert("RGB")
        W, H = img.size
        draw = ImageDraw.Draw(img)

        for reg in regioes:
            x = int(reg.get("x",0) / 100 * W)
            y = int(reg.get("y",0) / 100 * H)
            w = int(reg.get("w",10) / 100 * W)
            h = int(reg.get("h",10) / 100 * H)
            x2, y2 = min(x+w, W), min(y+h, H)
            # pega cor predominante da borda da regiao para pintar por cima
            border = 5
            bx1, by1 = max(0, x-border), max(0, y-border)
            bx2, by2 = min(W, x2+border), min(H, y2+border)
            region_img = img.crop((bx1, by1, bx2, by2))
            region_img = region_img.filter(ImageFilter.GaussianBlur(radius=2))
            avg = region_img.resize((1,1)).getpixel((0,0))
            draw.rectangle([x, y, x2, y2], fill=avg)

        # insere logo do cliente no canto inferior direito
        if LOGO_PATH and os.path.exists(LOGO_PATH):
            def _add_logo(base_img):
                logo = Image.open(LOGO_PATH).convert("RGBA")
                max_logo_w = int(W * 0.18)
                ratio = max_logo_w / logo.width
                logo = logo.resize((max_logo_w, int(logo.height * ratio)), Image.LANCZOS)
                margin = int(W * 0.02)
                pos = (W - logo.width - margin, H - logo.height - margin)
                base_img = base_img.convert("RGBA")
                base_img.paste(logo, pos, logo)
                return base_img.convert("RGB")
            img = await asyncio.to_thread(_add_logo, img)

        out_path = img_path + "_proc.jpg"
        await asyncio.to_thread(img.save, out_path, "JPEG", quality=92)
        return out_path

    except Exception as e:
        logger.error("ia_trocar_logo erro: " + str(e))
        return None

async def inserir_logo_simples(img_path):
    """Insere logo do cliente sem usar IA (quando troca de logo esta desligada)"""
    if not LOGO_PATH or not os.path.exists(LOGO_PATH): return None
    try:
        from PIL import Image
        def _proc():
            img = Image.open(img_path).convert("RGB")
            W, H = img.size
            logo = Image.open(LOGO_PATH).convert("RGBA")
            max_logo_w = int(W * 0.18)
            ratio = max_logo_w / logo.width
            logo = logo.resize((max_logo_w, int(logo.height * ratio)), Image.LANCZOS)
            margin = int(W * 0.02)
            pos = (W - logo.width - margin, H - logo.height - margin)
            base = img.convert("RGBA")
            base.paste(logo, pos, logo)
            out = img_path + "_logo.jpg"
            base.convert("RGB").save(out, "JPEG", quality=92)
            return out
        return await asyncio.to_thread(_proc)
    except Exception as e:
        logger.error("inserir_logo_simples erro: " + str(e))
        return None

# â”€â”€ handler principal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@userbot.on(events.NewMessage())
async def handler(ev):
    cid = ev.chat_id
    # filtra origens
    if SOURCE_IDS and cid not in SOURCE_IDS: return
    if not TARGET_GROUP_ID: return
    if cid == TARGET_GROUP_ID: return

    msg = ev.message
    tmp_path = None

    try:
        # â”€â”€ imagem presente â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if msg.photo or msg.document:
            tmp_path = "/tmp/fwd_media_" + str(ev.id) + ".jpg"
            await userbot.download_media(msg, file=tmp_path)

            # 1) Filtro de conteudo por IA
            if IA_FILTRO_ATIVO and OPENAI_KEY:
                passou = await ia_filtrar_imagem(tmp_path)
                if not passou:
                    logger.info("Mensagem bloqueada pelo filtro IA (chat=" + str(cid) + " msg=" + str(ev.id) + ")")
                    return

            # 2) Processamento de imagem
            final_path = tmp_path
            if IA_TROCAR_LOGO and OPENAI_KEY:
                processada = await ia_trocar_logo(tmp_path)
                if processada: final_path = processada
            elif LOGO_PATH:
                com_logo = await inserir_logo_simples(tmp_path)
                if com_logo: final_path = com_logo

            # 3) Envia imagem processada
            caption = TEXTO_FIXO if TEXTO_FIXO else (msg.text or "")
            await userbot.send_file(TARGET_GROUP_ID, final_path, caption=caption)

        # â”€â”€ so texto â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        elif msg.text or msg.raw_text:
            txt = msg.raw_text or msg.text
            if TEXTO_FIXO: txt = txt + NL + NL + TEXTO_FIXO if txt else TEXTO_FIXO
            await userbot.send_message(TARGET_GROUP_ID, txt)

    except Exception as e:
        logger.error("handler erro: " + str(e))
    finally:
        # limpa arquivos temp
        for p in [tmp_path, (tmp_path + "_proc.jpg") if tmp_path else None, (tmp_path + "_logo.jpg") if tmp_path else None]:
            if p and os.path.exists(p):
                try: os.remove(p)
                except: pass

# â”€â”€ comandos admin bot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@userbot.on(events.NewMessage(pattern="^/status$"))
async def cmd_status(ev):
    if ev.sender_id not in ADMIN_IDS: return
    linhas = [
        "Status - " + BOT_NOME,
        "Modo: " + FORWARD_MODE,
        "Origens: " + (SOURCE_IDS_RAW or "todas"),
        "Destino: " + str(TARGET_GROUP_ID),
        "Logo: " + (LOGO_PATH if LOGO_PATH else "nao definida"),
        "Texto fixo: " + (TEXTO_FIXO or "nenhum"),
        "IA Troca Logo: " + ("ON" if IA_TROCAR_LOGO else "OFF"),
        "IA Filtro: " + ("ON - " + IA_FILTRO_TAGS if IA_FILTRO_ATIVO else "OFF"),
        "Modelo: " + OPENAI_MODEL,
    ]
    await ev.respond(NL.join(linhas))

async def main():
    await userbot.start()
    logger.info(BOT_NOME + " userbot iniciado! Modo=" + FORWARD_MODE +
                " | IA Troca Logo=" + str(IA_TROCAR_LOGO) +
                " | IA Filtro=" + str(IA_FILTRO_ATIVO) +
                " | Tags=" + IA_FILTRO_TAGS)
    await userbot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())