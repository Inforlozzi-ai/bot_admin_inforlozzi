import os, logging, asyncio, re, subprocess, shutil, urllib.request, json
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
    except: return False

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
    return ler_env(os.path.join(BOTS_BASE, nome, ".env"), "BOT_NOME", nome)

async def run_cmd(cmd, timeout=90):
    try:
        r = await asyncio.wait_for(asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True), timeout=timeout)
        return (r.stdout + r.stderr)[-2000:] or "OK"
    except asyncio.TimeoutError: return "Tempo esgotado."
    except Exception as e: return "Erro: " + str(e)

def make_dockerfile(path):
    df = ("FROM python:3.12-slim" + NL + "WORKDIR /app" + NL +
          "RUN pip install --no-cache-dir telethon openai pillow python-dotenv" + NL +
          "COPY bot.py ." + NL + 'CMD ["python3","-u","bot.py"]' + NL)
    open(os.path.join(path,"Dockerfile"),"w").write(df)

# â”€â”€â”€ CHAT LISTER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async def listar_chats_bot(nome_bot, tipo="grupos", pagina=0):
    """Executa chat_lister.py dentro do container do userbot e retorna JSON"""
    ctr = "userbot_" + nome_bot
    # garante que o script estÃ¡ dentro do container
    lister_local = os.path.join(BOTS_BASE, nome_bot, "chat_lister.py")
    if not os.path.exists(lister_local):
        try:
            urllib.request.urlretrieve(REPO_RAW + "/chat_lister.py", lister_local)
        except:
            pass
    # copia para o container
    cp_out = await run_cmd(["docker","cp", lister_local, ctr+":/app/chat_lister.py"])
    # executa
    r = await asyncio.wait_for(
        asyncio.to_thread(subprocess.run,
            ["docker","exec", ctr, "python3","/app/chat_lister.py", tipo, str(pagina)],
            capture_output=True, text=True
        ), timeout=30
    )
    try:
        return json.loads(r.stdout)
    except:
        return {"erro": r.stderr[:300] or "Falha ao listar chats", "itens": []}

# â”€â”€â”€ ESTADO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
AGUARDANDO   = {}
NOVO_BOT     = {}
LOGO_BOT     = {}
FWD_CONTEXTO = {}
CHAT_SEL     = {}  # uid -> {nome_bot, modo(source/target), selecionados:[], pagina, tipo}

# â”€â”€â”€ KEYBOARDS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def kb_reply_main():
    return [
        [Button.text("Meus Bots"),    Button.text("Novo Bot"),      Button.text("Atualizar Todos")],
        [Button.text("Iniciar Bot"),  Button.text("Parar Bot"),      Button.text("Reiniciar Bot")],
        [Button.text("Ver Logs"),     Button.text("Remover Bot"),    Button.text("Status Geral")],
        [Button.text("Reencaminhar"), Button.text("Config IA")],
    ]

def kb_lista_bots(acao):
    bots = listar_bots()
    if not bots:
        return [[Button.inline("Nenhum bot instalado",b"noop"),Button.inline("Fechar",b"fechar")]]
    rows = []
    for nome in bots:
        est = "ON" if container_ativo(nome) else "OFF"
        rows.append([Button.inline(est+" - "+nome_exibicao(nome),(acao+"|"+nome).encode())])
    rows.append([Button.inline("Fechar",b"fechar")])
    return rows

def kb_gerenciar_bot(nome):
    return [
        [Button.inline("Iniciar",("iniciar|"+nome).encode()),Button.inline("Parar",("parar|"+nome).encode())],
        [Button.inline("Reiniciar",("reiniciar|"+nome).encode()),Button.inline("Ver Logs",("logs|"+nome).encode())],
        [Button.inline("Editar Nome",("editar_nome|"+nome).encode())],
        [Button.inline("Reencaminhar",("fwd_config|"+nome).encode())],
        [Button.inline("Config IA Bot",("ia_bot|"+nome).encode())],
        [Button.inline("Remover Bot",("remover|"+nome).encode())],
        [Button.inline("Fechar",b"fechar")],
    ]

def kb_reencaminhamento(nome):
    env_path = os.path.join(BOTS_BASE,nome,".env")
    mode = ler_env(env_path,"FORWARD_MODE","copy")
    cl = "Copiar (ativo)" if mode=="copy" else "Copiar"
    fl = "Encaminhar (ativo)" if mode=="forward" else "Encaminhar"
    return [
        [Button.inline("Ver Configuracao",("fwd_ver|"+nome).encode())],
        [Button.inline("IDs de Origem",("fwd_source_menu|"+nome).encode())],
        [Button.inline("ID Grupo Destino",("fwd_target_menu|"+nome).encode())],
        [Button.inline(cl,("fwd_mode|"+nome+"|copy").encode()),
         Button.inline(fl,("fwd_mode|"+nome+"|forward").encode())],
        [Button.inline("Voltar",("gerenciar|"+nome).encode()),Button.inline("Fechar",b"fechar")],
    ]

