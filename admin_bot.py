import os, logging, asyncio, re, subprocess, shutil, urllib.request
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
API_ID    = int(os.environ["API_ID"])
API_HASH  = os.environ["API_HASH"]
ADMIN_IDS = set(int(x) for x in os.environ.get("ADMIN_IDS","").split(",") if x.strip().isdigit())
BOTS_BASE = os.environ.get("BOTS_BASE", "/opt/bots")
REPO_RAW  = os.environ.get("REPO_RAW", "https://raw.githubusercontent.com/Inforlozzi-ai/bot_admin_inforlozzi/main")

bot = TelegramClient(StringSession(""), API_ID, API_HASH)
NL = chr(10)

def is_admin(uid): return not ADMIN_IDS or uid in ADMIN_IDS

def listar_bots():
    bots = []
    if os.path.isdir(BOTS_BASE):
        for d in sorted(os.listdir(BOTS_BASE)):
            if os.path.isfile(os.path.join(BOTS_BASE, d, "bot.py")):
                bots.append(d)
    return bots

def container_ativo(nome):
    try:
        r = subprocess.run(["docker","ps","--format","{{.Names}}"], capture_output=True, text=True)
        return ("userbot_" + nome) in r.stdout.split()
    except Exception:
        return False

def ler_env(env_path, chave, default=""):
    if not os.path.exists(env_path): return default
    for line in open(env_path).read().splitlines():
        if line.startswith(chave + "="): return line.split("=",1)[1].strip()
    return default

def atualizar_env(env_path, chave, valor):
    content = open(env_path).read() if os.path.exists(env_path) else ""
    if chave + "=" in content:
        content = re.sub("(?m)^" + chave + "=.*", chave + "=" + valor, content)
    else:
        content += NL + chave + "=" + valor
    open(env_path, "w").write(content)

def nome_exibicao(nome):
    env_path = os.path.join(BOTS_BASE, nome, ".env")
    return ler_env(env_path, "BOT_NOME", nome)

# ── REPLY KEYBOARD ───────────────────────────────────────────────
def kb_reply_main():
    return [
        [Button.text("Meus Bots"),    Button.text("Novo Bot"),      Button.text("Atualizar Todos")],
        [Button.text("Iniciar Bot"),  Button.text("Parar Bot"),      Button.text("Reiniciar Bot")],
        [Button.text("Ver Logs"),     Button.text("Remover Bot"),    Button.text("Status Geral")],
        [Button.text("Reencaminhar"), Button.text("Config IA")],
    ]

# ── INLINE KEYBOARDS ─────────────────────────────────────────────
def kb_lista_bots(acao):
    bots = listar_bots()
    if not bots:
        return [[Button.inline("Nenhum bot instalado", b"noop"), Button.inline("Fechar", b"fechar")]]
    linhas = []
    for nome in bots:
        est = "ON" if container_ativo(nome) else "OFF"
        label = est + " - " + nome_exibicao(nome)
        linhas.append([Button.inline(label, (acao + "|" + nome).encode())])
    linhas.append([Button.inline("Fechar", b"fechar")])
    return linhas

def kb_gerenciar_bot(nome):
    return [
        [Button.inline("Iniciar",      ("iniciar|" + nome).encode()),
         Button.inline("Parar",        ("parar|" + nome).encode())],
        [Button.inline("Reiniciar",    ("reiniciar|" + nome).encode()),
         Button.inline("Ver Logs",     ("logs|" + nome).encode())],
        [Button.inline("Editar Nome",  ("editar_nome|" + nome).encode())],
        [Button.inline("Reencaminhar", ("fwd_config|" + nome).encode())],
        [Button.inline("Remover Bot",  ("remover|" + nome).encode())],
        [Button.inline("Fechar",       b"fechar")],
    ]

