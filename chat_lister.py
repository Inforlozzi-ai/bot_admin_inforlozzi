#!/usr/bin/env python3
"""
chat_lister.py - roda dentro do container userbot
Uso: python3 chat_lister.py <tipo> [pagina]
tipos: grupos, canais, users, bots, busca:<query>
Saída: JSON [{id, nome, username, tipo}]
"""
import asyncio, json, sys, os
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    User, Chat, Channel,
    InputPeerUser, InputPeerChat, InputPeerChannel
)
from dotenv import load_dotenv

load_dotenv()

API_ID  = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION  = os.environ["SESSION_STRING"]

TIPO   = sys.argv[1] if len(sys.argv) > 1 else "grupos"
PAGINA = int(sys.argv[2]) if len(sys.argv) > 2 else 0
POR_PAG = 20

async def main():
    client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print(json.dumps({"erro": "Nao autorizado"})); return

    resultados = []

    if TIPO.startswith("busca:"):
        query = TIPO[6:]
        async for d in client.iter_dialogs(limit=200):
            nome = d.name or ""
            user = getattr(d.entity, "username", "") or ""
            if query.lower() in nome.lower() or query.lower() in user.lower():
                resultados.append({
                    "id":   d.id,
                    "nome": nome,
                    "username": user,
                    "tipo": _tipo(d.entity)
                })
            if len(resultados) >= 50: break

    else:
        async for d in client.iter_dialogs(limit=500):
            t = _tipo(d.entity)
            ok = False
            if TIPO == "grupos"  and t in ("grupo","supergrupo"): ok = True
            elif TIPO == "canais" and t == "canal": ok = True
            elif TIPO == "users"  and t == "user":  ok = True
            elif TIPO == "bots"   and t == "bot":   ok = True
            elif TIPO == "todos":                   ok = True
            if ok:
                resultados.append({
                    "id":   d.id,
                    "nome": d.name or "?",
                    "username": getattr(d.entity,"username","") or "",
                    "tipo": t
                })

    await client.disconnect()
    inicio = PAGINA * POR_PAG
    pagina = resultados[inicio:inicio + POR_PAG]
    total  = len(resultados)
    print(json.dumps({"total": total, "pagina": PAGINA, "por_pag": POR_PAG, "itens": pagina}, ensure_ascii=False))

def _tipo(ent):
    if isinstance(ent, User):
        return "bot" if ent.bot else "user"
    if isinstance(ent, Chat):
        return "grupo"
    if isinstance(ent, Channel):
        return "canal" if ent.broadcast else "supergrupo"
    return "desconhecido"

asyncio.run(main())