def kb_tipo_chat(nome, modo):
    """Menu igual imagem 2: User, Premium, Bot, Grupos, Canais, Forums, Buscar"""
    p = modo+"|"+nome
    return [
        [Button.inline("Grupos", ("csel_tipo|"+p+"|grupos").encode()),
         Button.inline("Canais", ("csel_tipo|"+p+"|canais").encode()),
         Button.inline("Bot",    ("csel_tipo|"+p+"|bots").encode())],
        [Button.inline("Buscar @username / ID", ("csel_buscar|"+p).encode())],
        [Button.inline("Digitar IDs manualmente",("csel_manual|"+p).encode())],
        [Button.inline("Voltar",("fwd_config|"+nome).encode()),Button.inline("Fechar",b"fechar")],
    ]

def kb_lista_chats(nome, modo, itens, pagina, total, tipo, selecionados):
    """Lista chats como botÃµes inline â€” imagem 3"""
    por_pag = 8
    rows = []
    for it in itens:
        cid = str(it["id"])
        marcado = "âœ… " if cid in selecionados else ""
        label = marcado + it["nome"][:38]
        rows.append([Button.inline(label, ("csel_pick|"+modo+"|"+nome+"|"+cid).encode())])
    # paginaÃ§Ã£o
    nav = []
    if pagina > 0:
        nav.append(Button.inline("Anterior", ("csel_tipo|"+modo+"|"+nome+"|"+tipo+"|"+str(pagina-1)).encode()))
    if (pagina+1)*por_pag < total:
        nav.append(Button.inline("Proxima", ("csel_tipo|"+modo+"|"+nome+"|"+tipo+"|"+str(pagina+1)).encode()))
    if nav: rows.append(nav)
    # aÃ§Ãµes finais
    qtd = str(len(selecionados))
    rows.append([Button.inline("Confirmar ("+qtd+" selecionados)", ("csel_confirmar|"+modo+"|"+nome).encode())])
    rows.append([Button.inline("Voltar", ("csel_voltar|"+modo+"|"+nome).encode()),
                 Button.inline("Fechar", b"fechar")])
    return rows

def kb_ia_bot(nome):
    env_path = os.path.join(BOTS_BASE,nome,".env")
    troca  = ler_env(env_path,"IA_TROCAR_LOGO","0")=="1"
    filtro = ler_env(env_path,"IA_FILTRO_ATIVO","0")=="1"
    tags   = ler_env(env_path,"IA_FILTRO_TAGS","")
    return [
        [Button.inline("Troca Logo: "+("ON" if troca else "OFF"),("ia_toggle_troca|"+nome).encode())],
        [Button.inline("Filtro IA: "+("ON" if filtro else "OFF"),("ia_toggle_filtro|"+nome).encode())],
        [Button.inline("Tags: "+(tags if tags else "nenhuma"),("ia_set_tags|"+nome).encode())],
        [Button.inline("Logo (foto)",("logo_foto_bot|"+nome).encode()),
         Button.inline("Logo (caminho)",("logo_bot|"+nome).encode())],
        [Button.inline("Remover Logo",("ia_rm_logo|"+nome).encode())],
        [Button.inline("Voltar",("gerenciar|"+nome).encode()),Button.inline("Fechar",b"fechar")],
    ]

def kb_ia_global():
    return [
        [Button.inline("Chave OpenAI (todos)",b"ia_set_key")],
        [Button.inline("Modelo GPT (todos)",b"ia_set_modelo")],
        [Button.inline("Texto Fixo (todos)",b"ia_set_texto")],
        [Button.inline("Reiniciar Todos",b"ia_reiniciar_todos")],
        [Button.inline("Config IA por Bot",b"ia_por_bot")],
        [Button.inline("Fechar",b"fechar")],
    ]

def kb_modelos():
    return [
        [Button.inline("gpt-4o",b"modelo|gpt-4o")],
        [Button.inline("gpt-4o-mini",b"modelo|gpt-4o-mini")],
        [Button.inline("gpt-4-turbo",b"modelo|gpt-4-turbo")],
        [Button.inline("gpt-3.5-turbo",b"modelo|gpt-3.5-turbo")],
        [Button.inline("Voltar",b"ia_voltar"),Button.inline("Fechar",b"fechar")],
    ]

def status_geral():
    bots = listar_bots(); sep = "="*30
    linhas = ["Status Geral - InforLozzi AI", sep]
    for nome in bots:
        est = "ATIVO" if container_ativo(nome) else "PARADO"
        env_path = os.path.join(BOTS_BASE,nome,".env")
        troca  = "TrocaLogo:ON" if ler_env(env_path,"IA_TROCAR_LOGO","0")=="1" else ""
        filtro = "Filtro:ON"    if ler_env(env_path,"IA_FILTRO_ATIVO","0")=="1" else ""
        flags  = " | ".join(f for f in [troca,filtro] if f)
        linhas.append("  "+nome_exibicao(nome)+" ("+nome+") - "+est+(" ["+flags+"]" if flags else ""))
    if not bots: linhas.append("  Nenhum bot instalado.")
    return NL.join(linhas)