def kb_reencaminhamento(nome):
    env_path = os.path.join(BOTS_BASE, nome, ".env")
    mode = ler_env(env_path, "FORWARD_MODE", "copy")
    cl = ("Copiar (ativo)" if mode == "copy" else "Copiar")
    fl = ("Encaminhar (ativo)" if mode == "forward" else "Encaminhar")
    return [
        [Button.inline("Ver Configuracao",  ("fwd_ver|" + nome).encode())],
        [Button.inline("IDs de Origem",     ("fwd_source|" + nome).encode())],
        [Button.inline("ID Grupo Destino",  ("fwd_target|" + nome).encode())],
        [Button.inline(cl, ("fwd_mode|" + nome + "|copy").encode()),
         Button.inline(fl, ("fwd_mode|" + nome + "|forward").encode())],
        [Button.inline("Voltar", ("gerenciar|" + nome).encode()),
         Button.inline("Fechar", b"fechar")],
    ]

def kb_ia():
    return [
        [Button.inline("Chave OpenAI",               b"ia_set_key")],
        [Button.inline("Modelo GPT",                  b"ia_set_modelo")],
        [Button.inline("Logo por Bot",                b"ia_set_logo")],
        [Button.inline("Texto Fixo (todos os bots)",  b"ia_set_texto")],
        [Button.inline("Reiniciar Todos os Bots",     b"ia_reiniciar_todos")],
        [Button.inline("Fechar",                      b"fechar")],
    ]

def kb_modelos():
    return [
        [Button.inline("gpt-4o",        b"modelo|gpt-4o")],
        [Button.inline("gpt-4o-mini",   b"modelo|gpt-4o-mini")],
        [Button.inline("gpt-4-turbo",   b"modelo|gpt-4-turbo")],
        [Button.inline("gpt-3.5-turbo", b"modelo|gpt-3.5-turbo")],
        [Button.inline("Voltar",        b"ia_voltar"),
         Button.inline("Fechar",        b"fechar")],
    ]

def status_geral():
    bots = listar_bots()
    sep = "=" * 30
    linhas = ["Status Geral - InforLozzi AI", sep]
    for nome in bots:
        est = "ATIVO" if container_ativo(nome) else "PARADO"
        label = nome_exibicao(nome)
        linhas.append("  " + label + " (" + nome + ") - " + est)
    if not bots: linhas.append("  Nenhum bot instalado.")
    return NL.join(linhas)

async def run_cmd(cmd, timeout=90):
    try:
        r = await asyncio.wait_for(asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True), timeout=timeout)
        return (r.stdout + r.stderr)[-2000:] or "OK"
    except asyncio.TimeoutError: return "Tempo esgotado."
    except Exception as e: return "Erro: " + str(e)

def make_dockerfile(path):
    df = ("FROM python:3.12-slim" + NL + "WORKDIR /app" + NL +
          "RUN pip install --no-cache-dir telethon openai pillow python-dotenv" + NL +
          "COPY bot.py ." + NL + 'CMD ["python3", "-u", "bot.py"]' + NL)
    open(os.path.join(path, "Dockerfile"), "w").write(df)

AGUARDANDO   = {}
NOVO_BOT     = {}
LOGO_BOT     = {}
FWD_CONTEXTO = {}

PASSOS = [
    ("nome",       "Nome interno do bot (sem espacos, ex: cliente2):"),
    ("api_id",     "API_ID da conta userbot (my.telegram.org):"),
    ("api_hash",   "API_HASH da conta userbot:"),
    ("session",    "SESSION_STRING da conta userbot:" + NL + NL + "Gere com @StringSessionBot ou no VPS"),
    ("bot_token",  "BOT_TOKEN do bot cliente (@BotFather):" + NL + NL + "Ex: 123456:ABC..."),
    ("bot_nome",   "Nome de exibicao do cliente (ex: Joao Silva):"),
    ("admin_ids",  "ADMIN_IDS do bot cliente:" + NL + NL + "Ex: 140226876"),
    ("client_ids", "CLIENT_IDS permitidos (virgula), ou ENTER para nenhum:"),
    ("target",     "TARGET_GROUP_ID - ID do grupo destino:" + NL + NL + "Ex: -100123456789"),
    ("sources",    "SOURCE_CHAT_IDS - IDs das origens (virgula), ou ENTER para todos:"),
    ("fw_mode",    "Modo de reencaminhamento:" + NL + NL + "  copy    - copia sem mostrar origem" + NL + "  forward - encaminha com origem"),
    ("openai_key", "OPENAI_API_KEY (ou ENTER para desativar IA):"),
    ("texto_fixo", "Texto fixo nas mensagens (ou ENTER para nenhum):"),
]

