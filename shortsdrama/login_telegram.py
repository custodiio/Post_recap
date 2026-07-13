import os
import asyncio
from telethon import TelegramClient
from dotenv import load_dotenv

# Carrega o arquivo .env
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
load_dotenv(os.path.join(parent_dir, ".env"))

API_ID = int(os.getenv("TELEGRAM_API_ID", "25657270"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "f2d5b9d5c89471989432ef1c2ee22993")
SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "shortsdrama_agent")

async def main():
    # Resolve caminhos da sessão
    if os.path.exists('/home/ubuntu/apps'):
        session_path = f"/home/ubuntu/apps/database/{SESSION_NAME}"
    else:
        session_path = os.path.join(current_dir, SESSION_NAME)
        
    print(f"Iniciando login interativo no Telegram...")
    print(f"Sessão: {session_path}")
    print(f"API_ID: {API_ID}")
    
    client = TelegramClient(session_path, API_ID, API_HASH)
    
    # Inicia o cliente interativamente no terminal
    await client.start()
    
    me = await client.get_me()
    print(f"\n[OK] Login efetuado com sucesso!")
    print(f"Usuário conectado: {me.first_name} {me.last_name or ''} (@{me.username or 'Sem Username'})")
    
    # Se salvou localmente na pasta shortsdrama, faz uma cópia para a pasta raiz (Post_recap)
    # caso o bot seja executado de lá
    import shutil
    local_session_file = f"{session_path}.session"
    parent_session_file = os.path.join(parent_dir, f"{SESSION_NAME}.session")
    
    if os.path.exists(local_session_file):
        try:
            shutil.copy2(local_session_file, parent_session_file)
            print(f"[OK] Cópia da sessão salva na raiz do projeto: {parent_session_file}")
        except Exception as e:
            print(f"[Aviso] Não foi possível copiar para a pasta raiz: {e}")
            
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