PASSOS = [
    ("nome",       "Nome interno do bot (sem espacos, ex: cliente2):"),
    ("api_id",     "API_ID da conta userbot (my.telegram.org):"),
    ("api_hash",   "API_HASH da conta userbot:"),
    ("session",    "SESSION_STRING da conta userbot:"+NL+NL+"Gere com @StringSessionBot ou no VPS"),
    ("bot_token",  "BOT_TOKEN do bot cliente (@BotFather):"+NL+NL+"Ex: 123456:ABC..."),
    ("bot_nome",   "Nome de exibicao do cliente (ex: Joao Silva):"),
    ("admin_ids",  "ADMIN_IDS do bot cliente:"+NL+NL+"Ex: 140226876"),
    ("client_ids", "CLIENT_IDS permitidos (virgula), ou ENTER para nenhum:"),
    ("target",     "TARGET_GROUP_ID (ou deixe em branco para configurar depois):"),
    ("sources",    "SOURCE_CHAT_IDS (virgula), ou ENTER para configurar depois:"),
    ("fw_mode",    "Modo:"+NL+NL+"  copy    - copia sem mostrar origem"+NL+"  forward - encaminha com origem"),
    ("openai_key", "OPENAI_API_KEY (ou ENTER para desativar IA):"),
    ("texto_fixo", "Texto fixo nas mensagens (ou ENTER para nenhum):"),
]

def resumo_novo_bot(dados):
    s = dados.get("session","")[:15]+"..." if len(dados.get("session",""))>15 else dados.get("session","")
    t = dados.get("bot_token","")[:12]+"..." if len(dados.get("bot_token",""))>12 else dados.get("bot_token","")
    return NL.join(["Resumo do Novo Bot","="*30,
        "Nome interno:  "+dados.get("nome",""),"Nome exibicao: "+dados.get("bot_nome",""),
        "API_ID:        "+dados.get("api_id",""),"SESSION:       "+s,"BOT_TOKEN:     "+t,
        "ADMIN_IDS:     "+dados.get("admin_ids",""),"CLIENT_IDS:    "+(dados.get("client_ids","") or "(nenhum)"),
        "Destino:       "+(dados.get("target","0") or "0"),"Origens:       "+(dados.get("sources","") or "todos"),
        "Modo:          "+dados.get("fw_mode","copy"),"IA:            "+("sim" if dados.get("openai_key","") else "nao"),
        "Texto fixo:    "+(dados.get("texto_fixo","") or "(nenhum)"),
    ])

def kb_confirmar():
    return [[Button.inline("Confirmar e Instalar",b"novo_confirmar")],[Button.inline("Cancelar",b"fechar")]]

async def instalar_bot(ev, dados):
    nome = dados["nome"]; bot_dir = os.path.join(BOTS_BASE,nome)
    os.makedirs(bot_dir,exist_ok=True)
    env_content = (
        "API_ID="+dados.get("api_id","")+NL+"API_HASH="+dados.get("api_hash","")+NL+
        "SESSION_STRING="+dados.get("session","")+NL+"BOT_TOKEN="+dados.get("bot_token","")+NL+
        "BOT_NOME="+dados.get("bot_nome","")+NL+"ADMIN_IDS="+dados.get("admin_ids","")+NL+
        "CLIENT_IDS="+dados.get("client_ids","")+NL+"TARGET_GROUP_ID="+dados.get("target","0")+NL+
        "SOURCE_CHAT_IDS="+dados.get("sources","")+NL+"FORWARD_MODE="+dados.get("fw_mode","copy")+NL+
        "OPENAI_API_KEY="+dados.get("openai_key","")+NL+"OPENAI_MODEL=gpt-4o-mini"+NL+
        "IA_LOGO_PATH="+NL+"IA_TEXTO_FIXO="+dados.get("texto_fixo","")+NL+
        "IA_TROCAR_LOGO=0"+NL+"IA_FILTRO_ATIVO=0"+NL+"IA_FILTRO_TAGS="+NL
    )
    open(os.path.join(bot_dir,".env"),"w").write(env_content)
    try:
        urllib.request.urlretrieve(REPO_RAW+"/userbot.py", os.path.join(bot_dir,"bot.py"))
        urllib.request.urlretrieve(REPO_RAW+"/chat_lister.py", os.path.join(bot_dir,"chat_lister.py"))
        make_dockerfile(bot_dir)
        img="userbot_img_"+nome; ctr="userbot_"+nome; ef=os.path.join(bot_dir,".env")
        await ev.respond("Construindo imagem Docker para "+nome+"...")
        await run_cmd(["docker","build","-q","-t",img,bot_dir],timeout=180)
        out = await run_cmd(["docker","run","-d","--name",ctr,"--restart","unless-stopped","--env-file",ef,img])
        await ev.respond("Bot "+dados.get("bot_nome",nome)+" instalado!"+NL+out[:200],buttons=kb_reply_main())
    except Exception as e:
        await ev.respond("Erro ao instalar: "+str(e),buttons=kb_reply_main())

# â”€â”€â”€ /start /menu â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@bot.on(events.NewMessage(pattern="^/start$"))
async def cmd_start(ev):
    if not is_admin(ev.sender_id): return
    await ev.respond("Bot Admin Revendedor - InforLozzi AI"+NL+NL+"Use os botoes abaixo.",buttons=kb_reply_main())