def resumo_novo_bot(dados):
    s = dados.get("session","")[:15] + "..." if len(dados.get("session","")) > 15 else dados.get("session","")
    t = dados.get("bot_token","")[:12] + "..." if len(dados.get("bot_token","")) > 12 else dados.get("bot_token","")
    linhas = ["Resumo do Novo Bot", "=" * 30,
        "Nome interno:  " + dados.get("nome",""),
        "Nome exibicao: " + dados.get("bot_nome",""),
        "API_ID:        " + dados.get("api_id",""),
        "SESSION:       " + s,
        "BOT_TOKEN:     " + t,
        "ADMIN_IDS:     " + dados.get("admin_ids",""),
        "CLIENT_IDS:    " + (dados.get("client_ids","") or "(nenhum)"),
        "Destino:       " + (dados.get("target","0") or "0"),
        "Origens:       " + (dados.get("sources","") or "todos"),
        "Modo:          " + dados.get("fw_mode","copy"),
        "IA:            " + ("sim" if dados.get("openai_key","") else "nao"),
        "Texto fixo:    " + (dados.get("texto_fixo","") or "(nenhum)"),
    ]
    return NL.join(linhas)

def kb_confirmar():
    return [[Button.inline("Confirmar e Instalar", b"novo_confirmar")],
            [Button.inline("Cancelar", b"fechar")]]

async def instalar_bot(ev, dados):
    nome = dados["nome"]
    bot_dir = os.path.join(BOTS_BASE, nome)
    os.makedirs(bot_dir, exist_ok=True)
    env_content = (
        "API_ID="          + dados.get("api_id","")      + NL +
        "API_HASH="        + dados.get("api_hash","")    + NL +
        "SESSION_STRING="  + dados.get("session","")     + NL +
        "BOT_TOKEN="       + dados.get("bot_token","")   + NL +
        "BOT_NOME="        + dados.get("bot_nome","")    + NL +
        "ADMIN_IDS="       + dados.get("admin_ids","")   + NL +
        "CLIENT_IDS="      + dados.get("client_ids","")  + NL +
        "TARGET_GROUP_ID=" + dados.get("target","0")     + NL +
        "SOURCE_CHAT_IDS=" + dados.get("sources","")     + NL +
        "FORWARD_MODE="    + dados.get("fw_mode","copy") + NL +
        "OPENAI_API_KEY="  + dados.get("openai_key","")  + NL +
        "OPENAI_MODEL=gpt-4o-mini"                       + NL +
        "IA_LOGO_PATH="                                   + NL +
        "IA_TEXTO_FIXO="   + dados.get("texto_fixo","")  + NL
    )
    open(os.path.join(bot_dir, ".env"), "w").write(env_content)
    try:
        urllib.request.urlretrieve(REPO_RAW + "/bot.py", os.path.join(bot_dir, "bot.py"))
        make_dockerfile(bot_dir)
        img = "userbot_img_" + nome
        ctr = "userbot_" + nome
        env_file = os.path.join(bot_dir, ".env")
        await ev.respond("Construindo imagem Docker para " + nome + "...")
        await run_cmd(["docker","build","-q","-t",img,bot_dir], timeout=180)
        out = await run_cmd(["docker","run","-d","--name",ctr,"--restart","unless-stopped","--env-file",env_file,img])
        await ev.respond("Bot " + dados.get("bot_nome",nome) + " instalado com sucesso!" + NL + out[:200], buttons=kb_reply_main())
    except Exception as e:
        await ev.respond("Erro ao instalar: " + str(e), buttons=kb_reply_main())