@bot.on(events.NewMessage(pattern="^/menu$"))
async def cmd_menu(ev):
    if not is_admin(ev.sender_id): return
    await ev.respond(status_geral(),buttons=kb_reply_main())

# â”€â”€â”€ REPLY KEYBOARD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@bot.on(events.NewMessage(pattern=r"^(Meus Bots|Novo Bot|Atualizar Todos|Iniciar Bot|Parar Bot|Reiniciar Bot|Ver Logs|Remover Bot|Status Geral|Reencaminhar|Config IA)$"))
async def handler_reply(ev):
    if not is_admin(ev.sender_id): return
    txt=ev.raw_text.strip(); uid=ev.sender_id
    if txt=="Status Geral":
        await ev.respond(status_geral(),buttons=[[Button.inline("Atualizar",b"status_refresh"),Button.inline("Fechar",b"fechar")]])
    elif txt=="Meus Bots":
        await ev.respond("Selecione um bot:",buttons=kb_lista_bots("gerenciar"))
    elif txt=="Novo Bot":
        AGUARDANDO.pop(uid,None); NOVO_BOT[uid]={"passo":0}
        _,perg=PASSOS[0]
        await ev.respond("Instalar Novo Bot"+NL+NL+"[1/"+str(len(PASSOS))+"] "+perg+NL+NL+"Use /menu para cancelar.",buttons=[[Button.inline("Cancelar",b"fechar")]])
    elif txt=="Atualizar Todos":
        await ev.respond("Atualizando bots...")
        try:
            urllib.request.urlretrieve(REPO_RAW+"/userbot.py","/tmp/bot_novo.py")
            linhas=sum(1 for _ in open("/tmp/bot_novo.py")); bots=listar_bots()
            for b in bots:
                shutil.copy("/tmp/bot_novo.py",os.path.join(BOTS_BASE,b,"bot.py"))
                ctr="userbot_"+b; img="userbot_img_"+b; ef=os.path.join(BOTS_BASE,b,".env")
                await run_cmd(["docker","stop",ctr]); await run_cmd(["docker","rm",ctr]); await run_cmd(["docker","rmi",img])
                make_dockerfile(os.path.join(BOTS_BASE,b))
                await run_cmd(["docker","build","-q","-t",img,os.path.join(BOTS_BASE,b)],timeout=180)
                await run_cmd(["docker","run","-d","--name",ctr,"--restart","unless-stopped","--env-file",ef,img])
            await ev.respond("Atualizado: "+str(linhas)+" linhas"+NL+(NL.join("OK "+nome_exibicao(b) for b in bots) if bots else "Nenhum bot."),buttons=[[Button.inline("Fechar",b"fechar")]])
        except Exception as e:
            await ev.respond("Erro: "+str(e),buttons=[[Button.inline("Fechar",b"fechar")]])
    elif txt=="Iniciar Bot":  await ev.respond("Selecione:",buttons=kb_lista_bots("iniciar"))
    elif txt=="Parar Bot":    await ev.respond("Selecione:",buttons=kb_lista_bots("parar"))
    elif txt=="Reiniciar Bot":await ev.respond("Selecione:",buttons=kb_lista_bots("reiniciar"))
    elif txt=="Ver Logs":     await ev.respond("Selecione:",buttons=kb_lista_bots("logs"))
    elif txt=="Remover Bot":  await ev.respond("Selecione:",buttons=kb_lista_bots("remover"))
    elif txt=="Reencaminhar": await ev.respond("Selecione:",buttons=kb_lista_bots("fwd_config"))
    elif txt=="Config IA":
        AGUARDANDO.pop(uid,None); NOVO_BOT.pop(uid,None)
        await ev.respond("Config IA - InforLozzi AI:",buttons=kb_ia_global())

# â”€â”€â”€ FOTO LOGO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@bot.on(events.NewMessage())
async def handler_foto(ev):
    uid=ev.sender_id
    if not is_admin(uid): return
    if not ev.photo: return
    if AGUARDANDO.get(uid)!="ia_logo_foto": return
    AGUARDANDO.pop(uid); nome=LOGO_BOT.pop(uid,None)
    if not nome: await ev.respond("Nenhum bot selecionado.",buttons=kb_ia_global()); return
    logo_path=os.path.join(BOTS_BASE,nome,"logo.jpg")
    try:
        await bot.download_media(ev.photo,file=logo_path)
        atualizar_env(os.path.join(BOTS_BASE,nome,".env"),"IA_LOGO_PATH","/app/logo.jpg")
        ctr="userbot_"+nome
        await run_cmd(["docker","cp",logo_path,ctr+":/app/logo.jpg"])
        await run_cmd(["docker","restart",ctr])
        await ev.respond("Logo salva para "+nome_exibicao(nome)+"! Bot reiniciado.",buttons=kb_ia_bot(nome))
    except Exception as e:
        await ev.respond("Erro: "+str(e),buttons=kb_ia_bot(nome))

# â”€â”€â”€ ENTRADA TEXTO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@bot.on(events.NewMessage())
async def entrada_texto(ev):
    uid=ev.sender_id
    if not is_admin(uid): return
    txt=ev.raw_text.strip()
    if txt.startswith("/"): return
    if ev.photo: return
    if re.match(r"^(Meus Bots|Novo Bot|Atualizar Todos|Iniciar Bot|Parar Bot|Reiniciar Bot|Ver Logs|Remover Bot|Status Geral|Reencaminhar|Config IA)$",txt): return

    if uid in AGUARDANDO:
        acao=AGUARDANDO.pop(uid)
        if acao=="ia_key":
            bots=listar_bots()
            for b in bots: atualizar_env(os.path.join(BOTS_BASE,b,".env"),"OPENAI_API_KEY",txt)
            await ev.respond("Chave atualizada em "+str(len(bots))+" bot(s).",buttons=kb_ia_global())
        elif acao=="ia_texto":
            bots=listar_bots()
            for b in bots: atualizar_env(os.path.join(BOTS_BASE,b,".env"),"IA_TEXTO_FIXO",txt)
            await ev.respond("Texto fixo atualizado.",buttons=kb_ia_global())
        elif acao=="ia_logo":
            nome=LOGO_BOT.pop(uid,None)
            if nome: atualizar_env(os.path.join(BOTS_BASE,nome,".env"),"IA_LOGO_PATH",txt); await ev.respond("Logo definida.",buttons=kb_ia_bot(nome))
        elif acao=="ia_tags":
            nome=FWD_CONTEXTO.pop(uid,(None,None))[1]
            if nome:
                atualizar_env(os.path.join(BOTS_BASE,nome,".env"),"IA_FILTRO_TAGS",txt)
                await run_cmd(["docker","restart","userbot_"+nome])
                await ev.respond("Tags: "+txt+NL+"Bot reiniciado.",buttons=kb_ia_bot(nome))
        elif acao=="csel_buscar":
            ctx=CHAT_SEL.get(uid,{})
            nome=ctx.get("nome"); modo=ctx.get("modo")
            if not nome: return
            await ev.respond("Buscando '"+txt+"'...")
            dados=await listar_chats_bot(nome,"busca:"+txt,0)
            itens=dados.get("itens",[])
            if not itens:
                await ev.respond("Nenhum resultado para '"+txt+"'.",buttons=kb_tipo_chat(nome,modo)); return
            sel=ctx.get("selecionados",[])
            await ev.respond("Resultados para '"+txt+"':",
                buttons=kb_lista_chats(nome,modo,itens,0,len(itens),"busca",sel))
        elif acao=="csel_manual":
            ctx=CHAT_SEL.get(uid,{})
            nome=ctx.get("nome"); modo=ctx.get("modo")
            if not nome: return
            ids=[x.strip() for x in txt.replace(" ","").split(",") if x.strip()]
            env_path=os.path.join(BOTS_BASE,nome,".env")
            if modo=="source":
                atual=ler_env(env_path,"SOURCE_CHAT_IDS","")
                existentes=[x for x in atual.split(",") if x.strip()]
                merged=list(dict.fromkeys(existentes+ids))
                atualizar_env(env_path,"SOURCE_CHAT_IDS",",".join(merged))
                await run_cmd(["docker","restart","userbot_"+nome])
                await ev.respond("Origens atualizadas:"+NL+",".join(merged)+NL+"Bot reiniciado.",buttons=kb_reencaminhamento(nome))
            else:
                atualizar_env(env_path,"TARGET_GROUP_ID",ids[0] if ids else "0")
                await run_cmd(["docker","restart","userbot_"+nome])
                await ev.respond("Destino: "+(ids[0] if ids else "0")+NL+"Bot reiniciado.",buttons=kb_reencaminhamento(nome))
            CHAT_SEL.pop(uid,None)
        elif acao=="fwd_source":
            nome=FWD_CONTEXTO.pop(uid,(None,None))[1]
            if nome: atualizar_env(os.path.join(BOTS_BASE,nome,".env"),"SOURCE_CHAT_IDS",txt); await ev.respond("Origens atualizadas.",buttons=kb_reencaminhamento(nome))
        elif acao=="fwd_target":
            nome=FWD_CONTEXTO.pop(uid,(None,None))[1]
            if nome: atualizar_env(os.path.join(BOTS_BASE,nome,".env"),"TARGET_GROUP_ID",txt); await ev.respond("Destino atualizado.",buttons=kb_reencaminhamento(nome))
        elif acao=="editar_nome":
            nome=FWD_CONTEXTO.pop(uid,(None,None))[1]
            if nome:
                atualizar_env(os.path.join(BOTS_BASE,nome,".env"),"BOT_NOME",txt)
                await run_cmd(["docker","restart","userbot_"+nome])
                await ev.respond("Nome: "+txt+" Bot reiniciado.",buttons=kb_gerenciar_bot(nome))
        return

    if uid not in NOVO_BOT or "passo" not in NOVO_BOT[uid]: return
    dados=NOVO_BOT[uid]; idx=dados["passo"]; chave,_=PASSOS[idx]; val=txt
    if chave=="nome":
        val=re.sub(r"[^a-zA-Z0-9_]","_",val)
        if not val: await ev.respond("Nome invalido:"); return
        if os.path.isdir(os.path.join(BOTS_BASE,val)): await ev.respond("Ja existe:"); return
    elif chave=="api_id":
        if not val.isdigit(): await ev.respond("Apenas numeros:"); return
    elif chave=="session":
        if len(val)<20: await ev.respond("SESSION invalida:"); return
    elif chave=="bot_token":
        if ":" not in val: await ev.respond("TOKEN invalido:"); return
    elif chave=="fw_mode":
        val=val.lower()
        if val not in ("copy","forward"): await ev.respond("copy ou forward:"); return
    elif chave=="target":
        if val and not val.lstrip("-").isdigit(): await ev.respond("Deve ser numero:"); return
        if not val: val="0"
    dados[chave]=val; idx+=1
    if idx<len(PASSOS):
        dados["passo"]=idx; _,perg=PASSOS[idx]
        await ev.respond("["+str(idx+1)+"/"+str(len(PASSOS))+"] "+perg)
    else:
        NOVO_BOT[uid].pop("passo"); NOVO_BOT[uid]["confirmando"]=True
        await ev.respond(resumo_novo_bot(dados),buttons=kb_confirmar())