# ─── COMANDOS /start e /menu ─────────────────────────────────────
@bot.on(events.NewMessage(pattern="^/start$"))
async def cmd_start(ev):
    if not is_admin(ev.sender_id): return
    await ev.respond(
        "Bot Admin Revendedor - InforLozzi AI" + NL + NL +
        "Use os botoes abaixo para gerenciar seus bots.",
        buttons=kb_reply_main()
    )

@bot.on(events.NewMessage(pattern="^/menu$"))
async def cmd_menu(ev):
    if not is_admin(ev.sender_id): return
    await ev.respond(status_geral(), buttons=kb_reply_main())

# ─── REPLY KEYBOARD — handler com pattern explícito ──────────────
@bot.on(events.NewMessage(pattern=r"^(Meus Bots|Novo Bot|Atualizar Todos|Iniciar Bot|Parar Bot|Reiniciar Bot|Ver Logs|Remover Bot|Status Geral|Reencaminhar|Config IA)$"))
async def handler_reply(ev):
    if not is_admin(ev.sender_id): return
    txt = ev.raw_text.strip()

    if txt == "Status Geral":
        await ev.respond(status_geral(), buttons=[[Button.inline("Atualizar", b"status_refresh"), Button.inline("Fechar", b"fechar")]])
    elif txt == "Meus Bots":
        await ev.respond("Selecione um bot para gerenciar:", buttons=kb_lista_bots("gerenciar"))
    elif txt == "Novo Bot":
        NOVO_BOT[ev.sender_id] = {"passo": 0}
        _, pergunta = PASSOS[0]
        await ev.respond("Instalar Novo Bot" + NL + NL + "[1/" + str(len(PASSOS)) + "] " + pergunta + NL + NL + "Use /menu para cancelar.", buttons=[[Button.inline("Cancelar", b"fechar")]])
    elif txt == "Atualizar Todos":
        await ev.respond("Atualizando bot.py em todos os bots...")
        try:
            urllib.request.urlretrieve(REPO_RAW + "/bot.py", "/tmp/bot_novo.py")
            linhas = sum(1 for _ in open("/tmp/bot_novo.py"))
            bots = listar_bots()
            for b in bots:
                shutil.copy("/tmp/bot_novo.py", os.path.join(BOTS_BASE, b, "bot.py"))
                ctr = "userbot_" + b; img = "userbot_img_" + b
                env_file = os.path.join(BOTS_BASE, b, ".env")
                await run_cmd(["docker","stop",ctr]); await run_cmd(["docker","rm",ctr]); await run_cmd(["docker","rmi",img])
                make_dockerfile(os.path.join(BOTS_BASE, b))
                await run_cmd(["docker","build","-q","-t",img,os.path.join(BOTS_BASE,b)], timeout=180)
                await run_cmd(["docker","run","-d","--name",ctr,"--restart","unless-stopped","--env-file",env_file,img])
            resultado = "bot.py atualizado: " + str(linhas) + " linhas" + NL + (NL.join("OK " + nome_exibicao(b) for b in bots) if bots else "Nenhum bot.")
            await ev.respond(resultado, buttons=[[Button.inline("Fechar", b"fechar")]])
        except Exception as e:
            await ev.respond("Erro: " + str(e), buttons=[[Button.inline("Fechar", b"fechar")]])
    elif txt == "Iniciar Bot":
        await ev.respond("Selecione o bot para iniciar:", buttons=kb_lista_bots("iniciar"))
    elif txt == "Parar Bot":
        await ev.respond("Selecione o bot para parar:", buttons=kb_lista_bots("parar"))
    elif txt == "Reiniciar Bot":
        await ev.respond("Selecione o bot para reiniciar:", buttons=kb_lista_bots("reiniciar"))
    elif txt == "Ver Logs":
        await ev.respond("Selecione o bot para ver os logs:", buttons=kb_lista_bots("logs"))
    elif txt == "Remover Bot":
        await ev.respond("Selecione o bot para remover:", buttons=kb_lista_bots("remover"))
    elif txt == "Reencaminhar":
        await ev.respond("Selecione o bot para configurar reencaminhamento:", buttons=kb_lista_bots("fwd_config"))
    elif txt == "Config IA":
        await ev.respond("Configuracoes de Inteligencia Artificial:", buttons=kb_ia())