# â”€â”€â”€ CALLBACKS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@bot.on(events.CallbackQuery)
async def callback(ev):
    uid=ev.sender_id
    if not is_admin(uid): await ev.answer("Sem permissao!",alert=True); return
    d=ev.data.decode("utf-8") if isinstance(ev.data,bytes) else ev.data

    if d=="fechar":
        AGUARDANDO.pop(uid,None); NOVO_BOT.pop(uid,None); LOGO_BOT.pop(uid,None); CHAT_SEL.pop(uid,None)
        try: await ev.delete()
        except: pass; return
    if d=="noop": await ev.answer("Nenhum bot.",alert=True); return
    if d=="status_refresh":
        await ev.edit(status_geral(),buttons=[[Button.inline("Atualizar",b"status_refresh"),Button.inline("Fechar",b"fechar")]]); return
    if d=="novo_confirmar":
        dados=NOVO_BOT.get(uid,{})
        if not dados or "confirmando" not in dados: await ev.edit("Nenhum bot pendente."); return
        NOVO_BOT.pop(uid,None); await ev.edit("Instalando "+dados.get("bot_nome","?")+"...")
        await instalar_bot(ev,dados); return
    if d=="ia_set_key":
        NOVO_BOT.pop(uid,None); AGUARDANDO[uid]="ia_key"
        await ev.edit("Digite a OPENAI_API_KEY:"); return
    if d=="ia_set_modelo": await ev.edit("Selecione o modelo:",buttons=kb_modelos()); return
    if d=="ia_set_texto":
        NOVO_BOT.pop(uid,None); AGUARDANDO[uid]="ia_texto"
        await ev.edit("Digite o texto fixo para TODOS os bots:"); return
    if d=="ia_voltar": await ev.edit("Config IA:",buttons=kb_ia_global()); return
    if d=="ia_reiniciar_todos":
        bots=listar_bots()
        for b in bots: await run_cmd(["docker","restart","userbot_"+b])
        await ev.edit(str(len(bots))+" bot(s) reiniciado(s).",buttons=[[Button.inline("Fechar",b"fechar")]]); return
    if d=="ia_por_bot": await ev.edit("Selecione:",buttons=kb_lista_bots("ia_bot")); return

    if "|" not in d: return
    partes=d.split("|"); acao=partes[0]; nome=partes[1]
    ctr="userbot_"+nome; img="userbot_img_"+nome
    env_path=os.path.join(BOTS_BASE,nome,".env"); label=nome_exibicao(nome)

    # â”€â”€ gerenciar â”€â”€
    if acao=="gerenciar":
        est="ATIVO" if container_ativo(nome) else "PARADO"
        await ev.edit("Gerenciar: "+label+NL+"Status: "+est,buttons=kb_gerenciar_bot(nome))
    elif acao=="iniciar":
        out=await run_cmd(["docker","start",ctr])
        await ev.edit(label+" iniciado:"+NL+out,buttons=[[Button.inline("Voltar",("gerenciar|"+nome).encode()),Button.inline("Fechar",b"fechar")]])
    elif acao=="parar":
        out=await run_cmd(["docker","stop",ctr])
        await ev.edit(label+" parado:"+NL+out,buttons=[[Button.inline("Voltar",("gerenciar|"+nome).encode()),Button.inline("Fechar",b"fechar")]])
    elif acao=="reiniciar":
        out=await run_cmd(["docker","restart",ctr])
        await ev.edit(label+" reiniciado:"+NL+out,buttons=[[Button.inline("Voltar",("gerenciar|"+nome).encode()),Button.inline("Fechar",b"fechar")]])
    elif acao=="logs":
        r=subprocess.run(["docker","logs","--tail","40",ctr],capture_output=True,text=True)
        t2=(r.stdout+r.stderr)[-3000:] or "Sem logs."
        await ev.edit("Logs - "+label+NL+NL+t2,buttons=[[Button.inline("Atualizar",("logs|"+nome).encode()),Button.inline("Voltar",("gerenciar|"+nome).encode()),Button.inline("Fechar",b"fechar")]])
    elif acao=="remover":
        await run_cmd(["docker","stop",ctr]); await run_cmd(["docker","rm",ctr]); await run_cmd(["docker","rmi",img])
        shutil.rmtree(os.path.join(BOTS_BASE,nome),ignore_errors=True)
        await ev.edit("Bot "+label+" removido!",buttons=[[Button.inline("Fechar",b"fechar")]])
    elif acao=="editar_nome":
        NOVO_BOT.pop(uid,None); FWD_CONTEXTO[uid]=("editar_nome",nome); AGUARDANDO[uid]="editar_nome"
        await ev.edit("Nome atual: "+ler_env(env_path,"BOT_NOME",nome)+NL+NL+"Novo nome:")
    elif acao=="modelo":
        bots=listar_bots()
        for b in bots: atualizar_env(os.path.join(BOTS_BASE,b,".env"),"OPENAI_MODEL",nome)
        await ev.edit("Modelo "+nome+" definido.",buttons=kb_ia_global())

    # â”€â”€ IA por bot â”€â”€
    elif acao=="ia_bot": await ev.edit("Config IA - "+label+":",buttons=kb_ia_bot(nome))
    elif acao=="ia_toggle_troca":
        novo="0" if ler_env(env_path,"IA_TROCAR_LOGO","0")=="1" else "1"
        atualizar_env(env_path,"IA_TROCAR_LOGO",novo)
        await run_cmd(["docker","restart",ctr])
        await ev.edit("Troca Logo: "+("ON" if novo=="1" else "OFF")+" Bot reiniciado.",buttons=kb_ia_bot(nome))
    elif acao=="ia_toggle_filtro":
        novo="0" if ler_env(env_path,"IA_FILTRO_ATIVO","0")=="1" else "1"
        atualizar_env(env_path,"IA_FILTRO_ATIVO",novo)
        await run_cmd(["docker","restart",ctr])
        await ev.edit("Filtro IA: "+("ON" if novo=="1" else "OFF")+" Bot reiniciado.",buttons=kb_ia_bot(nome))
    elif acao=="ia_set_tags":
        NOVO_BOT.pop(uid,None); FWD_CONTEXTO[uid]=("ia_tags",nome); AGUARDANDO[uid]="ia_tags"
        tags_atual=ler_env(env_path,"IA_FILTRO_TAGS","")
        await ev.edit("Filtro Conteudo - "+label+NL+NL+"Tags atuais: "+(tags_atual or "nenhuma")+NL+NL+"Digite as tags (virgula):"+NL+"Ex: futebol,filmes,series,anime")
    elif acao=="ia_rm_logo":
        atualizar_env(env_path,"IA_LOGO_PATH","")
        await run_cmd(["docker","restart",ctr])
        await ev.edit("Logo removida. Bot reiniciado.",buttons=kb_ia_bot(nome))
    elif acao=="logo_bot":
        NOVO_BOT.pop(uid,None); LOGO_BOT[uid]=nome; AGUARDANDO[uid]="ia_logo"
        await ev.edit("Caminho da logo para "+label+":"+NL+"Ex: /app/logo.png")
    elif acao=="logo_foto_bot":
        NOVO_BOT.pop(uid,None); LOGO_BOT[uid]=nome; AGUARDANDO[uid]="ia_logo_foto"
        await ev.edit("Envie a logo como FOTO (nao como arquivo)."+NL+"Sera salva em /app/logo.jpg no container.")

    # â”€â”€ SELETOR DE CHAT â€” menus tipo â”€â”€
    elif acao=="fwd_config": await ev.edit("Reencaminhamento - "+label+":",buttons=kb_reencaminhamento(nome))
    elif acao=="fwd_ver":
        src=ler_env(env_path,"SOURCE_CHAT_IDS",""); tgt=ler_env(env_path,"TARGET_GROUP_ID","?")
        mode=ler_env(env_path,"FORWARD_MODE","copy")
        await ev.edit("Config - "+label+NL+NL+"Origens: "+(src or "todas")+NL+"Destino: "+tgt+NL+"Modo: "+("Copiar" if mode=="copy" else "Encaminhar"),buttons=kb_reencaminhamento(nome))
    elif acao=="fwd_source_menu":
        CHAT_SEL[uid]={"nome":nome,"modo":"source","selecionados":[],"pagina":0,"tipo":"grupos"}
        await ev.edit("IDs de Origem - "+label+NL+NL+"Selecione o tipo de chat:",buttons=kb_tipo_chat(nome,"source"))
    elif acao=="fwd_target_menu":
        CHAT_SEL[uid]={"nome":nome,"modo":"target","selecionados":[],"pagina":0,"tipo":"grupos"}
        await ev.edit("Grupo Destino - "+label+NL+NL+"Selecione o tipo de chat:",buttons=kb_tipo_chat(nome,"target"))