# ─── ENTRADA DE TEXTO (wizard + aguardando input) ────────────────
@bot.on(events.NewMessage())
async def entrada_texto(ev):
    uid = ev.sender_id
    if not is_admin(uid): return
    txt = ev.raw_text.strip()
    # ignora comandos e botoes do reply keyboard
    if txt.startswith("/"): return
    if re.match(r"^(Meus Bots|Novo Bot|Atualizar Todos|Iniciar Bot|Parar Bot|Reiniciar Bot|Ver Logs|Remover Bot|Status Geral|Reencaminhar|Config IA)$", txt): return

    # wizard novo bot
    if uid in NOVO_BOT and "passo" in NOVO_BOT[uid]:
        dados = NOVO_BOT[uid]; idx = dados["passo"]
        chave, _ = PASSOS[idx]; val = txt
        if chave == "nome":
            val = re.sub(r"[^a-zA-Z0-9_]", "_", val)
            if not val: await ev.respond("Nome invalido. Use letras, numeros e underline:"); return
            if os.path.isdir(os.path.join(BOTS_BASE, val)): await ev.respond("Bot " + val + " ja existe. Escolha outro nome:"); return
        elif chave == "api_id":
            if not val.isdigit(): await ev.respond("API_ID deve conter apenas numeros:"); return
        elif chave == "session":
            if len(val) < 20: await ev.respond("SESSION_STRING parece invalida:"); return
        elif chave == "bot_token":
            if ":" not in val: await ev.respond("BOT_TOKEN invalido. Formato: 123456:ABC..."); return
        elif chave == "fw_mode":
            val = val.lower()
            if val not in ("copy","forward"): await ev.respond("Digite apenas copy ou forward:"); return
        elif chave == "target":
            if val and not val.lstrip("-").isdigit(): await ev.respond("TARGET_GROUP_ID deve ser numero:"); return
            if not val: val = "0"
        dados[chave] = val; idx += 1
        if idx < len(PASSOS):
            dados["passo"] = idx
            _, pergunta = PASSOS[idx]
            await ev.respond("[" + str(idx+1) + "/" + str(len(PASSOS)) + "] " + pergunta)
        else:
            NOVO_BOT[uid].pop("passo"); NOVO_BOT[uid]["confirmando"] = True
            await ev.respond(resumo_novo_bot(dados), buttons=kb_confirmar())
        return

    # aguardando input especifico
    if uid not in AGUARDANDO: return
    acao = AGUARDANDO.pop(uid)
    if acao == "ia_key":
        bots = listar_bots()
        for b in bots: atualizar_env(os.path.join(BOTS_BASE, b, ".env"), "OPENAI_API_KEY", txt)
        await ev.respond("Chave OpenAI atualizada em " + str(len(bots)) + " bot(s).", buttons=kb_ia())
    elif acao == "ia_texto":
        bots = listar_bots()
        for b in bots: atualizar_env(os.path.join(BOTS_BASE, b, ".env"), "IA_TEXTO_FIXO", txt)
        await ev.respond("Texto fixo atualizado em " + str(len(bots)) + " bot(s).", buttons=kb_ia())
    elif acao == "ia_logo":
        nome = LOGO_BOT.pop(uid, None)
        if nome: atualizar_env(os.path.join(BOTS_BASE, nome, ".env"), "IA_LOGO_PATH", txt); await ev.respond("Logo definida para " + nome_exibicao(nome) + ".", buttons=kb_ia())
    elif acao == "fwd_source":
        nome = FWD_CONTEXTO.pop(uid, (None,None))[1]
        if nome: atualizar_env(os.path.join(BOTS_BASE, nome, ".env"), "SOURCE_CHAT_IDS", txt); await ev.respond("IDs de origem atualizados para " + nome_exibicao(nome) + ".", buttons=kb_reencaminhamento(nome))
    elif acao == "fwd_target":
        nome = FWD_CONTEXTO.pop(uid, (None,None))[1]
        if nome: atualizar_env(os.path.join(BOTS_BASE, nome, ".env"), "TARGET_GROUP_ID", txt); await ev.respond("ID do grupo destino atualizado para " + nome_exibicao(nome) + ".", buttons=kb_reencaminhamento(nome))
    elif acao == "editar_nome":
        nome = FWD_CONTEXTO.pop(uid, (None,None))[1]
        if nome:
            atualizar_env(os.path.join(BOTS_BASE, nome, ".env"), "BOT_NOME", txt)
            await run_cmd(["docker","restart","userbot_" + nome])
            await ev.respond("Nome alterado para: " + txt + NL + "Bot reiniciado.", buttons=kb_gerenciar_bot(nome))

# ─── CALLBACKS INLINE ────────────────────────────────────────────
@bot.on(events.CallbackQuery)
async def callback(ev):
    uid = ev.sender_id
    if not is_admin(uid): await ev.answer("Sem permissao!", alert=True); return
    d = ev.data.decode("utf-8") if isinstance(ev.data, bytes) else ev.data

    if d == "fechar":
        try: await ev.delete()
        except Exception: pass
        return
    if d == "noop": await ev.answer("Nenhum bot instalado.", alert=True); return
    if d == "status_refresh":
        await ev.edit(status_geral(), buttons=[[Button.inline("Atualizar", b"status_refresh"), Button.inline("Fechar", b"fechar")]]); return
    if d == "novo_confirmar":
        dados = NOVO_BOT.get(uid, {})
        if not dados or "confirmando" not in dados: await ev.edit("Nenhum bot pendente."); return
        NOVO_BOT.pop(uid, None)
        await ev.edit("Instalando bot " + dados.get("bot_nome", dados.get("nome","?")) + "...")
        await instalar_bot(ev, dados); return
    if d == "ia_set_key":
        AGUARDANDO[uid] = "ia_key"; await ev.edit("Digite a OPENAI_API_KEY:" + NL + NL + "Sera aplicada em todos os bots."); return
    if d == "ia_set_modelo":
        await ev.edit("Selecione o modelo GPT:", buttons=kb_modelos()); return
    if d == "ia_set_logo":
        await ev.edit("Selecione o bot para definir a logo:", buttons=kb_lista_bots("logo_bot")); return
    if d == "ia_set_texto":
        AGUARDANDO[uid] = "ia_texto"; await ev.edit("Digite o texto fixo para TODOS os bots:"); return
    if d == "ia_voltar":
        await ev.edit("Configuracoes de IA:", buttons=kb_ia()); return
    if d == "ia_reiniciar_todos":
        bots = listar_bots()
        for b in bots: await run_cmd(["docker","restart","userbot_" + b])
        await ev.edit(str(len(bots)) + " bot(s) reiniciado(s).", buttons=[[Button.inline("Fechar", b"fechar")]]); return

    if "|" not in d: return
    partes = d.split("|"); acao2 = partes[0]; nome = partes[1]
    ctr = "userbot_" + nome; img = "userbot_img_" + nome
    env_path = os.path.join(BOTS_BASE, nome, ".env")
    label = nome_exibicao(nome)

    if acao2 == "gerenciar":
        est = "ATIVO" if container_ativo(nome) else "PARADO"
        await ev.edit("Gerenciar: " + label + NL + "Status: " + est, buttons=kb_gerenciar_bot(nome))
    elif acao2 == "iniciar":
        out = await run_cmd(["docker","start",ctr])
        await ev.edit(label + " iniciado:" + NL + out, buttons=[[Button.inline("Voltar", ("gerenciar|" + nome).encode()), Button.inline("Fechar", b"fechar")]])
    elif acao2 == "parar":
        out = await run_cmd(["docker","stop",ctr])
        await ev.edit(label + " parado:" + NL + out, buttons=[[Button.inline("Voltar", ("gerenciar|" + nome).encode()), Button.inline("Fechar", b"fechar")]])
    elif acao2 == "reiniciar":
        out = await run_cmd(["docker","restart",ctr])
        await ev.edit(label + " reiniciado:" + NL + out, buttons=[[Button.inline("Voltar", ("gerenciar|" + nome).encode()), Button.inline("Fechar", b"fechar")]])
    elif acao2 == "logs":
        r = subprocess.run(["docker","logs","--tail","40",ctr], capture_output=True, text=True)
        txt2 = (r.stdout + r.stderr)[-3000:] or "Sem logs."
        await ev.edit("Logs - " + label + NL + NL + txt2, buttons=[[Button.inline("Atualizar", ("logs|" + nome).encode()), Button.inline("Voltar", ("gerenciar|" + nome).encode()), Button.inline("Fechar", b"fechar")]])
    elif acao2 == "remover":
        await run_cmd(["docker","stop",ctr]); await run_cmd(["docker","rm",ctr]); await run_cmd(["docker","rmi",img])
        shutil.rmtree(os.path.join(BOTS_BASE, nome), ignore_errors=True)
        await ev.edit("Bot " + label + " removido com sucesso!", buttons=[[Button.inline("Fechar", b"fechar")]])
    elif acao2 == "editar_nome":
        FWD_CONTEXTO[uid] = ("editar_nome", nome); AGUARDANDO[uid] = "editar_nome"
        atual = ler_env(env_path, "BOT_NOME", nome)
        await ev.edit("Editar nome de exibicao" + NL + NL + "Bot interno: " + nome + NL + "Nome atual: " + atual + NL + NL + "Digite o novo nome:")
    elif acao2 == "modelo":
        bots = listar_bots()
        for b in bots: atualizar_env(os.path.join(BOTS_BASE, b, ".env"), "OPENAI_MODEL", nome)
        await ev.edit("Modelo " + nome + " definido em " + str(len(bots)) + " bot(s).", buttons=kb_ia())
    elif acao2 == "logo_bot":
        LOGO_BOT[uid] = nome; AGUARDANDO[uid] = "ia_logo"
        await ev.edit("Digite o caminho da logo para " + label + ":" + NL + "Ex: /app/logo.jpg")
    elif acao2 == "fwd_config":
        await ev.edit("Reencaminhamento - " + label + ":", buttons=kb_reencaminhamento(nome))
    elif acao2 == "fwd_ver":
        source = ler_env(env_path, "SOURCE_CHAT_IDS", "")
        target = ler_env(env_path, "TARGET_GROUP_ID", "nao definido")
        mode   = ler_env(env_path, "FORWARD_MODE", "copy")
        modo_label = "Copiar (sem mostrar origem)" if mode == "copy" else "Encaminhar (com origem)"
        await ev.edit("Configuracao - " + label + NL + NL + "Origens: " + (source or "todos") + NL + "Destino: " + target + NL + "Modo: " + modo_label, buttons=kb_reencaminhamento(nome))
    elif acao2 == "fwd_source":
        FWD_CONTEXTO[uid] = ("fwd_source", nome); AGUARDANDO[uid] = "fwd_source"
        atual = ler_env(env_path, "SOURCE_CHAT_IDS", "")
        await ev.edit("IDs de Origem - " + label + NL + NL + "Atual: " + (atual or "todos") + NL + NL + "Digite os novos IDs separados por virgula:" + NL + "Ex: -100123456,-100789012")
    elif acao2 == "fwd_target":
        FWD_CONTEXTO[uid] = ("fwd_target", nome); AGUARDANDO[uid] = "fwd_target"
        atual = ler_env(env_path, "TARGET_GROUP_ID", "nao definido")
        await ev.edit("Grupo Destino - " + label + NL + NL + "Atual: " + atual + NL + NL + "Digite o novo ID do grupo destino:" + NL + "Ex: -100123456789")
    elif acao2 == "fwd_mode":
        modo = partes[2]
        atualizar_env(env_path, "FORWARD_MODE", modo)
        await run_cmd(["docker","restart",ctr])
        modo_label = "Copiar" if modo == "copy" else "Encaminhar"
        await ev.edit("Modo alterado para: " + modo_label + NL + "Bot " + label + " reiniciado.", buttons=kb_reencaminhamento(nome))

async def main():
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("Bot Admin Revendedor - InforLozzi AI iniciado!")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