elif acao=="csel_tipo":
        # partes: csel_tipo | modo | nome_bot | tipo | [pagina]
        modo2=partes[1]; nome2=partes[2]; tipo=partes[3]
        pagina=int(partes[4]) if len(partes)>4 else 0
        CHAT_SEL[uid]=CHAT_SEL.get(uid,{}); CHAT_SEL[uid].update({"nome":nome2,"modo":modo2,"tipo":tipo,"pagina":pagina})
        if "selecionados" not in CHAT_SEL[uid]: CHAT_SEL[uid]["selecionados"]=[]
        await ev.edit("Carregando "+tipo+"...")
        dados=await listar_chats_bot(nome2,tipo,pagina)
        itens=dados.get("itens",[]); total=dados.get("total",0)
        if "erro" in dados:
            await ev.edit("Erro: "+dados["erro"],buttons=kb_tipo_chat(nome2,modo2)); return
        if not itens:
            await ev.edit("Nenhum "+tipo+" encontrado.",buttons=kb_tipo_chat(nome2,modo2)); return
        sel=CHAT_SEL[uid].get("selecionados",[])
        await ev.edit("Selecione os chats ("+tipo+") - "+nome_exibicao(nome2)+":",
            buttons=kb_lista_chats(nome2,modo2,itens,pagina,total,tipo,sel))

    elif acao=="csel_buscar":
        modo2=partes[1]; nome2=partes[2]
        CHAT_SEL[uid]=CHAT_SEL.get(uid,{"selecionados":[]}); CHAT_SEL[uid].update({"nome":nome2,"modo":modo2})
        AGUARDANDO[uid]="csel_buscar"
        await ev.edit("Digite o nome ou @username para buscar:")

    elif acao=="csel_manual":
        modo2=partes[1]; nome2=partes[2]
        CHAT_SEL[uid]=CHAT_SEL.get(uid,{"selecionados":[]}); CHAT_SEL[uid].update({"nome":nome2,"modo":modo2})
        AGUARDANDO[uid]="csel_manual"
        if modo2=="source":
            await ev.edit("Digite os IDs das origens (virgula):"+NL+"Ex: -100123456,-100789012")
        else:
            await ev.edit("Digite o ID do grupo destino:"+NL+"Ex: -100123456789")

    elif acao=="csel_pick":
        # partes: csel_pick | modo | nome_bot | chat_id
        modo2=partes[1]; nome2=partes[2]; cid=partes[3]
        ctx=CHAT_SEL.get(uid,{"selecionados":[],"pagina":0,"tipo":"grupos","nome":nome2,"modo":modo2})
        sel=ctx.get("selecionados",[])
        if cid in sel: sel.remove(cid)
        else:
            if modo2=="target": sel=[cid]  # destino = apenas 1
            else: sel.append(cid)
        ctx["selecionados"]=sel; CHAT_SEL[uid]=ctx
        tipo=ctx.get("tipo","grupos"); pagina=ctx.get("pagina",0)
        dados=await listar_chats_bot(nome2,tipo,pagina)
        itens=dados.get("itens",[]); total=dados.get("total",0)
        await ev.edit("Selecione os chats ("+tipo+") - "+nome_exibicao(nome2)+":"+NL+"Selecionados: "+str(len(sel)),
            buttons=kb_lista_chats(nome2,modo2,itens,pagina,total,tipo,sel))

    elif acao=="csel_confirmar":
        modo2=partes[1]; nome2=partes[2]
        ctx=CHAT_SEL.pop(uid,{}); sel=ctx.get("selecionados",[])
        env_p=os.path.join(BOTS_BASE,nome2,".env")
        if not sel:
            await ev.edit("Nenhum chat selecionado.",buttons=kb_reencaminhamento(nome2)); return
        if modo2=="source":
            atualizar_env(env_p,"SOURCE_CHAT_IDS",",".join(sel))
            await run_cmd(["docker","restart","userbot_"+nome2])
            await ev.edit("Origens definidas:"+NL+",".join(sel)+NL+"Bot reiniciado.",buttons=kb_reencaminhamento(nome2))
        else:
            atualizar_env(env_p,"TARGET_GROUP_ID",sel[0])
            await run_cmd(["docker","restart","userbot_"+nome2])
            await ev.edit("Destino: "+sel[0]+NL+"Bot reiniciado.",buttons=kb_reencaminhamento(nome2))

    elif acao=="csel_voltar":
        modo2=partes[1]; nome2=partes[2]
        CHAT_SEL.pop(uid,None)
        await ev.edit("Reencaminhamento - "+nome_exibicao(nome2)+":",buttons=kb_reencaminhamento(nome2))

    elif acao=="fwd_mode":
        modo=partes[2]; atualizar_env(env_path,"FORWARD_MODE",modo)
        await run_cmd(["docker","restart",ctr])
        await ev.edit("Modo: "+("Copiar" if modo=="copy" else "Encaminhar")+NL+label+" reiniciado.",buttons=kb_reencaminhamento(nome))

async def main():
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("Bot Admin InforLozzi AI iniciado!")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())